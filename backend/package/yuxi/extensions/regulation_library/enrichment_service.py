"""规范文档富化编排：读 chunks → 解析结构 → 表格打标分流 → 提取指标/方法映射 → 回填 tags → 建图"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as sql_text

from yuxi.extensions.regulation_library import indicator_extractor
from yuxi.extensions.regulation_library.graph_writer import RegulationGraphWriter
from yuxi.extensions.regulation_library.models import ensure_schema
from yuxi.extensions.regulation_library.table_role_classifier import (
    TableRoleClassifier,
    classify_table_role_by_title,
)
from yuxi.extensions.regulation_library.unit_parser import parse_chunk_unit
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk
from yuxi.utils import logger

_ALL_ROLES = ("limit", "method", "criteria", "param", "other")


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

    # 1+2. 读取 chunks 并解析结构单元 → 回填 tags（同一会话内完成写回）
    units: list[dict] = []
    table_chunks: list[tuple[str, str, str, str]] = []  # (chunk_id, unit_no, title, content)
    async with pg_manager.get_async_session_context() as session:
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
            if not unit:
                continue
            chunk.tags = {
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
    role_classifier = TableRoleClassifier()
    role_counts = dict.fromkeys(_ALL_ROLES, 0)
    tag_updates: dict[str, dict[str, Any]] = {}  # chunk_id -> 追加 tags（所有表格都带 table_role）
    all_indicators: list[dict] = []
    for chunk_id, unit_no, title, content in table_chunks:
        role = classify_table_role_by_title(title)
        if role is None:
            role = await role_classifier.classify(doc_code, unit_no, title, content)
        role_counts[role] += 1
        tag_updates[chunk_id] = {"table_role": role}
        if role == "limit":
            rows = await indicator_extractor.extract_indicators(doc_code, unit_no, content)
            for r in rows:
                r["unit_no"] = unit_no
                r["chunk_id"] = chunk_id
            all_indicators.extend(rows)
        elif role == "method":
            tag_updates[chunk_id]["method_map"] = await indicator_extractor.extract_method_mappings(
                doc_code, unit_no, content
            )

    # 3.5 表格打标回写 chunk tags（含不抽取的 criteria/param/other 表）
    if tag_updates:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_(list(tag_updates))))
            for chunk in result.scalars().all():
                chunk.tags = {**(chunk.tags or {}), **tag_updates.get(chunk.chunk_id, {})}

    if all_indicators:
        async with pg_manager.get_async_session_context() as session:
            # 幂等：先删该文档旧指标再插入
            await session.execute(
                sql_text("DELETE FROM standard_indicators WHERE doc_code = :code"),
                {"code": doc_code},
            )
            for ind in all_indicators:
                await session.execute(
                    sql_text(
                        "INSERT INTO standard_indicators "
                        "(id, doc_code, unit_no, chunk_id, pollutant, metric, limit_value,"
                        " unit, condition, category, period) "
                        "VALUES (:id, :code, :uno, :cid, :p, :m, :v, :u, :c, :cat, :prd)"
                    ),
                    {
                        "id": uuid.uuid4().hex[:32],
                        "code": doc_code,
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
        "table_roles": role_counts,
        "graph": graph_stats,
    }


async def query_indicators(doc_code: str | None = None, pollutant: str | None = None) -> list[dict]:
    """精确查询指标（供 API 与 writer 工具使用）"""
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
                f"SELECT doc_code, unit_no, pollutant, metric, limit_value, unit, condition, category, period "
                f"FROM standard_indicators {where} ORDER BY doc_code, unit_no"
            ),
            params,
        )
        return [dict(r._mapping) for r in result.all()]
