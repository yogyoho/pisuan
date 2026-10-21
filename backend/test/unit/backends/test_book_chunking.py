"""book 预设分块回归测试（bug-4116）：

hierarchical_merge 组内预算硬编码且标题组强制新块，chunk_token_num 只被末端
硬切当上限用，产物碎成标题面包屑小块。修复：层级产物按原序经 naive_merge
回填合并到 chunk_token_num，使其成为实际目标尺寸。
"""

from yuxi.knowledge.chunking.ragflow_like.nlp import count_tokens
from yuxi.knowledge.chunking.ragflow_like.parsers import book


def _many_short_sections_md(n: int = 30) -> str:
    sections = [f"#### 3.{i} 小节标题{i}\n本节一句话内容，描述该项调查与评价结论。" for i in range(1, n + 1)]
    return "## 3 矿区概况\n" + "\n".join(sections)


def test_short_sections_merge_toward_token_budget():
    """碎片化回归：短小节不再一标题一块，而是合并逼近 chunk_token_num。"""
    md = _many_short_sections_md()
    chunks = book.chunk_markdown(md, {"chunk_token_num": 1024})

    assert 1 <= len(chunks) < 10, f"短小节应合并为少量块，实际 {len(chunks)} 块"
    assert all(count_tokens(c) <= 1024 for c in chunks)


def test_chunk_starts_prefer_headings():
    """回填合并后块起点仍优先对齐标题行。"""
    md = _many_short_sections_md()
    chunks = book.chunk_markdown(md, {"chunk_token_num": 1024})

    heading_starts = sum(1 for c in chunks if c.lstrip().startswith("#"))
    assert heading_starts >= len(chunks) - 1, "合并后块起点应基本为标题行"


def test_oversize_section_still_hard_split():
    """超预算大段仍被硬切到上限内。"""
    big_body = "矿区现状调查与评价详细论述。" * 800  # 远超 1024 token
    md = "## 4 现状评价\n#### 4.1 大段论述\n" + big_body
    chunks = book.chunk_markdown(md, {"chunk_token_num": 1024})

    assert len(chunks) > 1
    assert all(count_tokens(c) <= 1024 for c in chunks)


def test_breadcrumb_not_repeated_within_chunk():
    """同节多段的祖先标题链只保留一次，不再块内重复（bug-4116“分片重复”）。"""
    body = "\n".join(f"第{i}段论述该小节的调查与评价内容，补充细节说明。" for i in range(6))
    md = "## 1 总则\n#### 1.1 规划背景\n" + body
    chunks = book.chunk_markdown(md, {"chunk_token_num": 1024})

    assert len(chunks) == 1
    assert chunks[0].count("#### 1.1 规划背景") == 1
    assert chunks[0].count("## 1 总则") == 1
