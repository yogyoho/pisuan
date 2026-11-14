import pytest
from langgraph.prebuilt.tool_node import ToolRuntime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _runtime(kb_id: str = "kb_scope"):
    """构造只启用一个知识库的运行时上下文。"""
    context = SimpleNamespace(knowledges=[kb_id] if kb_id else [])
    return ToolRuntime(
        state=None,
        context=context,
        config=None,
        stream_writer=None,
        tool_call_id=None,
        store=None,
    )


def _scope_patch(module, attribution="attr_scope", kb_id="kb_scope"):
    return patch.object(module, "DomainFactoryRepository", **{
        "return_value.get_kb_attribution": AsyncMock(
            return_value={"bound": True, "mixed": False, "attribution": attribution}
        )
    })


@pytest.mark.asyncio
async def test_graph_scope_rejects_ambiguous_or_invisible_knowledge_bases():
    """图谱工具不得在无归属、多库或不可见库时回退全量查询。"""
    from yuxi.agents.toolkits.buildin import tools as tools_mod

    with patch.object(tools_mod, "DomainFactoryRepository") as MockRepo:
        with pytest.raises(ValueError, match="没有启用知识库"):
            await tools_mod._resolve_graph_scope(None, _runtime(""))
        with pytest.raises(ValueError, match="必须显式指定 kb_id"):
            await tools_mod._resolve_graph_scope(
                None, SimpleNamespace(context=SimpleNamespace(knowledges=["kb-a", "kb-b"]))
            )
        with pytest.raises(ValueError, match="可见范围"):
            await tools_mod._resolve_graph_scope(
                "kb-other", SimpleNamespace(context=SimpleNamespace(knowledges=["kb-a"]))
            )
        with pytest.raises(ValueError, match="无法确认知识库会话可见性"):
            await tools_mod._resolve_graph_scope("kb-invisible", None)
        with pytest.raises(ValueError, match="无法确认知识库会话可见性"):
            await tools_mod._resolve_graph_scope("kb-invisible", _runtime(""))
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": False, "mixed": False, "attribution": ""}
        )
        with pytest.raises(ValueError, match="尚未绑定"):
            await tools_mod._resolve_graph_scope("kb-empty", _runtime("kb-empty"))
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": True, "mixed": True, "attribution": ""}
        )
        with pytest.raises(ValueError, match="混合归属"):
            await tools_mod._resolve_graph_scope("kb-mixed", _runtime("kb-mixed"))


@pytest.mark.asyncio
async def test_list_chapter_keys_uses_graph_first():
    from yuxi.agents.toolkits.buildin.tools import list_chapter_keys
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         _scope_patch(tools_mod):
        MockSvc.return_value.list_chapter_keys = AsyncMock(return_value=["地形地貌", "气候气象"])
        result = await list_chapter_keys.ainvoke(
            {"domain": "coal", "report_type": "eia_report", "runtime": _runtime()}
        )
    assert isinstance(result, list)
    assert "地形地貌" in result


@pytest.mark.asyncio
async def test_list_chapter_keys_falls_back_to_db():
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         patch.object(tools_mod, "DomainFactoryRepository") as MockRepo:
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": True, "mixed": False, "attribution": "attr_scope"}
        )
        MockSvc.return_value.list_chapter_keys = AsyncMock(side_effect=Exception("graph down"))
        MockRepo.return_value.list_chapter_keys = AsyncMock(return_value=["DB降级key"])
        result = await tools_mod.list_chapter_keys.ainvoke(
            {"domain": "coal", "report_type": "eia_report", "runtime": _runtime()}
        )
    assert isinstance(result, list)
    assert result == ["DB降级key"]


@pytest.mark.asyncio
async def test_get_chapter_outline_uses_graph_first():
    from yuxi.agents.toolkits.buildin.tools import get_chapter_outline
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    graph_data = {
        "canonical_chapter_key": "地形地貌", "title": "3.1.1 地形地貌",
        "level": 3, "order": 1, "rigidity": "rigid", "frequency": 1.0,
        "child_chapters": [], "paragraph_roles": [],
    }
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         _scope_patch(tools_mod):
        MockSvc.return_value.get_chapter_outline = AsyncMock(return_value=graph_data)
        result = await get_chapter_outline.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地形地貌",
            "runtime": _runtime(),
        })
    assert result is not None
    assert result.get("canonical_chapter_key") == "地形地貌"


@pytest.mark.asyncio
async def test_get_templates_uses_graph_first():
    from yuxi.agents.toolkits.buildin.tools import get_templates
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    graph_templates = [
        {"text_pattern": "{{矿区}}位于{{位置}}", "slots": [{"name": "矿区", "type": "string"}], "legal_references": []}
    ]
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         _scope_patch(tools_mod):
        MockSvc.return_value.get_templates = AsyncMock(return_value=graph_templates)
        result = await get_templates.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地形地貌",
            "runtime": _runtime(),
        })
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "text_pattern" in result[0]


@pytest.mark.asyncio
async def test_get_chapter_outline_falls_back_to_db():
    """get_chapter_outline 图谱异常时降级到 DB。"""
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    db_outline = {
        "canonical_chapter_key": "地形地貌", "title": "3.1.1 地形地貌",
        "level": 3, "order": 1,
    }
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         patch.object(tools_mod, "DomainFactoryRepository") as MockRepo:
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": True, "mixed": False, "attribution": "attr_scope"}
        )
        MockSvc.return_value.get_chapter_outline = AsyncMock(side_effect=Exception("graph down"))
        MockRepo.return_value.get_outline = AsyncMock(return_value=db_outline)
        result = await tools_mod.get_chapter_outline.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地形地貌",
            "runtime": _runtime(),
        })
    assert result.get("canonical_chapter_key") == "地形地貌"


@pytest.mark.asyncio
async def test_get_templates_falls_back_to_db():
    """get_templates 图谱异常时降级到 DB。"""
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    db_templates = [
        {"text_pattern": "DB模板", "slots": [], "legal_references": []}
    ]
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         patch.object(tools_mod, "DomainFactoryRepository") as MockRepo:
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": True, "mixed": False, "attribution": "attr_scope"}
        )
        MockSvc.return_value.get_templates = AsyncMock(side_effect=Exception("graph down"))
        MockRepo.return_value.list_learned_templates_by_key = AsyncMock(return_value=db_templates)
        result = await tools_mod.get_templates.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地形地貌",
            "runtime": _runtime(),
        })
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["text_pattern"] == "DB模板"


@pytest.mark.asyncio
async def test_get_chapter_outline_graph_empty_falls_back_to_db():
    """get_chapter_outline 图谱返回 None 时降级到 DB。"""
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    db_outline = {"canonical_chapter_key": "气候气象", "title": "3.1.2 气候气象"}
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         patch.object(tools_mod, "DomainFactoryRepository") as MockRepo:
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": True, "mixed": False, "attribution": "attr_scope"}
        )
        MockSvc.return_value.get_chapter_outline = AsyncMock(return_value=None)
        MockRepo.return_value.get_outline = AsyncMock(return_value=db_outline)
        result = await tools_mod.get_chapter_outline.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "气候气象",
            "runtime": _runtime(),
        })
    assert result.get("canonical_chapter_key") == "气候气象"


@pytest.mark.asyncio
async def test_list_leaf_sections_uses_graph_first():
    from yuxi.agents.toolkits.buildin import tools as tools_mod

    sections = [
        {
            "section_key": "CH_general_eia_report_c6a4592541",
            "canonical_chapter_key": "气候、气象",
            "chapter_no": "3.3.3",
            "path": ["区域自然和社会经济概况", "自然环境概况", "气候、气象"],
        }
    ]
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         _scope_patch(tools_mod), \
         patch.object(tools_mod, "_track_usage"):
        MockSvc.return_value.list_leaf_sections = AsyncMock(return_value=sections)
        result = await tools_mod.list_leaf_sections.ainvoke(
            {"domain": "coal", "report_type": "eia_report", "runtime": _runtime()}
        )

    assert result == sections
    MockSvc.return_value.list_leaf_sections.assert_awaited_once_with(
        "general", "eia_report", attribution="attr_scope", kb_id="kb_scope"
    )


@pytest.mark.asyncio
async def test_get_templates_by_section_key_uses_exact_lookup():
    from yuxi.agents.toolkits.buildin import tools as tools_mod

    graph_templates = [
        {
            "template_id": "TPL_PARA_exact",
            "text_pattern": "精确节模板",
            "slots": [],
            "legal_references": [],
            "section_key": "CH_general_eia_report_c6a4592541",
        }
    ]
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         _scope_patch(tools_mod), \
         patch.object(tools_mod, "_track_usage"):
        MockSvc.return_value.get_templates = AsyncMock(return_value=[dict(item) for item in graph_templates])
        result = await tools_mod.get_templates.ainvoke(
            {
                "domain": "coal",
                "report_type": "eia_report",
                "section_key": "CH_general_eia_report_c6a4592541",
                "runtime": _runtime(),
            }
        )

    assert result[0]["_source"] == "graph"
    assert result[0]["section_key"] == "CH_general_eia_report_c6a4592541"
    MockSvc.return_value.get_templates.assert_awaited_once_with(
        "general", "eia_report", section_key="CH_general_eia_report_c6a4592541",
        attribution="attr_scope", kb_id="kb_scope"
    )


@pytest.mark.asyncio
async def test_get_templates_by_section_key_does_not_fall_back_to_canonical():
    from yuxi.agents.toolkits.buildin import tools as tools_mod

    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         patch.object(tools_mod, "DomainFactoryRepository") as MockRepo, \
         patch.object(tools_mod, "_track_usage"):
        MockRepo.return_value.get_kb_attribution = AsyncMock(
            return_value={"bound": True, "mixed": False, "attribution": "attr_scope"}
        )
        MockRepo.return_value.list_learned_templates_by_key = AsyncMock(return_value=[])
        MockSvc.return_value.get_templates = AsyncMock(side_effect=RuntimeError("graph down"))
        result = await tools_mod.get_templates.ainvoke(
            {
                "domain": "coal",
                "report_type": "eia_report",
                "section_key": "CH_general_eia_report_c6a4592541",
                "runtime": _runtime(),
            }
        )

    assert result[0]["_source"] == "graph_error"
    assert result[0]["error"]
    MockRepo.return_value.list_learned_templates_by_key.assert_not_awaited()
