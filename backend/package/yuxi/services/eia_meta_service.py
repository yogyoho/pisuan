"""环评语料元数据人工标注服务（P2：DB 运营唯一真相 + 显式导出物化人工层文件）。

与 P1 词表的架构差异（均有意为之，见 docs/vibe/2026-10-10-eia-meta-annotation.md §1）：
  - 物化目标即人工层文件本体 corpus_meta_annotations.json（无脚本消费者、纯人工输入层，
    导出 = 用 DB 真相重写，替代手编 JSON），不设 overrides 覆盖层
  - 无开关：人工层文件没有「builtin 兜底」语义，导出后常驻
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_meta_repository import EiaMetaRepository
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.storage.postgres.models_domain_factory import EiaMetaAnnotation
from yuxi.utils import logger
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive

CORPUS_META_PATH = _SKILL_ROOT / "references" / "samples_bank" / "corpus_meta.json"
META_ANNOTATIONS_PATH = _SKILL_ROOT / "references" / "samples_bank" / "corpus_meta_annotations.json"

# 可标注字段与取值域（越界即 400，不静默丢弃未知字段）
_ANNOTATION_FIELDS = {"year_hint", "scale_mt_a"}


def _load_corpus_meta() -> dict[str, Any]:
    """自动层 corpus_meta.json（只读，标注裁决的对照面）。"""
    return json.loads(CORPUS_META_PATH.read_text(encoding="utf-8"))


def _validate_annotations(payload: Any) -> dict[str, Any]:
    """标注载荷校验（纯函数）：只认 year_hint/scale_mt_a，越界/类型错即拒。"""
    if not isinstance(payload, dict):
        raise ValueError("annotations 必须是对象")
    unknown = set(payload) - _ANNOTATION_FIELDS
    if unknown:
        raise ValueError(f"未知标注字段: {sorted(unknown)}（允许 {_ANNOTATION_FIELDS}）")
    clean: dict[str, Any] = {}
    if "year_hint" in payload:
        y = payload["year_hint"]
        if isinstance(y, bool) or not isinstance(y, int) or not 2000 <= y <= 2100:
            raise ValueError(f"year_hint 须为 2000–2100 整数，得到 {y!r}")
        clean["year_hint"] = y
    if "scale_mt_a" in payload:
        s = payload["scale_mt_a"]
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not 0 < float(s) <= 10000:
            raise ValueError(f"scale_mt_a 须为 (0, 10000] 数值（万吨/年），得到 {s!r}")
        clean["scale_mt_a"] = float(s)
    return clean


class EiaMetaService:
    """语料元数据人工标注：导入 / 标注确认 / 导出物化（重写人工层文件）。"""

    def __init__(self) -> None:
        self.repo = EiaMetaRepository()

    async def import_annotations(self) -> dict[str, Any]:
        """存量人工层文件 → DB（幂等：existing rid 一律跳过，绝不覆盖页面裁决）。"""
        existing_file = await run_in_threadpool(
            lambda: (
                json.loads(META_ANNOTATIONS_PATH.read_text(encoding="utf-8")) if META_ANNOTATIONS_PATH.is_file() else {}
            )
        )
        # rid 全集 = corpus_meta.reports 键（与 set/list/export 同一不变量）；
        # 语料普查漂移或手编笔误产生的越界 rid 拒收并计数上浮，绝不落库成幽灵行
        known_ids = set((await run_in_threadpool(_load_corpus_meta)).get("reports", {}))
        existing_ids = await self.repo.existing_ids()
        now = utc_now_naive()
        added = 0
        skipped_unknown = 0
        for rid, ann in sorted(existing_file.items()):
            if rid not in known_ids:
                skipped_unknown += 1
                logger.warning(f"[eia-meta] 导入跳过未知 rid（不在 corpus_meta）：{rid}")
                continue
            if rid in existing_ids:
                continue
            await self.repo.save_annotation(
                EiaMetaAnnotation(
                    report_id=rid,
                    annotations={k: ann[k] for k in _ANNOTATION_FIELDS if k in (ann or {})},
                    note=None,
                    decided_by="import",
                    decided_at=now,
                )
            )
            added += 1
        logger.info(
            f"[eia-meta] 导入完成：文件 {len(existing_file)} 条，新增 {added} 条，未知 rid 跳过 {skipped_unknown} 条"
        )
        return {"scanned": len(existing_file), "added": added, "skipped_unknown": skipped_unknown}

    async def list_reports(self) -> dict[str, Any]:
        """31 份报告总览：自动层只读 + DB 标注合并；counts 汇总待办。"""
        meta = await run_in_threadpool(_load_corpus_meta)
        rows = {r.report_id: r for r in await self.repo.list_annotations()}
        items: list[dict[str, Any]] = []
        counts = {"total": 0, "annotated": 0, "year_missing": 0, "scale_missing": 0, "scale_needs_review": 0}
        for rid, m in sorted(meta.get("reports", {}).items()):
            counts["total"] += 1
            row = rows.get(rid)
            ann = (row.annotations or {}) if row else {}
            auto_year = m.get("year_hint")
            auto_scale = m.get("scale_mt_a")
            eff_year = ann.get("year_hint", auto_year)
            eff_scale = ann.get("scale_mt_a", auto_scale)
            if ann.get("year_hint") is not None or ann.get("scale_mt_a") is not None:
                counts["annotated"] += 1
            if eff_year is None:
                counts["year_missing"] += 1
            if eff_scale is None:
                counts["scale_missing"] += 1
            if m.get("scale_basis") == "needs_review":
                counts["scale_needs_review"] += 1
            items.append(
                {
                    "report_id": rid,
                    "stage": m.get("stage"),
                    "province": m.get("province"),
                    "scale_basis": m.get("scale_basis"),
                    "scale_candidates": m.get("scale_candidates") or [],
                    "auto_year_hint": auto_year,
                    "auto_scale_mt_a": auto_scale,
                    "standards_count": len(m.get("standards_cited") or []),
                    "annotation": {
                        "year_hint": ann.get("year_hint"),
                        "scale_mt_a": ann.get("scale_mt_a"),
                        "note": row.note if row else None,
                        "decided_by": row.decided_by if row else None,
                        "decided_at": format_utc_datetime(row.decided_at) if row else None,
                    },
                    "year_missing": eff_year is None,
                    "scale_missing": eff_scale is None,
                }
            )
        return {"items": items, "total": counts["total"], "counts": counts}

    async def set_annotation(self, report_id: str, payload: dict[str, Any], username: str) -> dict[str, Any]:
        """标注落库（upsert）：rid 须在 corpus_meta 中（404），字段越界 400。"""
        meta = await run_in_threadpool(_load_corpus_meta)
        if report_id not in meta.get("reports", {}):
            raise KeyError(f"报告不存在于 corpus_meta: {report_id}")
        clean = _validate_annotations(payload.get("annotations"))
        note = payload.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError("note 须为字符串")
        row = await self.repo.get_annotation(report_id)
        if row is None:
            row = EiaMetaAnnotation(report_id=report_id)
        row.annotations = clean
        row.note = note
        row.decided_by = username
        row.decided_at = utc_now_naive()
        await self.repo.save_annotation(row)
        return row.to_dict()

    async def export_annotations(self, username: str) -> dict[str, Any]:
        """DB → 人工层文件全量重写（rid 序确定性）；全清空标注的 rid 从文件剔除。"""
        rows = await self.repo.list_annotations()
        doc: dict[str, Any] = {}
        for r in sorted(rows, key=lambda x: x.report_id):
            fields = {k: r.annotations[k] for k in _ANNOTATION_FIELDS if k in (r.annotations or {})}
            if fields:
                doc[r.report_id] = fields
        if not doc:
            raise ValueError("无标注可导出：请先完成标注或导入存量人工层")

        def _write() -> None:
            META_ANNOTATIONS_PATH.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
            )

        await run_in_threadpool(_write)
        logger.info(f"[eia-meta] 导出物化 {len(doc)} 条 → {META_ANNOTATIONS_PATH.name}（by {username}）")
        return {
            "materialized": len(doc),
            "path": "references/samples_bank/corpus_meta_annotations.json",
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


_service: EiaMetaService | None = None


def get_eia_meta_service() -> EiaMetaService:
    global _service
    if _service is None:
        _service = EiaMetaService()
    return _service
