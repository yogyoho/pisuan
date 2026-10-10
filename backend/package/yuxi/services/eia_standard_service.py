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

from yuxi.repositories.eia_standard_repository import EiaStandardRepository
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.storage.postgres.models_domain_factory import EiaStandardReview
from yuxi.utils import logger
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive

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
        from yuxi.services.eia_meta_service import _load_corpus_meta

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
        """limit_tables 只读原样（rows 录入留后续，一期仅展示）。"""
        doc = await run_in_threadpool(_load_standards_index)
        return {"limit_tables": doc.get("limit_tables", {})}

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


_service: EiaStandardService | None = None


def get_eia_standard_service() -> EiaStandardService:
    global _service
    if _service is None:
        _service = EiaStandardService()
    return _service
