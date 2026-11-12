"""知识工厂图谱身份与聚合治理。

本脚本把存量图谱收敛到当前写入契约：

1. `Document.document_key` 缺失时回填为文档 id，并按文档实际模板作用域校正 `Document.domain_code/report_type_code`；
2. `ParagraphTemplate.domain/report_type` 从贡献文档或唯一章节作用域回填；
3. 清理未命中实体元数据的 `EntitySchema` / `CONSTRAINS`，把无效引用保留为
   `Slot.unresolved_entity_ref`；
4. 从精确 Section 标题重建 `Document -[CONTAINS_CHAPTER]-> ChapterTemplate`；
5. 按唯一文档重算 `source_count`、`frequency`、`rigidity` 与
   `REALIZED_BY.frequency`；
6. 为知识工厂写入的身份标签建立唯一约束。

默认执行写库；`--dry-run` 只打印预检和计划。存在重复 id、缺失 id 或无法唯一
确定模板作用域时脚本失败，不创建约束。

用法（在 api 容器内）：

    python -m scripts.governance.repair_graph_identity --dry-run
    python -m scripts.governance.repair_graph_identity
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from neo4j import GraphDatabase

from pisuan.services.entity_meta_service import EntityMetaLoader


IDENTITY_LABELS = [
    "Document",
    "Section",
    "ParagraphTemplate",
    "Slot",
    "ChapterTemplate",
    "DomainOutline",
    "ParagraphRole",
    "EntitySchema",
    "TableSchema",
    "FormulaTemplate",
    "LegalReference",
    "CausalChain",
    "ConditionRule",
    "DataFlow",
    "ProcessFlow",
    "ProcessStep",
]


def constraint_name(label: str) -> str:
    """返回知识工厂身份标签的唯一约束名。"""
    return f"kf_{label.lower()}_id_unique"


def document_scope_mismatches(session) -> list[dict[str, Any]]:
    """返回文档作用域与唯一模板作用域不一致的记录。"""
    return session.run(
        """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
        WITH d, [scope IN collect(DISTINCT [pt.domain, pt.report_type])
                 WHERE scope[0] IS NOT NULL AND scope[0] <> ''
                   AND scope[1] IS NOT NULL AND scope[1] <> ''] AS scopes
        WHERE size(scopes) = 1
          AND (COALESCE(d.domain_code, '') <> scopes[0][0]
               OR COALESCE(d.report_type_code, '') <> scopes[0][1])
        RETURN d.id AS id,
               COALESCE(d.domain_code, '') AS document_domain,
               COALESCE(d.report_type_code, '') AS document_report_type,
               scopes[0][0] AS template_domain,
               scopes[0][1] AS template_report_type
        ORDER BY id
        """
    ).data()


def preflight(session, valid_entity_refs: set[str]) -> dict[str, Any]:
    """读取存量图谱的身份、作用域和聚合异常，不写库。"""
    report: dict[str, Any] = {
        "duplicate_ids": {},
        "missing_ids": {},
        "missing_document_keys": 0,
        "document_scope_mismatches": [],
        "paragraph_scope_missing": 0,
        "paragraph_scope_unresolved": 0,
        "invalid_entity_schemas": [],
        "invalid_slot_refs": [],
        "documents_without_outline": 0,
        "membership_edges": 0,
    }

    for label in IDENTITY_LABELS:
        missing = session.run(
            f"MATCH (n:{label}) WHERE n.id IS NULL OR n.id = '' RETURN count(n) AS n"
        ).single()["n"]
        if missing:
            report["missing_ids"][label] = int(missing)

        duplicates = session.run(
            f"""
            MATCH (n:{label})
            WHERE n.id IS NOT NULL AND n.id <> ''
            WITH n.id AS id, count(*) AS copies
            WHERE copies > 1
            RETURN id, copies
            ORDER BY copies DESC, id
            LIMIT 20
            """
        ).data()
        if duplicates:
            report["duplicate_ids"][label] = duplicates

    report["missing_document_keys"] = int(
        session.run(
            "MATCH (d:Document) WHERE d.document_key IS NULL OR d.document_key = '' RETURN count(d) AS n"
        ).single()["n"]
    )
    report["document_scope_mismatches"] = document_scope_mismatches(session)
    report["documents_without_outline"] = int(
        session.run(
            """
            MATCH (d:Document)-[:HAS_SECTION]->(:Section)
            WHERE NOT EXISTS { MATCH (d)-[:CONTRIBUTES_TO]->(:DomainOutline) }
            RETURN count(DISTINCT d) AS n
            """
        ).single()["n"]
    )
    report["membership_edges"] = int(
        session.run("MATCH ()-[r:CONTAINS_CHAPTER]->() RETURN count(r) AS n").single()["n"]
    )

    scope_rows = session.run(
        """
        MATCH (pt:ParagraphTemplate)
        WHERE pt.domain IS NULL OR pt.domain = '' OR pt.report_type IS NULL OR pt.report_type = ''
        OPTIONAL MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt)
        OPTIONAL MATCH (d)-[:CONTRIBUTES_TO]->(dol:DomainOutline)
        WITH pt, collect(DISTINCT [dol.domain, dol.report_type]) AS doc_scopes
        OPTIONAL MATCH (ch:ChapterTemplate {canonical_chapter_key: pt.canonical_chapter_key})
        WITH pt, doc_scopes, collect(DISTINCT [ch.domain, ch.report_type]) AS chapter_scopes
        WITH pt,
             CASE
                 WHEN size(doc_scopes) = 1
                      AND doc_scopes[0][0] IS NOT NULL AND doc_scopes[0][0] <> ''
                      AND doc_scopes[0][1] IS NOT NULL AND doc_scopes[0][1] <> ''
                 THEN doc_scopes[0]
                 WHEN size(chapter_scopes) = 1
                      AND chapter_scopes[0][0] IS NOT NULL AND chapter_scopes[0][0] <> ''
                      AND chapter_scopes[0][1] IS NOT NULL AND chapter_scopes[0][1] <> ''
                 THEN chapter_scopes[0]
                 ELSE null
             END AS scope
        RETURN count(pt) AS total,
               sum(CASE WHEN scope IS NULL THEN 1 ELSE 0 END) AS unresolved
        """
    ).single()
    report["paragraph_scope_missing"] = int(scope_rows["total"] or 0)
    report["paragraph_scope_unresolved"] = int(scope_rows["unresolved"] or 0)

    entity_rows = session.run(
        "MATCH (e:EntitySchema) RETURN e.id AS id, e.entity_key AS entity_key ORDER BY e.id"
    ).data()
    report["invalid_entity_schemas"] = [
        row for row in entity_rows if row["entity_key"] not in valid_entity_refs
    ]

    slot_rows = session.run(
        """
        MATCH (s:Slot)
        WHERE s.entity_ref IS NOT NULL AND s.entity_ref <> ''
        RETURN s.id AS id, s.name AS name, s.entity_ref AS entity_ref
        ORDER BY s.id
        """
    ).data()
    report["invalid_slot_refs"] = [
        row for row in slot_rows if row["entity_ref"] not in valid_entity_refs
    ]
    return report


def backfill_document_keys(session) -> int:
    """把缺失的文档身份回填为文档 id。"""
    return int(
        session.run(
            """
            MATCH (d:Document)
            WHERE d.document_key IS NULL OR d.document_key = ''
            SET d.document_key = d.id
            RETURN count(d) AS n
            """
        ).single()["n"]
    )


def backfill_paragraph_scopes(session) -> int:
    """按贡献文档作用域回填段落模板，必要时用唯一章节作用域兜底。"""
    updated = int(
        session.run(
            """
            MATCH (pt:ParagraphTemplate)
            WHERE pt.domain IS NULL OR pt.domain = '' OR pt.report_type IS NULL OR pt.report_type = ''
            OPTIONAL MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt)
            OPTIONAL MATCH (d)-[:CONTRIBUTES_TO]->(dol:DomainOutline)
            WITH pt, collect(DISTINCT [dol.domain, dol.report_type]) AS scopes
            WHERE size(scopes) = 1
              AND scopes[0][0] IS NOT NULL AND scopes[0][0] <> ''
              AND scopes[0][1] IS NOT NULL AND scopes[0][1] <> ''
            SET pt.domain = scopes[0][0], pt.report_type = scopes[0][1]
            RETURN count(pt) AS n
            """
        ).single()["n"]
    )
    updated += int(
        session.run(
            """
            MATCH (pt:ParagraphTemplate)
            WHERE (pt.domain IS NULL OR pt.domain = '' OR pt.report_type IS NULL OR pt.report_type = '')
              AND pt.canonical_chapter_key IS NOT NULL AND pt.canonical_chapter_key <> ''
            OPTIONAL MATCH (ch:ChapterTemplate {canonical_chapter_key: pt.canonical_chapter_key})
            WITH pt, collect(DISTINCT [ch.domain, ch.report_type]) AS scopes
            WHERE size(scopes) = 1
              AND scopes[0][0] IS NOT NULL AND scopes[0][0] <> ''
              AND scopes[0][1] IS NOT NULL AND scopes[0][1] <> ''
            SET pt.domain = scopes[0][0], pt.report_type = scopes[0][1]
            RETURN count(pt) AS n
            """
        ).single()["n"]
    )
    return updated


def reconcile_document_scopes(session) -> int:
    """把文档作用域校正为其实际模板的唯一作用域。"""
    return int(
        session.run(
            """
            MATCH (d:Document)
            OPTIONAL MATCH (d)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
            WITH d, [scope IN collect(DISTINCT [pt.domain, pt.report_type])
                     WHERE scope[0] IS NOT NULL AND scope[0] <> ''
                       AND scope[1] IS NOT NULL AND scope[1] <> ''] AS scopes
            WHERE size(scopes) = 1
              AND (COALESCE(d.domain_code, '') <> scopes[0][0]
                   OR COALESCE(d.report_type_code, '') <> scopes[0][1])
            SET d.domain_code = scopes[0][0], d.report_type_code = scopes[0][1]
            RETURN count(d) AS n
            """
        ).single()["n"]
    )


def clean_entity_schemas(session, valid_entity_refs: set[str]) -> dict[str, int]:
    """删除无效 EntitySchema，把无效 Slot 引用降级为 unresolved。"""
    deleted = int(
        session.run(
            """
            MATCH (e:EntitySchema)
            WHERE e.entity_key IS NULL OR NOT e.entity_key IN $valid_refs
            DETACH DELETE e
            RETURN count(e) AS n
            """,
            valid_refs=sorted(valid_entity_refs),
        ).single()["n"]
    )
    cleared = int(
        session.run(
            """
            MATCH (s:Slot)
            WHERE s.entity_ref IS NOT NULL AND s.entity_ref <> ''
              AND NOT s.entity_ref IN $valid_refs
            OPTIONAL MATCH (s)-[r:CONSTRAINS]->()
            DELETE r
            SET s.unresolved_entity_ref = s.entity_ref
            REMOVE s.entity_ref
            RETURN count(DISTINCT s) AS n
            """,
            valid_refs=sorted(valid_entity_refs),
        ).single()["n"]
    )
    session.run(
        """
        MATCH (s:Slot)
        WHERE s.entity_ref IN $valid_refs
        REMOVE s.unresolved_entity_ref
        """,
        valid_refs=sorted(valid_entity_refs),
    )
    return {"deleted_entity_schemas": deleted, "unresolved_slots": cleared}


def rebuild_membership(session) -> int:
    """按精确 Section 标题重建文档章节成员关系。"""
    session.run(
        """
        MATCH (d:Document)-[:HAS_SECTION]->(:Section)
        MATCH (d)-[r:CONTAINS_CHAPTER]->()
        DELETE r
        """
    )
    return int(
        session.run(
            """
            MATCH (d:Document)-[:HAS_SECTION]->(s:Section)
            MATCH (d)-[:CONTRIBUTES_TO]->(:DomainOutline)-[:HAS_CHAPTER]->(ch:ChapterTemplate)
            WHERE s.title IS NOT NULL AND s.title <> ''
              AND ch.canonical_chapter_key = s.title
            WITH d, s, collect(DISTINCT ch) AS candidates
            WITH d, s, candidates,
                 [candidate IN candidates WHERE candidate.chapter_no = s.section_path_str] AS narrowed
            WITH d,
                 CASE
                     WHEN size(narrowed) = 1 THEN narrowed[0]
                     WHEN size(candidates) = 1 THEN candidates[0]
                     ELSE null
                 END AS chapter
            WHERE chapter IS NOT NULL
            MERGE (d)-[:CONTAINS_CHAPTER]->(chapter)
            RETURN count(*) AS n
            """
        ).single()["n"]
    )


def recompute_source_counts(session) -> int:
    """按唯一 document_key 重算 DomainOutline.source_count。"""
    return int(
        session.run(
            """
            MATCH (dol:DomainOutline)
            OPTIONAL MATCH (dol)<-[:CONTRIBUTES_TO]-(d:Document)
            WITH dol, count(DISTINCT COALESCE(d.document_key, d.id)) AS source_count
            SET dol.source_count = source_count
            RETURN sum(source_count) AS n
            """
        ).single()["n"]
    )


def recompute_chapter_stats(session) -> int:
    """按唯一文档成员关系重算章节频率与刚性。"""
    outlines = session.run(
        "MATCH (dol:DomainOutline) RETURN dol.id AS id, dol.domain AS domain, dol.report_type AS report_type"
    ).data()
    updated = 0
    for outline in outlines:
        result = session.run(
            """
            MATCH (dol:DomainOutline {id: $outline_id})-[:HAS_CHAPTER]->(ch:ChapterTemplate)
            WHERE NOT ch.id STARTS WITH $std_prefix
            OPTIONAL MATCH (d:Document)-[:CONTAINS_CHAPTER]->(ch)
            WITH dol, ch, count(DISTINCT COALESCE(d.document_key, d.id)) AS covered
            SET ch.frequency = CASE
                    WHEN COALESCE(dol.source_count, 0) = 0 THEN 0.0
                    ELSE toFloat(covered) / dol.source_count
                END,
                ch.rigidity = CASE
                    WHEN COALESCE(dol.source_count, 0) = 0 THEN 'conditional'
                    WHEN toFloat(covered) / dol.source_count >= 0.9 THEN 'rigid'
                    WHEN toFloat(covered) / dol.source_count >= 0.5 THEN 'flexible'
                    ELSE 'conditional'
                END
            RETURN count(ch) AS n
            """,
            outline_id=outline["id"],
            std_prefix=f"CH_{outline['domain']}_{outline['report_type']}_std_",
        ).single()
        updated += int(result["n"] or 0)
    return updated


def recompute_role_frequency(session) -> int:
    """按来源文档数重算 ParagraphRole -> ParagraphTemplate 的频率。"""
    outlines = session.run("MATCH (dol:DomainOutline) RETURN dol.id AS id").data()
    updated = 0
    for outline in outlines:
        result = session.run(
            """
            MATCH (dol:DomainOutline {id: $outline_id})-[:HAS_CHAPTER]->(:ChapterTemplate)
                  -[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
            MATCH (pr)-[r:REALIZED_BY]->(pt:ParagraphTemplate)
            OPTIONAL MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt)
            WITH r, count(DISTINCT COALESCE(d.document_key, d.id)) AS doc_count
            SET r.frequency = doc_count
            RETURN count(r) AS n
            """,
            outline_id=outline["id"],
        ).single()
        updated += int(result["n"] or 0)
    return updated


def create_constraints(session) -> list[str]:
    """为知识工厂身份标签建立唯一约束。"""
    created: list[str] = []
    for label in IDENTITY_LABELS:
        name = constraint_name(label)
        session.run(
            f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        )
        created.append(name)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="知识工厂图谱身份与聚合治理")
    parser.add_argument("--dry-run", action="store_true", help="只预检，不写库")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://graph:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "0123456789"))
    args = parser.parse_args()

    valid_entity_refs = set(EntityMetaLoader().load().keys())
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        with driver.session() as session:
            report = preflight(session, valid_entity_refs)
            print(f"模式: {'dry-run(预览)' if args.dry_run else '执行'}")
            print(f"缺失身份: {report['missing_ids']}")
            print(f"重复身份: {report['duplicate_ids']}")
            print(f"缺失 document_key: {report['missing_document_keys']}")
            print(f"文档作用域与模板不一致: {report['document_scope_mismatches']}")
            print(
                "段落模板缺作用域: "
                f"{report['paragraph_scope_missing']}，无法唯一解析: {report['paragraph_scope_unresolved']}"
            )
            print(f"有 Section 但无 DomainOutline 贡献的文档: {report['documents_without_outline']}")
            print(f"无效 EntitySchema: {report['invalid_entity_schemas']}")
            print(f"无效 Slot entity_ref: {report['invalid_slot_refs']}")
            print(f"现有 CONTAINS_CHAPTER 边: {report['membership_edges']}")

            blockers = (
                report["missing_ids"]
                or report["duplicate_ids"]
                or report["paragraph_scope_unresolved"]
            )
            if blockers:
                raise SystemExit("预检未通过：先修复缺失/重复身份或无法唯一解析的模板作用域")
            if args.dry_run:
                return

            document_keys = backfill_document_keys(session)
            scopes = backfill_paragraph_scopes(session)
            document_scopes = reconcile_document_scopes(session)
            entity_stats = clean_entity_schemas(session, valid_entity_refs)
            memberships = rebuild_membership(session)
            source_total = recompute_source_counts(session)
            chapters = recompute_chapter_stats(session)
            roles = recompute_role_frequency(session)
            constraints = create_constraints(session)

            print(f"回填 document_key: {document_keys}")
            print(f"回填段落模板作用域: {scopes}")
            print(f"校正文档作用域: {document_scopes}")
            print(f"清理 EntitySchema: {entity_stats}")
            print(f"重建 CONTAINS_CHAPTER: {memberships}")
            print(f"重算文档来源总数: {source_total}")
            print(f"重算章节聚合: {chapters}")
            print(f"重算 REALIZED_BY.frequency: {roles}")
            print(f"创建/确认唯一约束: {len(constraints)}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
