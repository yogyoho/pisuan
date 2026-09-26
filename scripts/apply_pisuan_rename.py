#!/usr/bin/env python3
"""apply_pisuan_rename.py — 生成 yuxi→pisuan 机械改名层。

设计文档: docs/superpowers/specs/2026-09-26-yuxi-rename-sync-design.md

原则:
- 确定性: 相同树状态永远产出相同结果
- 幂等: 重复执行不再产生变化
- 显式模式表: 结构化标识符替换 + 带行保护的裸词替换, 不做盲目全局 sed
- 只触碰 git 跟踪文件; 运行时数据/未跟踪文件归切换日手册处理

用法:
  python scripts/apply_pisuan_rename.py           # dry-run: 只打印计划与残余报告
  python scripts/apply_pisuan_rename.py --apply   # 实际执行 git mv + 内容重写
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# 目录整体跳过（按路径组件名匹配）: .wolf 是会话元数据; docs/superpowers 是设计/计划
# 文档本身, 其中对 yuxi 的引用是对改名对象的描述而非待改标识符
SKIP_DIRS = {".git", ".wolf", "node_modules", "superpowers", ".venv"}
SKIP_FILES = {"uv.lock"}  # 由 uv lock 重新生成, 不做文本替换
SKIP_SUFFIXES = (".egg-info",)  # 路径组件以此结尾即跳过（构建产物）

# 结构化替换: 带分隔符上下文的标识符（路径/导入/环境变量）, 任何行都改。
# 否则代码跑不起来, 不受"上游指称"行保护约束。
# 后三条覆盖嵌入形态: 类名(YuxiWorker)/HTTP 头(x-yuxi-uid)/临时路径(.yuxi/)/
# 下划线嵌入(_message_chunk_yuxi_events); xerrors/Yuxi 的 Yuxi 前面是 "/",
# 不在 lookbehind [\w.\-] 内, 上游指称依然安全
STRUCTURAL_RULES = [
    (r"YUXI_(?=[A-Z0-9_])", "PISUAN_"),  # 环境变量名 YUXI_API_PORT 等
    (r"(?<![\w.\-])yuxi(?=[./_\-])", "pisuan"),  # yuxi. yuxi/ yuxi_ yuxi-
    (r"Yuxi(?=[A-Z0-9])", "Pisuan"),  # 嵌入大写: YuxiWorker → PisuanWorker
    (r"(?<=[\w.\-])yuxi", "pisuan"),  # 标识符嵌入: _yuxi_ .yuxi/ x-yuxi-uid
    (r"(?<=[\w.\-])Yuxi", "Pisuan"),  # 嵌入大写: X-Yuxi-Preview → X-Pisuan-Preview
]

# 裸词替换: 独立出现的 yuxi / Yuxi（导入尾词、引号内、品牌文案、路径末段）。
# 注意 lookbehind 不含 "/" —— 否则 volumes/yuxi 这类"分隔符+行尾"的路径末段会漏改。
# 含上游指称关键词的行整体跳过 —— 那是对上游项目的描述, 属保留清单
BARE_RULES = [
    (r"(?<![\w._\-])yuxi(?![\w./_\-])", "pisuan"),
    (r"(?<![\w._\-])Yuxi(?![\w./_\-])", "Pisuan"),
]
PROTECTED_LINE = ("xerrors", "上游", "upstream")

# 目录改名: 基名恰为 yuxi 或以 yuxi- 开头的跟踪目录
# （已知命中: backend/package/yuxi、packages/yuxi-cli）
DIR_EXACT = "yuxi"
DIR_PREFIX = "yuxi-"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def tracked_files(root: Path) -> list[Path]:
    out = git(root, "ls-files", "-z")
    paths = []
    for chunk in out.split("\0"):
        if not chunk:
            continue
        parts = Path(chunk).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if any(part in SKIP_FILES for part in parts):
            continue
        if any(part.endswith(SKIP_SUFFIXES) for part in parts):
            continue
        paths.append(root / chunk)
    return paths


def plan_dir_moves(files: list[Path], root: Path) -> list[tuple[Path, Path]]:
    """收集需要改名的目录（每个文件命中最顶层组件即止）。"""
    planned: dict[Path, Path] = {}
    for p in files:
        rel = p.relative_to(root)
        for i, part in enumerate(rel.parts[:-1]):
            if part == DIR_EXACT or part.startswith(DIR_PREFIX):
                src = root / Path(*rel.parts[: i + 1])
                planned.setdefault(src, src.parent / part.replace("yuxi", "pisuan", 1))
                break
    return sorted(planned.items())


def apply_dir_moves(root: Path, moves: list[tuple[Path, Path]]) -> list[tuple[str, str]]:
    done = []
    for src, dst in moves:
        if dst.exists():
            continue  # 幂等: 已改名
        git(root, "mv", "--", str(src.relative_to(root)), str(dst.relative_to(root)))
        done.append((src.relative_to(root).as_posix(), dst.relative_to(root).as_posix()))
    return done


def rewrite_text(text: str) -> tuple[str, int]:
    """应用全部替换规则, 返回 (新文本, 替换次数)。字节级保真（不动行尾）。"""
    count = 0
    for pattern, repl in STRUCTURAL_RULES:
        text, n = re.subn(pattern, repl, text)
        count += n
    lines = []
    for line in text.splitlines(keepends=True):
        if any(k in line for k in PROTECTED_LINE):
            lines.append(line)
            continue
        for pattern, repl in BARE_RULES:
            line, n = re.subn(pattern, repl, line)
            count += n
        lines.append(line)
    return "".join(lines), count


def residue_report(root: Path, files: list[Path]) -> list[str]:
    """改名后仍含 yuxi 字样的位置（应全部落在保留清单内）。"""
    hits = []
    for p in files:
        try:
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # 二进制文件
        for lineno, line in enumerate(text.splitlines(), 1):
            if "yuxi" in line.lower():
                hits.append(f"{p.relative_to(root)}:{lineno}: {line.strip()[:120]}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 yuxi→pisuan 机械改名层")
    ap.add_argument("--apply", action="store_true", help="实际执行（缺省 dry-run）")
    ap.add_argument("--root", default=None, help="仓库根（缺省取本脚本上上级目录）")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    moves = plan_dir_moves(tracked_files(root), root)
    applied = apply_dir_moves(root, moves) if args.apply else []

    files = tracked_files(root)  # 目录改名后重新枚举
    changed = 0
    for p in files:
        try:
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        new_text, n = rewrite_text(text)
        if n and new_text != text:
            if args.apply:
                p.write_bytes(new_text.encode("utf-8"))
            changed += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"== pisuan 改名 [{mode}] ==")
    print(f"目录 mv 计划: {len(moves)}")
    for src, dst in moves:
        print(f"  {src.relative_to(root).as_posix()} -> {dst.relative_to(root).as_posix()}")
    print(f"目录 mv 实际执行: {len(applied)}")
    for old, new in applied:
        print(f"  {old} -> {new}")
    print(f"内容改写文件: {changed}")
    residues = residue_report(root, files)
    print(f"残余 yuxi 位置: {len(residues)}")
    for h in residues:
        print(f"  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
