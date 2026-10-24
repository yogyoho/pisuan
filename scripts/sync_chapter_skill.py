#!/usr/bin/env python3
"""chapter-writer 技能包资产同步：coal-eia-writer 的 scripts/ + references/ 单向镜像覆盖。

chapter-writer = writer 的分章管线变体（spec 2026-10-24 §3）：脚本地基与参考资产字节一致，
仅 SKILL.md 契约不同（分章编排）。本脚本是唯一同步通道；守卫测试
backend/test/unit/skills/test_chapter_skill_assets_sync.py 断言两包逐文件字节一致，
任何一包手改造成漂移都会被守卫拦下——改 writer 源后重跑本脚本再提交。
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "backend" / "package" / "yuxi" / "agents" / "skills" / "buildin"
SRC = ROOT / "coal-eia-writer"
DST = ROOT / "coal-eia-chapter-writer"
SUBDIRS = ("scripts", "references")


def sync(check_only: bool = False) -> int:
    """镜像同步或纯校验。返回 0=一致（或已同步），1=check 模式发现漂移/缺失/孤儿。"""
    problems: list[str] = []
    copied = removed = kept = 0
    for sub in SUBDIRS:
        src_dir, dst_dir = SRC / sub, DST / sub
        if not src_dir.is_dir():
            print(f"[sync] 源缺失: {src_dir}", file=sys.stderr)
            return 1
        # __pycache__ 非资产：两侧都不入比对集（运行时产物，容器跑测试会再生，删了反复横跳）
        src_files = {p.relative_to(src_dir) for p in src_dir.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts}
        dst_files = {p.relative_to(dst_dir) for p in dst_dir.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts} if dst_dir.is_dir() else set()
        for rel in sorted(src_files - dst_files):
            problems.append(f"缺失 {sub}/{rel}")
            if not check_only:
                (dst_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_dir / rel, dst_dir / rel)
                copied += 1
        for rel in sorted(src_files & dst_files):
            if not filecmp.cmp(src_dir / rel, dst_dir / rel, shallow=False):
                problems.append(f"漂移 {sub}/{rel}")
                if not check_only:
                    shutil.copy2(src_dir / rel, dst_dir / rel)
                    copied += 1
            else:
                kept += 1
        for rel in sorted(dst_files - src_files):
            problems.append(f"孤儿 {sub}/{rel}")
            if not check_only:
                (dst_dir / rel).unlink()
                removed += 1
    if check_only:
        if problems:
            print("SYNC_CHECK_FAIL: " + "; ".join(problems[:20]))
            return 1
        print(f"SYNC_CHECK_OK: 两包字节一致（{kept} 文件）")
        return 0
    print(f"SYNC_DONE: copied={copied} removed={removed} unchanged={kept}" + (f"（修复 {len(problems)} 处漂移）" if problems else "（本已一致）"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="coal-eia-writer → coal-eia-chapter-writer 资产单向同步（scripts/ + references/ 镜像；SKILL.md 不在同步范围）")
    ap.add_argument("--check", action="store_true", help="只校验不写（与守卫测试同款判定）")
    return sync(ap.parse_args().check)


if __name__ == "__main__":
    sys.exit(main())
