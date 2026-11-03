"""briefing 渲染器测试：outline/chapter/data-request/calc-summary 四子命令。

- 机械渲染零编造：产物含标准中文名/公式名/资料中文名；机制词行剔除（宁缺毋滥）
- 语体回归：产物零机制标记（延续 test_user_message.py banlist 口径）
- 全部用 tmp fixture（--stage/--standards-file/--formulas-file 显式传路径），不触真实 references
"""

import io
import json
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest  # noqa: F401  # 与 tests 包其他模块同径；暂无 parametrize，保留 import 对齐包惯例

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import briefing

STAGE_MINI = {
    "stage": "planning_eia",
    "chapters": {
        "ch1": {
            "title": "总则",
            "mode": "评价总纲与执行标准（XS1 总锚点）",
            "std_refs": ["HJ 130-2019", "HJ 464"],
            "forms": [],
            "formulas": [],
            "tables": [],
            "sections": [{"id": "ch1_S01", "title": "评价目的", "slots": [], "uses": {"formulas": [], "slots": []}}],
        },
        "ch2": {
            "title": "规划方案概况及分析",
            "mode": "数据填充 + 双口径；难度 3/中（XS1 全局指标主锚点章）",
            "key_elements": [
                "环境保护目标变化段：目标名与登记名一致（XS2）",
                "{{TABLE:mine_plan}} 直渲表格",
            ],
            "writing_patterns": [
                "双口径表述必须成对带标签，禁混写单值",
                "规模数值全槽位（{{SLOT:mine_plan.*}}），禁生成",
            ],
            "std_refs": ["HJ 130-2019"],
            "tables": ["矿区主要规划指标表（修编前后双口径列）"],
            "forms": ["geo"],
            "formulas": ["subsidence"],
            "sections": [
                {"id": "ch2_S01", "title": "地理位置", "slots": ["{{TABLE:geo}}", "{{SLOT:geo.location_text}}"],
                 "uses": {"formulas": [], "slots": ["{{TABLE:geo}}"]}},
                {"id": "ch2_S02", "title": "规划指标", "slots": ["{{SLOT:mine_plan.total}}"],
                 "uses": {"formulas": ["subsidence"], "slots": []}},
            ],
        },
    },
    "forms": {
        "geo": {
            "label": "区域自然环境概况", "required": True, "chapters": ["ch1", "ch2"],
            "fields": [
                {"name": "location_text", "label": "位置与行政区划", "type": "string", "required": True,
                 "note": "user_docs 录入，禁手算极值"},
                {"name": "rows", "label": "井田清单", "type": "array<object>", "required": True,
                 "fields": ["mine_name 井田名称", "capacity 设计能力(Mt/a)"]},
            ],
        },
        "mon": {"label": "环境质量监测", "required": False, "chapters": ["ch3"], "fields": []},
        "subsidence_params": {"label": "沉陷预测参数", "required": True, "chapters": ["ch6"], "fields": [
            {"name": "param_source", "label": "参数来源", "type": "string", "required": True,
             "note": "三值枚举（user_monitoring/analog_mine/user_provided）"},
        ]},
    },
}
STDS = {"standards": [
    {"code": "HJ 130-2019", "title": "规划环境影响评价技术导则 总纲", "role": "规划环评通用工作程序（结构主纲）"},
    {"code": "HJ 464-2009", "title": "规划环境影响评价技术导则 煤炭矿区总体规划", "role": "煤炭矿区专项要求"},
]}
FORMULAS = {"formulas": [
    {"id": "subsidence", "name": "概率积分法地表沉陷预测", "chapter": "ch2_S02", "expr": "W_max = q × m × cosα",
     "inputs": [{"name": "q", "desc": "下沉系数", "unit": "-", "source": "subsidence_params（param_source 必填）"}],
     "outputs": [{"name": "subsidence.W_max", "desc": "最大下沉值", "unit": "mm"}],
     "slots": ["{{SLOT:subsidence.W_max}}"], "note": "多工作面需叠加（XS4）"}],
    "derived_slots": []}
STATE = {"version": 2, "values": {
    "subsidence.W_max": {"value": 12.3, "display": "12.30", "unit": "mm", "source": "derived:subsidence"},
    "geo.location_text": {"value": "某县某镇", "display": "某县某镇", "unit": "", "source": "form:geo(静态转录)"}},
    "anomalies": ["13_subsidence_params 缺失/空白——subsidence 链未计算（缺参不编造）"]}


def _capture(fn, ns) -> tuple[int, str, str]:
    so, se = io.StringIO(), io.StringIO()
    with redirect_stdout(so), redirect_stderr(se):
        rc = fn(ns)
    return rc, so.getvalue(), se.getvalue()


def _fixtures(tmp: Path) -> dict[str, Path]:
    d = tmp / "fx"
    d.mkdir(parents=True, exist_ok=True)
    paths = {"stage": d / "stage.json", "std": d / "std.json", "fx": d / "fx.json",
             "state": d / "formula_state.json"}
    paths["stage"].write_text(json.dumps(STAGE_MINI, ensure_ascii=False), encoding="utf-8")
    paths["std"].write_text(json.dumps(STDS, ensure_ascii=False), encoding="utf-8")
    paths["fx"].write_text(json.dumps(FORMULAS, ensure_ascii=False), encoding="utf-8")
    paths["state"].write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    return paths


# 机制词标记：产物正文禁出现（语体回归，与 P3-10 banlist 同口径）
ARTIFACT_BAN = ["{{", "}}", "XS1", "XS2", "XS4", "exact_match", "ingest", "FORM_", "param_source",
                "user_docs", ".json", "rc="]


def _assert_clean(text: str) -> None:
    for w in ARTIFACT_BAN:
        assert w not in text, f"产物含机制标记「{w}」"


def test_outline_renders(tmp_path):
    fx = _fixtures(tmp_path)
    out = tmp_path / "outline.md"
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]), out=str(out))
    rc, so, _ = _capture(briefing.cmd_outline, ns)
    assert rc == briefing.EXIT_OK
    text = out.read_text(encoding="utf-8")
    for frag in ["全书编写策划书", "第1章「总则」", "第2章「规划方案概况及分析」", "《HJ 130-2019》规划环境影响评价技术导则 总纲",
                 "《HJ 464-2009》", "概率积分法地表沉陷预测", "区域自然环境概况"]:
        assert frag in text, f"策划书缺「{frag}」"
    _assert_clean(text)


def test_outline_unknown_stage_rc1(tmp_path):
    fx = _fixtures(tmp_path)
    ns = Namespace(stage=str(tmp_path / "nope.json"), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   out=str(tmp_path / "o.md"))
    rc, _, se = _capture(briefing.cmd_outline, ns)
    assert rc == briefing.EXIT_ERROR and "ERROR" in se


def test_chapter_renders(tmp_path):
    fx = _fixtures(tmp_path)
    out = tmp_path / "brief_ch2.md"
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   chapter="ch2", out=str(out))
    rc, so, _ = _capture(briefing.cmd_chapter, ns)
    assert rc == briefing.EXIT_OK and "BRIEF_CHAPTER_OK" in so
    text = out.read_text(encoding="utf-8")
    for frag in ["第2章「规划方案概况及分析」编写说明", "前承：第1章「总则」", "后启", "双口径表述必须成对带标签",
                 "依据的标准规范", "本章计算说明", "概率积分法地表沉陷预测", "输入：下沉系数",
                 "区域自然环境概况", "各节写法注记", "上承「地理位置」", "下启「本章小结」",
                 "涉及计算：概率积分法地表沉陷预测", "用到资料：区域自然环境概况"]:
        assert frag in text, f"章说明缺「{frag}」"
    assert "{{TABLE:mine_plan}} 直渲表格" not in text  # 机制词行整行弃
    assert "规模数值全槽位" not in text  # 原行含模板记号（{{…}} 记号即内容）→ 整行弃
    _assert_clean(text)


def test_chapter_unknown_rc1(tmp_path):
    fx = _fixtures(tmp_path)
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   chapter="ch9", out=str(tmp_path / "b.md"))
    rc, _, se = _capture(briefing.cmd_chapter, ns)
    assert rc == briefing.EXIT_ERROR and "ERROR" in se


def test_data_request_renders(tmp_path):
    fx = _fixtures(tmp_path)
    outdir = tmp_path / "requests"
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   families="geo,mon,subsidence_params", out_dir=str(outdir))
    rc, so, _ = _capture(briefing.cmd_data_request, ns)
    assert rc == briefing.EXIT_OK and "BRIEF_REQUEST_OK" in so
    md = (outdir / "资料需求单.md").read_text(encoding="utf-8")
    for frag in ["资料需求单", "区域自然环境概况（必需）", "环境质量监测（可选）", "沉陷预测参数（必需）",
                 "供「概率积分法地表沉陷预测」等计算使用", "报告编写直接引用；第1章、第2章要用",
                 "位置与行政区划（必填）", "井田清单：表格", "参数来源（必填）"]:
        assert frag in md, f"需求单缺「{frag}」"
    assert "user_docs" not in md  # 机制 note 剔除
    assert "user_monitoring" not in md  # 通道/枚举名不泄漏
    _assert_clean(md)
    csvs = sorted(outdir.glob("*.csv"))
    assert len(csvs) == 1
    raw = csvs[0].read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "井田名称,设计能力(Mt/a)"
    assert lines[1] == "【请填写】,【请填写】"
    assert len(lines) == 2  # 无注释行（ingest 唯一写者防误解析）


def test_calc_summary_all_and_chapter(tmp_path):
    fx = _fixtures(tmp_path)
    out = tmp_path / "calc_all.md"
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   state_dir=str(fx["state"].parent), chapter="", out=str(out))
    rc, so, _ = _capture(briefing.cmd_calc_summary, ns)
    assert rc == briefing.EXIT_OK and "BRIEF_CALC_OK" in so
    text = out.read_text(encoding="utf-8")
    for frag in ["计算说明", "最大下沉值：12.30 mm——系统按公式计算", "来自区域自然环境概况资料",
                 "未完成计算（缺资料，未编造）", "沉陷预测参数"]:
        assert frag in text, f"计算说明缺「{frag}」"
    _assert_clean(text)

    out2 = tmp_path / "calc_ch2.md"
    ns2 = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                    state_dir=str(fx["state"].parent), chapter="ch2", out=str(out2))
    rc2, _, _ = _capture(briefing.cmd_calc_summary, ns2)
    assert rc2 == briefing.EXIT_OK
    t2 = out2.read_text(encoding="utf-8")
    assert "最大下沉值" in t2 and "来自区域自然环境概况资料" not in t2  # 章口径只含本章消费公式槽位


def test_calc_summary_missing_state_rc1(tmp_path):
    fx = _fixtures(tmp_path)
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   state_dir=str(tmp_path / "nostate"), chapter="", out=str(tmp_path / "c.md"))
    rc, _, se = _capture(briefing.cmd_calc_summary, ns)
    assert rc == briefing.EXIT_ERROR and "ERROR" in se


def test_data_request_unknown_family_rc1(tmp_path):
    fx = _fixtures(tmp_path)
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   families="nope", out_dir=str(tmp_path / "r"))
    rc, _, se = _capture(briefing.cmd_data_request, ns)
    assert rc == briefing.EXIT_ERROR and "ERROR" in se
