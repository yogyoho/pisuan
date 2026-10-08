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


def test_strip_toc_blank_line_gap():
    """目录行被空行间隔仍成段剔除（docx blocks 以空行 join 的真实形态，bug-398 A2）。"""
    body = "1 总 论\t5\n\n2 项目概况\t28\n\n3 评价标准\t33\n\n6.5 声环境影响评价\n正文段落。\n"
    out = strip_toc(body)
    assert "总 论\t5" not in out
    assert "项目概况\t28" not in out
    assert "评价标准\t33" not in out
    assert "6.5 声环境影响评价" in out  # 正文标题无页码不受影响
    assert "正文段落。" in out


def test_strip_toc_two_run_kept():
    """恰 2 行目录行 run 不应剔除（≥3 阈值反向锁定，bug-398 Issue B）。"""
    body = "1 总 论\t5\n2 项目概况\t28\n正文段落。\n"
    out = strip_toc(body)
    assert "总 论\t5" in out
    assert "项目概况\t28" in out
    assert "正文段落。" in out


def test_strip_toc_eof_run_boundary():
    """EOF 收尾分支：目录 run 直到文件结尾——≥3 剔除、<3 冲刷保留（无尾随正文行的路径）。"""
    tail3 = "1 总 论\t5\n2 项目概况\t28\n3 评价标准\t33"
    assert "总 论" not in strip_toc(tail3)
    out2 = strip_toc("1 总 论\t5\n2 项目概况\t28")
    assert "总 论\t5" in out2 and "项目概况\t28" in out2


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


def test_promote_headings_skip_list_like():
    """正文编号列表段保守启发式：题名 >30 字或含句读标点（。；，）不升级；顿号短题名仍升级（防误杀锚）。"""
    body = (
        "1 XF1逆断层:即野麦子塘西侧断层,位于调查区的东北部,向南延伸构造线走向北北西\n"  # 超长（无全角标点，纯长度条件）
        "2 对于需要搬迁的村庄,须就近安置。\n"  # 短但含句号（纯标点条件）
        "13.4.9 对太中银铁路、高速公路等地面保护目标的影响\n"  # 含顿号短题名 → 真标题仍升级
        "6.5 声环境影响评价\n"  # 常规标题
    )
    out = promote_headings(body)
    lines = out.splitlines()
    assert lines[0] == "1 XF1逆断层:即野麦子塘西侧断层,位于调查区的东北部,向南延伸构造线走向北北西"  # 原行保留
    assert lines[1] == "2 对于需要搬迁的村庄,须就近安置。"
    assert "#### 13.4.9 对太中银铁路、高速公路等地面保护目标的影响" in out
    assert "### 6.5 声环境影响评价" in out


def test_promote_headings_booktitle_conform():
    """书名号豁免（Task 4 实跑 80 条/16 份）：多级号+《》+无句读 ≤60 字真标题升级；
    单号法规清单段、含句读、超 60 字仍保留原行。"""
    body = (
        "3.2.1 与《宁夏回族自治区国民经济和社会发展第十四个五年规划和2035年远景目标纲要》的符合性分析\n"  # 多级号含《 → 升级
        "12 《中华人民共和国环境保护法》（2015年1月1日施行）中华人民共和国主席令第二十三号\n"  # 单号法规清单段 → 不升级
        "3.3.1 项目与《某矿区规划》逐项对比，结论如下。\n"  # 含句读 → 不升级
        "3.4.1 与《" + "某规划实施细则补充说明" * 5 + "》的符合性分析\n"  # >60 字 → 不升级
    )
    out = promote_headings(body)
    lines = out.splitlines()
    assert lines[0].startswith("#### 3.2.1 与《宁夏回族自治区国民经济")
    assert lines[1] == "12 《中华人民共和国环境保护法》（2015年1月1日施行）中华人民共和国主席令第二十三号"
    assert lines[2] == "3.3.1 项目与《某矿区规划》逐项对比，结论如下。"
    assert lines[3].startswith("3.4.1 与《")


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
