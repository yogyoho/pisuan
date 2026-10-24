"""范式角色分型测试：roles/<stage>.json schema + stage 全覆盖 + ch13 重归型钉死 + 解析器拒派语义。

Task 1（chapter-writer，2026-10-24）：_roles.json 单份 planning 形状目录化为
roles/<stage>.json，角色扩至六值（新增 conclusion/process），ch13 结论章重归型。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paradigm_role import LEGAL_ROLES, resolve

REFS = Path(__file__).resolve().parent.parent.parent / "references"


def _roles() -> dict:
    data = json.loads((REFS / "paradigms" / "roles" / "planning_eia.json").read_text(encoding="utf-8"))
    return data["roles"]


def _stage_section_ids() -> list[str]:
    st = json.loads((REFS / "stages" / "planning_eia.json").read_text(encoding="utf-8"))
    ids = []
    for cid, ch in st["chapters"].items():
        for i in range(1, len(ch["sections"]) + 1):
            ids.append(f"{cid}_S{i:02d}")
    return ids


def test_all_values_legal():
    """角色值必须全部在六合法值内。"""
    bad = set(_roles().values()) - LEGAL_ROLES
    assert not bad, f"非法角色值: {bad}"


def test_roles_cover_stage_sections_exactly():
    """映射必须与 stage sections 清单精确对齐（多节/少节都红）。"""
    roles = _roles()
    ids = _stage_section_ids()
    assert len(ids) == 77, f"stage 章节数漂移: {len(ids)}"
    missing = sorted(set(ids) - set(roles))
    extra = sorted(set(roles) - set(ids))
    assert not missing, f"映射缺节: {missing[:5]}"
    assert not extra, f"映射多节: {extra[:5]}"


def test_ch13_retyped_conclusion():
    """ch13 重归型钉死：S01 概况收束=baseline、S09 优化调整建议=measures、其余八节=conclusion。"""
    r = _roles()
    assert r["ch13_S01"] == "baseline"
    assert r["ch13_S09"] == "measures"
    for i in range(2, 9):
        assert r[f"ch13_S{i:02d}"] == "conclusion", f"ch13_S{i:02d} 应为 conclusion"
    assert r["ch13_S10"] == "conclusion"
    assert sum(1 for v in r.values() if v == "conclusion") >= 8, "全书 conclusion 节数不足"


def test_resolve_ok_and_rejects():
    """解析器：合法查得、未知节拒派、缺映射文件拒派。"""
    roles = _roles()
    assert resolve(REFS, "planning_eia", "ch6_S01") == roles["ch6_S01"]
    try:
        resolve(REFS, "planning_eia", "ch99_S99")
    except KeyError:
        pass
    else:
        raise AssertionError("未知节必须拒派（KeyError）")
    try:
        resolve(REFS, "no_such_stage", "ch1_S01")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("缺映射文件必须拒派（FileNotFoundError）")


def test_illegal_role_value_rejected_by_loader():
    """映射文件混入非法角色值时，加载即拒（不等到派发才炸）。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        roles_dir = Path(td) / "paradigms" / "roles"
        roles_dir.mkdir(parents=True)
        (roles_dir / "planning_eia.json").write_text(
            json.dumps({"roles": {"ch1_S01": "typo_role"}}, ensure_ascii=False), encoding="utf-8"
        )
        try:
            resolve(Path(td), "planning_eia", "ch1_S01")
        except ValueError:
            pass
        else:
            raise AssertionError("非法角色值必须加载即拒（ValueError）")


def test_new_paradigm_files_structure():
    """conclusion/process 范式文件结构与其他范式齐整（四小节齐备）。"""
    for role in ("conclusion", "process"):
        text = (REFS / "paradigms" / f"{role}.md").read_text(encoding="utf-8")
        for sec in ("## 适用", "## 结构骨架", "## 范文", "## 反模式"):
            assert sec in text, f"{role}.md 缺 {sec}"


def test_baseline_exemplar_no_banned_phrase():
    """baseline 范文不得示范 banned_phrases 首词「总体而言」（2026-10-24 文风裁定）。"""
    text = (REFS / "paradigms" / "baseline.md").read_text(encoding="utf-8")
    assert "总体而言" not in text, "baseline 范文残留 AI 腔词「总体而言」，写手会仿"
