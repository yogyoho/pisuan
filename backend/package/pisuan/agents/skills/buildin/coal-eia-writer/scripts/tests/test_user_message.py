"""话术下沉测试（评审 P3-10）：next/gate/confirm-chapter 输出 USER_MESSAGE 成文中文话术。

- next 全分支（full 7 态 + chapter 8 态）输出含 USER_MESSAGE 行
- 话术零机制词（banlist 回归锁定——SKILL.md 禁用词清单删除后约束由测试承担）
- gate PASS/FAIL 话术含章名与差距首句；confirm-chapter 含下一章预告
- 旧 state（init 无章 title）退化「第N章」不崩
"""

import io
import json
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress


def _capture(fn, *a) -> tuple[int, str, str]:
    so, se = io.StringIO(), io.StringIO()
    with redirect_stdout(so), redirect_stderr(se):
        rc = fn(*a)
    return rc, so.getvalue(), se.getvalue()

# banlist（原 SKILL.md 禁用词清单，现为测试承担）——USER_MESSAGE 行禁出现
BANLIST = [
    "BLOCKED", "DRAFTED", "VERIFIED", "gate", "派发", "额度", "折算", "地板", "冻结",
    "落盘", "收口", "记账", "落账", "降档", "裁决", "协商单", "回环",
]

STAGE_TITLED = {
    "chapters": {
        "ch2": {
            "title": "规划方案概况及分析",
            "sections": [{"id": "ch2_S01", "title": "总则"}, {"id": "ch2_S02", "title": "规划概述"}],
        },
        "ch3": {"title": "现状调查与评价", "sections": [{"id": "ch3_S01", "title": "现状调查"}]},
    }
}
STAGE_PLAIN = {"chapters": {k: {s: v[s] for s in v if s != "title"} for k, v in STAGE_TITLED["chapters"].items()}}


def _init(tmp: Path, mode: str = "chapter", stage_data=STAGE_TITLED) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    stage = tmp / "stage.json"
    stage.write_text(json.dumps(stage_data, ensure_ascii=False), encoding="utf-8")
    ns = Namespace(stage=str(stage), state_dir=str(tmp / "state"), data_dir=str(tmp / "data"), mode=mode)
    rc = progress.cmd_init(ns)
    assert rc == progress.EXIT_OK
    return tmp / "state"


def _capture(fn, *a) -> tuple[int, str, str]:
    so, se = io.StringIO(), io.StringIO()
    with redirect_stdout(so), redirect_stderr(se):
        rc = fn(*a)
    return rc, so.getvalue(), se.getvalue()


def _user_messages(out: str) -> list[str]:
    return [ln[len("USER_MESSAGE: "):] for ln in out.splitlines() if ln.startswith("USER_MESSAGE: ")]


def _plan(sd: Path, ch: str = "ch2") -> None:
    card = sd.parent / f"card_{ch}.md"
    card.write_text(f"# 计划卡 {ch}", encoding="utf-8")
    ns = Namespace(chapter=ch, summary_file=str(card), notes="", depth="full", target=None, state_dir=str(sd))
    rc, _, _ = _capture(progress.cmd_plan_confirm, ns)
    assert rc == progress.EXIT_OK


def _choice(sd: Path, ch: str = "ch2", report_id: str | None = None, none: bool = False) -> None:
    ns = Namespace(chapter=ch, report_id=report_id, none=none, state_dir=str(sd))
    rc, _, _ = _capture(progress.cmd_fragment_choice, ns)
    assert rc == progress.EXIT_OK


def _set(sd: Path, ch: str, **kw) -> None:
    p = sd / "progress.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["chapters"][ch].update(kw)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _assert_um(out: str, *fragments: str) -> str:
    ums = _user_messages(out)
    assert len(ums) == 1, f"期望恰好一条 USER_MESSAGE，得到 {len(ums)}: {ums}"
    for frag in fragments:
        assert frag in ums[0], f"话术缺「{frag}」: {ums[0]}"
    for w in BANLIST:
        assert w not in ums[0], f"话术含机制词「{w}」: {ums[0]}"
    return ums[0]


# ------------------------------------------------------- chapter 模式 next 各态


def test_chapter_collecting_no_plan(tmp_path):
    sd = _init(tmp_path)
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "编写计划已拟好", "第2章「规划方案概况及分析」", "确认")


def test_chapter_collecting_plan_no_choice(tmp_path):
    sd = _init(tmp_path)
    _plan(sd)
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "正在收集", "挑选参考范例")


def test_chapter_collecting_with_choice(tmp_path):
    sd = _init(tmp_path)
    _plan(sd)
    _choice(sd, report_id="038-2024-7-9")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "正在组织编写", "选定的范例为参照")


def test_chapter_collecting_choice_none(tmp_path):
    sd = _init(tmp_path)
    _plan(sd)
    _choice(sd, none=True)
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "正在组织编写", "不使用参考范例")


def test_chapter_gate_review_confirm_phases(tmp_path):
    sd = _init(tmp_path)
    _plan(sd)
    _choice(sd, none=True)
    _set(sd, "ch2", status="DRAFTED")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "已编写完成，正在质量校验")  # DRAFTED→GATE
    _set(sd, "ch2", status="VERIFIED")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "已通过质量校验", "章内审查")  # VERIFIED→REVIEW
    _set(sd, "ch2", status="REVIEWED", last_gate="PASS")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "请您过目章稿", "进入下一章")  # REVIEWED→CONFIRM


def test_chapter_negotiate_and_final(tmp_path):
    sd = _init(tmp_path)
    _set(sd, "ch2", status="BLOCKED", blocked_reason="产能缺口")
    _set(sd, "ch3", status="CONFIRMED")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "需要您拿主意", "补充资料", "按当前成稿收尾")
    sd2 = _init(tmp_path / "final")
    for c in ("ch2", "ch3"):
        _set(sd2, c, status="CONFIRMED")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd2)))
    _assert_um(out, "全部章节已确认", "汇总成稿")


def test_plain_stage_degrades_to_ordinal(tmp_path):
    """旧 state（init 无章 title）话术退化「第2章」。"""
    sd = _init(tmp_path, stage_data=STAGE_PLAIN)
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    um = _assert_um(out, "第2章")
    assert "「" not in um  # 无章名不得出现空书名号


# ------------------------------------------------------- full 模式 next 各态


def test_full_wave1_dispatch_and_gate(tmp_path):
    sd = _init(tmp_path, mode="full")  # full 缺省不写 mode 键
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "正在组织编写第2章", "共 2 节", "无需您操作")  # wave1=[ch2] PENDING
    _set(sd, "ch2", status="DRAFTED")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "第2章「规划方案概况及分析」已编写完成", "质量校验")


def test_full_budget_exhausted(tmp_path):
    sd = _init(tmp_path, mode="full")
    p = sd / "progress.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["total_dispatches"] = progress.DISPATCH_BUDGET
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "上限", "进度已保存")


def test_full_negotiate_key_points_wave2_final(tmp_path):
    sd = _init(tmp_path, mode="full")
    _set(sd, "ch2", status="VERIFIED", last_gate="PASS")
    _set(sd, "ch3", status="BLOCKED", blocked_reason="差距")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "需要您拿主意")
    _set(sd, "ch3", status="VERIFIED", last_gate="PASS")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "要点已汇总", "请您过目确认")  # KEY_POINTS
    doc = json.loads((sd / "progress.json").read_text(encoding="utf-8"))
    doc["key_points_confirmed"] = True
    (sd / "progress.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    _set(sd, "ch3", status="PENDING")  # wave2 结论章待编写
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "正在生成结论章")  # WAVE2 ch3 PENDING
    _set(sd, "ch3", status="DRAFTED")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "结论章", "正在质量校验")
    _set(sd, "ch3", status="VERIFIED", last_gate="PASS")
    rc, out, _ = _capture(progress.cmd_next, Namespace(state_dir=str(sd)))
    _assert_um(out, "全部章节校验通过", "汇总成稿", "交付")  # FINAL clean


# ------------------------------------------------------- gate 与 confirm-chapter


@pytest.fixture()
def gate_env(tmp_path, monkeypatch):
    import build_output

    sd = _init(tmp_path, mode="chapter")
    _plan(sd)
    _choice(sd, none=True)
    _set(sd, "ch2", status="DRAFTED")
    monkeypatch.setattr(build_output, "resolve_targets", lambda *a, **k: ({}, ""))
    return sd, build_output


def test_gate_user_message_pass_and_fail(gate_env, monkeypatch):
    sd, build_output = gate_env
    monkeypatch.setattr(build_output, "run_chapter_gate", lambda *a, **k: None)
    rc, out, _ = _capture(progress.cmd_gate, Namespace(state_dir=str(sd), chapters="ch2", targets=None))
    assert rc == progress.EXIT_OK
    assert "USER_MESSAGE: 第2章「规划方案概况及分析」质量校验通过。" in out

    sd2 = gate_env[0]
    _set(sd2, "ch2", status="DRAFTED")  # 复跑：VERIFIED→DRAFTED

    def _boom(*a, **k):
        raise ValueError("第2节 产能缺口 20%: 登记值 8.0 vs 目标 10.0")

    monkeypatch.setattr(build_output, "run_chapter_gate", _boom)
    rc, out, err = _capture(progress.cmd_gate, Namespace(state_dir=str(sd2), chapters="ch2", targets=None))
    assert rc == progress.EXIT_ERROR
    um = [ln for ln in out.splitlines() if ln.startswith("USER_MESSAGE: ")]
    assert len(um) == 1 and "质量校验未通过" in um[0] and "产能缺口 20%" in um[0]
    assert "无需您操作" in um[0]


def test_confirm_chapter_user_message(tmp_path):
    sd = _init(tmp_path)
    _plan(sd)
    _choice(sd, none=True)
    _set(sd, "ch2", status="REVIEWED", last_gate="PASS")
    _set(sd, "ch3", status="REVIEWED", last_gate="PASS")
    ns = Namespace(chapter="ch2", highlights="要点1|要点2", state_dir=str(sd))
    rc, out, _ = _capture(progress.cmd_confirm_chapter, ns)
    assert rc == progress.EXIT_OK
    expect = "USER_MESSAGE: 第2章「规划方案概况及分析」已确认登记。下一章第3章「现状调查与评价」即将开始编写。"
    assert expect in out
    rc, out, _ = _capture(progress.cmd_confirm_chapter, Namespace(chapter="ch3", highlights="要点", state_dir=str(sd)))
    assert rc == progress.EXIT_OK
    assert "全部章节确认完毕，即将汇总成稿" in out
