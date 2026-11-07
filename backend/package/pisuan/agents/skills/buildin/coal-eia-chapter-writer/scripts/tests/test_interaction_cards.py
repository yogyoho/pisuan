"""章节编写交互卡点测试（卡A计划卡 + 卡B范例挑选 + next 联动 + 篇幅模式）：

- plan-confirm：plan_<ch>.json 落盘（卡面+补充意见+篇幅选择）；幂等覆盖；custom 须带 --target；分章模式限定
- fragment-choice：fragment_choice_<ch>.json 落盘；--report-id 与 --none 恰好一个
- next 联动（COLLECTING）：无 plan → 只给计划卡动作（禁跳过收资料）；有 plan 无 choice → 派发前置候选卡；
  有 choice → 范例注入提示
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress

STAGE = {
    "chapters": {
        "ch2": {"sections": [{"id": "ch2_S01", "title": "总则"}, {"id": "ch2_S02", "title": "规划概述"}]},
        "ch3": {"sections": [{"id": "ch3_S01", "title": "现状调查"}]},
    }
}


def _init(tmp: Path, mode: str = "chapter") -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    stage = tmp / "stage.json"
    stage.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    rc = progress.cmd_init(Namespace(stage=str(stage), state_dir=str(tmp / "state"),
                                     data_dir=str(tmp / "data"), mode=mode))
    assert rc == progress.EXIT_OK
    return tmp / "state"


def _plan(sd: Path, ch: str = "ch2", depth: str = "full", target: int | None = None, notes: str = "") -> int:
    card = sd.parent / f"card_{ch}_{depth}.md"
    card.write_text(f"# 计划卡 {ch}\n要点…", encoding="utf-8")
    return progress.cmd_plan_confirm(Namespace(
        chapter=ch, summary_file=str(card), notes=notes, depth=depth, target=target,
        state_dir=str(sd)))


def _choice(sd: Path, ch: str = "ch2", report_id: str | None = None, none: bool = False) -> int:
    return progress.cmd_fragment_choice(Namespace(
        chapter=ch, report_id=report_id, none=none, state_dir=str(sd)))


def _next(sd: Path) -> str:
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = progress.cmd_next(Namespace(state_dir=str(sd)))
    assert rc == progress.EXIT_OK
    return buf.getvalue()


def test_plan_confirm_writes_artifact(tmp_path):
    sd = _init(tmp_path)
    rc = _plan(sd, notes="需含村庄分布", depth="custom", target=8000)
    assert rc == progress.EXIT_OK
    plan = json.loads((sd / "plan_ch2.json").read_text(encoding="utf-8"))
    assert plan["chapter"] == "ch2" and plan["notes"] == "需含村庄分布"
    assert plan["depth"] == {"mode": "custom", "target": 8000}
    assert "要点…" in plan["summary"] and plan["confirmed_at"]


def test_plan_confirm_custom_requires_target(tmp_path):
    sd = _init(tmp_path)
    rc = _plan(sd, depth="custom", target=None)
    assert rc == progress.EXIT_ERROR and not (sd / "plan_ch2.json").exists()


def test_plan_confirm_idempotent_overwrite(tmp_path):
    """修订回环：二次确认覆盖为最新版（意见+篇幅选择）。"""
    sd = _init(tmp_path)
    assert _plan(sd, notes="v1") == progress.EXIT_OK
    assert _plan(sd, notes="v2", depth="compact") == progress.EXIT_OK
    plan = json.loads((sd / "plan_ch2.json").read_text(encoding="utf-8"))
    assert plan["notes"] == "v2" and plan["depth"]["mode"] == "compact"


def test_plan_confirm_rejects_full_mode_and_unknown_ch(tmp_path):
    sd_full = _init(tmp_path / "full", mode="full")
    assert _plan(sd_full) == progress.EXIT_ERROR  # full 批量管线无计划卡
    sd = _init(tmp_path / "chapter")
    assert _plan(sd, ch="ch9") == progress.EXIT_ERROR


def test_fragment_choice_writes_and_mutex(tmp_path):
    sd = _init(tmp_path)
    assert _choice(sd, report_id="2201") == progress.EXIT_OK
    c = json.loads((sd / "fragment_choice_ch2.json").read_text(encoding="utf-8"))
    assert c["report_id"] == "2201"
    assert _choice(sd, report_id="2201", none=True) == progress.EXIT_ERROR  # 恰好一个
    assert _choice(sd, none=True) == progress.EXIT_OK
    c2 = json.loads((sd / "fragment_choice_ch2.json").read_text(encoding="utf-8"))
    assert c2["report_id"] is None


def test_next_without_plan_prompts_plan_card_only(tmp_path):
    """无 plan：next 只给计划卡动作（禁直接收资料/派发——红线 P13 前置）。"""
    sd = _init(tmp_path)
    out = _next(sd)
    assert "计划卡" in out and "plan-confirm" in out
    assert "batch_task" not in out  # 禁跳过：资料汇集动作不可见
    assert "篇幅规模" in out or "详实版" in out  # 业务语体篇幅三选提示


def test_next_with_plan_prompts_candidates(tmp_path):
    sd = _init(tmp_path)
    assert _plan(sd) == progress.EXIT_OK
    out = _next(sd)
    assert "candidates" in out and "fragment-choice" in out  # 派发前置候选卡
    assert "batch_task" in out  # 资料汇集动作恢复可见


def test_next_with_choice_notes_injection(tmp_path):
    sd = _init(tmp_path)
    assert _plan(sd) == progress.EXIT_OK
    assert _choice(sd, report_id="2201") == progress.EXIT_OK
    out = _next(sd)
    assert "2201" in out and "plan_ch2.json" in out  # 范例+计划卡注入派发契约
    assert "fragment-choice" not in out.split("范例")[0]  # 不再重复要求挑选
    assert _choice(sd, none=True) == progress.EXIT_OK
    assert "不用范例" in _next(sd)


def test_depth_mode_compact_not_enforced(tmp_path):
    """篇幅模式贯通（build_output）：compact 不拦；custom 用用户目标；无 plan 零回归。"""
    import build_output
    dm = build_output.plan_depth_mode(tmp_path, "ch2")
    assert dm is None  # 无 plan 工件 → 既有强制语义
    (tmp_path / "plan_ch2.json").write_text(
        json.dumps({"depth": {"mode": "compact", "target": None}}, ensure_ascii=False), encoding="utf-8")
    dm = build_output.plan_depth_mode(tmp_path, "ch2")
    eff, floor = build_output.validate_chapter_depth("ch2", "很短。", {"chapters": {"ch2": {"floor_chars": 1000}}}, depth_mode=dm)
    assert floor == 0  # 精简版：规则不启用
    (tmp_path / "plan_ch2.json").write_text(
        json.dumps({"depth": {"mode": "custom", "target": 50}}, ensure_ascii=False), encoding="utf-8")
    dm = build_output.plan_depth_mode(tmp_path, "ch2")
    try:
        build_output.validate_chapter_depth("ch2", "很短。", None, depth_mode=dm)
        raise AssertionError("custom 50 字应拦")
    except ValueError as e:
        assert "50" in str(e) and "用户指定" in str(e)
    eff, floor = build_output.validate_chapter_depth("ch2", "字" * 60, None, depth_mode=dm)
    assert floor == 50
    (tmp_path / "plan_ch2.json").write_text(
        json.dumps({"depth": {"mode": "bogus"}}, ensure_ascii=False), encoding="utf-8")
    try:
        build_output.plan_depth_mode(tmp_path, "ch2")
        raise AssertionError("mode 非法应报错")
    except ValueError as e:
        assert "唯一写者" in str(e)
