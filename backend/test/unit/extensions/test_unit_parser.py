"""结构单元解析测试：4 类文档格式的 unit_no 识别"""

from yuxi.extensions.regulation_library.unit_parser import parse_chunk_unit


def test_standard_clause():
    """标准条款: 4.2 / 4.2.1"""
    r = parse_chunk_unit("4.2 环境空气功能区分类\n环境空气功能区分为二类...", "technical_standard")
    assert r == {"unit_no": "4.2", "unit_type": "clause", "parent_unit": "4",
                 "title": "环境空气功能区分类"}


def test_law_article():
    """法律法条: 第X条"""
    r = parse_chunk_unit("第十二条 国务院环境保护主管部门...", "law")
    assert r["unit_no"] == "第十二条"
    assert r["unit_type"] == "article"
    assert r["parent_unit"] is None


def test_section_chinese_numbering():
    """规划/规章: 三、(一) 自由编号"""
    r = parse_chunk_unit("三、重点任务\n（一）加强源头防控...", "national_plan")
    assert r["unit_no"] == "三"
    assert r["unit_type"] == "section"


def test_table_chunk():
    """表格 chunk: 含 HTML table → table 类型"""
    r = parse_chunk_unit("表1 环境空气污染物基本项目浓度限值\n<table><tr><td>1</td></tr></table>", "technical_standard")
    assert r["unit_no"] == "表1"
    assert r["unit_type"] == "table"


def test_no_match_returns_none():
    """无结构线索的 chunk 返回 None"""
    assert parse_chunk_unit("这是一段没有编号的叙述文字。", "technical_standard") is None
