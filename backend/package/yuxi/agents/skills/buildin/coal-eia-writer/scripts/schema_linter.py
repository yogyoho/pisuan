#!/usr/bin/env python3
"""schema_linter.py — stage forms 资产静态体检（spec 2026-10-08-coal-eia-writer-hardening-design §4.3）。

五类检查（只报告不修复；stage JSON 修复另行立项）：
  L1 forms 族标量字段缺中文 label            （bug-366：135 字段）
  L2 label/note/type(enum 描述) 含 "|" 字符   （bug-393：28 组竖线枚举裂表）
  L3 数值型字段缺 unit（Task 2）
  L4 name 英文蛇形裸奔（Task 2）
  L5 枚举值卫生（Task 2）
用法（Task 2 实装 CLI）：
  python -X utf8 schema_linter.py --references <refs目录> [--stage planning_eia]
"""

import json
import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REFS_DEFAULT = SCRIPTS_DIR.parent / "references"

NUMERIC_TYPE_RE = re.compile(r"^(number|int|float)")
ENGLISH_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
HAS_CJK_RE = re.compile(r"[一-鿿]")
ENUM_PREFIX = "enum:"


def _iter_scalar_fields(forms: dict):
    """遍历 forms 树：yield (族名, 字段dict)。族内 fields[] 为字段清单。"""
    for fam_name, fam in forms.items():
        if not isinstance(fam, dict):
            continue
        for f in fam.get("fields", []):
            if isinstance(f, dict):
                yield fam_name, f


def lint_stage(stage_path: Path) -> dict:
    """单 stage 体检：返回 {"stage", "violations": [{check, family, field, detail}]}。"""
    doc = json.loads(stage_path.read_text(encoding="utf-8"))
    forms = doc.get("forms") or {}
    violations: list[dict] = []

    def add(check, fam, f, detail):
        violations.append({"check": check, "family": fam, "field": f.get("name", "?"), "detail": detail})

    for fam, f in _iter_scalar_fields(forms):
        label = str(f.get("label") or "")
        note = str(f.get("note") or "")
        ftype = str(f.get("type") or "")
        # L1 标量字段缺中文 label
        if not HAS_CJK_RE.search(label):
            add("L1", fam, f, f"label 缺失或非中文：{label!r}")
        # L2 竖线（label/note/type 全查）
        for src_name, src in (("label", label), ("note", note), ("type", ftype)):
            if "|" in src:
                add("L2", fam, f, f"{src_name} 含竖线：{src!r}")

    return {"stage": stage_path.stem, "violations": violations}
