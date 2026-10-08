"""bank_compile slice_report 测试：切片归并 + 重复章号消解（保留最长块，2026-10-08 裁决）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import slice_report


def test_slice_report_unique_baseline():
    """无重复：连续同章归并、子节归父片、secs 记完整节号。"""
    text = "## 1 总论\n正文A\n### 1.1 目的\n正文B\n## 2 概况\n正文C\n"
    slices, dup = slice_report(text)
    assert dup == []
    assert [s["chapter"] for s in slices] == ["1", "2"]
    assert slices[0]["secs"] == [{"sec": "1", "title": "总论"}, {"sec": "1.1", "title": "目的"}]
    assert "正文A" in slices[0]["seg"] and "正文B" in slices[0]["seg"]
    assert "正文C" in slices[1]["seg"]


def test_slice_report_dup_keeps_longest_block():
    """重复章号（001 月儿湾形态：真章块后混入局部编号碎片）→ 保留最长块。"""
    text = (
        "## 1 总论\n开头\n## 2 概况\n" + "真块正文" * 40
        + "\n## 3 中间\n中段正文\n## 2 计算步骤\n碎片\n## 4 结论\n末段\n"
    )
    slices, dup = slice_report(text)
    assert dup == ["2"]
    assert [s["chapter"] for s in slices] == ["1", "2", "3", "4"]  # ch2' 弃置，真块在位
    ch2 = next(s for s in slices if s["chapter"] == "2")
    assert ch2["secs"] == [{"sec": "2", "title": "概况"}]  # 碎片标题不进 secs
    assert "碎片" not in ch2["seg"] and "真块正文" in ch2["seg"]


def test_slice_report_dropped_block_merges_into_predecessor():
    """被弃块正文不丢：其文本并入前一保留块的 seg（局部清单语义上属于所在章正文）。

    月儿湾保煤柱形态：ch6 碎片（采区边界煤柱）弃置，真 ch6（生态环境）保留，
    ch5 的 seg 延展吞入 ch6 碎片与中间 ch7 块之前的正文。"""
    text = (
        "## 5 沉陷\n五章正文\n## 6 采区边界煤柱\n清单碎片\n## 7 巷道煤柱\n又一片\n"
        "## 6 生态环境\n" + "六章正文" * 10 + "\n## 8 结论\n尾\n"
    )
    slices, dup = slice_report(text)
    assert dup == ["6"]
    ch5 = next(s for s in slices if s["chapter"] == "5")
    ch6 = next(s for s in slices if s["chapter"] == "6")
    ch7 = next(s for s in slices if s["chapter"] == "7")
    assert "清单碎片" in ch5["seg"]  # 被弃 ch6 碎片并入前块
    assert "又一片" not in ch5["seg"] and "又一片" in ch7["seg"]  # ch7 是保留块，不吞
    assert "六章正文" not in ch5["seg"]
    assert "六章正文" in ch6["seg"] and "清单碎片" not in ch6["seg"]


def test_slice_report_appendix_repeat_resolved():
    """附录局部编号（1-4 全列重复）消解：真章宏观块保留，附录碎片并入末章 seg。"""
    real = "".join(f"## {n} 真{n}\n" + "章宏观正文" * 30 + "\n" for n in range(1, 5))
    appendix = "".join(f"## {n} 步骤{n}\n步骤说明\n" for n in range(1, 5))
    text = real + "附录：计算方法\n" + appendix
    slices, dup = slice_report(text)
    assert dup == ["1", "2", "3", "4"]
    assert [s["chapter"] for s in slices] == ["1", "2", "3", "4"]
    for s in slices:
        assert "章宏观正文" in s["seg"]
    assert "步骤说明" not in slices[0]["seg"]  # 前三章不含附录碎片
    assert "步骤说明" in slices[3]["seg"]  # 末章吞入附录残余
