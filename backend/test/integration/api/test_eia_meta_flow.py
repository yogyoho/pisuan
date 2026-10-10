"""eia_meta API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 P1：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；401 用例无凭据依赖恒跑。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_meta_requires_auth(test_client):
    """未认证访问元数据端点一律 401（读写与物化同门槛）。"""
    for method, url in (
        ("GET", "/api/domain-factory/eia/meta/reports"),
        ("PUT", "/api/domain-factory/eia/meta/reports/001-wps/annotation"),
        ("POST", "/api/domain-factory/eia/meta/import"),
        ("POST", "/api/domain-factory/eia/meta/export"),
    ):
        resp = await test_client.request(method, url, json={} if method != "GET" else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"
