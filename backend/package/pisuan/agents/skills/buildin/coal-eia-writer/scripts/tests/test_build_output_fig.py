"""R5 插图占位回归：{{FIG:图名}} 合法保留 + 空图名/畸形 FAIL + SLOT/TABLE 残留不回归。

背景（docs/vibe/2026-10-27-post-confirm-revision-and-figure-slots.md R5）：交付稿在适图位置
保留插图占位（不产真图，用户后续自行插入），占位形如 {{FIG:矿区井田划分图}}；门只校验形
合法（双括号规整、图名非空），不校验插图内容本身。stdlib-only，不依赖容器。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_output  # noqa: E402


def test_fig_placeholder_passes_residue_gate():
    """合法 FIG 占位原样保留——不触发残留扫描门。"""
    text = "矿区范围及井田划分见图。\n\n{{FIG:矿区井田划分图}}\n\n建议插图：井田边界与采区划分示意。\n"
    build_output.validate_residue("ch2_S01", text)  # 不抛即过


def test_fig_fullwidth_colon_passes():
    """全角冒号形宽容收（{{FIG：图名}}）——写手手输常见变体。"""
    build_output.validate_residue("ch2_S01", "沉陷预测布点见图。\n\n{{FIG：沉陷预测布点示意图}}\n")


@pytest.mark.parametrize("bad", ["{{FIG:}}", "{{FIG:   }}", "{{FIG：}}"])
def test_fig_empty_name_fails(bad):
    """空图名 FAIL（占位须业务语图名）。"""
    with pytest.raises(ValueError, match="FIG"):
        build_output.validate_residue("ch2_S01", f"井田划分如下。\n\n{bad}\n")


@pytest.mark.parametrize("bad", ["{FIG:矿区井田划分图}", "{{FIG:矿区井田划分图}单位}"])
def test_fig_malformed_fails(bad):
    """畸形 FIG（单括号/错配收形）FAIL——防字面量污染交付稿（N19 同构）。"""
    with pytest.raises(ValueError, match="FIG"):
        build_output.validate_residue("ch2_S01", f"井田划分如下。\n\n{bad}\n")


@pytest.mark.parametrize("mark", ["{{SLOT:mine_area}}", "{{TABLE:landuse}}", "{{FORM:legacy}}"])
def test_slot_table_residue_regression(mark):
    """SLOT/TABLE/FORM 残留照旧 FAIL——FIG 放行不放宽既有校验。"""
    with pytest.raises(ValueError):
        build_output.validate_residue("ch2_S01", f"参数如下。\n\n{mark}\n")
