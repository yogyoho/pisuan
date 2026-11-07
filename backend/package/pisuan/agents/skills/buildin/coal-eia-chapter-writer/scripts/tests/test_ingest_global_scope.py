"""门1 目标章裁剪（bug-4143 方案A）：ingest check --global-only --chapters 只校目标章引用的全局族。

口径：裁剪集 = 目标章 sections 的 {{SLOT:family.}} / {{TABLE:family}} 引用族 ∪ 消费公式族
FORMULA_FORM_DEPS 依赖；ingest 侧再与 global_families 取交集。未知章回退全量全局族
（正确性优先，同 formula_runner.resolve_scope 的 SCOPE_FALLBACK）。

背景：门1 原为工程级硬门（整包 7 族），「只写第2章」被迫为第 6/7/9 章才消费的
air/noise/solid_waste/subsidence_params/water/investment 备数——按目标章裁剪后，
第 2 章门1 只查 mine_plan 一族。
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _paths import refs_root  # 同目录上一级：references 根解析（P2-8 单源化回落）

import derive_globals
import ingest

# ── mini stage：ch2 引用 mine_plan 槽位（无公式）；ch3 只引用非全局族 geography；
#    ch6 引用 water 槽位/表 + mine_plan 槽位 + 消费公式 capacity:water ──

STAGE = {
    "chapters": {
        "ch2": {"sections": [
            {"uses": {"formulas": []}, "contract": "总规模 {{SLOT:mine_plan.total_scale_mt_a_after}} Mt/a"},
        ]},
        "ch3": {"sections": [
            {"uses": {"formulas": []}, "contract": "地貌 {{SLOT:geography.relief}}"},
        ]},
        "ch6": {"sections": [
            {"uses": {"formulas": ["capacity:water"]},
             "contract": "涌水 {{SLOT:water_balance.q}}，见表{{TABLE:water}}，井田数 {{SLOT:mine_plan.mine_count}}"},
        ]},
    },
    "forms": {
        "mine_plan": {"file": "01_mine_plan.json"},
        "water": {"file": "05_water.json"},
        "air": {"file": "04_air.json"},
    },
}

DEPS = {"capacity:water": ("water",), "_derived": ("solid_waste", "mine_plan", "investment")}


def test_scope_globals_slot_only():
    assert derive_globals.scope_globals(STAGE, {"ch2"}, formula_deps=DEPS) == {"mine_plan"}


def test_scope_globals_formula_and_table():
    # water_balance 是公式键族（{{SLOT:water_balance.q}}）——原始引用集含它，交集由 ingest 侧滤除
    assert derive_globals.scope_globals(STAGE, {"ch6"}, formula_deps=DEPS) == {"water", "mine_plan", "water_balance"}


def test_scope_globals_returns_raw_refs():
    # ch3 只引用非全局族 geography——返回原始引用族，与 global_families 的交集由 ingest 侧做
    assert derive_globals.scope_globals(STAGE, {"ch3"}, formula_deps=DEPS) == {"geography"}


def test_scope_globals_unknown_chapter_fallback():
    assert derive_globals.scope_globals(STAGE, {"ch9x"}, formula_deps=DEPS) is None


# ── cmd_check --chapters 集成：只校目标章引用的全局族 ──

@pytest.fixture()
def scope_env(tmp_path, monkeypatch):
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "data_expectations.json").write_text(
        json.dumps({"global_families": ["mine_plan", "water", "air"]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(derive_globals, "EXPECTATIONS_PATH", refs / "data_expectations.json")

    stage = tmp_path / "stage.json"
    stage.write_text(json.dumps({"chapters": STAGE["chapters"], "forms": STAGE["forms"]}, ensure_ascii=False),
                     encoding="utf-8")

    data = tmp_path / "data"
    data.mkdir()
    (data / "01_mine_plan.json").write_text(json.dumps({"x": "1"}), encoding="utf-8")  # 只有 mine_plan 就绪
    # bug-3229 外来文件守卫：data/ 文件须登记（与 test_global_families 同法）
    (data / "state_manifest.json").write_text(json.dumps(
        {"version": 1, "files": {"01_mine_plan.json": {"sha256": ingest.sha256_file(data / "01_mine_plan.json")}}}),
        encoding="utf-8")
    return tmp_path, stage


def _check_args(tmp: Path, stage: Path, chapters: str | None) -> Namespace:
    return Namespace(stage=str(stage), data_dir=str(tmp / "data"), output=None,
                     global_only=True, chapters=chapters)


def test_check_scoped_only_mine_plan_required(scope_env, capsys):
    tmp, stage = scope_env
    rc = ingest.cmd_check(_check_args(tmp, stage, chapters="ch2"))
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_OK
    assert "GATE1_COMPLETE" in out
    assert "GLOBAL_SCOPE" in out  # 裁剪口径对用户可见


def test_check_unscoped_still_requires_all_globals(scope_env, capsys):
    tmp, stage = scope_env
    rc = ingest.cmd_check(_check_args(tmp, stage, chapters=None))
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_MANUAL
    assert "05_water.json" in out and "04_air.json" in out


def test_check_unknown_chapter_falls_back_full(scope_env, capsys):
    tmp, stage = scope_env
    rc = ingest.cmd_check(_check_args(tmp, stage, chapters="ch9x"))
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_MANUAL
    assert "GLOBAL_SCOPE_FALLBACK" in out


def test_scope_real_planning_eia_ch2_mine_plan_only():
    """真实 planning_eia 健全性：第2章裁剪后全局族只剩 mine_plan（bug-4143 用户故事口径）。"""
    refs = refs_root()
    st = json.loads((refs / "stages" / "planning_eia.json").read_text(encoding="utf-8"))
    exp = json.loads((refs / "data_expectations.json").read_text(encoding="utf-8"))
    scoped = derive_globals.scope_globals(st, {"ch2"})
    assert scoped is not None
    assert scoped & set(exp["global_families"]) == {"mine_plan"}
    scoped6 = derive_globals.scope_globals(st, {"ch6"})
    assert scoped6 is not None
    assert {"subsidence_params", "water", "air", "noise", "solid_waste"} <= scoped6 & set(exp["global_families"])
