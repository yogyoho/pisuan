"""prepare_corpus 测试：节号标题识别 / 目录页剔除 / 表格 GFM / 标题层级提升。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prepare_corpus import SEC_LINE_RE, is_toc_line, strip_toc, table_to_gfm, promote_headings


def test_sec_line_levels():
    assert SEC_LINE_RE.match("6.5 声环境影响评价").groups() == ("6.5", "声环境影响评价")
    assert SEC_LINE_RE.match("1 总 论").groups() == ("1", "总 论")
    assert not SEC_LINE_RE.match("环境影响评价（无节号）")


def test_toc_line_and_strip():
    assert is_toc_line("1 总 论\t5")
    assert is_toc_line("2.1 评价目的 28")
    assert not is_toc_line("6.5 声环境影响评价")  # 正文标题无尾随页码
    body = "1 总 论\t5\n2 项目概况\t28\n3 评价标准\t33\n6.5 声环境影响评价\n正文段落。\n"
    assert "总 论\t5" not in strip_toc(body)  # 连续 3 行目录行 → 整段剔除
    assert "6.5 声环境影响评价" in strip_toc(body)


def test_table_to_gfm_pad():
    """docx 表行（list[list[str]]）→ GFM：列数取 max 补空（bug-393 反向杜绝）。"""
    rows = [["要素", "数值"], ["声级", "60", "多余列"]]
    md = table_to_gfm(rows)
    lines = md.splitlines()
    assert lines[1].count("|") == lines[0].count("|") == lines[2].count("|")
    assert "---" in lines[1]


def test_promote_headings():
    body = "6.5 声环境影响评价\n正文。\n6.5.1 点源预测\n子正文。\n"
    out = promote_headings(body)
    assert "### 6.5 声环境影响评价" in out  # 两段号 → ###
    assert "#### 6.5.1 点源预测" in out  # 三段号 → ####
    assert not any(ln.startswith("## 6.5 ") for ln in out.splitlines())  # 行首锚定（"## " 为 "### " 子串不可用 in）


def test_make_rid_ascii_slug_contract():
    """rid 契约（bug-398）：ASCII slug 兼容 bank_compile RID_RE；序号保唯一。"""
    import re

    from prepare_corpus import make_rid

    RID_CONTRACT = re.compile(r"[a-z0-9][a-z0-9\-_]*")  # bank_compile.py:53 原样
    # 纯中文名 → 非空合法 slug（保底 r）
    r1 = make_rid(3, "九龙川矿井及选煤厂环评")
    assert RID_CONTRACT.fullmatch(r1) and r1.startswith("003-")
    # 混合名 → ASCII 折叠保留
    r2 = make_rid(1, "(WPS)宁夏通达矿井环评-排版")
    assert RID_CONTRACT.fullmatch(r2) and "wps" in r2
    # 不同序号永不冲突；同函数确定性
    assert make_rid(2, "九龙川矿井及选煤厂环评") != r1
    assert make_rid(3, "九龙川矿井及选煤厂环评") == r1
