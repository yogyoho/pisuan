from __future__ import annotations

from typing import Any

from pisuan.knowledge.chunking.ragflow_like import nlp


def _unescape_delimiter(delimiter: str) -> str:
    return delimiter.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\")


def _iter_sections(markdown_content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    for line in (markdown_content or "").splitlines():
        text = line.strip()
        if not text:
            continue
        sections.append((text, ""))

    if not sections and markdown_content and markdown_content.strip():
        sections.append((markdown_content.strip(), ""))

    return sections


def _ensure_chunk_token_limit(chunks: list[str], chunk_token_num: int) -> list[str]:
    max_tokens = int(chunk_token_num or 0)
    normalized = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
    if max_tokens <= 0:
        return normalized

    protected: list[str] = []
    for chunk in normalized:
        if nlp.count_tokens(chunk) <= max_tokens:
            protected.append(chunk)
        else:
            protected.extend(nlp.hard_split_by_token_limit(chunk, max_tokens))
    return protected


def _merge_groups_to_chunks(groups: list[list[str]], chunk_token_num: int) -> list[str]:
    # hierarchical_merge 每组头部都带完整祖先标题链，直接拼接会让同一面包屑在块内反复出现
    # （bug-4116 所见“分片重复”）。与前一组合共享的头部行只保留一次；预算打满新起块时恢复
    # 完整面包屑置于块首，块首保持标题对齐且块内无重复。overlapped_percent 与标题对齐冲突，
    # 层级路径不生效（该预设默认及现网配置均为 0）。
    chunks: list[str] = []
    buf: list[str] = []
    prev: list[str] = []
    for group in groups:
        common = 0
        for x, y in zip(prev, group):
            if x != y:
                break
            common += 1
        delta = group[common:]
        prev = group
        if not delta:
            continue

        if not buf:
            buf = list(group)
        elif nlp.count_tokens("\n".join(buf + delta)) <= chunk_token_num:
            buf += delta
            continue
        else:
            chunks.append("\n".join(buf))
            buf = list(group)

        if nlp.count_tokens("\n".join(buf)) > chunk_token_num:
            # 单组自身超预算：硬切后各段直接成块
            chunks.extend(nlp.hard_split_by_token_limit("\n".join(buf), chunk_token_num))
            buf = []
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def chunk_markdown(markdown_content: str, parser_config: dict[str, Any] | None = None) -> list[str]:
    parser_config = parser_config or {}

    delimiter = _unescape_delimiter(str(parser_config.get("delimiter", "\n") or "\n"))
    chunk_token_num = int(parser_config.get("chunk_token_num", 512) or 512)
    overlapped_percent = int(parser_config.get("overlapped_percent", 0) or 0)

    sections = _iter_sections(markdown_content)
    if not sections:
        return []

    section_texts = [text for text, _ in sections]
    nlp.remove_contents_table(sections, eng=nlp.is_english(nlp.random_choices(section_texts, k=200)))
    nlp.make_colon_as_title(sections)

    bull = nlp.bullets_category([t for t in nlp.random_choices([t for t, _ in sections], k=100)])

    if bull >= 0:
        # hierarchical_merge 组内合并预算硬编码且标题组强制新块，chunk_token_num 不参与合并，
        # 产物碎成标题面包屑小块（预算只被末端 _ensure_chunk_token_limit 当裁剪上限）。
        # 层级产物按原序回填合并到预算：块起点仍对齐标题，chunk_token_num 成为实际目标尺寸。
        chunks = _merge_groups_to_chunks(nlp.hierarchical_merge(bull, sections, depth=5), chunk_token_num)
    else:
        chunks = nlp.naive_merge(
            sections,
            chunk_token_num=chunk_token_num,
            delimiter=delimiter,
            overlapped_percent=overlapped_percent,
        )

    if chunks:
        return _ensure_chunk_token_limit(chunks, chunk_token_num)

    return _ensure_chunk_token_limit(
        nlp.naive_merge(
            sections,
            chunk_token_num=chunk_token_num,
            delimiter=delimiter,
            overlapped_percent=overlapped_percent,
        ),
        chunk_token_num,
    )
