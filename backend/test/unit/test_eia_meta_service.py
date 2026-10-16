"""eia_meta_service 单测：标注载荷校验（year_hint/scale_mt_a/report_title/eia_org 取值域）+ list_reports 合并透出。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from yuxi.services import eia_meta_service
from yuxi.services.eia_meta_service import EiaMetaService, _validate_annotations


def test_validate_annotations_accepts_valid_payload():
    assert _validate_annotations({"year_hint": 2024, "scale_mt_a": 9.0}) == {"year_hint": 2024, "scale_mt_a": 9.0}
    assert _validate_annotations({}) == {}
    assert _validate_annotations({"year_hint": 2000}) == {"year_hint": 2000}


def test_validate_annotations_year_bounds():
    for bad in (1999, 2101, "2024", 2024.5, True, None):
        with pytest.raises(ValueError, match="year_hint"):
            _validate_annotations({"year_hint": bad})


def test_validate_annotations_scale_bounds():
    for bad in (0, -3, 10001, "9.0", True, None):
        with pytest.raises(ValueError, match="scale_mt_a"):
            _validate_annotations({"scale_mt_a": bad})
    assert _validate_annotations({"scale_mt_a": 10000}) == {"scale_mt_a": 10000.0}


def test_validate_annotations_rejects_unknown_fields_and_non_dict():
    with pytest.raises(ValueError, match="未知标注字段"):
        _validate_annotations({"coal_type": "动力煤"})
    with pytest.raises(ValueError):
        _validate_annotations([("year_hint", 2024)])


def test_validate_annotations_accepts_text_fields():
    out = _validate_annotations(
        {
            "report_title": "  甘肃省灵台矿区总体规划（修编）环境影响报告书 ",
            "eia_org": "中煤科工集团北京华宇工程有限公司",
        }
    )
    assert out == {
        "report_title": "甘肃省灵台矿区总体规划（修编）环境影响报告书",
        "eia_org": "中煤科工集团北京华宇工程有限公司",
    }
    # 边界：恰好 200 字须放行（off-by-one 护栏）
    assert _validate_annotations({"report_title": "x" * 200}) == {"report_title": "x" * 200}


def test_validate_annotations_rejects_bad_text_fields():
    for key in ("report_title", "eia_org"):
        for bad in ("", "   ", "x" * 201, 123, None, True):
            with pytest.raises(ValueError, match=key):
                _validate_annotations({key: bad})


def test_list_reports_merges_text_fields(monkeypatch):
    """schema 2 cover 层新字段透出：auto 值与 basis 独立两路，DB 标注层缺行时 annotation 字段为 None。"""
    meta = {
        "schema": 2,
        "reports": {
            "007-3": {
                "stage": "planning_eia",
                "report_title": "封面报告名",
                "report_title_basis": "cover",
                "eia_org": None,
                "eia_org_basis": "needs_review",
                "project_no": "H75041Z",
                "year_hint": 2025,
                "year_basis": "cover",
                "scale_basis": "needs_review",
                "scale_candidates": [],
                "province": "甘肃",
                "standards_cited": [],
            }
        },
    }

    class _FakeRepo:
        async def list_annotations(self):
            return []

    monkeypatch.setattr(eia_meta_service, "_load_corpus_meta", lambda: meta)
    svc = EiaMetaService()
    svc.repo = _FakeRepo()
    out = asyncio.run(svc.list_reports())
    item = next(i for i in out["items"] if i["report_id"] == "007-3")
    assert item["auto_report_title"] == "封面报告名"
    assert item["report_title_basis"] == "cover"
    assert item["auto_eia_org"] is None
    assert item["eia_org_basis"] == "needs_review"
    assert item["project_no"] == "H75041Z"
    assert item["annotation"]["report_title"] is None
    assert item["annotation"]["eia_org"] is None


def test_list_reports_annotation_passthrough_values(monkeypatch):
    """DB 标注层键名逐字透出：annotation 字段拼写漂移（如 report_titel）必须在此暴露。"""
    meta = {
        "schema": 2,
        "reports": {
            "007-3": {
                "stage": "planning_eia",
                "report_title": "封面报告名",
                "report_title_basis": "cover",
                "eia_org": None,
                "eia_org_basis": "needs_review",
                "project_no": "H75041Z",
                "year_hint": 2025,
                "year_basis": "cover",
                "scale_basis": "needs_review",
                "scale_candidates": [],
                "province": "甘肃",
                "standards_cited": [],
            }
        },
    }
    row = SimpleNamespace(
        report_id="007-3",
        annotations={"report_title": "DB名", "eia_org": "DB单位"},
        note=None,
        decided_by="qa",
        decided_at=datetime(2025, 6, 1),
    )

    class _FakeRepo:
        async def list_annotations(self):
            return [row]

    monkeypatch.setattr(eia_meta_service, "_load_corpus_meta", lambda: meta)
    svc = EiaMetaService()
    svc.repo = _FakeRepo()
    out = asyncio.run(svc.list_reports())
    item = next(i for i in out["items"] if i["report_id"] == "007-3")
    assert item["annotation"]["report_title"] == "DB名"
    assert item["annotation"]["eia_org"] == "DB单位"
