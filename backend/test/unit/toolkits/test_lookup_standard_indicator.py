"""§8 lookup_standard_indicator 工具测试（规范库 writer 工具）。

验证从 standard_indicators 查污染物限值，含无参数/无匹配/扩展缺失的兜底。
"""
from unittest.mock import AsyncMock

import pytest

import yuxi.agents.toolkits.buildin.tools as tools_mod


@pytest.mark.asyncio
async def test_lookup_returns_matching_indicators(monkeypatch):
    """命中 → 返回 matched 列表 + count + note。"""
    fake_rows = [
        {"doc_code": "GB 3095-2012", "unit_no": "4.2", "pollutant": "SO2",
         "metric": "年平均浓度限值", "limit_value": 60, "unit": "μg/m³", "condition": "二类区"},
    ]

    async def _fake_query(doc_code=None, pollutant=None):
        return fake_rows

    import sys
    fake_mod = type("M", (), {"query_indicators": _fake_query})
    monkeypatch.setitem(sys.modules, "yuxi.extensions.regulation_library.enrichment_service", fake_mod)

    out = await tools_mod.lookup_standard_indicator.ainvoke({"pollutant": "SO2", "doc_code": "GB 3095-2012"})

    assert out["count"] == 1
    assert out["matched"][0]["limit_value"] == 60
    assert "doc_code" in out["note"]


@pytest.mark.asyncio
async def test_lookup_no_match_returns_hint(monkeypatch):
    """无匹配 → matched=[] + hint 引导用 query_kb。"""
    async def _fake_query(doc_code=None, pollutant=None):
        return []
    import sys
    fake_mod = type("M", (), {"query_indicators": _fake_query})
    monkeypatch.setitem(sys.modules, "yuxi.extensions.regulation_library.enrichment_service", fake_mod)

    out = await tools_mod.lookup_standard_indicator.ainvoke({"pollutant": "罕见污染物"})

    assert out["matched"] == []
    assert "query_kb" in out["hint"]


@pytest.mark.asyncio
async def test_lookup_requires_pollutant():
    """pollutant 必填。"""
    out = await tools_mod.lookup_standard_indicator.ainvoke({"pollutant": ""})
    assert "error" in out
