import uuid

from neo4j import GraphDatabase

from yuxi.services.graph_builder import GraphBuilder, plan_legal_citations


def _legal_ref(name: str, source_para_id: str, code: str = "") -> dict:
    return {
        "name": name,
        "code": code or None,
        "type": "technical_standard",
        "scope": "national",
        "authority": "",
        "effective_date": "",
        "source_para_id": source_para_id,
    }


def _plan_paragraphs(body_refs: list[dict], legal_refs: list[dict]) -> list[dict]:
    return [
        {
            "id": "p_title",
            "is_title": True,
            "title": "测试引用章",
            "section_path": ["1"],
            "content": "",
            "classify_type": "heading",
        },
        {
            "id": "p_body",
            "section_path": ["1"],
            "content": "本项目执行 GB 1234-2020。",
            "classify_type": "prose",
            "template": {
                "generalized": "本项目执行{{标准}}。",
                "slots": [{"name": "标准", "type": "string"}],
                "legal_references": body_refs,
            },
        },
        {
            "id": "p_legal",
            "section_path": ["1"],
            "content": "（1）《中华人民共和国测试法》，2020-01-01起施行；",
            "classify_type": "legal_reference",
            "template": {"legal_references": legal_refs},
        },
    ]


def test_plan_legal_citations_scopes_each_ref_to_its_source_template():
    """正文引用和法规清单引用必须各自落到来源段落模板，不能互相串边。"""
    paragraphs = _plan_paragraphs(
        [_legal_ref("测试标准A", "p_body", "GB 1234-2020")],
        [_legal_ref("测试法律B", "p_legal")],
    )
    plan = plan_legal_citations(paragraphs, "doc_plan", {"1": {"section_id": "sec_1"}})

    by_source = {citation["source_para_id"]: citation for citation in plan["citations"]}
    assert set(by_source) == {"p_body", "p_legal"}
    assert by_source["p_body"]["ref"]["name"] == "测试标准A"
    assert by_source["p_legal"]["ref"]["name"] == "测试法律B"
    assert by_source["p_body"]["template_id"] != by_source["p_legal"]["template_id"]

    materialized = plan["templates"][by_source["p_legal"]["template_id"]]
    assert materialized["classify_type"] == "legal_reference"
    assert materialized["text_pattern"] == paragraphs[2]["content"]
    assert by_source["p_body"]["template_id"] not in plan["templates"]


def test_plan_legal_citations_skips_missing_source_and_section_without_kb_fallback():
    """来源段落或所属 Section 缺失时跳过，不生成任何知识库级回退边。"""
    paragraphs = _plan_paragraphs(
        [_legal_ref("孤儿标准", "missing_para", "GB 9999-2020")],
        [_legal_ref("孤儿法规", "p_legal")],
    )
    paragraphs[2]["section_path"] = ["9"]
    plan = plan_legal_citations(paragraphs, "doc_plan", {"1": {"section_id": "sec_1"}})

    assert plan["citations"] == []
    assert plan["templates"] == {}
    assert plan["skipped"]["missing_source_paragraph"] == 1
    assert plan["skipped"]["missing_section"] == 1


def test_plan_legal_citations_deduplicates_template_ref_pair():
    """同一来源模板与同一法规只保留一条 CITES。"""
    ref = _legal_ref("重复标准", "p_body", "GB 1234-2020")
    paragraphs = _plan_paragraphs([ref, dict(ref)], [])
    plan = plan_legal_citations(paragraphs, "doc_plan", {"1": {"section_id": "sec_1"}})

    assert len(plan["citations"]) == 1
    assert plan["skipped"]["duplicate_citation"] == 1


def test_map_tasks_to_documents_prefers_primary_then_unique_filename():
    """旧图谱随机 doc id 只在文件名唯一时回退，歧义文档保持不动。"""
    from scripts.governance.rebuild_legal_citations import map_tasks_to_documents

    tasks = [
        {"id": "t1", "file_name": "a.docx", "source_paragraphs": [{}]},
        {"id": "t2", "file_name": "legacy.docx", "source_paragraphs": [{}]},
        {"id": "t3", "file_name": "dup.docx", "source_paragraphs": [{}]},
        {"id": "t4", "file_name": "missing.docx", "source_paragraphs": [{}]},
    ]
    documents = [
        {"id": "doc_t1", "filename": "a.docx"},
        {"id": "doc_legacy", "filename": "legacy.docx"},
        {"id": "doc_dup_1", "filename": "dup.docx"},
        {"id": "doc_dup_2", "filename": "dup.docx"},
    ]

    mappings, skipped = map_tasks_to_documents(tasks, documents)

    assert {mapping["doc_id"] for mapping in mappings} == {"doc_t1", "doc_legacy"}
    reasons = {item.get("task_id"): item["reason"] for item in skipped}
    assert reasons["t3"] == "ambiguous_filename"
    assert reasons["t4"] == "no_document"


def test_resolve_document_scope_prefers_graph_then_normalizes_task_fallback():
    """重算沿用文档已有作用域；文档缺属性时才按任务报告类型归一化回退。"""
    from scripts.governance.rebuild_legal_citations import resolve_document_scope

    assert resolve_document_scope(
        {"report_type_code": "通用"},
        {"domain_code": "general", "report_type_code": "feasibility_report"},
    ) == ("general", "feasibility_report")
    assert resolve_document_scope(
        {"report_type_code": "通用"},
        {"domain_code": "", "report_type_code": ""},
    ) == ("general", "eia_report")


def _cleanup(driver, kb_id: str) -> None:
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.kb_id = $kb_id DETACH DELETE n", kb_id=kb_id)


def _cites(driver, kb_id: str) -> list[dict]:
    with driver.session() as session:
        result = session.run(
            """
            MATCH (pt:ParagraphTemplate)-[:CITES]->(lr:LegalReference)
            WHERE pt.kb_id = $kb_id
            RETURN pt.id AS template_id, pt.text_pattern AS text_pattern,
                   pt.classify_type AS classify_type, pt.source_only AS source_only,
                   lr.name AS ref_name
            ORDER BY template_id, ref_name
            """,
            kb_id=kb_id,
        )
        return [dict(record) for record in result]


def test_graph_builder_cites_concrete_source_templates_only():
    """真实图谱构建后，正文与法规清单模板各自只引用自己的法规，且重建幂等。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_test_legal_cites_{suffix}"
    doc_id = f"doc_test_legal_cites_{suffix}"
    body_ref = f"测试标准_{suffix}"
    legal_ref = f"测试法规_{suffix}"
    paragraphs = _plan_paragraphs(
        [_legal_ref(body_ref, "p_body", "GB 1234-2020")],
        [_legal_ref(legal_ref, "p_legal")],
    )
    paragraphs[2]["content"] = f"（1）《{legal_ref}》，2020-01-01起施行；"

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    try:
        _cleanup(driver, kb_id)
        first_stats = builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=doc_id,
            doc_title=f"引用来源测试_{suffix}",
            source_paragraphs=paragraphs,
        )
        assert first_stats["citations_created"] == 2
        assert first_stats["source_templates_created"] == 1
        rows = _cites(driver, kb_id)
        assert len(rows) == 2, f"只应存在两条来源边，实际: {rows}"

        body_cites = [row for row in rows if row["classify_type"] == "prose"]
        legal_cites = [row for row in rows if row["classify_type"] == "legal_reference"]
        assert [row["ref_name"] for row in body_cites] == [body_ref]
        assert [row["ref_name"] for row in legal_cites] == [legal_ref]
        assert legal_cites[0]["source_only"] is True
        assert legal_cites[0]["text_pattern"] == paragraphs[2]["content"]

        with driver.session() as session:
            role_count = session.run(
                """
                MATCH (:ParagraphRole)-[:REALIZED_BY]->(pt:ParagraphTemplate)
                WHERE pt.kb_id = $kb_id AND pt.source_only = true
                RETURN count(*) AS n
                """,
                kb_id=kb_id,
            ).single()["n"]
        assert role_count == 0, "来源专用模板不得挂到 ParagraphRole"

        second_stats = builder.build_knowledge_graph(
            kb_id=kb_id,
            doc_id=doc_id,
            doc_title=f"引用来源测试_{suffix}",
            source_paragraphs=paragraphs,
        )
        assert second_stats["citations_created"] == 0
        assert second_stats["source_templates_created"] == 0
        assert len(_cites(driver, kb_id)) == 2, "重复构建不得增加 CITES 边"
    finally:
        builder.close()
        _cleanup(driver, kb_id)
        driver.close()
