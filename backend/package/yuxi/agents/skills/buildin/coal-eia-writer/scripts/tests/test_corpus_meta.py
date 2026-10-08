"""corpus_meta 测试：省名三级判定 / 标准号归一 / 附件两种形态抽取 / 条目归一 /
分档阈值 / annotations 合并 / 幂等字节（vibe 2026-10-08-corpus-meta-and-attachment-checklist）。

stdlib-only，不依赖容器；fixture 沿 samples_bank/<stage>/slices/chX/<rid>__N.md 布局。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import corpus_meta  # noqa: E402


def _mk_slice(slices_root: Path, stage: str, rid: str, text: str) -> None:
    d = slices_root / stage / "slices" / "ch1"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}__0.md").write_text(text, encoding="utf-8")


# ── ① 标准号归一 ────────────────────────────────────────────────────────────


def test_normalize_standard_variants():
    """空格 / 全角破折号 / DB 地标 皆归一到无空格连字符形。"""
    assert corpus_meta.normalize_standard("HJ 2.2-2018") == "HJ2.2-2018"
    assert corpus_meta.normalize_standard("GB 20426—2006") == "GB20426-2006"
    assert corpus_meta.normalize_standard("HJ619–2011") == "HJ619-2011"
    assert corpus_meta.normalize_standard("DB15/ 2346-2021") == "DB15/2346-2021"
    assert corpus_meta.extract_standards("依据 HJ 2.2-2018 与 GB20426—2006；HJ 2.2-2018 重复。") == [
        "GB20426-2006",
        "HJ2.2-2018",
    ]


# ── ② 省名三级判定 ──────────────────────────────────────────────────────────


def test_detect_province_three_tiers():
    """manual 注 > 频次胜者（≥3 且严格第一）> needs_review（带候选）。"""
    ann = {"province": "甘肃"}
    assert corpus_meta.detect_province("灵台在陕西与河南之间提及。", ann) == {
        "value": "甘肃",
        "basis": "manual",
    }
    clear = "项目位于新疆哈密市。新疆矿区……新疆……新疆……"
    assert corpus_meta.detect_province(clear, {}) == {"value": "新疆", "basis": "regex"}
    tie = "陕西一处。甘肃一处。河南一处。"
    out = corpus_meta.detect_province(tie, {})
    assert out["basis"] == "needs_review" and set(out["candidates"]) == {"陕西", "甘肃", "河南"}


# ── ③ 附件清单抽取 ──────────────────────────────────────────────────────────


def test_extract_annex_items_two_forms():
    """裸头编号行（隔空行）与行内 附录N:/附件N:/附录N 空格 三形态；正文内联「见附图」
    与「附录2016」数字粘连不误收。"""
    text = (
        "### 13 结论\n结论正文。\n\n附  录\n\n1、委托函;\n\n2、《审查意见》(环审〔2022〕10号)。\n"
        "\n### 后记\n见附图6.1-1。\n附录26:监测报告。\n附件1:采矿许可证。\n附录1 委托书\n"
        "附录2016年规划批复。\n"
    )
    items = corpus_meta.extract_annex_items(text)
    assert items == ["委托函", "《审查意见》", "监测报告", "采矿许可证", "委托书"]


def test_normalize_item_strips_docno_and_punct():
    """去文号括注（圆括号/裸尾）与尾标点，保书名号；内部空白折叠。"""
    assert corpus_meta.normalize_item("《意见》(环审〔2022〕10号)；") == "《意见》"
    assert corpus_meta.normalize_item("公众参与调查表。") == "公众参与调查表"
    assert corpus_meta.normalize_item("取水  许可决定书（黄许可〔2023〕63号）") == "取水 许可决定书"
    assert corpus_meta.normalize_item('州政府"关于调整方案的请示",伊州政〔2020〕127号') == '州政府"关于调整方案的请示"'
    assert corpus_meta.normalize_item("关于文物保护的复函 新文旅复函〔2021〕757号") == "关于文物保护的复函"


# ── ④ 规模抽取 ──────────────────────────────────────────────────────────────


def test_scale_extraction_mt_normalization():
    """万t/a、万吨/年 归一为 Mt/a；多候选分歧 → needs_review 带候选。"""
    assert corpus_meta.extract_scale("设计生产能力800万t/a，") == {"value": 8.0, "basis": "regex"}
    assert corpus_meta.extract_scale("建设规模：1000万吨/年。") == {"value": 10.0, "basis": "regex"}
    out = corpus_meta.extract_scale("生产规模500万t/a。后文又写产能 12.0Mt/a。")
    assert out["basis"] == "needs_review" and len(out["candidates"]) == 2


# ── ⑤ 分档与 base 不足 ──────────────────────────────────────────────────────


def test_checklist_tiers_and_insufficient_base(tmp_path):
    """required ≥0.8 且 base≥5；0.3–0.8 common；<0.3 略去；base<5 整档 insufficient_base。"""
    root = tmp_path / "samples_bank"
    for i in range(5):
        _mk_slice(root, "stage_a", f"r{i}", "附录:\n1、公众参与调查表;\n" if i < 4 else "附录:\n1、监测报告。\n")
    _mk_slice(root, "stage_b", "r9", "附录:\n1、公众参与调查表;\n")
    doc = corpus_meta.build_attachment_checklist(root)
    a = doc["stages"]["stage_a"]
    assert a["base_reports"] == 5
    assert a["required"] == [{"item": "公众参与调查表", "freq": 0.8, "n_reports": 4}]
    assert a["common"] == []  # 监测报告 freq=0.2 < 0.3 下限 → 略去
    b = doc["stages"]["stage_b"]
    assert b["insufficient_base"] is True and b["base_reports"] == 1
    assert doc["provenance_note"].startswith("案例层统计")


# ── ⑥ 合并与确定性 ──────────────────────────────────────────────────────────


def test_corpus_meta_aggregates_slices(tmp_path):
    """整报告字段按 rid 聚合全部切片：省名只在首片出现也须命中（回归：逐片覆盖丢信号）。"""
    d = tmp_path / "samples_bank" / "stage_a" / "slices" / "ch1"
    d.mkdir(parents=True)
    (d / "rA__0.md").write_text("项目位于甘肃省庆阳市。" * 4, encoding="utf-8")
    (d / "rA__1.md").write_text("本节无省名。", encoding="utf-8")
    r = corpus_meta.build_corpus_meta(tmp_path / "samples_bank", {})["reports"]["rA"]
    assert r["province"] == "甘肃" and r["province_basis"] == "regex"


def test_corpus_meta_merge_and_determinism(tmp_path):
    """annotations 覆盖省/补 year_hint；schema 常量、键排序 → 双跑同字节。"""
    root = tmp_path / "samples_bank"
    _mk_slice(root, "stage_a", "r1", "项目在新疆。设计生产能力 500万t/a。依据 HJ 2.2-2018 编制。")
    ann = {"r1": {"province": "宁夏", "year_hint": 2024}}
    doc1 = corpus_meta.build_corpus_meta(root, ann)
    doc2 = corpus_meta.build_corpus_meta(root, ann)
    r = doc1["reports"]["r1"]
    assert r["province"] == "宁夏" and r["province_basis"] == "manual" and r["year_hint"] == 2024
    assert r["standards_cited"] == ["HJ2.2-2018"] and r["stage"] == "stage_a"
    b1 = json.dumps(doc1, sort_keys=True, ensure_ascii=False, indent=1)
    b2 = json.dumps(doc2, sort_keys=True, ensure_ascii=False, indent=1)
    assert hashlib.sha256(b1.encode()).hexdigest() == hashlib.sha256(b2.encode()).hexdigest()
