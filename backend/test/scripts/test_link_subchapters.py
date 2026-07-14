"""link_subchapters.py 单元测试: 存量 ETL 子章节归一化匹配逻辑。"""

from scripts.governance.link_subchapters import match_etl_to_standard


def test_match_exact_title():
    """ETL标题与标准子章节 key 完全匹配"""
    std_subs = [
        {"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"},
        {"sub_id": "std_5_2", "key": "评价因子筛选", "title": "5.2 评价因子筛选"},
    ]
    match = match_etl_to_standard("环境影响识别", std_subs)
    assert match is not None
    assert match["sub_id"] == "std_5_1"
    assert match["key"] == "环境影响识别"


def test_match_etl_contains_standard_key():
    """ETL标题包含标准 key (正向包含)"""
    std_subs = [
        {"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"},
    ]
    etl_title = "环境影响识别及评价因子筛选"
    match = match_etl_to_standard(etl_title, std_subs)
    assert match is not None
    assert match["sub_id"] == "std_5_1"


def test_match_standard_key_contains_etl():
    """标准 key 包含 ETL标题 (反向包含)"""
    std_subs = [
        {"sub_id": "std_6_1", "key": "大气环境影响预测", "title": "6.1 大气环境影响预测"},
    ]
    etl_title = "大气环境"
    match = match_etl_to_standard(etl_title, std_subs)
    assert match is not None
    assert match["sub_id"] == "std_6_1"


def test_no_match_returns_none():
    """无法匹配返回 None"""
    std_subs = [{"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"}]
    match = match_etl_to_standard("完全无关的标题XYZ", std_subs)
    assert match is None


def test_empty_etl_title_returns_none():
    """空标题返回 None"""
    match = match_etl_to_standard("", [{"sub_id": "x", "key": "k", "title": "t"}])
    assert match is None


def test_none_etl_title_returns_none():
    """None 标题返回 None"""
    match = match_etl_to_standard(None, [{"sub_id": "x", "key": "k", "title": "t"}])
    assert match is None


def test_exact_match_takes_priority_over_contains():
    """精确匹配优先于包含匹配"""
    std_subs = [
        {"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"},
        {"sub_id": "std_5_2", "key": "环境影响识别及评价", "title": "5.2 环境影响识别及评价"},
    ]
    # "环境影响识别" 精确匹配 std_5_1, 而非包含匹配 std_5_2
    match = match_etl_to_standard("环境影响识别", std_subs)
    assert match["sub_id"] == "std_5_1"
