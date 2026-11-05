"""progress.py next 指引路径口径回归（bug-4213）：COLLECTING 两分支（无 choice/已选）指引的
候选与切包路径必须与 SKILL.md 契约口径一致（candidates_<ch>.json / fragment_packs/<ch>），
禁回退旧下划线口径——fragment_packs_<ch> 曾使节级切包 P1-5 在实栈从未落地（3b 恒退章包）。
stdlib-only，不依赖容器。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import progress  # noqa: E402


def _mk_doc() -> dict:
    return {
        "mode": "chapter",
        "stage_path": "stages/planning_eia.json",
        "data_dir": "data",
        "chapters": {
            "ch2": {
                "title": "矿井开拓开采",
                "status": "PENDING",
                "sections": [{"id": "ch2_S01", "title": "开拓", "status": "PENDING"}],
            }
        },
    }


def test_collecting_choice_missing_guidance_paths(tmp_path):
    """无 choice 态：指引候选/切包路径=SKILL 契约口径，并带 --content-dir（候选全文数据面）。"""
    (tmp_path / "plan_ch2.json").write_text("{}", encoding="utf-8")
    out = progress.next_action_chapter(_mk_doc(), tmp_path)
    assert "state/candidates_ch2.json" in out
    assert "state/candidates_content_ch2" in out
    assert "state/fragment_packs/ch2" in out
    assert "state/sample_fragments_ch2.md" in out
    assert "sample_candidates_" not in out
    assert "fragment_packs_" not in out  # 旧下划线口径禁回流（bug-4213）


def test_collecting_choice_present_guidance_paths(tmp_path):
    """已选态：节包注入路径=state/fragment_packs/ch2（斜杠子目录）。"""
    (tmp_path / "plan_ch2.json").write_text("{}", encoding="utf-8")
    (tmp_path / "fragment_choice_ch2.json").write_text(
        json.dumps({"chapter": "ch2", "report_id": "004-2-2021-1"}), encoding="utf-8"
    )
    out = progress.next_action_chapter(_mk_doc(), tmp_path)
    assert "state/fragment_packs/ch2" in out
    assert "fragment_packs_" not in out
