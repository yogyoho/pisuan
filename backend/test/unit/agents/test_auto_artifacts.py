"""Test _auto_present_artifacts: 扫描 Workdir outputs 并登记 .md 交付物。"""

from types import SimpleNamespace

from pisuan.agents.backends.paths import VIRTUAL_PATH_PREFIX
from pisuan.agents.base import _auto_present_artifacts


def _context(uid="u1", workdir="projects/w1"):
    return SimpleNamespace(uid=uid, workdir_relative_path=workdir, thread_id="t1")


def _make_outputs(tmp_path, monkeypatch, uid="u1", workdir="projects/w1"):
    """建出真实 Workdir outputs 目录并把用户数据根指到 tmp。"""
    root = tmp_path / "user-data"
    outputs = root / "shared" / uid / "workspace" / workdir / "outputs"
    outputs.mkdir(parents=True)
    monkeypatch.setattr("pisuan.workspace.paths.get_user_data_dir", lambda: root)
    return outputs


def test_auto_present_artifacts_scans_md_files(tmp_path, monkeypatch):
    """outputs 下的 .md 文件以 runtime 虚拟路径返回。"""
    outputs = _make_outputs(tmp_path, monkeypatch)
    (outputs / "report.md").write_text("# Report", encoding="utf-8")
    (outputs / "chapter1.md").write_text("content", encoding="utf-8")

    result = _auto_present_artifacts(_context())
    assert f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/chapter1.md" in result
    assert f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/report.md" in result


def test_auto_present_artifacts_skips_internal_dirs(tmp_path, monkeypatch):
    """conversation_history / large_tool_results 下的文件被排除。"""
    outputs = _make_outputs(tmp_path, monkeypatch)
    (outputs / "report.md").write_text("# Report", encoding="utf-8")
    internal = outputs / "conversation_history"
    internal.mkdir()
    (internal / "secret.md").write_text("hidden", encoding="utf-8")

    result = _auto_present_artifacts(_context())
    assert f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/report.md" in result
    assert all("conversation_history" not in p for p in result)


def test_auto_present_artifacts_merges_existing(tmp_path, monkeypatch):
    """已有交付物保留，新产物追加。"""
    outputs = _make_outputs(tmp_path, monkeypatch)
    (outputs / "new.md").write_text("new", encoding="utf-8")

    existing = [f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/old.md"]
    result = _auto_present_artifacts(_context(), existing)
    assert f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/old.md" in result
    assert f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/new.md" in result


def test_auto_present_artifacts_without_workdir(tmp_path, monkeypatch):
    """无 Workdir 的会话（普通聊天）没有 outputs 概念，原样返回 existing。"""
    existing = [f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/old.md"]
    assert _auto_present_artifacts(_context(workdir=""), existing) == existing


def test_auto_present_artifacts_missing_workdir_dir(tmp_path, monkeypatch):
    """Workdir 未落盘时安全回退到 existing。"""
    root = tmp_path / "user-data"
    root.mkdir()
    monkeypatch.setattr("pisuan.workspace.paths.get_user_data_dir", lambda: root)
    existing = [f"{VIRTUAL_PATH_PREFIX}/projects/w1/outputs/old.md"]
    assert _auto_present_artifacts(_context(), existing) == existing
