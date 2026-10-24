"""global_families 派生测试：跨≥2章族 ∪ 冻结依赖族 + ingest check --global-only 门1 全局模式。

口径（spec §3.2 / plan Task 5）：global_families = per_chapter 中跨 ≥2 章出现的数据族
∪ 冻结公式依赖的数据表单族（跨章公式族的 FORMULA_FORM_DEPS + derived 常算块依赖）；
由脚本从 stage JSON + data_expectations 派生，不手拍。
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import derive_globals
import ingest

# ── mini fixture：3 章 5 族——shared1/shared2 跨章，solo_a/solo_c 单章，freeze_only 单章但被派生块依赖 ──

EXP = {
    "per_chapter": [
        {"chapter": "chA", "data_families": [{"family": "shared1"}, {"family": "solo_a"}]},
        {"chapter": "chB", "data_families": [{"family": "shared1"}, {"family": "shared2"}]},
        {"chapter": "chC", "data_families": [{"family": "shared2"}, {"family": "freeze_only"}]},
    ]
}

STAGE = {
    "chapters": {
        "chA": {"sections": [{"uses": {"formulas": ["fam_x"]}}]},
        "chB": {"sections": [{"uses": {"formulas": ["fam_x", "fam_y"]}}]},
        "chC": {"sections": [{"uses": {"formulas": []}}]},
    },
    "forms": {"shared1": {"file": "01_shared1.json"}, "freeze_only": {"file": "02_freeze_only.json"}},
}

DEPS = {"fam_x": ("shared1",), "fam_y": ("solo_a",), "_derived": ("freeze_only",)}


def test_derive_mini():
    # clause1: shared1/shared2 跨≥2章 → 进；solo_a/solo_c 单章且非冻结依赖 → 不进
    # clause2: fam_x 跨章(chA+chB) → shared1 进；fam_y 单章不进；_derived 常算 → freeze_only 进
    assert derive_globals.derive(EXP, STAGE, formula_deps=DEPS) == ["freeze_only", "shared1", "shared2"]


def test_derive_real_planning_eia():
    """真实 planning_eia 派生：冻结依赖 7 族 + 跨章 7 族（交并去重）全在；单章非冻结族不在。"""
    refs = Path(__file__).resolve().parent.parent.parent / "references"
    exp = json.loads((refs / "data_expectations.json").read_text(encoding="utf-8"))
    st = json.loads((refs / "stages" / "planning_eia.json").read_text(encoding="utf-8"))
    got = derive_globals.derive(exp, st)
    for fam in ("planning_indicators", "subsidence_params", "water", "air", "noise",
                "solid_waste", "mine_plan", "investment", "eco", "projection"):
        assert fam in got, fam
    for fam in ("measures", "public_participation", "standards_confirm", "sensitive_targets"):
        assert fam not in got, fam


def test_write_globals_zero_disturb_and_idempotent(tmp_path):
    """写回只动 global_families 键：其余字段零扰动（原紧凑格式字节保留）；重跑幂等。

    对「文件尚无 global_families（插入行）」与「已有（原行替换）」两态都必须成立。"""
    import re

    refs = Path(__file__).resolve().parent.parent.parent / "references"
    target = tmp_path / "data_expectations.json"
    original_text = (refs / "data_expectations.json").read_text(encoding="utf-8", newline="")  # raw，不翻译换行
    original = json.loads(original_text)
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(original_text)

    st = json.loads((refs / "stages" / "planning_eia.json").read_text(encoding="utf-8"))
    derive_globals.write_globals(target, st)
    once_bytes = target.read_bytes()
    once = json.loads(once_bytes.decode("utf-8"))
    expected = derive_globals.derive(original, st)
    assert once["global_families"] == expected
    # 其余字段零扰动 + 文本形状保留：预期文本=原文仅替换/插入 global_families 一处
    key = '"global_families": ' + json.dumps(expected, ensure_ascii=False)
    nl = "\r\n" if "\r\n" in original_text[:200] else "\n"
    if "global_families" in original:
        expected_text = re.sub(r'"global_families": \[[^\]]*\]', key, original_text, count=1)
    else:
        expected_text = original_text.replace("{", "{" + nl + "  " + key + ",", 1)
    assert once_bytes.decode("utf-8") == expected_text
    derive_globals.write_globals(target, st)
    assert target.read_bytes() == once_bytes


# ── ingest check --global-only：门1 全局包模式只校 global_families ──

@pytest.fixture()
def check_env(tmp_path, monkeypatch):
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "data_expectations.json").write_text(
        json.dumps({"global_families": ["shared1"]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(derive_globals, "EXPECTATIONS_PATH", refs / "data_expectations.json")

    stage = tmp_path / "stage.json"
    stage.write_text(json.dumps({"forms": {
        "shared1": {"file": "01_shared1.json", "fields": [{"name": "x", "required": True}]},
        "solo_p": {"file": "09_solo_p.json", "fields": [{"name": "y", "required": True}]},
    }}, ensure_ascii=False), encoding="utf-8")
    return tmp_path, stage


def _check_args(tmp: Path, stage: Path, global_only: bool) -> Namespace:
    return Namespace(stage=str(stage), data_dir=str(tmp / "data"), output=None, global_only=global_only)


def test_check_global_only_skips_chapter_families(check_env, capsys):
    tmp, stage = check_env
    rc = ingest.cmd_check(_check_args(tmp, stage, global_only=True))
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_MANUAL
    assert "01_shared1.json" in out  # 全局族缺失照报
    assert "09_solo_p.json" not in out  # 逐章族不进全局门


def test_check_full_mode_reports_both(check_env, capsys):
    tmp, stage = check_env
    ingest.cmd_check(_check_args(tmp, stage, global_only=False))
    out = capsys.readouterr().out
    assert "01_shared1.json" in out and "09_solo_p.json" in out


def test_check_global_only_complete(check_env, capsys):
    tmp, stage = check_env
    d = tmp / "data"
    d.mkdir()
    (d / "01_shared1.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    (d / "state_manifest.json").write_text(json.dumps(
        {"version": 1, "files": {"01_shared1.json": {"sha256": ingest.sha256_file(d / "01_shared1.json")}}}),
        encoding="utf-8")
    rc = ingest.cmd_check(_check_args(tmp, stage, global_only=True))
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_OK and "GATE1_COMPLETE" in out
