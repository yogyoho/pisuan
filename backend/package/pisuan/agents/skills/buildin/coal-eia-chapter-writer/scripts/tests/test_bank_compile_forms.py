"""forms_catalog 形态统计测试：table_lead 三形态 / numeric_citation / 例句溯源。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import classify_table_lead, build_forms_catalog


def test_classify_table_lead():
    assert classify_table_lead("矿区主要噪声源及其源强如下表所列。") == "complete_sentence"
    assert classify_table_lead("评价标准如下表所示：") == "complete_sentence"
    assert classify_table_lead("各源强参数见下表。") == "complete_sentence"
    assert classify_table_lead("沉陷参数体系及其逐井输入条件以") == "dangling"  # bug-394 同款残句
    assert classify_table_lead("**表 6-1 源强**") == "standalone_caption"
    assert classify_table_lead("表 6-1 源强") == "standalone_caption"  # 裸题注（本管线 docx→md 无粗体）
    assert classify_table_lead("表1.4-1") == "standalone_caption"  # 章内号 N.M-M——语料主流形态（7698/7969）
    assert classify_table_lead("表 6-1-1\t情景对照表") == "standalone_caption"  # 三段号


def test_build_forms_catalog_example_quota_per_form():
    """例句池按形态配额（各 20）：文档序填充不被主导形态灌满，两种引导句都有正样本。"""
    dangling = "沉陷参数体系及其逐井输入条件以\n| a | 1 |\n|---|---|\n| b | 2 |\n"
    complete = "噪声源如下表所列。\n| a | 1 |\n|---|---|\n| b | 2 |\n"
    segs = [(f"r{i}", dangling if i % 2 else complete) for i in range(30)]
    cat = build_forms_catalog(segs)
    examples = cat["forms"]["table_lead"]["examples"]
    by_form = {}
    for e in examples:
        by_form.setdefault(e["form"], []).append(e)
    assert len(by_form.get("complete_sentence", [])) == 15
    assert len(by_form.get("dangling", [])) == 15
    assert all("沉陷参数体系" in e["text"] for e in by_form["dangling"])


def test_build_forms_catalog():
    """锚点=GFM 表块首行（语料实测 8584 块）：无题注块 prev=引导句（complete），
    有题注块 prev=题注行（standalone）；数值引用例句带 report_id 溯源。"""
    segs = [
        ("rid1", "矿区主要噪声源如下表所列。\n\n| 源 | 强度 |\n|---|---|\n| a | 1 |\n\n厂界噪声为 60 dB(A)。\n"),
        ("rid2", "**表 6-2 标准**\n\n| 指标 | 值 |\n|---|---|\n| b | 2 |\n\n源强为 95 dB(A)。\n"),
    ]
    cat = build_forms_catalog(segs)
    tl = cat["forms"]["table_lead"]
    assert tl["stats"]["complete_sentence"] == 0.5
    assert tl["stats"]["standalone_caption"] == 0.5
    assert tl["examples"][0]["report_id"] == "rid1"  # complete 正样本入池
    nc = cat["forms"]["numeric_citation"]
    assert nc["stats"]["exact_with_unit"] == 1.0   # 两句数值均带 dB(A)
    assert {e["report_id"] for e in nc["examples"]} == {"rid1", "rid2"}


def test_build_forms_catalog_multi_table_block():
    """连续表行只锚块首（每表恰测一次）。"""
    seg = "引导句如下。\n| a | 1 |\n| b | 2 |\n"
    cat = build_forms_catalog([("r1", seg)])
    assert cat["forms"]["table_lead"]["stats"]["complete_sentence"] == 1.0
