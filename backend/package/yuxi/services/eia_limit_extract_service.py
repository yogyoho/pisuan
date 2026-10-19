"""语料限值提取服务（spec 2026-10-19 W2/W3 后端）。试跑→暂存；裁决→转正；候选→立表；引用→W1 辅助。

链路：samples_bank 各阶段 slices 切片 → 内核（locate/parse/aggregate）→ eia_limit_extract_rows 暂存；
人工裁决 confirm/edited 经 upsert_row 幂等转正到 eia_standard_limit_rows，discarded 留痕不转正；
未知标准号行落 __candidate__:<归一码> 候选键，register_candidate 立表后批量迁移。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_limit_extract_repository import EiaLimitExtractRepository
from yuxi.repositories.eia_standard_repository import EiaStandardRepository
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.services.eia_limit_extract_core import (
    aggregate_records,
    locate_standard_blocks,
    norm_code,
    parse_block,
    table_key_for,
)
from yuxi.services.eia_standard_service import LIMIT_TABLE_SCHEMAS
from yuxi.storage.postgres.models_domain_factory import EiaLimitExtractRow, EiaLimitTableRegistry
from yuxi.utils import logger
from yuxi.utils.datetime_utils import utc_now_naive

_BANK_ROOT = _SKILL_ROOT / "references" / "samples_bank"
_SLICE_NAME_RE = re.compile(r"^(?P<rid>.+?)__\d+\.md$")
_CANDIDATE_PREFIX = "__candidate__:"
_VALID_DECISIONS = {"confirm", "edited", "discarded"}
_TABLE_KEY_RE = re.compile(r"^[a-z0-9_]+$")
_NUMERIC_KEYS = ("limit_value", "day", "night", "a_value")


def _normalize_row_json(row: dict) -> dict:
    """数值列类型归一（有值转 float，空值置 None）并剥离 conflict_values——upsert_row 以 JSON 全等判幂等。"""
    out = dict(row)
    out.pop("conflict_values", None)  # 暂存诊断信息不进官方行，也不污染 upsert 幂等键
    for k in _NUMERIC_KEYS:
        if k in out:
            v = out[k]
            out[k] = float(v) if v not in (None, "") else None
    return out


def _row_biz(row: dict) -> tuple:
    """业务键 = 除数值列与 conflict_values 外全部字段。"""
    return tuple(sorted((k, str(v)) for k, v in row.items() if k not in _NUMERIC_KEYS and k != "conflict_values"))


def _decided_key(code: str, table_key: str, row_json: dict | None) -> tuple:
    return (norm_code(code), table_key) + _row_biz(row_json or {})


class EiaLimitExtractService:
    def __init__(self, repo: EiaLimitExtractRepository | None = None, std_repo: EiaStandardRepository | None = None):
        self._repo = repo or EiaLimitExtractRepository()
        self._std_repo = std_repo or EiaStandardRepository()

    def _bank_dirs(self) -> list[Path]:
        """samples_bank 根目录列表（阶段目录为其下含 slices/ 的子目录，threadpool 调用）。"""
        return [_BANK_ROOT] if _BANK_ROOT.is_dir() else []

    async def run_extraction(self, username: str) -> dict[str, Any]:
        """全库试跑：切片 → 区块定位/解析/聚合 → 幂等过滤 → 暂存行 + 报告。"""

        def _scan() -> tuple[int, int, list[dict]]:
            records: list[dict] = []
            scanned = skipped = 0
            for root in self._bank_dirs():
                for stage in sorted(p for p in root.iterdir() if (p / "slices").is_dir()):
                    for md in sorted((stage / "slices").rglob("*.md")):
                        m = _SLICE_NAME_RE.match(md.name)
                        if not m:
                            continue
                        scanned += 1
                        try:
                            text = md.read_text(encoding="utf-8")
                        except (UnicodeDecodeError, OSError) as exc:
                            skipped += 1  # 单坏文件隔离：告警跳过，不炸整次试跑
                            logger.warning(f"[eia-limit-extract] 切片读取失败跳过: {md} ({exc})")
                            continue
                        rid, anchor = m.group("rid"), f"{stage.name}/{md.stem}"
                        for b in locate_standard_blocks(text):
                            tk = table_key_for(b.code) or f"{_CANDIDATE_PREFIX}{norm_code(b.code)}"
                            records.extend(
                                {
                                    "code": b.code,
                                    "table_key": tk,
                                    "row": row,
                                    "source": {"report_id": rid, "anchor": anchor},
                                }
                                for row in parse_block(b)
                            )
            return scanned, skipped, records

        scanned, skipped, records = await run_in_threadpool(_scan)
        aggregated = aggregate_records(records)
        # 立表后重映射（spec 2026-10-19）：注册表覆盖的候选键改写为正式表键，防重跑复生候选行
        remap = {f"{_CANDIDATE_PREFIX}{norm_code(reg.code)}": reg.table_key for reg in await self._repo.list_registry()}
        if remap:
            for g in aggregated:
                hit = remap.get(f"{_CANDIDATE_PREFIX}{norm_code(g['code'])}")
                if hit:
                    g["table_key"] = hit
        existing = {
            _decided_key(r.code, r.table_key, r.row_json)
            for r in await self._repo.list_rows()  # 已裁决（≠pending）命中信跳过；pending 命中信不重插
        }
        now = utc_now_naive()
        fresh = [
            EiaLimitExtractRow(
                table_key=g["table_key"],
                code=g["code"],
                row_json=g["row"],
                confidence=g["confidence"],
                sources=g["sources"],
                status="pending",
                created_at=now,
            )
            for g in aggregated
            if _decided_key(g["code"], g["table_key"], g["row"]) not in existing
        ]
        inserted = await self._repo.add_rows(fresh) if fresh else 0
        tables: dict[str, dict[str, int]] = {}
        for g in aggregated:
            t = tables.setdefault(g["table_key"], {"total": 0, "multi": 0, "single": 0, "conflict": 0})
            t["total"] += 1
            t[g["confidence"]] += 1
        logger.info(
            f"[eia-limit-extract] 试跑 by {username}: 扫描 {scanned} 切片, 聚合 {len(aggregated)} 行, 新插 {inserted}"
        )
        return {
            "files_scanned": scanned,
            "aggregated": len(aggregated),
            "inserted": inserted,
            "skipped": skipped,
            "tables": tables,
        }

    async def list_rows(
        self, table_key: str | None = None, status: str | None = None, confidence: str | None = None
    ) -> list[dict[str, Any]]:
        rows = await self._repo.list_rows(table_key=table_key, status=status, confidence=confidence)
        return [r.to_dict() for r in rows]

    async def decide_row(
        self, row_id: int, action: str, row_json: dict | None, username: str, note: str | None = None
    ) -> dict[str, Any]:
        """行裁决：confirm/edited 经 upsert_row 转正（edited 须带非空 row_json），discarded 仅留痕。"""
        row = await self._repo.get_row(row_id)
        if row is None:
            raise KeyError(f"暂存行不存在: {row_id}")
        if action not in _VALID_DECISIONS:
            raise ValueError(f"action 须为 {sorted(_VALID_DECISIONS)}")
        if row.status != "pending":
            raise ValueError("已裁决行不可再裁决")
        if action == "edited" and (not isinstance(row_json, dict) or not row_json):
            raise ValueError("edited 裁决必须携带非空 row_json")
        if action in ("confirm", "edited") and row.table_key.startswith(_CANDIDATE_PREFIX):
            raise ValueError("候选表行须先立表迁移再裁决")
        if action in ("confirm", "edited"):
            target = dict(row_json) if action == "edited" else dict(row.row_json or {})
            normalized = _normalize_row_json(target)
            await self._std_repo.upsert_row(row.table_key, normalized, username)
            if action == "edited":
                row.row_json = normalized
        row.status = "confirmed" if action == "confirm" else action  # 状态词表 confirmed（模型列注释）
        row.decided_by = username
        row.decided_at = row.updated_at = utc_now_naive()
        row.note = note
        await self._repo.save_row(row)
        logger.info(f"[eia-limit-extract] 行 {row_id} 裁决 {action}（by {username}）")
        return row.to_dict()

    async def list_candidates(self) -> dict[str, Any]:
        """候选表行分组（__candidate__: 前缀），供立表评审。"""
        groups: dict[str, list] = {}
        for r in await self._repo.list_rows():
            if r.table_key.startswith(_CANDIDATE_PREFIX):
                groups.setdefault(r.table_key, []).append(r)
        return {
            "candidates": [
                {"candidate_key": key, "rows": [r.to_dict() for r in rows], "count": len(rows)}
                for key, rows in sorted(groups.items())
            ]
        }

    async def register_candidate(
        self, code: str, table_key: str, desc: str, columns_schema: dict, username: str
    ) -> dict[str, Any]:
        """候选立表：注册元数据入册，并把该标准号的 pending 候选行迁移到新键。"""
        if not _TABLE_KEY_RE.match(table_key):
            raise ValueError(f"table_key 须匹配 ^[a-z0-9_]+$: {table_key}")
        if table_key in LIMIT_TABLE_SCHEMAS or await self._repo.get_registry(table_key):
            raise ValueError(f"table_key 已存在: {table_key}")
        await self._repo.save_registry(
            EiaLimitTableRegistry(
                table_key=table_key, code=code, desc=desc, columns_schema=columns_schema, created_by=username
            )
        )
        cand_key = f"{_CANDIDATE_PREFIX}{norm_code(code)}"
        migrated = 0
        for r in await self._repo.list_rows(table_key=cand_key, status="pending"):
            r.table_key = table_key
            r.updated_at = utc_now_naive()
            await self._repo.save_row(r)
            migrated += 1
        logger.info(f"[eia-limit-extract] 候选立表 {table_key}（{code}，by {username}），迁移 {migrated} 行")
        return {"table_key": table_key, "migrated": migrated}

    async def list_citations(self, code: str) -> dict[str, Any]:
        """标准号在语料中的引用清单（corpus_meta.standards_cited 归一匹配）。"""
        from yuxi.services.eia_meta_service import _load_corpus_meta

        meta = await run_in_threadpool(_load_corpus_meta)
        target = norm_code(code)
        reports = []
        for rid, m in meta.get("reports", {}).items():
            cited_as = next((c for c in m.get("standards_cited") or [] if norm_code(c) == target), None)
            if cited_as:
                reports.append({"report_id": rid, "stage": m.get("stage", ""), "cited_as": cited_as})
        return {"code": code, "cited_count": len(reports), "reports": reports}
