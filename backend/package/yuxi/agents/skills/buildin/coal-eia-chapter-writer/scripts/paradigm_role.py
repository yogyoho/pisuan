#!/usr/bin/env python3
"""节角色解析器：stage + section_id -> paradigm role（派发契约查表唯一入口）。

映射文件在 references/paradigms/roles/<stage>.json。查不到映射或角色值非法即拒派
（SKILL.md 步骤 4.1 契约：拒派报错，禁静默跳过）。

CLI 用法：
    python paradigm_role.py --stage planning_eia --section ch6_S01
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LEGAL_ROLES = {"opener", "baseline", "analysis", "measures", "conclusion", "process"}


def load_roles(references_dir: Path, stage: str) -> dict[str, str]:
    """读取并校验一个 stage 的角色映射；文件缺失/形状错/值非法都抛异常。"""
    path = references_dir / "paradigms" / "roles" / f"{stage}.json"
    if not path.exists():
        raise FileNotFoundError(f"角色映射缺失（stage 未启用？）: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    roles = data.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError(f"角色映射为空或形状错误: {path}")
    bad = sorted(set(roles.values()) - LEGAL_ROLES)
    if bad:
        raise ValueError(f"非法角色值 {bad}（合法: {sorted(LEGAL_ROLES)}）: {path}")
    return roles


def resolve(references_dir: Path, stage: str, section_id: str) -> str:
    roles = load_roles(references_dir, stage)
    if section_id not in roles:
        raise KeyError(f"节 {section_id} 无角色映射（stage={stage}）——拒派")
    return roles[section_id]


def main() -> int:
    ap = argparse.ArgumentParser(description="节角色解析：stage+section -> paradigm role")
    default_refs = Path(__file__).resolve().parent.parent / "references"
    ap.add_argument("--references-dir", default=str(default_refs))
    ap.add_argument("--stage", required=True)
    ap.add_argument("--section", required=True)
    a = ap.parse_args()
    try:
        print(resolve(Path(a.references_dir), a.stage, a.section))
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"ROLE_RESOLVE_FAIL: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
