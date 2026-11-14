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


# ========== 引用影响面 ==========


async def test_entity_usage_returns_zero_counts_for_new_entity(test_client, admin_headers):
    await _delete_probe(test_client, admin_headers)
    created = await test_client.post(f"{BASE}/entities", json=_probe_payload(), headers=admin_headers)
    assert created.status_code == 200, created.text
    try:
        res = await test_client.get(f"{BASE}/entities/{PROBE_KEY}/usage", headers=admin_headers)
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["entity_key"] == PROBE_KEY
        assert data["totals"] == {
            "templates": 0,
            "pending_tasks": 0,
            "report_pps": 0,
            "facts": 0,
            "dangling_refs": 0,
        }
        assert data["properties"]["probe_attr"] == {
            "templates": 0,
            "pending_tasks": 0,
            "report_pps": 0,
            "facts": 0,
        }
        assert data["unused_properties"] == ["probe_attr"]
    finally:
        await _delete_probe(test_client, admin_headers)


async def test_entity_usage_missing_returns_404(test_client, admin_headers):
    res = await test_client.get(f"{BASE}/entities/no_such_entity_xyz/usage", headers=admin_headers)
    assert res.status_code == 404, res.text


# ========== 导入 / 导出对称性 ==========

IMPORT_KEY = "it_entity_import_probe"


def _import_entity(**overrides) -> dict:
    entity = {
        "entity_id": "env-a-import",
        "entity_key": IMPORT_KEY,
        "name_cn": "导入探针实体",
        "category": "natural_env",
        "domain_code": "general",
        "value_type": "String",
        "properties": [{"key": "probe_attr", "name_cn": "探针属性", "value_type": "String"}],
    }
    entity.update(overrides)
    return entity


async def _delete_import_probe(test_client, admin_headers) -> None:
    await test_client.delete(f"{BASE}/entities/{IMPORT_KEY}", headers=admin_headers)


async def test_import_dry_run_reports_without_writing(test_client, admin_headers):
    await _delete_import_probe(test_client, admin_headers)
    payload = {"entity_schemas": {"env-a-import": _import_entity()}}
    res = await test_client.post(f"{BASE}/import?dry_run=true", json=payload, headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["created"], body["updated"], body["rejected"]) == (1, 0, [])
    missing = await test_client.get(f"{BASE}/entities/{IMPORT_KEY}", headers=admin_headers)
    assert missing.status_code == 404, missing.text


async def test_import_matches_entity_key_across_env(test_client, admin_headers):
    """跨环境导入（entity_id 不同、entity_key 相同）走更新，不撞唯一约束。"""
    await _delete_import_probe(test_client, admin_headers)
    try:
        first = await test_client.post(
            f"{BASE}/import",
            json={"entity_schemas": {"env-a": _import_entity(entity_id="env-a-import")}},
            headers=admin_headers,
        )
        assert first.status_code == 200, first.text
        assert first.json()["created"] == 1

        second = await test_client.post(
            f"{BASE}/import",
            json={
                "entity_schemas": {
                    "env-b": _import_entity(entity_id="env-b-import", name_cn="导入探针实体（改名）")
                }
            },
            headers=admin_headers,
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert (body["created"], body["updated"], body["rejected"]) == (0, 1, [])

        detail = await test_client.get(f"{BASE}/entities/{IMPORT_KEY}", headers=admin_headers)
        data = detail.json()["data"]
        assert data["name_cn"] == "导入探针实体（改名）"
        assert data["entity_id"] == "env-a-import"  # 本地代理键不被文件覆盖
    finally:
        await _delete_import_probe(test_client, admin_headers)


async def test_import_rejects_foreign_domain_code(test_client, admin_headers):
    await _delete_import_probe(test_client, admin_headers)
    res = await test_client.post(
        f"{BASE}/import",
        json={"entity_schemas": {"coal": _import_entity(domain_code="coal")}},
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["created"], body["updated"]) == (0, 0)
    assert "coal" in body["rejected"][0]["reason"]
    missing = await test_client.get(f"{BASE}/entities/{IMPORT_KEY}", headers=admin_headers)
    assert missing.status_code == 404, missing.text


async def test_import_round_trip_of_exported_config(test_client, admin_headers):
    """导出结果原样回导：全部命中已存在实体，不产生新增。"""
    exported = await test_client.get(f"{BASE}/export", headers=admin_headers)
    assert exported.status_code == 200, exported.text
    config = exported.json()["data"]
    assert config["entity_schemas"]

    res = await test_client.post(f"{BASE}/import?dry_run=true", json=config, headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rejected"] == []
    assert body["created"] == 0
    assert body["updated"] == len(config["entity_schemas"])
