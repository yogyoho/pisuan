"""任务中心合并知识工厂状态的状态优先级单测。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.routers import domain_factory_router

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class _FakeDomainFactoryRepo:
    def __init__(self, status: str):
        self.status = status

    async def get_task(self, _task_id: str):
        return SimpleNamespace(status=self.status)


class _FakeDomainFactoryService:
    def __init__(self, status: str):
        self.repo = _FakeDomainFactoryRepo(status)


class _FakeTasker:
    def __init__(self, tasks: list[dict]):
        self.tasks = tasks

    async def list_tasks(self, limit: int = 100):
        return {"tasks": self.tasks}


def _task(**overrides):
    data = {
        "id": "task-1",
        "type": "domain_factory",
        "status": "running",
        "progress": 50,
        "message": "执行中",
        "cancel_requested": False,
        "payload": {"task_id": "df-1"},
    }
    data.update(overrides)
    return data


async def _tasks_center(monkeypatch, task: dict, df_status: str) -> dict:
    monkeypatch.setattr(
        domain_factory_router,
        "get_domain_factory_service",
        lambda: _FakeDomainFactoryService(df_status),
    )
    monkeypatch.setattr("yuxi.services.task_service.tasker", _FakeTasker([task]))
    return await domain_factory_router.get_tasks_for_task_center(limit=100, current_user=None)


async def test_durable_cancelled_not_overridden_by_domain_status(monkeypatch):
    """durable 已取消时，领域行滞留在 GENERALIZING 也不能把任务显示为进行中。"""
    task = _task(status="cancelled", progress=50, message="任务已取消", cancel_requested=True)

    result = await _tasks_center(monkeypatch, task, "GENERALIZING")

    assert result["tasks"][0]["status"] == "cancelled"
    assert result["tasks"][0]["progress"] == 50
    assert result["tasks"][0]["message"] == "任务已取消"


async def test_cancel_requested_keeps_durable_progress_and_marks_stopping(monkeypatch):
    """取消已提交但 worker 未停止时，提示取消中且不回退 durable 进度。"""
    task = _task(status="running", progress=55, message="正在提取信息...", cancel_requested=True)

    result = await _tasks_center(monkeypatch, task, "GENERALIZING")

    assert result["tasks"][0]["status"] == "running"
    assert result["tasks"][0]["progress"] == 55
    assert result["tasks"][0]["message"] == "取消中，等待 worker 停止"


async def test_active_durable_task_uses_domain_progress(monkeypatch):
    """durable 仍活跃时，领域行继续拥有 ETL 阶段进度语义。"""
    task = _task(status="running", progress=10, message="旧消息", cancel_requested=False)

    result = await _tasks_center(monkeypatch, task, "GENERALIZING")

    assert result["tasks"][0]["status"] == "running"
    assert result["tasks"][0]["progress"] == 80
    assert result["tasks"][0]["message"] == "正在生成槽位模板..."
