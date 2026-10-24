"""corpus_meta variant 变体标注测试：标题即判规则 + --add-variant 就地补标注零扰动。

规则（spec §3.2 / plan Task 5.4）：
- planning_eia：标题含「修编」（含全角括号变体）→ revision，否则 new
- project_eia_*：标题空缺/泛题 → needs_review（11 份）；含改扩/调整标记 → expansion；其余 → new
- post/tracking：stage 不分变体 → not_applicable
- annotations 显式 variant 优先（basis=manual）
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import corpus_meta


def test_judge_variant_rules():
    j = corpus_meta.judge_variant
    assert j("planning_eia", "横城矿区总体规划（修编）环境影响报告书") == ("revision", "标题含修编标记")
    assert j("planning_eia", "…总体规划〈修编〉环境影响报告书")[0] == "revision"
    assert j("planning_eia", "五间房矿区总体规划环境影响报告书") == ("new", "标题不含修编标记")
    assert j("project_eia_underground", None)[0] == "needs_review"
    assert j("project_eia_openpit", "环境影响报告书")[0] == "needs_review"
    assert j("project_eia_underground", "巴拉素矿井及选煤厂调整建设规模（10.0Mt/a调整至15.0Mt/a）环境影响报告书") == (
        "expansion", "标题含调整/改扩标记")
    assert j("project_eia_underground", "白岩子矿区郭家台二号煤矿项目环境影响报告书")[0] == "new"
    assert j("post_eia", None) == ("not_applicable", "post/tracking 不分变体")
    assert j("tracking_eia", "…跟踪评价报告书")[0] == "not_applicable"


def test_build_merges_manual_override(tmp_path):
    """build_corpus_meta 走 annotations 显式 variant（basis=manual）；无标注时标题即判。"""
    stage_dir = tmp_path / "planning_eia"
    (stage_dir / "slices").mkdir(parents=True)
    (stage_dir / "slices" / "r1__01.md").write_text("# 某矿区总体规划（修编）环境影响报告书\n", encoding="utf-8")
    doc = corpus_meta.build_corpus_meta(tmp_path, {"r1": {"variant": "new", "variant_basis": "人工裁定"}})
    r = doc["reports"]["r1"]
    assert r["variant"] == "new" and r["variant_basis"] == "人工裁定"
    doc2 = corpus_meta.build_corpus_meta(tmp_path, {})
    assert doc2["reports"]["r1"]["variant"] == "needs_review"  # 无封面侧车→title=None→规划报告也无法即判


def test_add_variant_real_corpus(tmp_path):
    """真实 corpus_meta 副本：33 份全部带 variant；除新增字段外字节零扰动；计数符合 plan 口径。"""
    src = Path(__file__).resolve().parent.parent.parent / "references" / "samples_bank" / "corpus_meta.json"
    target = tmp_path / "corpus_meta.json"
    raw = src.read_bytes()
    target.write_bytes(raw)

    rc = corpus_meta.add_variant(target, annotations={})
    assert rc == 0
    out = target.read_bytes()
    doc = json.loads(out.decode("utf-8"))
    reports = doc["reports"]
    assert len(reports) == 33
    assert all("variant" in r and "variant_basis" in r for r in reports.values())
    # 计数：planning 17 = revision 14 + new 3；needs_review 11；not_applicable 3（post2+tracking1）
    planning = [r for r in reports.values() if r["stage"] == "planning_eia"]
    assert sum(1 for r in planning if r["variant"] == "revision") == 14
    assert sum(1 for r in planning if r["variant"] == "new") == 3
    assert sum(1 for r in reports.values() if r["variant"] == "needs_review") == 11
    assert sum(1 for r in reports.values() if r["variant"] == "not_applicable") == 3
    # 除 variant/variant_basis 外零扰动：剥离新增键后与原文逐字节一致
    stripped = json.loads(raw.decode("utf-8"))
    for rid, r in stripped["reports"].items():
        added = {k: reports[rid][k] for k in ("variant", "variant_basis")}
        assert reports[rid] == {**r, **added}, rid
    # 幂等：重跑字节一致
    corpus_meta.add_variant(target, annotations={})
    assert target.read_bytes() == out


def test_add_variant_manual_override(tmp_path):
    """annotations 显式 variant 优先于标题即判，basis=manual。"""
    src = Path(__file__).resolve().parent.parent.parent / "references" / "samples_bank" / "corpus_meta.json"
    target = tmp_path / "corpus_meta.json"
    target.write_bytes(src.read_bytes())
    corpus_meta.add_variant(target, annotations={"003-1-2024-1-30": {"variant": "new", "variant_basis": "人工裁定"}})
    doc = json.loads(target.read_text(encoding="utf-8"))
    r = doc["reports"]["003-1-2024-1-30"]
    assert r["variant"] == "new" and r["variant_basis"] == "人工裁定"
