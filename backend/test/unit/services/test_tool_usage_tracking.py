"""W0 取用率埋点：台账表 repo 方法与 tools.py 接线辅助。"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


def _fake_pg(monkeypatch, sess):
    from yuxi.repositories import domain_factory_repository as mod

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=sess)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_pg = MagicMock()
    fake_pg.get_async_session_context = MagicMock(return_value=cm)
    monkeypatch.setattr(mod, "pg_manager", fake_pg)
    return mod


@pytest.mark.asyncio
async def test_record_tool_usage_inserts_row(monkeypatch):
    sess = _FakeSession()
    mod = _fake_pg(monkeypatch, sess)
    repo = mod.DomainFactoryRepository()
    await repo.record_tool_usage(
        tool_name="get_templates",
        domain="coal",
        report_type="planning_eia",
        args_summary={"canonical_chapter_key": "地表沉陷"},
        result_count=3,
        source="graph",
    )
    assert len(sess.added) == 1
    row = sess.added[0]
    assert row.tool_name == "get_templates"
    assert row.domain == "coal"
    assert row.report_type == "planning_eia"
    assert row.result_count == 3
    assert row.source == "graph"
    assert row.args_summary == {"canonical_chapter_key": "地表沉陷"}


@pytest.mark.asyncio
async def test_record_tool_usage_defaults(monkeypatch):
    """缺省参数落库为 0 / {}，不抛错"""
    sess = _FakeSession()
    mod = _fake_pg(monkeypatch, sess)
    repo = mod.DomainFactoryRepository()
    await repo.record_tool_usage(tool_name="list_report_types")
    row = sess.added[0]
    assert row.result_count == 0
    assert row.args_summary == {}
    assert row.source is None


@pytest.mark.asyncio
async def test_track_usage_failure_does_not_propagate(monkeypatch):
    """fire-and-forget 铁律：record_tool_usage 抛错也不外溢到工具调用方"""
    import asyncio

    from yuxi.agents.toolkits.buildin import tools as tools_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(tools_mod.DomainFactoryRepository, "record_tool_usage", _boom)
    tools_mod._track_usage("get_templates", domain="coal", result_count=1)
    await asyncio.gather(*tools_mod._tracking_tasks)
