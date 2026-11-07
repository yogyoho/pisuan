"""chapter-writer 资产守卫：scripts/ 与 writer 逐文件字节一致 + references/ 单源化不携带（spec §5 打包契约 + 评审 P2-8）。

chapter-writer 包 = coal-eia-writer 的分章管线变体，脚本地基由项目根
scripts/sync_chapter_skill.py 单向镜像；references/ 自 P2-8（2026-11-03）单源在
writer 包（chapter 脚本经 _paths.py 运行时回落解析），本测试拦脚本漂移与
references 复活——改 writer 源后须重跑同步脚本再提交。
"""
from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

import pytest

# 纯路径定位（禁 import pisuan：宿主 pytest 无 langgraph 依赖链）。两栖布局：
#   宿主 repo：   <backend>/package/pisuan/agents/skills/buildin
#   localized 容器：<app>/skill-sources/shared（pisuan 改名层把技能包挪到 skill-sources）
_APP = Path(__file__).resolve().parents[4]
BUILDIN = next(
    (c for c in (_APP / "package" / "pisuan" / "agents" / "skills" / "buildin",
                 _APP / "skill-sources" / "shared") if c.is_dir()),
    None,
)
# 同步脚本只存在于宿主 repo 布局（容器 /app 无项目根 scripts/）
SYNC_SCRIPT = next(
    (anc / "scripts" / "sync_chapter_skill.py"
     for anc in Path(__file__).resolve().parents
     if (anc / "scripts" / "sync_chapter_skill.py").is_file()),
    None,
)

SRC = BUILDIN / "coal-eia-writer"
DST = BUILDIN / "coal-eia-chapter-writer"
REVIEWER = BUILDIN / "coal-eia-reviewer"
SUBDIRS = ("scripts",)
# reviewer 最小副本清单（与 sync_chapter_skill.py REVIEWER_FILES 同源）
REVIEWER_FILES = ("references/compliance_checklist.md", "references/standards_index.json")


def _files(root: Path) -> set[Path]:
    # __pycache__ 非资产（容器跑测试再生的运行时产物），不入比对集
    return {p.relative_to(root) for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


def test_assets_byte_identical():
    if BUILDIN is None:
        pytest.skip(f"技能包根未定位（宿主/容器布局均未命中）：{_APP}")
    for sub in SUBDIRS:
        src_dir, dst_dir = SRC / sub, DST / sub
        assert src_dir.is_dir() and dst_dir.is_dir(), sub
        src_files, dst_files = _files(src_dir), _files(dst_dir)
        assert dst_files == src_files, (
            f"{sub}: 缺失 {sorted(src_files - dst_files)[:5]} / 孤儿 {sorted(dst_files - src_files)[:5]}")
        for rel in sorted(src_files):
            assert filecmp.cmp(src_dir / rel, dst_dir / rel, shallow=False), (
                f"{sub}/{rel} 两包字节不一致——重跑 scripts/sync_chapter_skill.py")
    # references/ 单源化（P2-8）：chapter 不携带，复活即漂移面回归
    assert not (DST / "references").exists(), (
        "chapter 包不应携带 references/（P2-8 单源化，脚本经 _paths.py 回落 writer 包）——"
        "重跑 scripts/sync_chapter_skill.py 清除")


def test_sync_script_check_mode_passes():
    if SYNC_SCRIPT is None:
        pytest.skip("容器 /app 布局无项目根 scripts/（宿主专属冒烟；字节守卫由上一用例承担）")
    r = subprocess.run([sys.executable, str(SYNC_SCRIPT), "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_reviewer_minimal_copies():
    """reviewer 包最小副本：清单内两文件与 writer 字节一致；references/ 无清单外文件。"""
    for rel in REVIEWER_FILES:
        assert filecmp.cmp(SRC / rel, REVIEWER / rel, shallow=False), f"reviewer/{rel} 与 writer 漂移"
    rev_refs = REVIEWER / "references"
    extra = {p.relative_to(REVIEWER) for p in rev_refs.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts} - {Path(r) for r in REVIEWER_FILES}
    assert not extra, f"reviewer/references 清单外文件: {sorted(extra)}"


def test_skill_md_is_per_package():
    """SKILL.md 为各包专属（不在同步范围）：chapter-writer 契约含分章专属标记。"""
    if BUILDIN is None:
        pytest.skip(f"技能包根未定位（宿主/容器布局均未命中）：{_APP}")
    for pkg in ("coal-eia-writer", "coal-eia-chapter-writer"):
        md = BUILDIN / pkg / "SKILL.md"
        assert md.is_file()
        assert f"name: {pkg}" in md.read_text(encoding="utf-8")
    chapter = (DST / "SKILL.md").read_text(encoding="utf-8")
    assert "--mode chapter" in chapter and "confirm-chapter" in chapter
