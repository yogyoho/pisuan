# 归一化清单自动同步：防抖合并、失败隔离、PYTEST 环境禁用（无真实 DB/子进程）。
import asyncio

from pisuan.services import normalization_inventory_sync as sync_mod


def _reset(monkeypatch, steps_calls):
    monkeypatch.setattr(sync_mod, "_state", {"task": None, "dirty": False})
    monkeypatch.setattr(sync_mod, "SYNC_DEBOUNCE_SECONDS", 0)

    async def fake_steps():
        steps_calls.append(1)

    monkeypatch.setattr(sync_mod, "_run_steps", fake_steps)


def test_enabled_guard(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert sync_mod._enabled() is True
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    assert sync_mod._enabled() is False


def test_coalesce_multiple_mutations_into_one_run(monkeypatch):
    steps_calls = []
    _reset(monkeypatch, steps_calls)
    monkeypatch.setattr(sync_mod, "_enabled", lambda: True)

    async def main():
        sync_mod.schedule_sync()
        sync_mod.schedule_sync()
        sync_mod.schedule_sync()
        task = sync_mod._state["task"]
        assert task is not None
        await task

    asyncio.run(main())
    assert len(steps_calls) == 1  # 三次变更合并为一轮
    assert sync_mod._state["dirty"] is False


def test_failure_isolated_and_retriable(monkeypatch):
    calls = []
    _reset(monkeypatch, calls)
    monkeypatch.setattr(sync_mod, "_enabled", lambda: True)

    async def boom():
        raise RuntimeError("gitea 挂了")

    monkeypatch.setattr(sync_mod, "_run_steps", boom)

    async def main():
        sync_mod.schedule_sync()
        await sync_mod._state["task"]  # 失败被吞，不抛

    asyncio.run(main())  # 不抛即通过
    # 失败后 dirty=False；下一次 schedule_sync 重新调度
    assert sync_mod._state["dirty"] is False
    sync_mod.schedule_sync()
    assert sync_mod._state["task"] is not None


def test_disabled_in_pytest_env(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    _reset(monkeypatch, [])
    sync_mod.schedule_sync()
    assert sync_mod._state["task"] is None and sync_mod._state["dirty"] is False
