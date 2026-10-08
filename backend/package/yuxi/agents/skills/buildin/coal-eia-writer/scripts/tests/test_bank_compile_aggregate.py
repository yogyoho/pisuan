# -*- coding: utf-8 -*-
"""bank_compile 聚合测试：per 矿种 → stage 级 floor_chars（组间 median × coefficient）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import _aggregate_depth_targets


def test_aggregate_median_across_minerals(tmp_path):
    refs = tmp_path / "references"
    dt = refs / "depth_targets" / "stage_a"
    dt.mkdir(parents=True)
    (dt / "coal.json").write_text(json.dumps(
        {"coefficient": 0.6, "per_chapter": {"ch1": {"median_eff": 10000}, "ch2": {"median_eff": 20000}}}), encoding="utf-8")
    (dt / "coal2.json").write_text(json.dumps(
        {"coefficient": 0.6, "per_chapter": {"ch1": {"median_eff": 20000}}}), encoding="utf-8")
    _aggregate_depth_targets(refs, "stage_a", generated="2026-10-08")
    doc = json.loads((refs / "depth_targets" / "stage_a.json").read_text(encoding="utf-8"))
    assert doc["chapters"]["ch1"]["floor_chars"] == 9000   # median(6000, 12000)
    assert doc["chapters"]["ch2"]["floor_chars"] == 12000  # 单矿种 20000*0.6
    assert doc["stage"] == "stage_a"
    assert "coal" in doc["source"]
