"""eia_standard_extract API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 paradigm flow：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；401 用例无凭据依赖恒跑。
写路径用例只用「未知行 404 / 键形状 400」等在落库前即失败的载荷，不触真实暂存数据。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_extract_endpoints_require_auth(test_client):
    """未认证访问限值提取端点一律 401（试跑/清单/裁决/候选/立表/引用同门槛）。"""
    for method, url in (
        ("POST", "/api/domain-factory/eia/standards/extract"),
        ("GET", "/api/domain-factory/eia/standards/extract/rows"),
        ("PUT", "/api/domain-factory/eia/standards/extract/rows/1"),
        ("GET", "/api/domain-factory/eia/standards/extract/candidates"),
        ("POST", "/api/domain-factory/eia/standards/extract/candidates/register"),
        ("GET", "/api/domain-factory/eia/standards/citations?code=GB3838-2002"),
    ):
        resp = await test_client.request(method, url, json={} if method != "GET" else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


async def test_extract_admin_endpoints_forbid_standard_user(test_client, standard_user):
    """非 admin 试跑/立表 403（extract 与 register 仅 admin 裁决；凭据缺失自动 skip）。"""
    for method, url in (
        ("POST", "/api/domain-factory/eia/standards/extract"),
        ("POST", "/api/domain-factory/eia/standards/extract/candidates/register"),
    ):
        resp = await test_client.request(
            method,
            url,
            headers=standard_user["headers"],
            json={"code": "GB3838-2002", "table_key": "coda_test", "columns_schema": {}},
        )
        assert resp.status_code == 403, f"{method} {url} -> {resp.status_code}: {resp.text}"


async def test_extract_decide_unknown_row_404(test_client, admin_headers):
    """未知暂存行 404（KeyError 映射先于任何转正触碰，用例只读不落真实数据）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/standards/extract/rows/999999999",
        headers=admin_headers,
        json={"action": "confirm"},
    )
    assert resp.status_code == 404, resp.text


async def test_extract_register_bad_table_key_400(test_client, admin_headers):
    """table_key 形状越界 400（正则校验先于注册表落库，载荷不触真实数据）。"""
    resp = await test_client.post(
        "/api/domain-factory/eia/standards/extract/candidates/register",
        headers=admin_headers,
        json={"code": "GB3838-2002", "table_key": "Bad-Key!", "desc": "", "columns_schema": {}},
    )
    assert resp.status_code == 400, resp.text
