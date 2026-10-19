from types import SimpleNamespace

from yuxi.knowledge.chunking.ragflow_like.parsers import semantic
from yuxi.knowledge.chunking.ragflow_like.utils.md_parser_utils import infer_heading_level


def test_heading_inference():
    """测试标题层级推断工具类。"""
    assert infer_heading_level("1. 简介") == 1
    assert infer_heading_level("1.1 详细设计") == 2
    assert infer_heading_level("1.2.3 核心逻辑") == 3
    assert infer_heading_level("一、 背景") == 1
    assert infer_heading_level("普通文本") == 1


def test_empty_heading_preserves_current_title_context():
    markdown_content = """
## Parent Section

### Child Section

Content before empty heading.

###

Content after empty heading.
"""

    chunks = semantic.chunk_markdown(
        markdown_content,
        parser_config={"chunk_token_num": 512},
        embed_fn=lambda texts: texts,
    )

    assert len(chunks) == 1
    assert chunks[0].splitlines()[0] == "### Parent Section|Child Section"
    assert "Content before empty heading." in chunks[0]
    assert "Content after empty heading." in chunks[0]


def test_truncated_heading_token_stream_is_ignored(monkeypatch):
    markdown_parser = semantic.MarkdownIt("commonmark")
    monkeypatch.setattr(markdown_parser, "parse", lambda _: [SimpleNamespace(type="heading_open")])
    monkeypatch.setattr(semantic, "MarkdownIt", lambda _: markdown_parser)

    assert semantic.chunk_markdown("#", embed_fn=lambda texts: texts) == []


def _make_markdown_table(rows: int, cell_text: str) -> str:
    lines = ["| 列一 | 列二 |", "| --- | --- |"]
    for i in range(rows):
        lines.append(f"| {cell_text} | {i} |")
    return "\n".join(lines)


def test_oversized_table_splits_within_milvus_varchar_limit():
    """超长附表（如导则类 PDF 巨型表格）必须落入 token 切分路径，单块不超 Milvus varchar 65535 上限。"""
    table = _make_markdown_table(rows=2000, cell_text="测" * 40)
    assert len(table) > 60000
    content = f"# 附录A 统计表\n\n{table}\n\n附表结束。"

    chunks = semantic.chunk_markdown(
        content,
        parser_config={"chunk_token_num": 512},
        embed_fn=lambda texts: texts,
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) < 65535
    table_chunks = [c for c in chunks if "|Table|" in c.splitlines()[0]]
    assert len(table_chunks) > 1
    for chunk in table_chunks:
        assert "|Table|Part" in chunk.splitlines()[0]


def test_normal_table_keeps_single_chunk_without_part_header():
    """正常尺寸表格仍整块保留，header 为 `# 标题|Table` 且不带 Part 编号。"""
    content = f"# 附表说明\n\n{_make_markdown_table(rows=3, cell_text='短数据')}\n\n附表结束。"

    chunks = semantic.chunk_markdown(
        content,
        parser_config={"chunk_token_num": 512},
        embed_fn=lambda texts: texts,
    )

    table_chunks = [c for c in chunks if c.splitlines()[0] == "# 附表说明|Table"]
    assert len(table_chunks) == 1
    header = table_chunks[0].splitlines()[0]
    assert header == "# 附表说明|Table"
    assert "Part" not in header
    assert "| 短数据 | 2 |" in table_chunks[0]
