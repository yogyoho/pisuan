import pytest
from unittest.mock import AsyncMock
import yuxi.agents.toolkits.buildin.tools as tools_mod


@pytest.mark.asyncio
async def test_get_chapter_outline_tool_returns_dict(monkeypatch):
    fake = {"canonical_chapter_key": "地下水环境影响预测", "chapter_title": "地下水", "regulations": []}
    monkeypatch.setattr(
        tools_mod, "DomainFactoryRepository", lambda: AsyncMock(get_outline=AsyncMock(return_value=fake))
    )
    fn = tools_mod.get_chapter_outline
    out = await fn.ainvoke(
        {"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地下水环境影响预测"}
    )
    assert out["canonical_chapter_key"] == "地下水环境影响预测"


@pytest.mark.asyncio
async def test_get_templates_tool_returns_list(monkeypatch):
    fake = [{"generalized": "水位{{水位值}}", "slots": [{"name": "水位值"}], "chapter": "5.2"}]
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(list_learned_templates_by_key=AsyncMock(return_value=fake)),
    )
    fn = tools_mod.get_templates
    out = await fn.ainvoke(
        {"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地下水环境影响预测"}
    )
    assert isinstance(out, list) and out[0]["generalized"].startswith("水位")
