"""eia_data_service P2 只读视图测试：节级明细（get_sections）+ 备料清单（get_data_expectations）。

P2-2/P2-4 均为文件只读通道（无 DB 裁决）：引用文件是管线契约产物，服务只做
形整形与排序透出，禁止再加工。节键排序按 DNR 6.10 教训用 int 元组自然序
（ch2 先于 ch10，字符串序会倒挂）。
"""

import json

import pytest

from pisuan.services import eia_data_service as svc_mod


def _write_sections_fixture(root):
    doc = {
        "version": "test",
        "stage_scope": "planning_eia",
        "sections": {
            "ch10_S01": {
                "title": "十章首节",
                "expected_quantities": [
                    {
                        "caliber": "塌陷面积",
                        "field": "mine.subsidence_area",
                        "tier": "contextual",
                        "unit": "km2",
                        "corpus_freq": 0.1,
                    }
                ],
            },
            "ch2_S10": {"title": "二章十节", "expected_quantities": []},
            "ch2_S01": {"title": "", "expected_quantities": []},
        },
        "unmapped": [
            {"caliber": "发边界重叠面积约", "sample": "002-016", "section": "ch1", "unit": "km2", "value": "33.71"}
        ],
    }
    d = root / "section_expectations"
    d.mkdir(parents=True)
    (d / "planning_eia.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def _write_expectations_fixture(root):
    doc = {
        "_comment": "备料清单",
        "stage_scope": "all",
        "source_hint_vocabulary": ["standards_index + user_planning", "user_docs"],
        "per_chapter": [
            {
                "chapter": "ch1",
                "title": "总则",
                "data_families": [
                    {
                        "family": "standards_confirm",
                        "items": ["执行标准三元组"],
                        "source_hint": "standards_index + user_planning",
                    }
                ],
            }
        ],
    }
    (root / "data_expectations.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


@pytest.fixture()
def refs_root(monkeypatch, tmp_path):
    monkeypatch.setattr(svc_mod, "_REFS", tmp_path)
    return tmp_path


def test_get_sections_sorts_keys_by_int_tuple_naturally(refs_root):
    _write_sections_fixture(refs_root)
    out = svc_mod.get_sections("planning_eia")

    assert [s["key"] for s in out["sections"]] == ["ch2_S01", "ch2_S10", "ch10_S01"]  # 字符串序会得到 ch10 在前
    assert out["stage_scope"] == "planning_eia"
    assert out["unmapped"][0]["value"] == "33.71"  # unmapped 原样透出


def test_get_sections_carries_title_and_quantities(refs_root):
    _write_sections_fixture(refs_root)
    out = svc_mod.get_sections("planning_eia")

    s10 = next(s for s in out["sections"] if s["key"] == "ch10_S01")
    assert s10["title"] == "十章首节"
    assert s10["quantities"][0]["field"] == "mine.subsidence_area"
    empty = next(s for s in out["sections"] if s["key"] == "ch2_S10")
    assert empty["quantities"] == []


def test_get_sections_rejects_unknown_stage(refs_root):
    _write_sections_fixture(refs_root)
    with pytest.raises(ValueError):  # 同 get_unmapped 先例：参数校验失败走 ValueError（路由翻 400）
        svc_mod.get_sections("nope_eia")


def test_get_data_expectations_passthrough(refs_root):
    doc = _write_expectations_fixture(refs_root)
    out = svc_mod.get_data_expectations()

    assert out["per_chapter"] == doc["per_chapter"]
    assert out["source_hint_vocabulary"] == doc["source_hint_vocabulary"]
    assert out["stage_scope"] == "all"
