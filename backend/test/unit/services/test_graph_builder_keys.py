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


@pytest.mark.asyncio
async def test_build_knowledge_graph_writes_para_canonical_key():
    """build_knowledge_graph 后 ParagraphTemplate 应有 canonical_chapter_key(继承所属章节)"""
    from yuxi.services.graph_builder import GraphBuilder

    builder = GraphBuilder()
    source_paragraphs = [
        {
            "id": "p_t2",
            "is_title": True,
            "title": "测试章节ParaKeyB",
            "section_path": ["2", "2.1"],
            "content": "",
            "classify_type": "narrative",
        },
        {
            "id": "p_c2",
            "is_title": False,
            "title": "",
            "section_path": ["2", "2.1"],
            "content": "某矿区位于某地，海拔1000m。",
            "classify_type": "parameter",
            "template": {
                "generalized": "{{矿区ParaB}}位于{{位置B}}，海拔{{海拔B}}。",
                "slots": [
                    {"name": "矿区ParaB", "type": "string"},
                    {"name": "位置B", "type": "string"},
                    {"name": "海拔B", "type": "number"},
                ],
            },
        },
    ]
    try:
        builder.build_knowledge_graph(
            kb_id="kb_test_para_keys",
            doc_id="doc_test_para_keys",
            doc_title="测试ParaKey文档B",
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
                "MATCH (pt:ParagraphTemplate) "
                "WHERE pt.text_pattern CONTAINS '{{矿区ParaB}}位于{{位置B}}' "
                "AND pt.kb_id = 'kb_test_para_keys' "
                "RETURN pt.canonical_chapter_key AS key"
            )
            rec = result.single()
            assert rec is not None, "ParagraphTemplate 应被创建"
            assert rec["key"] == "测试章节ParaKeyB", f"应继承所属章节key,实际: {rec['key']}"
    finally:
        driver.close()


@pytest.mark.asyncio
async def test_backfill_canonical_keys_updates_chapter():
    """GraphBuilder.backfill_canonical_keys 用 outline_map 更新 ChapterTemplate key"""
    from yuxi.services.graph_builder import GraphBuilder

    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as s:
            s.run("MERGE (ch:ChapterTemplate {id:'ch_test_backfill_llm'}) "
                  "SET ch.title='测试LLM回写', ch.canonical_chapter_key='', ch.kb_id='kb_test_backfill_llm'")

        builder = GraphBuilder()
        outline_map = {"ch_test_backfill_llm": "LLM算出的规范名"}
        updated = builder.backfill_canonical_keys(outline_map)
        builder.close()
        assert updated == 1

        with driver.session() as s:
            rec = s.run("MATCH (ch:ChapterTemplate {id:'ch_test_backfill_llm'}) "
                        "RETURN ch.canonical_chapter_key AS key").single()
            assert rec["key"] == "LLM算出的规范名"
    finally:
        with driver.session() as s:
            s.run("MATCH (ch:ChapterTemplate {id:'ch_test_backfill_llm'}) DETACH DELETE ch")
        driver.close()
