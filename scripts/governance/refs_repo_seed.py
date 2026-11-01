"""refs 数据仓播种：pisuan-custom committed refs → refs-repo 工作树 → push 本地 Gitea。

设计：docs/vibe/2026-11-01-eia-refs-local-git-chain.md 批次 2。refs-repo 卷（host 侧
docker/volumes/pisuan/refs-repo/worktree）是导出链的写手工作树；唯一权威 = 本地 Gitea
（refsadmin/eia-refs）。本脚本从仓库 **已提交** 的技能 refs 播种（不读工作树，避免未提交
漂移混入），幂等可重跑：字节无变化则不 commit 不 push。

入仓清单（相对 coal-eia-writer/references/，refs-repo 根 = references 根的扁平镜像）：
    stages/*.json、standards_index.json、paradigms/*.md + forms_catalog.json、
    sample_entities/、formulas.json、samples_bank/corpus_meta_annotations.json、
    overrides/curated_lexicon.json
排除（编译产物 / 治理刷新链资产）：samples_bank 其余全部（slices*、bank_index、
corpus_meta、stage 切片目录…）、depth_targets/、section_expectations/、
consistency_contracts.json、attachment_checklist.json、paradigms/roles/ 与
style_targets/（stage 启用资产，pisuan-custom 权威，随代码链分发）。

用法（仓库根，宿主执行；Gitea 须已 up 且 refsadmin/eia-refs 已建）：
    python scripts/governance/refs_repo_seed.py --password <refsadmin密码>
    python scripts/governance/refs_repo_seed.py --skip-push   # 离线演练：只填工作树不 push
密码也接受环境变量 GITEA_REFS_PASSWORD；不落任何文件。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_REFS = "backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references"
BOT_NAME, BOT_EMAIL = "pisuan-refs-bot", "refs-bot@pisuan.local"

# 手列文件（目录规则见 in_manifest）
INCLUDE_FILES = {
    "standards_index.json",
    "formulas.json",
    "samples_bank/corpus_meta_annotations.json",  # 唯一入仓的 samples_bank 文件（人工判定层）
}


def in_manifest(rel: str) -> bool:
    """rel 为 references 内 posix 相对路径。清单即真相：未列 = 不入仓。"""
    if rel in INCLUDE_FILES:
        return True
    parts = PurePosixPath(rel).parts
    top = parts[0]
    if top == "stages":
        return len(parts) == 2 and rel.endswith(".json")
    if top == "paradigms":  # 顶层 *.md + forms_catalog.json；roles/ 排除
        return len(parts) == 2 and (rel.endswith(".md") or rel == "forms_catalog.json")
    if top in ("sample_entities", "overrides"):
        return True
    return False


def run_git(args: list[str], cwd: Path, check: bool = True, binary: bool = False):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                       encoding=None if binary else "utf-8")
    if check and r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace") if isinstance(r.stderr, bytes) else r.stderr
        sys.exit(f"[refs-seed] git {' '.join(args[:3])} 失败:\n{err}")
    return r


def source_files(ref: str) -> list[str]:
    """committed refs 中命中清单的文件（references 内相对路径，posix）。"""
    out = run_git(["ls-tree", "-r", "--name-only", ref, "--", SKILL_REFS], REPO_ROOT)
    files = []
    for line in out.stdout.splitlines():
        rel = PurePosixPath(line.strip()).relative_to(PurePosixPath(SKILL_REFS)).as_posix()
        if in_manifest(rel):
            files.append(rel)
    if not files:
        sys.exit(f"[refs-seed] {ref} 下无命中清单的 refs 文件——检查 SKILL_REFS 路径")
    return sorted(files)


def materialize(worktree: Path, ref: str, files: list[str]) -> tuple[int, int]:
    """逐文件 git show 写入工作树（write_bytes 保真），并清掉清单内已不在源里的残留。"""
    for rel in files:
        blob = run_git(["show", f"{ref}:{SKILL_REFS}/{rel}"], REPO_ROOT, binary=True).stdout
        dest = worktree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    stale = []
    if (worktree / ".git").exists():
        tracked = run_git(["ls-files"], worktree).stdout.splitlines()
        stale = [t for t in tracked if t and not in_manifest(t)]
        for rel in stale:
            (worktree / rel).unlink(missing_ok=True)
    return len(files), len(stale)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="HEAD", help="播种源（pisuan-custom 的 commit，默认 HEAD）")
    ap.add_argument("--state-dir", default=os.environ.get("YUXI_STATE_DIR", "docker/volumes"),
                    help="卷根（默认 docker/volumes，与 compose YUXI_STATE_DIR 同源）")
    ap.add_argument("--remote", default="http://127.0.0.1:3000/refsadmin/eia-refs.git",
                    help="Gitea 仓 URL")
    ap.add_argument("--user", default="refsadmin")
    ap.add_argument("--password", default=os.environ.get("GITEA_REFS_PASSWORD"),
                    help="Gitea 密码（或 env GITEA_REFS_PASSWORD）")
    ap.add_argument("--skip-push", action="store_true", help="只物化工作树+本地 commit，不 push")
    args = ap.parse_args()

    ref_sha = run_git(["rev-parse", "--short=12", args.ref], REPO_ROOT).stdout.strip()
    worktree = Path(args.state_dir).resolve() / "pisuan" / "refs-repo" / "worktree"
    fresh = not (worktree / ".git").exists()
    if fresh:
        worktree.mkdir(parents=True)
        run_git(["init", "-b", "main"], worktree)
    # 字节保真：禁 autocrlf 改写；bot 身份只作用于本工作树
    run_git(["config", "core.autocrlf", "false"], worktree)
    run_git(["config", "user.name", BOT_NAME], worktree)
    run_git(["config", "user.email", BOT_EMAIL], worktree)
    run_git(["remote", "add" if fresh else "set-url", "origin", args.remote], worktree)

    files = source_files(args.ref)
    n_wrote, n_stale = materialize(worktree, args.ref, files)
    run_git(["add", "-A"], worktree)
    staged = run_git(["status", "--porcelain"], worktree).stdout
    if not staged.strip():
        head = run_git(["log", "-1", "--format=%h %s"], worktree).stdout.strip()
        print(f"[refs-seed] 幂等：与 HEAD 一致，无 commit（工作树 {len(files)} 文件；HEAD {head}）")
        return

    run_git(["commit", "-m",
             f"seed: pisuan-custom@{ref_sha} 初始化/对齐环评 refs 数据仓\n\n"
             f"清单：专家可编辑 8 条闭环 + overrides 词表层（{n_wrote} 文件）。\n"
             "编译产物不入仓（samples_bank 编译件/depth_targets/section_expectations 等）。"], worktree)
    print(f"[refs-seed] commit 完成：{n_wrote} 文件入仓（清残留 {n_stale}）")
    if args.skip_push:
        print("[refs-seed] --skip-push：本地 commit 未推送")
        return
    if not args.password:
        sys.exit("[refs-seed] 缺密码（--password 或 GITEA_REFS_PASSWORD）；本地 commit 已留，补密后重跑即可推送")
    # 密码只进 argv（瞬时），不落 .git/config；origin 保持无凭据 URL 供人读
    push_url = args.remote.replace("://", f"://{args.user}:{args.password}@", 1)
    run_git(["push", push_url, "main:refs/heads/main"], worktree)
    print(f"[refs-seed] push 完成 → {args.remote}")


if __name__ == "__main__":
    main()
