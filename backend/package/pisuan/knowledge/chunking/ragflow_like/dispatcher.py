from __future__ import annotations

import re
from typing import Any

from pisuan.knowledge.chunking.ragflow_like.parsers import book, general, laws, qa, semantic, separator, table
from pisuan.knowledge.chunking.ragflow_like.presets import map_to_internal_parser_id, normalize_chunk_preset_id

# 表格型文档自动检测：表格字符占比 ≥30% 且用户未显式指定预设时，自动切 table 预设
TABLE_RATIO_THRESHOLD = 0.3
_TABLE_BLOCK_RE_GLOBAL = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.IGNORECASE | re.DOTALL)


def auto_select_table_preset(markdown_content: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """解析产物表格占比高时自动切换 table 预设（表格原子分块）。

    规则：表格字符占比 ≥ TABLE_RATIO_THRESHOLD 且 ≥1 个 <table> 块，
    且用户未显式指定预设（params 无 chunk_preset_id）且未曾自动切换过（无 chunk_preset_auto）。
    触发时设置 chunk_preset_id="table" 与 chunk_preset_auto="table"（幂等标记）。
    """
    params = dict(params or {})
    if params.get("chunk_preset_id") or params.get("chunk_preset_auto"):
        return params
    if not markdown_content:
        return params
    tables = _TABLE_BLOCK_RE_GLOBAL.findall(markdown_content)
    if not tables:
        return params
    table_chars = sum(len(x) for x in tables)
    if table_chars / max(len(markdown_content), 1) >= TABLE_RATIO_THRESHOLD:
        params["chunk_preset_id"] = "table"
        params["chunk_preset_auto"] = "table"
    return params


def _build_chunk_records(
    text_chunks: list[str], file_id: str, filename: str, source_text: str | None = None
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    search_from = 0

    for idx, chunk_content in enumerate(text_chunks):
        text = (chunk_content or "").strip()
        if not text:
            continue

        start_char_pos = None
        end_char_pos = None
        if source_text:
            found_at = source_text.find(text, search_from)
            if found_at >= 0:
                start_char_pos = found_at
                end_char_pos = found_at + len(text)
                search_from = end_char_pos

        records.append(
            {
                "id": f"{file_id}_chunk_{idx}",
                "content": text,
                "file_id": file_id,
                "filename": filename,
                "chunk_index": idx,
                "source": filename,
                "chunk_id": f"{file_id}_chunk_{idx}",
                "start_char_pos": start_char_pos,
                "end_char_pos": end_char_pos,
                "start_token_pos": None,
                "end_token_pos": None,
                "extraction_result": None,
            }
        )

    return records


def _dispatch_markdown_parser(
    preset_id: str, filename: str, markdown_content: str, parser_config: dict[str, Any]
) -> list[str]:
    parser_id = map_to_internal_parser_id(preset_id)

    if parser_id == "naive":
        return general.chunk_markdown(markdown_content, parser_config)
    if parser_id == "qa":
        return qa.chunk_markdown(filename, markdown_content, parser_config)
    if parser_id == "book":
        return book.chunk_markdown(markdown_content, parser_config)
    if parser_id == "laws":
        return laws.chunk_markdown(filename, markdown_content, parser_config)
    if parser_id == "semantic":
        return semantic.chunk_markdown(markdown_content, parser_config)
    if parser_id == "separator":
        return separator.chunk_markdown(markdown_content, parser_config)
    if parser_id == "table":
        return table.chunk_markdown(markdown_content, parser_config)

    return general.chunk_markdown(markdown_content, parser_config)


def chunk_markdown(
    markdown_content: str, file_id: str, filename: str, processing_params: dict[str, Any]
) -> list[dict[str, Any]]:
    params = dict(processing_params or {})
    preset_id = normalize_chunk_preset_id(params.get("chunk_preset_id"))
    parser_config = params.get("chunk_parser_config") if isinstance(params.get("chunk_parser_config"), dict) else {}

    text_chunks = _dispatch_markdown_parser(preset_id, filename, markdown_content, parser_config)
    return _build_chunk_records(text_chunks, file_id, filename, markdown_content)


def chunk_file(
    file_content: str, file_id: str, filename: str, processing_params: dict[str, Any]
) -> list[dict[str, Any]]:
    # 当前链路中入库前均已转换为 markdown，因此与 chunk_markdown 保持同实现。
    return chunk_markdown(file_content, file_id, filename, processing_params)
