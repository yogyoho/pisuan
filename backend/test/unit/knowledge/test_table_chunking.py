"""R2 表格原子分块预设（table parser）单测（Task 15）。

钉住：<table> 块永不拦腰切（原子性）、表块配最近前置表标题行、表间正文按常规
token 上限合并、单表超嵌入上限 8192 记 warning 且整表保留（裁决 a）。零外部依赖。
宿主运行：cd backend && uv run --frozen --with pytest --with pytest-asyncio
python -m pytest test/unit/knowledge/test_table_chunking.py -q --noconftest
"""

import pytest
from pisuan.knowledge.chunking.ragflow_like import nlp
from pisuan.knowledge.chunking.ragflow_like.dispatcher import chunk_markdown
from pisuan.knowledge.chunking.ragflow_like.parsers import table as table_parser
from pisuan.knowledge.chunking.ragflow_like.presets import CHUNK_PRESETS, map_to_internal_parser_id


def _big_table(rows: int, cols: int = 4) -> str:
    body = "".join("<tr>" + "".join(f"<td>行{r}列{c}数据</td>" for c in range(cols)) + "</tr>" for r in range(rows))
    return f"<table>{body}</table>"


def _chunk(content: str, token_num: int = 512):
    return [
        c["content"]
        for c in chunk_markdown(
            markdown_content=content,
            file_id="f",
            filename="gb.md",
            processing_params={"chunk_preset_id": "table", "chunk_parser_config": {"chunk_token_num": token_num}},
        )
    ]


# --------------------------------------------------------------- 预设注册
def test_table_preset_registered_and_mapped():
    assert "table" in CHUNK_PRESETS
    assert CHUNK_PRESETS["table"]["label"] and CHUNK_PRESETS["table"]["description"]
    assert map_to_internal_parser_id("table") == "table"


# --------------------------------------------------------------- 原子性
def test_table_block_atomic_even_over_token_limit():
    content = f"表1 大表\n{_big_table(rows=80)}"  # ≈3000 token，远超 512
    chunks = _chunk(content, token_num=512)
    table_chunks = [c for c in chunks if "</table>" in c]
    assert len(table_chunks) == 1
    assert table_chunks[0].count("<tr>") == 80  # 整表未拦腰切
    assert table_chunks[0].startswith("表1 大表\n<table>")


def test_multiple_tables_stay_separate_chunks():
    content = f"表1 甲\n{_big_table(3)}\n表2 乙\n{_big_table(3)}"
    chunks = _chunk(content, token_num=512)
    table_chunks = [c for c in chunks if "</table>" in c]
    assert len(table_chunks) == 2
    assert table_chunks[0].startswith("表1 甲") and table_chunks[1].startswith("表2 乙")


def test_title_removed_from_preceding_text_flow():
    content = f"前言内容。\n表1 基本项目\n{_big_table(2)}\n后记内容。"
    chunks = _chunk(content, token_num=512)
    text_chunks = [c for c in chunks if "</table>" not in c]
    assert any("前言内容。" in c for c in text_chunks)
    assert all("表1 基本项目" not in c for c in text_chunks)  # 标题行随表走，不在正文流中重复


# --------------------------------------------------------------- 表间正文常规切分
def test_text_between_tables_merged_to_token_limit():
    para = "内容" * 60  # ≈120 token
    content = f"{para}甲\n{para}乙\n{para}丙\n表1 中间表\n{_big_table(2)}\n{para}丁\n{para}戊"
    chunks = _chunk(content, token_num=128)
    table_chunks = [c for c in chunks if "</table>" in c]
    text_chunks = [c for c in chunks if "</table>" not in c]
    assert len(table_chunks) == 1
    assert len(text_chunks) >= 2  # 表前/表后各自合并，不跨表拼接
    assert all(nlp.count_tokens(c) <= 128 * 1.5 for c in text_chunks)  # 1.5x 硬切保护
    assert chunks.index(table_chunks[0]) < len(text_chunks)  # 表块位于表前正文之后


def test_plain_document_falls_back_to_text_chunking():
    content = "\n".join(f"段落{i}" + "内容" * 60 for i in range(10))
    chunks = _chunk(content, token_num=128)
    assert len(chunks) > 1
    assert all("<table" not in c for c in chunks)


# --------------------------------------------------------------- 超嵌入上限（裁决 a）
def test_oversize_table_warns_and_kept_whole(monkeypatch):
    warnings = []
    monkeypatch.setattr(table_parser.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
    content = f"表1 排水量\n{_big_table(rows=260)}"  # >8192 token 嵌入上限
    chunks = _chunk(content, token_num=512)
    table_chunks = [c for c in chunks if "</table>" in c]
    assert len(table_chunks) == 1  # 整表保留，不续切分
    assert table_chunks[0].count("<tr>") == 260
    assert nlp.count_tokens(table_chunks[0]) > 8192
    assert any("8192" in w and "表1 排水量" in w for w in warnings)  # warning 记标题+token 数


def test_small_table_no_warning(monkeypatch):
    warnings = []
    monkeypatch.setattr(table_parser.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
    _chunk(f"表1 小表\n{_big_table(3)}", token_num=512)
    assert warnings == []


# --------------------------------------------------------------- 残段与边界
def test_unclosed_table_tail_kept_as_text():
    # 无闭合残段不归原子化管（enrich 侧才丢弃识别），作为普通文本参与合并
    content = f"{_big_table(2)}\n<table><tr><td>残段"
    chunks = _chunk(content, token_num=512)
    assert any("<td>残段" in c for c in chunks)
    assert len([c for c in chunks if "</table>" in c]) == 1


def test_empty_document_returns_empty():
    assert _chunk("") == []
    assert _chunk("正文，无表格。") == ["正文，无表格。"]


@pytest.mark.parametrize(
    "doc",
    [
        "<table><tr><td>无标题表</td></tr></table>",  # 无前置标题行：表块单独成 chunk
        "表1 甲\n<table><tr><td>a</td></tr></table><table><tr><td>b</td></tr></table>",  # 相邻双表
    ],
)
def test_table_chunks_wellformed(doc):
    chunks = _chunk(doc, token_num=512)
    table_chunks = [c for c in chunks if "<table" in c]
    assert table_chunks
    for c in table_chunks:
        assert c.count("<table") == c.count("</table")  # 任意表 chunk 均含完整闭合表格
