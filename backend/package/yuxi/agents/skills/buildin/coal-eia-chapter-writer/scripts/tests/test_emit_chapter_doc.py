"""章级成稿文档（--emit-doc）测试：门 PASS 凭据写盘 / FAIL 不写盘 / 文件名安全化 / 幂等。

背景（docs/vibe/2026-11-05-chapter-doc-delivery.md）：章确认后产注入版章文档
`<工作区>/章稿/第N章-{章名}.md`——以真跑章门 PASS 为唯一凭据；章稿目录唯一写者
= run_chapter_gate emit_doc 路径。门本身由 test_gates_systematic 覆盖，此处
monkeypatch build_chapter 聚焦 emit-doc 契约。stdlib-only，不依赖容器。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_output  # noqa: E402


# ── 文件名派生 ───────────────────────────────────────────────────────────────


def test_doc_path_filename_safe(tmp_path):
    """hostile 字符剔除保留中文；章号取数字段；缺 title 退化 ch_id。"""
    stage = {"chapters": {"ch3": {"title": '区域<概况>:"调查|?'}}}
    sd = tmp_path / "state"
    p = build_output._chapter_doc_path(stage, sd, "ch3")
    assert p == sd.parent / "章稿" / "第3章-区域概况调查.md"
    stage2 = {"chapters": {"ch12": {}}}
    p2 = build_output._chapter_doc_path(stage2, sd, "ch12")
    assert p2.name == "第12章-ch12.md"


# ── emit-doc 契约 ────────────────────────────────────────────────────────────


def _mk_env(tmp_path: Path, monkeypatch, *, raw: str | None = None, errors: list[str] | None = None):
    """最小门环境：formula_state 空库 + build_chapter stub（门逻辑由 test_gates_systematic 覆盖）。"""
    stage = {"chapters": {"ch3": {"title": "区域自然和社会经济概况", "sections": [{"id": "ch3_S01", "title": "概况"}]}}}
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "formula_state.json").write_text(json.dumps({"values": {}}), encoding="utf-8")
    injected = (
        "## 3 区域自然和社会经济概况\n### 3.1 概况\n\n"
        + "矿区开发历史悠久本段为有效正文字符填充。\n" * 100
        + "\n**表 3-1 概况**\n\n| 指标 | 数值 |\n|---|---|\n| 面积 | 314.1 |\n"
    )
    raw = raw if raw is not None else "## 3 区域自然和社会经济概况\n### 3.1 概况\n正文。\n"

    def fake_build_chapter(stage_arg, data_dir, state_dir_arg, ch_id, inject, absent_sections):
        return raw, injected, [{"id": "ch3_S01", "eff": 1200}], list(errors or [])

    monkeypatch.setattr(build_output, "build_chapter", fake_build_chapter)
    targets = {"chapters": {"ch3": {"floor_chars": 1000}}}
    return stage, state_dir, injected, targets


def test_emit_doc_pass_writes_injected(tmp_path, monkeypatch, capsys):
    """PASS → 章稿/第N章-{章名}.md 写盘，内容=注入稿（SL1 残留=0、FIG 合法保留）。"""
    stage, sd, injected, targets = _mk_env(tmp_path, monkeypatch)
    build_output.run_chapter_gate(stage, tmp_path / "data", sd, "ch3", targets, emit_doc=True)
    doc = sd.parent / "章稿" / "第3章-区域自然和社会经济概况.md"
    assert doc.exists()
    assert doc.read_text(encoding="utf-8") == injected
    out = capsys.readouterr().out
    assert "CHAPTER_GATE_PASS" in out and f"EMIT_DOC_OK: {doc}" in out
    assert "{{SLOT:" not in injected and "{{TABLE:" not in injected


def test_emit_doc_idempotent_no_rewrite(tmp_path, monkeypatch, capsys):
    """内容不变二次运行不重写（保 mtime，SC-4 同构）并明示未变化。"""
    stage, sd, _inj, targets = _mk_env(tmp_path, monkeypatch)
    build_output.run_chapter_gate(stage, tmp_path / "data", sd, "ch3", targets, emit_doc=True)
    doc = sd.parent / "章稿" / "第3章-区域自然和社会经济概况.md"
    mtime = doc.stat().st_mtime_ns
    build_output.run_chapter_gate(stage, tmp_path / "data", sd, "ch3", targets, emit_doc=True)
    assert doc.stat().st_mtime_ns == mtime
    assert "内容未变化" in capsys.readouterr().out


def test_emit_doc_fail_no_write(tmp_path, monkeypatch):
    """门 FAIL → ValueError 且章文档不落盘（无过门稿不产出）。"""
    stage, sd, _inj, targets = _mk_env(tmp_path, monkeypatch, raw="正文直接开写没有章题。\n")
    with pytest.raises(ValueError, match="单章门 FAIL"):
        build_output.run_chapter_gate(stage, tmp_path / "data", sd, "ch3", targets, emit_doc=True)
    assert not (sd.parent / "章稿").exists()


def test_emit_doc_requires_chapter(tmp_path, monkeypatch):
    """--emit-doc 脱离 --chapter → EXIT_ERROR（成稿文档以章门 PASS 为唯一凭据）。"""
    stage_p = tmp_path / "stage.json"
    stage_p.write_text("{}", encoding="utf-8")
    argv = [
        "build_output.py",
        "--stage",
        str(stage_p),
        "--data-dir",
        str(tmp_path / "data"),
        "--state-dir",
        str(tmp_path / "state"),
        "--emit-doc",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert build_output.main() == build_output.EXIT_ERROR
