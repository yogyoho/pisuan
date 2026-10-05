"""bug-353: _increment_learned_template_match_counts 原方法不存在被静默吞，match_count 永不增量。

验证三层：纯提取函数 → service 方法转发 repo → repo 构造 UPDATE 语句。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------- 纯提取逻辑 ----------

def test_extract_learned_match_ids():
    """只取 learned_ 前缀 id；静态标题模板 id / 缺失 / 非数字全部跳过；去重排序"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    paras = [
        {"template_match": {"template_id": "learned_7"}},
        {"template_match": {"template_id": "learned_3"}},
        {"template_match": {"template_id": "learned_7"}},      # 重复
        {"template_match": {"template_id": "HDR_CONCLUSION"}},  # 静态标题模板
        {"template_match": {"template_id": "learned_abc"}},     # 非数字
        {"template_match": {}},
        {"other": 1},
    ]
    assert DomainFactoryService._extract_learned_match_ids(paras) == [3, 7]


# ---------- service 方法 ----------

@pytest.mark.asyncio
async def test_service_increment_forwards_ids_to_repo():
    from yuxi.services.domain_factory_service import DomainFactoryService

    svc = DomainFactoryService()
    called = {}

    async def fake_inc(ids):
        called["ids"] = ids

    svc.repo = MagicMock()
    svc.repo.increment_learned_template_match_counts = fake_inc
    paras = [{"template_match": {"template_id": "learned_42"}}]
    await svc._increment_learned_template_match_counts(paras)
    assert called["ids"] == [42]


@pytest.mark.asyncio
async def test_increment_noop_when_no_learned_match():
    """无 learned_ 命中时不触 repo（纯静态模板命中的文档不该写库）"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    svc = DomainFactoryService()
    svc.repo = MagicMock()
    svc.repo.increment_learned_template_match_counts = AsyncMock()
    await svc._increment_learned_template_match_counts(
        [{"template_match": {"template_id": "HDR_X"}}]
    )
    svc.repo.increment_learned_template_match_counts.assert_not_awaited()


# ---------- repo 方法（fake session，验证 UPDATE 语句与 rowcount 透传） ----------

class _FakeResult:
    rowcount = 2


class _FakeSession:
    def __init__(self):
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _FakeResult()


@pytest.mark.asyncio
async def test_repo_increment_builds_update(monkeypatch):
    from yuxi.repositories import domain_factory_repository as mod

    sess = _FakeSession()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=sess)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_pg = MagicMock()
    fake_pg.get_async_session_context = MagicMock(return_value=cm)
    monkeypatch.setattr(mod, "pg_manager", fake_pg)

    repo = mod.DomainFactoryRepository()
    n = await repo.increment_learned_template_match_counts([42, 43])
    assert n == 2
    assert len(sess.executed) == 1
    sql = str(sess.executed[0].compile())
    assert "match_count=(domain_factory_learned_templates.match_count + " in sql
    assert "WHERE domain_factory_learned_templates.id IN" in sql


@pytest.mark.asyncio
async def test_repo_increment_empty_ids_no_db(monkeypatch):
    from yuxi.repositories import domain_factory_repository as mod

    fake_pg = MagicMock()
    monkeypatch.setattr(mod, "pg_manager", fake_pg)
    repo = mod.DomainFactoryRepository()
    n = await repo.increment_learned_template_match_counts([])
    assert n == 0
    fake_pg.get_async_session_context.assert_not_called()
