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
    n = _aggregate_depth_targets(refs, "stage_a")
    doc = json.loads((refs / "depth_targets" / "stage_a.json").read_text(encoding="utf-8"))
    assert n == 2
    assert doc["chapters"]["ch1"]["floor_chars"] == 9000   # median(6000, 12000)
    assert doc["chapters"]["ch2"]["floor_chars"] == 12000  # 单矿种 20000*0.6
    assert doc["stage"] == "stage_a"
    assert "generated" not in doc
    assert "coal" in doc["source"]


def test_aggregate_skips_corrupt_file(tmp_path):
    """坏 JSON 跳过不抛：合法者仍聚合，source 溯源只列成功解析者。"""
    refs = tmp_path / "references"
    dt = refs / "depth_targets" / "stage_a"
    dt.mkdir(parents=True)
    (dt / "coal.json").write_text(json.dumps(
        {"coefficient": 0.6, "per_chapter": {"ch1": {"median_eff": 10000}}}), encoding="utf-8")
    (dt / "broken.json").write_text("{not json", encoding="utf-8")
    n = _aggregate_depth_targets(refs, "stage_a")
    doc = json.loads((refs / "depth_targets" / "stage_a.json").read_text(encoding="utf-8"))
    assert n == 1
    assert doc["chapters"]["ch1"]["floor_chars"] == 6000
    assert "coal.json" in doc["source"] and "broken" not in doc["source"]


def test_aggregate_no_valid_docs_returns_none(tmp_path):
    """空目录/全损坏 → stderr 告警 + 返回 None，不落盘（AGGREGATED 不虚报）。"""
    refs = tmp_path / "references"
    dt = refs / "depth_targets" / "stage_a"
    dt.mkdir(parents=True)
    assert _aggregate_depth_targets(refs, "stage_a") is None  # 空目录
    (dt / "broken.json").write_text("{not json", encoding="utf-8")
    assert _aggregate_depth_targets(refs, "stage_a") is None  # 全损坏
    assert not (refs / "depth_targets" / "stage_a.json").exists()
