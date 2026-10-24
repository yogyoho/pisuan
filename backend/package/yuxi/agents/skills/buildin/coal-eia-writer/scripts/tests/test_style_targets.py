"""style_targets 生成测试：mini-bank fixture 精确数值 + 章目录对齐纪律（清单外目录忽略上报）。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from style_targets import generate

# fixture 文本均经实现口径逐字符核对：ch1 两切片全文 eff=91（54+37，含表格行）、
# 表行 4、表格块 2、文表引用 2、正文 eff=64、正文数字 9 → num_per_k=140.6；
# 分句 24/14/23 → 均句长 20.3
A1 = (
    "## 1 总则\n"
    "本次评价范围面积为86平方公里，见表1-1。\n"
    "| 指标 | 数值 |\n"
    "| 面积 | 86 |\n"
    "由表1-1可知，规划面积明确。\n"
)
B1 = (
    "## 1.2 评价时段\n"
    "评价时段为2025年至2035年。\n"
    "| 时段 | 年限 |\n"
    "| 近期 | 5 |\n"
)
A2 = "## 2 规划概况\n矿区位于某省某市，含三个井田。\n"
C4 = "## 4 识别\n由表4-1识别结果，见表4-2清单，由表4-3因子，详见表4-4。\n"  # 单文件 4 处引用


def _mk_bank(tmp: Path) -> Path:
    (tmp / "slices" / "ch1").mkdir(parents=True)
    (tmp / "slices" / "ch2").mkdir(parents=True)
    (tmp / "slices" / "ch4").mkdir(parents=True)
    (tmp / "slices" / "ch99").mkdir(parents=True)  # 清单外目录（碎段噪声）
    (tmp / "slices" / "ch1" / "a__1.md").write_text(A1, encoding="utf-8")
    (tmp / "slices" / "ch1" / "b__1.md").write_text(B1, encoding="utf-8")
    (tmp / "slices" / "ch2" / "a__2.md").write_text(A2, encoding="utf-8")
    (tmp / "slices" / "ch4" / "a__4.md").write_text(C4, encoding="utf-8")
    (tmp / "slices" / "ch99" / "junk__99.md").write_text("## 1600 ∞\n噪声\n", encoding="utf-8")
    stage = {
        "chapters": {
            "ch1": {"sections": ["s1", "s2"]},
            "ch2": {"sections": ["s1"]},
            "ch3": {"sections": ["s1"]},  # 清单内有、bank 无目录 → ABSENT
            "ch4": {"sections": ["s1"]},
        }
    }
    (tmp / "stage.json").write_text(json.dumps(stage, ensure_ascii=False), encoding="utf-8")
    return tmp


def test_generate_structure_and_absent(tmp_path):
    bank = _mk_bank(tmp_path)
    r = generate("demo", bank, tmp_path / "stage.json")
    assert set(r["chapters"]) == {"ch1", "ch2", "ch3", "ch4"}
    assert r["chapters"]["ch3"] == {"status": "ABSENT"}
    assert r["ignored_dirs"] == ["ch99"]
    assert r["stage"] == "demo"
    assert len(r["banned_phrases"]) == 11 and "总体而言" in r["banned_phrases"]
    assert "_comment" in r


def test_minibank_exact_metrics(tmp_path):
    bank = _mk_bank(tmp_path)
    c1 = generate("demo", bank, tmp_path / "stage.json")["chapters"]["ch1"]
    assert c1["status"] == "OK"
    assert c1["effective_chars"] == 91
    assert c1["table_rows"] == 4
    assert c1["table_blocks"] == 2
    assert c1["fig_refs"] == 2
    # 文表联动下限 = max(1, round(单份平均 refs×0.5))；ch1 两文件 2 refs → 地板 1
    assert c1["fig_table_ref_min"] == 1
    assert c1["num_per_k"]["obs"] == pytest.approx(140.6, abs=0.2)
    assert c1["avg_sent_len"]["obs"] == pytest.approx(20.3, abs=0.2)


def test_zero_table_chapter_floor(tmp_path):
    """零表章（如结论章）：表密度 obs=0，文表联动下限落 max(1,·) 地板。"""
    bank = _mk_bank(tmp_path)
    c2 = generate("demo", bank, tmp_path / "stage.json")["chapters"]["ch2"]
    assert c2["status"] == "OK"
    assert c2["table_blocks"] == 0
    assert c2["tbl_per_10k"]["obs"] == 0
    assert c2["fig_table_ref_min"] == 1


def test_fig_ref_min_per_report_scale(tmp_path):
    """文表引用下限按单份平均×0.5（ch1 两文件共 2 refs → 地板 1；ch4 单文件 4 refs → 2）。"""
    bank = _mk_bank(tmp_path)
    chs = generate("demo", bank, tmp_path / "stage.json")["chapters"]
    assert chs["ch1"]["fig_table_ref_min"] == 1
    assert chs["ch4"]["fig_refs"] == 4
    assert chs["ch4"]["fig_table_ref_min"] == 2


def test_band_formula(tmp_path):
    """区间 = 实测×0.8 下限 / ×1.25 上限。band 基于未取整原始值，obs 已取整，
    反算偏差上界 = obs 取整 0.05×系数 + min/max 取整 0.05 → 容差 0.12。"""
    bank = _mk_bank(tmp_path)
    c1 = generate("demo", bank, tmp_path / "stage.json")["chapters"]["ch1"]
    for key in ("num_per_k", "avg_sent_len", "tbl_per_10k"):
        obs = c1[key]["obs"]
        assert c1[key]["min"] == pytest.approx(obs * 0.8, abs=0.12), key
        assert c1[key]["max"] == pytest.approx(obs * 1.25, abs=0.12), key
