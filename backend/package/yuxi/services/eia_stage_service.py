"""环评 stages forms 口径字段编辑服务（P2：DB 裁决唯一真相 + 显式导出物化 stages/<stage>.json）。

方案乙同构。编辑边界（需求 doc 定稿决策 3）：add 新增字段 / amend 只改 label、required；
字段标识 name 禁改、文件锚点字段禁删（下游 {{SLOT:}} 寻址与一致性合约依赖）；
未物化 DB 裁决行可撤回。导出走文本级插接（五校准 p1_insert_fields.py 先例）：
括号计数定位 fields 数组 + CRLF 字面量 + 8 空格条目 / 6 空格收口，文件其余字节不动——
stages 实况为 CRLF + indent2 + 无尾换行，禁止 json.load→dumps 全文件重写（bug-417）。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_stage_repository import EiaStageRepository
from yuxi.services.eia_data_service import STAGES, _SKILL_ROOT
from yuxi.utils import logger

STAGES_DIR = _SKILL_ROOT / "references" / "stages"

# 一期新增字段类型白名单：标量口径 + enum: 前缀自由枚举（object/array 是管线复杂形态，专家添加场景不存在）
_BASE_TYPES = {"string", "number", "int", "bool"}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _valid_field_type(t: str) -> bool:
    return t in _BASE_TYPES or t.startswith("enum:")


# ── 文件读取 / 文本级插接（字节纪律核心）─────────────────────────────────────


def _load_stage_doc(stage: str) -> dict[str, Any]:
    p = STAGES_DIR / f"{stage}.json"
    if not p.exists():
        raise KeyError(f"未知 stage: {stage}")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_stage_text(stage: str) -> str:
    p = STAGES_DIR / f"{stage}.json"
    if not p.exists():
        raise KeyError(f"未知 stage: {stage}")
    return p.read_text(encoding="utf-8", newline="")  # newline='' 保 CRLF 原态


def _find_family_fields_span(text: str, fam: str) -> tuple[int, int]:
    """family 键 →（其 family 级 fields 数组开括号位，闭括号后一位）。五校准先例逐字沿用。"""
    key = f'"{fam}": {{'
    i = text.find(key)
    if i < 0:
        raise KeyError(f"family 未找到: {fam}")
    j = text.find('"fields":', i)
    if j < 0:
        raise KeyError(f"family 级 fields 未找到: {fam}")
    open_pos = text.find("[", j)
    depth, k, in_str = 0, open_pos, False
    while True:
        c = text[k]
        if in_str:
            if c == "\\":
                k += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    return open_pos, k + 1
        k += 1


def _field_block_span(segment: str, field_name: str) -> tuple[int, int]:
    """fields 数组片段内按 name 定位字段对象（开括号位，闭括号后一位）。"""
    marker = f'"name": "{field_name}"'
    i = segment.find(marker)
    if i < 0:
        raise KeyError(f"字段未找到: {field_name}")
    op = segment.rfind("{", 0, i)
    depth, k, in_str = 0, op, False
    while True:
        c = segment[k]
        if in_str:
            if c == "\\":
                k += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    return op, k + 1
        k += 1


def _render_fields(items: list[dict[str, Any]], item_indent: str) -> str:
    blocks = []
    for it in items:
        s = json.dumps(it, ensure_ascii=False, indent=2)
        blocks.append(s.replace("\n", "\n" + item_indent))
    return item_indent + (",\n" + item_indent).join(blocks)


def _apply_amend(block: str, patch: dict[str, Any]) -> tuple[str, bool]:
    """字段对象片段内精准替换 label/required；目标值已一致返回 (原文, False)（幂等）。"""
    changed = False
    if "label" in patch:
        want = json.dumps(patch["label"], ensure_ascii=False)
        m = re.search(r'"label": "(?:[^"\\]|\\.)*"', block)
        if not m:
            raise KeyError("label 行未找到")
        if m.group(0) != f'"label": {want}':
            block = block[: m.start()] + f'"label": {want}' + block[m.end() :]
            changed = True
    if "required" in patch:
        want = "true" if patch["required"] else "false"
        m = re.search(r'"required": (true|false)', block)
        if not m:
            raise KeyError("required 行未找到")
        if m.group(1) != want:
            block = block[: m.start()] + f'"required": {want}' + block[m.end() :]
            changed = True
    return block, changed


def _apply_stage_edits(text: str, fam_edits: dict[str, dict[str, Any]]) -> tuple[str, int, int]:
    """按 family span 位置倒序应用（先改后插互不扰动），返回 (新文本, 实插 add 数, 实改 amend 数)。"""
    added = amended = 0
    for fam in sorted(fam_edits, key=lambda f: -text.find(f'"{f}": {{')):
        e = fam_edits[fam]
        op, cl = _find_family_fields_span(text, fam)
        segment = text[op:cl]

        for fn, patch in e["amends"].items():
            fop, fcl = _field_block_span(segment, fn)
            block, changed = _apply_amend(segment[fop:fcl], patch)
            segment = segment[:fop] + block + segment[fcl:]
            if changed:
                amended += 1

        existing = json.loads(segment) if segment.strip() != "[]" else []
        existing_names = {f.get("name") for f in existing}
        adds = [a for a in e["adds"] if a.get("name") not in existing_names]  # 幂等：已物化跳过
        if adds:
            rendered = _render_fields(adds, "        ").replace("\n", "\r\n")
            if segment.strip() == "[]":
                segment = "[\r\n" + rendered + "\r\n      ]"
            else:
                segment = segment[:-1] + ",\r\n" + rendered + "]"
            added += len(adds)

        text = text[:op] + segment + text[cl:]

    if "\r" in text.replace("\r\n", ""):
        raise RuntimeError("插接产物出现孤立 CR（行尾形态混用），拒绝写盘")
    json.loads(text)
    return text, added, amended


class EiaStageService:
    """stages forms 口径字段：文件态 + DB 裁决合并（列表）与显式导出物化（方案乙）。"""

    def __init__(self, repo: EiaStageRepository | None = None) -> None:
        self.repo = repo or EiaStageRepository()

    @staticmethod
    def _edit_dict(r: Any) -> dict[str, Any]:
        """裁决行投影（不依赖模型 to_dict，repo fake 契约保持最小）。"""
        return {
            "stage": r.stage,
            "family_key": r.family_key,
            "field_name": r.field_name,
            "edit_kind": r.edit_kind,
            "field": dict(r.field_json),
            "decided_by": r.decided_by,
        }

    # ── 列表（合并态）─────────────────────────────────────────────────────

    async def list_stage_forms(self, stage: str | None = None) -> dict[str, Any]:
        """file 锚点字段 + DB 裁决合并：add 追加条目、amend 以 db_edit 覆盖层标注，pending 判物化态。"""
        if stage is not None and stage not in STAGES:
            raise KeyError(f"未知 stage: {stage}")
        stages = (stage,) if stage else STAGES
        edits = await self.repo.list_edits(stage)
        by_fam: dict[tuple[str, str], list[Any]] = {}
        for r in edits:
            by_fam.setdefault((r.stage, r.family_key), []).append(r)

        def _merge() -> dict[str, Any]:
            out: dict[str, Any] = {"stages": {}}
            for s in stages:
                doc = _load_stage_doc(s)
                fams: dict[str, Any] = {}
                for fk, f in doc.get("forms", {}).items():
                    rows = by_fam.get((s, fk), [])
                    fields: list[dict[str, Any]] = []
                    file_names = set()
                    for fd in f.get("fields", []):
                        entry = {**fd, "source": "file"}
                        file_names.add(fd.get("name"))
                        for r in rows:
                            if r.edit_kind == "amend" and r.field_name == fd.get("name"):
                                pending = any(
                                    k in r.field_json and r.field_json[k] != fd.get(k) for k in ("label", "required")
                                )
                                entry["db_edit"] = {
                                    "edit_kind": "amend",
                                    "field": dict(r.field_json),
                                    "pending": pending,
                                    "decided_by": r.decided_by,
                                }
                        fields.append(entry)
                    for r in rows:
                        if r.edit_kind == "add":
                            fields.append(
                                {
                                    **r.field_json,
                                    "source": "db",
                                    "edit_kind": "add",
                                    "pending": r.field_name not in file_names,
                                    "decided_by": r.decided_by,
                                }
                            )
                    fams[fk] = {
                        **{k: f.get(k) for k in ("label", "file", "required", "chapters", "note")},
                        "fields": fields,
                    }
                out["stages"][s] = {"families": fams}
            return out

        return await run_in_threadpool(_merge)

    # ── 保存 / 撤回（DB 裁决）─────────────────────────────────────────────

    async def save_stage_field(
        self, stage: str, family_key: str, payload: dict[str, Any], username: str
    ) -> dict[str, Any]:
        doc = await run_in_threadpool(_load_stage_doc, stage)
        forms = doc.get("forms", {})
        if family_key not in forms:
            raise KeyError(f"未知口径族: {family_key}")
        fam_fields = forms[family_key].get("fields", [])
        kind = payload.get("edit_kind")

        if kind == "add":
            name = payload.get("name")
            label = payload.get("label")
            ftype = payload.get("type")
            if not isinstance(name, str) or not _NAME_RE.match(name):
                raise ValueError("字段标识须为小写字母开头的 snake_case（小写字母/数字/下划线），导出后不可修改")
            if any(f.get("name") == name for f in fam_fields):
                raise ValueError(f"字段标识已存在: {name}")
            if not isinstance(label, str) or not label.strip():
                raise ValueError("中文名称必填")
            if not isinstance(ftype, str) or not _valid_field_type(ftype):
                raise ValueError("类型仅支持 string/number/int/bool 或 enum: 前缀")
            field_json: dict[str, Any] = {
                "name": name,
                "label": label.strip(),
                "type": ftype,
                "required": bool(payload.get("required", False)),
            }
            if payload.get("unit"):
                field_json["unit"] = str(payload["unit"])
            if payload.get("note"):
                field_json["note"] = str(payload["note"])
            row = await self.repo.upsert_edit(stage, family_key, name, "add", field_json, username)
            return {"edit": self._edit_dict(row)}

        if kind == "amend":
            fn = payload.get("field_name")
            if "name" in payload and payload["name"] != fn:
                raise ValueError("字段标识不可修改（SLOT 寻址依赖）；如需改名请走工程侧评审")
            if not isinstance(fn, str) or not fn:
                raise ValueError("amend 须提供 field_name")
            if not any(f.get("name") == fn for f in fam_fields):
                raise KeyError(f"字段未找到: {fn}")
            patch = {k: payload[k] for k in ("label", "required") if k in payload}
            if not patch:
                raise ValueError("amend 需至少提供 label 或 required")
            if "label" in patch and (not isinstance(patch["label"], str) or not patch["label"].strip()):
                raise ValueError("中文名称必填")
            row = await self.repo.upsert_edit(stage, family_key, fn, "amend", patch, username)
            return {"edit": self._edit_dict(row)}

        raise ValueError("edit_kind 仅支持 add/amend")

    async def delete_stage_field(self, stage: str, family_key: str, field_name: str) -> dict[str, Any]:
        """撤回未物化裁决行（仅草稿态；文件锚点不受影响）。"""
        deleted = await self.repo.delete_edit(stage, family_key, field_name)
        if not deleted:
            raise KeyError(f"无此待导出裁决行: {field_name}")
        return {"deleted": True}

    # ── 导出物化（admin）─────────────────────────────────────────────────

    async def export_stage_forms(self, stage: str | None, username: str) -> dict[str, Any]:
        """DB 裁决 → stages/<stage>.json 文本级插接；幂等（已物化跳过，字节不动）。"""
        edits = await self.repo.list_edits(stage)
        if not edits:
            raise ValueError("无待导出的口径字段裁决")
        by_stage: dict[str, dict[str, dict[str, Any]]] = {}
        for r in edits:
            fam = by_stage.setdefault(r.stage, {}).setdefault(r.family_key, {"adds": [], "amends": {}})
            if r.edit_kind == "add":
                fam["adds"].append(dict(r.field_json))
            else:
                fam["amends"][r.field_name] = dict(r.field_json)

        def _export_one(s: str, fam_edits: dict[str, dict[str, Any]]) -> dict[str, int]:
            original = _load_stage_text(s)
            text, added, amended = _apply_stage_edits(original, fam_edits)
            skipped = sum(len(e["adds"]) + len(e["amends"]) for e in fam_edits.values()) - added - amended
            if text != original:
                (STAGES_DIR / f"{s}.json").write_text(text, encoding="utf-8", newline="")
            return {"added": added, "amended": amended, "skipped": skipped}

        results = {s: await run_in_threadpool(_export_one, s, fam_edits) for s, fam_edits in by_stage.items()}
        total_added = sum(r["added"] for r in results.values())
        total_amended = sum(r["amended"] for r in results.values())
        logger.info(
            f"[eia-stage] 导出物化口径字段 +{total_added} add / ~{total_amended} amend"
            f" → {len(results)} 个 stage 文件（by {username}）"
        )
        return {
            "results": results,
            "paths": [f"references/stages/{s}.json" for s in results],
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


_service: EiaStageService | None = None


def get_eia_stage_service() -> EiaStageService:
    global _service
    if _service is None:
        _service = EiaStageService()
    return _service
