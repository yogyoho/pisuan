"""eia_standard_service.get_gate1_checks 测试（P2-3 门 1 体检卡）。

gate1_code_checks 是规则规格（desc/allowed_patterns/rules），不是违规明细数据源——
卡片只透出规则本身 + 注册表自检（standards[].code 对 allowed_patterns 逐条比对，
报出匹配不上任何模式的 code），不伪造违规细节。
"""

import json

import pytest

from yuxi.services import eia_standard_service as std_mod


def _index_fixture(tmp_path):
    doc = {
        "version": "test",
        "standards": [
            {"code": "HJ 130-2019", "title": "规划环评技术导则", "tier": "framework"},
            {"code": "GB/T 21598-2021", "title": "某国标", "tier": "method"},
            {"code": "《环境保护法》", "title": "法律全称", "tier": "law"},
            {"code": "（2018）", "title": "空括号占位实证", "tier": "method"},
            {"code": "HJxxx", "title": "缺年份空格错位", "tier": "method"},
        ],
        "gate1_code_checks": {
            "desc": "门 1 标准号体检",
            "allowed_patterns": [
                "^HJ\\s?\\d+(\\.\\d+)?(-\\d{4})?$",
                "^GB(/T)?\\s?\\d+(\\.\\d+)?(-\\d{4})?$",
                "^《[^《》]+》$",
            ],
            "rules": ["标准号非空——禁止空括号占位"],
        },
    }
    (tmp_path / "standards_index.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


@pytest.fixture()
def std(monkeypatch, tmp_path):
    _index_fixture(tmp_path)
    monkeypatch.setattr(std_mod, "STANDARDS_INDEX_PATH", tmp_path / "standards_index.json")
    return std_mod.EiaStandardService()


@pytest.mark.asyncio
async def test_gate1_returns_rule_spec_verbatim(std):
    out = await std.get_gate1_checks()
    assert out["desc"] == "门 1 标准号体检"
    assert out["rules"] == ["标准号非空——禁止空括号占位"]
    assert len(out["allowed_patterns"]) == 3


@pytest.mark.asyncio
async def test_gate1_registry_selfcheck_reports_pattern_violations(std):
    out = await std.get_gate1_checks()
    check = out["registry_check"]
    assert check["total"] == 5
    # （2018）空括号与 HJxxx 错位码均匹配不上任何 allowed_pattern
    assert check["violations"] == ["（2018）", "HJxxx"]
