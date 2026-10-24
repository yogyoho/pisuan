"""bug-4137 静态转录回归：stage forms JSON 族的顶层标量登记为 {family}.{field} 槽位。

背景：stage sections 声明静态 {{SLOT:mine_plan.total_scale_mt_a_before}} 等，但公式层
只 emit 公式族——静态槽位有声明无生产者，单章门干跑注入必 FAIL「未知槽位 key」。
修复后：compute() 末尾静态转录补齐生产者；公式派生键优先；bool/None/list/dict 跳过；
键形不合记 anomaly 不阻断。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import formula_runner
from formula_runner import Data, compute

STAGE = {
    "stage_id": "demo",
    "forms": {
        "mine_plan": {"file": "01_mine_plan.json"},
        "geography": {"file": "06_geography.json"},
    },
    "chapters": {"chA": {"sections": [{"id": "chA_S01", "uses": {"formulas": []}}]}},
}

MINE = {
    "total_scale_mt_a_before": 9.2,
    "total_scale_mt_a_after": 16.0,
    "mine_count": 4,
    "mines": [{"name": "甲矿"}],  # list——走 {{TABLE:mine_plan.mines}}，不入槽位
    "skip_me": None,  # None 跳过
    "flag": True,  # bool 跳过
    "bad field": 1,  # 键形不合（含空格）——anomaly 不阻断
}

GEO = {
    "location_text": "矿区位于鄂尔多斯盆地西缘。",
    "transport": {"rail": "包兰线"},  # dict 跳过
}


def _make(tmp: Path) -> tuple[Data, Path]:
    data_dir = tmp / "data"
    data_dir.mkdir()
    (data_dir / "01_mine_plan.json").write_text(json.dumps(MINE, ensure_ascii=False), encoding="utf-8")
    (data_dir / "06_geography.json").write_text(json.dumps(GEO, ensure_ascii=False), encoding="utf-8")
    return Data(data_dir, STAGE), data_dir


def test_static_scalars_registered(tmp_path):
    data, _ = _make(tmp_path)
    V, anomalies = compute(data)
    assert V["mine_plan.total_scale_mt_a_before"]["display"] == "9.2"
    assert V["mine_plan.total_scale_mt_a_after"]["value"] == 16.0
    assert V["mine_plan.mine_count"]["display"] == "4"
    assert V["geography.location_text"]["display"].startswith("矿区位于")
    assert V["mine_plan.total_scale_mt_a_before"]["source"].startswith("form:mine_plan")


def test_non_scalar_and_bool_skipped(tmp_path):
    data, _ = _make(tmp_path)
    V, _ = compute(data)
    for absent in ("mine_plan.mines", "mine_plan.skip_me", "mine_plan.flag", "geography.transport"):
        assert absent not in V


def test_bad_key_shape_anomaly_not_crash(tmp_path):
    data, _ = _make(tmp_path)
    V, anomalies = compute(data)
    assert "mine_plan.bad field" not in V
    assert any("静态转录跳过" in a and "mine_plan.bad field" in a for a in anomalies)


def test_static_works_under_chapter_scope(tmp_path):
    """章级切片 scope（only=frozenset()）下静态转录仍登记——ch2 类无公式章依赖此路径。"""
    data, _ = _make(tmp_path)
    V, _ = compute(data, only=frozenset())
    assert "mine_plan.total_scale_mt_a_before" in V


def test_state_write_roundtrip(tmp_path):
    """静态槽位经 write_state 终检（键形/display）可落盘。"""
    data, _ = _make(tmp_path)
    V, anomalies = compute(data)
    out = tmp_path / "state" / "formula_state.json"
    formula_runner.write_state(out, V, anomalies)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == 2
    assert doc["values"]["mine_plan.mine_count"]["display"] == "4"
