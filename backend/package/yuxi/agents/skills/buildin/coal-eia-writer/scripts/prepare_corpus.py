#!/usr/bin/env python3
"""prepare_corpus.py — 样例语料 docx → bank_compile 输入格式（hardening-design spec §五 解析边界）。

输入：<语料目录>/*.docx（41 份真实环评报告书）
输出：<workdir>/<report_id>/source.md（UTF-8、节号标题 ##/###/#### 化、GFM 表格）
      + <workdir>/manifest.json 草稿（report_id/stage/mineral/file_name——stage 人工过目后定稿）
用法：
  python -X utf8 prepare_corpus.py --corpus-dir <语料目录> --workdir <输出目录> [--census <census.json>]
边界：
  - 节号标题：正文行「数字(.数字)* + 空白 + 题名」（census 实测 679 标题仅 81 个有 style 标记，正文行匹配为主）
  - 目录页剔除：「节号+题+尾随页码」行连续 ≥3（行间空行不打断累计）判为目录区段整段剔除；
    须在 promote_headings 之前执行（升标题后行首为 #，目录形态失效）
  - 表格：docx table → GFM，列数取 max 补空（杜绝裂表）
  - 范围裁剪：首个节号标题之前的内容（封面/编制单位页）整体丢弃（目录区段已先行剔除）
  - 解析失败：逐份 stderr 警告 + 跳过（bank_compile 既有惯例）
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SEC_LINE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*\S|\S)\s*$")
TOC_TAIL_RE = re.compile(r"\s\t?\d{1,3}\s*$")
SENT_PUNCT_RE = re.compile(r"[。；，]")  # 句读标点（顿号「、」除外——真标题可含，见 promote_headings）
GFM_SEP = "|"


def is_toc_line(line: str) -> bool:
    """目录行：节号标题形态 + 尾随独立页码。"""
    m = SEC_LINE_RE.match(line.strip())
    if not m:
        return False
    return bool(TOC_TAIL_RE.search(line.rstrip())) and not line.rstrip().endswith(tuple("。；：，"))


def strip_toc(text: str) -> str:
    """目录区段剔除：≥3 行目录行（行间空行不打断累计）→ 整段剔除（含夹缝空行）。

    正文标题无页码不受影响；正文空行是合法段落分隔，除紧邻被剔除区段外均保留。"""
    out: list[str] = []
    run: list[str] = []  # 目录区段缓冲（目录行 + 夹缝空行，裁决时同生共死）
    toc_count = 0
    for ln in text.splitlines():
        if is_toc_line(ln):
            run.append(ln)
            toc_count += 1
        elif ln.strip():
            if toc_count >= 3:
                pass  # 丢弃目录区段（夹缝空行随段剔）
            else:
                out.extend(run)
            run.clear()
            toc_count = 0
            out.append(ln)
        elif toc_count:
            run.append(ln)  # 区段进行中的空行 → 夹缝缓冲
        else:
            out.append(ln)  # 区段外空行 → 合法段落分隔，保留
    if toc_count < 3:
        out.extend(run)
    return "\n".join(out)


def promote_headings(body: str) -> str:
    """节号行加 markdown 标题前缀：单段号→##，两段→###，三段+→####（bank SEC_RE 认 ##~####）。

    保守启发式（正文编号列表段识别，bug-398 第三层）：题名 >30 字或含句读标点（。；，）
    判为列表段不升级、保留原行；顿号不计——真标题如「13.4.9 对太中银铁路、高速公路等…」。
    漏网的短清单项（如「3 断层保护煤柱」）Task 4 实跑统计后人工处置。"""
    out = []
    for ln in body.splitlines():
        m = SEC_LINE_RE.match(ln.strip())
        if m and len(m.group(1)) <= 12 and len(m.group(2)) <= 30 and not SENT_PUNCT_RE.search(m.group(2)):
            depth = m.group(1).count(".")
            prefix = "##" if depth == 0 else ("###" if depth == 1 else "####")
            out.append(f"{prefix} {m.group(1)} {m.group(2)}")
        else:
            out.append(ln)
    return "\n".join(out)


def table_to_gfm(rows: list[list[str]]) -> str:
    """docx 表 → GFM；列数取 max 补空。"""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [list(r) + [""] * (width - len(r)) for r in rows]
    norm = [[c.replace("\n", " ").replace("|", "／").strip() for c in r] for r in norm]
    head = GFM_SEP + GFM_SEP.join(norm[0]) + GFM_SEP
    sep = GFM_SEP + GFM_SEP.join(["---"] * width) + GFM_SEP
    body = "\n".join(GFM_SEP + GFM_SEP.join(r) + GFM_SEP for r in norm[1:])
    return "\n".join([head, sep, body])


def iter_blocks(doc):
    """docx body 有序遍历（Paragraph/Table 混排；版本无关，不走 iter_inner_content）。"""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def docx_to_md(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts: list[str] = []
    for block in iter_blocks(doc):
        if block.__class__.__name__ == "Paragraph":
            t = unicodedata.normalize("NFKC", block.text).strip()
            if t:
                parts.append(t)
        else:
            rows = [[c.text for c in row.cells] for row in block.rows]
            gfm = table_to_gfm(rows)
            if gfm:
                parts.append(gfm)
    # 先剔目录后升标题：目录行行首为数字，升标题加 # 前缀后 is_toc_line 不再匹配（bug-398 A1）
    text = promote_headings(strip_toc("\n\n".join(parts)))
    # 范围裁剪：首个节号标题行之前的内容（封面/编制单位页）丢弃
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#") and SEC_LINE_RE.match(ln.lstrip("#").strip()):
            return "\n".join(lines[i:])
    return ""  # 零节号标题 → 空串（main 侧按「零节号标题跳过」处理）


def make_rid(seq: int, stem: str) -> str:
    """report_id 生成：`{序号:03d}-{ASCII slug}`。

    bank_compile RID_RE = [a-z0-9][a-z0-9-_]*（ASCII 守卫，fullmatch 失败整份跳过）——
    slug 必须 ASCII 小写；纯中文名折叠后为空，`r` 保底；序号前缀天然唯一，截断安全。"""
    ascii_slug = re.sub(r"[^a-z0-9\-_]+", "-", unicodedata.normalize("NFKC", stem).lower()).strip("-")
    return f"{seq:03d}-{ascii_slug or 'r'}"[:60]


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="语料 docx → bank_compile 输入（source.md + manifest 草稿）")
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--census", default=None, help="corpus-census/census.json——继承普查元数据")
    args = ap.parse_args(argv)
    corpus, workdir = Path(args.corpus_dir), Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    census = {}
    if args.census and Path(args.census).is_file():
        census = {Path(e["file"]).stem: e for e in json.loads(Path(args.census).read_text(encoding="utf-8"))}
    manifest, ok = [], 0
    for seq, docx in enumerate(sorted(corpus.glob("*.docx")), start=1):
        rid = make_rid(seq, docx.stem)
        # 逐份解析失败：警告+跳过（bank_compile 既有惯例）
        try:
            md = docx_to_md(docx)
        except Exception as exc:  # noqa: BLE001
            print(f"[prepare_corpus] {docx.name} 解析失败——跳过：{exc}", file=sys.stderr)
            continue
        if not md:
            print(f"[prepare_corpus] {docx.name} 零节号标题——跳过", file=sys.stderr)
            continue
        d = workdir / rid
        d.mkdir(exist_ok=True)
        (d / "source.md").write_text(md + "\n", encoding="utf-8", newline="\n")
        meta = census.get(docx.stem, {})
        manifest.append(
            {
                "report_id": rid,
                "stage": "",
                "mineral": "coal",
                "file_name": docx.name,
                "chars": meta.get("chars", len(md)),
            }
        )
        ok += 1
        print(f"[prepare_corpus] {docx.name} -> {rid}（{len(md)} chars）")
    (workdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"PREPARED: {ok} report(s) -> {workdir}")
    return 0 if ok else 1


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
