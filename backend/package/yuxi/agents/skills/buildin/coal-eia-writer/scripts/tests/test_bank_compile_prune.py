"""bank_compile --prune 单测：(stage, rid) 二元组判定，rid 改判 stage 旧位同清（bug-4011）。

_prune_stale_slices 旧实现只按 rid 是否在 keep 集删除——rid 改判 stage 后旧 stage 目录的
切片与 SL3 指纹幸存且新位重写，非递归 glob 指纹池双计。现按 (stage, rid) 全等匹配。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import bank_compile as bc  # noqa: E402


def _mk(refs: Path, kind: str, stage: str, name: str) -> Path:
    if kind == "slice":
        p = refs / "samples_bank" / stage / "slices" / "ch3" / name
    else:
        p = refs / "samples" / stage / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("seg", encoding="utf-8")
    return p


def test_prune_keeps_current_pair(tmp_path):
    refs = tmp_path / "refs"
    s = _mk(refs, "slice", "planning_eia", "r1__3.md")
    f = _mk(refs, "sl3", "planning_eia", "ch3__r1.md")
    removed = bc._prune_stale_slices(refs, {("planning_eia", "r1")})
    assert removed == 0
    assert s.is_file() and f.is_file()


def test_prune_removes_stage_moved_old_location(tmp_path):
    """rid 改判 stage：旧 planning_eia 位清除，新 project_eia_underground 位保留（双计防护）。"""
    refs = tmp_path / "refs"
    old_s = _mk(refs, "slice", "planning_eia", "r1__3.md")
    old_f = _mk(refs, "sl3", "planning_eia", "ch3__r1.md")
    new_s = _mk(refs, "slice", "project_eia_underground", "r1__3.md")
    new_f = _mk(refs, "sl3", "project_eia_underground", "ch3__r1.md")
    removed = bc._prune_stale_slices(refs, {("project_eia_underground", "r1")})
    assert removed == 2
    assert not old_s.exists() and not old_f.exists()
    assert new_s.exists() and new_f.exists()


def test_prune_removes_rid_gone_and_spares_handwritten(tmp_path):
    """rid 消失 → 清除；缺 stage 条目（keep 集为空对）→ 同清；手写 chN_sample.md 豁免。"""
    refs = tmp_path / "refs"
    gone = _mk(refs, "slice", "post_eia", "r9__1.md")
    hand = refs / "samples_bank" / "post_eia" / "slices" / "ch1" / "ch1_sample.md"
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text("手写样例", encoding="utf-8")
    removed = bc._prune_stale_slices(refs, set())
    assert removed == 1
    assert not gone.exists()
    assert hand.exists()
