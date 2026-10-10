"""eia_standard 服务层全链路集成测试（不经 HTTP，无凭据依赖）。

覆盖：总览（62 条文件态 + counts + 语料引用数）→ limit_tables 只读 →
核实校验（未知 code 404 / action 白名单 / 未知字段 400）→ 裁决落库合并 →
导出翻转两标志（round-trip 字节纪律：翻转外逐字节不变）→ 空库导出拒绝。
关键隔离：测试前后恢复 standards_index.json 原字节（导出会重写技能内真实文件），
DB 行前后自清理；绝不污染运行库与技能目录。
"""

from __future__ import annotations

import json

import pytest

from yuxi.services.eia_standard_service import (
    STANDARDS_INDEX_PATH,
    get_eia_standard_service,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _clean_state():
    """DB 行自清理 + 注册表文件字节级快照恢复（pg_manager.initialize 幂等）。"""
    from sqlalchemy import delete

    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.storage.postgres.models_domain_factory import EiaStandardReview

    pg_manager.initialize()
    snapshot = STANDARDS_INDEX_PATH.read_bytes()

    async def _wipe():
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EiaStandardReview))

    await _wipe()
    yield
    await _wipe()
    STANDARDS_INDEX_PATH.write_bytes(snapshot)


async def test_standard_full_flow():
    """总览合并 → limit 只读 → 裁决校验 → 导出翻转与字节纪律。"""
    svc = get_eia_standard_service()
    # 期望值从注册表文件自算（与 needs_verification 断言同构），避免钉死数据指纹——
    # 合法新增标准/限值表/样例行不应使测试误红
    file_doc = json.loads(STANDARDS_INDEX_PATH.read_text(encoding="utf-8"))
    exp_total = len(file_doc["standards"])
    exp_pending = sum(
        1 for t in file_doc["limit_tables"].values() if isinstance(t, dict) and t.get("needs_verification")
    )
    exp_rows = sum(len(t["rows"]) for t in file_doc["limit_tables"].values() if isinstance(t, dict))
    assert exp_total > 0 and exp_pending > 0

    # 1) 总览：全量条目；初始态（DB 空）counts 与文件态一致；引用数与明细自洽
    data = await svc.list_standards()
    assert data["total"] == exp_total == len(data["items"])
    assert data["counts"]["confirmed"] == 0
    assert data["counts"]["needs_verification"] == sum(1 for i in data["items"] if i["needs_verification"])
    assert data["counts"]["limit_tables_pending"] == exp_pending
    codes = [i["code"] for i in data["items"]]
    assert len(codes) == len(set(codes))
    assert all(isinstance(i["cited_count"], int) and i["cited_count"] >= 0 for i in data["items"])
    assert sum(i["cited_count"] for i in data["items"]) > 0  # 语料确有引用

    # 2) limit_tables 只读原样：表骨架（另有 _comment 注释键）；rows 仅样例逐字锚点行，
    #    无批量档位录入（一期不做行级录入）
    limits = await svc.list_limit_tables()
    tables = {k: v for k, v in limits["limit_tables"].items() if isinstance(v, dict)}
    assert len(tables) == sum(1 for v in file_doc["limit_tables"].values() if isinstance(v, dict))
    assert all(isinstance(t.get("rows"), list) for t in tables.values())
    assert sum(len(t["rows"]) for t in tables.values()) == exp_rows

    # 3) 裁决校验：未知 code 404（KeyError）；action 白名单/未知字段/note 类型 400（ValueError）
    nv = next(i for i in data["items"] if i["needs_verification"])
    with pytest.raises(KeyError):
        await svc.set_review("no-such-std", {"action": "confirm"}, "tester")
    with pytest.raises(ValueError, match="action"):
        await svc.set_review(nv["code"], {"action": "reject"}, "tester")
    with pytest.raises(ValueError, match="未知核实字段"):
        await svc.set_review(nv["code"], {"action": "confirm", "tier": "x"}, "tester")
    with pytest.raises(ValueError, match="note"):
        await svc.set_review(nv["code"], {"action": "confirm", "note": 1}, "tester")

    # 4) 合法裁决落库：总览 confirmed +1，review 明细回显
    row = await svc.set_review(nv["code"], {"action": "confirm", "note": "编号/年份/名称已对照原文"}, "tester")
    assert row["action"] == "confirm" and row["decided_by"] == "tester"
    data2 = await svc.list_standards()
    assert data2["counts"]["confirmed"] == 1
    it2 = next(i for i in data2["items"] if i["code"] == nv["code"])
    assert it2["review"]["note"] == "编号/年份/名称已对照原文"
    assert it2["needs_verification"] is True  # 文件态未变，导出前 nv 仍 true

    # 5) 导出翻转：仅被裁决条目两标志翻转，其余内容 round-trip 逐字节不变
    before = STANDARDS_INDEX_PATH.read_text(encoding="utf-8")
    result = await svc.export_reviews("tester")
    assert result["materialized"] == 1
    assert result["path"] == "references/standards_index.json"
    after = STANDARDS_INDEX_PATH.read_text(encoding="utf-8")
    snap = json.loads(before)
    for s in snap["standards"]:
        if s["code"] == nv["code"]:
            s["needs_verification"] = False
            s["verified"] = True
    assert after == json.dumps(snap, ensure_ascii=False, indent=2)  # 无尾换行、保原键序

    # 6) 导出后总览：该条 nv 翻转为 false，其余条目不受影响
    data3 = await svc.list_standards()
    it3 = next(i for i in data3["items"] if i["code"] == nv["code"])
    assert it3["needs_verification"] is False and it3["verified"] is True
    assert data3["counts"]["needs_verification"] == data["counts"]["needs_verification"] - 1
    # 未裁决的其余条目文件态逐字段不变
    by3 = {i["code"]: i for i in data3["items"]}
    for i in data["items"]:
        if i["code"] == nv["code"]:
            continue
        j = by3[i["code"]]
        assert (j["needs_verification"], j["verified"]) == (i["needs_verification"], i["verified"])


async def test_standard_export_empty_rejected():
    """空库导出拒绝（ValueError），不产生半成品文件改写。"""
    svc = get_eia_standard_service()
    before = STANDARDS_INDEX_PATH.read_bytes()
    with pytest.raises(ValueError, match="无核实裁决可导出"):
        await svc.export_reviews("tester")
    assert STANDARDS_INDEX_PATH.read_bytes() == before
