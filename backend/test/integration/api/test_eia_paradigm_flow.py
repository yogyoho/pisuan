"""eia_paradigm API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 standard flow：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；401 用例无凭据依赖恒跑。
不触真实技能文件：写路径全部用「未知资产 404 / 键形状 400」等在落盘前即失败的用例。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_paradigms_requires_auth(test_client):
    """未认证访问范式端点一律 401（概览/详情/存撤草稿/预览/导出同门槛）。"""
    for method, url in (
        ("GET", "/api/domain-factory/eia/paradigms"),
        ("GET", "/api/domain-factory/eia/paradigms/paradigm_md/analysis"),
        ("PUT", "/api/domain-factory/eia/paradigms/paradigm_md/analysis/draft"),
        ("DELETE", "/api/domain-factory/eia/paradigms/forms_catalog/table_lead/draft"),
        ("POST", "/api/domain-factory/eia/paradigms/export/preview"),
        ("POST", "/api/domain-factory/eia/paradigms/export"),
    ):
        resp = await test_client.request(method, url, json={} if method != "GET" else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


async def test_paradigms_export_requires_admin(test_client, standard_user):
    """非 admin 导出物化 403（export 仅 admin 裁决；凭据缺失自动 skip）。"""
    resp = await test_client.post("/api/domain-factory/eia/paradigms/export", headers=standard_user["headers"])
    assert resp.status_code == 403, resp.text


async def test_paradigm_draft_unknown_asset_404(test_client, admin_headers):
    """kind/asset 不在注册表 → 404（KeyError 映射先于任何文件/DB 触碰，用例不落真实数据）。"""
    for kind, asset_id in (
        ("no_such_kind", "analysis"),
        ("paradigm_md", "no_such"),
        ("forms_catalog", "no_such"),
    ):
        resp = await test_client.put(
            f"/api/domain-factory/eia/paradigms/{kind}/{asset_id}/draft",
            headers=admin_headers,
            json={"md": "# x"},
        )
        assert resp.status_code == 404, f"{kind}/{asset_id} -> {resp.status_code}: {resp.text}"


async def test_paradigm_draft_extra_keys_rejected_400(test_client, admin_headers):
    """forms 草稿仅收 desc/templates 两键（stats/examples 只读）→ 400，两键纪律先于落库。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/paradigms/forms_catalog/table_lead/draft",
        headers=admin_headers,
        json={"desc": "d", "templates": ["t。"], "stats": {"colon_lead": 0.0}},
    )
    assert resp.status_code == 400, resp.text
    assert "stats" in resp.text


async def test_paradigm_export_empty_400(test_client, admin_headers):
    """导出/预览空态 → 400（ValueError「无待导出的范式草稿」）。

    共享开发库可能已有他人草稿，此时 200 亦合法（admin 导出本就是合法操作）；
    不变量为「非 5xx、不因空态崩溃」。
    """
    preview = await test_client.post("/api/domain-factory/eia/paradigms/export/preview", headers=admin_headers)
    assert preview.status_code in (400, 200), preview.text
    export = await test_client.post("/api/domain-factory/eia/paradigms/export", headers=admin_headers)
    assert export.status_code in (400, 200), export.text
