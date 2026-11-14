import pytest
from types import SimpleNamespace
from langgraph.prebuilt.tool_node import ToolRuntime
from unittest.mock import AsyncMock
import yuxi.agents.toolkits.buildin.tools as tools_mod


def _runtime():
    return ToolRuntime(
        state=None,
        context=SimpleNamespace(knowledges=["kb"]),
        config=None,
        stream_writer=None,
        tool_call_id=None,
        store=None,
    )


def _scoped_repo(**methods):
    return AsyncMock(
        get_kb_attribution=AsyncMock(return_value={"bound": True, "mixed": False, "attribution": "attr"}),
        **methods,
    )


@pytest.mark.asyncio
async def test_get_chapter_outline_tool_returns_dict(monkeypatch):
    fake = {"canonical_chapter_key": "地下水环境影响预测", "chapter_title": "地下水", "regulations": []}
    monkeypatch.setattr(
        tools_mod, "DomainFactoryRepository", lambda: _scoped_repo(get_outline=AsyncMock(return_value=fake))
    )
    fn = tools_mod.get_chapter_outline
    out = await fn.ainvoke(
        {"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地下水环境影响预测", "runtime": _runtime()}
    )
    assert out["canonical_chapter_key"] == "地下水环境影响预测"


@pytest.mark.asyncio
async def test_get_templates_tool_returns_list(monkeypatch):
    fake = [{"generalized": "水位{{水位值}}", "slots": [{"name": "水位值"}], "chapter": "5.2"}]
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: _scoped_repo(list_learned_templates_by_key=AsyncMock(return_value=fake)),
    )
    fn = tools_mod.get_templates
    out = await fn.ainvoke(
        {"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地下水环境影响预测", "runtime": _runtime()}
    )
    assert isinstance(out, list) and out[0]["generalized"].startswith("水位")
