"""规范文档富化编排：读 chunks → 解析结构 → 表格打标分流 → 提取指标/方法映射 → 回填 tags → 建图"""

from __future__ import annotations

import re
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
from yuxi.extensions.regulation_library.table_splitter import split_table_units
from yuxi.extensions.regulation_library.unit_parser import parse_chunk_unit
from yuxi.services.eia_limit_extract_core import norm_code
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk
from yuxi.utils import logger
from yuxi.utils.datetime_utils import format_utc_datetime

_ALL_ROLES = ("limit", "method", "criteria", "param", "other")
_CONTINUATION_RE = re.compile(r"[（(]续[)）]\s*$")  # 续表 unit_no 后缀（表N（续）），半/全角括号兼容
_MANUAL_MAX_ROWS = 500  # 手工单次录入行数上限（防误传超大载荷）
_MANUAL_UNIT_NO = "手录"  # 手工行统一表单元号


class StandardConflictError(Exception):
    """standard_indicators 写冲突（手工行挡道 / doc_code 已存在 / 非手工行），路由映射 409。"""


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
                f"SELECT doc_code, unit_no, pollutant, metric, limit_value, unit, condition, category, period, "
                f"verified_at, verified_by, source "
                f"FROM standard_indicators {where} ORDER BY doc_code, unit_no"
            ),
            params,
        )
        rows = [dict(r._mapping) for r in result.all()]
        for r in rows:  # TIMESTAMPTZ → ISO 串，保证 JSON/tool 输出可序列化
            r["verified_at"] = format_utc_datetime(r["verified_at"])
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
        value = indicator_extractor._normalize_limit_value(r.get("limit_value"))
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


async def _insert_manual_rows(session: Any, doc_code: str, rows: list[dict[str, Any]], username: str) -> None:
    """手工行落库：born-verified（保存即核验生效），unit_no 固定「手录」，source='expert'。"""
    for r in rows:
        await session.execute(
            sql_text(
                "INSERT INTO standard_indicators "
                "(id, doc_code, unit_no, chunk_id, pollutant, metric, limit_value,"
                " unit, condition, category, period, verified_at, verified_by, source) "
                "VALUES (:id, :code, :uno, NULL, :p, :m, :v, :u, :c, :cat, :prd, now(), :verified_by, 'expert')"
            ),
            {
                "id": uuid.uuid4().hex[:32],
                "code": doc_code,
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


async def create_manual_standard(doc_code: str, rows: list[dict[str, Any]], username: str) -> int:
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
        await _insert_manual_rows(session, doc_code, rows, username)
    return len(rows)


async def replace_manual_standard(doc_code: str, rows: list[dict[str, Any]], username: str) -> int:
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
        await _insert_manual_rows(session, doc_code, rows, username)
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
