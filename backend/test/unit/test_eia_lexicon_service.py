"""eia_lexicon_service 单元测试：导入预置 / 区间构建 / 语料扫描与提及收集。

语料相关断言依赖仓库内置 coal-eia-writer 技能（宿主无技能目录时自动跳过）；
DB 流转（导入幂等 / PATCH 状态机 / 拆分 / 导出物化）在集成环境（容器 + PG）验证。
"""

import pytest

from yuxi.services.eia_data_service import _scan_all, _skill_root_exists
from yuxi.services.eia_lexicon_service import _build_range, _load_bank_compile, _preset_status, collect_mentions


def test_preset_status_import_mapping():
    """导入预置（2026-10-09 裁决）：A 类入选 / B 类候选 / C 类留档 / 控制效率→拆分。"""
    assert _preset_status("measure", "除尘效率") == "approved"
    assert _preset_status("site", "超标率") == "candidate"
    assert _preset_status("junk", "占地面积") == "rejected"
    assert _preset_status("measure", "控制效率") == "splitting"


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


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_scan_all_matches_census():
    """全量扫描与语料普查口径一致：89 候选 / A30 / B34 / range_ready 6。"""
    entries = _scan_all()
    assert len(entries) == 89
    assert sum(1 for e in entries if e["category"] == "measure") == 30
    assert sum(1 for e in entries if e["category"] == "site") == 34
    assert sum(1 for e in entries if e["range_ready"]) == 6


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_collect_mentions_consistent_with_scan():
    """mentions 收集与扫描同源：任一扫描条目的提及数 == n_values，distinct rid 数 == n_reports。"""
    entries = _scan_all()
    e = max(entries, key=lambda x: x["n_values"])
    ms = collect_mentions(e["stage"], e["caliber"], e["unit"])
    assert len(ms) == e["n_values"]
    assert len({m["rid"] for m in ms}) == e["n_reports"]
    assert all(m["unit"] == e["unit"] for m in ms)
