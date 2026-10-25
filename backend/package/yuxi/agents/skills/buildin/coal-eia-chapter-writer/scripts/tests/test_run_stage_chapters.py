"""run-stage freeze --chapters 透传（bug-4143 方案A）：目标章集模式切片冻结，缺省全量零变化。

配套口径：门1 裁剪见 test_ingest_global_scope.py（derive_globals.scope_globals）；
切片冻结后派生常算块照常计算，后续章 3a 增量冻结按 setdefault 合并不重算。
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress

STAGE = {
    "chapters": {"ch2": {"sections": [{"id": "ch2_S01", "title": "总则"}]}},
    "forms": {},
}


def _freeze_state(tmp: Path) -> Path:
    stage = tmp / "stage.json"
    stage.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    sd = tmp / "state"
    rc = progress.cmd_init(Namespace(stage=str(stage), state_dir=str(sd),
                                     data_dir=str(tmp / "data"), mode="chapter"))
    assert rc == progress.EXIT_OK
    return sd


def _run_freeze(tmp: Path, chapters: str | None, monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(script, *args):
        calls.append([script, *args])
        return progress.EXIT_OK

    monkeypatch.setattr(progress, "_run_py", fake_run)
    rc = progress.cmd_run_stage(Namespace(stage_name="freeze", state_dir=str(tmp / "state"),
                                          chapters=chapters, outputs_dir=None, allow_partial=False))
    assert rc == progress.EXIT_OK
    return calls


def test_freeze_scoped_passes_chapters(tmp_path, monkeypatch):
    _freeze_state(tmp_path)
    calls = _run_freeze(tmp_path, "ch2", monkeypatch)
    fr = next(c for c in calls if c[0] == "formula_runner.py")
    assert "--chapters" in fr and "ch2" in fr


def test_freeze_default_full_unchanged(tmp_path, monkeypatch):
    """缺省（整本）不传 --chapters——全量冻结路径字节级不变。"""
    _freeze_state(tmp_path)
    calls = _run_freeze(tmp_path, None, monkeypatch)
    fr = next(c for c in calls if c[0] == "formula_runner.py")
    assert "--chapters" not in fr
