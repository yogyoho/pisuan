"""init stage 可用性预检测试（评审 P1-4）：内置 stage「可选 5 个、能跑 1 个」的落差在开题第一秒闭合。

契约：
- 仅内置 stage（路径落在技能包 references/stages/ 下）做预检——roles/style_targets 缺失即拒 init
- 自造 stage（测试/变体，路径在包外）不预检，由调用方自责
- planning_eia 为当前唯一启用 stage（roles + style_targets 双资产在位）
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _paths import refs_root  # 同目录上一级：references 根解析（P2-8 单源化回落）

import progress

REFS = refs_root()
STAGE = {
    "chapters": {
        "ch2": {"sections": [{"id": "ch2_S01", "title": "总则"}]},
    }
}


def test_enabled_builtin_stage_has_no_missing_assets():
    assert progress.builtin_stage_missing_assets(str(REFS / "stages" / "planning_eia.json")) == []


def test_disabled_builtin_stage_reports_missing_assets():
    missing = progress.builtin_stage_missing_assets(str(REFS / "stages" / "project_eia_underground.json"))
    names = [m.name for m in missing]
    assert names == ["project_eia_underground.json", "project_eia_underground.json"]
    assert any("paradigms" in str(m) for m in missing) and any("style_targets" in str(m) for m in missing)


def test_custom_stage_outside_package_skips_precheck(tmp_path):
    custom = tmp_path / "my_stage.json"
    custom.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    assert progress.builtin_stage_missing_assets(str(custom)) == []


def test_init_rejects_disabled_builtin_stage(capsys):
    rc = progress.cmd_init(
        Namespace(stage=str(REFS / "stages" / "post_eia.json"), state_dir=str(tmp_state := Path("/nonexistent-precheck-tmp") / "s"),
                  data_dir=None, mode="chapter")
    )
    assert rc == progress.EXIT_ERROR
    err = capsys.readouterr().err
    assert "尚未启用" in err and "目前可跑: planning_eia" in err
    assert not (Path("/nonexistent-precheck-tmp") / "s" / "progress.json").exists()  # 拒绝时不落账
