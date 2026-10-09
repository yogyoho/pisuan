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
        {
            "rid": "r1",
            "chapter": "6",
            "sec": "6.5",
            "title": "声环境影响评价",
            "text": "源强为 95 dB(A)。运输噪声源强为 75 dB(A)。",
        },
        {"rid": "r2", "chapter": "6", "sec": "6.5", "title": "声环境影响评价", "text": "主要声源源强为 92 dB(A)。"},
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
        {
            "rid": "r1",
            "chapter": "6",
            "sec": "6.5",
            "title": "声环境",
            "text": "源强为 95 dB(A)。另一源强为 70 dB(A)。",
        },
        {"rid": "r2", "chapter": "6", "sec": "6.5", "title": "声环境", "text": "本节无匹配量词。"},
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
    seg = (
        "## 6 声环境\n章引言\n### 6.5 声环境影响评价\n源强为 95 dB(A)。\n"
        "#### 6.5.1 点源\n子节正文。\n### 6.6 固废\n六六正文。\n"
    )
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


# ── 数值区间护栏（P5-P95，v1.1） ────────────────────────────────────────────


def _mk_db_segs(n: int) -> list[dict]:
    return [
        {"rid": f"r{i}", "chapter": "6", "sec": "6.5", "title": "声环境", "text": f"源强为 {90 + i} dB(A)。"}
        for i in range(n)
    ]


def test_range_intensive_unit_published():
    """5 报告同节同口径 dB(A) → range 发布；线性插值分位手算校验（90..94）。"""
    doc = build_section_expectations(_mk_db_segs(5), {"源强": "noise.source_level"}, stage="planning_eia")
    q = doc["sections"]["ch6_S05"]["expected_quantities"][0]
    assert q["range"]["n_values"] == 5 and q["range"]["n_reports"] == 5
    assert q["range"]["p50"] == 92.0
    assert q["range"]["p5"] == 90.2  # pos=4*0.05=0.2 → 90+(91-90)*0.2
    assert q["range"]["p95"] == 93.8  # pos=4*0.95=3.8 → 93+(94-93)*0.8


def test_range_extensive_unit_skipped():
    """extensive 量（万t，随产能走）不发布原始区间——scale 归一前置未熟。"""
    segs = [
        {"rid": f"r{i}", "chapter": "3", "sec": "3.2", "title": "固废", "text": "矸石产生量为 12 万t。"}
        for i in range(5)
    ]
    doc = build_section_expectations(segs, {"矸石产生量": "solidwaste.gangue"}, stage="planning_eia")
    q = doc["sections"]["ch3_S02"]["expected_quantities"][0]
    assert "range" not in q


def test_range_min_reports_gate():
    """distinct-rid < 5 → 不发布（小样本 P5/P95≈min/max 无意义）。"""
    doc = build_section_expectations(_mk_db_segs(4), {"源强": "noise.source_level"}, stage="planning_eia")
    q = doc["sections"]["ch6_S05"]["expected_quantities"][0]
    assert "range" not in q


def test_range_first_seen_unit_only():
    """同口径跨单位：range 只统计首见单位（%）的值，后见单位（mg/L）不混入同一分布。"""
    segs = [
        {"rid": f"r{i}", "chapter": "6", "sec": "6.5", "title": "声环境", "text": f"除尘效率为 {95 + i} %。"}
        for i in range(5)
    ]
    segs.append({"rid": "rZ", "chapter": "6", "sec": "6.5", "title": "声环境", "text": "除尘效率为 30 mg/L。"})
    doc = build_section_expectations(segs, {"除尘效率": "air.removal"}, stage="planning_eia")
    q = doc["sections"]["ch6_S05"]["expected_quantities"][0]
    assert q["unit"] == "%" and q["range"]["n_values"] == 5 and q["range"]["n_reports"] == 6


# ── 词表覆盖层（v1.2 curated 跨节发布）──────────────────────────────────────

_CURATED_RANGE = {"p5": 90.0, "p50": 95.0, "p95": 99.0, "n_values": 12, "n_reports": 10}


def _mk_curated_segs() -> list[dict]:
    """同节仅 3 报告（v1.1 门槛不足），同口径跨两节共 6 报告——curated 跨节发布的靶形。"""
    segs = [
        {"rid": f"r{i}", "chapter": "6", "sec": "6.5", "title": "声环境", "text": f"除尘效率为 {95 + i} %。"}
        for i in range(3)
    ]
    segs += [
        {"rid": f"r{i}", "chapter": "7", "sec": "7.1", "title": "措施", "text": f"除尘效率为 {96 + i} %。"}
        for i in range(3, 6)
    ]
    return segs


def test_curated_range_attached_cross_section():
    """curated range 挂到口径出现的每个节（v1.1 同节 distinct-rid<5 不发布，v1.2 覆盖发布）；
    curated 键走 _map_caliber 后缀归并（「主要除尘效率」→「除尘效率」）。"""
    curated = {"主要除尘效率": {"stage": "planning_eia", "caliber": "除尘效率", "unit": "%", "range": _CURATED_RANGE}}
    doc = build_section_expectations(
        _mk_curated_segs(), {"除尘效率": "air.removal"}, stage="planning_eia", curated=curated
    )
    assert doc["version"] == "1.2"
    for key in ("ch6_S05", "ch7_S01"):
        q = doc["sections"][key]["expected_quantities"][0]
        assert q["range"] == _CURATED_RANGE


def test_curated_unit_mismatch_falls_back_to_v11():
    """curated unit 与节首见单位不一致 → 不挂（跨单位不混布），回落 v1.1 同节口径。"""
    curated = {"除尘效率": {"stage": "planning_eia", "caliber": "除尘效率", "unit": "mg/L", "range": _CURATED_RANGE}}
    segs = [
        {"rid": f"r{i}", "chapter": "6", "sec": "6.5", "title": "声环境", "text": f"除尘效率为 {95 + i} %。"}
        for i in range(5)
    ]
    doc = build_section_expectations(segs, {"除尘效率": "air.removal"}, stage="planning_eia", curated=curated)
    q = doc["sections"]["ch6_S05"]["expected_quantities"][0]
    assert q["range"]["n_values"] == 5 and q["range"]["n_values"] != _CURATED_RANGE["n_values"]


def test_curated_unmapped_caliber_skipped():
    """curated 口径未映射 forms 字段 → 跳过（stderr 告警），无 curated 命中时 version 回落 1.1。"""
    curated = {"不存在口径": {"stage": "planning_eia", "caliber": "不存在口径", "unit": "%", "range": _CURATED_RANGE}}
    doc = build_section_expectations(
        _mk_db_segs(5), {"源强": "noise.source_level"}, stage="planning_eia", curated=curated
    )
    q = doc["sections"]["ch6_S05"]["expected_quantities"][0]
    assert doc["version"] == "1.1" and q["caliber"] == "源强"


def test_curated_absent_keeps_v11_version():
    """无 curated（文件缺失/无本 stage 条目）→ version 恒 1.1（删文件即字节级回滚的语义锚）。"""
    doc = build_section_expectations(_mk_db_segs(5), {"源强": "noise.source_level"}, stage="planning_eia")
    assert doc["version"] == "1.1"
