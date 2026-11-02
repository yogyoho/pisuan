"""导出物化运行时传播的单测：重播/内容跳过/残留清理（隔离 tmp 根，不触真实运行栈）。"""

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
