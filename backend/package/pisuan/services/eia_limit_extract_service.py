"""语料限值提取服务（spec 2026-10-19 W2/W3 后端 + Task 13 B 通道）。试跑→暂存；裁决→转正；候选→立表；引用→W1 辅助。

链路：samples_bank 各阶段 slices 切片 → 内核 locate 定位 → LLM 语义判别（仅限值陈述放行，fail-closed）
→ 内核 parse_block/聚合 → eia_limit_extract_rows 暂存（行标 extractor="llm"）；
人工裁决 confirm/edited 经 upsert_row 幂等转正到 eia_standard_limit_rows，discarded 留痕不转正；
未知标准号行落 __candidate__:<归一码> 候选键，register_candidate 立表后批量迁移。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi.concurrency import run_in_threadpool

from pisuan.repositories.eia_limit_extract_repository import EiaLimitExtractRepository
from pisuan.repositories.eia_standard_repository import EiaStandardRepository
from pisuan.services.eia_data_service import _SKILL_ROOT
from pisuan.services.eia_limit_extract_core import (
    aggregate_cited_codes,
    aggregate_records,
    diff_source_candidates,
    locate_standard_blocks,
    norm_code,
    parse_block,
    table_key_for,
)
from pisuan.services.eia_limit_llm_classifier import EiaLimitLLMClassifier, GateStats, JudgeResult, gate_report
from pisuan.services.eia_standard_service import LIMIT_TABLE_SCHEMAS
from pisuan.storage.postgres.models_domain_factory import EiaLimitExtractRow, EiaLimitTableRegistry
from pisuan.utils import logger
from pisuan.utils.datetime_utils import utc_now_naive

_BANK_ROOT = _SKILL_ROOT / "references" / "samples_bank"
_SLICE_NAME_RE = re.compile(r"^(?P<rid>.+?)__\d+\.md$")
_CANDIDATE_PREFIX = "__candidate__:"
_VALID_DECISIONS = {"confirm", "edited", "discarded"}
_TABLE_KEY_RE = re.compile(r"^[a-z0-9_]+$")
_NUMERIC_KEYS = ("limit_value", "day", "night", "a_value")
_JUDGE_CONCURRENCY = 6  # 判别有界并发（I4）：防供应商限流；全库 7581 块实测串行为小时级


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
    def __init__(
        self,
        repo: EiaLimitExtractRepository | None = None,
        std_repo: EiaStandardRepository | None = None,
        classifier: EiaLimitLLMClassifier | None = None,
    ):
        self._repo = repo or EiaLimitExtractRepository()
        self._std_repo = std_repo or EiaStandardRepository()
        self._classifier = classifier or EiaLimitLLMClassifier()  # 默认 LLM 判别门，无旁路
        self._run_lock = asyncio.Lock()  # 进程内试跑互斥（I3）：单例共享判别器，防重叠试跑清对方计数

    def _bank_dirs(self) -> list[Path]:
        """samples_bank 根目录列表（阶段目录为其下含 slices/ 的子目录，threadpool 调用）。"""
        return [_BANK_ROOT] if _BANK_ROOT.is_dir() else []

    async def run_extraction(self, username: str) -> dict[str, Any]:
        """全库试跑：切片 → 区块定位 → LLM 语义判别（有界并发）→ 解析/聚合 → 幂等过滤 → 暂存行 + 报告。

        判别门（Task 13 B 通道）：每个 locate 命中区块先经 LLM 判别是否限值陈述，
        监测陈述与判别失败（fail-closed）一律不进入解析。行数据带 extractor="llm" 标注。
        进程内互斥（I3）：单例共享判别器，重叠试跑在锁上串行化，防 gate 计数互相清零。
        """
        async with self._run_lock:
            return await self._run_extraction_locked(username)

    async def _run_extraction_locked(self, username: str) -> dict[str, Any]:
        def _scan() -> tuple[int, int, list[tuple]]:
            hits: list[tuple] = []
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
                            hits.append((b, tk, rid, anchor))
            return scanned, skipped, hits

        classifier = self._classifier
        classifier.stats = GateStats()  # 报告口径按单次试跑计，不跨次累计
        scanned, skipped, hits = await run_in_threadpool(_scan)
        sem = asyncio.Semaphore(_JUDGE_CONCURRENCY)

        async def _judge_one(hit: tuple) -> tuple[tuple, JudgeResult]:
            """单块判别（I4 有界并发）；异常只影响该块——按判别器内部同款 failed 口径 fail-closed。"""
            b, tk, rid, anchor = hit
            async with sem:
                try:
                    return hit, await classifier.judge(b.code, "\n".join(b.lines), tk)
                except Exception as exc:
                    logger.warning(f"[eia-limit-extract] 判别异常按未通过处理（code={b.code}）: {exc}")
                    return hit, JudgeResult(False, "failed", {}, f"判别异常: {exc}")

        results = await asyncio.gather(*(_judge_one(h) for h in hits))
        passed = [hit for hit, verdict in results if verdict.passed]

        def _parse_passed() -> list[dict]:
            records: list[dict] = []
            for b, tk, rid, anchor in passed:
                records.extend(
                    {
                        "code": b.code,
                        "table_key": tk,
                        "row": {**row, "extractor": "llm"},
                        "source": {"report_id": rid, "anchor": anchor},
                    }
                    for row in parse_block(b)
                )
            return records

        records = await run_in_threadpool(_parse_passed)
        aggregated = aggregate_records(records)
        # 立表后重映射（spec 2026-10-19）：注册表覆盖的候选键改写为正式表键，防重跑复生候选行
        remap = {f"{_CANDIDATE_PREFIX}{norm_code(reg.code)}": reg.table_key for reg in await self._repo.list_registry()}
        if remap:
            for g in aggregated:
                if hit := remap.get(g["table_key"]):  # 仅候选键组可能命中，正式表键不受影响
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
            "gate": gate_report(classifier.stats),
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
        from pisuan.services.eia_meta_service import _load_corpus_meta

        meta = await run_in_threadpool(_load_corpus_meta)
        target = norm_code(code)
        reports = []
        for rid, m in meta.get("reports", {}).items():
            cited_as = next((c for c in m.get("standards_cited") or [] if norm_code(c) == target), None)
            if cited_as:
                reports.append({"report_id": rid, "stage": m.get("stage", ""), "cited_as": cited_as})
        return {"code": code, "cited_count": len(reports), "reports": reports}

    async def list_source_candidates(self) -> list[dict[str, Any]]:
        """缺源候选：语料引用标准号聚合，归一化后减去 standard_indicators 已覆盖（引用数降序）。

        v1 简化：候选全部视为「缺源」；「已入 KB · 待提取」状态判定延后。
        """
        from pisuan.services.eia_meta_service import _load_corpus_meta

        meta = await run_in_threadpool(_load_corpus_meta)
        from pisuan.extensions.regulation_library.enrichment_service import distinct_doc_codes

        covered = await distinct_doc_codes()
        candidates = diff_source_candidates(aggregate_cited_codes(meta), covered)
        logger.info(
            f"[eia-limit-extract] 缺源候选 {len(candidates)} 个（standard_indicators 已覆盖 {len(covered)} 个）"
        )
        return candidates


_service: EiaLimitExtractService | None = None


def get_eia_limit_extract_service() -> EiaLimitExtractService:
    global _service
    if _service is None:
        _service = EiaLimitExtractService()
    return _service
