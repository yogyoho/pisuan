"""get_chapter_outline 图谱回退可见性测试（P1: bug-127）。

验证图谱查询失败回退 DB 时，返回值标注 _source=db_fallback + _degraded_note，
让 agent 感知并可转告用户（不再静默降级）。
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

import yuxi.agents.toolkits.buildin.tools as tools_mod


@pytest.mark.asyncio
async def test_graph_success_tags_source_graph(monkeypatch):
    """图谱命中 → _source=graph，无 degraded_note。"""
    import yuxi.services.graph_query_service as gqs_mod
    svc = MagicMock()
    svc.return_value.get_chapter_outline = AsyncMock(return_value={"canonical_chapter_key": "总则", "purpose": "..."})
    svc.return_value.close = MagicMock()
    monkeypatch.setattr(gqs_mod, "GraphQueryService", svc)
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: AsyncMock())

    out = await tools_mod.get_chapter_outline.ainvoke({"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "总则"})

    assert out["_source"] == "graph"
    assert "_degraded_note" not in out


@pytest.mark.asyncio
async def test_graph_error_fallback_tags_degraded(monkeypatch):
    """图谱抛异常 → 回退 DB，标注 _source=db_fallback + _degraded_note。"""
    import yuxi.services.graph_query_service as gqs_mod
    svc = MagicMock()
    svc.return_value.get_chapter_outline = AsyncMock(side_effect=RuntimeError("neo4j down"))
    svc.return_value.close = MagicMock()
    monkeypatch.setattr(gqs_mod, "GraphQueryService", svc)
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(get_outline=AsyncMock(return_value={"canonical_chapter_key": "总则", "purpose": "db内容"})),
    )

    out = await tools_mod.get_chapter_outline.ainvoke({"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "总则"})

    assert out["_source"] == "db_fallback"
    assert "_degraded_note" in out
    assert "图谱" in out["_degraded_note"]


@pytest.mark.asyncio
async def test_graph_empty_fallback_not_degraded(monkeypatch):
    """图谱返回空（无数据，非错误）→ 回退 DB，_source=db 但无 degraded_note。"""
    import yuxi.services.graph_query_service as gqs_mod
    svc = MagicMock()
    svc.return_value.get_chapter_outline = AsyncMock(return_value=None)
    svc.return_value.close = MagicMock()
    monkeypatch.setattr(gqs_mod, "GraphQueryService", svc)
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(get_outline=AsyncMock(return_value={"canonical_chapter_key": "总则"})),
    )

    out = await tools_mod.get_chapter_outline.ainvoke({"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "总则"})

    assert out["_source"] == "db"
    assert "_degraded_note" not in out
