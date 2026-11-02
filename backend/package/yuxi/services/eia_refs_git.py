"""环评 refs 数据仓 git 链（批次2）：导出物化 → refs-repo 工作树 commit → push 本地 Gitea。

设计：docs/vibe/2026-11-01-eia-refs-local-git-chain.md。各 eia_*_service 导出动作写完
_SKILL_ROOT 真实文件后调用 commit_refs_export，把同字节抄送进 refs-repo 工作树
（refs-repo 根 = coal-eia-writer/references 的扁平镜像），commit 后 push 本地 Gitea
（refsadmin/eia-refs，唯一权威）。幂等：与工作树 HEAD 无字节差异 → 不 commit。

env（可选启用，缺省不动 git，导出行为与批次2 之前完全一致）：
- REFS_REPO_WORKTREE：工作树绝对路径（运行栈由 compose 注入 /app/refs-repo/worktree；
  宿主播种脚本默认 <栈卷>/pisuan/refs-repo/worktree）
- REFS_GITEA_PUSH_URL / GITEA_REFS_USER / GITEA_REFS_PASSWORD：push 三件套；缺失则仅本地
  commit（info 日志说明），不视为错误——宿主离线工具链可直接复用本模块。

权威 commit/push 完成后统一触发运行时传播（eia_refs_propagate.propagate_refs_export：
栈包→shared 原子重播；投影由 Agent Run 初始化自动刷）。传播仅在 git 链启用时执行——
离线复用本模块不触碰运行栈状态。

git 失败（含工作树不存在、push 被拒）一律抛 RuntimeError：文件导出已落盘成功，git 链断裂
必须显性暴露给调用方与日志，禁止静默吞掉（否则 Gitea 权威悄悄落后，对账失真）。
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

BOT_NAME, BOT_EMAIL = "pisuan-refs-bot", "refs-bot@pisuan.local"


def _git(worktree: Path, args: list[str], *, binary: bool = False) -> subprocess.CompletedProcess:
    # -c 前置（safe.directory 防跨 uid 拒认；身份按次注入，不依赖 .git/config 残留）
    return subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={worktree}",
            "-c",
            f"user.name={BOT_NAME}",
            "-c",
            f"user.email={BOT_EMAIL}",
            *args,
        ],
        cwd=worktree,
        capture_output=True,
        encoding=None if binary else "utf-8",
    )


def _worktree_rel(src: Path) -> str:
    """_SKILL_ROOT 下真实文件路径 → refs-repo 扁平相对路径（取 references/ 之后的部分）。"""
    parts = src.parts
    if "references" not in parts:
        raise RuntimeError(f"导出文件不在 references 树内，无法入 refs 仓: {src}")
    i = len(parts) - 1 - parts[::-1].index("references")
    return "/".join(parts[i + 1 :])


def commit_refs_export(files: list[Path], message: str) -> str | None:
    """把本次导出物化的文件抄送进 refs-repo 工作树并 commit（可选 push）+ 运行时传播。

    files：本次导出实际写入的 _SKILL_ROOT 下文件绝对路径（服务侧已按字节变更过滤）。
    返回 commit sha；未配置 REFS_REPO_WORKTREE 或无字节变化返回 None
    （传播仍执行：栈包内容可能领先于工作树）。
    """
    root = os.environ.get("REFS_REPO_WORKTREE", "").strip()
    if not root:
        logger.warning("[refs-git] REFS_REPO_WORKTREE 未配置，跳过 git 链与运行时传播（导出仅落技能文件）")
        return None
    worktree = Path(root)
    if not (worktree / ".git").exists():
        raise RuntimeError(f"refs-repo 工作树不是 git 仓（先跑 scripts/governance/refs_repo_seed.py）: {worktree}")

    for src in files:
        rel = _worktree_rel(src)
        dest = worktree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())

    _git(worktree, ["add", "-A"])
    sha: str | None = None
    if not _git(worktree, ["status", "--porcelain"]).stdout.strip():
        logger.info("[refs-git] 工作树与 HEAD 无字节差异，幂等跳过 commit")
    else:
        r = _git(worktree, ["commit", "-m", message])
        if r.returncode != 0:
            raise RuntimeError(f"refs-repo commit 失败:\n{r.stderr}")
        sha = _git(worktree, ["rev-parse", "--short=12", "HEAD"]).stdout.strip()

        url = os.environ.get("REFS_GITEA_PUSH_URL", "").strip()
        user = os.environ.get("GITEA_REFS_USER", "").strip()
        password = os.environ.get("GITEA_REFS_PASSWORD", "")
        if url and user and password:
            authed = url.replace("://", f"://{user}:{password}@", 1)  # 密码只进 argv，不落 .git/config
            p = _git(worktree, ["push", authed, "main:refs/heads/main"])
            if p.returncode != 0:
                raise RuntimeError(f"refs-repo push 失败（Gitea 权威落后，须人工核查）:\n{p.stderr}")
            logger.info(f"[refs-git] commit {sha} 已 push → {url}")
        else:
            logger.info(
                f"[refs-git] commit {sha} 仅本地（未配置 REFS_GITEA_PUSH_URL/GITEA_REFS_USER/GITEA_REFS_PASSWORD 全套）"
            )

    # 运行时传播（栈包→shared 重播；投影由 Agent Run 初始化自动刷）。
    # 权威链完成后执行，失败抛错显性暴露——导出幂等，重试导出即可自愈。
    from yuxi.services.eia_refs_propagate import propagate_refs_export  # 局部导入：离线路径零开销，避免 skills 依赖环

    propagate_refs_export()
    return sha
