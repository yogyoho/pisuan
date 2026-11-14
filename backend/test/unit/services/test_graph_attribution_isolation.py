"""归属隔离负向证据：同一 domain/report_type 下不同归属不得共享图谱身份或互相命中。"""

import uuid

from neo4j import GraphDatabase

from pisuan.services.domain_factory_region import attribution_scope_key
from pisuan.services.graph_builder import GraphBuilder
from pisuan.services.graph_query_service import GraphQueryService


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


def _prose(para_id: str, path: list[str], content: str) -> dict:
    return {
        "id": para_id,
        "is_title": False,
        "title": "",
        "section_path": path,
        "content": content,
        "classify_type": "prose",
        "template": {"generalized": content, "slots": []},
    }


async def test_attribution_isolates_graph_identity_and_queries():
    """相同章节标题、不同归属：Chapter/ParagraphTemplate 必须各自成点，查询只能命中本归属。"""
    suffix = uuid.uuid4().hex[:10]
    domain = f"test_attr_{suffix}"
    report_type = "eia_report"
    kb_a = f"kb_attr_a_{suffix}"
    kb_b = f"kb_attr_b_{suffix}"
    title = f"共同章节_{suffix}"
    pattern_a = f"甲区域内容_{suffix}"
    pattern_b = f"乙区域内容_{suffix}"
    paragraphs_a = [_title(f"t_a_{suffix}", ["1"], title), _prose(f"p_a_{suffix}", ["1"], pattern_a)]
    paragraphs_b = [_title(f"t_b_{suffix}", ["1"], title), _prose(f"p_b_{suffix}", ["1"], pattern_b)]
    attr_a = attribution_scope_key(kb_a, "hengcheng", "regional", "")
    attr_b = attribution_scope_key(kb_b, "other_region", "regional", "")

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    builder = GraphBuilder()
    query = GraphQueryService()
    try:
        _cleanup(driver, kb_a)
        _cleanup(driver, kb_b)
        builder.build_knowledge_graph(
            kb_id=kb_a,
            doc_id=f"doc_a_{suffix}",
            doc_title="甲区域文档",
            source_paragraphs=paragraphs_a,
            domain_code=domain,
            report_type_code=report_type,
            region_key="hengcheng",
            scope="regional",
        )
        builder.build_knowledge_graph(
            kb_id=kb_b,
            doc_id=f"doc_b_{suffix}",
            doc_title="乙区域文档",
            source_paragraphs=paragraphs_b,
            domain_code=domain,
            report_type_code=report_type,
            region_key="other_region",
            scope="regional",
        )

        with driver.session() as session:
            chapters = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $title})
                RETURN ch.id AS id, ch.attribution AS attribution, ch.kb_id AS kb_id
                """,
                domain=domain,
                rt=report_type,
                title=title,
            ).data()
            templates = session.run(
                """
                MATCH (pt:ParagraphTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $title})
                RETURN pt.id AS id, pt.attribution AS attribution, pt.kb_id AS kb_id
                """,
                domain=domain,
                rt=report_type,
                title=title,
            ).data()
        assert len(chapters) == 2, f"不同归属的章节必须各自成点，实际 {chapters}"
        assert {row["attribution"] for row in chapters} == {attr_a, attr_b}
        assert {row["kb_id"] for row in chapters} == {kb_a, kb_b}
        assert len(templates) == 2, f"不同归属的段落模板必须各自成点，实际 {templates}"
        assert {row["attribution"] for row in templates} == {attr_a, attr_b}

        templates_a = await query.get_templates(domain, report_type, title, attribution=attr_a)
        templates_b = await query.get_templates(domain, report_type, title, attribution=attr_b)
        assert [item["text_pattern"] for item in templates_a] == [pattern_a]
        assert [item["text_pattern"] for item in templates_b] == [pattern_b]

        templates_a_by_kb = await query.get_templates(domain, report_type, title, kb_id=kb_a)
        assert [item["text_pattern"] for item in templates_a_by_kb] == [pattern_a]

        leaves_a = await query.list_leaf_sections(domain, report_type, attribution=attr_a)
        leaves_b = await query.list_leaf_sections(domain, report_type, attribution=attr_b)
        assert len(leaves_a) == 1 and len(leaves_b) == 1
        assert leaves_a[0]["canonical_chapter_key"] == leaves_b[0]["canonical_chapter_key"] == title
        assert leaves_a[0]["section_key"] != leaves_b[0]["section_key"]
    finally:
        query.close()
        builder.close()
        _cleanup(driver, kb_a)
        _cleanup(driver, kb_b)
        driver.close()
