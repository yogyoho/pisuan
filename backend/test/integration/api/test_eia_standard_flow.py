"""eia_standard API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 P2：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；401 用例无凭据依赖恒跑。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_standards_requires_auth(test_client):
    """未认证访问标准端点一律 401（读写与物化同门槛）。"""
    for method, url in (
        ("GET", "/api/domain-factory/eia/standards"),
        ("GET", "/api/domain-factory/eia/standards/limits"),
        ("PUT", "/api/domain-factory/eia/standards/review"),
        ("POST", "/api/domain-factory/eia/standards/export"),
    ):
        resp = await test_client.request(method, url, json={} if method != "GET" else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


async def test_standards_export_requires_admin(test_client, standard_user):
    """非 admin 导出物化 403（export 仅 admin 裁决；凭据缺失自动 skip）。"""
    resp = await test_client.post("/api/domain-factory/eia/standards/export", headers=standard_user["headers"])
    assert resp.status_code == 403, resp.text


async def test_standards_review_unknown_code_404(test_client, admin_headers):
    """code 不在注册表 → 404（KeyError 映射；含 `/` 的编号走 body，路径参数跨不过 %2F 解码）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/standards/review",
        headers=admin_headers,
        json={"code": "no-such-std", "action": "confirm"},
    )
    assert resp.status_code == 404, resp.text
