"""eia stages/sections/gate1 API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 eia_standard_flow 先例：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；
401 用例无凭据依赖恒跑。仅做非变异断言（404/400/只读形态），不污染运行栈数据。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_eia_p2_routes_require_auth(test_client):
    """未认证访问 P2 新端点一律 401（只读与裁决同门槛）。"""
    for method, url in (
        ("GET", "/api/domain-factory/eia/expectations/sections?stage=planning_eia"),
        ("GET", "/api/domain-factory/eia/expectations/data"),
        ("GET", "/api/domain-factory/eia/standards/gate1"),
        ("GET", "/api/domain-factory/eia/stages/forms?stage=planning_eia"),
        ("PUT", "/api/domain-factory/eia/stages/forms/planning_eia/subsidence/fields"),
        ("DELETE", "/api/domain-factory/eia/stages/forms/planning_eia/subsidence/fields/whatever"),
        ("POST", "/api/domain-factory/eia/stages/forms/export"),
    ):
        resp = await test_client.request(method, url, json={} if method == "PUT" else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


async def test_sections_unknown_stage_400(test_client, admin_headers):
    """stage 不在 STAGES 白名单 → 400（ValueError 映射，同 unmapped 先例）。"""
    resp = await test_client.get(
        "/api/domain-factory/eia/expectations/sections?stage=nope_eia", headers=admin_headers
    )
    assert resp.status_code == 400, resp.text


async def test_sections_shape_natural_order(test_client, admin_headers):
    """节级明细 200：自然序（ch2 先于 ch10）+ unmapped 字段在位。"""
    resp = await test_client.get(
        "/api/domain-factory/eia/expectations/sections?stage=planning_eia", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    keys = [s["key"] for s in body["sections"]]
    assert keys == sorted(keys, key=lambda k: (0, int(k[2:].split("_S")[0]), int(k.split("_S")[1])))
    assert "unmapped" in body and isinstance(body["unmapped"], list)


async def test_data_expectations_shape(test_client, admin_headers):
    """备料清单 200：per_chapter 列表 + source_hint_vocabulary 在位。"""
    resp = await test_client.get("/api/domain-factory/eia/expectations/data", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["per_chapter"], list) and body["per_chapter"]
    assert "source_hint_vocabulary" in body


async def test_gate1_shape_and_selfcheck(test_client, admin_headers):
    """门 1 体检卡 200：规则规格三件套 + 注册表自检结构。"""
    resp = await test_client.get("/api/domain-factory/eia/standards/gate1", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"desc", "allowed_patterns", "rules"} <= set(body)
    check = body["registry_check"]
    assert set(check) == {"total", "violations"}
    assert all(isinstance(c, str) for c in check["violations"])


async def test_stage_forms_unknown_stage_404(test_client, admin_headers):
    """stage 不在 STAGES → 404（KeyError 映射，资源寻址失败）。"""
    resp = await test_client.get("/api/domain-factory/eia/stages/forms?stage=nope_eia", headers=admin_headers)
    assert resp.status_code == 404, resp.text


async def test_save_stage_field_rejects_bad_kind_400(test_client, admin_headers):
    """edit_kind 非法 → 400（ValueError 映射；不落库）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/stages/forms/planning_eia/subsidence/fields",
        headers=admin_headers,
        json={"edit_kind": "replace"},
    )
    assert resp.status_code == 400, resp.text


async def test_save_stage_field_unknown_family_404(test_client, admin_headers):
    """family 不在 forms → 404（KeyError 映射）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/stages/forms/planning_eia/nope_fam/fields",
        headers=admin_headers,
        json={"edit_kind": "add", "name": "x_field", "label": "x", "type": "string"},
    )
    assert resp.status_code == 404, resp.text
