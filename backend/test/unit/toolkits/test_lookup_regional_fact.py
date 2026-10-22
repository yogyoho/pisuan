"""lookup_regional_fact 工具测试（writer 消费区域事实仓库，P1-2）。

归属管理页裁决产物（confirmed 事实）此前无任何写手工具消费；本工具为唯一只读通道：
region_key 必填（一地区一 KB，不跨区混供）、仅 confirmed、q 子串过滤、无匹配给结构化 hint、
取用走 _track_usage 埋点。仓库契约（status 下推过滤）以 fake 忠实模拟。
"""

import pytest

import pisuan.agents.toolkits.buildin.tools as tools_mod
from pisuan.agents.toolkits.registry import get_all_tool_instances


def _fake_repo(monkeypatch, rows, capture=None):
    """以 repo 契约模拟 list_regional_facts：region/type/status 三过滤下推。"""

    async def _list(self, region_key=None, fact_type=None, status=None, page=1, page_size=20):
        if capture is not None:
            capture.update(region_key=region_key, fact_type=fact_type, status=status, page_size=page_size)
        out = [
            r
            for r in rows
            if (status is None or r["status"] == status)
            and (region_key is None or r["region_key"] == region_key)
            and (fact_type is None or r["fact_type"] == fact_type)
        ]
        return out, len(out)

    repo = type("R", (), {"list_regional_facts": _list})
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", repo)


def _fact(i, status="confirmed", content="事实内容", fact_type="monitoring", region_key="宁夏/横城"):
    return {
        "id": i,
        "fact_type": fact_type,
        "region_key": region_key,
        "content": content,
        "status": status,
        "year": 2023,
        "source_task_id": "t1",
        "source_task_file_name": "a.docx",
        "source_ref": "详查报告 §4.2",
        "created_at": "2026-10-12T00:00:00",
        "updated_at": None,
    }


async def test_registered_in_buildin_registry():
    """验收：工具在 buildin registry 可见（@tool 自动收集）。"""
    assert tools_mod.lookup_regional_fact in get_all_tool_instances()


@pytest.mark.asyncio
async def test_requires_region_key(monkeypatch):
    """region_key 缺省不跨区混供：报错并引导先确认矿区，仓库不被调用。"""
    calls = {}
    _fake_repo(monkeypatch, [], capture=calls)
    out = await tools_mod.lookup_regional_fact.ainvoke({"fact_type": "monitoring"})
    assert "error" in out
    assert calls == {}


@pytest.mark.asyncio
async def test_rejects_invalid_fact_type(monkeypatch):
    calls = {}
    _fake_repo(monkeypatch, [], capture=calls)
    out = await tools_mod.lookup_regional_fact.ainvoke({"fact_type": "whatever", "region_key": "宁夏/横城"})
    assert "error" in out
    assert calls == {}


@pytest.mark.asyncio
async def test_returns_confirmed_only_with_projection(monkeypatch):
    """仅 confirmed：status 下推仓库过滤，draft 恒不外露；输出按写作需要投影。"""
    capture = {}
    rows = [
        _fact(1),
        _fact(2, status="draft", content="草稿事实"),
        _fact(3, status="retired", content="已退役事实"),
    ]
    _fake_repo(monkeypatch, rows, capture=capture)
    out = await tools_mod.lookup_regional_fact.ainvoke({"fact_type": "monitoring", "region_key": "宁夏/横城"})
    assert capture["status"] == "confirmed"
    assert capture["region_key"] == "宁夏/横城"
    assert capture["fact_type"] == "monitoring"
    assert [f["content"] for f in out["facts"]] == ["事实内容"]
    assert set(out["facts"][0]) == {"fact_type", "region_key", "content", "year", "source_ref"}
    assert out["total"] == 1
    assert "source_ref" in out["note"]


@pytest.mark.asyncio
async def test_q_filters_by_content_substring(monkeypatch):
    rows = [
        _fact(1, content="3 煤层涌水量长期观测数据"),
        _fact(2, content="河流水质本底监测"),
    ]
    _fake_repo(monkeypatch, rows)
    out = await tools_mod.lookup_regional_fact.ainvoke(
        {"fact_type": "monitoring", "region_key": "宁夏/横城", "q": "涌水量"}
    )
    assert out["total"] == 1
    assert out["facts"][0]["content"] == "3 煤层涌水量长期观测数据"


@pytest.mark.asyncio
async def test_no_match_returns_structured_hint(monkeypatch):
    """无匹配 → 结构化 hint（引导类比矿/业主数据路径），非裸空数组。"""
    _fake_repo(monkeypatch, [])
    out = await tools_mod.lookup_regional_fact.ainvoke({"fact_type": "monitoring", "region_key": "未知区"})
    assert out["facts"] == []
    assert out["total"] == 0
    assert "hint" in out


@pytest.mark.asyncio
async def test_usage_tracked(monkeypatch):
    """验收：取用走 _track_usage 埋点（result_count 为命中数）。"""
    _fake_repo(monkeypatch, [_fact(1, fact_type="measure")])
    seen = {}
    monkeypatch.setattr(tools_mod, "_track_usage", lambda name, **kw: seen.update(name=name, **kw))
    await tools_mod.lookup_regional_fact.ainvoke({"fact_type": "measure", "region_key": "宁夏/横城"})
    assert seen["name"] == "lookup_regional_fact"
    assert seen["result_count"] == 1
    assert seen["args_summary"]["region_key"] == "宁夏/横城"
