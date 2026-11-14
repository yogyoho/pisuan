"""领域实体构建器 router 集成测试（/api/domain-entity-builder/*）。

注意：entity_type_router.py 是内存 STUB（重启丢数据），真实实体 API 在本 router。
覆盖只读端点 + 鉴权门控 + 写入校验（P0：键/值类型/重复属性/改名 400）。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PROBE_KEY = "it_entity_builder_probe"
BASE = "/api/domain-entity-builder"


def _probe_payload(**overrides) -> dict:
    payload = {
        "entity_key": PROBE_KEY,
        "name_cn": "集成测试探针实体",
        "category": "natural_env",
        "value_type": "String",
        "properties": [{"key": "probe_attr", "name_cn": "探针属性", "value_type": "Integer"}],
    }
    payload.update(overrides)
    return payload


async def _delete_probe(test_client, admin_headers) -> None:
    # 清理可能存在的探针（上一次失败运行残留），不存在时 404 可忽略
    await test_client.delete(f"{BASE}/entities/{PROBE_KEY}", headers=admin_headers)


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


# ========== 写入校验（P0） ==========


async def test_create_entity_rejects_key_with_dot(test_client, admin_headers):
    res = await test_client.post(
        f"{BASE}/entities", json=_probe_payload(entity_key="probe.with.dot"), headers=admin_headers
    )
    assert res.status_code == 400, res.text
    assert "点号" in res.json()["detail"]


async def test_create_entity_rejects_unknown_value_type(test_client, admin_headers):
    res = await test_client.post(
        f"{BASE}/entities", json=_probe_payload(value_type="Money"), headers=admin_headers
    )
    assert res.status_code == 400, res.text
    assert "未知值类型" in res.json()["detail"]


async def test_create_entity_rejects_unknown_property_value_type(test_client, admin_headers):
    res = await test_client.post(
        f"{BASE}/entities",
        json=_probe_payload(properties=[{"key": "probe_attr", "name_cn": "探针属性", "value_type": "日期"}]),
        headers=admin_headers,
    )
    assert res.status_code == 400, res.text
    assert "未知值类型" in res.json()["detail"]


async def test_create_entity_rejects_duplicate_property_key(test_client, admin_headers):
    res = await test_client.post(
        f"{BASE}/entities",
        json=_probe_payload(
            properties=[
                {"key": "probe_attr", "name_cn": "探针属性", "value_type": "String"},
                {"key": "PROBE_ATTR", "name_cn": "探针属性二", "value_type": "String"},
            ]
        ),
        headers=admin_headers,
    )
    assert res.status_code == 400, res.text
    assert "重复" in res.json()["detail"]


async def test_create_entity_normalizes_legacy_value_type(test_client, admin_headers):
    await _delete_probe(test_client, admin_headers)
    try:
        res = await test_client.post(
            f"{BASE}/entities", json=_probe_payload(value_type="Numeric"), headers=admin_headers
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["value_type"] == "Float"
    finally:
        await _delete_probe(test_client, admin_headers)


async def test_update_entity_rejects_key_rename(test_client, admin_headers):
    await _delete_probe(test_client, admin_headers)
    created = await test_client.post(f"{BASE}/entities", json=_probe_payload(), headers=admin_headers)
    assert created.status_code == 200, created.text
    try:
        res = await test_client.put(
            f"{BASE}/entities/{PROBE_KEY}",
            json={"entity_key": f"{PROBE_KEY}_renamed"},
            headers=admin_headers,
        )
        assert res.status_code == 400, res.text
        assert "不允许修改" in res.json()["detail"]
    finally:
        await _delete_probe(test_client, admin_headers)
