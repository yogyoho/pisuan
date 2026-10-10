"""eia_standard_service 纯函数单测：核实载荷校验（action 白名单、note 类型、未知字段拒收）+ 引用码归一。"""

from __future__ import annotations

import pytest

from yuxi.services.eia_standard_service import _norm_std, _validate_review


def test_validate_review_accepts_confirm():
    assert _validate_review({"action": "confirm"}) is None
    assert _validate_review({"action": "confirm", "note": "已对照标准原文"}) is None


def test_validate_review_rejects_bad_action():
    for bad in ("reject", "Confirm", "", None):
        with pytest.raises(ValueError, match="action"):
            _validate_review({"action": bad})
    with pytest.raises(ValueError, match="action"):
        _validate_review({})


def test_validate_review_rejects_unknown_fields():
    with pytest.raises(ValueError, match="未知核实字段"):
        _validate_review({"action": "confirm", "tier": "emission_limit"})


def test_validate_review_rejects_non_string_note():
    with pytest.raises(ValueError, match="note"):
        _validate_review({"action": "confirm", "note": 123})


def test_norm_std_absorbs_citation_noise():
    """语料引用码噪声归一：空格/连字符/破折号/斜杠差异不改变同一性。"""
    base = _norm_std("GB 15618-2018")
    assert base == _norm_std("GB/15618-2018")
    assert base == _norm_std("GB15618—2018")
    assert base == _norm_std("gb 15618 - 2018")
    assert base == _norm_std("GB–15618–2018")
