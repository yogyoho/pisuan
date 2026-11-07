"""表格原子分块：`<table>` 块永不拦腰切，每表配最近前置的表标题行独立成 chunk。

表格优先于 chunk_token_num——表块整体出块（原子性由本模块保证，不经 hard_split）；
表间正文段落沿用 general 的合并 + 1.5x 硬切保护。单表超嵌入上限（8192 token）时按
裁决 a) 允许超限整表入库，logger.warning 记表标题与 token 数（可观测，不续切分：
写作侧权威接口是结构化指标行，不依赖表格 chunk 向量检索）。
"""

from __future__ import annotations

import re
from typing import Any

from pisuan.knowledge.chunking.ragflow_like import nlp
from pisuan.knowledge.chunking.ragflow_like.parsers.general import (
    _ensure_chunk_token_limit,
    _iter_sections,
    _unescape_delimiter,
)
from pisuan.utils import logger

EMBED_TOKEN_LIMIT = 8192

_TABLE_BLOCK_RE = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.IGNORECASE | re.DOTALL)
# 表标题行（与 enrich 侧 unit_parser 同款行首形态）：表1 / 表 2-1
_TABLE_TITLE_RE = re.compile(r"^表\s*\d")


def _chunk_text(text: str, chunk_token_num: int, delimiter: str, overlapped_percent: int) -> list[str]:
    """表间正文：常规 token 上限合并 + 1.5x 硬切保护（沿用 general 配方）。"""
    sections = _iter_sections(text, delimiter)
    chunks = nlp.naive_merge(
        sections, chunk_token_num=chunk_token_num, delimiter=delimiter, overlapped_percent=overlapped_percent
    )
    return _ensure_chunk_token_limit(chunks, chunk_token_num)


def _split_title_line(leading: str) -> tuple[str, str]:
    """取表块前置文本的最近非空行；命中表标题行则作为表 chunk 标题并从正文流中移除。

    Returns:
        (移除标题行后的前置正文, 标题行；非标题行原样留在正文流中)
    """
    lines = leading.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            if _TABLE_TITLE_RE.match(lines[i].strip()):
                return "\n".join(lines[:i]).strip("\n"), lines[i].strip()
            return "\n".join(lines), ""
    return "", ""


def chunk_markdown(markdown_content: str, parser_config: dict[str, Any] | None = None) -> list[str]:
    parser_config = parser_config or {}
    delimiter = _unescape_delimiter(str(parser_config.get("delimiter", "\n") or "\n"))
    chunk_token_num = int(parser_config.get("chunk_token_num", 512) or 512)
    overlapped_percent = int(parser_config.get("overlapped_percent", 0) or 0)

    text = markdown_content or ""
    blocks = list(_TABLE_BLOCK_RE.finditer(text))
    if not blocks:
        return _chunk_text(text, chunk_token_num, delimiter, overlapped_percent)

    chunks: list[str] = []
    cursor = 0
    for block in blocks:
        leading = text[cursor : block.start()].strip()
        body, title = _split_title_line(leading) if leading else ("", "")
        if body.strip():
            chunks.extend(_chunk_text(body, chunk_token_num, delimiter, overlapped_percent))
        table_chunk = f"{title}\n{block.group(0)}" if title else block.group(0)
        tokens = nlp.count_tokens(table_chunk)
        if tokens > EMBED_TOKEN_LIMIT:
            logger.warning(
                f"表格原子分块: 单表 {tokens} token 超嵌入上限 {EMBED_TOKEN_LIMIT}，"
                f"允许超限整表入库（标题: {title or '无'}）"
            )
        chunks.append(table_chunk)
        cursor = block.end()
    if tail := text[cursor:].strip():
        chunks.extend(_chunk_text(tail, chunk_token_num, delimiter, overlapped_percent))
    return chunks
