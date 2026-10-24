"""formula_runner --chapters 章级切片测试：scope 解析 + compute 块 guard + 增量冻结合并 + SCOPE_FALLBACK。

fixture 只喂 subsidence_params（可成功 emit）；noise 族缺数据——恰好让 guard 语义可观测：
chB(noise) scope 执行产出空增量，合并后已冻结的 subsidence 槽位必须原样保留。
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import formula_runner

STAGE = {
    "stage_id": "demo",
    "forms": {"subsidence_params": {"file": "subsidence_params.json"}},
    "chapters": {
        "chA": {"sections": [{"id": "chA_S01", "uses": {"formulas": ["subsidence"]}}]},
        "chB": {"sections": [{"id": "chB_S01", "uses": {"formulas": ["noise"]}}]},
        "chC": {"sections": [{"id": "chC_S01", "uses": {"formulas": []}}]},
        "chX": {"sections": [{"id": "chX_S01", "uses": {"formulas": ["no_such_formula"]}}]},
    },
}

SUBS = {
    "q": 0.6, "b": 0.25, "tan_beta": 2.0,
    "per_mine": [{"mine": "甲矿", "seam": "2号层", "m": 2.0, "H": 300, "alpha": 5, "repeat_mining": False}],
}


def _setup(tmp: Path) -> tuple[Path, Path]:
    data_dir = tmp / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "subsidence_params.json").write_text(json.dumps(SUBS, ensure_ascii=False), encoding="utf-8")
    stage_path = tmp / "stage.json"
    stage_path.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    return data_dir, stage_path


def _args(tmp: Path, chapters: str | None) -> Namespace:
    data_dir, stage_path = _setup(tmp)
    return Namespace(data_dir=str(data_dir), stage=str(stage_path), state_dir=str(tmp / "state"), output=None, chapters=chapters)


def test_resolve_scope_branches():
    assert formula_runner.resolve_scope("chA", STAGE) == frozenset({"subsidence"})
    assert formula_runner.resolve_scope("chA,chB", STAGE) == frozenset({"subsidence", "noise"})
    assert formula_runner.resolve_scope("chC", STAGE) == frozenset()  # 空集合法（如 ch2 无公式消费）
    assert formula_runner.resolve_scope(None, STAGE) is None  # 全量


def test_resolve_scope_fallback(capsys):
    assert formula_runner.resolve_scope("chZ", STAGE) is None  # 未知章
    assert "SCOPE_FALLBACK" in capsys.readouterr().out
    assert formula_runner.resolve_scope("chX", STAGE) is None  # 未知族名
    assert "SCOPE_FALLBACK" in capsys.readouterr().out


def test_compute_only_guard(tmp_path):
    data_dir, stage_path = _setup(tmp_path)
    data = formula_runner.Data(data_dir, STAGE)
    full, _ = formula_runner.compute(data)
    assert any(k.startswith("subsidence.") for k in full)
    only_sub, _ = formula_runner.compute(data, only=frozenset({"subsidence"}))
    assert any(k.startswith("subsidence.") for k in only_sub)
    # guard 生效：scope=noise 时即使 subsidence 数据齐全也不计算
    only_noise, _ = formula_runner.compute(data, only=frozenset({"noise"}))
    assert not any(k.startswith("subsidence.") for k in only_noise)


def _run(tmp: Path, chapters: str | None) -> Path:
    rc = formula_runner.cmd_execute(_args(tmp, chapters))
    assert rc in (0, 3), rc  # EXIT_OK / EXIT_ANOMALY 均算执行成功
    return tmp / "state" / "formula_state.json"


def test_execute_chapter_scope_subset(tmp_path):
    out = _run(tmp_path, "chA")
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert any(k.startswith("subsidence.") for k in doc["values"])
    assert not any(k.startswith("noise.") for k in doc["values"])


def test_execute_incremental_merge_and_idempotent(tmp_path):
    out = _run(tmp_path, "chA")
    first = json.loads(out.read_text(encoding="utf-8"))
    sub_keys = [k for k in first["values"] if k.startswith("subsidence.")]
    assert sub_keys
    # chB 增量：noise scope 产出空增量，已冻结 subsidence 槽位必须原样保留（不重算不丢失）
    _run(tmp_path, "chB")
    merged = json.loads(out.read_text(encoding="utf-8"))
    for k in sub_keys:
        assert merged["values"][k] == first["values"][k], k
    # 幂等：同 scope 重跑字节一致
    before = out.read_bytes()
    _run(tmp_path, "chB")
    assert out.read_bytes() == before


def test_execute_full_unchanged_by_default(tmp_path):
    """不带 --chapters 全量路径行为不变：两章数据齐全时一次冻结全部。"""
    out = _run(tmp_path, None)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert any(k.startswith("subsidence.") for k in doc["values"])


def test_execute_unknown_chapter_falls_back_full(tmp_path, capsys):
    out = _run(tmp_path, "chZ")
    assert "SCOPE_FALLBACK" in capsys.readouterr().out
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert any(k.startswith("subsidence.") for k in doc["values"])
