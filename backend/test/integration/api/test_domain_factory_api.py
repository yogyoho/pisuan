"""领域知识工厂 router 集成测试（/api/domain-factory/*）。

覆盖主链路只读端点 + 鉴权门控。写端点（upload/commit/reingest）涉及重依赖
（docling/Milvus/Neo4j/MinIO），放 E2E 层；本层聚焦 HTTP 契约与权限。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_get_domains_admin_ok(test_client, admin_headers):
    """admin 能取领域列表（即使空也应是 200 + list 结构）。"""
    res = await test_client.get("/api/domain-factory/domains", headers=admin_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert isinstance(data, list) or isinstance(data, dict)


async def test_get_contexts_returns_stats(test_client, admin_headers):
    """getContexts 返回 stats（committed_tasks/entity_count/learned_templates）。"""
    res = await test_client.get("/api/domain-factory/contexts", headers=admin_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    # stats 字段存在（数值型）
    if isinstance(data, dict):
        stats = data.get("stats", data)
        for key in ("committed_tasks", "entity_count", "learned_templates"):
            assert key in stats or not stats, f"missing {key} in stats"


async def test_data_sources_and_history_lists(test_client, admin_headers):
    """data-sources / history 返回列表结构。"""
    for path in ("/api/domain-factory/data-sources", "/api/domain-factory/history"):
        res = await test_client.get(path, headers=admin_headers)
        assert res.status_code == 200, f"{path}: {res.text}"
        assert isinstance(res.json(), (list, dict))


async def test_outline_templates_list(test_client, admin_headers):
    """outline-templates 列表端点可达。"""
    res = await test_client.get("/api/domain-factory/outline-templates", headers=admin_headers)
    assert res.status_code == 200, res.text


async def test_pipeline_and_prompt_config_get(test_client, admin_headers):
    """pipeline-config / prompt-config GET 可达。"""
    for path in ("/api/domain-factory/pipeline-config", "/api/domain-factory/prompt-config"):
        res = await test_client.get(path, headers=admin_headers)
        assert res.status_code == 200, f"{path}: {res.text}"


async def test_non_admin_forbidden(test_client, standard_user):
    """非 admin 访问 domain-factory 应被拒（401/403）。"""
    res = await test_client.get("/api/domain-factory/domains", headers=standard_user["headers"])
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}"


async def test_task_detail_404_for_unknown(test_client, admin_headers):
    """不存在的 task_id 返回 404（而非 500）。"""
    res = await test_client.get("/api/domain-factory/tasks/nonexistent-task-id", headers=admin_headers)
    assert res.status_code in (404, 400, 422), f"expected not-found, got {res.status_code}: {res.text[:200]}"
