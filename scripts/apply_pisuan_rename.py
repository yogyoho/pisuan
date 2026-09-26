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
# 文件整体跳过: uv.lock 由 uv lock 重新生成; 改名工具与其测试是对改名对象的描述
# （含规则字面量/断言夹具）, 参与改写会自毁规则表与断言, 与 docs/superpowers 同理豁免
SKIP_FILES = {"uv.lock", "apply_pisuan_rename.py", "test_apply_pisuan_rename.py"}
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

# 目录改名: 基名恰为 yuxi 或以 yuxi- / yuxi_ 开头的跟踪目录, 嵌套闭包迭代至无命中
# （已知命中: backend/package/yuxi、packages/yuxi-cli、packages/yuxi-cli/src/yuxi_cli）
DIR_EXACT = "yuxi"
DIR_PREFIXES = ("yuxi-", "yuxi_")


def is_rename_dir(name: str) -> bool:
    return name == DIR_EXACT or name.startswith(DIR_PREFIXES)


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


def shallowest_dir_moves(files: list[Path], root: Path) -> list[tuple[Path, Path]]:
    """收集当前各跟踪路径的最浅命中目录（每文件首个命中组件即止, 去重）。"""
    planned: dict[Path, Path] = {}
    for p in files:
        rel = p.relative_to(root)
        for i, part in enumerate(rel.parts[:-1]):
            if is_rename_dir(part):
                src = root / Path(*rel.parts[: i + 1])
                planned.setdefault(src, src.parent / rewrite_text(part)[0])
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


def apply_dir_closure(root: Path) -> list[tuple[str, str]]:
    """真实执行嵌套闭包: 每轮重新枚举 ls-files 取最浅命中执行 git mv, 直至无命中。"""
    done: list[tuple[str, str]] = []
    while True:
        executed = apply_dir_moves(root, shallowest_dir_moves(tracked_files(root), root))
        if not executed:
            return done
        done.extend(executed)


def original_parts(src: tuple[str, ...], plan: list[tuple[str, str]]) -> tuple[str, ...]:
    """把当前虚拟坐标的目录沿已规划条目逆向映射回原始坐标。"""
    parts = list(src)
    for orig, final in reversed(plan):
        final_parts = final.split("/")
        if parts[: len(final_parts)] == final_parts:
            parts = orig.split("/") + parts[len(final_parts):]
    return tuple(parts)


def plan_dir_closure(rel_parts: list[tuple[str, ...]]) -> list[tuple[str, str]]:
    """dry-run 用的虚拟闭包规划, 条目为 (原始路径, 最终路径), 顺序即真实执行顺序。

    每轮对各虚拟路径取最浅命中目录做前缀替换直至无命中; 深层目录在外层
    改名后才会暴露, 故需迭代而非单轮 break。
    """
    virt = [list(parts) for parts in rel_parts]
    plan: list[tuple[str, str]] = []
    while True:
        hits: dict[tuple[str, ...], str] = {}
        for parts in virt:
            for i in range(len(parts) - 1):
                if is_rename_dir(parts[i]):
                    hits.setdefault(tuple(parts[: i + 1]), rewrite_text(parts[i])[0])
                    break
        if not hits:
            return plan
        for src in sorted(hits, key=len):
            dst = src[:-1] + (hits[src],)
            plan.append(("/".join(original_parts(src, plan)), "/".join(dst)))
            for parts in virt:
                if tuple(parts[: len(src)]) == src:
                    parts[:] = list(dst) + parts[len(src):]


def virtual_final_parts(rel_parts: tuple[str, ...], dir_plan: list[tuple[str, str]]) -> tuple[str, ...]:
    """把原始路径按目录闭包计划映射为最终虚拟路径（深前缀优先应用）。"""
    parts = list(rel_parts)
    for src, dst in reversed(dir_plan):
        src_parts = src.split("/")
        if parts[: len(src_parts)] == src_parts:
            parts = dst.split("/") + parts[len(src_parts):]
    return tuple(parts)


def plan_file_renames(rel_parts: list[tuple[str, ...]]) -> list[tuple[str, str]]:
    """跟踪文件基名按同一套替换规则改名（路径单行, 无保护行场景）。"""
    plan = []
    for parts in rel_parts:
        new_name, _ = rewrite_text(parts[-1])
        if new_name != parts[-1]:
            plan.append(("/".join(parts), "/".join(parts[:-1] + (new_name,))))
    return sorted(plan)


def apply_file_renames(root: Path, plan: list[tuple[str, str]]) -> list[tuple[str, str]]:
    done = []
    for src, dst in plan:
        if (root / dst).exists():
            continue  # 幂等: 已改名
        git(root, "mv", "--", src, dst)
        done.append((src, dst))
    return done


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


def residue_report(root: Path, files: list[Path]) -> tuple[list[str], int]:
    """改名后仍含 yuxi 字样的位置（应全部落在保留清单内）, 连同非 UTF-8 跳过文件数。

    与 main 的改写循环枚举同一份 files, 跳过集合恒等, 计数以此为单一来源。
    """
    hits = []
    skipped = 0
    for p in files:
        try:
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue  # 二进制文件
        for lineno, line in enumerate(text.splitlines(), 1):
            if "yuxi" in line.lower():
                hits.append(f"{p.relative_to(root)}:{lineno}: {line.strip()[:120]}")
    return hits, skipped


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="生成 yuxi→pisuan 机械改名层")
    ap.add_argument("--apply", action="store_true", help="实际执行（缺省 dry-run）")
    ap.add_argument("--root", default=None, help="仓库根（缺省取本脚本上上级目录）")
    ap.add_argument("--allow-dirty", action="store_true", help="跳过脏工作树守卫")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    if args.apply and not args.allow_dirty:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        if dirty:
            print("工作树有未提交改动, 拒绝 --apply（确认无误可用 --allow-dirty 跳过）:", file=sys.stderr)
            for line in dirty.splitlines()[:20]:
                print(f"  {line}", file=sys.stderr)
            return 1
    files = tracked_files(root)
    dir_plan = plan_dir_closure([p.relative_to(root).parts for p in files])
    dir_done: list[tuple[str, str]] = []
    file_plan: list[tuple[str, str]] = []
    file_done: list[tuple[str, str]] = []
    if args.apply:
        dir_done = apply_dir_closure(root)
        files = tracked_files(root)  # 目录改名后重新枚举
        file_plan = plan_file_renames([p.relative_to(root).parts for p in files])
        file_done = apply_file_renames(root, file_plan)
        files = tracked_files(root)  # 文件改名后重新枚举
    else:
        file_plan = plan_file_renames(
            [virtual_final_parts(p.relative_to(root).parts, dir_plan) for p in files]
        )

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
    print(f"目录 mv 计划: {len(dir_plan)}")
    for src, dst in dir_plan:
        print(f"  {src} -> {dst}")
    print(f"目录 mv 实际执行: {len(dir_done)}")
    for src, dst in dir_done:
        print(f"  {src} -> {dst}")
    print(f"文件改名计划: {len(file_plan)}")
    for src, dst in file_plan:
        print(f"  {src} -> {dst}")
    print(f"文件改名实际执行: {len(file_done)}")
    for src, dst in file_done:
        print(f"  {src} -> {dst}")
    print(f"内容改写文件: {changed}")
    residues, skipped = residue_report(root, files)
    if args.apply:
        print(f"残余 yuxi 位置: {len(residues)}")
    else:
        print(f"当前含 yuxi 位置: {len(residues)}（dry-run 未改写, 含将被改写的行）")
    print(f"跳过非 UTF-8 文件: {skipped}")
    for h in residues:
        print(f"  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
