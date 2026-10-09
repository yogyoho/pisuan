"""eia_lexicon 服务层全链路集成测试（不经 HTTP，无凭据依赖）。

覆盖：导入幂等 → 状态分布 → PATCH 状态机 → 拆分 → 导出物化 → 开关闭环。
同覆盖面的 API 层测试（test_eia_lexicon_flow.py）需 TEST_USERNAME/TEST_PASSWORD；
本文件直连服务层，容器内即可验证业务语义。
前后清理 DB 行与 overrides 文件，绝不污染运行库与技能目录。
"""

from __future__ import annotations

import json

import pytest

from yuxi.services.eia_data_service import _scan_all, _skill_root_exists
from yuxi.services.eia_lexicon_service import OVERRIDES_PATH, get_eia_lexicon_service

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _clean_state():
    from sqlalchemy import delete

    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.storage.postgres.models_domain_factory import EiaDatasetSwitch, EiaLexiconEntry

    pg_manager.initialize()  # 幂等；pytest-asyncio 函数级 loop 不容模块级 async fixture

    async def _wipe():
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EiaLexiconEntry))
            await session.execute(delete(EiaDatasetSwitch))

    await _wipe()
    OVERRIDES_PATH.unlink(missing_ok=True)
    yield
    await _wipe()
    OVERRIDES_PATH.unlink(missing_ok=True)


async def test_lexicon_service_full_flow():
    """导入幂等 → 状态分布 → PATCH 状态机 → 拆分 → 导出物化 → 开关闭环。"""
    if not _skill_root_exists():
        pytest.skip("coal-eia-writer 技能目录不存在")
    svc = get_eia_lexicon_service()

    # 1) 导入幂等：二次导入零新增
    r1 = await svc.import_entries()
    assert r1["added"] == len(_scan_all())
    r2 = await svc.import_entries()
    assert r2["added"] == 0

    # 2) 状态分布完整，实时计数已合并
    data = await svc.list_entries()
    assert data["total"] == r1["scanned"]
    assert sum(data["counts"].values()) == data["total"]
    by_status: dict[str, list[dict]] = {}
    for it in data["items"]:
        by_status.setdefault(it["status"], []).append(it)
    assert "approved" in by_status and "candidate" in by_status

    # 3) PATCH 状态机：candidate→approved→candidate 可逆；splitting 不可直设
    cand = by_status["candidate"][0]
    assert (await svc.update_entry(cand["id"], {"status": "approved"}, "tester"))["status"] == "approved"
    assert (await svc.update_entry(cand["id"], {"status": "candidate"}, "tester"))["status"] == "candidate"
    with pytest.raises(ValueError):
        await svc.update_entry(cand["id"], {"status": "splitting"}, "tester")

    # 4) 拆分：splitting 不得直接入选；mentions 与扫描同源；拆出 N 条 approved 子口径
    splitters = by_status.get("splitting", [])
    if splitters:
        ent = splitters[0]
        with pytest.raises(ValueError):
            await svc.update_entry(ent["id"], {"status": "approved"}, "tester")
        ms = (await svc.get_mentions(ent["id"]))["mentions"]
        half = max(1, len(ms) // 2)
        result = await svc.split_entry(
            ent["id"],
            [
                {"caliber": f"{ent['caliber']}(甲)", "values": ms[:half]},
                {"caliber": f"{ent['caliber']}(乙)", "values": ms[half:]},
            ],
            "tester",
        )
        assert result["children"] == 2
        rows = {it["id"]: it for it in (await svc.list_entries())["items"]}
        assert rows[ent["id"]]["status"] == "rejected"
        children = [it for it in rows.values() if it["caliber"].startswith(f"{ent['caliber']}(")]
        assert len(children) == 2 and all(c["status"] == "approved" for c in children)

    # 5) 导出物化：只收 approved；splitting 拆分后的子条目可能掉到 n≥5 门槛之下，
    # 故 materialized ≤ measure 且 range_ready 的条目数（父条目已 rejected 不再占位）
    result = await svc.export_overrides("tester")
    assert result["materialized"] == len(json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))["entries"])
    assert 1 <= result["materialized"] <= sum(1 for e in _scan_all() if e["category"] == "measure" and e["range_ready"])
    doc = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert doc["source"] == "eia_lexicon_entries" and doc["entries"]
    for e in doc["entries"]:
        assert set(e["range"]) == {"p5", "p50", "p95", "n_values", "n_reports"}
    sw = (await svc.get_switches())[0]
    assert sw["enabled"] is True and sw["overrides_file"] is True

    # 6) 开关关闭 → 物化文件删除（管线回 builtin 的前提）
    await svc.set_switch("curated_lexicon", False, "tester")
    assert not OVERRIDES_PATH.exists()
