"""重算知识工厂文档的 LegalReference/CITES 来源边（幂等治理脚本）。

旧实现把同一 kb 内所有 Section 的所有 TPL_PARA_* 模板连接到每条法规引用，
导致引用来源失真。本脚本按 PostgreSQL 中的 task.source_paragraphs 重算：

- CITES 起点必须是具体来源段落模板；
- 法规清单段落物化 TPL_SRC_* 来源模板（不参与段落角色推荐）；
- 无法定位来源段落或 Section 的引用跳过，不做知识库级回退；
- 只删除可重建文档专属模板上的旧 CITES，共享给不可重建文档的模板保持不动。

文档映射优先使用 `doc_{task_id}`；旧图谱中随机 doc id 按唯一文件名回退，
文件名对应多个任务时视为歧义并跳过。

用法（在 backend 目录或 api 容器内）：
  python -m scripts.governance.rebuild_legal_citations --dry-run
  python -m scripts.governance.rebuild_legal_citations
"""

from __future__ import annotations

import argparse
import os

from pisuan.services.graph_builder import (
    GraphBuilder,
    load_document_section_map,
    plan_legal_citations,
)


def load_tasks() -> list[dict]:
    """从 PostgreSQL 读取所有含 source_paragraphs 的领域工厂任务。"""
    import psycopg

    url = os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/pisuan")
    with psycopg.connect(url.replace("+asyncpg", "").replace("+psycopg", "")) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, file_name, knowledge_base_id, report_type_code, source_paragraphs "
                "FROM domain_factory_tasks "
                "WHERE source_paragraphs IS NOT NULL "
                "ORDER BY id"
            )
            columns = [item[0] for item in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def load_documents(session) -> list[dict]:
    """读取图中全部 Document 的身份、文件名、知识库与图谱作用域。"""
    result = session.run(
        """
        MATCH (d:Document)
        RETURN d.id AS id, d.filename AS filename, d.kb_id AS kb_id,
               d.domain_code AS domain_code, d.report_type_code AS report_type_code,
               d.attribution AS attribution
        ORDER BY d.id
        """
    )
    return [dict(record) for record in result]


def resolve_document_scope(task: dict, document: dict) -> tuple[str, str]:
    """优先沿用图中文档作用域，缺失时按任务元数据归一化回退。"""
    from pisuan.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        _normalize_report_type,
    )

    domain_code = str(document.get("domain_code") or "").strip() or GENERAL_DOMAIN_CODE
    report_type_code = str(document.get("report_type_code") or "").strip()
    if not report_type_code:
        report_type_code = _normalize_report_type(str(task.get("report_type_code") or ""))
    return domain_code, report_type_code


def map_tasks_to_documents(tasks: list[dict], documents: list[dict]) -> tuple[list[dict], list[dict]]:
    """把任务映射到图谱文档；主键优先，唯一文件名回退。"""
    docs_by_id = {doc["id"]: doc for doc in documents}
    docs_by_filename: dict[str, list[dict]] = {}
    for doc in documents:
        docs_by_filename.setdefault(doc.get("filename") or "", []).append(doc)

    mappings: list[dict] = []
    skipped: list[dict] = []
    for task in tasks:
        paragraphs = task.get("source_paragraphs") or []
        if not isinstance(paragraphs, list) or not paragraphs:
            skipped.append({"task_id": task["id"], "reason": "no_source_paragraphs"})
            continue

        doc = docs_by_id.get(f"doc_{task['id']}")
        if doc is None:
            candidates = docs_by_filename.get(task.get("file_name") or "", [])
            task_kb_id = task.get("knowledge_base_id")
            if task_kb_id:
                same_kb = [item for item in candidates if item.get("kb_id") == task_kb_id]
                if same_kb:
                    candidates = same_kb
            if len(candidates) == 1:
                doc = candidates[0]
            elif len(candidates) > 1:
                skipped.append({"task_id": task["id"], "reason": "ambiguous_filename"})
                continue
            else:
                skipped.append({"task_id": task["id"], "reason": "no_document"})
                continue
        mappings.append({"task": task, "doc_id": doc["id"], "document": doc})

    # 同一文档被多个任务命中时状态不确定，保持原图不动。
    tasks_by_doc: dict[str, list[dict]] = {}
    for mapping in mappings:
        tasks_by_doc.setdefault(mapping["doc_id"], []).append(mapping["task"])
    unique_mappings: list[dict] = []
    for doc_id, doc_tasks in tasks_by_doc.items():
        if len(doc_tasks) > 1:
            skipped.append({"doc_id": doc_id, "reason": "multiple_tasks_same_document"})
            continue
        unique_mappings.append({"task": doc_tasks[0], "doc_id": doc_id})
    return unique_mappings, skipped


def count_cites(session) -> int:
    """返回图中 CITES 边总数。"""
    record = session.run("MATCH ()-[r:CITES]->() RETURN count(r) AS n").single()
    return int(record["n"] if record else 0)


def count_scoped_cites(session, doc_ids: list[str]) -> int:
    """返回可重建文档专属模板上的 CITES 边数。"""
    record = session.run(
        """
        MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
        WHERE d.id IN $doc_ids
        WITH DISTINCT pt
        WHERE NOT EXISTS {
            MATCH (other:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt)
            WHERE NOT (other.id IN $doc_ids)
        }
        MATCH (pt)-[r:CITES]->(:LegalReference)
        RETURN count(r) AS n
        """,
        doc_ids=doc_ids,
    ).single()
    return int(record["n"] if record else 0)


def delete_scoped_cites(session, doc_ids: list[str]) -> int:
    """分批删除可重建文档专属模板上的旧 CITES 边。"""
    deleted = 0
    while True:
        record = session.run(
            """
            MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
            WHERE d.id IN $doc_ids
            WITH DISTINCT pt
            WHERE NOT EXISTS {
                MATCH (other:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt)
                WHERE NOT (other.id IN $doc_ids)
            }
            MATCH (pt)-[r:CITES]->(:LegalReference)
            WITH r LIMIT 10000
            DELETE r
            RETURN count(*) AS n
            """,
            doc_ids=doc_ids,
        ).single()
        batch = int(record["n"] if record else 0)
        if batch == 0:
            return deleted
        deleted += batch


def collect_plan(session, mappings: list[dict]) -> dict:
    """预计算每个文档的来源映射与计划边，不写库。"""
    planned_edges = 0
    planned_source_templates = 0
    skipped = {
        "missing_source_paragraph": 0,
        "missing_section": 0,
        "empty_source_content": 0,
        "invalid_reference": 0,
        "duplicate_citation": 0,
    }
    for mapping in mappings:
        task = mapping["task"]
        doc_id = mapping["doc_id"]
        section_map = load_document_section_map(session, doc_id)
        if not section_map:
            continue
        plan = plan_legal_citations(task.get("source_paragraphs") or [], doc_id, section_map)
        planned_edges += len(plan["citations"])
        planned_source_templates += len(plan["templates"])
        for key, value in plan["skipped"].items():
            skipped[key] += value
    return {
        "planned_edges": planned_edges,
        "planned_source_templates": planned_source_templates,
        "skipped": skipped,
    }


def rebuild(session, mappings: list[dict]) -> dict:
    """删除旧 CITES 后按来源段落模板重建。"""
    doc_ids = [mapping["doc_id"] for mapping in mappings]
    deleted = delete_scoped_cites(session, doc_ids)
    created_edges = 0
    materialized_sources = 0
    rebuilt_docs = 0
    for mapping in mappings:
        task = mapping["task"]
        doc_id = mapping["doc_id"]
        domain_code, report_type_code = resolve_document_scope(task, mapping.get("document") or {})
        section_map = load_document_section_map(session, doc_id)
        if not section_map:
            continue
        attribution = str((mapping.get("document") or {}).get("attribution") or "")
        stats = GraphBuilder.rebuild_legal_citations(
            session,
            task.get("knowledge_base_id") or "",
            doc_id,
            task.get("source_paragraphs") or [],
            section_map,
            domain_code,
            report_type_code,
            attribution,
        )
        rebuilt_docs += 1
        created_edges += stats.get("citations_created", 0)
        materialized_sources += stats.get("source_templates_created", 0)
    return {
        "deleted_edges": deleted,
        "rebuilt_docs": rebuilt_docs,
        "created_edges": created_edges,
        "materialized_sources": materialized_sources,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="重算 LegalReference/CITES 来源边")
    parser.add_argument("--dry-run", action="store_true", help="只统计计划与现状，不写入")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://graph:7687"), help="Neo4j URI")
    parser.add_argument("--user", default=os.getenv("NEO4J_USERNAME", "neo4j"), help="Neo4j 用户名")
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "0123456789"), help="Neo4j 密码")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    tasks = load_tasks()
    print(f"模式: {'dry-run(预览)' if args.dry_run else '执行'}")
    print(f"读取领域工厂任务: {len(tasks)}")

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        with driver.session() as session:
            documents = load_documents(session)
            mappings, skipped_tasks = map_tasks_to_documents(tasks, documents)
            doc_ids = [mapping["doc_id"] for mapping in mappings]
            before = count_cites(session)
            scoped = count_scoped_cites(session, doc_ids)
            plan = collect_plan(session, mappings)
            print(f"图中文档: {len(documents)}，可重建文档: {len(mappings)}")
            print(f"跳过任务: {skipped_tasks}")
            print(f"当前 CITES 边: {before}，可重建范围内: {scoped}")
            if scoped < before:
                print(f"注意: {before - scoped} 条 CITES 位于不可重建文档共享模板，保持不动")
            print(f"计划 CITES 边（按文档去重后累计）: {plan['planned_edges']}")
            print(f"计划物化来源专用模板: {plan['planned_source_templates']}")
            print(f"跳过引用: {plan['skipped']}")

            if args.dry_run or not mappings:
                return

            result = rebuild(session, mappings)
            after = count_cites(session)
            print(f"删除旧 CITES 边: {result['deleted_edges']}")
            print(f"重建文档: {result['rebuilt_docs']}")
            print(f"本次新建 CITES 边: {result['created_edges']}")
            print(f"物化来源专用模板: {result['materialized_sources']}")
            print(f"重建后 CITES 边: {after}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
