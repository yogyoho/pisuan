"""深度基线投影折算与真源统一测试（bug-4148/4149 + 评审 P0-1）：

- resolve_targets 按 stage 文档 stage_id 命中注册表（文件名改名不脱钩，bug-4149）；stem 兜底兼容
- chapter_floor_scaled：floor × 投影节数/样例章节数（标题级中位）向上取整；投影≥样例直通；无 bank 直通；
  折算不可穿透标定下限 median_eff×absolute_floor（评审 P0-1：标定契约接线，ch2 曾被折到注册值 1/18）
- validate_chapter_depth 传 stage 时 FAIL 消息带折算说明；不传 stage 保持未折算语义（既有调用零变化）
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _paths import refs_root  # 同目录上一级：references 根解析（P2-8 单源化回落）

import build_output

STAGE_CH2 = {
    "stage_id": "calib_stage",  # 合成 stage id：不与真注册表（planning_eia）撞标定记录
    "chapters": {"ch2": {"sections": [{"id": f"ch2_S0{i}"} for i in range(1, 3)]}},  # 投影 2 节（< 样例中位 3 → 折算）
}

BANK = {
    "calib_stage": {
        "ch2": [
            {"report_id": "A", "sec": s}
            for s in ("2", "2.1", "2.1.1", "2.2")  # 报告 A：4 个标题级节
        ]
        + [
            {"report_id": "B", "sec": s}
            for s in ("2", "2.1")  # 报告 B：2 个 → 计数 [2,4] → 中位 3
        ]
    }
}


@pytest.fixture()
def bank_cache():
    """隔离 bank/标定两级懒缓存（模块级按用例切换，防真实库串味）。"""
    saved_bank, saved_calib = dict(build_output._BANK_CACHE), dict(build_output._CALIB_CACHE)
    build_output._BANK_CACHE.clear()
    build_output._CALIB_CACHE.clear()
    yield
    build_output._BANK_CACHE.clear()
    build_output._BANK_CACHE.update(saved_bank)
    build_output._CALIB_CACHE.clear()
    build_output._CALIB_CACHE.update(saved_calib)


def test_resolve_targets_by_stage_id(tmp_path):
    """stage 文件名 ≠ stage_id 仍命中注册表（/tmp 拷贝改名不再脱钩，bug-4149）。

    期望值从活动 DEPTH_DIR 注册表派生而非硬编码——depth_targets 是 bank_compile
    派生产物（运行时随语料重标定），repo/运行栈两树快照会漂移，硬编码必脆断。"""
    stage_file = tmp_path / "renamed_stage.json"
    stage_file.write_text(json.dumps({"stage_id": "planning_eia"}, ensure_ascii=False), encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage_file)
    registry = json.loads((build_output.DEPTH_DIR / "planning_eia.json").read_text(encoding="utf-8"))
    assert targets is not None
    assert src.name == "planning_eia.json"
    assert targets == registry  # 命中的就是注册表本体（stage_id 路由，非文件名）


def test_resolve_targets_stem_fallback(tmp_path):
    """stage 无 stage_id 字段 → 文件名 stem 兜底（旧 stage 文档兼容）。"""
    stage_file = tmp_path / "planning_eia.json"
    stage_file.write_text("{}", encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage_file)
    assert targets is not None and src.name == "planning_eia.json"


def test_floor_scaled_by_projection(bank_cache, monkeypatch):
    monkeypatch.setitem(build_output._BANK_CACHE, "bank", BANK)
    targets = {"chapters": {"ch2": {"floor_chars": 1000}}}
    floor, base, note = build_output.chapter_floor_scaled(STAGE_CH2, "ch2", targets)
    assert base == 1000
    assert floor == 667  # ceil(1000×2/3)
    assert "折算" in note and "投影2" in note


def test_floor_direct_when_projection_covers_sample(bank_cache, monkeypatch):
    monkeypatch.setitem(build_output._BANK_CACHE, "bank", BANK)
    stage = {"stage_id": "calib_stage", "chapters": {"ch2": {"sections": [{"id": f"ch2_S0{i}"} for i in range(1, 5)]}}}
    # 样例中位 3 < 投影 4 → 直通
    floor, base, note = build_output.chapter_floor_scaled(stage, "ch2", {"chapters": {"ch2": {"floor_chars": 1000}}})
    assert floor == base == 1000 and note == ""


def test_floor_direct_without_bank(bank_cache, monkeypatch):
    monkeypatch.setitem(build_output._BANK_CACHE, "bank", {})  # bank 无数据（缺失/损坏同路径）→ 直通
    floor, base, note = build_output.chapter_floor_scaled(
        STAGE_CH2, "ch2", {"chapters": {"ch2": {"floor_chars": 1000}}}
    )
    assert floor == base == 1000 and note == ""


def test_depth_gate_message_carries_scaling_note(bank_cache, monkeypatch):
    monkeypatch.setitem(build_output._BANK_CACHE, "bank", BANK)
    targets = {"chapters": {"ch2": {"floor_chars": 1000}}}
    with pytest.raises(ValueError) as ei:
        build_output.validate_chapter_depth("ch2", "太短。", targets, stage=STAGE_CH2)
    assert "667" in str(ei.value) and "折算" in str(ei.value)


def test_depth_gate_unscaled_without_stage(bank_cache):
    """不传 stage = 未折算语义（既有调用/测试零变化）。"""
    targets = {"chapters": {"ch6": {"floor_chars": 100}}}
    with pytest.raises(ValueError) as ei:
        build_output.validate_chapter_depth("ch6", "太短。", targets)
    assert "折算" not in str(ei.value) and "100" in str(ei.value)


def _seed_calibration(monkeypatch, tmp_path, median_eff: int, absolute_floor: float = 0.4) -> None:
    """合成 stage 的标定记录落盘 + DEPTH_DIR 指向 tmp（不触真注册表）。"""
    monkeypatch.setitem(build_output._BANK_CACHE, "bank", BANK)
    monkeypatch.setattr(build_output, "DEPTH_DIR", tmp_path)
    calib = tmp_path / "calib_stage" / "coal.json"
    calib.parent.mkdir()
    calib.write_text(
        json.dumps({"absolute_floor": absolute_floor, "per_chapter": {"ch2": {"median_eff": median_eff}}}),
        encoding="utf-8",
    )


def test_floor_bounded_by_calibration(bank_cache, monkeypatch, tmp_path):
    """折算低于标定下限（median_eff×absolute_floor）时托底——评审 P0-1：折算不可穿透标定契约。"""
    _seed_calibration(monkeypatch, tmp_path, median_eff=5000)
    targets = {"chapters": {"ch2": {"floor_chars": 1000}}}
    floor, base, note = build_output.chapter_floor_scaled(STAGE_CH2, "ch2", targets)
    assert base == 1000
    assert floor == 2000  # int(5000×0.4)=2000 > ceil(1000×2/3)=667 → 托底
    assert "标定下限 2000" in note


def test_fold_kept_when_above_calibration_bound(bank_cache, monkeypatch, tmp_path):
    """折算值 ≥ 标定下限 → 折算值直出（下限只托底、不抬杠）。"""
    _seed_calibration(monkeypatch, tmp_path, median_eff=1000)
    targets = {"chapters": {"ch2": {"floor_chars": 1000}}}
    floor, base, note = build_output.chapter_floor_scaled(STAGE_CH2, "ch2", targets)
    assert floor == 667 and "标定下限" not in note


def test_depth_gate_message_carries_bound_note(bank_cache, monkeypatch, tmp_path):
    _seed_calibration(monkeypatch, tmp_path, median_eff=5000)
    targets = {"chapters": {"ch2": {"floor_chars": 1000}}}
    with pytest.raises(ValueError) as ei:
        build_output.validate_chapter_depth("ch2", "太短。", targets, stage=STAGE_CH2)
    assert "标定下限 2000" in str(ei.value)


def test_real_registry_floor_honors_calibration(bank_cache):
    """真注册表全章回归（评审 P0-1 标定合理性）：折算章地板不得穿透 median_eff×absolute_floor
    ——bank_compile 落盘的标定契约（absolute_floor）必须被门兑现；直通章保持注册地板语义。"""
    refs = refs_root()
    checked_folded = checked_all = 0
    for stage_path in sorted((refs / "stages").glob("*.json")):
        stage = json.loads(stage_path.read_text(encoding="utf-8"))
        sid = str(stage.get("stage_id") or stage_path.stem)
        targets = json.loads((refs / "depth_targets" / f"{sid}.json").read_text(encoding="utf-8"))
        calib_path = refs / "depth_targets" / sid / "coal.json"
        calib = json.loads(calib_path.read_text(encoding="utf-8")) if calib_path.exists() else {}
        af = calib.get("absolute_floor")
        for ch_id, ch in (stage.get("chapters") or {}).items():
            if not [s for s in (ch or {}).get("sections", []) if s.get("id")]:
                continue
            checked_all += 1
            floor, base, note = build_output.chapter_floor_scaled(stage, ch_id, targets)
            assert floor >= base // 2, f"{sid}/{ch_id} 折算地板 {floor} 穿透注册半值 {base // 2}"
            if "折算" not in note:  # 直通章（投影≥样例/无 bank）：注册地板语义，不在折算契约射程内
                continue
            median_eff = ((calib.get("per_chapter") or {}).get(ch_id) or {}).get("median_eff")
            if af is not None and median_eff:
                bound = int(median_eff * float(af))
                assert floor >= bound, f"{sid}/{ch_id} 折算地板 {floor} < 标定下限 {bound}（median {median_eff}×{af}）"
                checked_folded += 1
    assert checked_all >= 60  # 五 stage 真资产在册（80 折算章 + 直通章）
    assert checked_folded >= 60
