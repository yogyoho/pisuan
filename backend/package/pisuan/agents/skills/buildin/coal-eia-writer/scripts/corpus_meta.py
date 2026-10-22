"""语料第1层元数据 + 附件必备清单编译器（vibe 2026-10-08-corpus-meta-and-attachment-checklist）。

输入只依赖已入库资产：references/samples_bank/<stage>/slices/** 切片 + 人工核正
corpus_meta_annotations.json（省/年份/规模的人工判定，basis=manual）。输出两产物且幂等
（无墙钟时间戳，sort_keys + 换行归一，对齐 bank_compile 裁决）。

边界：附件清单是案例层频次统计（见产物内 provenance_note），不构成法规依据；
现行/废止判定属 standards_index 时效字段（部分二），本脚本不涉及。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

PROVINCES = (
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 "
    "山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆"
).split()

STANDARD_CODE_RE = re.compile(r"(?:HJ/T|HJ|DB\d{1,2}/|GB(?:/\d+)?)\s?\d{1,5}(?:\.\d+)*\s?[-—–]\s?(?:\d{4}|\d{2})")

SCALE_RE = re.compile(
    r"(设计生产能力|生产规模|建设规模|设计规模|产能|总规模)"
    r"[^。；\n]{0,20}?(\d+(?:\.\d+)?)\s*(万t/a|万t/年|万吨/年|Mt/a)"
)
_UNIT_TO_MT = {"万t/a": 0.01, "万t/年": 0.01, "万吨/年": 0.01, "Mt/a": 1.0}

ANNEX_BARE_RE = re.compile(r"^附\s*[录件]\s*[:：]?\s*$")
ANNEX_INLINE_RE = re.compile(r"^附\s*[录件]\s*\d{1,3}(?:\s*[:：、.]|\s)\s*(.+)$")
ANNEX_NUM_ITEM_RE = re.compile(r"^\(?(\d{1,3})[)）]?[、.：:，,]?\s*(.+)$")
ANNEX_ITEM_CAP = 100

_DOCNO_GROUP_RE = re.compile(r"[（(][^（）()]*〔[^（）()]*[)）]|[（(][^（）()]*\d{4}[^（）()]*[)）]")
_TAIL_DOCNO_RE = re.compile(r"[,，、;；\s]*[一-鿿a-zA-Z0-9]*[〔\[]\d{2,4}[〕\]]\d{1,5}\s*号?")

DELEGATE_RE = re.compile(
    r"委托\s*([^，。；、（）()《》\s]{4,30}?(?:有限公司|研究院|设计院|评估中心|科学研究院|勘查院|中心|大学|学院))\s*(?:编制|开展)"
)
ORG_SENT_NOISE_RE = re.compile(r"(公告|第二次|基本|批复)")

PROVENANCE_NOTE = (
    "案例层统计：附件必备项为已批复语料在本 stage 内的出现率结论，不构成法规依据；法规必备性以条款库/标准库为准。"
)


def normalize_standard(code: str) -> str:
    return code.upper().replace(" ", "").replace("—", "-").replace("–", "-")


def extract_standards(text: str) -> list[str]:
    return sorted({normalize_standard(m) for m in STANDARD_CODE_RE.findall(text)})


def detect_province(text: str, ann: dict | None = None, front: dict | None = None) -> dict:
    """manual 注 > cover 封面（front_extract 标题/首段命中）> 频次胜者（≥3 且超次名两倍）> needs_review（带候选）。"""
    if ann and ann.get("province"):
        return {"value": ann["province"], "basis": "manual"}
    if front and front.get("province"):
        return {"value": front["province"], "basis": "cover"}
    counts = {p: n for p in PROVINCES if (n := text.count(p))}
    if not counts:
        return {"value": None, "basis": "needs_review", "candidates": []}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top, n = ranked[0]
    if n >= 3 and (len(ranked) == 1 or n > ranked[1][1] * 2):
        return {"value": top, "basis": "regex"}
    return {"value": None, "basis": "needs_review", "candidates": sorted(counts)}


def normalize_item(name: str) -> str:
    name = _DOCNO_GROUP_RE.sub("", name)
    name = _TAIL_DOCNO_RE.sub("", name)
    return re.sub(r"\s+", " ", name.strip("；;,，.。、：: "))


def extract_annex_items(text: str) -> list[str]:
    items: list[str] = []
    collecting = False
    for line in text.splitlines():
        s = line.strip()
        if ANNEX_BARE_RE.match(s):
            collecting = True
            continue
        if collecting:
            m = ANNEX_NUM_ITEM_RE.match(s)
            if m:
                items.append(normalize_item(m.group(2)))
                if len(items) >= ANNEX_ITEM_CAP:
                    collecting = False
                continue
            if s:
                collecting = False
        m = ANNEX_INLINE_RE.match(s)
        if m:
            items.append(normalize_item(m.group(1)))
    return [it for it in items if it]


def extract_scale(text: str) -> dict:
    """单值一致 → {value, basis=regex}；多值分歧 → {basis=needs_review, candidates}。"""
    seen: list[tuple[str, float]] = []
    for label, num, unit in SCALE_RE.findall(text):
        v = round(float(num) * _UNIT_TO_MT[unit], 2)
        if v not in {x[1] for x in seen}:
            seen.append((label, v))
        if len(seen) >= 5:
            break
    if not seen:
        return {"basis": "needs_review", "candidates": []}
    if len(seen) == 1:
        return {"value": seen[0][1], "basis": "regex"}
    return {"basis": "needs_review", "candidates": [{"label": lb, "value": v} for lb, v in seen]}


def delegate_org(text: str) -> str | None:
    """正文委托编制句 → 环评机构（cover 标签行缺席时的第二层）；噪声句剔除，频次胜者。"""
    counts: Counter = Counter()
    for sent in re.split(r"[。；;\n]", text):
        if ORG_SENT_NOISE_RE.search(sent):
            continue
        if m := DELEGATE_RE.search(sent):
            counts[m.group(1)] += 1
    return counts.most_common(1)[0][0] if counts else None


def build_corpus_meta(slices_root: Path, annotations: dict, front: dict | None = None) -> dict:
    """按 rid 聚合全部切片再判定（省/标准/规模是整报告字段，逐片算会被后片覆盖）。"""
    by_rid: dict[str, list] = {}
    for stage_dir in sorted(p for p in slices_root.iterdir() if p.is_dir()):
        for f in sorted(stage_dir.glob("slices/**/*.md")):
            rid = f.name.split("__")[0]
            entry = by_rid.setdefault(rid, [stage_dir.name, ""])
            entry[1] += f.read_text(encoding="utf-8")
    reports: dict[str, dict] = {}
    for rid, (stage, text) in sorted(by_rid.items()):
        r: dict = {"stage": stage}
        ann = annotations.get(rid, {})
        front_entry = (front or {}).get(rid) or {}
        if ann.get("scale_mt_a") is not None:
            r["scale_mt_a"], r["scale_basis"] = ann["scale_mt_a"], "manual"
        else:
            sc = extract_scale(text)
            r["scale_basis"] = sc["basis"]
            if sc["basis"] == "regex":
                r["scale_mt_a"] = sc["value"]
            else:
                r["scale_candidates"] = sc["candidates"]
                if front_entry.get("cover_scale_mt_a") is not None:
                    v = round(float(front_entry["cover_scale_mt_a"]), 2)
                    if v in {c["value"] for c in r["scale_candidates"]}:  # 等值去重：候选改挂封面标签
                        for c in r["scale_candidates"]:
                            if c["value"] == v:
                                c["label"] = "封面总规模"
                    else:
                        r["scale_candidates"].append({"label": "封面总规模", "value": v})
        prov = detect_province(text, ann, front_entry)
        r["province"], r["province_basis"] = prov["value"], prov["basis"]
        if prov.get("candidates"):
            r["province_candidates"] = prov["candidates"]
        if ann.get("year_hint") is not None:
            r["year_hint"], r["year_basis"] = ann["year_hint"], "manual"
        elif front_entry.get("year"):
            r["year_hint"], r["year_basis"] = front_entry["year"], "cover"
        if front_entry.get("report_title"):
            r["report_title"], r["report_title_basis"] = front_entry["report_title"], "cover"
        else:
            r["report_title_basis"] = "needs_review"
        if front_entry.get("eia_org"):
            r["eia_org"], r["eia_org_basis"] = front_entry["eia_org"], "cover"
        elif org := delegate_org(text):
            r["eia_org"], r["eia_org_basis"] = org, "body"
        else:
            r["eia_org"], r["eia_org_basis"] = None, "needs_review"
            if front_entry.get("eia_org_candidates"):
                r["eia_org_candidates"] = front_entry["eia_org_candidates"]
        if front_entry.get("project_no"):
            r["project_no"] = front_entry["project_no"]
        r["standards_cited"] = extract_standards(text)
        reports[rid] = r
    return {"schema": 2, "reports": reports}


def build_attachment_checklist(slices_root: Path) -> dict:
    stages: dict[str, dict] = {}
    for stage_dir in sorted(p for p in slices_root.iterdir() if p.is_dir()):
        per_rid: dict[str, set] = {}
        for f in sorted(stage_dir.glob("slices/**/*.md")):
            rid = f.name.split("__")[0]
            per_rid.setdefault(rid, set()).update(extract_annex_items(f.read_text(encoding="utf-8")))
        base = [r for r, its in per_rid.items() if its]
        n = len(base)
        counts: Counter = Counter()
        for its in per_rid.values():
            counts.update(its)
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        entry: dict = {"base_reports": n, "rids_without_items": sorted(set(per_rid) - set(base))}
        if n < 5:
            entry["insufficient_base"] = True
            entry["observed"] = [
                {"item": it, "freq": round(c / n, 4) if n else 0.0, "n_reports": c} for it, c in ranked
            ]
        else:
            for tier, lo in (("required", 0.8), ("common", 0.3)):
                entry[tier] = [
                    {"item": it, "freq": round(c / n, 4), "n_reports": c}
                    for it, c in ranked
                    if lo <= c / n and (lo == 0.8 or c / n < 0.8)
                ]
        stages[stage_dir.name] = entry
    return {"provenance_note": PROVENANCE_NOTE, "stages": stages}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="编译语料元数据与附件必备清单（幂等）")
    ap.add_argument("--slices-root", default=str(SCRIPTS_DIR.parent / "references" / "samples_bank"))
    ap.add_argument("--annotations", default=None, help="默认 slices-root 下 corpus_meta_annotations.json")
    ap.add_argument(
        "--front-matter",
        default=None,
        help="默认 references/samples_bank 下 front_matter.json；rid 为目录排序位，跨库复用需防 rid 碰撞",
    )
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)
    root = Path(args.slices_root)
    ann_path = Path(args.annotations) if args.annotations else root / "corpus_meta_annotations.json"
    annotations = json.loads(ann_path.read_text(encoding="utf-8")) if ann_path.exists() else {}
    front_path = (
        Path(args.front_matter)
        if args.front_matter
        else SCRIPTS_DIR.parent / "references" / "samples_bank" / "front_matter.json"  # 勘误：指向提交物位置
    )
    front = json.loads(front_path.read_text(encoding="utf-8")) if front_path.exists() else {}
    out_dir = Path(args.out_dir) if args.out_dir else root
    docs = {
        "corpus_meta.json": build_corpus_meta(root, annotations, front),
        "attachment_checklist.json": build_attachment_checklist(root),
    }
    for name, doc in docs.items():
        (out_dir / name).write_text(
            json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    reports = docs["corpus_meta.json"]["reports"]
    by_basis = Counter(r["province_basis"] for r in reports.values())
    print(
        f"corpus_meta: {len(reports)} report(s), "
        f"province cover={by_basis.get('cover', 0)} regex={by_basis.get('regex', 0)} "
        f"manual={by_basis.get('manual', 0)} needs_review={by_basis.get('needs_review', 0)}"
    )
    for stage, entry in docs["attachment_checklist.json"]["stages"].items():
        mark = " [insufficient_base]" if entry.get("insufficient_base") else ""
        print(
            f"checklist {stage}: base={entry['base_reports']} "
            f"required={len(entry.get('required', []))} common={len(entry.get('common', []))}{mark}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
