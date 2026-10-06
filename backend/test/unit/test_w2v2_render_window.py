"""W2 v2 三条输入小窗——渲染器锚点机制 + 顶层 stage/std_ref 单测。

自包含：importlib 渲染器 + 读 repo 真源 JSON，不依赖 yuxi 包（宿主 --noconftest 可跑）。
spec: docs/superpowers/specs/2026-10-06-w2-v2-three-input-window-design.md
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
RENDERER = BACKEND / "scripts" / "render_report_skeletons.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("rrs", RENDERER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _titles(rendered: dict) -> list[str]:
    return [c["title"] for c in rendered["chapters"].values()]


# ---- 锚点机制（Task 1）----


def test_openpit_blast_anchored_after_solidwaste():
    """R2 add 爆破按 insert_after 落固废之后（非尾部）。"""
    rrs = _load_renderer()
    conds = {"report_family": "project_eia", "mine_type": "openpit"}
    rendered = rrs.render(conds, rrs.load_layers())
    ts = _titles(rendered)
    assert "爆破环境影响评价" in ts
    assert ts.index("爆破环境影响评价") == ts.index("固体废物环境影响评价") + 1
    assert "R2" in rendered["generated_from"]["applied_rules"]


def test_underground_no_blast_no_r2():
    """井工：无爆破、无 R2（基线行为不回归）。"""
    rrs = _load_renderer()
    conds = {"report_family": "project_eia", "mine_type": "underground"}
    rendered = rrs.render(conds, rrs.load_layers())
    ts = _titles(rendered)
    assert "爆破环境影响评价" not in ts
    assert "R2" not in rendered["generated_from"]["applied_rules"]


def test_revised2019_r3_chapters_anchored():
    """R3 两章按锚落位：三线一单→论证后；不确定性→环管后。"""
    rrs = _load_renderer()
    conds = {"report_family": "planning_eia", "guideline_version": "revised2019"}
    rendered = rrs.render(conds, rrs.load_layers())
    ts = _titles(rendered)
    assert ts.index("三线一单及空间管控") == ts.index("规划方案综合论证及优化调整建议") + 1
    assert ts.index("不确定性分析") == ts.index("环境管理、监测计划与跟踪评价") + 1
    assert "R3" in rendered["generated_from"]["applied_rules"]


def _mini_layers(insert_after: str | None):
    """合成三层：3 canonical 章 + 1 optional 章（可选锚）。"""
    chapters = {
        t: {"slot_id": f"CH{i}", "aliases": [], "sections": [], "key_elements": [], "writing_patterns": []}
        for i, t in enumerate(["甲章", "乙章", "丙章"], 1)
    }
    opt = {"slot_id": "OPT_9", "aliases": [], "sections": [], "key_elements": [], "writing_patterns": []}
    if insert_after:
        opt["insert_after"] = insert_after
    l1 = {"canonical_order": ["甲章", "乙章", "丙章"], "chapters": chapters, "optional_chapters": {"附加章": opt}}
    return {"planning_eia": {"l1": l1, "l3": {}}, "rules": [{"id": "RA", "when": {}, "add": ["附加章"]}]}


def test_anchor_missing_fails_loud():
    rrs = _load_renderer()
    with pytest.raises(KeyError, match="锚章不在渲染集"):
        rrs.render({"report_family": "planning_eia"}, _mini_layers("不存在的章"))


def test_no_anchor_appends_tail():
    """无锚词条维持旧行为（尾部追加），向后兼容。"""
    rrs = _load_renderer()
    rendered = rrs.render({"report_family": "planning_eia"}, _mini_layers(None))
    assert _titles(rendered)[-1] == "附加章"
