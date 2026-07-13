import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_list_chapter_keys_uses_graph_first():
    from yuxi.agents.toolkits.buildin.tools import list_chapter_keys
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc:
        MockSvc.return_value.list_chapter_keys = AsyncMock(return_value=["地形地貌", "气候气象"])
        result = await list_chapter_keys.ainvoke({"domain": "coal", "report_type": "eia_report"})
    assert isinstance(result, list)
    assert "地形地貌" in result


@pytest.mark.asyncio
async def test_list_chapter_keys_falls_back_to_db():
    from yuxi.agents.toolkits.buildin import tools as tools_mod
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc, \
         patch.object(tools_mod, "DomainFactoryRepository") as MockRepo:
        MockSvc.return_value.list_chapter_keys = AsyncMock(side_effect=Exception("graph down"))
        MockRepo.return_value.list_chapter_keys = AsyncMock(return_value=["DB降级key"])
        result = await tools_mod.list_chapter_keys.ainvoke({"domain": "coal", "report_type": "eia_report"})
    assert isinstance(result, list)
    assert result == ["DB降级key"]


@pytest.mark.asyncio
async def test_get_chapter_outline_uses_graph_first():
    from yuxi.agents.toolkits.buildin.tools import get_chapter_outline
    graph_data = {
        "canonical_chapter_key": "地形地貌", "title": "3.1.1 地形地貌",
        "level": 3, "order": 1, "rigidity": "rigid", "frequency": 1.0,
        "child_chapters": [], "paragraph_roles": [],
    }
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc:
        MockSvc.return_value.get_chapter_outline = AsyncMock(return_value=graph_data)
        result = await get_chapter_outline.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地形地貌"
        })
    assert result is not None
    assert result.get("canonical_chapter_key") == "地形地貌"


@pytest.mark.asyncio
async def test_get_templates_uses_graph_first():
    from yuxi.agents.toolkits.buildin.tools import get_templates
    graph_templates = [
        {"text_pattern": "{{矿区}}位于{{位置}}", "slots": [{"name": "矿区", "type": "string"}], "legal_references": []}
    ]
    with patch("yuxi.services.graph_query_service.GraphQueryService") as MockSvc:
        MockSvc.return_value.get_templates = AsyncMock(return_value=graph_templates)
        result = await get_templates.ainvoke({
            "domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地形地貌"
        })
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "text_pattern" in result[0]
