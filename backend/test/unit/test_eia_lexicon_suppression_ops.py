"""eia_lexicon_service 抑制名单运营单元测试：列表 / 手工添加校验 / 撤回 / 扫描差集。

DB 流转零依赖：FakeRepo 代表抑制表访问面，monkeypatch svc._scan_all 代表语料扫描；
绝不触真实 PG（集成流测试会清 eia_lexicon_entries 表，禁在运行栈跑）。
"""

import asyncio
from types import SimpleNamespace

import pytest

import yuxi.services.eia_lexicon_service as svc

# 语料扫描替身：3 候选，其一已是词条
SCAN_CANDS = [
    {"stage": "planning_eia", "caliber": "水平达标率", "unit": "%", "category": "measure"},
    {"stage": "planning_eia", "caliber": "节水率", "unit": "%", "category": "measure"},
    {"stage": "planning_eia", "caliber": "已入库口径", "unit": "%", "category": "site"},
]


class _SuppressionRow(SimpleNamespace):
    """镜像真实行形状：EiaLexiconSuppression 含 to_dict（models_domain_factory.py:475）。"""

    def to_dict(self):
        return {
            "id": self.id,
            "stage": self.stage,
            "caliber": self.caliber,
            "unit": self.unit,
            "new_caliber": self.new_caliber,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


def _row(sid=1, new_caliber="三率水平达标率", reason="改名抑制：水平达标率 → 三率水平达标率"):
    return _SuppressionRow(
        id=sid,
        stage="planning_eia",
        caliber="水平达标率",
        unit="%",
        new_caliber=new_caliber,
        reason=reason,
        created_by="alice",
        created_at=None,
    )


class FakeRepo:
    """抑制表访问面替身：内存行集 + existing 指纹集 + add 调用记录。"""

    def __init__(self, rows=None, existing=()):
        self.rows = list(rows or [])
        self.existing = set(existing)
        self.added = []

    async def list_suppressions(self):
        return list(self.rows)

    async def get_suppression(self, sid):
        return next((r for r in self.rows if r.id == sid), None)

    async def delete_suppression(self, sid):
        self.rows = [r for r in self.rows if r.id != sid]

    async def add_suppression(self, stage, caliber, unit, new_caliber, reason, created_by):
        self.added.append((stage, caliber, unit, new_caliber, reason, created_by))

    async def existing_keys(self):
        return set(self.existing)

    async def suppressed_keys(self):
        return {(r.stage, r.caliber, r.unit) for r in self.rows}


def _svc(repo):
    s = svc.EiaLexiconService()
    s.repo = repo
    return s


@pytest.fixture(autouse=True)
def fake_scan(monkeypatch):
    monkeypatch.setattr(svc, "_scan_all", lambda: [dict(c) for c in SCAN_CANDS])


def test_list_suppressions_maps_rows():
    out = asyncio.run(_svc(FakeRepo([_row(1), _row(2)])).list_suppressions())
    assert out["total"] == 2
    assert [it["id"] for it in out["items"]] == [1, 2]
    assert out["items"][0]["caliber"] == "水平达标率"


def test_add_suppression_missing_fields_rejected():
    with pytest.raises(ValueError, match="必填"):
        asyncio.run(_svc(FakeRepo()).add_suppression({"stage": "", "caliber": "x"}, "bob"))


def test_add_suppression_validates_against_scan_diff():
    repo = FakeRepo(existing={("planning_eia", "已入库口径", "%")})
    s = _svc(repo)
    # 已是词条 → 拒绝（词条上直接操作即可，无需抑制）
    with pytest.raises(ValueError, match="已是词表条目"):
        asyncio.run(s.add_suppression({"stage": "planning_eia", "caliber": "已入库口径", "unit": "%"}, "bob"))
    # 不在语料扫描结果 → 拒绝（抑制永不生效，静默无操作必须报错）
    with pytest.raises(ValueError, match="不在语料扫描结果"):
        asyncio.run(s.add_suppression({"stage": "planning_eia", "caliber": "语料没有的词", "unit": "%"}, "bob"))
    # 合法候选 → 落库且 new_caliber=''（手工行无语境回落）
    asyncio.run(
        s.add_suppression({"stage": "planning_eia", "caliber": "节水率", "unit": "%", "reason": "扫描噪声"}, "bob")
    )
    assert repo.added == [("planning_eia", "节水率", "%", "", "扫描噪声", "bob")]


def test_add_suppression_idempotent_refresh_on_suppressed():
    """已抑制指纹重复登记 → 幂等刷新（repo upsert），不报错。"""
    repo = FakeRepo(rows=[_row(1)])
    asyncio.run(
        _svc(repo).add_suppression(
            {"stage": "planning_eia", "caliber": "水平达标率", "unit": "%", "reason": "复评"}, "carol"
        )
    )
    assert repo.added == [("planning_eia", "水平达标率", "%", "", "复评", "carol")]


def test_withdraw_suppression_deletes_row_or_raises():
    repo = FakeRepo([_row(7)])
    out = asyncio.run(_svc(repo).withdraw_suppression(7, "bob"))
    assert out["id"] == 7
    assert repo.rows == []
    with pytest.raises(KeyError):
        asyncio.run(_svc(repo).withdraw_suppression(7, "bob"))


def test_scan_candidates_diff():
    repo = FakeRepo(rows=[_row(1)], existing={("planning_eia", "已入库口径", "%")})
    out = asyncio.run(_svc(repo).scan_candidates())
    # 水平达标率已抑制、已入库口径已入库 → 只剩 节水率
    assert out["total"] == 1
    assert out["items"][0]["caliber"] == "节水率"
