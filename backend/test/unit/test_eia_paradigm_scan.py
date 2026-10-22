"""eia_paradigm_scan 单元测试：专名扫描集构建与命中（承方向 A A1 红线）。

扫描集依赖仓库内置 coal-eia-writer 技能 sample_entities（宿主无技能目录时自动跳过）。
夹具动态取自真实黑名单（不硬编码实体串，防黑名单迭代漂移）。
"""

import json

import pytest

from pisuan.services import eia_paradigm_scan
from pisuan.services.eia_data_service import _SKILL_ROOT

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
    """≥3 份不同黑名单共现的词与各文件 generic_terms 声明的通用词不入扫描集。"""
    counts: dict[str, int] = {}
    files_by_term: dict[str, set[str]] = {}
    generic: set[str] = set()
    for p in sorted(_ENTITIES_DIR.glob("*.json")):
        if p.name == "_index.json":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        for terms in doc["entities"].values():
            for t in terms:
                counts[t] = counts.get(t, 0) + 1
                files_by_term.setdefault(t, set()).add(p.name)
        # 夹具镜像实现侧豁免规则①：generic_terms 含「/」复合作逐段拆分
        for g in doc.get("generic_terms", []):
            generic.update(g.split("/"))
    freq = [t for t, fs in files_by_term.items() if len(fs) >= 3]
    assert eia_paradigm_scan.GENERIC_TERMS() >= set(freq) | generic
    occ3 = {t for t, n in counts.items() if n >= 3 and len(files_by_term[t]) < eia_paradigm_scan.GENERIC_MIN_FILES}
    assert not (occ3 & eia_paradigm_scan.GENERIC_TERMS())  # 「次数≥3 但不同文件<3」不是通用词（bug-448 语义锚）
    for t in list(set(freq) | generic)[:5]:
        assert t not in eia_paradigm_scan.scan_text(f"文本提及{t}不判命中。")


def test_substring_of_generic_exempt():
    """专名若为某通用词的子串（或反之）→ 豁免（规则③；差分锚：删子串过滤必红）。"""
    blacklists = _blacklists()
    terms = {t for d in blacklists for terms in d.get("entities", {}).values() for t in terms}
    generic = eia_paradigm_scan.GENERIC_TERMS()
    rule3_only = sorted(t for t in terms - generic if any(t in g or g in t for g in generic))
    assert rule3_only, "真实黑名单应存在仅由规则③豁免的词；为空说明语料变化，本测试需重审"
    t0 = rule3_only[0]
    assert t0 not in eia_paradigm_scan.scan_text(f"xx{t0}yy")


def test_scan_deterministic_sorted():
    hits = eia_paradigm_scan.scan_text("".join(sorted(eia_paradigm_scan.PROPER_NOUNS())[:3]))
    assert hits == sorted(hits)
