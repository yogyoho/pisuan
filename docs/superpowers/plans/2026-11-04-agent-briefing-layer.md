# Agent 业务简报渲染层（briefing 层）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `briefing.py` 确定性渲染器，把 stage/standards_index/formulas/formula_state 结构化资产渲染成用户侧业务简报（策划书/章说明/资料需求单+CSV 模板/计算说明/节注记），双包 SKILL.md 接线五处，零新增停车点。

**Architecture:** 纯标准库单脚本（writer 真源，sync 到 chapter-writer，字节守卫自动覆盖）；机械模板拼接零 LLM；机制词行/括注剔除（宁缺毋滥）；四子命令各自渲染一份 Markdown 工件落盘。设计文档：`docs/vibe/2026-11-04-agent-briefing-layer.md`。

**Tech Stack:** Python 3.12 标准库（json/re/csv/argparse），pytest（容器 + 宿主临时目录 harness），uvx ruff 0.16.4。

**分支约定：** 直接在 `pisuan-custom` 工作树实施（项目惯例，不开 worktree）；docs/vibe 设计文档 gitignore 本地留存不入库；本计划文档 tracked 随首个提交入库。

**素材结构事实（勘察已核实，写代码勿再猜）：**
- stage JSON：`chapters`（dict，插入序=章序）每章 `{title, mode, key_elements[], writing_patterns[], std_refs[], tables[], forms[](族键), formulas[](公式id), sections[{id,title,slots[],uses{slots[],formulas[],contracts[]}}]}`；顶层 `forms` 每族 `{label, file, required, chapters[], fields[]}`；字段 `{name, label, type, required, note?}`，数组字段 `type:"array<object>"`、其 `fields` 是**字符串列表**（形如 `"element 要素(大气/地表水/…)"`——首空格后是中文说明）
- `standards_index.json`：`{standards: [{code, title, role, chapters, tier, ...}]}`（62 条；章内 std_refs 可能省年份如 `HJ 464`，需前缀回退）
- `formulas.json`：`{formulas: [{id, name, chapter, expr, inputs[{name,desc,unit,source}], outputs[{name,desc,unit}], precision, slots[], note, regression}], derived_slots: [{slot, expr, source, chapter, note}]}`；章 `formulas` 键存的是公式 **id**（如 `["subsidence","capacity:water"]`）
- `formula_state.json`：`{version, values: {"族.槽位": {value, display, unit, source}}, anomalies: [str]}`；source 形如 `form:standards_confirm(静态转录)` / `derived:subsidence`
- `_paths.py`：`refs_root()`（先自身包 references，缺则回落 writer 兄弟包）

---

### Task 1: briefing.py 骨架 + 共用工具 + outline 子命令（TDD）

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py`
- Test: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py`

- [ ] **Step 1: 写失败测试（骨架 + outline 断言）**

创建 `scripts/tests/test_briefing.py`：

```python
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

import pytest

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
    paths = {"stage": d / "stage.json", "std": d / "std.json", "fx": d / "fx.json", "state": d / "fs.json"}
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
```

- [ ] **Step 2: 跑测试确认失败**

宿主临时目录 harness（绕 repo 祖先链 conftest——cerebrum DNR：宿主 pytest 直跑技能 tests 会沿祖先链 import yuxi 炸收集）：

```bash
cd /c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin
H=$(mktemp -d); mkdir -p "$H/pkg"
cmd //c "mklink /J $(cygpath -w "$H/pkg/coal-eia-writer") $(cygpath -w "$PWD/coal-eia-writer")"
cd "$H" && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -m pytest pkg/coal-eia-writer/scripts/tests/test_briefing.py -q
```

Expected: FAIL / ERROR（`ModuleNotFoundError: briefing` 或 AttributeError）。

- [ ] **Step 3: 写 briefing.py 骨架 + outline 最小实现**

创建 `scripts/briefing.py`（骨架含全部共用工具，后续任务只加渲染/命令函数）：

```python
#!/usr/bin/env python3
"""Agent 业务内容简报渲染器（交互体验重塑 2026-11-04，docs/vibe/2026-11-04-agent-briefing-layer.md）。

把 references/ 结构化资产（stage 章结构/forms、standards_index、formulas、formula_state 冻结值）
机械渲染成业务语体的用户侧简报工件——零 LLM 参与、零编造；机制词行/括注剔除（宁缺毋滥）。

子命令：
    outline      --stage S --out F                          全书编写策划书
    chapter      --stage S --chapter chN --out F            第N章编写说明（含每节注记）
    data-request --stage S [--families F1,F2] --out-dir D   资料需求单 + 表格族 CSV 模板
    calc-summary --stage S --state-dir T [--chapter chN] --out F   计算说明（冻结值+来源）

--stage 一律填 stage JSON 路径或裸 id（自动经 refs_root() 归一）；--standards-file/--formulas-file
缺省取 references/standards_index.json、references/formulas.json（同归一口径）。
rc：0=工件落盘（stdout 末行 BRIEF_*_OK）；1=参数/文件错误（未知 stage/章/族、缺 state）。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import refs_root  # noqa: E402  # 同目录：references 根解析（P2-8 单源化回落）

EXIT_OK, EXIT_ERROR = 0, 1

# 机制词标记：剔机制括注后正文仍命中 → 整行弃（宁缺毋滥，细节由卡A/对话承载）
_MECH_RE = re.compile(
    r"\{\{|\}\}|SLOT|TABLE|exact_match|ingest|FORM_|rc=|\bXS\d+|\bEO\d+|门\s?\d|\.json|param_source|--[a-z]"
)
_PAREN_RE = re.compile(r"（[^（）]*）|\([^()]*\)")


def _strip_mech_parens(text: str) -> str:
    """剔除含机制词的括注，干净括注保留。"""
    return _PAREN_RE.sub(lambda m: "" if _MECH_RE.search(m.group(0)) else m.group(0), text)


def _clean_lines(lines) -> list[str]:
    """逐行剔机制括注；仍命中机制词的整行弃；剥尾部悬空标点。"""
    out = []
    for raw in lines or []:
        t = _strip_mech_parens(str(raw)).strip()
        if t and not _MECH_RE.search(t):
            out.append(t.rstrip("；;，,、：:").strip())
    return out


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(value: str, sub: str = "") -> Path:
    """路径直用；裸名回落 references/[sub/]<value>.json。"""
    p = Path(value)
    if p.exists():
        return p
    cand = (refs_root() / sub / f"{value}.json") if sub else (refs_root() / value)
    if cand.exists():
        return cand
    raise FileNotFoundError(f"找不到文件：{value}")


def _ctx(ns) -> tuple[dict, dict, list[dict]]:
    """(stage, std_map, formulas_list) 公共加载。"""
    stage = _load_json(_resolve(ns.stage, "stages"))
    std_doc = _load_json(_resolve(ns.standards_file) if ns.standards_file else refs_root() / "standards_index.json")
    fx_doc = _load_json(_resolve(ns.formulas_file) if ns.formulas_file else refs_root() / "formulas.json")
    return stage, {s.get("code", ""): s for s in std_doc.get("standards", [])}, fx_doc.get("formulas", [])


def _std_display(code: str, stds: dict) -> str:
    e = stds.get(code)
    if e is None:  # 章内引用常省年份（如 HJ 464）：前缀回退，字典序取首
        hits = sorted(k for k in stds if k.startswith(code))
        e = stds[hits[0]] if hits else None
    if e is None:
        return f"《{code}》"
    role = _strip_mech_parens(e.get("role", "")).strip("；; （）")
    return f"《{e['code']}》{e.get('title', '')}" + (f"（{role}）" if role else "")


def _fam_label(fam: str, forms: dict) -> str:
    return forms.get(fam, {}).get("label") or fam


def _slots_fams(slots) -> set[str]:
    out = set()
    for s in slots or []:
        m = re.match(r"\{\{(?:TABLE|SLOT):([^.}]+)", str(s))
        if m:
            out.add(m.group(1))
    return out


def _formula_fam_users(fam: str, formulas: list[dict]) -> list[str]:
    """资料族用途反查：公式描述里出现该族键 → 公式名列表。"""
    return [f.get("name", f.get("id", "")) for f in formulas if fam in json.dumps(f, ensure_ascii=False)]


def _render_outline(stage: dict, stds: dict, formulas: list[dict]) -> str:
    forms, chs = stage.get("forms", {}), stage.get("chapters", {})
    L = ["# 全书编写策划书", "",
         "> 本策划书由系统按报告结构契约自动生成：全书怎么写、每章依据哪些标准规范、涉及哪些计算、需要准备哪些资料。", "",
         "## 一、报告结构总览", ""]
    for i, (cid, ch) in enumerate(chs.items(), 1):
        mode = _clean_lines([ch.get("mode", "")])
        L.append(f"{i}. 第{i}章「{ch.get('title', cid)}」" + (f"——{mode[0]}" if mode else ""))
    L += ["", "## 二、各章写法与依据", ""]
    for i, (cid, ch) in enumerate(chs.items(), 1):
        L.append(f"### 第{i}章「{ch.get('title', cid)}」")
        for m in _clean_lines([ch.get("mode", "")]):
            L.append(f"- 章定位：{m}")
        refs = _clean_lines([_std_display(c, stds) for c in ch.get("std_refs", [])])
        L.append("- 依据标准：" + ("、".join(refs) if refs else "以总则章标准体系为准"))
        fids = ch.get("formulas", [])
        fnames = [f.get("name", fid) for f in formulas if f.get("id") in fids]
        L.append("- 涉及计算：" + ("、".join(fnames) if fnames else "本章不含计算"))
        fams = "、".join(_fam_label(x, forms) for x in ch.get("forms", []))
        L.append("- 需要的资料：" + (fams or "无专项资料"))
        tbls = _clean_lines(ch.get("tables", []))
        if tbls:
            L.append("- 主要表格：" + "、".join(tbls))
        L.append("")
    return "\n".join(L) + "\n"


def cmd_outline(ns) -> int:
    try:
        stage, stds, formulas = _ctx(ns)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_outline(stage, stds, formulas), encoding="utf-8")
    print(f"BRIEF_OUTLINE_OK {out}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Agent 业务内容简报渲染器（机械渲染，零 LLM）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("outline", help="全书编写策划书")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_outline)

    ns = ap.parse_args(argv)
    sys.exit(ns.fn(ns))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑 Task 1 测试确认通过**

同 Step 2 harness 命令。Expected: `2 passed`。

- [ ] **Step 5: Commit**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
        backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py \
        docs/superpowers/plans/2026-11-04-agent-briefing-layer.md
git commit -m "feat(skills): briefing 渲染器骨架与 outline 策划书子命令（交互体验重塑 T1）

机械模板拼接零 LLM；机制词行/括注剔除；tmp fixture 测试不触真实 references。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: chapter 子命令（章说明 + 每节注记）

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py`
- Test: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py`

- [ ] **Step 1: 追加失败测试**

在 `test_briefing.py` 追加：

```python
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
    assert "规模数值全槽位" not in text  # 括注剔后仍命中 → 整行弃
    _assert_clean(text)


def test_chapter_unknown_rc1(tmp_path):
    fx = _fixtures(tmp_path)
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   chapter="ch9", out=str(tmp_path / "b.md"))
    rc, _, se = _capture(briefing.cmd_chapter, ns)
    assert rc == briefing.EXIT_ERROR and "ERROR" in se
```

- [ ] **Step 2: 跑测试确认失败**

同 harness 命令。Expected: FAIL（`cmd_chapter` 不存在）。

- [ ] **Step 3: 实现 chapter**

`briefing.py` 在 `cmd_outline` 前追加（`_render_chapter` 置于 `_render_outline` 后）：

```python
def _render_chapter(stage: dict, ch_id: str, stds: dict, formulas: list[dict]) -> str:
    chs = stage.get("chapters", {})
    if ch_id not in chs:
        raise KeyError(ch_id)
    forms = stage.get("forms", {})
    order = list(chs)
    i = order.index(ch_id) + 1
    ch = chs[ch_id]
    prev_txt = f"第{i - 1}章「{chs[order[i - 2]].get('title', '')}」" if i >= 2 else "报告开头部分"
    next_txt = f"第{i + 1}章「{chs[order[i]].get('title', '')}」" if i < len(order) else "结论与交付"
    L = [f"# 第{i}章「{ch.get('title', ch_id)}」编写说明", "",
         "> 本说明由系统按报告结构契约自动生成：这一章怎么写、依据哪些标准、涉及哪些计算、需要哪些资料、每节的上下文衔接。",
         "", "## 一、本章定位与上下文", ""]
    for m in _clean_lines([ch.get("mode", "")]):
        L.append(f"- 章定位：{m}")
    L.append(f"- 前承：{prev_txt}；后启：{next_txt}。")
    ke = _clean_lines(ch.get("key_elements", []))
    if ke:
        L.append("- 编写要点：")
        L += [f"  - {x}" for x in ke]
    wp = _clean_lines(ch.get("writing_patterns", []))
    if wp:
        L.append("- 注意事项：")
        L += [f"  - {x}" for x in wp]
    L += ["", "## 二、依据的标准规范", ""]
    L += [f"- {_std_display(c, stds)}" for c in ch.get("std_refs", [])]
    L += ["", "## 三、本章计算说明", ""]
    fids = ch.get("formulas", [])
    mine = [f for f in formulas if f.get("id") in fids]
    if not mine:
        L.append("本章不含计算内容，数值由已登记资料直接带入。")
    for f in mine:
        L += [f"### {f.get('name', f.get('id'))}", f"- 算法：{_strip_mech_parens(f.get('expr', ''))}"]
        for inp in f.get("inputs", []):
            unit = f"，单位 {inp['unit']}" if inp.get("unit") else ""
            src = str(inp.get("source", ""))
            fam_hit = next((fm for fm in forms if fm in src), None)
            src_txt = f"（来自{_fam_label(fam_hit, forms)}资料）" if fam_hit else ""
            L.append(f"- 输入：{inp.get('desc', inp.get('name', ''))}{unit}{src_txt}")
        outs = "、".join(_strip_mech_parens(o.get("desc") or o.get("name", "")) for o in f.get("outputs", []))
        L.append(f"- 输出：{outs}")
        note = _clean_lines([f.get("note", "")])
        if note:
            L.append(f"- 说明：{note[0]}")
    L += ["", "## 四、本章资料清单", ""]
    for fam in ch.get("forms", []):
        users = _formula_fam_users(fam, formulas)
        u = f"（供「{'」「'.join(users[:3])}」等计算使用）" if users else ""
        L.append(f"- {_fam_label(fam, forms)}{u}")
    tbls = _clean_lines(ch.get("tables", []))
    if tbls:
        L += ["", "## 五、本章主要表格", ""] + [f"- {t}" for t in tbls]
    L += ["", "## 六、各节写法注记", ""]
    secs = ch.get("sections", [])
    for j, sec in enumerate(secs):
        prev_s = secs[j - 1].get("title", "") if j else ""
        next_s = secs[j + 1].get("title", "") if j + 1 < len(secs) else "本章小结"
        fams = sorted(_slots_fams(sec.get("slots") or sec.get("uses", {}).get("slots", [])))
        fids_s = sec.get("uses", {}).get("formulas", [])
        fnames = [f.get("name", fid) for f in formulas if f.get("id") in fids_s]
        refs = "、".join(f"《{c}》" for c in ch.get("std_refs", [])[:3])
        L.append(f"### {sec.get('id', '')}「{sec.get('title', '')}」")
        link = ([f"上承「{prev_s}」"] if prev_s else []) + [f"下启「{next_s}」"]
        L.append("，".join(link) + "。")
        if refs:
            L.append(f"编写依据：{refs}。")
        if fams:
            L.append("用到资料：" + "、".join(_fam_label(x, forms) for x in fams) + "。")
        L.append("涉及计算：" + ("、".join(fnames) if fnames else "本节不含计算") + "。")
        L.append("")
    return "\n".join(L)


def cmd_chapter(ns) -> int:
    try:
        stage, stds, formulas = _ctx(ns)
        text = _render_chapter(stage, ns.chapter, stds, formulas)
    except (FileNotFoundError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"BRIEF_CHAPTER_OK {out}")
    return EXIT_OK
```

并在 `main()` 的 outline parser 后追加：

```python
    p = sub.add_parser("chapter", help="第N章编写说明（含每节注记）")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--chapter", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_chapter)
```

- [ ] **Step 4: 跑 Task 2 测试确认通过**

同 harness 命令。Expected: `4 passed`。

- [ ] **Step 5: Commit**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
        backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py
git commit -m "feat(skills): briefing chapter 子命令——章编写说明+每节注记（T2）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: data-request 子命令（资料需求单 + CSV 模板）

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py`
- Test: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py`

**设计偏差明示（对设计文档 §4.1）**：CSV 内**不放**底部填写说明注释行（设计文档原写「底部注释行」）——注释行有被 `ingest.py file` 解析进数据的风险（ingest 是唯一写者）；填写说明改放需求单 md 内对应条目下。其余（UTF-8 BOM、中文列头、1 行示例）不变。

- [ ] **Step 1: 追加失败测试**

```python
def test_data_request_renders(tmp_path):
    fx = _fixtures(tmp_path)
    outdir = tmp_path / "requests"
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   families="geo,mon", out_dir=str(outdir))
    rc, so, _ = _capture(briefing.cmd_data_request, ns)
    assert rc == briefing.EXIT_OK and "BRIEF_REQUEST_OK" in so
    md = (outdir / "资料需求单.md").read_text(encoding="utf-8")
    for frag in ["资料需求单", "区域自然环境概况（必需）", "环境质量监测（可选）", "供「概率积分法地表沉陷预测」",
                 "第1章、第2章要用", "位置与行政区划（必填）", "井田清单：表格"]:
        assert frag in md, f"需求单缺「{frag}」"
    assert "user_docs" not in md  # 机制 note 剔除
    _assert_clean(md)
    csvs = sorted(outdir.glob("*.csv"))
    assert len(csvs) == 1
    raw = csvs[0].read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "井田名称,设计能力(Mt/a)"
    assert lines[1] == "【请填写】,【请填写】"
    assert len(lines) == 2  # 无注释行（ingest 唯一写者防误解析）


def test_data_request_unknown_family_rc1(tmp_path):
    fx = _fixtures(tmp_path)
    ns = Namespace(stage=str(fx["stage"]), standards_file=str(fx["std"]), formulas_file=str(fx["fx"]),
                   families="nope", out_dir=str(tmp_path / "r"))
    rc, _, se = _capture(briefing.cmd_data_request, ns)
    assert rc == briefing.EXIT_ERROR and "ERROR" in se
```

- [ ] **Step 2: 跑测试确认失败**

Expected: FAIL（`cmd_data_request` 不存在）。

- [ ] **Step 3: 实现 data-request**

`briefing.py` 追加（import 区补 `import csv`、`import io`——骨架已含）：

```python
def _csv_columns(arr_field: dict) -> list[str]:
    """数组族字段 → CSV 列名。item fields 字符串形如 "element 要素(…)"：取首空格后中文；dict 取 label。"""
    cols = []
    for item in arr_field.get("fields", []):
        if isinstance(item, str):
            cols.append(item.split(" ", 1)[1] if " " in item else item)
        elif isinstance(item, dict):
            cols.append(str(item.get("label") or item.get("name", "")))
    return [c for c in cols if c]


def _csv_templates(stage: dict, fams: list[str], out_dir: Path) -> list[Path]:
    forms = stage.get("forms", {})
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for fam in fams:
        spec = forms.get(fam) or {}
        for arr in [f for f in spec.get("fields", []) if str(f.get("type", "")).startswith("array")]:
            cols = _csv_columns(arr)
            if not cols:
                continue
            buf = io.StringIO()
            csv.writer(buf).writerows([cols, ["【请填写】"] * len(cols)])
            p = out_dir / f"{fam}_{arr.get('name', 'rows')}_模板.csv"
            p.write_text(buf.getvalue(), encoding="utf-8-sig")
            paths.append(p)
    return paths


def _render_request(stage: dict, fams: list[str], csv_paths: list[Path], formulas: list[dict]) -> str:
    forms = stage.get("forms", {})
    known = [f for f in fams if f in forms]
    L = ["# 资料需求单", "",
         "> 请按下列条目准备资料：表格类条目已附 CSV 模板（Excel 打开、每行填一条、列顺序勿动，填完发回对话即可）；"
         "文字类条目直接在对话里告诉我。", ""]
    for fam in known:
        spec = forms[fam]
        users = _formula_fam_users(fam, formulas)
        chs = "、".join(f"第{int(c[2:])}章" for c in spec.get("chapters", []) if str(c).startswith("ch") and c[2:].isdigit())
        use = ("供「" + "」「".join(users[:3]) + "」等计算使用") if users else "报告编写直接引用"
        tail = f"；{chs}要用" if chs else ""
        req = "必需" if spec.get("required") else "可选"
        L += [f"## {spec.get('label', fam)}（{req}）", f"- 用途：{use}{tail}。"]
        for f in spec.get("fields", []):
            if str(f.get("type", "")).startswith("array"):
                cols = _csv_columns(f)
                hit = next((p.name for p in csv_paths if p.name.startswith(f"{fam}_")), "")
                cols_txt = "、".join(cols[:6]) + ("等" if len(cols) > 6 else "")
                attach = f"（已附模板 {hit}）" if hit else ""
                L.append(f"- {f.get('label', f['name'])}：表格，逐行填写{attach}（列：{cols_txt}）")
            else:
                note = _clean_lines([f.get("note", "")])
                star = "必填" if f.get("required") else "可选"
                L.append(f"- {f.get('label', f['name'])}（{star}）" + (f"——{note[0]}" if note else ""))
        L.append("")
    return "\n".join(L)


def cmd_data_request(ns) -> int:
    try:
        stage, stds, formulas = _ctx(ns)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    forms = stage.get("forms", {})
    fams = [f.strip() for f in ns.families.split(",") if f.strip()] if ns.families else list(forms)
    unknown = [f for f in fams if f not in forms]
    if unknown:
        print(f"ERROR: 未知资料族：{'、'.join(unknown)}", file=sys.stderr)
        return EXIT_ERROR
    out_dir = Path(ns.out_dir)
    csv_paths = _csv_templates(stage, fams, out_dir)
    md = out_dir / "资料需求单.md"
    md.write_text(_render_request(stage, fams, csv_paths, formulas), encoding="utf-8")
    print(f"BRIEF_REQUEST_OK {md} ({len(csv_paths)} csv)")
    return EXIT_OK
```

`main()` 追加 parser：

```python
    p = sub.add_parser("data-request", help="资料需求单 + 表格族 CSV 模板")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--families", default="")
    p.add_argument("--out-dir", required=True)
    p.set_defaults(fn=cmd_data_request)
```

- [ ] **Step 4: 跑 Task 3 测试确认通过**

Expected: `6 passed`。

- [ ] **Step 5: Commit**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
        backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py
git commit -m "feat(skills): briefing data-request 子命令——资料需求单+CSV 模板（T3）

CSV 内不放注释行（ingest 唯一写者防误解析，对设计文档的偏差已记录）。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: calc-summary 子命令（计算说明）

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py`
- Test: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py`

- [ ] **Step 1: 追加失败测试**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Expected: FAIL（`cmd_calc_summary` 不存在）。

- [ ] **Step 3: 实现 calc-summary**

`briefing.py` 追加：

```python
_SRC_ZH = (("derived:", "系统按公式计算"), ("user_monitoring", "您提供的监测数据"),
           ("analog_mine", "类比矿井实测"), ("user_docs", "您上传的文件"), ("form:", "您登记的资料"))


def _src_zh(src: str, forms: dict) -> str:
    for prefix, zh in _SRC_ZH:
        if src.startswith(prefix):
            if prefix == "form:":
                fam = src[len(prefix):].split("(", 1)[0].strip()
                return f"来自{_fam_label(fam, forms)}资料"
            return zh
    return src


def _chapter_prefixes(stage: dict, ch_id: str, fx_doc: dict) -> set[str]:
    """章口径槽位前缀 = 本章公式 slots + 本章消费的派生槽。"""
    prefixes = set()
    fids = stage["chapters"].get(ch_id, {}).get("formulas", [])
    for f in fx_doc.get("formulas", []):
        if f.get("id") in fids:
            for s in f.get("slots", []):
                m = re.match(r"\{\{SLOT:([^.}]+)", str(s))
                if m:
                    prefixes.add(m.group(1))
    for d in fx_doc.get("derived_slots", []):
        if ch_id in str(d.get("chapter", "")):
            m = re.match(r"\{\{SLOT:([^.}]+)", str(d.get("slot", "")))
            if m:
                prefixes.add(m.group(1))
    return prefixes


def _render_calc(stage: dict, state: dict, ch_id: str, fx_doc: dict) -> str:
    forms = stage.get("forms", {})
    formulas = fx_doc.get("formulas", [])
    prefixes = _chapter_prefixes(stage, ch_id, fx_doc) if ch_id else None
    title = f"第{list(stage['chapters']).index(ch_id) + 1}章" if ch_id else "全书"
    L = ["# 计算说明", "",
         f"> 报告中的数字由系统按公式统一核算。下列为{title}本次核算结果与数据来源（自动生成，未经人工改动）。"]
    cur_fam = None
    for key in sorted(state.get("values", {})):
        if prefixes is not None and not any(key.startswith(p + ".") for p in prefixes):
            continue
        fam = key.split(".", 1)[0]
        if fam != cur_fam:
            cur_fam = fam
            L += ["", f"## {_fam_label(fam, forms)}", ""]
        v = state["values"][key]
        desc = key.split(".", 1)[1]
        for f in formulas:
            hit = next((o for o in f.get("outputs", [])
                        if key == o.get("name") or key.startswith(o.get("name", "\0").split("[")[0])), None)
            if hit:
                desc = _strip_mech_parens(hit.get("desc") or hit.get("name", desc)) or desc
                break
        unit = f" {v['unit']}" if v.get("unit") else ""
        L.append(f"- {desc}：{v.get('display', v.get('value'))}{unit}——{_src_zh(str(v.get('source', '')), forms)}")
    anomalies = _clean_lines(state.get("anomalies", []))
    if anomalies:
        L += ["", "## 未完成计算（缺资料，未编造）", ""]
        for a in anomalies:
            txt = a
            for fam, spec in forms.items():
                txt = txt.replace(fam, spec.get("label", fam))
            L.append(f"- {txt}")
    return "\n".join(L) + "\n"


def cmd_calc_summary(ns) -> int:
    try:
        stage, stds, formulas = _ctx(ns)
        fx_doc = {"formulas": formulas, "derived_slots": _load_json(
            Path(ns.formulas_file) if ns.formulas_file else refs_root() / "formulas.json").get("derived_slots", [])}
        state = _load_json(Path(ns.state_dir) / "formula_state.json")
        if ns.chapter and ns.chapter not in stage.get("chapters", {}):
            raise KeyError(ns.chapter)
    except (FileNotFoundError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_calc(stage, state, ns.chapter, fx_doc), encoding="utf-8")
    print(f"BRIEF_CALC_OK {out}")
    return EXIT_OK
```

`main()` 追加 parser：

```python
    p = sub.add_parser("calc-summary", help="计算说明（冻结值+来源）")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--chapter", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_calc_summary)
```

- [ ] **Step 4: 跑全量测试确认通过**

Expected: `8 passed`。

- [ ] **Step 5: Commit**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
        backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py
git commit -m "feat(skills): briefing calc-summary 子命令——计算说明冻结值+来源（T4）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 质量关——sync 守卫 + 全量测试 + ruff/isort

**Files:**
- Modify（生成）: `backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/`（由 sync 脚本生成）

- [ ] **Step 1: 跑 sync 脚本（writer → chapter-writer 单向同步）**

```bash
cd /c/workspace/pisuan && python -X utf8 scripts/sync_chapter_skill.py
```

Expected: 同步完成输出（briefing.py + test_briefing.py 进 chapter 包 scripts/）；`git status` 显示 chapter 包两个新文件。

- [ ] **Step 2: 宿主全量测试（双布局之一：repo 布局 harness）**

harness 同 Task 1 Step 2，跑两个目录：

```bash
cd "$H" && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -m pytest pkg/coal-eia-writer/scripts/tests/ pkg/coal-eia-chapter-writer/scripts/tests/ -q
```

注：junction 只挂 writer；chapter 包测试回落 refs_root() 到 writer 兄弟包——harness 里补第二个 junction：

```bash
cmd //c "mklink /J $(cygpath -w "$H/pkg/coal-eia-chapter-writer") $(cygpath -w "/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer")"
```

Expected: 全绿（既有 263+ 一侧全量 + 新增 8×2）。

- [ ] **Step 3: ruff + isort 零违规（新文件零基线直接全清）**

```bash
cd /c/workspace/pisuan/backend
uvx ruff@0.16.4 format package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
    package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py
uvx ruff@0.16.4 check package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
    package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py
uvx isort package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/briefing.py \
    package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_briefing.py
```

注意（cerebrum DNR）：E501 按 Unicode 显示宽计（CJK×2），话术/文案行超 120 用隐式拼接拆行；`from _paths import` 在 sys.path.insert 后须 `# noqa: E402`（isort 序：`_paths` 排在字母小写模块之前）。格式化后重跑 Step 2 确认仍全绿，然后 sync 重跑一次使 chapter 包字节一致，amend 不做——追加提交：

- [ ] **Step 4: Commit（sync 产物 + 格式化收尾）**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/briefing.py \
        backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/tests/test_briefing.py
git commit -m "chore(skills): sync_chapter_skill 同步 briefing 资产到 chapter 包（T5）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 栈部署（挂载层字节拷贝）+ 容器双布局全量测试

**Files:** 无 repo 改动；向 `pisuan-localized` 工作树拷贝（DNR：briefing.py 无 yuxi import → 字节直拷免 sed；测试文件同）。

- [ ] **Step 1: 拷贝到挂载层（api 热重载可见）**

```bash
W=/c/workspace/pisuan-localized/backend/package/pisuan/agents/skills/buildin
R=/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin
for pkg in coal-eia-writer coal-eia-chapter-writer; do
  cp "$R/$pkg/scripts/briefing.py" "$W/$pkg/scripts/briefing.py"
  cp "$R/$pkg/scripts/tests/test_briefing.py" "$W/$pkg/scripts/tests/test_briefing.py"
done
```

- [ ] **Step 2: 容器双布局全量测试**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -m pytest /app/package/pisuan/agents/skills/buildin/coal-eia-writer/scripts/tests/ -q
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -m pytest /app/package/pisuan/agents/skills/buildin/coal-eia-chapter-writer/scripts/tests/ -q
```

Expected: 两包全绿（基线量 + 8/侧）。容器路径禁省 MSYS_NO_PATHCONV=1（Git Bash 会改写 /app 路径致静默 0 collected——cerebrum DNR）。

- [ ] **Step 3: 容器内真数据冒烟（真实 references + 真实 stage）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -X utf8 /app/package/pisuan/agents/skills/buildin/coal-eia-writer/scripts/briefing.py outline --stage planning_eia --out /tmp/brief_outline.md
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -X utf8 /app/package/pisuan/agents/skills/buildin/coal-eia-writer/scripts/briefing.py chapter --stage planning_eia --chapter ch6 --out /tmp/brief_ch6.md
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -X utf8 /app/package/pisuan/agents/skills/buildin/coal-eia-writer/scripts/briefing.py data-request --stage planning_eia --families subsidence_params,monitoring --out-dir /tmp/dr
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -X utf8 /app/package/pisuan/agents/skills/buildin/coal-eia-writer/scripts/briefing.py calc-summary --stage planning_eia --state-dir /app/package/pisuan/agents/skills/buildin/coal-eia-writer/scripts/tests --chapter ch6 --out /tmp/calc.md
```

Expected: 四条 rc=0（BRIEF_*_OK）。calc-summary 冒烟用 tests 目录凑 state-dir 会 rc=1（无 formula_state.json）——属预期错误路径验证，换断言：前两条 rc=0 且 `/tmp/brief_outline.md` 含「概率积分法」；data-request 生成 ≥1 csv；calc-summary 报 ERROR rc=1 即通过。真实 formula_state 冒烟放 Task 9 用实测工作区数据。

---

### Task 7: writer SKILL.md 接线（四处）

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`

- [ ] **Step 1: 接线①——开题预告处（「步骤 1」第 1 条 ② 数据预告段尾）**

锚点（现文）：`用户明确缺的族照常落 `[待确认]`，缺数不编造。`
追加一句：

```markdown
预告同时生成《全书编写策划书》文件卡：`briefing.py outline --stage S --out T/state/brief_outline.md`（rc=0=BRIEF_OUTLINE_OK）经 `present_artifacts` 呈现——策划书含全书章链定位、各章标准依据、计算概览与资料需求总表，机械渲染稿照贴原文禁改写；与数据预告同轮完成，不另发消息、不停车。
```

- [ ] **Step 2: 接线②——数组族三步协议①（「步骤 1」第 5 条数组族批量收集三步协议）**

锚点（现文）：`① agent 从 stage schema 子字段中文 label 生成 CSV 模板（UTF-8 **with BOM**，含 1 行示例）经 present_artifacts 呈现下载；`
整行替换为：

```markdown
① 跑 `briefing.py data-request --stage S --families <缺项族,逗号分隔> --out-dir T/data_requests/`（rc=0=BRIEF_REQUEST_OK）经 `present_artifacts` 呈现**资料需求单 + 各表格族 CSV 模板**（UTF-8 BOM、中文列名、1 行示例；填写说明在需求单内，CSV 内不放注释行防 ingest 误解析）——机械渲染稿禁手工改动列结构；多族缺项时一次全部生成，用户可离线一次备齐（≤5 行小数组可改逐项卡，既有口径不变）；
```

- [ ] **Step 3: 接线③——门 2 段尾（「步骤 2–3 · 冻结计算 → 门 2」门 2 说明段尾）**

锚点（现文）：`公式结果全 0/空时同样走本门呈现。`
追加：

```markdown
门 2 处置完成后呈现《计算说明》文件卡：`briefing.py calc-summary --stage S --state-dir T --out T/state/calc_summary.md`（rc=0=BRIEF_CALC_OK）——冻结值、算法与数据来源的机械渲染稿照贴原文禁改写，与 anomalies 卡同轮呈出，不新增停车点。
```

- [ ] **Step 4: 接线④——每章首波派发前 + 节稿注记（「步骤 4」4.1 派发契约段首）**

锚点（现文）：`**4.1 派发契约**（每 PENDING 章按波一次；重派=原 prompt 原文 + 门 stderr 原文，**不重新组装**——防逐次漂移）：`
在其前插入一段：

```markdown
**4.0.5 每章开写说明（非停车）**：每章首波派发前 `briefing.py chapter --stage S --chapter chN --out T/state/brief_chN.md`（rc=0=BRIEF_CHAPTER_OK）经 `present_artifacts` 呈《第N章编写说明》文件卡——含本章定位与前后章衔接、标准规范（中文名+作用）、计算说明、资料清单、**各节写法注记**。此后每节稿呈现时，头部先贴该节注记原文（取自本文件「各节写法注记」块，照贴禁改写；文件缺失时按同口径自拟：依据标准/用到资料与计算/上下文衔接，≤3 句）。
```

- [ ] **Step 5: Commit**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md
git commit -m "docs(skills): writer SKILL.md 接线 briefing 四触点（T7）

开题策划书/资料需求单+CSV模板/计算说明/每章开写说明+节注记；零新增停车点。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: chapter-writer SKILL.md 接线（五处）

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/SKILL.md`

- [ ] **Step 1: 接线①——开题数据预告（步骤 1 第 2 条 ①+② 段尾）**

锚点（现文）：`①+② 载体 = 首张表单 `question` 文本开头，不另发独立消息。`
追加：

```markdown
预告同轮生成《全书编写策划书》文件卡：`briefing.py outline --stage S --out T/state/brief_outline.md`（rc=0=BRIEF_OUTLINE_OK，STAGE 口径同全脚本）经 `present_artifacts` 呈现，机械渲染稿照贴原文禁改写，不停车。
```

- [ ] **Step 2: 接线②——卡A 计划卡（步骤 1 第 3 条）**

锚点（现文，卡A 五块内容句）：`④ **将用到的资料**（本章数据族中文名清单；只预告不提问，问什么仍以门 1 裁决为准）；`
替换为：

```markdown
④ **将用到的资料**（本章数据族中文名清单，每族带用途一句话——供哪个计算/哪节使用，素材同 briefing 渲染口径；只预告不提问，问什么仍以门 1 裁决为准）；
```

锚点（现文）：`**无计划卡不得进门 1 与后续任何收集动作（红线 P13）**；`
在其前插入：

```markdown
卡A 呈现同轮附带《第N章编写说明》文件卡：`briefing.py chapter --stage S --chapter chN --out T/state/brief_chN.md`（rc=0=BRIEF_CHAPTER_OK）经 `present_artifacts` 呈出（含定位衔接/标准规范/计算说明/资料清单/各节写法注记，机械渲染稿禁改写），卡尾注明「详细写法、标准依据与计算说明见附件《第N章编写说明》」——文件卡不停车，卡A 停车语义不变。
```

- [ ] **Step 3: 接线③——收集纪律（步骤 1 第 5 条）**

锚点（现文）：`交互纪律全套继承 writer（单回合一卡、CSV 三步协议、示例值≠数据、只传用户提交的键、每收完一类立即落盘、脚本崩溃即停、ingest 唯一写者）。`
替换为：

```markdown
交互纪律全套继承 writer（单回合一卡、CSV 三步协议、示例值≠数据、只传用户提交的键、每收完一类立即落盘、脚本崩溃即停、ingest 唯一写者）。**缺项收集首动作为资料需求单**：把门1 缺项族经 `briefing.py data-request --stage S --families <缺项族,逗号分隔> --out-dir T/data_requests/` 生成《资料需求单》+ 表格族 CSV 模板（每项带用途说明；机械渲染稿禁改写）与缺项卡同轮呈出——问什么仍以门 1 裁决为准（红线 P9 不变），需求单只做「为什么需要+怎么填」的载体。
```

- [ ] **Step 4: 接线④——3a 增量冻结后（3a 条目尾）**

锚点（现文）：`（stdout `SCOPE:` 行为切片日志，向用户如实转述）。`
追加：

```markdown
冻结完成后呈现《本章计算说明》文件卡：`briefing.py calc-summary --stage S --state-dir T --chapter chN --out T/state/calc_summary_chN.md`（rc=0=BRIEF_CALC_OK）——本章冻结值、算法与数据来源照贴原文禁改写，随 3a 汇报同轮呈出，不停车。
```

- [ ] **Step 5: 接线⑤——节稿即产即呈（3 段首「节稿即产即呈」句）**

锚点（现文）：`**节稿即产即呈**：每节写完并批量记账后，读该节稿全文在对话中完整呈现（节标题+正文+表格+一句业务化要点提示）——随写随看，3e 确认卡不重贴。正文语体按用户沟通规范红线执行（机制性独白禁入正文）。`
替换为：

```markdown
**节稿即产即呈**：每节写完并批量记账后，读该节稿全文在对话中完整呈现（节标题+正文+表格+一句业务化要点提示）——随写随看，3e 确认卡不重贴。呈现头部先贴该节**写法注记**（取自 `state/brief_chN.md`「各节写法注记」块对应节，照贴禁改写，≤3 句；文件缺失时按同口径自拟：依据标准/用到资料与计算/上下文衔接）。正文语体按用户沟通规范红线执行（机制性独白禁入正文）。
```

- [ ] **Step 6: Commit**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/SKILL.md
git commit -m "docs(skills): chapter-writer SKILL.md 接线 briefing 五触点（T8）

卡A 附章说明+资料带用途/需求单与CSV模板/增量冻结计算说明/节注记照贴；卡A/卡B/确认卡停车语义零变化。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 沙箱运行面部署（四面链剩余两面）+ 真数据冒烟

**Files:** 无 repo 改动；向 localized 栈 skill-sources / projections 拷贝。

- [ ] **Step 1: 拷贝到 skill-sources/shared 与 skill-projections/admin**

```bash
R=/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin
for base in /c/workspace/pisuan-localized/docker/volumes/pisuan/skill-sources/shared \
            /c/workspace/pisuan-localized/docker/volumes/pisuan/skill-projections/admin; do
  for pkg in coal-eia-writer coal-eia-chapter-writer; do
    cp "$R/$pkg/scripts/briefing.py" "$base/$pkg/scripts/briefing.py"
    cp "$R/$pkg/scripts/tests/test_briefing.py" "$base/$pkg/scripts/tests/test_briefing.py"
  done
done
```

四面核对（哈希一致）：

```bash
R=/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin
B=/c/workspace/pisuan-localized/backend/package/pisuan/agents/skills/buildin
S=/c/workspace/pisuan-localized/docker/volumes/pisuan/skill-sources/shared
P=/c/workspace/pisuan-localized/docker/volumes/pisuan/skill-projections/admin
md5sum "$R/coal-eia-writer/scripts/briefing.py" "$B/coal-eia-writer/scripts/briefing.py" \
       "$S/coal-eia-writer/scripts/briefing.py" "$P/coal-eia-writer/scripts/briefing.py" \
       "$R/coal-eia-chapter-writer/scripts/briefing.py" "$B/coal-eia-chapter-writer/scripts/briefing.py" \
       "$S/coal-eia-chapter-writer/scripts/briefing.py" "$P/coal-eia-chapter-writer/scripts/briefing.py"
```

Expected: 每包四面 md5 一致（两两相同共 2 组）。

- [ ] **Step 2: 实测工作区真数据冒烟（hengcheng-ch3 现场有真实 formula_state）**

容器内挂载路径对工作区 volumes 不可见——冒烟在宿主直接跑（briefing 纯标准库，宿主可跑）：

```bash
cd /c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts
PYTHONIOENCODING=utf-8 python -X utf8 briefing.py calc-summary --stage planning_eia \
  --state-dir /c/workspace/pisuan-localized/docker/volumes/pisuan/threads/shared/admin/workspace/workspace/eia-report/hengcheng-ch3/state \
  --chapter ch3 --out /tmp/calc_ch3_real.md
PYTHONIOENCODING=utf-8 python -X utf8 briefing.py outline --stage planning_eia --out /tmp/outline_real.md
PYTHONIOENCODING=utf-8 python -X utf8 briefing.py data-request --stage planning_eia --families monitoring,subsidence_params --out-dir /tmp/dr_real
```

Expected: 三条 rc=0；`/tmp/calc_ch3_real.md` 含真实冻结值与「未完成计算」段；`/tmp/outline_real.md` 含 13 章全链；`/tmp/dr_real` 有 monitoring 各数组族 csv ≥2 份。人工抽查产物语体（零机制词、标准中文名在位）。

- [ ] **Step 3: 冒烟通过后收尾记录（无 commit——纯部署面）**

记录四面哈希输出与冒烟产物路径到会话日志即可。

---

### Task 10: changelog + 簿记 + 推送

**Files:**
- Modify: `docs/develop-guides/changelog.md`
- Modify: `.wolf/cerebrum.md`、`.wolf/memory.md`、`.wolf/anatomy.md`（hook 自动收录新文件则只补描述）

- [ ] **Step 1: changelog 条目**

`docs/develop-guides/changelog.md` v0.7.3 段顶部追加（格式随现有条目）：

```markdown
- **feat(skills): Agent 业务简报渲染层（briefing 层）**——交互体验重塑（用户实测反馈：管线播报式输出缺业务层引导）。新增 `briefing.py` 四子命令（outline 全书策划书 / chapter 章说明+每节注记 / data-request 资料需求单+表格族 CSV 模板 / calc-summary 计算说明冻结值+来源），references 结构化资产机械渲染零 LLM、机制词剔除；writer SKILL.md 四触点、chapter-writer 五触点接线（卡A 附章说明、资料带用途、缺项首动作需求单、冻结后计算说明、节稿注记照贴）；**零新增停车点**，progress/ingest/formula_runner/build_output 零改动。CSV 内不放注释行（防 ingest 误解析，对设计文档的偏差已记录）。测试：`scripts/tests/test_briefing.py` 8 用例 + banlist 语体回归；双布局容器全绿；四面部署哈希一致。
```

- [ ] **Step 2: 簿记**

- `.wolf/cerebrum.md` 追加 Key Learnings：briefing 渲染器四子命令口径 + CSV 无注释行原因 + 数组族 item fields 字符串形状（`"element 要素(…)"` 首空格后中文）
- `.wolf/memory.md` 追加会话行（hook 可能已自动记录部分）
- `.wolf/anatomy.md` 确认 briefing.py/test_briefing.py 条目在册（hook 自动；缺则补一行）

- [ ] **Step 3: 推送**

```bash
cd /c/workspace/pisuan
git push origin pisuan-custom
```

Expected: 推送成功（前两笔均首试成功口径）。

---

## Self-Review 记录

1. **Spec 覆盖**：设计文档 §4.1 四子命令→T1–T4；§4.2 节注记→T2（chapter 内置）+T7④/T8⑤ 照贴规则；§4.3 卡A 增厚→T8 Step 2；§4.4 五处接线→T7（writer 四处：writer 无卡A，章说明挪 4.0.5）+T8（chapter 五处）；§6 测试→各 Task Step + T5/T6；§7 验收 1–4/8→工件与接线，5→注记，6→banlist 回归，7→零新增停车（各接线明示「不停车」）。CSV 注释行偏差已在 T3/T10 明示。
2. **占位符扫描**：无 TBD/TODO；所有代码块完整；错误路径均有断言。
3. **类型一致性**：`_ctx(ns)` 返回三元组在 T1–T4 一致；`cmd_*(ns)->int` 一致；fixture 键名（stage/std/fx/state）跨用例一致；`Namespace` 字段与 parser 参数一一对应（`out_dir`/`families`/`state_dir`/`chapter`）。
