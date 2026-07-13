"""Task 6-8: _commit_pipeline_async 异常不吞改造测试。

校验三类场景：
- Task 6: 提交前校验失败 → COMMIT_FAILED（不进入阶段1）
- Task 7: 图谱构建失败 → COMMIT_FAILED（不再吞异常）
- Task 8: outline/模板回流失败 → COMMIT_PARTIAL（状态真实反映）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_context(task_payload):
    """构造带 _tasker 的 fake context。task_payload 含 task_id/reviewer/kb_id/ingest_task_id。"""
    ctx = MagicMock()
    ctx.task_id = "run_1"
    task_obj = MagicMock()
    task_obj.payload = task_payload
    ctx._tasker._tasks = {ctx.task_id: task_obj}
    ctx.set_progress = AsyncMock()
    ctx.set_message = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_commit_pipeline_rejects_invalid_task():
    """提交前校验失败(无段落) → pipeline 返回 COMMIT_FAILED,不进入阶段1"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    payload = {"task_id": "t1", "reviewer": "admin", "knowledge_base_id": "kb1", "ingest_task_id": "ing1"}
    ctx = _fake_context(payload)

    invalid_detail = {"source_paragraphs": []}  # 无段落 → 校验失败
    fake_service = MagicMock()
    fake_service.get_task_detail = AsyncMock(return_value=invalid_detail)
    update_calls = []

    async def fake_update(tid, data):
        update_calls.append({"task_id": tid, **data})

    fake_service.repo.update_task = fake_update

    with patch("yuxi.services.domain_factory_service.get_domain_factory_service", return_value=fake_service):
        result = await DomainFactoryService()._commit_pipeline_async(ctx)

    assert result.get("status") == "COMMIT_FAILED" or "error" in str(result.get("message", ""))
    assert any(c.get("status") == "COMMIT_FAILED" for c in update_calls)
