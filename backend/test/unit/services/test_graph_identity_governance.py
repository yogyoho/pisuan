import uuid

from neo4j import GraphDatabase

from pisuan.services.entity_meta_service import EntityMetaLoader
from scripts.governance.repair_graph_identity import preflight, reconcile_document_scopes


def test_preflight_detects_unscoped_template_and_invalid_entity_refs():
    """预检必须报出无作用域模板和无效实体引用，不能静默放行。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_identity_{suffix}"
    template_id = f"TPL_TEST_{suffix}"
    entity_id = f"entity_test_{suffix}"
    slot_id = f"SLOT_TEST_{suffix}"
    invalid_ref = f"missing_entity_{suffix}"

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as session:
            session.run(
                """
                CREATE (pt:ParagraphTemplate {
                    id: $template_id,
                    canonical_chapter_key: $canonical_key,
                    kb_id: $kb_id
                })
                """,
                template_id=template_id,
                canonical_key=f"不存在的章节_{suffix}",
                kb_id=kb_id,
            )
            session.run(
                """
                CREATE (e:EntitySchema {id: $entity_id, entity_key: $invalid_ref, kb_id: $kb_id})
                """,
                entity_id=entity_id,
                invalid_ref=invalid_ref,
                kb_id=kb_id,
            )
            session.run(
                """
                CREATE (s:Slot {id: $slot_id, name: $slot_name, entity_ref: $invalid_ref, kb_id: $kb_id})
                """,
                slot_id=slot_id,
                slot_name=f"测试插槽_{suffix}",
                invalid_ref=invalid_ref,
                kb_id=kb_id,
            )

            report = preflight(session, set(EntityMetaLoader().load().keys()))

        assert report["paragraph_scope_unresolved"] >= 1
        assert any(row["id"] == entity_id for row in report["invalid_entity_schemas"])
        assert any(row["id"] == slot_id for row in report["invalid_slot_refs"])
    finally:
        with driver.session() as session:
            session.run("MATCH (n) WHERE n.kb_id = $kb_id DETACH DELETE n", kb_id=kb_id)
        driver.close()


def test_preflight_and_reconcile_document_scope_from_templates():
    """文档作用域应与实际模板一致，治理脚本必须能发现并校正旧域值。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_doc_scope_{suffix}"
    doc_id = f"doc_scope_{suffix}"
    section_id = f"sec_scope_{suffix}"
    template_id = f"TPL_SCOPE_{suffix}"

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as session:
            session.run(
                """
                CREATE (d:Document {id: $doc_id, kb_id: $kb_id, domain_code: 'coal', report_type_code: 'eia_report'})
                CREATE (s:Section {id: $section_id, kb_id: $kb_id})
                CREATE (pt:ParagraphTemplate {
                    id: $template_id,
                    kb_id: $kb_id,
                    domain: 'general',
                    report_type: 'eia_report'
                })
                CREATE (d)-[:HAS_SECTION]->(s)
                CREATE (s)-[:COMPOSED_OF]->(pt)
                """,
                doc_id=doc_id,
                section_id=section_id,
                template_id=template_id,
                kb_id=kb_id,
            )

            report = preflight(session, set(EntityMetaLoader().load().keys()))
            assert any(row["id"] == doc_id for row in report["document_scope_mismatches"])

            updated = reconcile_document_scopes(session)
            assert updated >= 1
            row = session.run(
                "MATCH (d:Document {id: $doc_id}) RETURN d.domain_code AS domain, d.report_type_code AS report_type",
                doc_id=doc_id,
            ).single()
            assert row["domain"] == "general"
            assert row["report_type"] == "eia_report"
    finally:
        with driver.session() as session:
            session.run("MATCH (n) WHERE n.kb_id = $kb_id DETACH DELETE n", kb_id=kb_id)
        driver.close()
