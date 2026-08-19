"""领域实体构建器 router 集成测试（/api/domain-entity-builder/*）。

注意：entity_type_router.py 是内存 STUB（重启丢数据），真实实体 API 在本 router。
覆盖只读端点 + 鉴权门控。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_list_domains_admin_ok(test_client, admin_headers):
    res = await test_client.get("/api/domain-entity-builder/domains", headers=admin_headers)
    assert res.status_code == 200, res.text
    assert isinstance(res.json(), (list, dict))


async def test_taxonomy_reachable(test_client, admin_headers):
    """taxonomy 端点可达（domain_code 可选）。"""
    res = await test_client.get("/api/domain-entity-builder/taxonomy", headers=admin_headers)
    assert res.status_code in (200, 400, 422), res.text  # 400/422 若 domain 必填


async def test_list_entities_admin_ok(test_client, admin_headers):
    res = await test_client.get("/api/domain-entity-builder/entities", headers=admin_headers)
    assert res.status_code == 200, res.text


async def test_export_config(test_client, admin_headers):
    """导出实体配置（domain_code 取已有领域或默认）。"""
    res = await test_client.get("/api/domain-entity-builder/export", headers=admin_headers)
    assert res.status_code in (200, 400, 404), res.text


async def test_non_admin_forbidden(test_client, standard_user):
    res = await test_client.get("/api/domain-entity-builder/entities", headers=standard_user["headers"])
    assert res.status_code in (401, 403), f"expected auth denial, got {res.status_code}"
