"""环评标准条目人工核实服务（P3：DB 运营唯一真相 + 显式导出物化 standards_index.json）。

方案乙同构（见 docs/vibe/2026-10-10-eia-standard-review.md）：
  - 核实裁决（confirm = 编号/年份/名称对照标准原文无误）落 DB，导出仅翻转被裁决条目的
    needs_verification/verified 两字段，文件其余内容 round-trip 字节不变
  - 无 import：初始态即文件态（41 条 nv 全是待办），DB 从零起步；文件常驻无开关
  - note 仅 DB 留档；限值断言授权仍由 limit_tables 数据在位情况决定（LLM 写作纪律）
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool

from pisuan.repositories.eia_standard_repository import EiaStandardRepository
from pisuan.services.eia_data_service import _SKILL_ROOT
from pisuan.storage.postgres.models_domain_factory import EiaStandardReview
from pisuan.utils import logger
from pisuan.utils.datetime_utils import format_utc_datetime, utc_now_naive

STANDARDS_INDEX_PATH = _SKILL_ROOT / "references" / "standards_index.json"

# 核实动作白名单（一期唯一：编号/年份/名称对照标准原文核实无误）
_VALID_ACTIONS = {"confirm"}

# 语料引用码噪声归一：GB/15618-2018 ↔ GB 15618-2018 ↔ GB15618—2018 视为同一标准
_STD_NOISE_RE = re.compile(r"[\s\-—–/]+")


def _norm_std(code: str) -> str:
    return _STD_NOISE_RE.sub("", code).upper()


def _load_standards_index() -> dict[str, Any]:
    """注册表 standards_index.json（只读，核实裁决的对照面）。"""
    return json.loads(STANDARDS_INDEX_PATH.read_text(encoding="utf-8"))


def _validate_review(payload: dict[str, Any]) -> None:
    """核实载荷校验（纯函数）：action 白名单 + note 字符串，未知字段拒收。"""
    unknown = set(payload) - {"action", "note"}
    if unknown:
        raise ValueError(f"未知核实字段: {sorted(unknown)}（允许 {{'action', 'note'}}）")
    if payload.get("action") not in _VALID_ACTIONS:
        raise ValueError(f"action 须为 {_VALID_ACTIONS}（限值档位录入留后续，见设计文档）")
    note = payload.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError("note 须为字符串")


# 限值查找表行结构（服务端唯一权威）：PUT 校验与前端可编辑表格渲染共用；
# type: str → 非空白字符串（去首尾空白），number → int/float（拒收 bool/数值字符串）
LIMIT_TABLE_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "gb3096_zone_limits": {  # GB 3096 声环境质量标准：功能区限值
        "category": {"label": "声环境功能区", "type": "str", "required": True},
        "day": {"label": "昼间", "type": "number", "required": True},
        "night": {"label": "夜间", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
    "gb12348_boundary_limits": {  # GB 12348 工业企业厂界环境噪声排放标准：厂界限值
        "category": {"label": "厂界外声环境功能区", "type": "str", "required": True},
        "day": {"label": "昼间", "type": "number", "required": True},
        "night": {"label": "夜间", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
    "gb3095_concentration_limits": {  # GB 3095 环境空气质量标准：污染物浓度限值
        "pollutant": {"label": "污染物", "type": "str", "required": True},
        "period": {"label": "时间周期", "type": "str", "required": True},
        "grade": {"label": "级别", "type": "str", "required": True},
        "limit_value": {"label": "浓度限值", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
    "gb3838_category_limits": {  # GB 3838 地表水环境质量标准：水域功能分类限值
        "category": {"label": "水域功能类别", "type": "str", "required": True},
        "pollutant": {"label": "污染物", "type": "str", "required": True},
        "limit_value": {"label": "标准限值", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
    "gbt14848_category_limits": {  # GB/T 14848 地下水质量标准：质量分类限值
        "category": {"label": "地下水质量类别", "type": "str", "required": True},
        "pollutant": {"label": "污染物", "type": "str", "required": True},
        "limit_value": {"label": "标准限值", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
    "gb20426_emission_limits": {  # GB 20426 煤炭工业污染物排放标准：排放限值
        "pollutant": {"label": "污染物", "type": "str", "required": True},
        "phase": {"label": "时段", "type": "str", "required": True},
        "limit_value": {"label": "排放限值", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
    "gbt13201_a_value": {  # GB/T 13201 大气污染物排放标准技术方法：A 值分区
        "region_type": {"label": "区域类型", "type": "str", "required": True},
        "a_value": {"label": "A 值", "type": "number", "required": True},
        "unit": {"label": "单位", "type": "str", "required": True},
    },
}


def _validate_limit_rows(table_key: str, rows: Any) -> list[dict[str, Any]]:
    """限值行载荷校验（纯函数）：未知表 KeyError；行规范化后返回（去空白/丢未注册键）。"""
    schema = LIMIT_TABLE_SCHEMAS.get(table_key)
    if schema is None:
        raise KeyError(f"限值表不存在: {table_key}")
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows 须为非空数组")
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {i + 1} 行须为对象")
        unknown = set(raw) - set(schema)
        if unknown:
            raise ValueError(f"第 {i + 1} 行未知限值字段: {sorted(unknown)}（允许 {sorted(schema)}）")
        row: dict[str, Any] = {}
        for key, spec in schema.items():
            v = raw.get(key)
            if v is None or (isinstance(v, str) and not v.strip()):
                if spec["required"]:
                    raise ValueError(f"第 {i + 1} 行缺少必填字段: {key}")
                continue
            if spec["type"] == "str":
                if not isinstance(v, str):
                    raise ValueError(f"第 {i + 1} 行字段 {key} 须为字符串")
                row[key] = v.strip()
            else:
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise ValueError(f"第 {i + 1} 行字段 {key} 须为数值")
                row[key] = v
        out.append(row)
    return out


class EiaStandardService:
    """标准条目人工核实：核实裁决 / 导出物化（翻转 nv/verified 字段）。"""

    def __init__(self) -> None:
        self.repo = EiaStandardRepository()

    def _cited_counter(self, corpus_meta: dict[str, Any]) -> Counter:
        """语料引用面：31 份报告 standards_cited 按归一码聚合。"""
        counter: Counter = Counter()
        for m in corpus_meta.get("reports", {}).values():
            for c in m.get("standards_cited") or []:
                counter[_norm_std(c)] += 1
        return counter

    async def list_standards(self) -> dict[str, Any]:
        """62 条总览：文件态只读 + DB 裁决合并 + 语料引用数 + counts 汇总。"""
        from pisuan.services.eia_meta_service import _load_corpus_meta

        doc = await run_in_threadpool(_load_standards_index)
        corpus_meta = await run_in_threadpool(_load_corpus_meta)
        cited = self._cited_counter(corpus_meta)
        rows = {r.code: r for r in await self.repo.list_reviews()}
        items: list[dict[str, Any]] = []
        counts = {"total": 0, "needs_verification": 0, "confirmed": 0, "limit_tables_pending": 0}
        for s in doc.get("standards", []):
            counts["total"] += 1
            row = rows.get(s["code"])
            if s.get("needs_verification"):
                counts["needs_verification"] += 1
            if row is not None:
                counts["confirmed"] += 1
            items.append(
                {
                    "code": s["code"],
                    "title": s.get("title"),
                    "role": s.get("role"),
                    "chapters": s.get("chapters"),
                    "tier": s.get("tier"),
                    "needs_verification": bool(s.get("needs_verification")),
                    "verified": bool(s.get("verified")),
                    "origin": s.get("origin"),
                    "note": s.get("note"),
                    "cited_count": cited.get(_norm_std(s["code"]), 0),
                    "review": {
                        "action": row.action if row else None,
                        "note": row.note if row else None,
                        "decided_by": row.decided_by if row else None,
                        "decided_at": format_utc_datetime(row.decided_at) if row else None,
                    },
                }
            )
        for name, t in doc.get("limit_tables", {}).items():
            if isinstance(t, dict) and t.get("needs_verification"):
                counts["limit_tables_pending"] += 1
        return {"items": items, "total": counts["total"], "counts": counts}

    async def list_limit_tables(self) -> dict[str, Any]:
        """limit_tables：文件态 + DB 录入行合并（DB 已录入的表整体覆盖文件锚点行）+ 行结构 schemas。"""
        doc = await run_in_threadpool(_load_standards_index)
        by_table: dict[str, list] = {}
        for r in await self.repo.list_rows():
            by_table.setdefault(r.table_key, []).append(r)

        def _db_fields(rows: list) -> dict[str, Any]:
            first = rows[0]
            return {
                "rows": [r.row_json for r in rows],
                "source": "db",
                "decided_by": first.decided_by,
                "updated_at": format_utc_datetime(first.updated_at) if first.updated_at else None,
            }

        tables: dict[str, Any] = {}
        for name, t in doc.get("limit_tables", {}).items():
            if not isinstance(t, dict):  # _comment 等说明项原样透传
                tables[name] = t
                continue
            merged = dict(t)
            rows = by_table.get(name)
            merged.update(_db_fields(rows) if rows else {"source": "file"})
            tables[name] = merged
        for key, rows in by_table.items():  # DB 已录入而文件注册表漂移掉的表：仍须露出
            if key not in tables:
                tables[key] = _db_fields(rows)
        return {"limit_tables": tables, "schemas": LIMIT_TABLE_SCHEMAS}

    async def get_gate1_checks(self) -> dict[str, Any]:
        """门 1 体检卡（P2-3 只读）：规则规格原样 + 注册表自检。

        gate1_code_checks 是规则规格（desc/allowed_patterns/rules）而非违规明细数据源——
        自检只报「standards[].code 匹配不上任何 allowed_pattern」的名单，供专家回查，
        不伪造违规细节。
        """
        idx = await run_in_threadpool(_load_standards_index)
        spec = idx.get("gate1_code_checks", {})
        patterns = [re.compile(p) for p in spec.get("allowed_patterns", [])]
        codes = [str(s.get("code", "")) for s in idx.get("standards", [])]
        violations = [c for c in codes if not any(p.match(c) for p in patterns)]
        return {
            "desc": spec.get("desc", ""),
            "allowed_patterns": spec.get("allowed_patterns", []),
            "rules": spec.get("rules", []),
            "registry_check": {"total": len(codes), "violations": violations},
        }

    async def set_review(self, code: str, payload: dict[str, Any], username: str) -> dict[str, Any]:
        """核实裁决落库（upsert）：code 须在 standards_index（404），action 白名单外 400。"""
        doc = await run_in_threadpool(_load_standards_index)
        if code not in {s["code"] for s in doc.get("standards", [])}:
            raise KeyError(f"标准编号不存在于 standards_index: {code}")
        _validate_review(payload)
        row = await self.repo.get_review(code)
        if row is None:
            row = EiaStandardReview(code=code)
        row.action = payload["action"]
        row.note = payload.get("note")
        row.decided_by = username
        row.decided_at = utc_now_naive()
        await self.repo.save_review(row)
        return row.to_dict()

    async def export_reviews(self, username: str) -> dict[str, Any]:
        """DB → 注册表文件：仅翻转被裁决条目的 needs_verification/verified，其余 round-trip 不变。"""
        rows = await self.repo.list_reviews()
        if not rows:
            raise ValueError("无核实裁决可导出：请先完成标准核实")

        def _write() -> tuple[dict[str, Any], int]:
            doc = _load_standards_index()
            index = {s["code"]: s for s in doc.get("standards", [])}
            flipped = 0
            for r in sorted(rows, key=lambda x: x.code):
                s = index.get(r.code)
                if s is None:
                    # 注册表漂移（条目被删）时跳过计数上浮，绝不动文件其余结构
                    logger.warning(f"[eia-standard] 导出跳过已消失的标准编号：{r.code}")
                    continue
                s["needs_verification"] = False
                s["verified"] = True
                flipped += 1
            STANDARDS_INDEX_PATH.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
            )
            return doc, flipped

        _, flipped = await run_in_threadpool(_write)
        logger.info(f"[eia-standard] 导出物化 {flipped} 条裁决 → {STANDARDS_INDEX_PATH.name}（by {username}）")
        return {
            "materialized": flipped,
            "path": "references/standards_index.json",
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    async def save_limit_rows(self, table_key: str, rows: Any, username: str) -> dict[str, Any]:
        """限值行整表替换落库（先校验后写：未知表 KeyError→404，载荷问题 ValueError→400）。"""
        validated = _validate_limit_rows(table_key, rows)
        saved = await self.repo.replace_rows(table_key, validated, username)
        logger.info(f"[eia-standard] 限值表 {table_key} 录入 {saved} 行（by {username}）")
        return {"table_key": table_key, "saved": saved}

    async def export_limit_rows(self, username: str) -> dict[str, Any]:
        """DB → 注册表文件：已录入表整表替换 rows（样例锚点行被人工核对行取代）并翻转 nv/verified。"""
        rows = await self.repo.list_rows()
        if not rows:
            raise ValueError("无限值录入行可导出：请先在各限值表完成录入")

        def _write() -> tuple[int, int]:
            doc = _load_standards_index()
            tables = doc.get("limit_tables", {})
            n_tables = 0
            n_rows = 0
            for key in sorted({r.table_key for r in rows}):
                t = tables.get(key)
                if not isinstance(t, dict):
                    # 注册表漂移（表被删）时跳过计数上浮，绝不动文件其余结构
                    logger.warning(f"[eia-standard] 导出跳过已消失的限值表：{key}")
                    continue
                items = sorted((r for r in rows if r.table_key == key), key=lambda x: x.id)
                t["rows"] = [dict(r.row_json) for r in items]
                t["needs_verification"] = False
                t["verified"] = True
                n_tables += 1
                n_rows += len(items)
            STANDARDS_INDEX_PATH.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
            )
            return n_tables, n_rows

        n_tables, n_rows = await run_in_threadpool(_write)
        logger.info(f"[eia-standard] 导出物化 {n_tables} 张限值表 {n_rows} 行 → standards_index.json（by {username}）")
        return {
            "materialized": n_tables,
            "rows": n_rows,
            "path": "references/standards_index.json",
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


_service: EiaStandardService | None = None


def get_eia_standard_service() -> EiaStandardService:
    global _service
    if _service is None:
        _service = EiaStandardService()
    return _service
