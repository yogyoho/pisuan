#!/usr/bin/env python3
"""schema_linter.py — stage forms 资产静态体检（spec 2026-10-08-coal-eia-writer-hardening-design §4.3）。

五类检查（只报告不修复；stage JSON 修复另行立项）：
  L1 forms 族标量字段缺中文 label            （bug-366：135 字段）
  L2 label/note/type(enum 描述) 含 "|" 字符   （bug-393：28 组竖线枚举裂表）
  L3 数值型字段缺 unit（unit 键缺失/空且 note 无单位词表字样）
  L4 复合字段嵌套列名清单英文裸奔（行内无 "en 中文" 注记且族旁无映射）
  L5 枚举值卫生（段含英文字母/重复/单段超 20 字）
用法：
  python -X utf8 schema_linter.py --references <refs目录> [--stage planning_eia]
stdout 输出 JSON 摘要（各 stage × L1-L5 计数 + total），stderr 逐条明细，exit 1=有违规。
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REFS_DEFAULT = SCRIPTS_DIR.parent / "references"

NUMERIC_TYPE_RE = re.compile(r"^(number|int|float)")
ENGLISH_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
HAS_CJK_RE = re.compile(r"[一-鿿]")
HAS_LETTER_RE = re.compile(r"[A-Za-z]")
ENUM_PREFIX = "enum:"
ENUM_SEP_RE = re.compile(r"[、,，/；;]")
UNIT_WORDS = ("m³", "m2", "hm2", "km2", "dB", "mg/L", "μg", "km", "万m³", "万t", "%")
CHECKS = ("L1", "L2", "L3", "L4", "L5")


def _unit_in_note(note: str) -> bool:
    """note 文本含任一单位词表字样即认有单位。"""
    return any(w in note for w in UNIT_WORDS)


def _iter_scalar_fields(forms: dict):
    """遍历 forms 树：yield (族名, 字段dict)。族内 fields[] 为字段清单。"""
    for fam_name, fam in forms.items():
        if not isinstance(fam, dict):
            continue
        for f in fam.get("fields", []):
            if isinstance(f, dict):
                yield fam_name, f


def _check_l4_composite(forms: dict, add) -> None:
    """L4：复合字段（fields 为字符串列名清单）中英文蛇名的裸奔检查。

    真实形状是行内注记（"en_name 中文label" 同串）；旁挂映射（labels/columns/
    <字段名>_labels 的 dict）同样认数。判违规：列名符合 ENGLISH_NAME_RE 且行内、
    映射均无中文。
    """
    for fam_name, fam in forms.items():
        if not isinstance(fam, dict):
            continue
        for fd in fam.get("fields", []):
            cols = fd.get("fields") if isinstance(fd, dict) else None
            if not (isinstance(cols, list) and cols and isinstance(cols[0], str)):
                continue
            label_map: dict = {}
            for holder in (fd, fam):
                for k, v in holder.items():
                    if isinstance(v, dict) and (k in ("labels", "columns") or k == f"{fd.get('name')}_labels"):
                        label_map.update(v)
            for entry in cols:
                parts = str(entry).split()
                name = parts[0] if parts else ""
                if not ENGLISH_NAME_RE.match(name) or HAS_CJK_RE.search(str(entry)):
                    continue
                if HAS_CJK_RE.search(str(label_map.get(name, ""))):
                    continue
                add("L4", fam_name, fd, f"复合字段列名英文裸奔：{name}")


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
                add("L2", fam, f, f"{src_name}：含竖线 {src!r}")
        # L3 数值型缺单位
        if NUMERIC_TYPE_RE.match(ftype) and not str(f.get("unit") or "").strip() and not _unit_in_note(note):
            add("L3", fam, f, "数值型缺单位：unit 键缺失/空且 note 无单位字样")
        # L5 枚举值卫生
        if ftype.startswith(ENUM_PREFIX):
            seen: set[str] = set()
            for seg in ENUM_SEP_RE.split(ftype[len(ENUM_PREFIX):]):
                seg = seg.strip()
                if not seg:
                    continue
                if HAS_LETTER_RE.search(seg):
                    add("L5", fam, f, f"枚举段含英文字母：{seg!r}")
                if seg in seen:
                    add("L5", fam, f, f"枚举段重复：{seg!r}")
                seen.add(seg)
                if len(seg) > 20:
                    add("L5", fam, f, f"枚举段超 20 字（{len(seg)}）：{seg!r}")

    _check_l4_composite(forms, add)
    return {"stage": stage_path.stem, "violations": violations}


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="stage forms 五类静态体检（L1-L5，只报告不修复）")
    ap.add_argument("--references", default=str(REFS_DEFAULT), help="技能 references 目录")
    ap.add_argument("--stage", default=None, help="只查单个 stage（缺省全量 stages/*.json）")
    args = ap.parse_args(argv)
    stages_dir = Path(args.references) / "stages"
    if not stages_dir.is_dir():
        print(f"[schema_linter] stages 目录不存在：{stages_dir}", file=sys.stderr)
        return 2
    paths = sorted(stages_dir.glob("*.json")) if not args.stage else [stages_dir / f"{args.stage}.json"]
    if not paths:
        print(f"[schema_linter] 无可扫 stage 文件：{stages_dir}", file=sys.stderr)
        return 2
    summary = {}
    total = 0
    for p in paths:
        rep = lint_stage(p)
        counts: dict[str, int] = dict.fromkeys(CHECKS, 0)
        for v in rep["violations"]:
            counts[v["check"]] += 1
            print(f"[{rep['stage']}] {v['check']} {v['family']}.{v['field']}: {v['detail']}", file=sys.stderr)
        summary[rep["stage"]] = counts
        total += len(rep["violations"])
    print(json.dumps({"stages": summary, "total": total}, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if total else 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
