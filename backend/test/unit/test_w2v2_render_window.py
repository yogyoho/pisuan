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


def _mini_layers(anchors: dict[str, str] | None):
    """合成三层：3 canonical 章 + N optional 章。None=单无锚附加章；dict=章名→insert_after。"""
    chapters = {
        t: {"slot_id": f"CH{i}", "aliases": [], "sections": [], "key_elements": [], "writing_patterns": []}
        for i, t in enumerate(["甲章", "乙章", "丙章"], 1)
    }
    names = list(anchors) if anchors else ["附加章"]
    optional_chapters = {}
    for i, name in enumerate(names, 1):
        opt = {"slot_id": f"OPT_{i}", "aliases": [], "sections": [], "key_elements": [], "writing_patterns": []}
        if anchors:
            opt["insert_after"] = anchors[name]
        optional_chapters[name] = opt
    l1 = {"canonical_order": ["甲章", "乙章", "丙章"], "chapters": chapters, "optional_chapters": optional_chapters}
    return {"planning_eia": {"l1": l1, "l3": {}}, "rules": [{"id": "RA", "when": {}, "add": names}]}


def test_anchor_missing_fails_loud():
    rrs = _load_renderer()
    with pytest.raises(KeyError, match="锚章不在渲染集"):
        rrs.render({"report_family": "planning_eia"}, _mini_layers({"附加章": "不存在的章"}))


def test_no_anchor_appends_tail():
    """无锚词条维持旧行为（尾部追加），向后兼容。"""
    rrs = _load_renderer()
    rendered = rrs.render({"report_family": "planning_eia"}, _mini_layers(None))
    assert _titles(rendered)[-1] == "附加章"


def test_same_anchor_stable_order():
    """同锚两章按 l1 声明序稳定落位（spec §4.1，不抛链不收敛）。"""
    rrs = _load_renderer()
    layers = _mini_layers({"附加甲": "乙章", "附加乙": "乙章"})
    layers["rules"] = [{"id": "RA", "when": {}, "add": ["附加甲", "附加乙"]}]
    layers["rules"][0]["add"] = ["附加乙", "附加甲"]  # 逆序 add——稳定序须仍按 l1 声明序
    rendered = rrs.render({"report_family": "planning_eia"}, layers)
    ts = _titles(rendered)
    assert ts == ["甲章", "乙章", "附加甲", "附加乙", "丙章"]


# ---- 顶层 stage/std_ref（Task 2）----


def test_stage_meta_derives_by_mine_type():
    """project 族按矿型拼 stage_id，其余族直用 family；字段从真源逐字可读。"""
    rrs = _load_renderer()
    assert rrs._stage_meta({"mine_type": "openpit"}, "project_eia")["stage_id"] == "project_eia_openpit"
    assert rrs._stage_meta({"mine_type": "underground"}, "project_eia")["stage_id"] == "project_eia_underground"
    meta = rrs._stage_meta({}, "planning_eia")
    assert meta["stage_id"] == "planning_eia"
    assert meta["stage"] and meta["std_ref"]  # 真源非空


def test_stage_meta_missing_stage_fails_loud():
    rrs = _load_renderer()
    with pytest.raises(FileNotFoundError, match="真源不存在"):
        rrs._stage_meta({"mine_type": "nonexistent"}, "project_eia")


def test_rendered_top_level_fields():
    """渲染产物顶层三件套非空且 stage_id 为真值（不再用 family 冒充）。"""
    rrs = _load_renderer()
    rendered = rrs.render({"report_family": "project_eia", "mine_type": "openpit"}, rrs.load_layers())
    assert rendered["stage_id"] == "project_eia_openpit"
    assert rendered["stage"]
    assert rendered["std_ref"]
