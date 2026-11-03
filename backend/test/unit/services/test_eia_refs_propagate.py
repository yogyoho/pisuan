"""导出物化运行时传播的单测：重播/内容跳过/残留清理/bank 输出家族双包镜像（隔离 tmp 根，不触真实运行栈）。"""

import pytest
from yuxi.services import eia_refs_propagate as prop

pytestmark = [pytest.mark.unit]


def _mk_skill(src_root, slug: str, content: str = "v1"):
    d = src_root / slug
    (d / "references").mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: x\nversion: 1.0.0\n---\n\n# {slug}\n", encoding="utf-8"
    )
    (d / "references" / "a.json").write_text(content, encoding="utf-8")
    return d


@pytest.fixture()
def fake_env(tmp_path, monkeypatch):
    """隔离的 shared 根与栈包源根。"""
    shared = tmp_path / "shared"
    shared.mkdir()
    src_root = tmp_path / "builtin"
    src_root.mkdir()
    monkeypatch.setattr(prop, "get_skills_root_dir", lambda: shared)
    return shared, src_root


def _patch_specs(monkeypatch, src_root, slugs):
    monkeypatch.setattr(
        prop,
        "list_builtin_skill_specs",
        lambda: [{"slug": s, "source_dir": src_root / s} for s in slugs],
    )


def test_propagate_copies_then_skips_unchanged(fake_env, monkeypatch):
    shared, src_root = fake_env
    _mk_skill(src_root, "s-a")
    _patch_specs(monkeypatch, src_root, ["s-a"])

    r1 = prop.propagate_refs_export()
    assert r1["propagated"] == ["s-a"]
    assert (shared / "s-a" / "references" / "a.json").read_text(encoding="utf-8") == "v1"

    # 内容未变 → skill_dirs_equal 跳过，不再整树复制
    r2 = prop.propagate_refs_export()
    assert r2["propagated"] == []


def test_propagate_replays_on_content_change(fake_env, monkeypatch):
    shared, src_root = fake_env
    _mk_skill(src_root, "s-a", "v1")
    _patch_specs(monkeypatch, src_root, ["s-a"])
    prop.propagate_refs_export()

    _mk_skill(src_root, "s-a", "v2")
    r = prop.propagate_refs_export()
    assert r["propagated"] == ["s-a"]
    assert (shared / "s-a" / "references" / "a.json").read_text(encoding="utf-8") == "v2"


def test_propagate_cleans_interrupted_residue(fake_env, monkeypatch):
    shared, src_root = fake_env
    _mk_skill(src_root, "s-a")
    _patch_specs(monkeypatch, src_root, ["s-a"])
    residue = shared / ".s-a.tmp-deadbeef"
    residue.mkdir()
    (residue / "junk").write_text("x", encoding="utf-8")

    prop.propagate_refs_export()
    assert not residue.exists()
    assert (shared / "s-a" / "references" / "a.json").is_file()


# ------------------------------------------------- bank 输出家族双包镜像（bug-4206）

_BANK_DIRS = prop._BANK_OUTPUT_DIRS


def _mk_bank_output(skill_dir, depth_value: str = "1") -> None:
    """writer 侧 bank 输出家族样例（四目录各一文件，内容可参数化）。"""
    refs = skill_dir / "references"
    for p in ("depth_targets", "samples/planning_eia", "samples_bank", "section_expectations"):
        (refs / p).mkdir(parents=True, exist_ok=True)
    (refs / "depth_targets" / "planning_eia.json").write_text(f'{{"floor": {depth_value}}}', encoding="utf-8")
    (refs / "samples" / "planning_eia" / "ch1__r1.md").write_text("sl3", encoding="utf-8")
    (refs / "samples_bank" / "bank_index.json").write_text("{}", encoding="utf-8")
    (refs / "section_expectations" / "planning_eia.json").write_text("[]", encoding="utf-8")


def test_mirror_feeds_chapter_then_shared_replay(fake_env, monkeypatch):
    """传播后双包栈内一致 + shared chapter 同步跟上（一个接线点，两条路径都收敛）。"""
    shared, src_root = fake_env
    _mk_skill(src_root, prop._WRITER_SLUG)
    _mk_skill(src_root, prop._CHAPTER_SLUG)
    _mk_bank_output(src_root / prop._WRITER_SLUG)
    _patch_specs(monkeypatch, src_root, [prop._WRITER_SLUG, prop._CHAPTER_SLUG])

    r = prop.propagate_refs_export()
    assert sorted(r["mirrored"]) == sorted(_BANK_DIRS)
    ch_refs = src_root / prop._CHAPTER_SLUG / "references"
    for d in _BANK_DIRS:
        assert (ch_refs / d).is_dir(), d
    assert (ch_refs / "depth_targets" / "planning_eia.json").read_text(encoding="utf-8") == '{"floor": 1}'
    # shared 重播携带收敛后的 chapter（传播在同一调用内完成）
    assert (shared / prop._CHAPTER_SLUG / "references" / "samples_bank" / "bank_index.json").is_file()

    # 二次传播：内容未变全跳过（镜像与重播双 skip）
    r2 = prop.propagate_refs_export()
    assert r2["mirrored"] == [] and r2["propagated"] == []


def test_mirror_prunes_stale_keeps_chapter_only_assets(fake_env, monkeypatch):
    """chapter 残留旧切片随镜像清除；chapter 独有静态资产（镜像射程外）原样保留。"""
    shared, src_root = fake_env
    w, c = _mk_skill(src_root, prop._WRITER_SLUG), _mk_skill(src_root, prop._CHAPTER_SLUG)
    _mk_bank_output(w)
    ch_refs = c / "references"
    stale_dir = ch_refs / "samples" / "old_eia"  # writer 没有的 stage：整目录替换后必须消失
    stale_dir.mkdir(parents=True)
    (stale_dir / "ch1__stale.md").write_text("stale", encoding="utf-8")
    (ch_refs / "stages").mkdir()
    (ch_refs / "stages" / "planning_eia.json").write_text("{}", encoding="utf-8")  # chapter 独有
    _patch_specs(monkeypatch, src_root, [prop._WRITER_SLUG, prop._CHAPTER_SLUG])

    prop.propagate_refs_export()
    assert not (ch_refs / "samples" / "old_eia" / "ch1__stale.md").exists()
    assert (ch_refs / "stages" / "planning_eia.json").read_text(encoding="utf-8") == "{}"
    assert (ch_refs / "samples" / "planning_eia" / "ch1__r1.md").exists()


def test_mirror_noop_without_chapter_or_bank(fake_env, monkeypatch):
    """chapter 未安装 / writer 尚无 bank 输出（首次编译前）→ 空镜像不报错。"""
    shared, src_root = fake_env
    _mk_skill(src_root, prop._WRITER_SLUG)  # 只有 writer
    _patch_specs(monkeypatch, src_root, [prop._WRITER_SLUG])
    assert prop.propagate_refs_export()["mirrored"] == []

    # chapter 在场但 writer 无 bank 输出（首次编译前）→ 跳过不误伤
    _mk_skill(src_root, prop._CHAPTER_SLUG)
    _mk_bank_output(src_root / prop._CHAPTER_SLUG)  # chapter 自带旧产物，writer 没有
    r = prop.propagate_refs_export()
    assert r["mirrored"] == []
    assert (src_root / prop._CHAPTER_SLUG / "references" / "samples_bank" / "bank_index.json").exists()


def test_mirror_cleans_in_references_residue(fake_env, monkeypatch):
    """references 内的中断残留（skills_root 级清理够不到的 .{name}.tmp-）随镜像清扫。"""
    shared, src_root = fake_env
    w, c = _mk_skill(src_root, prop._WRITER_SLUG), _mk_skill(src_root, prop._CHAPTER_SLUG)
    _mk_bank_output(w)
    residue = c / "references" / ".depth_targets.tmp-deadbeef"
    residue.mkdir()
    (residue / "junk").write_text("x", encoding="utf-8")
    _patch_specs(monkeypatch, src_root, [prop._WRITER_SLUG, prop._CHAPTER_SLUG])

    prop.propagate_refs_export()
    assert not residue.exists()
