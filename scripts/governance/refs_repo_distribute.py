"""refs 数据仓分发：Gitea pull → skill-sources/shared → projections（批次2 分发步）。

设计：docs/vibe/2026-11-01-eia-refs-local-git-chain.md。导出链把专家裁决 push 到本地
Gitea（唯一权威）并直写栈包 references；本脚本把 refs-repo 工作树（pull 后 = Gitea HEAD）
的 **清单内文件** 分发到技能消费侧（skill-sources/shared + 各 projection 的
coal-eia-writer/references）。清单级 overlay：只覆盖入仓清单文件，目标处的编译产物
（depth_targets/samples_bank 编译件等）不动——那些仍走 bank_compile 编译链。

用法（仓库根，宿主执行；--state-dir 指运行栈卷根）：
    python scripts/governance/refs_repo_distribute.py \
        --state-dir C:\\workspace\\pisuan-localized\\docker\\volumes --password <pw>
    # --check 只对账不改文件；--no-pull 跳过 Gitea 拉取只重放本地工作树
对账口径：清单内每文件在消费侧存在且 md5 一致；消费侧多余文件不视为漂移。
"""
import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refs_repo_seed import in_manifest  # 清单唯一权威：与播种同一份规则

SKILL = "coal-eia-writer"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def git(wt: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=wt, capture_output=True, text=True)


def manifest_files(worktree: Path) -> list[Path]:
    return [p for p in worktree.rglob("*") if p.is_file() and ".git" not in p.parts
            and in_manifest(p.relative_to(worktree).as_posix())]


def targets_for(state_dir: Path) -> list[Path]:
    """消费侧 references 根：shared + 已有该技能包的各 projection。"""
    root = state_dir / "pisuan"
    out = [root / "skill-sources" / "shared" / SKILL / "references"]
    proj = root / "skill-projections"
    if proj.is_dir():
        out += sorted(d / SKILL / "references" for d in proj.iterdir()
                      if d.is_dir() and (d / SKILL / "references").is_dir())
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-dir", default=os.environ.get("YUXI_STATE_DIR", ""),
                    help="运行栈卷根（含 pisuan/refs-repo、pisuan/skill-sources…）")
    ap.add_argument("--remote", default="http://127.0.0.1:3000/refsadmin/eia-refs.git")
    ap.add_argument("--user", default="refsadmin")
    ap.add_argument("--password", default=os.environ.get("GITEA_REFS_PASSWORD"))
    ap.add_argument("--check", action="store_true", help="只对账，不 pull 不写")
    ap.add_argument("--no-pull", action="store_true", help="跳过 pull，直接分发本地工作树")
    args = ap.parse_args()
    if not args.state_dir:
        sys.exit("[refs-dist] 缺 --state-dir（运行栈卷根）")

    worktree = Path(args.state_dir).resolve() / "pisuan" / "refs-repo" / "worktree"
    if not (worktree / ".git").exists():
        sys.exit(f"[refs-dist] 工作树不存在（先跑 refs_repo_seed.py）: {worktree}")

    if not args.check and not args.no_pull:
        if not args.password:
            sys.exit("[refs-dist] pull 需 --password / GITEA_REFS_PASSWORD（或改用 --no-pull）")
        authed = args.remote.replace("://", f"://{args.user}:{args.password}@", 1)
        r = git(worktree, "-c", f"safe.directory={worktree}", "pull", "--ff-only", authed, "main")
        if r.returncode != 0:
            sys.exit(f"[refs-dist] pull 失败:\n{r.stdout}\n{r.stderr}")
        print(f"[refs-dist] pull: {'已是最新' if 'up to date' in r.stdout.lower() or not r.stdout else r.stdout.strip().splitlines()[0]}")

    files = manifest_files(worktree)
    if not files:
        sys.exit("[refs-dist] 工作树无清单内文件——检查 refs_repo_seed.in_manifest")
    digest = {p.relative_to(worktree).as_posix(): md5(p) for p in files}

    failed = 0
    for troot in targets_for(state_dir=Path(args.state_dir).resolve()):
        rel_troot = troot.relative_to(Path(args.state_dir).resolve())
        if args.check:
            bad = [rel for rel, h in digest.items()
                   if not (troot / rel).is_file() or md5(troot / rel) != h]
            print(f"[refs-dist] 对账 {rel_troot}: {len(digest)} 文件，不一致/缺失 {len(bad)}")
            for rel in bad[:10]:
                print(f"    ✗ {rel}")
            failed += len(bad)
            continue
        for src in files:
            dest = troot / src.relative_to(worktree)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
        print(f"[refs-dist] 分发 {len(files)} 文件 → {rel_troot}")

    if args.check:
        print("[refs-dist] 对账结论:", "一致" if not failed else f"{failed} 处漂移（先跑分发）")
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
