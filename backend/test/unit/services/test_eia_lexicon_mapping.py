"""词表 × 章节口径期望联动（P2）：可映射性标注与导出跳过均与编译器同判。

映射链：eia_lexicon_entries.caliber --_map_caliber(build_label_map(refs))--> forms fam.name。
未映射条目 list_entries 标 forms_field=None、export_overrides 直接跳过——否则条目入了覆盖层
也会在编译时被静默丢弃，页面却显示正常。用真实 refs + 真 bank_compile 保证「页面所见 = 编译器所查」。
"""

import json
from typing import Any

import pytest

from yuxi.services import eia_lexicon_service as svc


class FakeEntry:
    """最小条目桩：list_entries / export_overrides 只消费这些属性。"""

    def __init__(self, id_: int, stage: str, caliber: str, unit: str, values_json: list | None = None):
        self.id = id_
        self.stage = stage
        self.caliber = caliber
        self.unit = unit
        self.category = "measure"
        self.status = "approved"
        self.values_json = values_json
        self.note = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "stage": self.stage,
            "caliber": self.caliber,
            "unit": self.unit,
            "category": self.category,
            "status": self.status,
            "values": self.values_json,
            "note": self.note,
        }


class FakeRepo:
    def __init__(self, entries: list[FakeEntry]):
        self.entries = entries
        self.saved: list[tuple] = []

    async def list_entries(self):
        return list(self.entries)

    async def save_switch(self, key, enabled, username):
        self.saved.append((key, enabled, username))


@pytest.fixture()
def label_map():
    """真实 refs 构建的范式字段词汇表（与编译器同一函数、同一数据）。"""
    return svc._load_bank_compile().build_label_map(svc._SKILL_REFS)


@pytest.fixture()
def no_scan(monkeypatch):
    monkeypatch.setattr(svc, "_scan_all", lambda: [])


def test_build_label_map_shape(label_map):
    """词汇表形状：{label: fam.name}，非空（真实 refs 有 forms 字段）。"""
    assert label_map
    for label, fam_field in label_map.items():
        assert isinstance(label, str) and len(label) >= 2
        assert "." in fam_field


@pytest.mark.usefixtures("no_scan")
async def test_list_entries_attaches_forms_field(monkeypatch, label_map):
    """已映射条目挂 forms_field（与编译器同判），未映射条目为 None。"""
    known = next(iter(label_map))
    junk = "永不命中范式字段的虚构口径甲乙丙"
    assert svc._load_bank_compile()._map_caliber(junk, label_map) is None
    repo = FakeRepo([FakeEntry(1, "post_eia", known, "mg/L"), FakeEntry(2, "post_eia", junk, "m")])
    monkeypatch.setattr(svc, "EiaLexiconRepository", lambda: repo)
    svc._service = None

    res = await svc.get_eia_lexicon_service().list_entries()
    by_id = {d["id"]: d for d in res["items"]}
    assert by_id[1]["forms_field"] == label_map[known]
    assert by_id[2]["forms_field"] is None


@pytest.mark.usefixtures("no_scan")
async def test_export_overrides_skips_unmapped(monkeypatch, label_map, tmp_path):
    """未映射范式字段的 approved 条目导出即跳过；已映射的按 values_json 页面裁决值集物化。"""
    known = next(iter(label_map))
    junk = "永不命中范式字段的虚构口径甲乙丙"
    values = [{"value": v, "rid": f"rid-{i}"} for i, v in enumerate([1.0, 2.0, 3.0, 4.0, 5.0])]
    repo = FakeRepo(
        [
            FakeEntry(1, "post_eia", known, "mg/L", values_json=values),
            FakeEntry(2, "post_eia", junk, "m"),
        ]
    )
    monkeypatch.setattr(svc, "EiaLexiconRepository", lambda: repo)
    svc._service = None
    overrides = tmp_path / "curated_lexicon.json"
    monkeypatch.setattr(svc, "OVERRIDES_PATH", overrides)
    monkeypatch.setattr(svc, "collect_stage_values", lambda: ({}, {}))

    res = await svc.get_eia_lexicon_service().export_overrides("tester")

    assert res["materialized"] == 1
    assert [s["caliber"] for s in res["skipped"]] == [junk]
    assert all("未映射范式表单字段" in s["reason"] for s in res["skipped"])
    doc = json.loads(overrides.read_text(encoding="utf-8"))
    assert [e["caliber"] for e in doc["entries"]] == [known]
    assert list(repo.saved) == [("curated_lexicon", True, "tester")]
