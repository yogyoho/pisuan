"""环评 formulas 参数参考值编辑服务（P3-1：DB 覆盖唯一真相 + 显式导出物化 formulas.json）。

方案乙同构。编辑边界：仅 user_input 参数的参考值（value/note）；expr / derived_slots /
outputs / 结构恒只读（写手按 expr 复算，覆盖结构会破坏冻结口径）。导出走文本级插接：
inputs 每项单行紧凑对象，仅目标 input 行内注入/替换 `"value": <规范化值>`，
文件其余字节不动（stages bug-417 同款教训）。值规范化：DB 存 TEXT，导出时
json.loads 可解析则用规范化 JSON 值（"0.6"→0.6），否则按 JSON 字符串字面量写入——
同状态重复导出 byte-identical（幂等）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_formula_repository import EiaFormulaRepository
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.utils import logger

FORMULAS_PATH = _SKILL_ROOT / "references" / "formulas.json"


def _load_formulas_text() -> str:
    if not FORMULAS_PATH.exists():
        raise KeyError(f"formulas.json 未找到: {FORMULAS_PATH}")
    return FORMULAS_PATH.read_text(encoding="utf-8", newline="")


def _normalize_value(value_text: str) -> str:
    """TEXT → JSON 字面量：可解析则规范化（数字保持数字），否则字符串字面量。"""
    try:
        return json.dumps(json.loads(value_text), ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        return json.dumps(value_text, ensure_ascii=False)


def _input_line_span(text: str, formula_id: str, input_name: str) -> tuple[int, int]:
    """定位目标 input 单行（formula 块作用域内字面寻址；找不到抛 KeyError）。"""
    fid_marker = f'"id": "{formula_id}"'
    start = text.find(fid_marker)
    if start < 0:
        raise KeyError(f"未知公式: {formula_id}")
    end = text.find('"id": "', start + len(fid_marker))
    if end < 0:
        end = len(text)

    marker = f'{{"name": "{input_name}", '
    i = text.find(marker, start, end)
    if i < 0:
        raise KeyError(f"未知参数: {formula_id}.{input_name}")
    line_start = text.rfind("\n", 0, i) + 1
    line_end = text.find("\n", i)
    if line_end < 0:
        line_end = len(text)
    return line_start, line_end


def _splice_value(line: str, input_name: str, json_value: str) -> tuple[str, bool]:
    """行内注入/替换 value；返回（新行，是否变化）。

    注入点固定在 {"name": "<input>", 之后——插接最省字节、diff 最小；
    已有 value 时用 JSON raw_decode 精确定位值跨度后整段替换。
    """
    pos = line.find('"value": ')
    if pos < 0:
        indent = len(line) - len(line.lstrip(" "))  # 行含缩进，注入点按缩进宽偏移
        inject_at = indent + len(f'{{"name": "{input_name}", ')
        return line[:inject_at] + f'"value": {json_value}, ' + line[inject_at:], True
    dec = json.JSONDecoder()
    val_pos = pos + len('"value": ')
    _, val_end = dec.raw_decode(line, val_pos)
    new_line = line[:val_pos] + json_value + line[val_end:]
    return new_line, new_line != line


class EiaFormulaService:
    """formulas 参数参考值：list / set / clear / export（导出 admin 显式触发）。"""

    def __init__(self, repo: EiaFormulaRepository | None = None):
        self.repo = repo or EiaFormulaRepository()

    async def list_formulas(self) -> dict[str, Any]:
        """锚点 + DB 覆盖合并视图；override 已与锚点物化值一致时 pending=False。"""
        doc = json.loads(_load_formulas_text())
        by_key = {(r.formula_id, r.input_name): r for r in await self.repo.list_overrides()}

        def _override(fid: str, inp: dict[str, Any]) -> dict[str, Any] | None:
            r = by_key.get((fid, inp["name"]))
            if r is None:
                return None
            pending = inp.get("value") != json.loads(_normalize_value(r.value))
            return {
                "value": r.value,
                "note": r.note,
                "decided_by": r.decided_by,
                "updated_at": r.updated_at.isoformat() if hasattr(r.updated_at, "isoformat") else r.updated_at,
                "pending": pending,
            }

        formulas = [
            {**f, "inputs": [{**inp, "override": _override(f["id"], inp)} for inp in f["inputs"]]}
            for f in doc.get("formulas", [])
        ]
        pending_count = sum(
            1 for f in formulas for inp in f["inputs"] if inp["override"] and inp["override"]["pending"]
        )
        return {
            "formulas": formulas,
            "derived_slots": doc.get("derived_slots", []),
            "pending_count": pending_count,
        }

    async def set_input_value(
        self, formula_id: str, input_name: str, value: str, note: str | None, username: str
    ) -> dict[str, Any]:
        """参考值裁决落库（同键覆盖）；锚点寻址校验先行。"""
        doc = json.loads(_load_formulas_text())
        formula = next((f for f in doc.get("formulas", []) if f["id"] == formula_id), None)
        if formula is None:
            raise KeyError(f"未知公式: {formula_id}")
        inp = next((i for i in formula.get("inputs", []) if i["name"] == input_name), None)
        if inp is None:
            raise KeyError(f"未知参数: {formula_id}.{input_name}")
        if inp.get("type") != "user_input":
            raise ValueError(f"仅 user_input 参数可设参考值: {input_name}({inp.get('type')})")
        if not value or not value.strip():
            raise ValueError("参考值不能为空")

        row = await self.repo.upsert_override(formula_id, input_name, value, note, username)
        logger.info(f"[eia-formula] 参考值裁决 {formula_id}.{input_name} = {value!r}（by {username}）")
        return {
            "id": row.id,
            "formula_id": row.formula_id,
            "input_name": row.input_name,
            "value": row.value,
            "note": row.note,
            "decided_by": row.decided_by,
            "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else row.updated_at,
        }

    async def clear_input_value(self, formula_id: str, input_name: str) -> bool:
        """撤回覆盖行（文件锚点不受影响）。"""
        return await self.repo.delete_override(formula_id, input_name)

    async def export_formulas(self, username: str) -> dict[str, Any]:
        """DB 覆盖 → formulas.json 行级插接；幂等（已物化同值跳过，字节不动）。"""
        overrides = await self.repo.list_overrides()
        if not overrides:
            raise ValueError("无待导出的参数参考值覆盖")

        def _export_one() -> dict[str, dict[str, int]]:
            original = _load_formulas_text()
            text = original
            results: dict[str, dict[str, int]] = {}
            for r in overrides:
                stat = results.setdefault(r.formula_id, {"materialized": 0, "skipped": 0})
                line_start, line_end = _input_line_span(text, r.formula_id, r.input_name)
                new_line, changed = _splice_value(
                    line=text[line_start:line_end], input_name=r.input_name, json_value=_normalize_value(r.value)
                )
                if changed:
                    text = text[:line_start] + new_line + text[line_end:]
                    stat["materialized"] += 1
                else:
                    stat["skipped"] += 1
            if text != original:
                FORMULAS_PATH.write_text(text, encoding="utf-8", newline="")
            return results

        results = await run_in_threadpool(_export_one)
        total = sum(s["materialized"] for s in results.values())
        skipped = sum(s["skipped"] for s in results.values())
        logger.info(f"[eia-formula] 导出物化参考值 +{total}（跳过已同值 {skipped}）→ formulas.json（by {username}）")
        return {
            "results": results,
            "paths": ["references/formulas.json"],
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


_service: EiaFormulaService | None = None


def get_eia_formula_service() -> EiaFormulaService:
    global _service
    if _service is None:
        _service = EiaFormulaService()
    return _service
