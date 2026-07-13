import pytest
from neo4j import GraphDatabase


@pytest.mark.asyncio
async def test_build_knowledge_graph_writes_chapter_canonical_key():
    """build_knowledge_graph 后 ChapterTemplate 应有 canonical_chapter_key"""
    from yuxi.services.graph_builder import GraphBuilder

    builder = GraphBuilder()
    source_paragraphs = [
        {
            "id": "p_t1",
            "is_title": True,
            "title": "测试章节标题A",
            "section_path": ["1", "1.1"],
            "content": "",
            "classify_type": "narrative",
        }
    ]
    try:
        builder.build_knowledge_graph(
            kb_id="kb_test_graph_keys",
            doc_id="doc_test_graph_keys",
            doc_title="测试文档A",
            source_paragraphs=source_paragraphs,
            domain_label="coal",
            base_info={},
            domain_code="coal",
            report_type_code="eia_report",
        )
    finally:
        builder.close()

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (ch:ChapterTemplate {title:'测试章节标题A'}) "
                "WHERE ch.kb_id = 'kb_test_graph_keys' "
                "RETURN ch.canonical_chapter_key AS key"
            )
            rec = result.single()
            assert rec is not None, "ChapterTemplate 应被创建"
            assert rec["key"] == "测试章节标题A", f"canonical_key 应为纯标题,实际: {rec['key']}"
    finally:
        driver.close()
