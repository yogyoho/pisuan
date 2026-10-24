#!/usr/bin/env python3
"""文风基准生成：从 samples_bank/<stage>/slices/ 实测每章指标，产出 style_targets/<stage>.json。

口径（与 .wolf/writing-test/style_compare.py 同源）：
- eff：剥 HTML 注释、#{}[] 标记符与全部空白后的字符
- 正文：剥表格行（^|...|$）后的文本；数字密度与均句长只算正文
- 均句长：正文按 。；！？ 分句、句长>4 计，取均有效字
- 表密度：表行数 / 全文 eff × 10000
- 文表联动：正文「由表|见表|详见表|如表」次数；下限 = max(1, round(表格块数×0.5))
基准带：下限 = 实测×0.8，上限 = 实测×1.25（一位小数）。

章目录对齐纪律：只认 references/stages/<stage>.json 章清单目录（ch1..ch13）；
bank 中清单外目录是切片算法切出的 OCR 噪声碎段（ch0/ch0101/ch1600 等，n=1、首标题乱码），
一律忽略并在 ignored_dirs 上报，严禁按目录名猜测归章。

CLI：
    python style_targets.py --stage planning_eia [--bank DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# AI 腔禁用词（2026-10-24 横城 B 测试实测裁定，AI 稿 30 处 vs 原文 6 处）
BANNED_PHRASES = [
    "总体而言", "值得注意", "至关重要", "旨在", "重要意义", "换言之",
    "毋庸置疑", "不言而喻", "众所周知", "不难发现", "进一步凸显",
]

_COMMENT = (
    "文风基准（chapter-writer Task 2 生成）：各值来自 samples_bank 实测（下限=实测×0.8，上限=实测×1.25）；"
    "数字密度/均句长的分母是正文（剥表格行）有效字，表密度分母是全文有效字；"
    "fig_table_ref_min 为该章单份报告正文文表引用（由表/见表/详见表/如表）的最低次数（单份平均×0.5，地板 1）；"
    "status=ABSENT 表示 bank 无该章切片，chapgate 对 ABSENT 章跳过对应规则并如实上报。"
)


def _eff(t: str) -> str:
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"[#{}\[\]]", "", t)
    return re.sub(r"\s", "", t)


def _strip_tables(t: str) -> str:
    return re.sub(r"^\|.+$", "", t, flags=re.M)


def _metrics(text: str) -> dict:
    body = _strip_tables(text)
    eff = len(_eff(text))
    body_e = _eff(body)
    body_eff = len(body_e)
    sents = [s for s in re.split(r"[。；！？]", body_e) if len(s) > 4]
    avg_sent = sum(len(s) for s in sents) / max(1, len(sents))
    nums = len(re.findall(r"\d+(?:\.\d+)?", body_e))
    table_rows = len(re.findall(r"^\|.+\|$", text, flags=re.M))
    table_blocks = len(re.findall(r"(?:^\|.+\|$\n?)+", text, flags=re.M))
    fig_refs = len(re.findall(r"由表|见表|详见表|如表", body_e))
    return {
        "eff": eff,
        "avg_sent": avg_sent,
        # 数字密度分母=正文有效字（表格行数字已由表密度体现，不双计）
        "num_per_k": nums / body_eff * 1000 if body_eff else 0.0,
        "tbl_per_10k": table_rows / eff * 10000 if eff else 0.0,
        "table_rows": table_rows,
        "table_blocks": table_blocks,
        "fig_refs": fig_refs,
    }


def _band(x: float) -> dict:
    return {"obs": round(x, 1), "min": round(x * 0.8, 1), "max": round(x * 1.25, 1)}


def generate(stage: str, bank_dir: Path, stage_json: Path) -> dict:
    st = json.loads(Path(stage_json).read_text(encoding="utf-8"))
    chapter_ids = list(st["chapters"].keys())
    slices = Path(bank_dir) / "slices"
    ignored = []
    if slices.is_dir():
        ignored = sorted(p.name for p in slices.iterdir() if p.is_dir() and p.name not in chapter_ids)
    chapters: dict[str, dict] = {}
    for cid in chapter_ids:
        cdir = slices / cid
        if not cdir.is_dir():
            chapters[cid] = {"status": "ABSENT"}
            continue
        text = "".join(f.read_text(encoding="utf-8") for f in sorted(cdir.glob("*.md")))
        n_files = max(1, len(list(cdir.glob("*.md"))))
        m = _metrics(text)
        chapters[cid] = {
            "status": "OK",
            "effective_chars": m["eff"],
            "table_rows": m["table_rows"],
            "table_blocks": m["table_blocks"],
            "fig_refs": m["fig_refs"],
            # 文表引用是单报告行为：下限按单份平均×0.5（总量口径会得出数百次的不可能下限）
            "fig_table_ref_min": max(1, round(m["fig_refs"] / n_files * 0.5)),
            "avg_sent_len": _band(m["avg_sent"]),
            "num_per_k": _band(m["num_per_k"]),
            "tbl_per_10k": _band(m["tbl_per_10k"]),
        }
    return {
        "_comment": _COMMENT,
        "stage": stage,
        "banned_phrases": BANNED_PHRASES,
        "chapters": chapters,
        "ignored_dirs": ignored,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="从 bank 实测生成文风基准 style_targets/<stage>.json")
    refs = Path(__file__).resolve().parent.parent / "references"
    ap.add_argument("--stage", required=True)
    ap.add_argument("--bank", default=str(refs / "samples_bank"))
    ap.add_argument("--stage-json", default=str(refs / "stages"))
    ap.add_argument("--out", default=str(refs / "style_targets"))
    a = ap.parse_args()
    result = generate(a.stage, Path(a.bank) / a.stage, Path(a.stage_json) / f"{a.stage}.json")
    out = Path(a.out) / f"{a.stage}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = sum(1 for c in result["chapters"].values() if c["status"] == "OK")
    n = len(result["chapters"])
    print(f"written {out} | chapters OK={ok} ABSENT={n - ok} | ignored_dirs={len(result['ignored_dirs'])}")
    if result["ignored_dirs"]:
        print(f"IGNORED_DIRS(碎段噪声，未参与基准): {' '.join(result['ignored_dirs'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
