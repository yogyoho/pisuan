# auto_select_table_preset 单测：表格占比阈值、显式预设跳过、幂等标记。
from yuxi.knowledge.chunking.ragflow_like.dispatcher import auto_select_table_preset


def md_with_tables(n: int) -> str:
    # 单元：48 字表格 + 100 字正文 → 占比 32% ≥ 阈值
    one = "<table><tr><td>类别</td><td>耕地</td></tr></table>" + "正文段落。" * 20
    return one * n


def test_high_ratio_switches_to_table():
    md = md_with_tables(3)  # 表格占比 > 30%
    params = auto_select_table_preset(md, {})
    assert params["chunk_preset_id"] == "table"
    assert params["chunk_preset_auto"] == "table"


def test_low_ratio_no_switch():
    md = md_with_tables(0) + "纯文本。" * 500  # 无表格
    params = auto_select_table_preset(md, {})
    assert "chunk_preset_id" not in params
    md2 = md_with_tables(1) + "纯文本。" * 2000  # 占比 < 30%
    params2 = auto_select_table_preset(md2, {})
    assert "chunk_preset_id" not in params2


def test_explicit_preset_wins():
    md = md_with_tables(3)
    params = auto_select_table_preset(md, {"chunk_preset_id": "semantic"})
    assert params["chunk_preset_id"] == "semantic"
    assert "chunk_preset_auto" not in params


def test_idempotent_after_auto_switch():
    md = md_with_tables(3)
    once = auto_select_table_preset(md, {})
    twice = auto_select_table_preset(md, once)
    assert twice["chunk_preset_id"] == "table"
    assert twice["chunk_preset_auto"] == "table"
