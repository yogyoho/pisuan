"""eia_paradigm_scan 单元测试：专名扫描集构建与命中（承方向 A A1 红线）。

扫描集依赖仓库内置 coal-eia-writer 技能 sample_entities（宿主无技能目录时自动跳过）。
夹具动态取自真实黑名单（不硬编码实体串，防黑名单迭代漂移）。
"""

import json

import pytest

from yuxi.services import eia_paradigm_scan
from yuxi.services.eia_data_service import _SKILL_ROOT

_ENTITIES_DIR = _SKILL_ROOT / "references" / "sample_entities"

pytestmark = pytest.mark.skipif(not _ENTITIES_DIR.exists(), reason="宿主无技能 sample_entities 目录")


def _blacklists() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(_ENTITIES_DIR.glob("*.json"))
        if p.name != "_index.json"
    ]


def test_propernoun_hit_in_text():
    """黑名单专名（单文件独有）进扫描集，出现在文本中即命中。"""
    doc = next(d for d in _blacklists() if d["sample_slug"] == "hengcheng")
    term = doc["entities"]["projects"][0]
    assert term not in eia_paradigm_scan.GENERIC_TERMS()
    assert term in eia_paradigm_scan.scan_text(f"本报告以{term}规划区为对象。")


def test_high_frequency_and_generic_terms_exempt():
    """≥3 份黑名单共现的词与各文件 generic_terms 声明的通用词不入扫描集。"""
    counts: dict[str, int] = {}
    for d in _blacklists():
        for terms in d["entities"].values():
            for t in terms:
                counts[t] = counts.get(t, 0) + 1
    freq = [t for t, n in counts.items() if n >= 3]
    # 夹具镜像实现侧豁免规则①：generic_terms 含「/」复合作逐段拆分
    generic = {seg for d in _blacklists() for g in d.get("generic_terms", []) for seg in g.split("/")}
    assert eia_paradigm_scan.GENERIC_TERMS() >= set(freq) | generic
    for t in list(set(freq) | generic)[:5]:
        assert t not in eia_paradigm_scan.scan_text(f"文本提及{t}不判命中。")


def test_substring_of_generic_exempt():
    """专名若为某通用词的子串（或反之）→ 豁免（方向 A §8 规则）。"""
    generic = sorted(eia_paradigm_scan.GENERIC_TERMS())
    assert generic, "通用词集不应为空"
    g = generic[0]
    assert g not in eia_paradigm_scan.scan_text(f"xx{g}yy")


def test_scan_deterministic_sorted():
    hits = eia_paradigm_scan.scan_text("".join(sorted(eia_paradigm_scan.PROPER_NOUNS())[:3]))
    assert hits == sorted(hits)
