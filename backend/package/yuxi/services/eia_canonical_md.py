"""eia_canonical_md.py — 环评文件库 canonical md 内核（spec 2026-10-18 方案 B 正源，纯函数模块）。

docx → canonical md：正文与离线产线 prepare_corpus.docx_to_md 逐字节一致（33 份金标准
回归守护，test_eia_canonical_md_goldens.py），唯一差异是封面/扉页区保留为前置区 +
EIA-FRONT-MATTER-END 标记行。前置区 RAW 段落喂 extract_front 与技能 front_extract
（docx-XML 路径）字段全等（2026-10-18 宿主机实证 33/33），front_extract.read_front_paras
的 docx zip 直读自此退役。

规则函数逐行移植自技能三脚本（技能脚本原地保留，离线产线不动，避免双头维护误解由
后续 changelog 说明）：
  - prepare_corpus.py: strip_toc / promote_headings / table_to_gfm / iter_blocks / make_rid
  - front_extract.py:  extract_front（纯函数部分）
  - bank_compile.py:   slice_report / _heading_title（P2 加工切片计数）
docx 病态守卫复用 yuxi.services.docx_guard（悬空关系自动手术，bug-355）。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from yuxi.services.docx_guard import guard_docx_bytes

FRONT_MARKER = "<!-- EIA-FRONT-MATTER-END -->"

# ---------------------------------------------------------------- prepare_corpus 移植

SEC_LINE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*\S|\S)\s*$")
TOC_TAIL_RE = re.compile(r"\s\t?\d{1,3}\s*$")
SENT_PUNCT_RE = re.compile(r"[。；，]")  # 句读标点（顿号「、」除外——真标题可含，见 promote_headings）
BOOK_MARK_RE = re.compile(r"[《》]")
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


def is_policy_conform_title(number: str, title: str) -> bool:
    """书名号豁免：与《规划/法规》符合性分析节是真标题。

    双守卫防反向漏网：节号须含点（法规清单列表段是单号）、题名 ≤60 字。"""
    return "." in number and len(title) <= 60 and BOOK_MARK_RE.search(title) is not None


def promote_headings(body: str) -> str:
    """节号行加 markdown 标题前缀：单段号→##，两段→###，三段+→####（bank SEC_RE 认 ##~####）。

    保守启发式：题名 >30 字、节号 >12 字符或含句读标点（。；，）判为列表段不升级、
    保留原行；顿号不计——真标题如「13.4.9 对太中银铁路、高速公路等…」。
    豁免：多级号书名号符合性分析节（is_policy_conform_title）。"""
    out = []
    for ln in body.splitlines():
        m = SEC_LINE_RE.match(ln.strip())
        if not m:
            out.append(ln)
            continue
        num, title = m.group(1), m.group(2)
        if len(num) > 12 or SENT_PUNCT_RE.search(title):
            out.append(ln)  # 列表段：节号超长或含句读
        elif len(title) <= 30 or is_policy_conform_title(num, title):
            depth = num.count(".")
            prefix = "##" if depth == 0 else ("###" if depth == 1 else "####")
            out.append(f"{prefix} {num} {title}")
        else:
            out.append(ln)  # 超长无书名号：保守保留
    return "\n".join(out)


def table_to_gfm(rows: list[list[str]]) -> str:
    """docx 表 → GFM；列数取 max 补空（杜绝裂表）。"""
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


def make_rid(seq: int, stem: str) -> str:
    """report_id 生成：`{序号:03d}-{ASCII slug}`。

    bank_compile RID_RE = [a-z0-9][a-z0-9-_]*（ASCII 守卫，fullmatch 失败整份跳过）——
    slug 必须 ASCII 小写；纯中文名折叠后为空，`r` 保底；序号前缀天然唯一，截断安全。"""
    ascii_slug = re.sub(r"[^a-z0-9\-_]+", "-", unicodedata.normalize("NFKC", stem).lower()).strip("-")
    return f"{seq:03d}-{ascii_slug or 'r'}"[:60]


# ---------------------------------------------------------------- front_extract 移植（纯函数部分）

SPACE_RE = re.compile(r"[\s　]+")
TITLE_TAIL_RE = re.compile(r"(环境影响报告书|环境影响报告表|环境影响跟踪评价报告书|环境影响后评价报告书|环评报告书)$")
BACK_JOIN_BLOCK_RE = re.compile(r"[：:年月]|^\d")
ORG_LABEL_RE = re.compile(r"^(?:环评|编制|评价)单位[：:]")
ORG_NAME_RE = re.compile(r"(有限公司|研究院|设计院|评估中心|科学研究院|勘查院|集团公司)")
ORG_NOISE_RE = re.compile(r"(项目|矿井|矿区|报告|选煤厂|煤矿$)")
DATE_RE = re.compile(r"[〇零一二三四五六七八九]{4}年(?:[一二三四五六七八九十]{1,3}月)?|\d{4}年(?:\d{1,2}月)?")
PROJECT_NO_RE = re.compile(r"工程编号[：:](\S+)")
SCALE_LINE_RE = re.compile(r"^(?:矿区)?(?:开发)?总规模[：:](\d+(?:\.\d+)?)Mt?/?a?$")
_CJK_DIGITS = str.maketrans(
    {
        "〇": "0",
        "零": "0",
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
    }
)
PROVINCES = (
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 "
    "山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆"
).split()
PROVINCES_BY_LEN = sorted(PROVINCES, key=len, reverse=True)


def _parse_year(fragment: str) -> int | None:
    digits = re.sub(r"\D", "", fragment.translate(_CJK_DIGITS))
    if len(digits) < 4:
        return None
    y = int(digits[:4])
    return y if 2000 <= y <= 2100 else None


def extract_front(paras: list[str]) -> dict:
    """前置区段落 → 封面七字段（与技能 front_extract.extract_front 同一实现）。

    入参约定 RAW 段落（不预归一）；函数内部 SPACE 归一与 read_front_paras 同规。"""
    paras = [p for p in (SPACE_RE.sub("", x) for x in paras) if p]  # 归一与 read_front_paras 同规（全角空格变体）
    title = org_labeled = year = project_no = cover_scale = None
    org_candidates: list[str] = []
    for i, s in enumerate(paras):
        if title is None and len(s) <= 45 and TITLE_TAIL_RE.search(s):
            back: list[str] = []
            for j in range(i - 1, max(-1, i - 4), -1):
                if len(paras[j]) <= 50 and not BACK_JOIN_BLOCK_RE.search(paras[j]):
                    back.insert(0, paras[j])
                else:
                    break
            title = "".join(back) + s
        if year is None and (m := DATE_RE.search(s)):
            year = _parse_year(m.group())
        if project_no is None and (m := PROJECT_NO_RE.search(s)):
            project_no = m.group(1)
        if cover_scale is None and (m := SCALE_LINE_RE.match(s)):
            cover_scale = round(float(m.group(1)), 2)
        if ORG_LABEL_RE.match(s):
            val = ORG_LABEL_RE.sub("", s)
            if val and len(val) <= 50:
                if org_labeled is None:
                    org_labeled = val
                elif val not in org_candidates:
                    org_candidates.append(val)
        elif ORG_NAME_RE.search(s) and not ORG_NOISE_RE.search(s) and len(s) < 50:
            bare = re.sub(r"^(?:建设|环评|编制|评价)单位[：:]", "", s)
            if bare not in org_candidates:
                org_candidates.append(bare)
    org_candidates = [c for c in org_candidates if c != org_labeled][:5]
    province = None
    if title:
        province = next((p for p in PROVINCES_BY_LEN if p in title), None)
    if province is None:
        for s in paras[:6]:
            province = next((p for p in PROVINCES_BY_LEN if s.startswith(p)), None)
            if province:
                break
    return {
        "report_title": title,
        "eia_org": org_labeled,
        "eia_org_candidates": org_candidates,
        "year": year,
        "project_no": project_no,
        "cover_scale_mt_a": cover_scale,
        "province": province,
    }


# ---------------------------------------------------------------- bank_compile 移植（切片内核）

SEC_RE = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\s", re.MULTILINE)


def _heading_title(line: str) -> str:
    """从标题行剥掉井号前缀与节号，余下文本即节标题（如 `## 2 地质特征` → `地质特征`）。"""
    no_hash = re.sub(r"^#{1,6}\s+", "", line)
    return re.sub(r"^\d+(?:\.\d+)*\s+", "", no_hash).strip()


def slice_report(text: str) -> tuple[list[dict], list[str]]:
    """把报告全文切成片：连续同片号的节归并进同一片（子节归父片）。

    返回 ([{chapter, seg, secs}], dup_chapters)：chapter=节号首段，seg=裸切片文本，
    secs=片内节条目 [{sec, title}]；dup_chapters=发生同章多块的章号（已按
    「保留最长块」消解，coal 语料局部编号序列是几行碎片，真章是宏观段）。"""
    matches = list(SEC_RE.finditer(text))
    if not matches:
        return [], []
    slices: list[dict] = []
    cur: dict | None = None
    for m in matches:
        sec = m.group(2)
        chapter = sec.split(".")[0]
        if cur is None or cur["chapter"] != chapter:
            if cur is not None:
                slices.append(cur)
            cur = {"chapter": chapter, "start": m.start(), "secs": []}
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line = text[m.start() : line_end].rstrip("\r")
        cur["secs"].append({"sec": sec, "title": _heading_title(line)})
    if cur is not None:
        slices.append(cur)
    for i, s in enumerate(slices):
        s["end"] = slices[i + 1]["start"] if i + 1 < len(slices) else len(text)
    by_ch: dict[str, list[dict]] = {}
    for s in slices:
        by_ch.setdefault(s["chapter"], []).append(s)
    dup = sorted(ch for ch, blocks in by_ch.items() if len(blocks) > 1)
    kept = [
        blocks[0] if len(blocks) == 1 else max(blocks, key=lambda s: s["end"] - s["start"]) for blocks in by_ch.values()
    ]
    kept.sort(key=lambda s: s["start"])
    for i, s in enumerate(kept):
        end = kept[i + 1]["start"] if i + 1 < len(kept) else len(text)
        s["seg"] = text[s["start"] : end]
        del s["start"]
        del s["end"]
    return kept, dup


# ---------------------------------------------------------------- 本模块新逻辑


@dataclass(frozen=True)
class CanonicalMd:
    """canonical md 产物：md 全文（前置区+标记+正文）、RAW 前置段落、字符数。"""

    md: str
    front_paras: list[str]
    chars: int


def docx_bytes_to_canonical_md(data: bytes, label: str = "") -> CanonicalMd | None:
    """docx bytes → canonical md；零节号标题返回 None（调用方记 md_status=failed）。

    前置段落走 RAW 变体（与 front_extract.read_front_paras 逐字符同构）：
    python-docx 块序、含表格单元段落、不做 NFKC、cap=300——extract_front 内部
    自做 SPACE 归一，故与技能金标准字段全等（33/33 实证）。
    病态 docx 经 guard_docx_bytes（悬空关系自动手术）；不可救病类 ValueError 透出。
    """
    from io import BytesIO

    from docx import Document

    guarded = guard_docx_bytes(data, label)
    doc = Document(BytesIO(guarded))
    parts: list[str] = []
    raw_paras: list[str] = []
    boundary_hit = False
    for block in iter_blocks(doc):
        if block.__class__.__name__ == "Paragraph":
            t = unicodedata.normalize("NFKC", block.text).strip()
            if t:
                parts.append(t)
            if not boundary_hit and len(raw_paras) < 300:
                raw = block.text.strip()
                if raw:
                    if SEC_LINE_RE.match(raw):
                        boundary_hit = True
                    else:
                        raw_paras.append(raw)
        else:
            rows = [[c.text for c in row.cells] for row in block.rows]
            gfm = table_to_gfm(rows)
            if gfm:
                parts.append(gfm)
            if not boundary_hit:
                for row in block.rows:
                    for cell in row.cells:
                        t = cell.text.strip()
                        if t and len(raw_paras) < 300:
                            raw_paras.append(t)
    # 先剔目录后升标题：目录行行首为数字，升标题加 # 前缀后 is_toc_line 不再匹配（bug-398 A1）
    text = promote_headings(strip_toc("\n\n".join(parts)))
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#") and SEC_LINE_RE.match(ln.lstrip("#").strip()):
            front_lines = [x for x in lines[:i] if x.strip()]
            body = "\n".join(lines[i:])
            head = ("\n\n".join(front_lines) + "\n\n") if front_lines else ""
            md = f"{head}{FRONT_MARKER}\n\n{body}\n"
            return CanonicalMd(md=md, front_paras=raw_paras, chars=len(md))
    return None


def split_canonical_md(md: str) -> tuple[list[str], str]:
    """canonical md → (前置区非空行, 正文含末换行)；正文即 source.md 等价物。"""
    front_part, _, body = md.partition(FRONT_MARKER)
    front = [ln for ln in front_part.splitlines() if ln.strip()]
    return front, body.lstrip("\n")
