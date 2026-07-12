"""Test _auto_present_artifacts: scan outputs dir and register .md files as artifacts."""

from yuxi.agents.base import _auto_present_artifacts


def test_auto_present_artifacts_scans_md_files(tmp_path, monkeypatch):
    """Non-internal .md files in outputs are returned as virtual paths."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "report.md").write_text("# Report", encoding="utf-8")
    (outputs / "chapter1.md").write_text("content", encoding="utf-8")

    monkeypatch.setattr(
        "yuxi.agents.backends.sandbox.paths.sandbox_outputs_dir",
        lambda thread_id: outputs,
    )

    result = _auto_present_artifacts("t1", "u1")
    assert "/home/gem/user-data/outputs/chapter1.md" in result
    assert "/home/gem/user-data/outputs/report.md" in result


def test_auto_present_artifacts_skips_internal_dirs(tmp_path, monkeypatch):
    """Files in conversation_history / large_tool_results are excluded."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "report.md").write_text("# Report", encoding="utf-8")
    internal = outputs / "conversation_history"
    internal.mkdir()
    (internal / "secret.md").write_text("hidden", encoding="utf-8")

    monkeypatch.setattr(
        "yuxi.agents.backends.sandbox.paths.sandbox_outputs_dir",
        lambda thread_id: outputs,
    )

    result = _auto_present_artifacts("t1", "u1")
    assert "/home/gem/user-data/outputs/report.md" in result
    assert all("conversation_history" not in p for p in result)


def test_auto_present_artifacts_merges_existing(tmp_path, monkeypatch):
    """Already-present artifact paths are preserved, new ones added."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "new.md").write_text("new", encoding="utf-8")

    monkeypatch.setattr(
        "yuxi.agents.backends.sandbox.paths.sandbox_outputs_dir",
        lambda thread_id: outputs,
    )

    existing = ["/home/gem/user-data/outputs/old.md"]
    result = _auto_present_artifacts("t1", "u1", existing)
    assert "/home/gem/user-data/outputs/old.md" in result
    assert "/home/gem/user-data/outputs/new.md" in result


def test_auto_present_artifacts_no_outputs_dir(tmp_path, monkeypatch):
    """When outputs dir doesn't exist, returns existing list unchanged."""
    monkeypatch.setattr(
        "yuxi.agents.backends.sandbox.paths.sandbox_outputs_dir",
        lambda thread_id: tmp_path / "nonexistent",
    )
    result = _auto_present_artifacts("t1", "u1", ["/home/gem/user-data/outputs/old.md"])
    assert result == ["/home/gem/user-data/outputs/old.md"]
