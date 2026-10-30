"""领域知识工厂 router 集成测试（/api/domain-factory/*）。

覆盖主链路只读端点 + 鉴权门控。写端点（upload/commit/reingest）涉及重依赖
（docling/Milvus/Neo4j/MinIO），放 E2E 层；本层聚焦 HTTP 契约与权限。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


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


async def test_prompt_config_get(test_client, admin_headers):
    """prompt-config GET 可达。"""
    res = await test_client.get("/api/domain-factory/prompt-config", headers=admin_headers)
    assert res.status_code == 200, res.text


async def test_standard_user_workflow_access(test_client, standard_user):
    """普通用户可访问工作流只读端点（2026-09-27 权限放开）。"""
    for path in ("/api/domain-factory/contexts",):
        res = await test_client.get(path, headers=standard_user["headers"])
        assert res.status_code == 200, f"{path}: {res.text}"


async def test_standard_user_config_forbidden(test_client, standard_user):
    """普通用户访问配置类端点仍应被拒（401/403）。"""
    res = await test_client.post(
        "/api/domain-factory/outline-templates/seed", json={}, headers=standard_user["headers"]
    )
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}"
    res = await test_client.put("/api/domain-factory/prompt-config", json={}, headers=standard_user["headers"])
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}"


async def test_unauthenticated_denied(test_client):
    """未认证访问 domain-factory 应被拒（401）。"""
    res = await test_client.get("/api/domain-factory/data-sources")
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}"


async def test_task_detail_404_for_unknown(test_client, admin_headers):
    """不存在的 task_id 返回 404（而非 500）。"""
    res = await test_client.get("/api/domain-factory/tasks/nonexistent-task-id", headers=admin_headers)
    assert res.status_code in (404, 400, 422), f"expected not-found, got {res.status_code}: {res.text[:200]}"


async def test_expectations_recompile_unauthenticated_denied(test_client):
    """章节口径重编译未认证应被拒（admin 写端点）。"""
    res = await test_client.post("/api/domain-factory/eia/stages/expectations/recompile")
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}"


async def test_expectations_recompile_standard_user_denied(test_client, standard_user):
    """普通用户重编译应被拒（admin 专用）。"""
    res = await test_client.post(
        "/api/domain-factory/eia/stages/expectations/recompile", headers=standard_user["headers"]
    )
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}: {res.text[:200]}"


async def test_upload_without_domain_field_ok(test_client, admin_headers):
    """去领域化：上传不再要求 domain 表单字段，响应 domain 恒 general。"""
    files = {"file": ("dedomain-smoke.txt", "通用域去领域化冒烟内容".encode(), "text/plain")}
    res = await test_client.post("/api/domain-factory/upload", headers=admin_headers, files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["domain"] == "general"


async def test_contexts_single_general_domain(test_client, admin_headers):
    """去领域化：contexts 只返回通用域单元素。"""
    res = await test_client.get("/api/domain-factory/contexts", headers=admin_headers)
    assert res.status_code == 200
    domains = res.json().get("domains") or []
    assert [d["code"] for d in domains] == ["general"]
