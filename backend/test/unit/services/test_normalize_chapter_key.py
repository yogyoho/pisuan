"""章节标题归一化与聚合身份键解析单测（不连图库）。

覆盖 bug-4167 设计 spec §4.1：
- normalize_chapter_key：去前导多级编号 + 去所有内部空白 + 纯编号返回空
- resolve_chapter_id：两文档同树→同 id / std 命中复用 / 不同父同名单独成点
- _derive_chapter_no：section_path → 点分编号
"""

from pisuan.services.graph_builder import (
    _derive_canonical_key,
    _derive_chapter_no,
    resolve_chapter_id,
)
from pisuan.utils import hashstr, normalize_chapter_key


# ---- normalize_chapter_key：标题归一化 ----


def test_fullwidth_space_collapsed():
    """全角空格「总　则」→「总则」"""
    assert normalize_chapter_key("总　则") == "总则"


def test_halfwidth_spaces_collapsed():
    """半角空格「总  则」→「总则」"""
    assert normalize_chapter_key("总  则") == "总则"


def test_tab_and_mixed_whitespace_collapsed():
    """制表符与混合空白 →「总则」"""
    assert normalize_chapter_key("总\t则") == "总则"
    assert normalize_chapter_key(" 总　\t则 ") == "总则"


def test_leading_numbering_stripped():
    """多级前导编号剥离（含编号后带空白）"""
    assert normalize_chapter_key("1  总  则") == "总则"
    assert normalize_chapter_key("1.4.2 评价时段") == "评价时段"


def test_pure_numbering_returns_empty():
    """纯编号 → 空串"""
    assert normalize_chapter_key("3.2") == ""
    assert normalize_chapter_key("12") == ""


def test_empty_inputs_return_empty():
    """空串、纯空白、None → 空串"""
    assert normalize_chapter_key("") == ""
    assert normalize_chapter_key("   ") == ""
    assert normalize_chapter_key(None) == ""


def test_derive_canonical_key_delegates_to_normalize():
    """_derive_canonical_key 薄委托 normalize_chapter_key，既有调用点语义随归一化升级"""
    assert _derive_canonical_key("1  总  则") == "总则"
    assert _derive_canonical_key("总　则") == "总则"
    assert _derive_canonical_key("3.2") == ""


# ---- resolve_chapter_id：聚合身份键解析（std 索引作参数，不连 Neo4j） ----

D, RT = "coal", "eia_report"

# 模拟 std 索引（键 = (归一canonical, 父解析id, level)，形态同 seed 脚本）
STD_INDEX = {
    ("总则", "", 1): f"CH_{D}_{RT}_std_1",
    ("结论与建议", "", 1): f"CH_{D}_{RT}_std_13",
    ("编制依据", f"CH_{D}_{RT}_std_1", 2): f"CH_{D}_{RT}_std_1_1",
    ("公众参与", f"CH_{D}_{RT}_std_12", 2): f"CH_{D}_{RT}_std_12_1",
}


def test_std_hit_reuses_std_id():
    """归一 canonical 命中 std → 复用 std id"""
    assert resolve_chapter_id(D, RT, "总则", 1, "", STD_INDEX) == f"CH_{D}_{RT}_std_1"
    assert resolve_chapter_id(D, RT, "结论与建议", 1, "", STD_INDEX) == f"CH_{D}_{RT}_std_13"
    assert (
        resolve_chapter_id(D, RT, "编制依据", 2, f"CH_{D}_{RT}_std_1", STD_INDEX)
        == f"CH_{D}_{RT}_std_1_1"
    )


def test_std_hit_requires_resolved_parent_match():
    """level2 std 命中取决于解析后的父 std id，防同名误挂"""
    assert resolve_chapter_id(D, RT, "公众参与", 2, f"CH_{D}_{RT}_std_12", STD_INDEX) == f"CH_{D}_{RT}_std_12_1"
    # 父不是 std_12 → 不命中，落聚合键 id
    under_other = resolve_chapter_id(D, RT, "公众参与", 2, f"CH_{D}_{RT}_std_13", STD_INDEX)
    assert under_other.startswith(f"CH_{D}_{RT}_2_")


def test_miss_id_follows_aggregation_key_formula():
    """未命中 std → CH_{d}_{rt}_{level}_{hashstr(canonical + '|' + 父解析id)}"""
    parent = f"CH_{D}_{RT}_std_13"
    expected = f"CH_{D}_{RT}_2_{hashstr(f'公众参与|{parent}', 10)}"
    assert resolve_chapter_id(D, RT, "公众参与", 2, parent, STD_INDEX) == expected

    level1_expected = f"CH_{D}_{RT}_1_{hashstr('前言|', 10)}"
    assert resolve_chapter_id(D, RT, "前言", 1, "", STD_INDEX) == level1_expected


def test_same_tree_resolves_same_ids_across_docs():
    """两文档同构章节树 → 解析出相同节点 id（MERGE 幂等的根源）"""
    l1_a = resolve_chapter_id(D, RT, "前言", 1, "", STD_INDEX)
    l1_b = resolve_chapter_id(D, RT, "前言", 1, "", STD_INDEX)
    assert l1_a == l1_b

    # 子章节以解析后的父 id 参与身份，父一致则子 id 一致
    l2_a = resolve_chapter_id(D, RT, "评价时段", 2, l1_a, STD_INDEX)
    l2_b = resolve_chapter_id(D, RT, "评价时段", 2, l1_b, STD_INDEX)
    assert l2_a == l2_b


def test_same_name_under_different_parents_resolves_distinct_ids():
    """不同父同名单独成点（旧 CONTAINS+LIMIT 1 错挂根源的回归断言）"""
    under_12 = resolve_chapter_id(D, RT, "公众参与", 2, f"CH_{D}_{RT}_std_12", STD_INDEX)
    under_13 = resolve_chapter_id(D, RT, "公众参与", 2, f"CH_{D}_{RT}_std_13", STD_INDEX)
    assert under_12 == f"CH_{D}_{RT}_std_12_1"
    assert under_13 != under_12


# ---- _derive_chapter_no：section_path → 点分编号 ----


def test_chapter_no_from_counted_stack_path():
    """计数栈路径逐级以'.'连接：[1, 4] → '1.4'"""
    assert _derive_chapter_no([1, 4]) == "1.4"
    assert _derive_chapter_no(["1", 1, 2]) == "1.1.2"


def test_chapter_no_from_dotted_etl_path():
    """ETL 路径末段即完整点分编号，直接取用"""
    assert _derive_chapter_no(["1", "1.4.2"]) == "1.4.2"


def test_chapter_no_edge_cases():
    """空路径与单级路径"""
    assert _derive_chapter_no([]) == ""
    assert _derive_chapter_no(None) == ""
    assert _derive_chapter_no(["1"]) == "1"
