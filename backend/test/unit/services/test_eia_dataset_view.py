"""eia_data_service.get_dataset_view 单测（P3-3：三数据集只读抽屉数据通道）。"""

from __future__ import annotations

import json

import pytest

from yuxi.services import eia_data_service as svc_mod


@pytest.fixture
def refs(tmp_path, monkeypatch):
    refs = tmp_path / "references"
    bank = tmp_path / "samples_bank"
    refs.mkdir()
    bank.mkdir()

    (bank / "attachment_checklist.json").write_text(
        json.dumps(
            {
                "provenance_note": "基准来自 16 份样例",
                "stages": {
                    "planning_eia": {
                        "base_reports": 16,
                        "common": [{"item": "公众参与调查表", "freq": 0.5, "n_reports": 8}],
                        "required": [],
                        "rids_without_items": ["028-r"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (refs / "consistency_contracts.json").write_text(
        json.dumps(
            {
                "version": "1.1",
                "generated": "2026-09-09",
                "source": "设计文档",
                "contract_types": {"cross_section": "跨章 exact_match"},
                "caliber_labels": {},
                "activation_semantics": "合约激活语义",
                "geo_inherited_note": "",
                "contracts": [
                    {
                        "id": "XS1",
                        "type": "cross_section",
                        "name": "planning_indicators_capacity",
                        "description": "规划指标跨章",
                        "stages": ["planning_eia"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dt = refs / "depth_targets"
    dt.mkdir()
    for stage in svc_mod.STAGES:
        (dt / f"{stage}.json").write_text(
            json.dumps(
                {
                    "stage": stage,
                    "source": "digest 实测",
                    "confidence": "high",
                    "chapters": {"ch1": {"floor_chars": 7052}, "ch2": {"floor_chars": 14599}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(svc_mod, "_REFS", refs)
    monkeypatch.setattr(svc_mod, "_BANK", bank)
    return refs


def test_dataset_view_attachment_checklist(refs):
    out = svc_mod.get_dataset_view("attachment_checklist")
    assert out["key"] == "attachment_checklist"
    assert out["provenance_note"] == "基准来自 16 份样例"
    assert out["stages"]["planning_eia"]["base_reports"] == 16


def test_dataset_view_consistency_contracts(refs):
    out = svc_mod.get_dataset_view("consistency_contracts")
    assert out["key"] == "consistency_contracts"
    assert out["contract_types"]["cross_section"] == "跨章 exact_match"
    assert out["contracts"][0]["id"] == "XS1"


def test_dataset_view_depth_targets_aggregates_stages(refs):
    out = svc_mod.get_dataset_view("depth_targets")
    assert out["key"] == "depth_targets"
    st = out["stages"]["planning_eia"]
    assert st["confidence"] == "high"
    assert st["chapters"]["ch2"] == {"floor_chars": 14599}
    assert set(out["stages"]) == set(svc_mod.STAGES)


def test_dataset_view_unknown_key_raises_keyerror(refs):
    with pytest.raises(KeyError):
        svc_mod.get_dataset_view("paradigms")
