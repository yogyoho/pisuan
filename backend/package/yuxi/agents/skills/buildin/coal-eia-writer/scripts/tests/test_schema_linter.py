"""schema_linter 测试：L1-L5 五类检查 + CLI 报告（fixture stage 构造违规逐一命中）。"""

import json
import sys
from pathlib import Path

import pytest

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
    # 来源归属钉死（Task 2 补强）：detail 以「<来源>：」开头
    assert {(v["field"], v["detail"].split("：")[0]) for v in l2} == {("a", "label"), ("b", "note"), ("c", "type")}


# ---------- L3 数值型缺单位 ----------


def test_l3_numeric_missing_unit(tmp_path):
    """数值型字段 unit 键缺失/空且 note 无单位词表字样 → L3 命中；有 unit 键或 note 含单位 → 放行。"""
    forms = {
        "fam1": {
            "label": "族一",
            "fields": [
                {"name": "bare", "label": "面积", "type": "number"},
                {"name": "note_unit", "label": "长度", "type": "float", "note": "沿线单位 km 计"},
                {"name": "with_unit", "label": "处数", "type": "int", "unit": "处"},
                {"name": "empty_unit", "label": "库容", "type": "number", "unit": "", "note": "详见台账"},
                {"name": "text_field", "label": "描述", "type": "string"},
            ],
        }
    }
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l3 = [v for v in rep["violations"] if v["check"] == "L3"]
    assert {v["field"] for v in l3} == {"bare", "empty_unit"}


# ---------- L4 复合字段嵌套列名英文裸奔 ----------


def test_l4_composite_bare_english(tmp_path):
    """复合字段字符串列名清单：英文蛇名行内无中文注记 → L4 命中（行内 "en 中文" 与纯中文列名放行）。"""
    forms = {
        "geo": {
            "label": "地理族",
            "fields": [
                {"name": "coords", "label": "经纬度范围", "type": "object",
                 "fields": ["lon_min", "lon_max", "lat_min", "lat_max"]},
                {"name": "climate", "label": "气象要素", "type": "object",
                 "fields": ["气温", "降水"]},
                {"name": "mines", "label": "井田清单", "type": "array<object>",
                 "fields": ["name 井田名", "scale_before 原能力"]},
            ],
        }
    }
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l4 = [v for v in rep["violations"] if v["check"] == "L4"]
    assert len(l4) == 4
    assert {v["family"] for v in l4} == {"geo"}
    assert {v["field"] for v in l4} == {"coords"}
    assert {v["detail"].split("：")[1] for v in l4} == {"lon_min", "lon_max", "lat_min", "lat_max"}


def test_l4_family_labels_mapping_rescues(tmp_path):
    """列名清单旁挂 labels/列名_labels dict 映射给中文 → 对应列名放行。"""
    forms = {
        "fam1": {
            "label": "族一",
            "fields": [
                {"name": "mapped", "label": "映射列", "type": "object",
                 "fields": ["code_a", "code_b"], "labels": {"code_a": "甲列"}},
                {"name": "renamed", "label": "旁挂映射", "type": "object",
                 "fields": ["code_c", "code_d"], "renamed_labels": {"code_c": "丙列"}},
            ],
        }
    }
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l4 = [v for v in rep["violations"] if v["check"] == "L4"]
    assert {v["detail"].split("：")[1] for v in l4} == {"code_b", "code_d"}


# ---------- L5 枚举值卫生 ----------


def test_l5_enum_hygiene(tmp_path):
    """enum: 后半段按 [、,，/；;] 分段：含英文字母/重复/超 20 字 → 各记一条 L5；正常枚举放行。"""
    forms = {
        "proj": {
            "label": "项目族",
            "fields": [
                {"name": "e_letter", "label": "字母段", "type": "enum:甲/mt_units/丙"},
                {"name": "e_dup", "label": "重复段", "type": "enum:甲、乙、甲"},
                {"name": "e_long", "label": "超长段", "type": "enum:" + "甲" * 21},
                {"name": "e_ok", "label": "正常段", "type": "enum:新建/改扩建"},
            ],
        }
    }
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l5 = [v for v in rep["violations"] if v["check"] == "L5"]
    by_field: dict[str, list[str]] = {}
    for v in l5:
        by_field.setdefault(v["field"], []).append(v["detail"])
    assert set(by_field) == {"e_letter", "e_dup", "e_long"}
    assert len(by_field["e_letter"]) == 1 and "mt_units" in by_field["e_letter"][0]
    assert len(by_field["e_dup"]) == 1
    assert len(by_field["e_long"]) == 1


# ---------- CLI 全量扫描 ----------


def test_cli_report_and_exit(tmp_path, capsys):
    """CLI：违规 → exit 1 + JSON 摘要含各 stage 计数。"""
    from schema_linter import main_with_args
    refs = tmp_path / "references" / "stages"
    refs.mkdir(parents=True)
    (refs / "stage_a.json").write_text(json.dumps(
        {"stage": "a", "forms": {"f": {"label": "族", "fields": [{"name": "x", "type": "string"}]}}},
        ensure_ascii=False), encoding="utf-8")
    (refs / "stage_b.json").write_text(json.dumps(
        {"stage": "b", "forms": {"f": {"label": "族", "fields": [{"name": "y", "label": "乙", "type": "string"}]}}},
        ensure_ascii=False), encoding="utf-8")
    rc = main_with_args(["--references", str(tmp_path / "references")])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["stages"]["stage_a"]["L1"] >= 1
    assert out["stages"]["stage_b"]["L1"] == 0


def test_cli_clean_exit_zero(tmp_path, capsys):
    """无违规 → exit 0，total=0。"""
    from schema_linter import main_with_args
    refs = tmp_path / "references" / "stages"
    refs.mkdir(parents=True)
    (refs / "clean.json").write_text(json.dumps(
        {"stage": "clean", "forms": {"f": {"label": "族", "fields": [{"name": "a", "label": "甲", "type": "string"}]}}},
        ensure_ascii=False), encoding="utf-8")
    rc = main_with_args(["--references", str(tmp_path / "references")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 0


def test_lint_stage_missing_file_raises(tmp_path):
    """库层不吞读文件异常（Task 1 审查定下的分层）。"""
    with pytest.raises(FileNotFoundError):
        lint_stage(tmp_path / "no_such_stage.json")


def test_cli_empty_scan_guard(tmp_path, capsys):
    """空扫描守卫（Task 2 审查 I1）：references 路径无效 → exit 2——「没查」≠「干净」。"""
    from schema_linter import main_with_args

    rc = main_with_args(["--references", str(tmp_path / "nonexistent")])
    assert rc == 2
    assert capsys.readouterr().err
