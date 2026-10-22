"""门逻辑系统性测试：形状/残留/摆位/表题合并/章深地板/节题六类正反用例（Task 10）。

覆盖「三轮人修缺陷类」的机器可验形态——签名对齐 build_output.py 现状
（validate_section / validate_residue / validate_section_title / validate_chapter_depth /
_assign_table_numbers），fixture 沿用 test_build_output_bug394 的 _mk_stage 模式。
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
    """stage forms（dict 族带 label）+ data kv 表（同 bug394 模式）。"""
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


# ── ① 形状门 ────────────────────────────────────────────────────────────────


def test_gate_shape_fail():
    """形状门正反：首行非 ### FAIL（含竖线枚举/表格粘贴/章级标题），单 ### + #### PASS。"""
    with pytest.raises(ValueError, match="首行必须是"):
        build_output.validate_section("ch6_S01", "| 列1 | 列2 |\n|---|---|\n| a | b |\n")
    with pytest.raises(ValueError, match="首行必须是"):
        build_output.validate_section("ch6_S01", "正文直接开写，没有标题。\n")
    with pytest.raises(ValueError, match="章级标题"):
        build_output.validate_section("ch6_S01", "### 6.1 沉陷\n## 6 沉陷预测\n正文。\n")
    with pytest.raises(ValueError, match="多个 ###"):
        build_output.validate_section("ch6_S01", "### 6.1 沉陷\n正文。\n### 6.2 声环境\n正文。\n")
    ok = "### 6.1 地表沉陷预测\n正文一句。正文两句。正文三句。\n#### 6.1.1 预测方法\n子节正文。\n"
    build_output.validate_section("ch6_S01", ok)  # 不抛即过


# ── ② 残留扫描门 ────────────────────────────────────────────────────────────


def test_gate_slot_residue():
    """残留门正反：未注入槽位/畸形槽位/XX 占位 FAIL；[待确认] 与干净正文 PASS。"""
    for bad in ("源强为 {{SLOT:q1}}。", "数值 {SLOT:q1} 畸形。", "取 XX 值。", "（未知表单族 xx）"):
        with pytest.raises(ValueError, match="残留扫描门"):
            build_output.validate_residue("ch6", f"### 6.1 沉陷\n{bad}\n")
    build_output.validate_residue("ch6", "### 6.1 沉陷\n最大下沉值为 2600mm，缺项标 [待确认]。\n")


# ── ③ 摆位门 ────────────────────────────────────────────────────────────────


def test_gate_table_placement():
    """摆位门四例：句中嵌 FAIL×3 + 独立行 PASS；连排标记/表后紧邻亦 PASS。"""
    with pytest.raises(ValueError, match="独立成行"):
        build_output.validate_section(
            "ch6_S01", "### 6.1 沉陷\n沉陷参数体系及其逐井输入条件以{{TABLE:subsidence_params}}\n"
        )
    with pytest.raises(ValueError, match="独立成行"):
        build_output.validate_section("ch6_S01", "### 6.1 沉陷\n主要参数如下表所列：{{TABLE:subsidence_params}}\n")
    with pytest.raises(ValueError, match="句末标点收束"):
        build_output.validate_section("ch6_S01", "### 6.1 沉陷\n沉陷参数体系以\n{{TABLE:subsidence_params}}\n")
    ok = "### 6.1 沉陷\n主要参数如下表所列。\n{{TABLE:subsidence_params}}\n"
    build_output.validate_section("ch6_S01", ok)
    # 连排多表（prev=标记行）与表后紧跟表（prev=表行）均合法
    build_output.validate_section(
        "ch6_S01", "### 6.1 沉陷\n两类参数分别如下。\n{{TABLE:subsidence_params}}\n{{TABLE:subsidence_params}}\n"
    )
    build_output.validate_section(
        "ch6_S01", "### 6.1 沉陷\n| a | b |\n|---|---|\n| 1 | 2 |\n{{TABLE:subsidence_params}}\n"
    )


# ── ④ 表题行合并 ────────────────────────────────────────────────────────────


def test_gate_caption_merge(tmp_path):
    """写手表题行合并（bug394 补正反例）：紧邻机表占位（隔空行亦可）→ 名留号机发；
    后随正文行（非表）→ 不合并，写手自编号保留原文。"""
    stage, data_dir = _mk_stage(tmp_path)
    inject, _ = _inject_of(stage, data_dir)
    # 合并：写手名优先，占位族名让位，机发序号
    out = inject("沉陷预测参数见表。\n\n表 6-2 沉陷预测参数一览\n\n{{TABLE:subsidence_params}}\n")
    assert "**表 6-1 沉陷预测参数一览**" in out
    assert "表 6-2" not in out and "⟦TBLNO⟧" not in out
    # 反例（隔正文行不合并）：写手表题行后随正文 → 原文保留、不落号
    inject2, _ = _inject_of(stage, data_dir)  # 独立 ctx：序号从 1 重新机发
    out2 = inject2("表 6-1 沉陷预测参数一览\n\n下表所列参数来源于实测。\n\n{{TABLE:subsidence_params}}\n")
    assert "表 6-1 沉陷预测参数一览" in out2  # 写手行原文保留（未紧邻机表）
    assert "**表 6-1 沉陷预测参数**" in out2  # 机表照常落号


# ── ⑤ 章深地板门 ────────────────────────────────────────────────────────────


def test_gate_depth_floor():
    """L2 章深地板：低于 floor_chars FAIL（值内嵌报错行），达标 PASS 返回 (eff, floor)。"""
    targets = {"chapters": {"ch6": {"floor_chars": 100}}}
    body = "一字一句。" * 40  # effective_chars 计非标题非表格行的去装饰字符
    eff, floor = build_output.validate_chapter_depth("ch6", f"## 6 沉陷\n{body}\n", targets)
    assert eff >= 100 and floor == 100
    with pytest.raises(ValueError, match="L2 深度门"):
        build_output.validate_chapter_depth("ch6", "## 6 沉陷\n太短。\n", targets)
    # 无 targets → 缺省绝对地板
    assert build_output.chapter_floor(None, "ch6") == build_output.DEFAULT_CHAPTER_FLOOR_CHARS


# ── ⑥ 节题相符门 ────────────────────────────────────────────────────────────


def test_gate_section_title():
    """节题语义匹配：编号无关、双向包含；语义无关 FAIL。"""
    build_output.validate_section_title("ch6_S01", "### 6.1 地表沉陷预测\n正文。\n", "沉陷预测")
    build_output.validate_section_title("ch6_S05", "### 6.5 声环境影响评价\n正文。\n", "声环境影响评价")
    with pytest.raises(ValueError, match="节题"):
        build_output.validate_section_title("ch6_S05", "### 6.5 固体废物影响\n正文。\n", "声环境影响评价")
