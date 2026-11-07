"""eia_refs_git 单测：真 git 于用例自建临时仓（非 mock subprocess，覆盖 add/status/commit/push 全链）。

push 用本地 bare 仓充当远端（URL 无 :// 前缀，authed 注入退化为原路径，正好复用生产代码路径）。
幂等语义：同字节重导出 → 无 commit；显性失败：工作树非 git 仓 / 文件越出 references 树。
"""

import subprocess
from pathlib import Path

import pytest

from pisuan.services.eia_refs_git import commit_refs_export


def _git(cwd: Path | str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _git_out(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _init_worktree(tmp: Path, name: str = "worktree") -> Path:
    """模拟宿主播种产物：git init + 首个 seed commit（references 扁平布局）。"""
    wt = tmp / name
    wt.mkdir()
    _git(wt, "init", "-b", "main")
    (wt / "stages").mkdir()
    (wt / "stages" / "planning_eia.json").write_text("{}\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "-c", "user.name=seeder", "-c", "user.email=s@x", "commit", "-m", "seed")
    return wt


def _export_src(tmp: Path, content: str = '{"k": 1}\n') -> Path:
    """构造一个 _SKILL_ROOT 风格的源文件绝对路径（…/references/stages/planning_eia.json）。"""
    src = tmp / "skill" / "references" / "stages" / "planning_eia.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content, encoding="utf-8")
    return src


@pytest.fixture()
def worktree(tmp_path, monkeypatch):
    wt = _init_worktree(tmp_path)
    monkeypatch.setenv("REFS_REPO_WORKTREE", str(wt))
    monkeypatch.delenv("REFS_GITEA_PUSH_URL", raising=False)
    return wt


# ── 未启用链 ──


def test_env_unset_skips_git_chain(tmp_path, monkeypatch):
    monkeypatch.delenv("REFS_REPO_WORKTREE", raising=False)
    src = _export_src(tmp_path)
    assert commit_refs_export([src], "export: x") is None  # 不抛不写，导出行为与批次2 前一致


def test_worktree_not_git_repo_raises(tmp_path, monkeypatch):
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    monkeypatch.setenv("REFS_REPO_WORKTREE", str(bare))
    src = _export_src(tmp_path)
    with pytest.raises(RuntimeError, match="refs_repo_seed"):
        commit_refs_export([src], "export: x")


def test_file_outside_references_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("REFS_REPO_WORKTREE", str(_init_worktree(tmp_path)))
    outside = tmp_path / "elsewhere" / "a.json"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="references"):
        commit_refs_export([outside], "export: x")


# ── commit 链 ──


def test_commit_copies_bytes_and_commits(worktree, tmp_path):
    src = _export_src(tmp_path, '{"added": true}')
    sha = commit_refs_export([src], "export: stages 口径字段 +1 add（by tester）")
    assert sha
    assert (worktree / "stages" / "planning_eia.json").read_text(encoding="utf-8") == '{"added": true}'
    log = _git_out(worktree, "log", "-1", "--format=%s%n%an")
    assert "export: stages 口径字段 +1 add（by tester）" in log
    assert "pisuan-refs-bot" in log  # 身份按次注入，不依赖 .git/config


def test_idempotent_same_bytes_no_second_commit(worktree, tmp_path):
    src = _export_src(tmp_path, '{"added": true}')
    assert commit_refs_export([src], "export: 首次")
    assert commit_refs_export([src], "export: 重复导出") is None  # 无字节差异 → 不 commit
    assert _git_out(worktree, "rev-list", "--count", "HEAD") == "2"  # seed + 首次


# ── push 链（本地 bare 仓端到端）──


def test_push_to_remote_updates_bare(tmp_path, monkeypatch):
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    wt = _init_worktree(tmp_path, "wt-push")
    monkeypatch.setenv("REFS_REPO_WORKTREE", str(wt))
    monkeypatch.setenv("REFS_GITEA_PUSH_URL", str(bare))
    monkeypatch.setenv("GITEA_REFS_USER", "refsadmin")
    monkeypatch.setenv("GITEA_REFS_PASSWORD", "pw-not-real")
    src = _export_src(tmp_path, '{"pushed": 1}')
    sha = commit_refs_export([src], "export: 词表 6 条（by tester）")
    assert sha
    assert _git_out(bare, "rev-parse", "--short=12", "refs/heads/main") == sha  # bare 已达工作树 HEAD


def test_push_creds_incomplete_falls_back_to_local_commit(worktree, tmp_path, monkeypatch):
    monkeypatch.setenv("REFS_GITEA_PUSH_URL", "http://127.0.0.1:9/refsadmin/eia-refs.git")
    monkeypatch.setenv("GITEA_REFS_USER", "refsadmin")
    monkeypatch.delenv("GITEA_REFS_PASSWORD", raising=False)  # 缺密码 → 仅本地 commit，不抛
    src = _export_src(tmp_path)
    sha = commit_refs_export([src], "export: 本地兜底")
    assert sha  # commit 已成，push 缺件仅日志说明
