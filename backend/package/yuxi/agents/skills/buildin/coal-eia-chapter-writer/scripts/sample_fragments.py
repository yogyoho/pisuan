#!/usr/bin/env python3
"""样例片段包生成器：stage + 章节 → samples_bank 同章真实切片（派发注入唯一参照来源，bug-4147）。

背景（bug-4147）：写作派发的范式上下文只有 references/paradigms 通用范式文档（模板库），
样例库切片注入在 SKILL.md 里只是契约项，执行时落空——本脚本把「从样例库取同章片段」
变成脚本化必做：选片→按预算截断→落盘，包缺失/为空才降级范式文档。

语料形状与选片口径（确定性，禁随机）：
- bank_index[stage][chN] 是标题级索引条目，同一报告的整章切片文件按其内标题展开成多条
  （bank_compile 语义）；章桶内一报告 ↔ 一个整章文件（<rid>__<N>.md）；
- 主导报告 = 索引条目最多者（章节最完整的代理指标，平局取 report_id 字典序）；
- 包 = 主导报告整章切片原文，超 --max-chars 时在预算内最后一个节标题处截断
  （保住开头完整节；无标题可断则硬截）；
- 片段原文自带溯源标记行（【矿种】…【report_id】【节号】），包不脱敏——数值/实体禁抄由
  SKILL.md 红线（样例实体注册表 + 残留扫描门）在写作侧把守。

CLI 用法：
    python sample_fragments.py --stage planning_eia --chapter ch2 --out state/sample_fragments_ch2.md
rc：0=成包；2=样例库无本章切片（降级范式文档并如实告知用户）；1=参数/文件错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^#{2,4} \d", re.MULTILINE)


def load_bank(references_dir: Path) -> dict:
    path = references_dir / "samples_bank" / "bank_index.json"
    if not path.exists():
        raise FileNotFoundError(f"bank_index 缺失（样例库未编译？先跑 bank_compile.py）: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def pick_report_file(bank: dict, stage: str, chapter: str) -> tuple[str, str] | None:
    """主导报告的本章切片文件：(report_id, 相对 references 的文件路径)。无切片返回 None。"""
    entries = (bank.get(stage) or {}).get(chapter) or []
    if not entries:
        return None
    per_report: dict[str, list[str]] = {}
    for e in entries:
        per_report.setdefault(str(e.get("report_id", "")), []).append(str(e.get("file", "")))
    rid = min(per_report, key=lambda r: (-len(per_report[r]), r))
    return rid, sorted(set(per_report[rid]))[0]


def clip_at_heading(text: str, max_chars: int) -> str:
    """预算截断：预算内最后一个节标题（##/###/#### 任意级）处下刀，保完整开头节；无标题可断则硬截。"""
    if len(text) <= max_chars:
        return text
    cuts = [m.start() for m in HEADING_RE.finditer(text[:max_chars]) if m.start() > 0]
    cut = cuts[-1] if cuts else max_chars
    return text[:cut].rstrip() + "\n"


def build_pack(bank: dict, stage: str, chapter: str, max_chars: int, references_dir: Path) -> tuple[str, str, bool]:
    """拼包：(包文本, 主导 report_id, 是否截断)。无切片/切片文件缺失返回空串。"""
    hit = pick_report_file(bank, stage, chapter)
    if hit is None:
        return "", "", False
    rid, rel = hit
    p = Path(references_dir) / rel
    if not p.exists():
        return "", "", False
    full = p.read_text(encoding="utf-8").strip()
    body = clip_at_heading(full, max_chars)
    clipped = len(body) < len(full)
    note = f"截断自 {len(full)} 字符（预算内最后一个节标题处）" if clipped else "全文"
    head = (
        f"# 样例片段包 · {stage} {chapter}（写作参照——禁抄数值/实体入正文，红线「样例/范文禁抄」把守）\n"
        f"<!-- source: bank_index 主导报告 {rid} · {rel} · {note} -->\n"
    )
    return head + body + "\n", rid, clipped


def main() -> int:
    ap = argparse.ArgumentParser(description="stage+章节 → samples_bank 同章真实切片包（bug-4147）")
    default_refs = Path(__file__).resolve().parent.parent / "references"
    ap.add_argument("--references-dir", default=str(default_refs))
    ap.add_argument("--stage", required=True, help="stage id，如 planning_eia（bank_index 顶层键）")
    ap.add_argument("--chapter", required=True, help="章 id，如 ch2（bank_index 章键）")
    ap.add_argument("--out", required=True, help="包落盘路径（建议 state/sample_fragments_<ch>.md）")
    ap.add_argument("--max-chars", type=int, default=12000, help="包正文字符预算（缺省 12000）")
    a = ap.parse_args()
    try:
        bank = load_bank(Path(a.references_dir))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"SAMPLE_FRAGMENTS_FAIL: {e}", file=sys.stderr)
        return 1
    pack, rid, clipped = build_pack(bank, a.stage, a.chapter, a.max_chars, Path(a.references_dir))
    if not pack:
        print(
            f"SAMPLE_FRAGMENTS_EMPTY: {a.stage}/{a.chapter} 无样例切片——降级范式文档并如实告知用户",
            file=sys.stderr,
        )
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pack, encoding="utf-8", newline="\n")
    print(f"SAMPLE_FRAGMENTS_OK: {out}（主导报告 {rid} · {len(pack)} 字符 · {'预算截断' if clipped else '全文'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
