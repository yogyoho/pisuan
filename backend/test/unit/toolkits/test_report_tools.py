import pytest
from unittest.mock import AsyncMock
import yuxi.agents.toolkits.buildin.tools as tools_mod


@pytest.mark.asyncio
async def test_create_report_tool(monkeypatch):
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository",
                        lambda: AsyncMock(create_report=AsyncMock(return_value={"id": "rpt_1", "title": "T", "status": "draft"})))
    out = await tools_mod.create_report.ainvoke(
        {"thread_id": "t1", "title": "T", "domain": "coal", "report_type": "eia_report", "kb_id": "kb_x"})
    assert out["id"] == "rpt_1"


@pytest.mark.asyncio
async def test_get_report_and_set_pps_tools(monkeypatch):
    snap = {"id": "rpt_1", "status": "writing", "pps": [], "chapters": [], "registry": []}
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository",
                        lambda: AsyncMock(get_report_snapshot=AsyncMock(return_value=snap),
                                          upsert_pps_param=AsyncMock(return_value={"entity_key": "k", "value": "v"})))
    rep = await tools_mod.get_report.ainvoke({"report_id": "rpt_1"})
    assert rep["status"] == "writing"
    p = await tools_mod.set_pps_param.ainvoke(
        {"report_id": "rpt_1", "entity_key": "k", "name": "n", "value": "v", "value_type": "number", "unit": "m", "source": "s"})
    assert p["value"] == "v"
