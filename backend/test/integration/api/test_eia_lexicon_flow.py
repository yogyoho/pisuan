"""eia_lexicon 全链路集成测试：导入幂等 → 确认流 → 拆分 → 导出物化 → 开关闭环。

依赖：PG（test_client fixture）+ 仓库内置 coal-eia-writer 语料（宿主无技能目录时跳过）。
自清理：前后删除 eia_lexicon_entries / eia_dataset_switches 行并移除 overrides 文件，
测试绝不污染运行库与技能目录。
"""

from __future__ import annotations

import json

import pytest

from pisuan.services.eia_data_service import _scan_all, _skill_root_exists
from pisuan.services.eia_lexicon_service import OVERRIDES_PATH

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ENTRIES_PATH = "/api/domain-factory/eia/lexicon/entries"
SWITCHES_PATH = "/api/domain-factory/eia/datasets/switches"
IMPORT_PATH = "/api/domain-factory/eia/lexicon/import"
EXPORT_PATH = "/api/domain-factory/eia/lexicon/export"


@pytest.fixture(autouse=True)
async def _clean_lexicon_state():
    """前后清理：词表行、开关行、物化文件。"""
    from sqlalchemy import delete

    from pisuan.storage.postgres.manager import pg_manager
    from pisuan.storage.postgres.models_domain_factory import EiaDatasetSwitch, EiaLexiconEntry

    async def _wipe():
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EiaLexiconEntry))
            await session.execute(delete(EiaDatasetSwitch))

    await _wipe()
    if OVERRIDES_PATH.is_file():
        OVERRIDES_PATH.unlink()
    yield
    await _wipe()
    if OVERRIDES_PATH.is_file():
        OVERRIDES_PATH.unlink()


async def test_lexicon_requires_auth(test_client):
    """写操作拒绝匿名访问。"""
    assert (await test_client.post(EXPORT_PATH)).status_code == 401
    assert (await test_client.post(IMPORT_PATH)).status_code == 401


async def test_lexicon_full_flow(test_client, admin_headers):
    """导入幂等 → 状态分布 → PATCH 状态机 → 拆分 → 导出物化 → 开关闭环。"""
    if not _skill_root_exists():
        pytest.skip("coal-eia-writer 技能目录不存在")

    # 1) 导入幂等：二次导入零新增（绝不覆盖人工决策）
    r1 = (await test_client.post(IMPORT_PATH, headers=admin_headers)).json()
    assert r1["success"] and r1["added"] == len(_scan_all())
    r2 = (await test_client.post(IMPORT_PATH, headers=admin_headers)).json()
    assert r2["success"] and r2["added"] == 0

    # 2) 列表：状态分布完整，实时计数已合并
    data = (await test_client.get(ENTRIES_PATH, headers=admin_headers)).json()
    assert data["total"] == r1["scanned"]
    assert sum(data["counts"].values()) == data["total"]
    by_status: dict[str, list[dict]] = {}
    for it in data["items"]:
        by_status.setdefault(it["status"], []).append(it)
    assert "approved" in by_status and "candidate" in by_status

    # 3) PATCH 状态机：candidate→approved→candidate 可逆；splitting 不可直设
    cand = by_status["candidate"][0]
    r = await test_client.patch(f"{ENTRIES_PATH}/{cand['id']}", headers=admin_headers, json={"status": "approved"})
    assert r.status_code == 200 and r.json()["entry"]["status"] == "approved"
    r = await test_client.patch(f"{ENTRIES_PATH}/{cand['id']}", headers=admin_headers, json={"status": "candidate"})
    assert r.status_code == 200
    r = await test_client.patch(f"{ENTRIES_PATH}/{cand['id']}", headers=admin_headers, json={"status": "splitting"})
    assert r.status_code == 400

    # 4) 拆分：splitting 不得直接入选；mentions 与扫描同源；拆出 N 条 approved 子口径
    splitters = by_status.get("splitting", [])
    if splitters:
        ent = splitters[0]
        r = await test_client.patch(f"{ENTRIES_PATH}/{ent['id']}", headers=admin_headers, json={"status": "approved"})
        assert r.status_code == 400
        ms = (await test_client.get(f"{ENTRIES_PATH}/{ent['id']}/mentions", headers=admin_headers)).json()["mentions"]
        half = max(1, len(ms) // 2)
        payload = {
            "items": [
                {"caliber": f"{ent['caliber']}(甲)", "values": ms[:half]},
                {"caliber": f"{ent['caliber']}(乙)", "values": ms[half:]},
            ]
        }
        r = await test_client.post(f"{ENTRIES_PATH}/{ent['id']}/split", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        data2 = (await test_client.get(ENTRIES_PATH, headers=admin_headers)).json()
        statuses = {it["id"]: it["status"] for it in data2["items"]}
        assert statuses[ent["id"]] == "rejected"
        children = [it for it in data2["items"] if it["caliber"].startswith(f"{ent['caliber']}(")]
        assert len(children) == 2 and all(c["status"] == "approved" for c in children)

    # 5) 导出物化：材料化数 ≥ range_ready 数；文件结构与开关置位
    r = await test_client.post(EXPORT_PATH, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    expected_ready = sum(1 for e in _scan_all() if e["range_ready"])
    assert body["materialized"] >= expected_ready
    assert OVERRIDES_PATH.is_file()
    doc = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert doc["source"] == "eia_lexicon_entries" and doc["entries"]
    for e in doc["entries"]:
        assert set(e["range"]) == {"p5", "p50", "p95", "n_values", "n_reports"}
    sw = (await test_client.get(SWITCHES_PATH, headers=admin_headers)).json()["items"][0]
    assert sw["enabled"] is True and sw["overrides_file"] is True

    # 6) 开关关闭 → 物化文件删除（管线回 builtin 的前提）
    r = await test_client.put(f"{SWITCHES_PATH}/curated_lexicon", headers=admin_headers, json={"enabled": False})
    assert r.status_code == 200 and not OVERRIDES_PATH.exists()
