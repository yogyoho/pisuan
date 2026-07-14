"""seed_standard_subchapters.py 单元测试: 解析 outlines/ MD 写作骨架 + 标准子章节生成。"""

from scripts.seed_standard_subchapters import parse_skeleton, STANDARD_SUBCHAPTERS


def test_parse_skeleton_extracts_subchapters():
    """解析写作骨架段, 提取 level=2 标准子章节"""
    md_text = """## 写作骨架
5.1 环境影响识别
  5.1.1 识别方法（矩阵法/清单法）
  5.1.2 施工期影响识别
5.2 评价因子筛选
5.3 重点评价要素确定

## 数据需求清单"""
    subs = parse_skeleton(md_text, parent_order=5)
    assert len(subs) == 3
    assert subs[0] == {
        "parent_order": 5,
        "sub_order": 1,
        "key": "环境影响识别",
        "title": "5.1 环境影响识别",
    }
    assert subs[1] == {
        "parent_order": 5,
        "sub_order": 2,
        "key": "评价因子筛选",
        "title": "5.2 评价因子筛选",
    }
    assert subs[2] == {
        "parent_order": 5,
        "sub_order": 3,
        "key": "重点评价要素确定",
        "title": "5.3 重点评价要素确定",
    }


def test_parse_skeleton_no_skeleton_returns_empty():
    """无写作骨架段返回空"""
    subs = parse_skeleton("## 其他\n无骨架", parent_order=1)
    assert subs == []


def test_parse_skeleton_skips_level3_lines():
    """level=3 行(有前导空格)被跳过"""
    md_text = """## 写作骨架
6.1 大气环境影响预测
  6.1.1 预测模式与参数
  6.1.2 预测情景
6.2 地表水环境影响预测

## 数据需求"""
    subs = parse_skeleton(md_text, parent_order=6)
    assert len(subs) == 2
    assert subs[0]["sub_order"] == 1
    assert subs[0]["key"] == "大气环境影响预测"
    assert subs[1]["sub_order"] == 2
    assert subs[1]["key"] == "地表水环境影响预测"


def test_parse_skeleton_filters_wrong_parent_order():
    """只保留匹配 parent_order 的行"""
    md_text = """## 写作骨架
5.1 环境影响识别
5.2 评价因子筛选"""
    subs = parse_skeleton(md_text, parent_order=6)
    assert subs == []


def test_standard_subchapters_generated_from_all_outlines():
    """从全部13章 outlines/ 解析出标准子章节"""
    assert len(STANDARD_SUBCHAPTERS) > 0
    # 第5章应有子章节
    ch5_subs = [s for s in STANDARD_SUBCHAPTERS if s["parent_order"] == 5]
    assert len(ch5_subs) >= 3
    assert any(s["key"] == "环境影响识别" for s in ch5_subs)


def test_standard_subchapters_id_format():
    """标准子章节 id 格式: CH_coal_eia_report_std_{parent_order}_{sub_order}"""
    for sub in STANDARD_SUBCHAPTERS:
        expected_id = f"CH_coal_eia_report_std_{sub['parent_order']}_{sub['sub_order']}"
        assert "std_" in expected_id
