"""跨页断表合并：修复逐页转写 OCR 产生的续表碎片（纯函数，无 IO）。

逐页转写的 PDF 表格跨页时会产生独立 `<table>` 碎片，带「表N（续）/续表N」标记
与逐字重复的表头。本模块在文档装配后将碎片合并回完整表格；规则保守、
fail-open——无法确信是同一张表时一律不合并。
"""

import re
import unicodedata

TABLE_BLOCK_RE = re.compile(r"<table\b[^>]*>[\s\S]*?</table>", re.IGNORECASE)
_FIRST_ROW_RE = re.compile(r"<tr\b[^>]*>[\s\S]*?</tr>", re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>([\s\S]*?)</t[dh]>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

# 表间允许出现的行：续表标记（表1（续）/续表1/表 1-2 (续)）与页码（12 / - 3 - / 第 2 页）
_CONTINUATION_MARK_RE = re.compile(r"^(?:续\s*表\s*\S+|表\s*[\w.．\-—]+\s*[（(]\s*续\s*[）)])$")
_PAGE_NO_RE = re.compile(r"^(?:\d{1,4}|[-–—\s]*\d+[-–—\s]*|第\s*\d+\s*页)$")

# OCR 易混字符折叠（仅用于表头比对，I/i/l 与全角竖线常被混识为 1）
_HEADER_FOLD = str.maketrans({"I": "1", "i": "1", "l": "1", "｜": "1"})


def merge_split_tables(md: str) -> tuple[str, int]:
    """合并文档内跨页断裂的 HTML 表格，返回 (合并后 markdown, 合并次数)。"""
    matches = list(TABLE_BLOCK_RE.finditer(md))
    if len(matches) < 2:
        return md, 0

    parts: list[str] = []
    prev_end = matches[0].end()
    prev_html = matches[0].group(0)
    merged_count = 0

    for current in matches[1:]:
        gap = md[prev_end : current.start()]
        gap_lines = [line.strip() for line in gap.strip().splitlines() if line.strip()]
        has_marker = any(_CONTINUATION_MARK_RE.match(line) for line in gap_lines)
        # 间隙必须只含标记/页码/空白；且须有续标记或表头一致才允许合并
        gap_clean = has_marker or all(
            _CONTINUATION_MARK_RE.match(line) or _PAGE_NO_RE.match(line) for line in gap_lines
        )
        rows_match = bool(gap_clean) and _header_cells(prev_html) == _header_cells(current.group(0))

        if not gap_clean or not (has_marker or rows_match):
            parts.append(prev_html)
            parts.append(gap)
            prev_end = current.end()
            prev_html = current.group(0)
            continue

        continuation = current.group(0)
        if rows_match:
            continuation = _drop_first_row(continuation)
        prev_html = _append_rows(prev_html, continuation)
        prev_end = current.end()
        merged_count += 1

    parts.append(prev_html)
    return "".join(parts), merged_count


def _header_cells(table_html: str) -> list[str]:
    """提取表格首行的归一化单元格文本（空表返回 []）。"""
    first_row = _FIRST_ROW_RE.search(table_html)
    if not first_row:
        return []
    return [_normalize_cell(cell) for cell in _CELL_RE.findall(first_row.group(0))]


def _normalize_cell(text: str) -> str:
    plain = _TAG_RE.sub("", text)
    folded = unicodedata.normalize("NFKC", plain).translate(_HEADER_FOLD)
    return re.sub(r"\s+", "", folded)


def _drop_first_row(table_html: str) -> str:
    row = _FIRST_ROW_RE.search(table_html)
    if not row:
        return table_html
    return table_html[: row.start()] + table_html[row.end() :]


def _append_rows(prev_html: str, continuation_html: str) -> str:
    """把续片表体行追加到前表（续片标记行与间隙由调用方丢弃）。"""
    continuation_inner = re.sub(r"^<table\b[^>]*>|</table>\s*$", "", continuation_html.strip(), flags=re.IGNORECASE)
    prev_inner = re.sub(r"</table>\s*$", "", prev_html, flags=re.IGNORECASE)
    return prev_inner + continuation_inner + "</table>"
