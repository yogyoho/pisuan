"""分类编码表（taxonomy）结构化抽取：HTML 表 → {类别代码, 名称, 含义} 行。

面向 GB/T 21010 类「分类学表」：一级类/二级类两段式表头、rowspan/colspan 合并单元格、
含义列在行末。正则取行取格 + 占位网格展开（rowspan 的文本自然延续到后续行），零新依赖。

行抽取规则：
- 表头行（所有非空单元格都是 码/名/义/一级类/二级类 等纯表头词）不出行；
- 数据行取第一个形如 2~4 位数字的单元格为 code，其后第一个非空单元格为 name，
  最末非空单元格为 meaning；parent_code = code 前 2 位（二级类 011 → 一级类 01）；
- 仅支持数字编码（当前目标：GB/T 21010 地类编码）；字母编码的表不出行。
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import Any

_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TD_RE = re.compile(r"<td\b([^>]*)>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_ROWSPAN_RE = re.compile(r'rowspan\s*=\s*"?\s*(\d+)', re.IGNORECASE)
_COLSPAN_RE = re.compile(r'colspan\s*=\s*"?\s*(\d+)', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_CODE_RE = re.compile(r"^\d{2,4}$")
_HEADER_WORDS = {"编码", "名称", "含义", "一级类", "二级类", "三大类", "类型编码", "类型名称", "类别代码"}


def _clean_cell(html: str) -> str:
    return _TAG_RE.sub("", html).replace("&nbsp;", " ").strip()


def _attr_span(attrs: str, name: str) -> int:
    m = (_ROWSPAN_RE if name == "rowspan" else _COLSPAN_RE).search(attrs)
    return int(m.group(1)) if m else 1


def _parse_cell_rows(table_html: str) -> list[list[tuple[int, str, int]]]:
    """每行 → [(colspan, 文本, rowspan)]。"""
    out = []
    for tr in _TR_RE.finditer(table_html):
        row = [
            (_attr_span(attrs, "colspan"), _clean_cell(body), _attr_span(attrs, "rowspan"))
            for attrs, body in _TD_RE.findall(tr.group(1))
        ]
        if row:
            out.append(row)
    return out


def _expand_grid(cell_rows: list[list[tuple[int, str, int]]]) -> list[list[str]]:
    """rowspan 占位网格展开：占位格的文本自然延续到被合并的行。"""
    grid: dict[tuple[int, int], str] = {}
    occupied: set[tuple[int, int]] = set()
    for r, row in enumerate(cell_rows):
        col = 0
        for span, text, rowspan in row:
            while (r, col) in occupied:
                col += 1
            for dr in range(rowspan):
                for dc in range(span):
                    occupied.add((r + dr, col + dc))
                    grid[(r + dr, col + dc)] = text
            col += span
    if not occupied:
        return []
    max_r = max(r for r, _ in occupied)
    max_c = max(c for _, c in occupied)
    return [[grid.get((r, c), "") for c in range(max_c + 1)] for r in range(max_r + 1)]


def extract_taxonomy_rows(table_html: str) -> list[dict[str, Any]]:
    """从 <table> HTML 抽出 {code, name, meaning, parent_code} 行（已滤表头/残片）。"""
    cell_rows = _parse_cell_rows(table_html)
    if not cell_rows:
        return []
    grid = _expand_grid(cell_rows)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in grid:
        cells = [c.strip() for c in row]
        codes = [c for c in cells if _CODE_RE.match(c)]
        if not codes:
            continue  # 表头行 / 无编码残片
        # 取最后一个编码 = 本行最具体的类别（rowspan 展开后父级编码会复制到二级类行）
        code = codes[-1]
        idx = len(cells) - 1 - cells[::-1].index(code)
        rest = [c for c in cells[idx + 1 :] if c and c not in _HEADER_WORDS]
        if not rest:
            continue
        name = rest[0]
        meaning = rest[-1] if len(rest) > 1 else ""
        if code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "code": code,
                "name": name,
                "meaning": meaning,
                "parent_code": code[:2] if len(code) > 2 else "",
            }
        )
    return rows


def row_id(doc_code: str, code: str) -> str:
    return hashlib.sha1(f"{doc_code}|{code}".encode("utf-8")).hexdigest()[:32]
