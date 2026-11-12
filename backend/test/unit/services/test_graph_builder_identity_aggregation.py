import uuid

from neo4j import GraphDatabase

from pisuan.services.graph_builder import GraphBuilder


def _cleanup(driver, kb_id: str) -> None:
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.kb_id = $kb_id DETACH DELETE n", kb_id=kb_id)


def _title(para_id: str, path: list[str], title: str) -> dict:
    return {
        "id": para_id,
        "is_title": True,
        "title": title,
        "section_path": path,
        "content": "",
        "classify_type": "heading",
    }


def _prose(para_id: str, path: list[str], content: str, slots: list[dict] | None = None) -> dict:
    return {
        "id": para_id,
        "is_title": False,
        "title": "",
        "section_path": path,
        "content": content,
        "classify_type": "prose",
        "template": {
            "generalized": content,
            "slots": slots or [],
        },
    }


def _table(para_id: str, path: list[str], name: str) -> dict:
    return {
        "id": para_id,
        "is_title": False,
        "title": "",
        "section_path": path,
        "content": "| 指标 | 数值 |\n| --- | --- |\n| PM10 | 1 |",
        "classify_type": "table",
        "template": {
            "table_schema": {
                "name": name,
                "table_type": "general",
                "columns": [{"name": "指标", "type": "string"}, {"name": "数值", "type": "number"}],
            }
        },
    }


def _formula(para_id: str, path: list[str], original: str) -> dict:
    return {
        "id": para_id,
        "is_title": False,
        "title": "",
        "section_path": path,
        "content": original,
        "classify_type": "formula",
        "template": {
            "formula": {
                "original": original,
                "purpose": "测试公式",
                "format": "text",
                "variables": [{"symbol": "x", "name": "变量X", "type": "number", "unit": "m"}],
            }
        },
    }


def test_source_count_uses_distinct_document_key_and_recomputes_frequency():
    """同一文档重复构建不增加 source_count；不同文档才改变章节频率。"""
    suffix = uuid.uuid4().hex[:10]
    domain = f"test_agg_{suffix}"
    report_type = "eia_report"
    kb_id = f"kb_test_agg_{suffix}"
    doc_a = f"doc_a_{suffix}"
    doc_b = f"doc_b_{suffix}"
    title = f"测试章节_{suffix}"
    paragraphs_a = [_title(f"t_a_{suffix}", ["1"], title), _prose(f"p_a_{suffix}", ["1"], "A 内容")]
    paragraphs_b = [_title(f"t_b_{suffix}", ["1"], f"另一章节_{suffix}"), _prose(f"p_b_{suffix}", ["1"], "B 内容")]

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    try:
        _cleanup(driver, kb_id)
        for _ in range(2):
            builder.build_knowledge_graph(
                kb_id=kb_id,
                doc_id=doc_a,
                doc_title="文档A",
                source_paragraphs=paragraphs_a,
                domain_code=domain,
                report_type_code=report_type,
                document_key="same-content",
            )
        with driver.session() as session:
            source_count = session.run(
                "MATCH (dol:DomainOutline {id: $outline_id}) RETURN dol.source_count AS sc",
                outline_id=f"OUTLINE_{domain}_{report_type}",
            ).single()["sc"]
        assert source_count == 1, f"同一文档重复构建后 source_count 应为 1，实际 {source_count}"

        builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=doc_b,
            doc_title="文档B",
            source_paragraphs=paragraphs_b,
            domain_code=domain,
            report_type_code=report_type,
            document_key="other-content",
        )
        with driver.session() as session:
            row = session.run(
                """
                MATCH (dol:DomainOutline {id: $outline_id})-[:HAS_CHAPTER]->(ch:ChapterTemplate)
                WHERE ch.canonical_chapter_key = $title
                RETURN dol.source_count AS sc, ch.frequency AS freq, ch.rigidity AS rigidity
                """,
                outline_id=f"OUTLINE_{domain}_{report_type}",
                title=title,
            ).single()
        assert row["sc"] == 2, f"两篇文档应有 source_count=2，实际 {row['sc']}"
        assert row["freq"] == 0.5, f"章节只出现在 1/2 文档中，frequency 应为 0.5，实际 {row['freq']}"
        assert row["rigidity"] == "flexible", f"frequency=0.5 按现有设计应为 flexible，实际 {row['rigidity']}"
    finally:
        builder.close()
        _cleanup(driver, kb_id)
        driver.close()


def test_document_scope_refreshes_when_same_document_is_reingested():
    """同一文档再次入库时，Document 作用域必须跟随本次构建，而不是保留旧值。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_doc_scope_{suffix}"
    doc_id = f"doc_scope_{suffix}"
    legacy_domain = f"test_legacy_{suffix}"
    current_domain = f"test_current_{suffix}"
    paragraphs = [
        _title(f"t_scope_{suffix}", ["1"], f"作用域章节_{suffix}"),
        _prose(f"p_scope_{suffix}", ["1"], "作用域内容"),
    ]

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    try:
        _cleanup(driver, kb_id)
        for domain in (legacy_domain, current_domain):
            builder.build_knowledge_graph(
                kb_id=kb_id,
                doc_id=doc_id,
                doc_title="作用域文档",
                source_paragraphs=paragraphs,
                domain_code=domain,
                report_type_code="eia_report",
            )
        with driver.session() as session:
            row = session.run(
                "MATCH (d:Document {id: $doc_id}) RETURN d.domain_code AS domain, d.report_type_code AS report_type",
                doc_id=doc_id,
            ).single()
        assert row["domain"] == current_domain
        assert row["report_type"] == "eia_report"
    finally:
        builder.close()
        _cleanup(driver, kb_id)
        driver.close()


def test_same_slot_name_with_different_semantics_creates_two_slots():
    """同名 Slot 的类型或单位不同，不能合并成一个节点。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_slot_{suffix}"
    slot_name = f"温度_{suffix}"
    paragraphs = [
        _title(f"t_{suffix}", ["1"], f"槽位章节_{suffix}"),
        _prose(
            f"p_{suffix}",
            ["1"],
            "温度记录",
            [
                {"name": slot_name, "type": "number", "unit": "C"},
                {"name": slot_name, "type": "number", "unit": "F"},
            ],
        ),
    ]

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    try:
        _cleanup(driver, kb_id)
        builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=f"doc_slot_{suffix}",
            doc_title="槽位测试",
            source_paragraphs=paragraphs,
            domain_code=f"test_slot_{suffix}",
            report_type_code="eia_report",
        )
        with driver.session() as session:
            rows = list(
                session.run(
                    "MATCH (s:Slot {name: $name, kb_id: $kb_id}) RETURN s.unit AS unit ORDER BY s.unit",
                    name=slot_name,
                    kb_id=kb_id,
                )
            )
        assert len(rows) == 2, f"不同单位应生成两个 Slot，实际 {len(rows)}"
        assert [row["unit"] for row in rows] == ["C", "F"]
    finally:
        builder.close()
        _cleanup(driver, kb_id)
        driver.close()


def test_invalid_entity_ref_does_not_create_entity_schema_or_constrains():
    """未命中实体元数据的 entity_ref 只保留为 unresolved，不造 EntitySchema。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_entity_{suffix}"
    bad_ref = f"missing_entity_{suffix}.最大值"
    paragraphs = [
        _title(f"t_{suffix}", ["1"], f"实体章节_{suffix}"),
        _prose(
            f"p_{suffix}",
            ["1"],
            "实体引用",
            [{"name": f"数值_{suffix}", "type": "number", "entity_ref": bad_ref}],
        ),
    ]

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    try:
        _cleanup(driver, kb_id)
        builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=f"doc_entity_{suffix}",
            doc_title="实体测试",
            source_paragraphs=paragraphs,
            domain_code=f"test_entity_{suffix}",
            report_type_code="eia_report",
        )
        with driver.session() as session:
            schema_count = session.run(
                "MATCH (e:EntitySchema {entity_key: $key}) RETURN count(e) AS n", key=bad_ref
            ).single()["n"]
            unresolved = session.run(
                "MATCH (s:Slot {unresolved_entity_ref: $ref, kb_id: $kb_id}) RETURN count(s) AS n",
                ref=bad_ref,
                kb_id=kb_id,
            ).single()["n"]
            constrains = session.run(
                "MATCH (:Slot {kb_id: $kb_id})-[:CONSTRAINS]->(:EntitySchema) RETURN count(*) AS n",
                kb_id=kb_id,
            ).single()["n"]
        assert schema_count == 0
        assert unresolved == 1
        assert constrains == 0
    finally:
        builder.close()
        _cleanup(driver, kb_id)
        driver.close()


def test_table_and_formula_attach_to_exact_source_template_and_section():
    """同一 KB 下相同 Section 路径的两个文档不能互相串表格/公式来源。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_provenance_{suffix}"
    doc_a = f"doc_prov_a_{suffix}"
    doc_b = f"doc_prov_b_{suffix}"
    path = ["1"]
    title = f"共用路径章节_{suffix}"
    table_name = f"测试表_{suffix}"
    formula_text = f"Q_{suffix}=x*2"
    paragraphs_a = [_title(f"t_a_{suffix}", path, title), _table(f"table_{suffix}", path, table_name)]
    paragraphs_b = [_title(f"t_b_{suffix}", path, title), _formula(f"formula_{suffix}", path, formula_text)]

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    try:
        _cleanup(driver, kb_id)
        builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=doc_a,
            doc_title="文档A",
            source_paragraphs=paragraphs_a,
            domain_code=f"test_prov_{suffix}",
            report_type_code="eia_report",
        )
        builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=doc_b,
            doc_title="文档B",
            source_paragraphs=paragraphs_b,
            domain_code=f"test_prov_{suffix}",
            report_type_code="eia_report",
        )
        with driver.session() as session:
            table_docs = [
                row["doc_id"]
                for row in session.run(
                    """
                    MATCH (d:Document)-[:HAS_SECTION]->(s:Section)-[:HAS_TABLE_SCHEMA]->(ts:TableSchema {name: $name})
                    RETURN DISTINCT d.id AS doc_id
                    """,
                    name=table_name,
                )
            ]
            formula_docs = [
                row["doc_id"]
                for row in session.run(
                    """
                    MATCH (d:Document)-[:HAS_SECTION]->(s:Section)-[:HAS_FORMULA]->
                          (f:FormulaTemplate {original: $original})
                    RETURN DISTINCT d.id AS doc_id
                    """,
                    original=formula_text,
                )
            ]
            direct_table_sources = session.run(
                "MATCH (:ParagraphTemplate {kb_id: $kb_id})-[:HAS_TABLE_SCHEMA]->"
                "(:TableSchema {name: $name}) RETURN count(*) AS n",
                kb_id=kb_id,
                name=table_name,
            ).single()["n"]
            direct_formula_sources = session.run(
                "MATCH (:ParagraphTemplate {kb_id: $kb_id})-[:HAS_FORMULA]->"
                "(:FormulaTemplate {original: $original}) RETURN count(*) AS n",
                kb_id=kb_id,
                original=formula_text,
            ).single()["n"]
        assert table_docs == [doc_a], f"表格只能挂到文档A，实际 {table_docs}"
        assert formula_docs == [doc_b], f"公式只能挂到文档B，实际 {formula_docs}"
        assert direct_table_sources == 1
        assert direct_formula_sources == 1
    finally:
        builder.close()
        _cleanup(driver, kb_id)
        driver.close()
