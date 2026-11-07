"""账面路径守卫测试（bug-4172）：init/gate/run-stage 对 stage_path/data_dir 的存在性快速失败。

背景（ch2 审查发现）：hxmc-planning-rev2-chapter 的 progress.json data_dir 指向不存在的
eia-report/ 前缀路径——run_chapter_gate 仅签名兼容不读 data_dir，门检查未受影响，但任何
未来真读 data_dir 的命令（render_front_matter/render_family 等对缺失文件静默回退 {}）会
无声降级。守卫语义：
- init：--data-dir 给了就必须真实在盘（is_dir），否则拒绝建账；
- gate / run-stage：账面 stage_path/data_dir 必须在盘（exists），否则拒跑并提示停 run 修账
  （progress.json 单写者，账面路径漂移=工作区被移动或 init 记错，宁可响错不可哑跑）。
"""

import io
import json
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress

STAGE = {"chapters": {"ch2": {"sections": [{"id": "ch2_S01", "title": "总则"}]}}}


def _capture(fn, *args) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = fn(*args)
    return rc, out.getvalue(), err.getvalue()


def _write_stage(tmp: Path) -> Path:
    stage = tmp / "stage.json"
    stage.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    return stage


def _init_ok(tmp: Path) -> Path:
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    stage = _write_stage(tmp)
    rc = progress.cmd_init(
        Namespace(stage=str(stage), state_dir=str(tmp / "state"), data_dir=str(tmp / "data"), mode="chapter")
    )
    assert rc == progress.EXIT_OK
    return tmp / "state"


def _stale_data_dir(sd: Path) -> None:
    """账面漂移模拟：工作区 data 目录被移动后 progress.json 未修账。"""
    p = sd / "progress.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["data_dir"] = str(sd.parent / "moved-away-data")
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def test_init_rejects_missing_data_dir(tmp_path):
    stage = _write_stage(tmp_path)
    rc, _, err = _capture(
        progress.cmd_init,
        Namespace(
            stage=str(stage), state_dir=str(tmp_path / "state"), data_dir=str(tmp_path / "no-such-data"), mode="chapter"
        ),
    )
    assert rc == progress.EXIT_ERROR
    assert "不存在" in err
    assert not (tmp_path / "state" / "progress.json").exists()


def test_init_accepts_existing_data_dir(tmp_path):
    stage = _write_stage(tmp_path)
    (tmp_path / "data").mkdir()
    rc, _, _ = _capture(
        progress.cmd_init,
        Namespace(stage=str(stage), state_dir=str(tmp_path / "state"), data_dir=str(tmp_path / "data"), mode="chapter"),
    )
    assert rc == progress.EXIT_OK
    doc = json.loads((tmp_path / "state" / "progress.json").read_text(encoding="utf-8"))
    assert Path(doc["data_dir"]).is_dir()


def test_gate_rejects_stale_data_dir(tmp_path):
    sd = _init_ok(tmp_path)
    _stale_data_dir(sd)
    rc, _, err = _capture(progress.cmd_gate, Namespace(state_dir=str(sd), chapters="ch2", targets=None))
    assert rc == progress.EXIT_ERROR
    assert "账面路径不在盘" in err
    assert "data_dir" in err


def test_run_stage_rejects_stale_data_dir(tmp_path):
    sd = _init_ok(tmp_path)
    _stale_data_dir(sd)
    rc, _, err = _capture(
        progress.cmd_run_stage,
        Namespace(state_dir=str(sd), stage_name="freeze", outputs_dir=None),
    )
    assert rc == progress.EXIT_ERROR
    assert "账面路径不在盘" in err
