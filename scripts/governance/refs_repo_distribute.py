"""refs 数据仓分发：Gitea pull → skill-sources/shared → projections（批次2 分发步）。

设计：docs/vibe/2026-11-01-eia-refs-local-git-chain.md。导出链把专家裁决 push 到本地
Gitea（唯一权威）并直写栈包 references；本脚本把 refs-repo 工作树（pull 后 = Gitea HEAD）
的 **清单内文件** 分发到各消费技能的 references（skill-sources/shared + 各 projection）。
消费面按技能收窄（CONSUMERS）：writer 全清单（权威消费方）；chapter-writer 不收 stages/
（同名异义：其章骨架与 writer 口径字段 5 文件名完全重叠，全量分发会静默覆盖章骨架）与
sample_entities（其自有注册表是 sample_entities.md 单文件）；reviewer 只收
standards_index.json（在册核对真源）。清单级 overlay：只覆盖清单内文件，目标处的编译产物
（depth_targets/samples_bank 编译件等）不动——那些仍走 bank_compile 编译链。

用法（仓库根，宿主执行；--state-dir 指运行栈卷根）：
    python scripts/governance/refs_repo_distribute.py \
        --state-dir C:\\workspace\\pisuan-localized\\docker\\volumes --password <pw>
    # --check 只对账不改文件；--no-pull 跳过 Gitea 拉取只重放本地工作树
对账口径：清单内每文件在消费侧存在且内容一致（CRLF 归一 md5——Gitea 权威字节是 LF，
Windows 检出/栈包副本是 CRLF，同内容异 EOL 不算漂移）；消费侧多余文件不视为漂移。
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refs_repo_seed import in_manifest  # 清单唯一权威：与播种同一份规则

# 消费面清单：值为 refs-repo 内允许分发到该技能的文件/目录前缀白名单（None = 全清单）。
# refs 仓是 writer 权威镜像；其他技能只收其实际消费的资产子集（见模块 docstring）。
CONSUMERS: dict[str, tuple[str, ...] | None] = {
    "coal-eia-writer": None,
    "coal-eia-chapter-writer": (
        "standards_index.json",
        "formulas.json",
        "samples_bank/corpus_meta_annotations.json",
        "paradigms/",
        "overrides/",
    ),
    "coal-eia-reviewer": ("standards_index.json",),
}


def in_consumer_scope(rel: str, skill: str) -> bool:
    """rel 为 references 内 posix 相对路径；范围恒为清单子集（digest 只含清单文件）。"""
    allowed = CONSUMERS[skill]
    if allowed is None:
        return True
    return rel in allowed or any(rel.startswith(p) for p in allowed if p.endswith("/"))


def md5(p: Path) -> str:
    """内容级 md5：CRLF 归一后再比——同内容异 EOL（检出风味）不算漂移。"""
    return hashlib.md5(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def git(wt: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=wt, capture_output=True, text=True)


def manifest_files(worktree: Path) -> list[Path]:
    return [
        p
        for p in worktree.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and in_manifest(p.relative_to(worktree).as_posix())
    ]


def targets_for(state_dir: Path) -> list[tuple[Path, str]]:
    """消费侧 (references 根, 技能)：shared + 已有该技能包的各 projection；根不存在则跳过。"""
    root = state_dir / "pisuan"
    proj = root / "skill-projections"
    out: list[tuple[Path, str]] = []
    for skill in CONSUMERS:
        shared = root / "skill-sources" / "shared" / skill / "references"
        if shared.is_dir():
            out.append((shared, skill))
        if proj.is_dir():
            out += [
                (d / skill / "references", skill)
                for d in sorted(proj.iterdir())
                if d.is_dir() and (d / skill / "references").is_dir()
            ]
    return out


def main() -> None:
    # Windows 控制台默认 cp936，✗ 等字符会 UnicodeEncodeError 中断对账；保编码仅替换不可编码符
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--state-dir",
        default=os.environ.get("YUXI_STATE_DIR", ""),
        help="运行栈卷根（含 pisuan/refs-repo、pisuan/skill-sources…）",
    )
    ap.add_argument("--remote", default="http://127.0.0.1:3000/refsadmin/eia-refs.git")
    ap.add_argument("--user", default="refsadmin")
    ap.add_argument("--password", default=os.environ.get("GITEA_REFS_PASSWORD"))
    ap.add_argument("--check", action="store_true", help="只对账，不 pull 不写")
    ap.add_argument(
        "--no-pull", action="store_true", help="跳过 pull，直接分发本地工作树"
    )
    args = ap.parse_args()
    if not args.state_dir:
        sys.exit("[refs-dist] 缺 --state-dir（运行栈卷根）")

    worktree = Path(args.state_dir).resolve() / "pisuan" / "refs-repo" / "worktree"
    if not (worktree / ".git").exists():
        sys.exit(f"[refs-dist] 工作树不存在（先跑 refs_repo_seed.py）: {worktree}")

    if not args.check and not args.no_pull:
        if not args.password:
            sys.exit(
                "[refs-dist] pull 需 --password / GITEA_REFS_PASSWORD（或改用 --no-pull）"
            )
        authed = args.remote.replace("://", f"://{args.user}:{args.password}@", 1)
        r = git(
            worktree,
            "-c",
            f"safe.directory={worktree}",
            "pull",
            "--ff-only",
            authed,
            "main",
        )
        if r.returncode != 0:
            sys.exit(f"[refs-dist] pull 失败:\n{r.stdout}\n{r.stderr}")
        print(
            f"[refs-dist] pull: {'已是最新' if 'up to date' in r.stdout.lower() or not r.stdout else r.stdout.strip().splitlines()[0]}"
        )

    files = manifest_files(worktree)
    if not files:
        sys.exit("[refs-dist] 工作树无清单内文件——检查 refs_repo_seed.in_manifest")
    digest = {p.relative_to(worktree).as_posix(): md5(p) for p in files}

    failed = 0
    for troot, skill in targets_for(state_dir=Path(args.state_dir).resolve()):
        scope = sorted(rel for rel in digest if in_consumer_scope(rel, skill))
        rel_troot = troot.relative_to(Path(args.state_dir).resolve())
        if args.check:
            bad = [
                rel
                for rel in scope
                if not (troot / rel).is_file() or md5(troot / rel) != digest[rel]
            ]
            print(
                f"[refs-dist] 对账 {rel_troot}（{skill}）: {len(scope)} 文件，不一致/缺失 {len(bad)}"
            )
            for rel in bad[:10]:
                print(f"    ✗ {rel}")
            failed += len(bad)
            continue
        for rel in scope:
            dest = troot / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((worktree / rel).read_bytes())
        print(f"[refs-dist] 分发 {len(scope)} 文件 → {rel_troot}（{skill}）")

    if args.check:
        print(
            "[refs-dist] 对账结论:",
            "一致" if not failed else f"{failed} 处漂移（先跑分发）",
        )
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
