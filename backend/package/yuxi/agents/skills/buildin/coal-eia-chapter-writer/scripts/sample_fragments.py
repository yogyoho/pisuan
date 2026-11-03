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
    python sample_fragments.py --stage planning_eia --chapter ch2 --candidates 3 \
        --out state/sample_candidates_ch2.json --content-dir state/candidates_content_ch2
    python sample_fragments.py --stage planning_eia --chapter ch2 --report-id 2201 --out state/sample_fragments_ch2.md
    python sample_fragments.py --stage planning_eia --chapter ch2 --report-id 2201 \
        --per-section --out-dir state/fragment_packs/ch2   # 按 ### 节级逐节切包（bug P1-5：每节派发注入对应节包）
rc：0=成包/候选列出/节包落盘；2=样例库无本章切片或切不出 ### 节（降级范式文档/章包并如实告知用户）；
1=参数/文件错误（含 --report-id 不在候选、--per-section 参数冲突）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^#{2,4} \d", re.MULTILINE)
SECTION_HEADING_RE = re.compile(r"^### (\d[\d.]*) ?(.*)$", re.MULTILINE)
CHAPTER_HEADING_RE = re.compile(r"^## \d[^\n]*", re.MULTILINE)


def top_level_secs(secs: set[str]) -> set[str]:
    """节级口径（卡B「覆盖节数」）：无其它 sec 以「sec.」为前缀扩展者。
    2 被 2.1 扩展=章题、2.1.1 被 2.1.x 扩展=小节；2.1/2.2 无扩展=真节——标题级条目计数含子节虚高（56 vs 实节 8）。"""
    return {s for s in secs if not any(t != s and t.startswith(s + ".") for t in secs)}


def load_bank(references_dir: Path) -> dict:
    path = references_dir / "samples_bank" / "bank_index.json"
    if not path.exists():
        raise FileNotFoundError(f"bank_index 缺失（样例库未编译？先跑 bank_compile.py）: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def pick_report_file(bank: dict, stage: str, chapter: str, report_id: str | None = None) -> tuple[str, str] | None:
    """本章切片文件：(report_id, 相对 references 的文件路径)。report_id 指定时取该报告（范例挑选卡
    用户选定，bug-…交互卡点）；缺省=主导报告（索引条目最多者，章节最完整的代理指标，平局取字典序）。
    无切片/指定报告不在库返回 None。"""
    entries = (bank.get(stage) or {}).get(chapter) or []
    if not entries:
        return None
    per_report: dict[str, list[str]] = {}
    for e in entries:
        per_report.setdefault(str(e.get("report_id", "")), []).append(str(e.get("file", "")))
    rid = report_id or min(per_report, key=lambda r: (-len(per_report[r]), r))
    if rid not in per_report:
        return None
    return rid, sorted(set(per_report[rid]))[0]


def pick_candidates(bank: dict, stage: str, chapter: str, top: int, references_dir: Path) -> list[dict]:
    """top-N 候选摘要（确定性排序：索引条目数降序、report_id 字典序）——范例挑选卡数据面。"""
    entries = (bank.get(stage) or {}).get(chapter) or []
    per_report: dict[str, list[str]] = {}
    for e in entries:
        per_report.setdefault(str(e.get("report_id", "")), []).append(str(e.get("file", "")))
    ranked = sorted(per_report, key=lambda r: (-len(per_report[r]), r))
    out: list[dict] = []
    for rid in ranked[: max(0, top)]:
        secs = {str(e.get("sec", "")) for e in entries if str(e.get("report_id", "")) == rid}
        rel = sorted(set(per_report[rid]))[0]
        p = Path(references_dir) / rel
        chars = len(p.read_text(encoding="utf-8").strip()) if p.exists() else 0
        # 覆盖节数=节级口径（### 级真节数）：标题级条目把 #### 小节也计入，卡面虚高误导选型
        out.append({"report_id": rid, "sections": len(top_level_secs(secs)), "chars": chars, "file": rel})
    return out


def export_candidates(
    bank: dict,
    stage: str,
    chapter: str,
    top: int,
    references_dir: Path,
    out: Path,
    content_dir: Path | None = None,
) -> tuple[list[dict], int]:
    """候选摘要落盘 + 每份候选整章原文导出（范例挑选卡数据面+内容面）。

    content_dir 给定时逐份写 candidate-<i>-<report_id>.md：整章切片原文（方案一：原文展示，
    来源可见——用户通读比对写法质量后再选；卡面摘要仍按 bug-4155 脱敏，摘要与全文分层）。
    候选 JSON 逐份增记 content_file 路径。返回 (候选列表, rc)：rc=0 成功；rc=2 无切片。"""
    cands = pick_candidates(bank, stage, chapter, top, references_dir)
    if not cands:
        return [], 2
    if content_dir is not None:
        content_dir.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(cands, 1):
        if content_dir is None:
            continue
        p = Path(references_dir) / c["file"]
        body = p.read_text(encoding="utf-8").strip() if p.exists() else ""
        head = (
            f"# 范例候选{i} · {stage} {chapter}（{c['sections']} 节 · 约 {c['chars']} 字）\n"
            f"<!-- 候选整章原文（供通读比对后选择；report_id={c['report_id']} · {c['file']}） -->\n"
        )
        f = content_dir / f"candidate-{i}-{c['report_id']}.md"
        f.write_text(head + body + "\n", encoding="utf-8", newline="\n")
        c["content_file"] = str(f)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cands, 0


def clip_at_heading(text: str, max_chars: int) -> str:
    """预算截断：预算内最后一个节标题（##/###/#### 任意级）处下刀，保完整开头节；无标题可断则硬截。"""
    if len(text) <= max_chars:
        return text
    cuts = [m.start() for m in HEADING_RE.finditer(text[:max_chars]) if m.start() > 0]
    cut = cuts[-1] if cuts else max_chars
    return text[:cut].rstrip() + "\n"


def build_pack(
    bank: dict, stage: str, chapter: str, max_chars: int, references_dir: Path, report_id: str | None = None
) -> tuple[str, str, bool]:
    """拼包：(包文本, 主导(或指定) report_id, 是否截断)。无切片/切片文件缺失返回空串。"""
    hit = pick_report_file(bank, stage, chapter, report_id)
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


def split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """按 ### 节级标题切节：返回 (章题行, [(节号, 节文本含标题行与 #### 子节)])。
    同节号重复出现（脏切片）按文档序并包不丢内容；无 ### 节标题返回空清单（薄 stage/脏切片 → 调用方降级章包）。"""
    matches = list(SECTION_HEADING_RE.finditer(text))
    chapter = CHAPTER_HEADING_RE.search(text)
    chapter_line = chapter.group(0).strip() if chapter else ""
    chunks: dict[str, list[str]] = {}
    order: list[str] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sec = m.group(1).strip()
        body = text[m.start() : end].strip()
        if sec not in chunks:
            chunks[sec] = []
            order.append(sec)
        chunks[sec].append(body)
    return chapter_line, [(s, "\n\n".join(chunks[s])) for s in order]


def build_section_packs(
    bank: dict,
    stage: str,
    chapter: str,
    max_chars: int,
    references_dir: Path,
    out_dir: Path,
    report_id: str | None = None,
) -> tuple[list[dict], str]:
    """--per-section：选定（缺省主导）报告整章切片按 ### 节级逐节落盘 <out_dir>/<节号>.md（bug P1-5）。
    每节派发注入对应节包；节包自带包头红线注释 + 章题行上下文；预算按节独立截断（预算内最后一个 #### 小节标题处收口）。
    返回 (节清单 [{sec, chars, file}], report_id)；无切片/切不出节返回 ([], "")。"""
    hit = pick_report_file(bank, stage, chapter, report_id)
    if hit is None:
        return [], ""
    rid, rel = hit
    p = Path(references_dir) / rel
    if not p.exists():
        return [], ""
    chapter_line, sections = split_sections(p.read_text(encoding="utf-8").strip())
    if not sections:
        return [], ""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for sec, body in sections:
        clipped = clip_at_heading(body, max_chars)
        note = f"截断自 {len(body)} 字符（预算内最后一个节标题处）" if len(clipped) < len(body) else "全节"
        head = (
            f"# 样例片段包 · {stage} {chapter} §{sec}（写作参照——禁抄数值/实体入正文，红线「样例/范文禁抄」把守）\n"
            f"<!-- source: bank_index {'选定' if report_id else '主导'}报告 {rid} · {rel} · §{sec} {note} -->\n"
        )
        ctx = f"{chapter_line}\n\n" if chapter_line else ""
        f = out_dir / f"{sec}.md"
        f.write_text(head + ctx + clipped + "\n", encoding="utf-8", newline="\n")
        manifest.append({"sec": sec, "chars": len(clipped), "file": str(f)})
    return manifest, rid


def main() -> int:
    ap = argparse.ArgumentParser(
        description="stage+章节 → samples_bank 同章真实切片包（bug-4147；范例挑选卡候选/取件）"
    )
    default_refs = Path(__file__).resolve().parent.parent / "references"
    ap.add_argument("--references-dir", default=str(default_refs))
    ap.add_argument(
        "--stage", required=True, help="stages/*.json 路径或裸 stage id（如 planning_eia；路径自动取回 id）"
    )
    ap.add_argument("--chapter", required=True, help="章 id，如 ch2（bank_index 章键）")
    ap.add_argument(
        "--out", help="落盘路径（章包/候选 JSON；建议 state/sample_fragments_<ch>.md 或 candidates_<ch>.json）"
    )
    ap.add_argument(
        "--per-section",
        action="store_true",
        help="按 ### 节级逐节切包落盘 --out-dir（bug P1-5：每节派发注入对应节包；与 --candidates/--content-dir 互斥）",
    )
    ap.add_argument("--out-dir", help="节包落盘目录（与 --per-section 同用；建议 state/fragment_packs/<ch>）")
    ap.add_argument("--max-chars", type=int, default=12000, help="包正文字符预算（缺省 12000）")
    ap.add_argument(
        "--candidates", type=int, metavar="N", help="列 top-N 候选摘要 JSON 到 --out（范例挑选卡数据面，不取件）"
    )
    ap.add_argument(
        "--content-dir",
        help="候选逐份整章原文导出目录（范例挑选卡内容面——供用户点开通读比对后再选；与 --candidates 同用）",
    )
    ap.add_argument("--report-id", help="取指定报告的整章切片（范例挑选卡用户选定；缺省=自动主导报告）")
    a = ap.parse_args()
    try:
        bank = load_bank(Path(a.references_dir))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"SAMPLE_FRAGMENTS_FAIL: {e}", file=sys.stderr)
        return 1
    stage = Path(a.stage).stem  # 容错：--stage 传 stages/<id>.json 路径时取回 id（全脚本口径为路径，裸 id 亦收）
    if stage not in bank:
        print(
            f"SAMPLE_FRAGMENTS_FAIL: stage '{a.stage}'（归一为 '{stage}'）不在样例库（顶层键：{'、'.join(bank)}）",
            file=sys.stderr,
        )
        return 1
    if a.per_section:
        if a.candidates or a.content_dir:
            print(
                "SAMPLE_FRAGMENTS_FAIL: --per-section 与 --candidates/--content-dir 互斥（候选卡走章级口径）",
                file=sys.stderr,
            )
            return 1
        if not a.out_dir:
            print("SAMPLE_FRAGMENTS_FAIL: --per-section 需 --out-dir（节包落盘目录）", file=sys.stderr)
            return 1
        if a.report_id:
            valid = {c["report_id"] for c in pick_candidates(bank, stage, a.chapter, 10**9, Path(a.references_dir))}
            if a.report_id not in valid:
                print(
                    f"SAMPLE_FRAGMENTS_FAIL: 候选中无报告 {a.report_id}（先 --candidates 查看在库候选）",
                    file=sys.stderr,
                )
                return 1
        manifest, rid = build_section_packs(
            bank, stage, a.chapter, a.max_chars, Path(a.references_dir), Path(a.out_dir), a.report_id
        )
        if not manifest:
            print(
                f"SAMPLE_FRAGMENTS_EMPTY: {stage}/{a.chapter} 无样例切片或切不出 ### 节——节级降级用章包，如实告知用户",
                file=sys.stderr,
            )
            return 2
        detail = " ".join(f"{m['sec']}={m['chars']}字" for m in manifest)
        print(f"SAMPLE_FRAGMENTS_PER_SECTION_OK: {len(manifest)} 节 → {a.out_dir}（{rid}；{detail}）")
        return 0
    if not a.out:
        print(
            "SAMPLE_FRAGMENTS_FAIL: 需 --out（章包/候选落盘路径）或 --per-section --out-dir（节包目录）",
            file=sys.stderr,
        )
        return 1
    if a.candidates:
        cands, rc = export_candidates(
            bank,
            stage,
            a.chapter,
            a.candidates,
            Path(a.references_dir),
            Path(a.out),
            Path(a.content_dir) if a.content_dir else None,
        )
        if rc == 2:
            print(
                f"SAMPLE_FRAGMENTS_EMPTY: {stage}/{a.chapter} 无样例切片——降级范式文档并如实告知用户", file=sys.stderr
            )
            return 2
        extra = f" · 候选全文 x{len(cands)} → {a.content_dir}" if a.content_dir else ""
        print(f"SAMPLE_CANDIDATES_OK: {len(cands)} 份候选 → {a.out}{extra}（呈用户挑选后 fragment-choice 落账）")
        return 0
    if a.report_id:
        valid = {c["report_id"] for c in pick_candidates(bank, stage, a.chapter, 10**9, Path(a.references_dir))}
        if a.report_id not in valid:
            print(f"SAMPLE_FRAGMENTS_FAIL: 候选中无报告 {a.report_id}（先 --candidates 查看在库候选）", file=sys.stderr)
            return 1
    pack, rid, clipped = build_pack(bank, stage, a.chapter, a.max_chars, Path(a.references_dir), a.report_id)
    if not pack:
        print(
            f"SAMPLE_FRAGMENTS_EMPTY: {stage}/{a.chapter} 无样例切片——降级范式文档并如实告知用户",
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
