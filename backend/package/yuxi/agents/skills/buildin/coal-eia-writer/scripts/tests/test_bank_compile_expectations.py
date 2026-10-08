"""section_expectations 测试：数值抽取 / field 归并 / 报告覆盖率 / tier 划档 / unmapped 池 / 节文本切分。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import QUANTITY_RE, build_section_expectations, extract_sec_texts


def test_quantity_re_nfkc_unit_forms():
    """prepare_corpus 全文 NFKC（²→2），语料实为 km2/m2——白名单须认归一形，
    且 km2/m2 不得被更短的 km/m 短路（交替序）。"""
    assert QUANTITY_RE.search("国家级公益林面积为 0.23km2").group(3) == "km2"
    assert QUANTITY_RE.search("沉陷区面积为 12.5km²").group(3) == "km²"
    assert QUANTITY_RE.search("巷道长度为 300 m").group(3) == "m"
    assert QUANTITY_RE.search("年用水量为 15万m3").group(3) == "万m3"


def test_build_section_expectations():
    """两报告同节各提「源强为 95 dB(A)」→ 覆盖率 1.0 → required；S 号零填充两位（6.5→S05）；
    产物无 generated 键（幂等裁决）。"""
    segs = [
        {"rid": "r1", "chapter": "6", "sec": "6.5", "title": "声环境影响评价",
         "text": "源强为 95 dB(A)。运输噪声源强为 75 dB(A)。"},
        {"rid": "r2", "chapter": "6", "sec": "6.5", "title": "声环境影响评价",
         "text": "主要声源源强为 92 dB(A)。"},
    ]
    label_map = {"源强": "noise.source_level"}
    doc = build_section_expectations(segs, label_map, stage="planning_eia")
    assert "generated" not in doc
    s = doc["sections"]["ch6_S05"]
    q = {e["caliber"]: e for e in s["expected_quantities"]}
    assert q["源强"]["corpus_freq"] == 1.0 and q["源强"]["tier"] == "required"
    assert q["源强"]["unit"] == "dB(A)"
    assert q["源强"]["field"] == "noise.source_level"


def test_corpus_freq_is_report_coverage():
    """corpus_freq=报告覆盖率（spec §4.2）：2 报告仅 1 份提及 → 0.5 → optional；
    单报告多次提及不抬高频率（distinct-rid 计数，非出现次数）。"""
    segs = [
        {"rid": "r1", "chapter": "6", "sec": "6.5", "title": "声环境",
         "text": "源强为 95 dB(A)。另一源强为 70 dB(A)。"},
        {"rid": "r2", "chapter": "6", "sec": "6.5", "title": "声环境",
         "text": "本节无匹配量词。"},
    ]
    doc = build_section_expectations(segs, {"源强": "noise.source_level"}, stage="planning_eia")
    q = doc["sections"]["ch6_S05"]["expected_quantities"][0]
    assert q["corpus_freq"] == 0.5 and q["tier"] == "optional"


def test_unmapped_pool():
    """label 未命中 forms_label_map → 进 unmapped 池显式列出（不静默丢弃）。"""
    segs = [{"rid": "r1", "chapter": "3", "sec": "3.2", "title": "某某分析", "text": "不确定量为 12 km。"}]
    doc = build_section_expectations(segs, {}, stage="planning_eia")
    assert doc["unmapped"], "未归并量应进 unmapped 池显式列出"


def test_extract_sec_texts_subsection_folds_into_parent():
    """节文本切分：两段号 sec 的 span 到下一个两段号为止，三段号内容折叠进父节；
    单段号（章标题行）跳过。"""
    seg = ("## 6 声环境\n章引言\n### 6.5 声环境影响评价\n源强为 95 dB(A)。\n"
           "#### 6.5.1 点源\n子节正文。\n### 6.6 固废\n六六正文。\n")
    texts = extract_sec_texts(seg)
    assert set(texts) == {"6.5", "6.6"}
    assert "点源" in texts["6.5"] and "源强为 95" in texts["6.5"]
    assert "六六正文" not in texts["6.5"]


def test_sections_sorted_deterministic():
    """sections 键按（章号, 节号）数值序排列——同输入必同字节（幂等）。"""
    segs = [
        {"rid": "r1", "chapter": "6", "sec": "6.10", "title": "十节", "text": "量为 3 t。"},
        {"rid": "r1", "chapter": "6", "sec": "6.2", "title": "二节", "text": "量为 3 t。"},
        {"rid": "r1", "chapter": "13", "sec": "13.1", "title": "十三章", "text": "量为 3 t。"},
    ]
    doc = build_section_expectations(segs, {}, stage="planning_eia")
    assert list(doc["sections"]) == ["ch6_S02", "ch6_S10", "ch13_S01"]
