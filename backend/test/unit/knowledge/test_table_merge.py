"""跨页断表合并纯函数单测（无 IO / 无 DB）。

用例形态取自 GB/T 14848 真实 OCR 产物（.wolf/gbt_content_ds.md）：续表标记、
逐字重复表头、`1 类` vs `I 类` 噪声表头、colspan 分组行、链式续表。
"""

from pisuan.knowledge.parser.table_merge import merge_split_tables


def _table(rows: list[str], open_tag: str = "<table>") -> str:
    body = "".join(f"<tr>{''.join(f'<td>{c}</td>' for c in row)}</tr>" for row in rows)
    return f"{open_tag}{body}</table>"


HEADER = ["序号", "指标", "I 类", "II 类"]
NOISY_HEADER = ["序号", "指标", "1 类", "II 类"]


def test_marker_with_identical_header_merges_and_drops_header():
    md = (
        "前言\n"
        + _table([HEADER, ["1", "色", "≤5"]])
        + "\n\n表1（续）\n\n"
        + _table([HEADER, ["2", "味", "无"]])
        + "\n"
    )
    merged, count = merge_split_tables(md)
    assert count == 1
    assert merged.count("<table>") == 1
    assert "表1（续）" not in merged
    assert merged.count("<td>序号</td>") == 1  # 重复表头被丢弃
    assert "<td>2</td>" in merged and "<td>味</td>" in merged


def test_noisy_header_folds_and_merges():
    md = _table([HEADER, ["1", "pH", "6.5"]]) + "\n\n续表1\n\n" + _table([NOISY_HEADER, ["2", "锌", "0.05"]])
    merged, count = merge_split_tables(md)
    assert count == 1
    assert merged.count("<table>") == 1


def test_chain_of_three_fragments():
    md = (
        _table([HEADER, ["1", "a", "1"]])
        + "\n表2（续）\n"
        + _table([HEADER, ["2", "b", "2"]])
        + "\n表2（续）\n"
        + _table([HEADER, ["3", "c", "3"]])
    )
    merged, count = merge_split_tables(md)
    assert count == 2
    assert merged.count("<table>") == 1
    assert "<td>3</td>" in merged


def test_adjacent_different_tables_not_merged():
    md = (
        "表2 地下水质量标准\n"
        + _table([HEADER, ["1", "a", "1"]])
        + "\n\n表3 其他指标\n\n"
        + _table([["序号", "项目", "限值"], ["1", "b", "2"]])
    )
    merged, count = merge_split_tables(md)
    assert count == 0
    assert merged.count("<table>") == 2


def test_no_marker_and_different_headers_not_merged():
    md = _table([HEADER, ["1", "a", "1"]]) + "\n\n" + _table([["编号", "名称"], ["1", "b"]])
    merged, count = merge_split_tables(md)
    assert count == 0
    assert merged.count("<table>") == 2


def test_no_marker_but_identical_headers_merges():
    md = _table([HEADER, ["1", "a", "1"]]) + "\n\n第 2 页\n\n" + _table([HEADER, ["2", "b", "2"]])
    merged, count = merge_split_tables(md)
    assert count == 1
    assert merged.count("<table>") == 1


def test_marker_with_mismatched_header_keeps_all_rows():
    md = _table([HEADER, ["1", "a", "1"]]) + "\n表A.1（续）\n" + _table([["编号", "名称"], ["9", "b"]])
    merged, count = merge_split_tables(md)
    assert count == 1
    assert merged.count("<table>") == 1
    assert "<td>编号</td>" in merged  # 表头不匹配则全行保留
    assert "<td>9</td>" in merged


def test_body_text_between_tables_not_merged():
    md = _table([HEADER, ["1", "a", "1"]]) + "\n\n上述限值适用于 IV 类水体。\n\n" + _table([HEADER, ["2", "b", "2"]])
    merged, count = merge_split_tables(md)
    assert count == 0
    assert merged.count("<table>") == 2


def test_realistic_gbt14848_fragment():
    header = "<tr><td>序号</td><td>指标</td><td>I 类</td><td>II 类</td></tr>"
    group_row = '<tr><td colspan="4">毒理学指标</td></tr>'
    first = f"<table>{header}{group_row}<tr><td>24</td><td>硝酸盐</td><td>≤2.0</td><td>≤5.0</td></tr></table>"
    continuation = f"<table>{header}{group_row}<tr><td>25</td><td>氰化物</td><td>≤0.001</td><td>≤0.05</td></tr></table>"
    merged, count = merge_split_tables(f"表1\n\n{first}\n\n表1（续）\n\n{continuation}")
    assert count == 1
    assert merged.count("<table>") == 1
    assert merged.count("<td>序号</td>") == 1
    assert "<td>25</td>" in merged


def test_single_or_zero_tables_unchanged():
    assert merge_split_tables("无表格文本") == ("无表格文本", 0)
    single = _table([HEADER, ["1", "a", "1"]])
    assert merge_split_tables(single) == (single, 0)


def test_marker_with_page_number_gap_merges():
    md = _table([HEADER, ["1", "a", "1"]]) + "\n表1（续）\n12\n" + _table([HEADER, ["2", "b", "2"]])
    merged, count = merge_split_tables(md)
    assert count == 1
    assert "12" not in merged
