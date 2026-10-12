"""eia formulas/entities/datasets API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 eia_stage_flow 先例：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；
401 用例无凭据依赖恒跑。仅做非变异断言（400/404/只读形态），不落库不导出，
不污染运行栈数据。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_eia_p3_routes_require_auth(test_client):
    """未认证访问 P3 新端点一律 401（只读、裁决与导出同门槛）。"""
    for method, url in (
        ("GET", "/api/domain-factory/eia/formulas"),
        ("PUT", "/api/domain-factory/eia/formulas/f_x/inputs/q"),
        ("DELETE", "/api/domain-factory/eia/formulas/f_x/inputs/q"),
        ("POST", "/api/domain-factory/eia/formulas/export"),
        ("GET", "/api/domain-factory/eia/entities/samples"),
        ("GET", "/api/domain-factory/eia/entities/some_slug"),
        ("PUT", "/api/domain-factory/eia/entities/some_slug/items"),
        ("DELETE", "/api/domain-factory/eia/entities/items/1"),
        ("POST", "/api/domain-factory/eia/entities/export"),
        ("GET", "/api/domain-factory/eia/datasets/attachment_checklist/view"),
    ):
        resp = await test_client.request(method, url, json={} if method == "PUT" else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


async def test_formulas_shape_readonly_structure(test_client, admin_headers):
    """公式合并态 200：formulas/derived_slots 在位；inputs 带 override 键（无覆盖为 null）。"""
    resp = await test_client.get("/api/domain-factory/eia/formulas", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["formulas"], list) and body["formulas"]
    assert "derived_slots" in body and "pending_count" in body
    f0 = body["formulas"][0]
    assert {"id", "expr", "inputs"} <= set(f0)
    assert all("override" in inp for inp in f0["inputs"])


async def test_set_formula_value_unknown_target_404(test_client, admin_headers):
    """未知公式/参数 → 404（KeyError 映射；不落库）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/formulas/nope_formula/inputs/nope_input",
        headers=admin_headers,
        json={"value": "1"},
    )
    assert resp.status_code == 404, resp.text


async def test_set_formula_value_blank_400(test_client, admin_headers):
    """空参考值 → 400（ValueError 映射；不落库）。"""
    listing = await test_client.get("/api/domain-factory/eia/formulas", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    f0 = listing.json()["formulas"][0]
    resp = await test_client.put(
        f"/api/domain-factory/eia/formulas/{f0['id']}/inputs/{f0['inputs'][0]['name']}",
        headers=admin_headers,
        json={"value": "   "},
    )
    assert resp.status_code == 400, resp.text


async def test_entity_samples_and_registry_shape(test_client, admin_headers):
    """样例清单与单样例注册表 200：counts/etype 分组在位。"""
    resp = await test_client.get("/api/domain-factory/eia/entities/samples", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    samples = resp.json()["samples"]
    assert samples

    slug = samples[0]["slug"]
    resp = await test_client.get(f"/api/domain-factory/eia/entities/{slug}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["entities"]) == {"projects", "mines", "orgs", "places", "sensitive"}
    assert "pending_count" in body


async def test_entity_registry_unknown_slug_404(test_client, admin_headers):
    """未知样例 → 404（KeyError 映射）。"""
    resp = await test_client.get("/api/domain-factory/eia/entities/nope_slug", headers=admin_headers)
    assert resp.status_code == 404, resp.text


async def test_add_entity_rejects_bad_etype_400(test_client, admin_headers):
    """etype 非白名单 → 400（ValueError 映射；不落库）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/entities/some_slug/items",
        headers=admin_headers,
        json={"etype": "rivers", "name": "x"},
    )
    assert resp.status_code == 400, resp.text


async def test_withdraw_entity_missing_id_returns_false(test_client, admin_headers):
    """撤回不存在行 → 200 success=false（非变异）。"""
    resp = await test_client.delete("/api/domain-factory/eia/entities/items/99999999", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": False}


async def test_dataset_view_three_keys_and_unknown_404(test_client, admin_headers):
    """三数据集只读通道 200 + 未知 key 404。"""
    for key, probe in (
        ("attachment_checklist", "stages"),
        ("consistency_contracts", "contracts"),
        ("depth_targets", "stages"),
    ):
        resp = await test_client.get(f"/api/domain-factory/eia/datasets/{key}/view", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["key"] == key and body[probe]

    resp = await test_client.get("/api/domain-factory/eia/datasets/paradigms/view", headers=admin_headers)
    assert resp.status_code == 404, resp.text
