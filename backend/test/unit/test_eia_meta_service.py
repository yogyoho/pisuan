"""eia_meta_service 纯函数单测：标注载荷校验（year_hint/scale_mt_a 取值域、未知字段拒收）。"""

from __future__ import annotations

import pytest

from yuxi.services.eia_meta_service import _validate_annotations


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
