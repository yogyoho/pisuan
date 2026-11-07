"""文风门测试：四规则判定 + banned 词节级归因 + 基准缺失/章 ABSENT 的 skip 上报。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_output

# 基准 fixture：ch2 表密度带 [100,500]/万字、文表下限 1、数字密度下限 0（恒过——节标题号
# 「2.1」会贡献 ~33/千字的底噪，聚焦其他规则的用例不受其干扰）；ch9 ABSENT
# （小章稿表密度天然偏高：2 表行/83 eff 字 ≈ 241/万字——max 须配 500 才能让 PASS 用例成立）
BASE = {
    "stage": "demo",
    "banned_phrases": ["总体而言"],
    "chapters": {
        "ch2": {
            "status": "OK",
            "avg_sent_len": {"obs": 60, "min": 48, "max": 75},
            "num_per_k": {"obs": 40, "min": 0, "max": 50},
            "tbl_per_10k": {"obs": 200, "min": 100, "max": 500},
            "fig_table_ref_min": 1,
        },
        "ch9": {"status": "ABSENT"},
    },
}


def _base_with_num_min(minimum: float) -> dict:
    """数字密度 FAIL 用例专用基准：下限抬高到标题号底噪（~33/千字）之上。"""
    base = json.loads(json.dumps(BASE))
    base["chapters"]["ch2"]["num_per_k"]["min"] = minimum
    return base

OK_DRAFT = (
    "## 2.1 概况\n"
    "规划面积为86平方公里，见表2-1。评价范围内含三个井田与一处集中工业场地，"
    "可采储量合计约为12亿吨，服务年限为35年。\n"
    "| 指标 | 数值 |\n"
    "| 面积 | 86 |\n"
)


def _targets(tmp_path: Path, base: dict | None = None) -> Path:
    p = tmp_path / "style_targets_demo.json"
    p.write_text(json.dumps(base if base is not None else BASE, ensure_ascii=False), encoding="utf-8")
    return p


def test_all_pass(tmp_path):
    build_output.validate_style_gate("demo", "ch2", OK_DRAFT, targets_path=_targets(tmp_path))


def test_num_density_fail(tmp_path):
    # 长正文稀释节标题号底噪（标题号在真实章稿尺度贡献微小；极小稿会放大到 50+/千字）
    draft = (
        "## 2.1 概况\n"
        "本节说明规划概况与评价范围。规划区位于区域腹地，交通运输条件便利，水源供应稳定。"
        "矿区与周边城镇的位置关系相对清晰，防护距离满足要求。区内人口分布稀疏，主要居民点沿道路与河谷延展。"
        "地形总体呈现缓坡丘陵形态，植被覆盖程度中等。评价工作按照导则要求组织，"
        "范围界定依据规划边界与环境敏感程度综合确定。\n"
        "| 指标 | 数值 |\n"
        "| 面积 | 86 |\n"
    )
    with pytest.raises(ValueError) as e:
        build_output.validate_style_gate("demo", "ch2", draft, targets_path=_targets(tmp_path, _base_with_num_min(40)))
    assert "数字密度" in str(e.value)


def test_table_over_max_fail(tmp_path):
    rows = "\n".join(f"| a{i} | b{i} |" for i in range(30))
    draft = f"## 2.1 概况\n规划面积见表2-1。\n{rows}\n"
    with pytest.raises(ValueError) as e:
        build_output.validate_style_gate("demo", "ch2", draft, targets_path=_targets(tmp_path))
    assert "表密度" in str(e.value)


def test_fig_ref_fail(tmp_path):
    base = json.loads(json.dumps(BASE))
    base["chapters"]["ch2"]["fig_table_ref_min"] = 2
    draft = "## 2.1 概况\n规划面积为86平方公里，见表2-1。\n| 指标 | 数值 |\n| 面积 | 86 |\n"
    with pytest.raises(ValueError) as e:
        build_output.validate_style_gate("demo", "ch2", draft, targets_path=_targets(tmp_path, base))
    assert "文表联动" in str(e.value)


def test_banned_phrase_fail_with_section_attribution(tmp_path):
    draft = "## 2.1 概况\n规划面积为86平方公里，总体而言规模适中，见表2-1。\n| 指标 | 数值 |\n| 面积 | 86 |\n"
    with pytest.raises(ValueError) as e:
        build_output.validate_style_gate("demo", "ch2", draft, targets_path=_targets(tmp_path))
    msg = str(e.value)
    assert "AI 腔" in msg and "总体而言" in msg and "2.1 概况" in msg


def test_multi_fail_reports_all(tmp_path):
    """一次报齐：数字密度 + 文表联动 + AI 腔三项同章同报（长正文稀释标题号底噪）。"""
    draft = (
        "## 2.1 概况\n"
        "本节说明规划概况与评价范围。规划区位于区域腹地，交通运输条件便利，水源供应稳定。"
        "矿区与周边城镇的位置关系总体而言相对清晰，防护距离满足要求。区内人口分布稀疏，主要居民点沿道路与河谷延展。"
        "地形总体呈现缓坡丘陵形态，植被覆盖程度中等。评价工作按照导则要求组织，"
        "范围界定依据规划边界与环境敏感程度综合确定。\n"
        "| 指标 | 数值 |\n"
        "| 面积 | 86 |\n"
    )
    with pytest.raises(ValueError) as e:
        build_output.validate_style_gate("demo", "ch2", draft, targets_path=_targets(tmp_path, _base_with_num_min(40)))
    msg = str(e.value)
    assert "数字密度" in msg and "文表联动" in msg and "AI 腔" in msg


def test_missing_targets_file_skips(tmp_path, capsys):
    build_output.validate_style_gate("demo", "ch2", OK_DRAFT, targets_path=tmp_path / "nope.json")
    assert "STYLE_GATE_SKIPPED" in capsys.readouterr().out


def test_absent_chapter_skips(tmp_path, capsys):
    build_output.validate_style_gate("demo", "ch9", OK_DRAFT, targets_path=_targets(tmp_path))
    assert "STYLE_GATE_SKIPPED" in capsys.readouterr().out
