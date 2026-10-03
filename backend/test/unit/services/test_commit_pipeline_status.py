"""Task 6-8: _commit_pipeline_async 异常不吞改造测试。

校验三类场景：
- Task 6: 提交前校验失败 → COMMIT_FAILED（不进入阶段1）
- Task 7: 图谱构建失败 → COMMIT_FAILED（不再吞异常）
- Task 8: outline/模板回流失败 → COMMIT_PARTIAL（状态真实反映）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_context(task_payload):
    """构造符合持久任务 TaskContext 协议的 fake context（payload 直读）。

    task_payload 含 task_id/reviewer/kb_id/ingest_task_id。
    """
    ctx = MagicMock()
    ctx.task_id = "run_1"
    ctx.payload = task_payload
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

    assert result.get("status") == "COMMIT_FAILED"
    assert any(c.get("status") == "COMMIT_FAILED" for c in update_calls)


@pytest.mark.asyncio
async def test_graph_build_failure_marks_commit_failed():
    """图谱构建失败 → COMMIT_FAILED(不再吞异常)"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    ctx, fake_service, update_calls, fake_kb_manager = _partial_pipeline_env()
    with (
        patch("yuxi.services.domain_factory_service.get_domain_factory_service", return_value=fake_service),
        patch("yuxi.knowledge.runtime.knowledge_base", fake_kb_manager),
        patch(
            "yuxi.services.graph_builder.GraphBuilder.build_knowledge_graph", side_effect=RuntimeError("neo4j refused")
        ),
    ):
        await DomainFactoryService()._commit_pipeline_async(ctx)

    assert any(c.get("status") == "COMMIT_FAILED" for c in update_calls), (
        f"图谱失败应标记 COMMIT_FAILED,实际: {update_calls}"
    )


@pytest.mark.asyncio
async def test_outline_failure_marks_commit_partial():
    """outline 生成失败(图谱OK) → COMMIT_PARTIAL"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    ctx, fake_service, update_calls, fake_kb_manager = _partial_pipeline_env()
    fake_service._produce_outlines_async = AsyncMock(side_effect=RuntimeError("LLM超时"))
    with (
        patch("yuxi.services.domain_factory_service.get_domain_factory_service", return_value=fake_service),
        patch("yuxi.knowledge.runtime.knowledge_base", fake_kb_manager),
        patch(
            "yuxi.services.graph_builder.GraphBuilder.build_knowledge_graph",
            return_value={"nodes_created": 0, "relationships_created": 0},
        ),
    ):
        await DomainFactoryService()._commit_pipeline_async(ctx)

    final = [c for c in update_calls if c.get("status")]
    assert any(c["status"] == "COMMIT_PARTIAL" for c in final), f"outline失败应标记 COMMIT_PARTIAL,实际: {final}"


# ------------------------------------------------------------------
# D2/D6 清理批次（[pisuan-custom] 2026-10-04）
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_gate_rejects_missing_knowledge_base_id():
    """D6: 无 knowledge_base_id → 保持 WAITING_REVIEW + error_message,不进入校验/入库阶段"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    payload = {"task_id": "t1", "reviewer": "admin", "knowledge_base_id": None, "ingest_task_id": None}
    ctx = _fake_context(payload)

    fake_service = MagicMock()
    fake_service.get_task_detail = AsyncMock()  # 门在校验之前,不应被触达
    update_calls = []

    async def fake_update(tid, data):
        update_calls.append({"task_id": tid, **data})

    fake_service.repo.update_task = fake_update

    with patch("yuxi.services.domain_factory_service.get_domain_factory_service", return_value=fake_service):
        result = await DomainFactoryService()._commit_pipeline_async(ctx)

    assert result.get("status") == "WAITING_REVIEW"
    assert any("知识库" in c.get("error_message", "") for c in update_calls)
    fake_service.get_task_detail.assert_not_called()


def _partial_pipeline_env():
    """构造走到阶段2.5 的通用夹具: kb_id 已指定、校验通过、入库与后续阶段全部 AsyncMock。

    D3 之后入库阶段是真实调用（manager.get_kb_executor/index_file），必须 mock，
    否则测试会打到容器里真实的 Milvus 管理器（"Database kb1 not found"）。
    """
    payload = {"task_id": "t1", "reviewer": "admin", "knowledge_base_id": "kb1", "ingest_task_id": "ing1"}
    ctx = _fake_context(payload)
    valid_detail = {
        "source_paragraphs": [{"id": "p1", "type": "parameter", "template": {"text_pattern": "{{x}}"}}],
        "domain": "coal",
        "report_type_code": "eia_report",
        "file_name": "test.docx",
    }
    fake_service = MagicMock()
    fake_service.get_task_detail = AsyncMock(return_value=valid_detail)
    fake_service.repo.commit_task = AsyncMock()
    fake_service._save_learned_templates_from_task = AsyncMock(return_value=1)
    fake_service._produce_outlines_async = AsyncMock(return_value=1)
    fake_service._merge_cross_report_knowledge = AsyncMock(return_value={})
    fake_service._upload_original_to_minio = AsyncMock(return_value=("", 100))
    update_calls = []

    async def fake_update(tid, data):
        update_calls.append({"task_id": tid, **data})

    fake_service.repo.update_task = fake_update

    fake_kb_instance = MagicMock()
    fake_kb_instance._save_markdown_to_minio = AsyncMock(return_value="minio://fake")
    fake_kb_instance._persist_file_meta = AsyncMock()
    fake_kb_manager = MagicMock()
    fake_kb_manager.get_kb_executor = AsyncMock(return_value=fake_kb_instance)
    fake_kb_manager.index_file = AsyncMock()
    return ctx, fake_service, update_calls, fake_kb_manager


@pytest.mark.asyncio
async def test_graph_build_skipped_marks_commit_partial():
    """D2: GraphBuilder 内部降级返回 {'skipped': True} → COMMIT_PARTIAL,不误报成功"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    ctx, fake_service, update_calls, fake_kb_manager = _partial_pipeline_env()
    with (
        patch("yuxi.services.domain_factory_service.get_domain_factory_service", return_value=fake_service),
        patch("yuxi.knowledge.runtime.knowledge_base", fake_kb_manager),
        patch(
            "yuxi.services.graph_builder.GraphBuilder.build_knowledge_graph",
            return_value={"nodes_created": 0, "relationships_created": 0, "skipped": True},
        ),
    ):
        await DomainFactoryService()._commit_pipeline_async(ctx)

    final = [c for c in update_calls if c.get("status")]
    assert any(c["status"] == "COMMIT_PARTIAL" for c in final), f"图谱 skipped 应标记 COMMIT_PARTIAL,实际: {final}"


@pytest.mark.asyncio
async def test_graph_build_error_dict_marks_commit_partial():
    """D2: GraphBuilder 折叠写异常返回 {'error': ...} → COMMIT_PARTIAL"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    ctx, fake_service, update_calls, fake_kb_manager = _partial_pipeline_env()
    with (
        patch("yuxi.services.domain_factory_service.get_domain_factory_service", return_value=fake_service),
        patch("yuxi.knowledge.runtime.knowledge_base", fake_kb_manager),
        patch(
            "yuxi.services.graph_builder.GraphBuilder.build_knowledge_graph",
            return_value={"nodes_created": 0, "relationships_created": 0, "error": "neo4j write failed"},
        ),
    ):
        await DomainFactoryService()._commit_pipeline_async(ctx)

    final = [c for c in update_calls if c.get("status")]
    assert any(c["status"] == "COMMIT_PARTIAL" for c in final), f"图谱 error dict 应标记 COMMIT_PARTIAL,实际: {final}"
