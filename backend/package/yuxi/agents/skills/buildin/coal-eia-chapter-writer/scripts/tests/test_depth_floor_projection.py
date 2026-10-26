"""深度基线投影折算与真源统一测试（bug-4148/4149）：

- resolve_targets 按 stage 文档 stage_id 命中注册表（文件名改名不脱钩，bug-4149）；stem 兜底兼容
- chapter_floor_scaled：floor × 投影节数/样例章节数（标题级中位）向上取整；投影≥样例直通；无 bank 直通
- validate_chapter_depth 传 stage 时 FAIL 消息带折算说明；不传 stage 保持未折算语义（既有调用零变化）
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_output

STAGE_CH2 = {
    "stage_id": "planning_eia",
    "chapters": {"ch2": {"sections": [{"id": f"ch2_S0{i}"} for i in range(1, 3)]}},  # 投影 2 节（< 样例中位 3 → 折算）
}

BANK = {
    "planning_eia": {
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
    """隔离 bank 缓存（模块级懒缓存按用例如换，防真实库串味）。"""
    saved = dict(build_output._BANK_CACHE)
    build_output._BANK_CACHE.clear()
    yield
    build_output._BANK_CACHE.clear()
    build_output._BANK_CACHE.update(saved)


def test_resolve_targets_by_stage_id(tmp_path):
    """stage 文件名 ≠ stage_id 仍命中注册表（/tmp 拷贝改名不再脱钩，bug-4149）。"""
    stage_file = tmp_path / "renamed_stage.json"
    stage_file.write_text(json.dumps({"stage_id": "planning_eia"}, ensure_ascii=False), encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage_file)
    assert targets is not None
    assert src.name == "planning_eia.json"
    assert targets["chapters"]["ch2"]["floor_chars"] == 14599  # 真注册表


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
    stage = {"stage_id": "planning_eia", "chapters": {"ch2": {"sections": [{"id": f"ch2_S0{i}"} for i in range(1, 5)]}}}
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
