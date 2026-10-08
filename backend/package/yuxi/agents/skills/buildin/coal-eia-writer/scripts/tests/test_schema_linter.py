"""schema_linter 测试：L1-L5 五类检查 + CLI 报告（fixture stage 构造违规逐一命中）。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema_linter import lint_stage


def _mk_stage(tmp_path: Path, forms: dict) -> Path:
    p = tmp_path / "stage_x.json"
    p.write_text(json.dumps({"stage": "x", "forms": forms}, ensure_ascii=False), encoding="utf-8")
    return p


def test_l1_missing_label(tmp_path):
    """标量字段缺中文 label → L1 命中。"""
    forms = {
        "fam1": {
            "label": "族一",
            "fields": [
                {"name": "no_label", "type": "string", "required": True},
                {"name": "empty_label", "label": "  ", "type": "string"},
                {"name": "ok", "label": "正常字段", "type": "string"},
            ],
        }
    }
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l1 = [v for v in rep["violations"] if v["check"] == "L1"]
    assert len(l1) == 2
    assert {v["field"] for v in l1} == {"no_label", "empty_label"}


def test_l2_pipe_char(tmp_path):
    """label/note 含竖线 → L2 命中（bug-393 裂表根因）。"""
    forms = {
        "fam1": {
            "label": "族一",
            "fields": [
                {"name": "a", "label": "良好|含竖线", "type": "string"},
                {"name": "b", "label": "正常", "type": "string", "note": "备注|也禁"},
                {"name": "c", "label": "枚举族", "type": "enum:甲|乙|丙"},
            ],
        }
    }
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l2 = [v for v in rep["violations"] if v["check"] == "L2"]
    assert len(l2) == 3
