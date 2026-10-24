"""分章模式状态机测试：REVIEWED/CONFIRMED 增态 + confirm-chapter + 分章 next 编排。

契约（plan Task 6 / spec §3 分章管线）：
- 章状态链 PENDING→DRAFTED→(gate 真跑)→VERIFIED→REVIEWED→CONFIRMED；
  CONFIRMED 唯一通道 = confirm-chapter（mark 禁达，同 bug-3049 语义）；CONFIRMED→DRAFTED 返工
- next 分章模式输出序 COLLECTING→gate→review→确认卡→下一章；恢复检测认 CONFIRMED 跳过前序
- BLOCKED 不阻后续章（协商后置到只剩 BLOCKED 时）
- key_points 增量：confirm-chapter 把本章 highlights 并入 state/key_points.json（幂等重放字节一致）
- `--mode full` 默认路径零变化：progress.json 不写 mode 键、next 仍 WAVE1 批量编排、confirm-chapter 拒绝
"""

import json
import sys
from argparse import Namespace
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress

STAGE = {
    "chapters": {
        "ch2": {"sections": [{"id": "ch2_S01", "title": "总则"}, {"id": "ch2_S02", "title": "规划概述"}]},
        "ch3": {"sections": [{"id": "ch3_S01", "title": "现状调查"}]},
        "ch4": {"sections": [{"id": "ch4_S01", "title": "影响识别"}]},
    }
}


def _init(tmp: Path, mode: str = "chapter") -> Path:
    stage = tmp / "stage.json"
    stage.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    rc = progress.cmd_init(Namespace(stage=str(stage), state_dir=str(tmp / "state"),
                                     data_dir=str(tmp / "data"), mode=mode))
    assert rc == progress.EXIT_OK
    return tmp / "state"


def _mark(sd: Path, chapter: str, status: str, sections: str | None = None) -> int:
    return progress.cmd_mark(Namespace(chapter=chapter, status=status, sections=sections,
                                       state_dir=str(sd), gate=None, detail=""))


def _gate(sd: Path, chapters: str | None = None) -> int:
    return progress.cmd_gate(Namespace(state_dir=str(sd), chapters=chapters, targets=None))


def _next(sd: Path) -> str:
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = progress.cmd_next(Namespace(state_dir=str(sd)))
    assert rc == progress.EXIT_OK
    return buf.getvalue()


def _confirm(sd: Path, chapter: str, highlights: str = "") -> int:
    return progress.cmd_confirm_chapter(Namespace(chapter=chapter, highlights=highlights, state_dir=str(sd)))


@pytest.fixture()
def stub_gate(monkeypatch):
    """章门 stub：run_chapter_gate 无异常 = PASS（推进凭据语义与真门一致）。"""
    stub = ModuleType("build_output")
    stub.resolve_targets = lambda targets, stage_path, data_dir=None: ({}, "stub")
    stub.run_chapter_gate = lambda stage, data_dir, state_dir, ch, targets: None
    monkeypatch.setitem(sys.modules, "build_output", stub)


def _doc(sd: Path) -> dict:
    return json.loads((sd / "progress.json").read_text(encoding="utf-8"))


# ── 全链：PENDING→DRAFTED→(gate)→VERIFIED→REVIEWED→CONFIRMED ──

def test_full_chain_to_confirmed(tmp_path, stub_gate, capsys):
    sd = _init(tmp_path)
    out = _next(sd)
    assert "COLLECTING" in out and "ch2" in out and "模板推荐" in out  # 首站：汇集+模板推荐+派发
    assert "ch3" not in out.split("ch2_S01")[0] or "ch3" not in out  # 单章聚焦，不并派后章

    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK
    assert "GATE" in _next(sd)

    assert _gate(sd, "ch2") == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["status"] == "VERIFIED"
    assert "REVIEW" in _next(sd) and "审查" in _next(sd)

    assert _mark(sd, "ch2", "REVIEWED") == progress.EXIT_OK
    out = _next(sd)
    assert "确认卡" in out and "confirm-chapter" in out  # 发卡即停契约

    assert _confirm(sd, "ch2", "规划规模 15.0Mt/a|两轮公参完成") == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["status"] == "CONFIRMED"
    out = _next(sd)
    assert "ch3" in out and "COLLECTING" in out and "前序已确认" in out  # 恢复检测跳过 ch2


def test_next_skips_confirmed_chapters(tmp_path, stub_gate):
    sd = _init(tmp_path)
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK
    assert _gate(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch2", "REVIEWED") == progress.EXIT_OK
    assert _confirm(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch3", "DRAFTED") == progress.EXIT_OK
    assert _gate(sd, "ch3") == progress.EXIT_OK
    assert _mark(sd, "ch3", "REVIEWED") == progress.EXIT_OK
    assert _confirm(sd, "ch3") == progress.EXIT_OK
    out = _next(sd)
    assert "ch4" in out and "COLLECTING" in out  # ch2/ch3 CONFIRMED 全跳过
    assert "前序已确认 2 章（跳过）" in out
    assert out.count("ch2") == 1 and out.count("ch3") == 1  # 确认章只在恢复行出现


def test_confirmed_rework_via_mark_draft(tmp_path, stub_gate):
    sd = _init(tmp_path)
    _mark(sd, "ch2", "DRAFTED")
    _gate(sd, "ch2")
    _mark(sd, "ch2", "REVIEWED")
    assert _confirm(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK  # 确认卡返工唯一出口
    assert _doc(sd)["chapters"]["ch2"]["status"] == "DRAFTED"


# ── BLOCKED 不阻后续章 ──

def test_blocked_does_not_block_later_chapters(tmp_path, stub_gate):
    sd = _init(tmp_path)
    _mark(sd, "ch2", "DRAFTED")
    assert _mark(sd, "ch2", "BLOCKED") == progress.EXIT_OK  # 门 FAIL 重派耗尽语义
    out = _next(sd)
    assert "ch3" in out and "COLLECTING" in out  # 不卡死在 ch2，继续后章
    assert "挂起" in out and "BLOCKED ch2" in out  # 挂起章如实提示且不阻当前章

    # 收口后章 → 只剩 BLOCKED 时才进协商
    _mark(sd, "ch3", "DRAFTED")
    _gate(sd, "ch3")
    _mark(sd, "ch3", "REVIEWED")
    _confirm(sd, "ch3")
    _mark(sd, "ch4", "DRAFTED")
    _gate(sd, "ch4")
    _mark(sd, "ch4", "REVIEWED")
    _confirm(sd, "ch4")
    out = _next(sd)
    assert "NEGOTIATE" in out or "协商" in out  # 协商后置


# ── key_points 增量合并幂等 ──

def test_key_points_incremental_merge_idempotent(tmp_path, stub_gate):
    sd = _init(tmp_path)
    for ch, hl in (("ch2", "规模 15.0Mt/a"), ("ch3", "现状调查结论 A")):
        _mark(sd, ch, "DRAFTED")
        _gate(sd, ch)
        _mark(sd, ch, "REVIEWED")
        assert _confirm(sd, ch, hl) == progress.EXIT_OK
    kp = json.loads((sd / "key_points.json").read_text(encoding="utf-8"))
    assert kp["chapters"]["ch2"] == ["规模 15.0Mt/a"]
    assert kp["chapters"]["ch3"] == ["现状调查结论 A"]
    once = (sd / "key_points.json").read_bytes()
    # 幂等重放：同章同要点 → CONFIRMED_ALREADY，字节一致
    rc = _confirm(sd, "ch2", "规模 15.0Mt/a")
    assert rc == progress.EXIT_OK
    assert (sd / "key_points.json").read_bytes() == once
    # 不同要点改 CONFIRMED 章 → 拒绝（确认卡变更须先 mark DRAFTED 返工）
    assert _confirm(sd, "ch2", "改口") != progress.EXIT_OK


# ── 守卫：mark 不可达 CONFIRMED / REVIEWED 章级专属 / VERIFIED 禁手动不破 ──

def test_mark_guards(tmp_path, capsys):
    sd = _init(tmp_path)
    assert _mark(sd, "ch2", "CONFIRMED") != progress.EXIT_OK  # 唯一通道 confirm-chapter
    assert "confirm-chapter" in capsys.readouterr().err
    assert _mark(sd, "ch2", "VERIFIED") != progress.EXIT_OK  # bug-3049 不破
    assert _mark(sd, None, "REVIEWED", sections="ch2_S01") != progress.EXIT_OK  # REVIEWED 章级专属
    assert "章级" in capsys.readouterr().err
    assert _doc(sd)["chapters"]["ch2"]["status"] == "PENDING"  # 全批未动


def test_confirm_requires_reviewed(tmp_path):
    sd = _init(tmp_path)
    assert _confirm(sd, "ch2") != progress.EXIT_OK  # PENDING 直接确认拒绝


# ── full 默认零变化 ──

def test_full_mode_default_unchanged(tmp_path):
    sd = _init(tmp_path, mode="full")
    assert "mode" not in _doc(sd)  # full 模式 progress.json 无 mode 键（字节级不变）
    out = _next(sd)
    assert "COLLECTING" not in out and "确认卡" not in out  # 分章编排不出现在 full
    assert _confirm(sd, "ch2") != progress.EXIT_OK  # confirm-chapter 仅分章模式
    assert _doc(sd)["phase"] == "WAVE1"  # phase 推导零变化
