"""bug-393 回归测试：markdown 表格 cell 含裸 '|'（表头列数膨胀/数据行断裂）。

背景（test2 交付稿实测，349 张表 + 8 行）：机器渲染表的表头 label 自带竖线枚举
（stage forms 列定义「时相(现状|三期对比各期)」式），表头 cell 数膨胀与分隔行
不齐，GFM 判列数不匹配拒渲染整表；一致性附录 warn 行详情 cell 含槽位寻址记法
「collapse_height[王坡一号井|层1]」同样入裸竖线。
修复（build_output._md_table 单一咽喉，全部机器表均经此渲染）：
  1. 表头 cell 含 '|' = 结构错误硬 FAIL（bug-366 先例：stage 资产修源头，
     同时拦截上游同步回灌）；
  2. 数据 cell 含 '|' = 转义 '\\|'（槽位寻址等正当内容保真渲染）。
stdlib-only，不依赖容器。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_output  # noqa: E402


def test_clean_table_unchanged():
    out = build_output._md_table(["地类", "面积"], [["有林地", "2610"]])
    assert out == "| 地类 | 面积 |\n|---|---|\n| 有林地 | 2610 |"


def test_header_pipe_hard_fail():
    with pytest.raises(ValueError, match="时相"):
        build_output._md_table(["地类", "时相(现状|三期对比各期)"], [["有林地", "现状"]])


def test_data_cell_pipe_escaped():
    out = build_output._md_table(
        ["级别", "详情"],
        [["warn", "collapse_height[王坡一号井|层1]=26.00（未精确引用）"]],
    )
    assert r"collapse_height[王坡一号井\|层1]=26.00" in out
    assert out.split("\n")[0] == "| 级别 | 详情 |"
