"""eia_lexicon_service 单元测试：导入预置 / 区间构建 / 语料扫描与提及收集。

语料相关断言依赖仓库内置 coal-eia-writer 技能（宿主无技能目录时自动跳过）；
DB 流转（导入幂等 / PATCH 状态机 / 拆分 / 导出物化）在集成环境（容器 + PG）验证。
"""

import pytest

from pisuan.services.eia_data_service import (
    _block_span,
    _load_quantity_re,
    _scan_all,
    _skill_root_exists,
)
from pisuan.services.eia_lexicon_service import (
    _IMPORT_BLOCKLIST,
    _build_range,
    _load_bank_compile,
    _preset_status,
    collect_mention_details,
    collect_mentions,
)


def test_preset_status_import_mapping():
    """导入预置（2026-10-09 裁决）：A 类入选 / B 类候选 / C 类留档 / 控制效率→拆分。"""
    assert _preset_status("measure", "除尘效率") == "approved"
    assert _preset_status("site", "超标率") == "candidate"
    assert _preset_status("junk", "占地面积") == "rejected"
    assert _preset_status("measure", "控制效率") == "splitting"


def test_import_blocklist_matches_adjudicated_renames():
    """导入抑制种子（2026-10-10 方案B 裁决）：恰为 7 条改名条目的旧断章指纹，防漂移。

    P4 后运行态判跳过查 DB 抑制表（eia_lexicon_suppressions，v13 迁移播种本名单）；
    本测试钉的是 _LEXICON_BLOCKLIST_SEED 的再导出视图——名单漂移即迁移种子漂移。
    语义：这 7 条已 PATCH 改规范名，旧指纹不在 DB（改名即失配），无抑制则重扫必以
    断章名复活（measure 类按预置直接回 approved）。多一条会误杀同名合法新句式，
    少一条会复活，故钉死全集。"""
    assert _IMPORT_BLOCKLIST == {
        ("planning_eia", "价区植被覆盖度值", "%"),  # → 评价区植被覆盖度
        ("project_eia_openpit", "处置率", "%"),  # → 剥离物处置率
        ("planning_eia", "水平达标率", "%"),  # → 三率水平达标率
        ("planning_eia", "危险废物处置率", "%"),  # → 煤矸石及危险废物处置率
        ("planning_eia", "节水率", "%"),  # → 抑尘剂节水率
        ("planning_eia", "降尘效率", "%"),  # → 抑尘剂降尘效率
        ("project_eia_openpit", "环境质量达标率", "%"),  # → 土壤环境质量达标率
    }


def test_build_range_gate_and_percentiles():
    """区间构建：门槛取自 bank_compile（RANGE_MIN_REPORTS），分位数与 bank_compile._pctl 同源。"""
    mod = _load_bank_compile()
    vals = [90.0, 91.0, 92.0, 93.0, 94.0]
    rng = _build_range(vals, mod.RANGE_MIN_REPORTS)
    assert rng["p50"] == 92.0
    assert rng["p5"] == 90.2  # pos=4*0.05=0.2 → 90+(91-90)*0.2
    assert rng["p95"] == 93.8
    assert rng["n_values"] == 5
    assert _build_range(vals, mod.RANGE_MIN_REPORTS - 1) is None  # distinct 报告数门槛
    assert _build_range([], mod.RANGE_MIN_REPORTS) is None


def test_block_span_extends_to_cover_match_end():
    """行块定位（P4 语境契约）：上下吸收非空行；QUANTITY_RE 的 \\s* 吞空行致 match 跨块
    时（实测 3/1245），行块须延伸覆盖 match.end()，否则三段文本切掉 hit 尾部。"""
    text = "甲段\n\n乙段首行\n乙段续行\n\n丙段"
    s = text.index("乙段首行")  # 命中起点在乙段首行
    e = text.index("乙段续行") + 2  # 终点落在下一行（跨换行）
    bs, be = _block_span(text, s, e)
    assert text[bs:be] == "乙段首行\n乙段续行"

    e2 = text.index("丙段") + 2  # 终点跨过空行落到丙段（吞空行实况）
    bs2, be2 = _block_span(text, s, e2)
    assert text[bs2:be2] == "乙段首行\n乙段续行\n\n丙段"

    s3 = text.index("丙段")  # 前面隔空行：不向上吸收甲乙段
    bs3, be3 = _block_span(text, s3, s3 + 2)
    assert text[bs3:be3] == "丙段"


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_scan_all_matches_census():
    """全量扫描与语料普查口径一致：92 候选 / A34 / B34 / range_ready 9
    （P1 连接词扩展 +1：planning 煤矸石综合利用率 2/2 独立成键；
    P2 拉丁前缀窗 +2：裸「控制效率」三分成三子口径（splitting 不计数故 -1 不显）、
    「产生量」精化为「TSP产生量」切片源未达 n≥2 门槛 -1，净 +2；控制效率入 measure
    枚举后 range_ready 6→9）。"""
    entries = _scan_all()
    assert len(entries) == 92
    assert sum(1 for e in entries if e["category"] == "measure") == 34
    assert sum(1 for e in entries if e["category"] == "site") == 34
    assert sum(1 for e in entries if e["range_ready"]) == 9


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_collect_mentions_consistent_with_scan():
    """mentions 收集与扫描同源：任一扫描条目的提及数 == n_values，distinct rid 数 == n_reports。"""
    entries = _scan_all()
    e = max(entries, key=lambda x: x["n_values"])
    ms = collect_mentions(e["stage"], e["caliber"], e["unit"])
    assert len(ms) == e["n_values"]
    assert len({m["rid"] for m in ms}) == e["n_reports"]
    assert all(m["unit"] == e["unit"] for m in ms)


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_mention_details_hit_is_exact_regex_match():
    """三段契约（P4 改名对话框）：hit 恰为 QUANTITY_RE 的一个完整匹配（含连接词与数值
    单位，即 group(0)），前后截断 ≤200 字，值/单位与扫描同源。"""
    qty_re = _load_quantity_re()
    checked = 0
    for e in _scan_all():
        for d in collect_mention_details(e["stage"], e["caliber"], e["unit"]):
            assert qty_re.fullmatch(d["hit"])
            assert len(d["before"]) <= 200 and len(d["after"]) <= 200
            assert d["unit"] == e["unit"] and d["rid"]
            assert d["hit"] and isinstance(d["value"], float)
            checked += 1
            if checked >= 50:
                return
    assert checked >= 50  # 全语料 1245 处提及，取满 50 即证契约普遍成立


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_mention_details_dedup_and_determinism():
    """同段重复命中去重合并：distinct rid 数与扫描一致；两次调用结果确定。"""
    entries = _scan_all()
    e = max(entries, key=lambda x: x["n_values"])
    d1 = collect_mention_details(e["stage"], e["caliber"], e["unit"])
    d2 = collect_mention_details(e["stage"], e["caliber"], e["unit"])
    assert d1 == d2
    assert {d["rid"] for d in d1} == {m["rid"] for m in collect_mentions(e["stage"], e["caliber"], e["unit"])}
    keys = [(d["rid"], d["before"], d["hit"], d["after"]) for d in d1]
    assert len(keys) == len(set(keys))  # 展示行无重复
