"""bug-395 回归测试：NR1 表/图号声明不认机器粗体表题行。

背景：bug-394 后全书表题统一为「**表 X-Y 名称**」粗体行（1128 张），
CAPTION_RE 只认行首裸「表 X-Y」→ 声明集为空，REF_RE 收进的正文引用全部
误报 NR1 warn「引用了未声明的表/图号」。修复：CAPTION_RE 兼容可选 `**`
前缀（裸格式保留兼容旧稿/单章输出）。
stdlib-only，不依赖容器。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import consistency  # noqa: E402


def _run(chapters):
    rep = consistency.Report()
    consistency.check_nr(rep, chapters)
    return {i["contract"]: i for i in rep.items}


def test_bold_caption_declared_no_dangling():
    """机器粗体表题入声明集：正文引用不再误报未声明。"""
    body = "本节参数如下表所列。\n\n**表 6-1 沉陷预测参数**\n\n| 指标 | 数值 |\n|---|---|\n| 下沉 | 2600 |"
    items = _run([("ch6 环境影响预测", body)])
    assert "warn" not in items["NR1"]["severity"]
    assert items["NR1"]["severity"] == "pass"
    assert "表/图号声明 1 个" in items["NR1"]["detail"]


def test_plain_caption_still_declared():
    """裸表题行（旧稿/写手格式）仍认。"""
    body = "规划标识统一列于表 1-1。\n\n表 1-1 项目基本情况\n\n| 指标 | 数值 |\n|---|---|\n| 井田 | 王坡 |"
    items = _run([("ch1 总则", body)])
    assert items["NR1"]["severity"] == "pass"


def test_dangling_ref_still_warns():
    """真悬空引用仍要 warn（防线不放松）。"""
    body = "见下表。\n\n**表 6-1 参数**\n\n| 指标 | 数值 |\n|---|---|\n| a | 1 |\n\n其余见表 6-9。"
    items = _run([("ch6 预测", body)])
    assert items["NR1"]["severity"] == "warn"
    assert "表6-9" in items["NR1"]["detail"]


def test_dup_across_formats():
    """同号重声明（裸 + 粗体）跨章仍判重号 fail。"""
    b1 = "**表 3-1 监测**\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    b2 = "详见表 3-1。\n\n表 3-1 监测\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    items = _run([("ch3 现状", b1), ("ch4 补充", b2)])
    assert items["NR1"]["severity"] == "fail"
    assert "表3-1" in items["NR1"]["detail"]
