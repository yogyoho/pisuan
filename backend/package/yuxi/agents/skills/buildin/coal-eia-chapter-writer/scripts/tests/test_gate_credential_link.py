"""门凭据时效链测试（bug-4146）：VERIFIED/REVIEWED/CONFIRMED 三通道全部凭「最近一次真跑门」放行。

契约：
- 章门 FAIL → VERIFIED 当场回落 DRAFTED（last_gate=FAIL）；REVIEWED 状态不动但确认通道封死
- mark VERIFIED→REVIEWED 要求 last_gate=PASS（双保险拦手改 state 绕门）；REVIEWED 不抹门凭据
- confirm-chapter：last_gate=PASS 放行；非 PASS 须 approve-downgrade 显式豁免（禁静默确认）
"""

import json
import sys
from argparse import Namespace
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress

STAGE = {
    "chapters": {
        "ch2": {"sections": [{"id": "ch2_S01", "title": "总则"}, {"id": "ch2_S02", "title": "规划概述"}]},
        "ch3": {"sections": [{"id": "ch3_S01", "title": "现状调查"}]},
    }
}

FAIL_MSG = "L2 深度门 FAIL：章有效字符 10 < 章地板 100"


def _stub(monkeypatch, fail: set[str]):
    """章门 stub：fail 集内的章抛 ValueError（真门 FAIL 语义），其余 PASS。"""
    stub = ModuleType("build_output")
    stub.resolve_targets = lambda targets, stage_path, data_dir=None: ({}, "stub")

    def run(stage, data_dir, state_dir, ch, targets):
        if ch in fail:
            raise ValueError(FAIL_MSG)

    stub.run_chapter_gate = run
    monkeypatch.setitem(sys.modules, "build_output", stub)


def _init(tmp: Path) -> Path:
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    stage = tmp / "stage.json"
    stage.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    rc = progress.cmd_init(
        Namespace(stage=str(stage), state_dir=str(tmp / "state"), data_dir=str(tmp / "data"), mode="chapter")
    )
    assert rc == progress.EXIT_OK
    return tmp / "state"


def _mark(sd: Path, chapter: str, status: str) -> int:
    return progress.cmd_mark(
        Namespace(chapter=chapter, status=status, sections=None, state_dir=str(sd), gate=None, detail="")
    )


def _gate(sd: Path, chapters: str) -> int:
    return progress.cmd_gate(Namespace(state_dir=str(sd), chapters=chapters, targets=None))


def _confirm(sd: Path, chapter: str, highlights: str = "") -> int:
    return progress.cmd_confirm_chapter(Namespace(chapter=chapter, highlights=highlights, state_dir=str(sd)))


def _approve(sd: Path, chapters: str, note: str = "") -> int:
    return progress.cmd_approve(Namespace(state_dir=str(sd), chapters=chapters, note=note))


def _doc(sd: Path) -> dict:
    return json.loads((sd / "progress.json").read_text(encoding="utf-8"))


def _plan(sd: Path, chapter: str) -> int:
    """计划卡落账（卡A）：真走 cmd_plan_confirm 契约（summary_file 须在盘）。"""
    card = sd.parent / f"card_{chapter}.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(f"# {chapter} 编写计划卡\n目标要点。", encoding="utf-8")
    return progress.cmd_plan_confirm(
        Namespace(state_dir=str(sd), chapter=chapter, summary_file=str(card), notes="", depth="full", target=None)
    )


def _choice(sd: Path, chapter: str, none: bool = False) -> int:
    """范例卡落账（卡B）：真走 cmd_fragment_choice 契约；none=True = 用户显式不用范例（P10 豁免）。"""
    return progress.cmd_fragment_choice(
        Namespace(state_dir=str(sd), chapter=chapter, report_id=None if none else "027-2025-11", none=none)
    )


def _credentials(sd: Path, chapter: str) -> None:
    """补齐双卡凭据（P0-3 起章 mark DRAFTED/gate 的前置）。"""
    assert _plan(sd, chapter) == progress.EXIT_OK
    assert _choice(sd, chapter) == progress.EXIT_OK


def test_gate_fail_reverts_verified_and_blocks_review(tmp_path, monkeypatch, capsys):
    _stub(monkeypatch, fail={"ch2"})
    sd = _init(tmp_path)
    _credentials(sd, "ch2")
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK
    assert _gate(sd, "ch2") == progress.EXIT_ERROR
    ch = _doc(sd)["chapters"]["ch2"]
    assert ch["status"] == "DRAFTED"
    assert ch["last_gate"] is None  # DRAFTED 章本无凭据——FAIL 只报 stderr，不造凭据
    assert "CHAPTER_GATE_FAIL" in capsys.readouterr().err
    assert _mark(sd, "ch2", "REVIEWED") != progress.EXIT_OK  # DRAFTED→REVIEWED 非法转移（第一道防线）
    assert "非法转移" in capsys.readouterr().err


def test_gate_fail_after_pass_invalidates_stale_credential(tmp_path, monkeypatch):
    """先 PASS 拿到 VERIFIED，改稿后重跑门 FAIL → 旧凭据当场作废（bug-4146 实测复现路径）。"""
    sd = _init(tmp_path)
    _stub(monkeypatch, fail=set())
    _credentials(sd, "ch2")
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK
    assert _gate(sd, "ch2") == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["status"] == "VERIFIED"
    _stub(monkeypatch, fail={"ch2"})
    assert _gate(sd, "ch2") == progress.EXIT_ERROR
    ch = _doc(sd)["chapters"]["ch2"]
    assert ch["status"] == "DRAFTED" and ch["last_gate"] == "FAIL"
    # 状态机闭环：回落 DRAFTED 后 mark REVIEWED 非法转移，必须重跑门至 PASS
    assert _mark(sd, "ch2", "REVIEWED") != progress.EXIT_OK


def test_reviewed_keeps_gate_credential_and_confirm_passes(tmp_path, monkeypatch, capsys):
    sd = _init(tmp_path)
    _stub(monkeypatch, fail=set())
    _credentials(sd, "ch2")
    _mark(sd, "ch2", "DRAFTED")
    assert _gate(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch2", "REVIEWED") == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["last_gate"] == "PASS"  # 审查收口不抹门凭据
    assert _confirm(sd, "ch2", "要点") == progress.EXIT_OK
    assert "降档豁免" not in capsys.readouterr().out


def test_confirm_with_fail_credential_requires_downgrade(tmp_path, monkeypatch, capsys):
    """REVIEWED 章新门 FAIL → 确认被拒；approve-downgrade 显式豁免后放行（bug-4146 豁免通道）。"""
    sd = _init(tmp_path)
    _stub(monkeypatch, fail=set())
    _credentials(sd, "ch2")
    _mark(sd, "ch2", "DRAFTED")
    assert _gate(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch2", "REVIEWED") == progress.EXIT_OK
    _stub(monkeypatch, fail={"ch2"})
    assert _gate(sd, "ch2") == progress.EXIT_ERROR  # REVIEWED 状态不动，凭据翻 FAIL
    assert _doc(sd)["chapters"]["ch2"]["status"] == "REVIEWED"
    assert _doc(sd)["chapters"]["ch2"]["last_gate"] == "FAIL"
    assert _confirm(sd, "ch2") != progress.EXIT_OK
    assert "approve-downgrade" in capsys.readouterr().err
    assert _approve(sd, "ch2", note="用户接受一期深度") == progress.EXIT_OK
    assert _confirm(sd, "ch2") == progress.EXIT_OK
    assert "降档豁免" in capsys.readouterr().out
    assert _doc(sd)["chapters"]["ch2"]["status"] == "CONFIRMED"


def test_handedited_verified_without_credential_cannot_review(tmp_path, capsys):
    """手改 state 造出 VERIFIED + 无凭据 → mark REVIEWED 双保险拦截。"""
    sd = _init(tmp_path)
    doc = _doc(sd)
    doc["chapters"]["ch2"]["status"] = "VERIFIED"
    (sd / "progress.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _mark(sd, "ch2", "REVIEWED") != progress.EXIT_OK
    assert "门凭据非 PASS" in capsys.readouterr().err


# ── P0-3 双卡凭据守卫（红线 P13 脚本强制）：无计划卡/范例卡不得进写作 ──────────

def test_mark_draft_requires_plan_card(tmp_path, capsys):
    """有范例卡、无计划卡 → mark DRAFTED 拒绝（评审 P0-3 用例 1）。"""
    sd = _init(tmp_path)
    assert _choice(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_ERROR
    assert "plan_ch2.json" in capsys.readouterr().err
    assert _doc(sd)["chapters"]["ch2"]["status"] == "PENDING"  # 账不动


def test_mark_draft_requires_fragment_choice(tmp_path, capsys):
    """有计划卡、无范例卡 → mark DRAFTED 拒绝（评审 P0-3 用例 2）。"""
    sd = _init(tmp_path)
    assert _plan(sd, "ch2") == progress.EXIT_OK
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_ERROR
    assert "fragment_choice_ch2.json" in capsys.readouterr().err
    assert _doc(sd)["chapters"]["ch2"]["status"] == "PENDING"


def test_none_choice_is_valid_waiver(tmp_path, monkeypatch):
    """--none 显式不用范例同样落账 → 凭据在位放行（评审 P0-3 用例 3：合法豁免非绕过）。"""
    sd = _init(tmp_path)
    _stub(monkeypatch, fail=set())
    assert _plan(sd, "ch2") == progress.EXIT_OK
    assert _choice(sd, "ch2", none=True) == progress.EXIT_OK
    assert (sd / "fragment_choice_ch2.json").exists()
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["status"] == "DRAFTED"


def test_gate_rejects_missing_credentials_then_passes_after_backfill(tmp_path, monkeypatch, capsys):
    """绕过 mark 直接跑门同样被拦（P0-3 第 2 条）；补卡后重试通过（幂等覆盖）。"""
    _stub(monkeypatch, fail=set())
    sd = _init(tmp_path)
    _credentials(sd, "ch3")  # ch3 有卡，ch2 无——乱序态整批拒
    assert _mark(sd, "ch3", "DRAFTED") == progress.EXIT_OK
    assert _gate(sd, "ch2,ch3") == progress.EXIT_ERROR
    err = capsys.readouterr().err
    assert "plan_ch2.json" in err and "红线 P13" in err
    _credentials(sd, "ch2")
    assert _mark(sd, "ch2", "DRAFTED") == progress.EXIT_OK
    assert _gate(sd, "ch2,ch3") == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["status"] == "VERIFIED"


def test_full_mode_mark_draft_needs_no_cards(tmp_path):
    """full 批量管线无计划卡契约——mode 非 chapter 不做双卡校验（回归保障）。"""
    (tmp_path / "data").mkdir()
    stage = tmp_path / "stage.json"
    stage.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    sd = tmp_path / "state"
    assert progress.cmd_init(
        Namespace(stage=str(stage), state_dir=str(sd), data_dir=str(tmp_path / "data"), mode="full")
    ) == progress.EXIT_OK
    assert progress.cmd_mark(
        Namespace(chapter="ch2", status="DRAFTED", sections=None, state_dir=str(sd), gate=None, detail="")
    ) == progress.EXIT_OK
    assert _doc(sd)["chapters"]["ch2"]["status"] == "DRAFTED"
