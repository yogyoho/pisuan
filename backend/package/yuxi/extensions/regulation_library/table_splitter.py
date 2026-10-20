"""按 <table> 边界把 chunk 内容拆成表格单元（R1 多表识别）。

parse_chunk_unit 只认 chunk 开头一表，4096-token 大 chunk 一段埋多表时其余表全被埋没。
本模块把 content 按闭合的 <table>...</table> 切开：每张表一个独立单元，配最近前置的
表标题行。标题只在「本表开始标签与上一表结束标签」之间的区间内自后向前找：行首
「表N」或续表标记（表N（完）/续表）命中即用，其余行跳过——纯单位行（mg/L、
单位：mg/L）因此自然被越过；区间内无标题用「表?」占位。表格被分块器拦腰切的
残段（无闭合 </table>）丢弃不识别——宁可漏不可错。

纯函数模块，供 enrichment_service 调用。
"""

from __future__ import annotations

import re

from yuxi.utils import logger

_TABLE_BLOCK_RE = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.IGNORECASE | re.DOTALL)
# 表标题行：表1 / 表 2-1，后接标题文字
_TITLE_RE = re.compile(r"^表\s*(\d[\d\-]*)\s*(.*)$")
# 续表标记行：表2（完）/ 表5(续表) / 孤立「续表」
_CONTINUATION_RE = re.compile(r"^表\s*(\d[\d\-]*)\s*[（(](?:完|续表?)[)）]$|^续表$")


def split_table_units(content: str) -> list[dict]:
    """按闭合 <table> 边界把 chunk 内容拆成表格单元。

    Returns:
        [{"unit_no", "title", "unit_type": "table", "table_content"}, ...]，按文档顺序。
    """
    text = content or ""
    blocks = list(_TABLE_BLOCK_RE.finditer(text))
    residuals = len(re.findall(r"<table\b", text, flags=re.IGNORECASE)) - len(blocks)
    if residuals:
        logger.debug(f"split_table_units: 丢弃 {residuals} 个未闭合表格残段（宁可漏不可错）")
    if not blocks:
        return []

    units: list[dict] = []
    last_no = ""
    for i, block in enumerate(blocks):
        region_start = blocks[i - 1].end() if i else 0
        unit_no, title = _find_title(text[region_start : block.start()], last_no)
        units.append({"unit_no": unit_no, "title": title, "unit_type": "table", "table_content": block.group(0)})
        last_no = unit_no
    return units


def _find_title(region: str, last_no: str) -> tuple[str, str]:
    """在表格前置区间内自后向前找标题行，返回 (unit_no, title)。"""
    for line in reversed(region.splitlines()):
        line = line.strip()
        if not line:
            continue
        m = _CONTINUATION_RE.match(line)
        if m:
            base = f"表{m.group(1)}" if m.group(1) else last_no.removesuffix("（续）") or "表?"
            return f"{base}（续）", ""
        m = _TITLE_RE.match(line)
        if m:
            return f"表{m.group(1)}", m.group(2).strip()
    return "表?", ""
