"""规范文档富化编排：读 chunks → 解析结构 → 表格打标分流 → 提取指标/方法映射 → 回填 tags → 建图"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as sql_text

from pisuan.extensions.regulation_library import indicator_extractor
from pisuan.extensions.regulation_library.graph_writer import RegulationGraphWriter
from pisuan.extensions.regulation_library.models import ensure_schema
from pisuan.extensions.regulation_library.taxonomy_extractor import extract_taxonomy_rows, row_id
from pisuan.extensions.regulation_library.table_role_classifier import (
    TableRoleClassifier,
    classify_table_role_by_title,
)
from pisuan.extensions.regulation_library.table_splitter import split_table_units
from pisuan.extensions.regulation_library.unit_parser import parse_chunk_unit
from pisuan.services.eia_data_service import _SKILL_ROOT
from pisuan.services.eia_limit_extract_core import norm_code
from pisuan.config.options import invalidate_option_cache, system_options, update_option_value
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_knowledge import KnowledgeChunk
from pisuan.storage.postgres.models_knowledge import KnowledgeFile
from pisuan.utils import logger
from pisuan.utils.datetime_utils import format_utc_datetime

_ALL_ROLES = ("limit", "method", "criteria", "param", "taxonomy", "other")
_CONTINUATION_RE = re.compile(r"[（(]续[)）]\s*$")  # 续表 unit_no 后缀（表N（续）），半/全角括号兼容
_MANUAL_MAX_ROWS = 500  # 手工单次录入行数上限（防误传超大载荷）
_MANUAL_UNIT_NO = "手录"  # 手工行统一表单元号
_DOC_CODE_RE = re.compile(
    r"(?:GB/T|GBT|GB|HJ|DB\d{1,2}|CJ|SL|NY)\s*\d{3,5}(?:\.\d+)?(?:\s*[-—–]\s*\d{4})?",
    re.IGNORECASE,
)

# enrich 幂等删旧：仅清自身候选行——expert 权威行对重跑免疫（P1 合流，spec §5）
ENRICH_DELETE_SQL = "DELETE FROM standard_indicators WHERE doc_code = :code AND source = 'enrich'"


class StandardConflictError(Exception):
    """standard_indicators 写冲突（手工行挡道 / doc_code 已存在 / 非手工行），路由映射 409。"""


class EnrichRunInProgressError(Exception):
    """同一标准的规范加工任务仍在进行中，路由映射 409。"""


def _suggest_doc_code(filename: str, tag_codes: list[str]) -> str:
    """优先取富化 chunk 中的 doc_code；未加工文件从标准文件名解析标准号。"""
    counts = Counter(code.strip() for code in tag_codes if str(code or "").strip())
    if counts:
        return counts.most_common(1)[0][0]
    normalized = (filename or "").replace("－", "-").replace("—", "-").replace("／", "/").upper()
    match = _DOC_CODE_RE.search(normalized)
    if not match:
        return ""
    return re.sub(r"\s+", "", match.group(1)) if match.groups() else re.sub(r"\s+", "", match.group(0))


def _build_regulation_document_items(
    files: list[Any],
    chunks: list[Any],
    indicator_rows: list[Any],
) -> list[dict[str, Any]]:
    """把文件、chunk 富化 tags、指标聚合组装为文档工作台行；纯函数便于测试。"""
    chunks_by_file: dict[str, list[Any]] = {}
    for chunk in chunks:
        chunks_by_file.setdefault(chunk.file_id, []).append(chunk)

    indicators_by_file: dict[str, dict[str, int]] = {}
    for row in indicator_rows:
        indicators_by_file[str(row.file_id)] = {
            "total": int(row.total or 0),
            "expert": int(row.expert or 0),
            "reviewed": int(row.reviewed or 0),
            "candidate": int(row.candidate or 0),
            "doc_codes": int(row.doc_codes or 0),
        }

    items: list[dict[str, Any]] = []
    for file in files:
        file_chunks = chunks_by_file.get(file.file_id, [])
        doc_codes: Counter[str] = Counter()
        table_roles: Counter[str] = Counter()
        unit_keys: set[tuple[str, str]] = set()
        table_keys: set[tuple[str, str]] = set()
        tagged_chunk_count = 0
        for chunk in file_chunks:
            tags = chunk.tags or {}
            code = str(tags.get("doc_code") or "").strip()
            if not code:
                continue
            tagged_chunk_count += 1
            doc_codes[code] += 1
            unit_no = str(tags.get("unit_no") or "").strip()
            if tags.get("unit_type") == "table" and unit_no:
                table_keys.add((code, unit_no))
                table_roles[str(tags.get("table_role") or "unclassified")] += 1
            if unit_no:
                unit_keys.add((code, unit_no))
            for unit in tags.get("table_units") or []:
                if not isinstance(unit, dict):
                    continue
                child_no = str(unit.get("unit_no") or "").strip()
                if not child_no:
                    continue
                unit_keys.add((code, child_no))
                if unit.get("unit_type") == "table":
                    table_keys.add((code, child_no))
                    table_roles[str(unit.get("table_role") or "unclassified")] += 1

        stats = indicators_by_file.get(
            file.file_id,
            {"total": 0, "expert": 0, "reviewed": 0, "candidate": 0, "doc_codes": 0},
        )
        has_chunks = bool(file_chunks) or int(file.chunk_count or 0) > 0
        enriched = tagged_chunk_count > 0 or stats["total"] > 0
        if not has_chunks:
            status = "empty"
        elif enriched:
            status = "enriched"
        else:
            status = "indexed"
        suggested_code = _suggest_doc_code(file.filename or "", list(doc_codes.elements()))
        suggested_name = re.sub(r"\.(pdf|docx?|md)$", "", file.filename or "", flags=re.IGNORECASE)
        suggested_name = re.sub(r"^\s*《?|\》?\s*$", "", suggested_name).strip()
        suggested_name = re.sub(
            r"\s*(GB/T|GBT|GB|HJ|DB\d{0,2}|CJ|SL|NY)\s*\d{3,5}(?:\.\d+)?(?:\s*[-—–]\s*\d{4})?.*$",
            "",
            suggested_name,
            flags=re.IGNORECASE,
        ).strip("《》（）() -—–")

        items.append(
            {
                "file_id": file.file_id,
                "kb_id": file.kb_id,
                "filename": file.filename,
                "status": file.status,
                "process_status": status,
                "chunk_count": int(file.chunk_count or 0),
                "file_size": int(file.file_size or 0),
                "updated_at": file.updated_at.isoformat() if file.updated_at else None,
                "doc_codes": sorted(doc_codes),
                "suggested_doc_code": suggested_code,
                "suggested_doc_name": suggested_name,
                "processed_chunk_count": tagged_chunk_count,
                "unit_count": len(unit_keys),
                "table_count": len(table_keys),
                "table_roles": dict(table_roles),
                "indicators": stats,
            }
        )
    return items


async def list_regulation_documents(
    kb_id: str,
    *,
    keyword: str | None = None,
    process_status: str | None = None,
    run_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """列出规范知识库中的文件及其加工/指标状态，供页面工作台消费。"""
    await ensure_schema()
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    async with pg_manager.get_async_session_context() as session:
        file_result = await session.execute(
            select(KnowledgeFile)
            .where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.is_folder.is_(False))
            .order_by(KnowledgeFile.filename)
        )
        files = file_result.scalars().all()
        chunk_result = await session.execute(
            select(
                KnowledgeChunk.file_id,
                KnowledgeChunk.tags,
                KnowledgeChunk.updated_at,
            ).where(KnowledgeChunk.kb_id == kb_id)
        )

        class _ChunkRow:
            def __init__(self, file_id: str, tags: Any):
                self.file_id = file_id
                self.tags = tags

        chunks = [_ChunkRow(row.file_id, row.tags) for row in chunk_result.all()]
        indicator_result = await session.execute(
            sql_text(
                """
                SELECT kc.file_id,
                       count(si.id) AS total,
                       count(si.id) FILTER (WHERE si.source = 'expert') AS expert,
                       count(si.id) FILTER (WHERE si.source = 'enrich' AND si.verified_at IS NOT NULL) AS reviewed,
                       count(si.id) FILTER (WHERE si.source = 'enrich' AND si.verified_at IS NULL) AS candidate,
                       count(DISTINCT si.doc_code) AS doc_codes
                  FROM standard_indicators si
                  JOIN knowledge_chunks kc ON kc.chunk_id = si.chunk_id
                 WHERE kc.kb_id = :kb_id
                 GROUP BY kc.file_id
                """
            ),
            {"kb_id": kb_id},
        )
        indicator_rows = indicator_result.all()

        run_rows = (
            await session.execute(
                sql_text(
                    """
                    SELECT DISTINCT ON (file_id)
                           run_id, file_id, status, started_by, started_at, finished_at,
                           error_message, result
                      FROM regulation_enrich_runs
                     WHERE kb_id = :kb_id
                     ORDER BY file_id, started_at DESC, id DESC
                    """
                ),
                {"kb_id": kb_id},
            )
        ).mappings()
        run_counts = (
            await session.execute(
                sql_text(
                    """
                    SELECT file_id,
                           count(*) AS total,
                           count(*) FILTER (WHERE status = 'conflict') AS conflicts,
                           count(*) FILTER (WHERE status = 'failed') AS failed,
                           count(*) FILTER (WHERE status = 'pending') AS running
                      FROM regulation_enrich_runs
                     WHERE kb_id = :kb_id
                     GROUP BY file_id
                    """
                ),
                {"kb_id": kb_id},
            )
        ).all()

    latest_runs = {str(row.file_id): dict(row) for row in run_rows}
    run_stats = {
        str(row.file_id): {
            "total": int(row.total or 0),
            "conflicts": int(row.conflicts or 0),
            "failed": int(row.failed or 0),
            "running": int(row.running or 0),
        }
        for row in run_counts
    }

    items = _build_regulation_document_items(files, chunks, indicator_rows)
    for item in items:
        run = latest_runs.get(item["file_id"])
        stats = run_stats.get(item["file_id"], {"total": 0, "conflicts": 0, "failed": 0, "running": 0})
        item["last_run_id"] = run["run_id"] if run else None
        item["last_run_status"] = run["status"] if run else "none"
        item["last_run_started_at"] = run["started_at"].isoformat() if run and run["started_at"] else None
        item["last_run_finished_at"] = run["finished_at"].isoformat() if run and run["finished_at"] else None
        item["last_run_error"] = run["error_message"] if run else None
        item["run_count"] = stats["total"]
        item["conflict_count"] = stats["conflicts"]
        item["failed_count"] = stats["failed"]
        item["processing"] = stats["running"] > 0
        item["run_status"] = (
            "running" if stats["running"] else run["status"] if run else "not_run"
        )
        item["status_reason"] = run["error_message"] if run and run["status"] in {"failed", "conflict"} else ""
    summary = {
        "documents": len(items),
        "enriched": sum(1 for item in items if item["process_status"] == "enriched"),
        "indexed": sum(1 for item in items if item["process_status"] == "indexed"),
        "empty": sum(1 for item in items if item["process_status"] == "empty"),
        "indicators": sum(item["indicators"]["total"] for item in items),
        "verified": sum(item["indicators"]["expert"] + item["indicators"]["reviewed"] for item in items),
        "process_status_counts": {
            "enriched": sum(1 for item in items if item["process_status"] == "enriched"),
            "indexed": sum(1 for item in items if item["process_status"] == "indexed"),
            "empty": sum(1 for item in items if item["process_status"] == "empty"),
        },
        "run_status_counts": {
            "not_run": sum(1 for item in items if item["run_status"] == "not_run"),
            "running": sum(1 for item in items if item["run_status"] == "running"),
            "success": sum(1 for item in items if item["run_status"] == "success"),
            "failed": sum(1 for item in items if item["run_status"] == "failed"),
            "conflict": sum(1 for item in items if item["run_status"] == "conflict"),
        },
    }
    if keyword:
        keyword_value = keyword.strip().lower()
        items = [
            item
            for item in items
            if keyword_value in " ".join([item["filename"], item["suggested_doc_code"], *item["doc_codes"]]).lower()
        ]
    if process_status:
        items = [item for item in items if item["process_status"] == process_status]
    if run_status:
        items = [item for item in items if item["run_status"] == run_status]
    total = len(items)
    start = (page - 1) * page_size
    return {
        "kb_id": kb_id,
        "items": items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": summary,
    }


async def get_bound_kb_id() -> str:
    """返回当前部署绑定的标准规范库知识库 ID；空串表示未绑定。"""
    config = await system_options.get()
    return str(config.get("regulation_library_kb_id") or "").strip()


async def bind_kb(kb_id: str, operator: str | None) -> str:
    """手动绑定当前部署的标准规范库；必须为已索引知识库，写后失效配置缓存。"""
    from pisuan.knowledge.runtime import knowledge_base

    kb_id = str(kb_id or "").strip()
    if not kb_id:
        raise ValueError("kb_id 不能为空")
    if await knowledge_base.get_database_info(kb_id) is None:
        raise ValueError(f"绑定的知识库不存在: {kb_id}")
    async with pg_manager.get_async_session_context() as session:
        await update_option_value(
            session,
            system_options.key,
            {"regulation_library_kb_id": kb_id},
            operator or "",
        )
        await session.commit()
    await invalidate_option_cache(system_options.key)
    return kb_id


async def start_enrich_run(
    kb_id: str,
    file_id: str,
    doc_code: str,
    doc_name: str,
    doc_type: str,
    operator: str | None,
) -> str:
    """创建一次规范加工的 pending 记录，返回 run_id。"""
    await ensure_schema()
    run_id = uuid.uuid4().hex
    async with pg_manager.get_async_session_context() as session:
        await session.execute(
            sql_text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"regulation-enrich:{kb_id}:{doc_code}"},
        )
        await session.execute(
            sql_text(
                """
                UPDATE regulation_enrich_runs
                   SET status = 'failed',
                       finished_at = now(),
                       error_message = '加工进程中断或超过 30 分钟未收敛',
                       updated_at = now()
                 WHERE kb_id = :kb_id
                   AND doc_code = :doc_code
                   AND status = 'pending'
                   AND started_at < now() - interval '30 minutes'
                """
            ),
            {"kb_id": kb_id, "doc_code": doc_code},
        )
        active_run = await session.execute(
            sql_text(
                """
                SELECT run_id
                  FROM regulation_enrich_runs
                 WHERE kb_id = :kb_id
                   AND doc_code = :doc_code
                   AND status = 'pending'
                 LIMIT 1
                """
            ),
            {"kb_id": kb_id, "doc_code": doc_code},
        )
        if active_run.scalar_one_or_none() is not None:
            raise EnrichRunInProgressError(f"{doc_code} 正在加工中，请等待当前任务完成")
        await session.execute(
            sql_text(
                """
                INSERT INTO regulation_enrich_runs
                    (run_id, kb_id, file_id, doc_code, doc_name, doc_type,
                     status, started_by, started_at)
                VALUES
                    (:run_id, :kb_id, :file_id, :doc_code, :doc_name, :doc_type,
                     'pending', :started_by, now())
                """
            ),
            {
                "run_id": run_id,
                "kb_id": kb_id,
                "file_id": file_id,
                "doc_code": doc_code,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "started_by": operator,
            },
        )
        await session.commit()
    return run_id


async def finish_enrich_run(
    run_id: str,
    status: str,
    *,
    error_message: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    """收敛一次规范加工记录；result 仅保存统计与图谱写入结果。"""
    async with pg_manager.get_async_session_context() as session:
        await session.execute(
            sql_text(
                """
                UPDATE regulation_enrich_runs
                   SET status = :status,
                       finished_at = now(),
                       error_message = :error_message,
                       result = CAST(:result AS JSONB),
                       updated_at = now()
                 WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "error_message": error_message,
                "result": json.dumps(result, ensure_ascii=False) if result is not None else None,
            },
        )
        await session.commit()


async def get_regulation_document_detail(kb_id: str, file_id: str) -> dict[str, Any]:
    """返回单份规范的 chunk 结构、表格分类、指标预览和加工运行历史。"""
    await ensure_schema()
    async with pg_manager.get_async_session_context() as session:
        file = (
            await session.execute(
                select(KnowledgeFile).where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.file_id == file_id,
                    KnowledgeFile.is_folder.is_(False),
                )
            )
        ).scalar_one_or_none()
        if file is None:
            return {}

        chunks = (
            await session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.kb_id == kb_id, KnowledgeChunk.file_id == file_id)
                .order_by(KnowledgeChunk.chunk_index)
            )
        ).scalars().all()
        runs = (
            await session.execute(
                sql_text(
                    """
                    SELECT run_id, status, started_by, started_at, finished_at,
                           error_message, result
                      FROM regulation_enrich_runs
                     WHERE kb_id = :kb_id AND file_id = :file_id
                     ORDER BY started_at DESC, id DESC
                    """
                ),
                {"kb_id": kb_id, "file_id": file_id},
            )
        ).mappings().all()

    doc_codes: set[str] = set()
    units: list[dict[str, Any]] = []
    table_roles: dict[str, int] = {}
    for chunk in chunks:
        tags = chunk.tags or {}
        code = str(tags.get("doc_code") or "").strip()
        if not code:
            continue
        doc_codes.add(code)
        if tags.get("unit_no"):
            units.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "doc_code": code,
                    "unit_no": str(tags.get("unit_no") or ""),
                    "unit_type": str(tags.get("unit_type") or "other"),
                    "parent_unit": tags.get("parent_unit"),
                    "title": tags.get("title") or "",
                    "table_role": tags.get("table_role"),
                }
            )
            # 单表 chunk 的角色是标量键（table 预设产出的整表块均为单表）——
            # 此前只数多表 chunk 的 table_units 清单，单表 chunk 角色从不进计数
            if tags.get("unit_type") == "table":
                role = str(tags.get("table_role") or "unclassified")
                table_roles[role] = table_roles.get(role, 0) + 1
        for unit in tags.get("table_units") or []:
            if not isinstance(unit, dict):
                continue
            code_unit = str(unit.get("unit_no") or "").strip()
            if not code_unit:
                continue
            units.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "doc_code": code,
                    "unit_no": code_unit,
                    "unit_type": str(unit.get("unit_type") or "table"),
                    "parent_unit": unit.get("parent_unit"),
                    "title": unit.get("title") or "",
                    "table_role": unit.get("table_role"),
                }
            )
            role = str(unit.get("table_role") or "unclassified")
            table_roles[role] = table_roles.get(role, 0) + 1

    codes = sorted(doc_codes)
    indicators: list[dict[str, Any]] = []
    if codes:
        placeholders = ", ".join(f":code_{i}" for i in range(len(codes)))
        params = {f"code_{i}": code for i, code in enumerate(codes)}
        rows = (
            await session.execute(
                sql_text(
                    f"""
                    SELECT id, doc_code, unit_no, pollutant, metric, limit_value, unit,
                           condition, category, period, source, verified_at, verified_by
                      FROM standard_indicators
                     WHERE doc_code IN ({placeholders})
                     ORDER BY unit_no, pollutant, metric
                    """
                ),
                params,
            )
        ).mappings()
        for row in rows:
            item = dict(row)
            item["verified_at"] = format_utc_datetime(item.get("verified_at"))
            item["layer"] = _layer_of(item.get("source") or "", item.get("verified_at"))
            indicators.append(item)

    run_items = []
    latest_result = None
    for run in runs:
        raw_result = run.get("result")
        run_items.append(
            {
                "run_id": run["run_id"],
                "status": run["status"],
                "started_by": run["started_by"],
                "started_at": run["started_at"].isoformat() if run["started_at"] else None,
                "finished_at": run["finished_at"].isoformat() if run["finished_at"] else None,
                "error_message": run["error_message"],
                "result": raw_result,
            }
        )
        if latest_result is None:
            latest_result = raw_result

    return {
        "file": {
            "file_id": file.file_id,
            "kb_id": file.kb_id,
            "filename": file.filename,
            "status": file.status,
            "chunk_count": int(file.chunk_count or 0),
            "updated_at": file.updated_at.isoformat() if file.updated_at else None,
        },
        "doc_codes": codes,
        "units": units,
        "table_roles": table_roles,
        "indicators": indicators,
        "runs": run_items,
        "latest_run": run_items[0] if run_items else None,
        "latest_result": latest_result,
    }


async def enrich_regulation_file(
    kb_id: str,
    file_id: str,
    doc_code: str,
    doc_name: str,
    doc_type: str,
) -> dict[str, Any]:
    """对已入库的规范文档文件执行富化（幂等，可重跑）。

    Args:
        kb_id/file_id: 知识库与文件标识（上游已入库）
        doc_code: 文档编号，如 "GB 3095-2012"
        doc_name: 文档名称
        doc_type: LEGAL_TYPE_MAP 的 9 类之一
    """
    await ensure_schema()

    # 1+2. 读取 chunks 并解析结构单元 → 回填 tags（同一会话内完成写回）。
    # 含闭合 HTML 表格的 chunk 一律按 <table> 边界拆成独立表格单元（大 chunk 埋多表时不再只认开头一表）；
    # 纯文本/markdown 表格 chunk 仍走 parse_chunk_unit 老路。
    units: list[dict] = []
    table_chunks: list[tuple[str, str, str, str]] = []  # (chunk_id, unit_no, title, content)
    multi_table_chunk_ids: set[str] = set()  # 埋多张表的 chunk：tags 走 table_units 清单，不写标量
    async with pg_manager.get_async_session_context() as session:
        # 冲突守护（检测点唯一）：expert 手工行在场时整个 enrich 直接拒绝，防静默冲掉专家成果
        expert_rows = (
            await session.execute(
                sql_text("SELECT count(*) FROM standard_indicators WHERE doc_code = :code AND source = 'expert'"),
                {"code": doc_code},
            )
        ).scalar_one()
        if expert_rows:
            raise StandardConflictError(f"{doc_code} 检测到手工行，拒绝覆盖，请先删除或迁移手工行")

        result = await session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.kb_id == kb_id, KnowledgeChunk.file_id == file_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        chunks = result.scalars().all()
        if not chunks:
            return {"error": "该文件无 chunks，请先完成知识库索引"}

        for chunk in chunks:
            unit = parse_chunk_unit(chunk.content, doc_type)
            table_units = split_table_units(chunk.content or "")
            if table_units:
                head_unit = unit if unit and unit["unit_type"] != "table" else None
                chunk.tags = {
                    **(chunk.tags or {}),  # 保留入库期预置的既有键，富化键以本次为准
                    "doc_code": doc_code,
                    "doc_type": doc_type,
                    **(head_unit or {}),
                }
                if head_unit:
                    units.append({**head_unit, "chunk_id": chunk.chunk_id})
                for tu in table_units:
                    units.append(
                        {
                            "unit_no": tu["unit_no"],
                            "unit_type": "table",
                            "parent_unit": None,
                            "title": tu["title"],
                            "chunk_id": chunk.chunk_id,
                        }
                    )
                    table_chunks.append((chunk.chunk_id, tu["unit_no"], tu["title"], tu["table_content"]))
                if len(table_units) >= 2:
                    multi_table_chunk_ids.add(chunk.chunk_id)
                elif not head_unit:
                    # 单表 chunk：tags 标量形态与现状一致（向后兼容）
                    tu = table_units[0]
                    chunk.tags.update(unit_no=tu["unit_no"], unit_type="table", parent_unit=None, title=tu["title"])
                continue

            if unit and unit["unit_type"] == "table" and "<table" in (chunk.content or ""):
                # 表格被分块器拦腰切（无闭合 </table>）：整段丢弃不识别，宁可漏不可错
                logger.debug(f"规范富化: chunk {chunk.chunk_id} 含未闭合表格残段，丢弃不识别")
                continue

            if not unit:
                continue
            chunk.tags = {
                **(chunk.tags or {}),
                "doc_code": doc_code,
                "doc_type": doc_type,
                **unit,
            }
            units.append({**unit, "chunk_id": chunk.chunk_id})
            if unit["unit_type"] == "table":
                table_chunks.append((chunk.chunk_id, unit["unit_no"], unit["title"], chunk.content))

    logger.info(f"规范富化: {doc_code} 解析出 {len(units)} 个结构单元, {len(table_chunks)} 张表")

    # 3. 表格打标分流：快路径标题规则 → 慢路径 LLM（判别失败/拿不准 → other，宁可漏抽不可错抽）。
    # limit → 指标抽取；method → 因子→方法名→标准号映射入 tags（本期不建新表）；其余仅打标建图。
    # 多表 chunk 的角色/映射逐单元写 tags["table_units"] 清单；单表 chunk 保持标量键（向后兼容）。
    role_classifier = TableRoleClassifier()
    role_counts = dict.fromkeys(_ALL_ROLES, 0)
    tag_updates: dict[str, dict[str, Any]] = {}  # 单表 chunk_id -> 追加 tags（所有表格都带 table_role）
    unit_tags_by_chunk: dict[str, list[dict[str, Any]]] = {}  # 多表 chunk_id -> table_units 清单
    all_indicators: list[dict] = []
    all_taxonomy_rows: list[dict] = []
    role_memo: dict[str, str] = {}  # unit_no -> role；续表（表N（续））按主表序号继承角色，不重复走 LLM
    for chunk_id, unit_no, title, content in table_chunks:
        role = classify_table_role_by_title(title)
        if role is None and unit_no:
            base = _CONTINUATION_RE.sub("", unit_no).strip()
            if base != unit_no:
                role = role_memo.get(base)
        if role is None:
            role = await role_classifier.classify(doc_code, unit_no, title, content)
        role_memo[unit_no] = role
        role_counts[role] += 1
        unit_tag: dict[str, Any] = {"table_role": role}
        if role == "limit":
            rows = await indicator_extractor.extract_indicators(doc_code, unit_no, content)
            for r in rows:
                r["unit_no"] = unit_no
                r["chunk_id"] = chunk_id
            all_indicators.extend(rows)
        elif role == "taxonomy":
            tax_rows = extract_taxonomy_rows(content)
            for r in tax_rows:
                r["unit_no"] = unit_no
                r["chunk_id"] = chunk_id
            all_taxonomy_rows.extend(tax_rows)
        elif role == "method":
            unit_tag["method_map"] = await indicator_extractor.extract_method_mappings(doc_code, unit_no, content)
        if chunk_id in multi_table_chunk_ids:
            unit_tag.update(unit_no=unit_no, title=title)
            unit_tags_by_chunk.setdefault(chunk_id, []).append(unit_tag)
        else:
            tag_updates[chunk_id] = unit_tag

    # 3.5 表格打标回写 chunk tags（含不抽取的 criteria/param/other 表）。
    # tags 先提交、指标事务在后属有意顺序：两段间中断只留下短暂不一致，幂等重跑可治愈。
    if tag_updates or unit_tags_by_chunk:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_([*tag_updates, *unit_tags_by_chunk]))
            )
            for chunk in result.scalars().all():
                updates = tag_updates.get(chunk.chunk_id, {})
                if chunk.chunk_id in unit_tags_by_chunk:
                    updates = {**updates, "table_units": unit_tags_by_chunk[chunk.chunk_id]}
                chunk.tags = {**(chunk.tags or {}), **updates}

    if all_indicators:
        async with pg_manager.get_async_session_context() as session:
            # 幂等：先删该文档旧指标再插入
            await session.execute(
                sql_text(ENRICH_DELETE_SQL),
                {"code": doc_code},
            )
            for ind in all_indicators:
                await session.execute(
                    sql_text(
                        "INSERT INTO standard_indicators "
                        "(id, doc_code, doc_name, unit_no, chunk_id, pollutant, metric, limit_value,"
                        " unit, condition, category, period) "
                        "VALUES (:id, :code, :doc_name, :uno, :cid, :p, :m, :v, :u, :c, :cat, :prd)"
                    ),
                    {
                        "id": uuid.uuid4().hex[:32],
                        "code": doc_code,
                        "doc_name": doc_name,
                        "uno": ind.get("unit_no"),
                        "cid": ind.get("chunk_id"),
                        "p": ind["pollutant"],
                        "m": ind["metric"],
                        "v": ind["limit_value"],
                        "u": ind.get("unit", ""),
                        "c": ind.get("condition", ""),
                        "cat": ind.get("category", ""),
                        "prd": ind.get("period", ""),
                    },
                )

    if all_taxonomy_rows:
        async with pg_manager.get_async_session_context() as session:
            # 幂等：按 (doc_code, code) upsert，续表/重跑覆盖不重复
            for r in all_taxonomy_rows:
                await session.execute(
                    sql_text(
                        "INSERT INTO eia_taxonomy_rows "
                        "(id, doc_code, unit_no, chunk_id, code, name, meaning, parent_code) "
                        "VALUES (:id, :doc, :uno, :cid, :code, :name, :meaning, :pcode) "
                        "ON CONFLICT (doc_code, code) DO UPDATE SET "
                        "name = EXCLUDED.name, meaning = EXCLUDED.meaning, "
                        "unit_no = EXCLUDED.unit_no, chunk_id = EXCLUDED.chunk_id, "
                        "parent_code = EXCLUDED.parent_code"
                    ),
                    {
                        "id": row_id(doc_code, r["code"]),
                        "doc": doc_code,
                        "uno": r.get("unit_no"),
                        "cid": r.get("chunk_id"),
                        "code": r["code"],
                        "name": r.get("name") or "",
                        "meaning": r.get("meaning") or "",
                        "pcode": r.get("parent_code") or "",
                    },
                )

    # 4. 确定性建图
    writer = RegulationGraphWriter()
    try:
        graph_stats = writer.write_document_graph(doc_code, doc_name, doc_type, units, all_indicators)
    finally:
        writer.close()

    return {
        "doc_code": doc_code,
        "units": len(units),
        "tables": len(table_chunks),
        "indicators": len(all_indicators),
        "taxonomy_rows": len(all_taxonomy_rows),
        "table_roles": role_counts,
        "graph": graph_stats,
    }


def _layer_of(source: str, verified_at: Any) -> str:
    """行级分层：expert 权威 / enrich+verified 已核验候选 / enrich 裸候选（spec §2）。"""
    if source == "expert":
        return "authority"
    return "reviewed" if verified_at else "candidate"


def _anchor_maps(doc: dict[str, Any]) -> tuple[dict[str, str], dict[str, bool]]:
    """standards_index.json 锚点：{code: tier} + {table_key: needs_verification}。"""
    tier_by_code = {s["code"]: s.get("tier") for s in doc.get("standards", []) if s.get("code")}
    tables = doc.get("limit_tables", {})
    # isinstance 守卫承重：实库 limit_tables 含字符串项 _comment，无守卫实测崩溃
    nv_by_ref = {k: bool(t.get("needs_verification")) for k, t in tables.items() if isinstance(t, dict)}
    return tier_by_code, nv_by_ref


async def query_indicators(doc_code: str | None = None, pollutant: str | None = None) -> list[dict]:
    """精确查询指标（分层：authority > reviewed > candidate；供 API 与 writer 工具使用）"""
    await ensure_schema()
    conditions, params = [], {}
    if doc_code:
        conditions.append("doc_code = :code")
        params["code"] = doc_code
    if pollutant:
        conditions.append("pollutant = :p")
        params["p"] = pollutant
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            sql_text(
                f"SELECT doc_code, doc_name, unit_no, pollutant, metric, limit_value, "
                f"unit, condition, category, period, verified_at, verified_by, source, "
                f"table_key FROM standard_indicators {where} "
                f"ORDER BY CASE WHEN source = 'expert' THEN 0 ELSE 1 END, doc_code, unit_no"
            ),
            params,
        )
        rows = [dict(r._mapping) for r in result.all()]
    doc = json.loads((_SKILL_ROOT / "references" / "standards_index.json").read_text(encoding="utf-8"))
    tier_by_code, nv_by_ref = _anchor_maps(doc)
    for r in rows:  # TIMESTAMPTZ → ISO 串 + 派生分层/锚点标注
        r["verified_at"] = format_utc_datetime(r["verified_at"])
        r["layer"] = _layer_of(r["source"], r["verified_at"])
        r["tier"] = tier_by_code.get(r["doc_code"])
        r["table_nv"] = nv_by_ref.get(r["table_key"]) if r["table_key"] else None
    return rows


async def set_unit_verification(doc_code: str, unit_no: str, verified: bool, username: str) -> int:
    """核验/撤销核验指定表单元（doc_code+unit_no）的全部指标行，返回受影响行数。

    enrich 重跑按 doc_code 删旧插新，核验态随行消失——重跑即重验，无需额外失效代码（有意设计）。
    """
    await ensure_schema()
    if verified:
        sql = (
            "UPDATE standard_indicators SET verified_at = now(), verified_by = :verified_by "
            "WHERE doc_code = :code AND unit_no = :uno"
        )
        params: dict[str, Any] = {"verified_by": username, "code": doc_code, "uno": unit_no}
    else:
        sql = (
            "UPDATE standard_indicators SET verified_at = NULL, verified_by = NULL "
            "WHERE doc_code = :code AND unit_no = :uno"
        )
        params = {"code": doc_code, "uno": unit_no}
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(sql_text(sql), params)
        return result.rowcount


async def distinct_doc_codes() -> list[str]:
    """全部去重 doc_code（缺源候选差集与手工查重的归一化比对面）。"""
    await ensure_schema()
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(sql_text("SELECT DISTINCT doc_code FROM standard_indicators"))
        return [r[0] for r in result.all()]


def _validated_manual_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """手工行校验 + limit_value 数值归一（沿用指标抽取同款口径，保证 NUMERIC 列类型安全）。"""
    if len(rows) > _MANUAL_MAX_ROWS:
        raise ValueError(f"限值行数超上限 {_MANUAL_MAX_ROWS}（当前 {len(rows)}）")
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            raise ValueError(f"第 {i} 行须为对象")
        pollutant = str(r.get("pollutant") or "").strip()
        if not pollutant:
            raise ValueError(f"第 {i} 行 pollutant 必填")
        value = indicator_extractor.normalize_limit_value(r.get("limit_value"))
        if value is None:
            raise ValueError(f"第 {i} 行 limit_value 无法解析为数值: {r.get('limit_value')!r}")
        out.append(
            {
                "pollutant": pollutant,
                "metric": str(r.get("metric") or ""),
                "limit_value": value,
                "unit": str(r.get("unit") or ""),
                "condition": str(r.get("condition") or ""),
                "category": str(r.get("category") or ""),
                "period": str(r.get("period") or ""),
            }
        )
    return out


async def _insert_manual_rows(
    session: Any, doc_code: str, doc_name: str | None, rows: list[dict[str, Any]], username: str
) -> None:
    """手工行落库：born-verified（保存即核验生效），unit_no 固定「手录」，source='expert'。"""
    for r in rows:
        await session.execute(
            sql_text(
                "INSERT INTO standard_indicators "
                "(id, doc_code, doc_name, unit_no, chunk_id, pollutant, metric, limit_value,"
                " unit, condition, category, period, verified_at, verified_by, source) "
                "VALUES (:id, :code, :doc_name, :uno, NULL, :p, :m, :v, :u, :c, :cat, :prd,"
                " now(), :verified_by, 'expert')"
            ),
            {
                "id": uuid.uuid4().hex[:32],
                "code": doc_code,
                "doc_name": doc_name,
                "uno": _MANUAL_UNIT_NO,
                "p": r["pollutant"],
                "m": r["metric"],
                "v": r["limit_value"],
                "u": r["unit"],
                "c": r["condition"],
                "cat": r["category"],
                "prd": r["period"],
                "verified_by": username,
            },
        )


async def create_manual_standard(doc_code: str, doc_name: str | None, rows: list[dict[str, Any]], username: str) -> int:
    """专家手工新建标准：doc_code 归一化查重（任何既有行都拒绝），行 born-verified 入权威表。

    返回插入行数；doc_code 已存在 → StandardConflictError，行校验失败 → ValueError。
    """
    await ensure_schema()
    doc_code = doc_code.strip()
    rows = _validated_manual_rows(rows)
    covered = {norm_code(c) for c in await distinct_doc_codes()}
    if norm_code(doc_code) in covered:
        raise StandardConflictError(f"doc_code 已存在指标行，拒绝重复创建: {doc_code}")
    async with pg_manager.get_async_session_context() as session:
        await _insert_manual_rows(session, doc_code, doc_name, rows, username)
    return len(rows)


async def replace_manual_standard(
    doc_code: str, doc_name: str | None, rows: list[dict[str, Any]], username: str
) -> int:
    """整标准替换手工行：事务内删该 doc_code 全部 expert 行再重插（重插行保持 born-verified）。

    目标 doc_code 无 expert 行（不存在或 enrich 行）→ StandardConflictError。
    """
    await ensure_schema()
    doc_code = doc_code.strip()
    rows = _validated_manual_rows(rows)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            sql_text("DELETE FROM standard_indicators WHERE doc_code = :code AND source = 'expert'"),
            {"code": doc_code},
        )
        if result.rowcount == 0:
            raise StandardConflictError(f"doc_code 无手工行，拒绝替换: {doc_code}")
        await _insert_manual_rows(session, doc_code, doc_name, rows, username)
    return len(rows)


async def delete_manual_standard(doc_code: str) -> int:
    """删除该 doc_code 全部手工行；enrich 行拒删（无 expert 行 → StandardConflictError）。"""
    await ensure_schema()
    doc_code = doc_code.strip()
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            sql_text("DELETE FROM standard_indicators WHERE doc_code = :code AND source = 'expert'"),
            {"code": doc_code},
        )
        deleted = result.rowcount
    if deleted == 0:
        raise StandardConflictError(f"doc_code 无手工行，拒绝删除: {doc_code}")
    return deleted
