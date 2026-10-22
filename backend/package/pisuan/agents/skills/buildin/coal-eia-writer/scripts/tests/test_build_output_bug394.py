"""bug-394 回归测试：表格编号/表题注入 + {{TABLE:}} 摆位门。

背景（test2 交付稿实测）：① 写手把 {{TABLE:族}} 嵌在句中（「…输入条件以{{TABLE:…}}」），
注入后表格从句中炸出，衔接句被切断；② 管线无表号体系——kv 表无表题、行表题
「**label**（N 行）」是开发者腔，第一章写手自发的「表 1-1」与其余章无号并存。
修复（组装单点收口）：render_family 发射 ⟦TBLNO⟧ 占位表题（族 label 为名），
_assign_table_numbers 落章内机发序号「表 {ch}-{seq}」，写手自带表题行合并（名留号机发）；
validate_section 增摆位门（标记独立成行 + 前文完整句收束）。
stdlib-only，不依赖容器。
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_output  # noqa: E402


def _mk_stage(tmp_path: Path) -> tuple[dict, Path]:
    """stage forms（dict 族带 label）+ data kv 表。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "params.json").write_text(
        json.dumps({"max_subsidence": "2600", "boundary_angle": "68"}, ensure_ascii=False),
        encoding="utf-8",
    )
    stage = {
        "forms": {
            "subsidence_params": {
                "file": "params.json",
                "label": "沉陷预测参数",
                "fields": [
                    {"name": "max_subsidence", "label": "最大下沉值(mm)"},
                    {"name": "boundary_angle", "label": "边界角(°)"},
                ],
            }
        }
    }
    return stage, data_dir


def _inject_of(stage: dict, data_dir: Path, ch_no: str = "6"):
    unknown: set[str] = set()
    ctx = {"ch_no": ch_no, "seq": itertools.count(1)}
    return build_output.make_inject(stage, data_dir, {}, unknown, ctx=ctx), unknown


def test_kv_caption_numbered(tmp_path):
    """kv 表带表题行 + 章内机发序号。"""
    stage, data_dir = _mk_stage(tmp_path)
    inject, _ = _inject_of(stage, data_dir)
    out = inject("沉陷预测结果如下表所列。\n\n{{TABLE:subsidence_params}}\n")
    assert "**表 6-1 沉陷预测参数**" in out
    assert "| 指标 | 数值 |" in out
    assert "⟦TBLNO⟧" not in out


def test_numbers_sequential_in_chapter(tmp_path):
    """同章两表序号连续（表 6-1、表 6-2）。"""
    stage, data_dir = _mk_stage(tmp_path)
    inject, _ = _inject_of(stage, data_dir)
    text = "参数如下表所列。\n\n{{TABLE:subsidence_params}}\n\n汇总如下表所列。\n\n{{TABLE:subsidence_params}}\n"
    out = inject(text)
    assert "表 6-1 沉陷预测参数" in out
    assert "表 6-2 沉陷预测参数" in out


def test_writer_caption_merged():
    """写手自带表题行：号改机发、名保留。"""
    text = "表 1-1 井田特征\n\n| 指标 | 数值 |\n|---|---|\n| 井田面积 | 102.7 |"
    out = build_output._assign_table_numbers(text, {"ch_no": "1", "seq": itertools.count(1)})
    assert "**表 1-1 井田特征**" in out
    lines = out.split("\n")
    assert lines[0] == "**表 1-1 井田特征**"


def test_writer_caption_kept_without_ch_no():
    """工具调用路径（无 ch_no）：写手表题行原样保留，占位剥为纯表题。"""
    out = build_output._assign_table_numbers(
        "**⟦TBLNO⟧ 沉陷预测参数**\n\n| 指标 | 数值 |",
        {"ch_no": "", "seq": itertools.count(1)},
    )
    assert out.startswith("**沉陷预测参数**")


def test_prose_line_not_matched():
    """叙述句里的「表 X-N」不在表上方 → 不误改。"""
    text = "采区划分见表 3-2，各采区接续时序详见表 3-3。"
    out = build_output._assign_table_numbers(text, {"ch_no": "3", "seq": itertools.count(1)})
    assert out == text


def test_writer_caption_above_marker_merged():
    """写手表题行紧邻机表占位：并入机表表题（写手名 + 机发号），自编号行删除。"""
    text = "表 1-1 井田特征\n\n**⟦TBLNO⟧ 项目基本情况**\n\n| 指标 | 数值 |\n|---|---|\n| 井田面积 | 102.7 |"
    out = build_output._assign_table_numbers(text, {"ch_no": "1", "seq": itertools.count(1)})
    assert "**表 1-1 井田特征**" in out
    assert "⟦TBLNO⟧" not in out
    assert "项目基本情况**" not in out
    assert out.split("\n")[0] == "**表 1-1 井田特征**"


def test_gate_writer_caption_before_marker_passes():
    build_output.validate_section("ch1_S01", "### 1.1 概况\n表 1-1 项目基本情况\n\n{{TABLE:project}}\n")


def test_missing_family_label_hard_fail(tmp_path):
    """族缺 label = 结构错误硬 FAIL（表题行需要族名）。"""
    data_dir = tmp_path / "d"
    data_dir.mkdir()
    (data_dir / "x.json").write_text("{}", encoding="utf-8")
    stage = {"forms": {"nofam": {"file": "x.json"}}}
    with pytest.raises(ValueError, match="label"):
        build_output.render_family("nofam", stage, data_dir)


# ── 摆位门 ──────────────────────────────────────────────────────────────────


def test_gate_inline_marker_fails():
    with pytest.raises(ValueError, match="独立成行"):
        build_output.validate_section("ch6_S02", "### 6.2 参数\n本节所依据的参数以{{TABLE:subsidence_params}}为准。")


def test_gate_incomplete_lead_in_fails():
    with pytest.raises(ValueError, match="句末标点"):
        build_output.validate_section(
            "ch6_S02", "### 6.2 参数\n本节所依据的沉陷参数体系及其逐井输入条件以\n{{TABLE:subsidence_params}}\n"
        )


def test_gate_legal_placements_pass():
    ok = [
        # 完整句 + 标记
        "### 6.2 参数\n主要参数如下表所列。\n\n{{TABLE:subsidence_params}}\n",
        # 连排两标记
        "### 6.2 参数\n参数如下表所列。\n\n{{TABLE:subsidence_params}}\n\n{{TABLE:subsidence_params}}\n",
        # 表后紧跟表（前一行是表行）
        "### 6.2 参数\n参数如下两表所列。\n\n{{TABLE:subsidence_params}}\n\n| 指标 | 数值 |\n|---|---|\n| a | 1 |\n\n{{TABLE:subsidence_params}}\n",
        # 冒号收束也合法
        "### 6.2 参数\n主要参数如下：\n\n{{TABLE:subsidence_params}}\n",
    ]
    for text in ok:
        build_output.validate_section("ch6_S02", text)  # 不抛即过
