"""eia_lexicon 全链路集成测试：导入幂等 → 确认流 → 拆分 → 导出物化 → 开关闭环。

依赖：PG（test_client fixture）+ 仓库内置 coal-eia-writer 语料（宿主无技能目录时跳过）。
关键隔离（bug-4217）：运行库为共享生产库，此前「前后裸 delete 全表 + 删物化文件」曾把
运营词表整体抹掉——autouse fixture 在用例 skip 时同样执行，裸 wipe 不可接受。现改为
行级/字节级快照恢复：测试前整表快照 + 文件字节快照，清理后原样回灌；导出侧的 refs-repo
git 链与重编译排队同样不打真实共享态（用例内 monkeypatch，见 test_lexicon_full_flow）。
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
    """快照 → 清理 → 测试 → 回灌（bug-4217：运行库为共享库，禁止裸 wipe）。"""
    from sqlalchemy import delete

    from pisuan.storage.postgres.manager import pg_manager
    from pisuan.storage.postgres.models_domain_factory import EiaDatasetSwitch, EiaLexiconEntry

    from test.integration.services._flow_isolation import restore_rows, snapshot_rows

    pg_manager.initialize()  # 幂等；pytest-asyncio 函数级 loop 不容模块级 async fixture

    saved_entries = await snapshot_rows(EiaLexiconEntry)
    saved_switches = await snapshot_rows(EiaDatasetSwitch)
    overrides_snapshot = OVERRIDES_PATH.read_bytes() if OVERRIDES_PATH.is_file() else None

    async def _wipe():
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EiaLexiconEntry))
            await session.execute(delete(EiaDatasetSwitch))

    await _wipe()
    OVERRIDES_PATH.unlink(missing_ok=True)
    yield
    await _wipe()
    if overrides_snapshot is None:
        OVERRIDES_PATH.unlink(missing_ok=True)
    else:
        OVERRIDES_PATH.write_bytes(overrides_snapshot)
    await restore_rows(EiaLexiconEntry, saved_entries)
    await restore_rows(EiaDatasetSwitch, saved_switches)


async def test_lexicon_requires_auth(test_client):
    """写操作拒绝匿名访问。"""
    assert (await test_client.post(EXPORT_PATH)).status_code == 401
    assert (await test_client.post(IMPORT_PATH)).status_code == 401


async def test_lexicon_full_flow(test_client, admin_headers, monkeypatch):
    """导入幂等 → 状态分布 → PATCH 状态机 → 拆分 → 导出物化 → 开关闭环。"""
    if not _skill_root_exists():
        pytest.skip("coal-eia-writer 技能目录不存在")

    # 共享态隔离：导出不抄送 refs-repo git、重编译排队不打真实任务（同服务层测试口径）
    monkeypatch.delenv("REFS_REPO_WORKTREE", raising=False)
    from types import SimpleNamespace

    from pisuan.services.task_service import tasker

    monkeypatch.setattr(
        tasker,
        "enqueue_unique_by_payload",
        lambda *a, **k: (SimpleNamespace(id="test-suppressed"), True),
    )

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
