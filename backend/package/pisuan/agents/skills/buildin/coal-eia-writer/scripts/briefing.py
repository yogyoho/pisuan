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
    r"\{\{|\}\}|SLOT|TABLE|exact_match|ingest|FORM_|rc=|\bXS\d+|\bEO\d+|门\s?\d|\.json|param_source|"
    r"user_docs|user_monitoring|analog_mine|--[a-z]"
)
_PAREN_RE = re.compile(r"（[^（）]*）|\([^()]*\)")


def _strip_mech_parens(text: str) -> str:
    """剔除含机制词的括注，干净括注保留。"""
    return _PAREN_RE.sub(lambda m: "" if _MECH_RE.search(m.group(0)) else m.group(0), text)


def _clean_lines(lines) -> list[str]:
    """逐行剔机制括注；原行含模板记号（{{…}}——记号即内容，剔后句子失义）或剔后仍命中机制词 → 整行弃。"""
    out = []
    for raw in lines or []:
        s = str(raw)
        t = _strip_mech_parens(s).strip()
        if not t or _MECH_RE.search(t) or "{{" in s:
            continue
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
    L = [
        "# 全书编写策划书",
        "",
        "> 本策划书由系统按报告结构契约自动生成：全书怎么写、每章依据哪些标准规范、涉及哪些计算、需要准备哪些资料。",
        "",
        "## 一、报告结构总览",
        "",
    ]
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
        fnames = [f.get("name") or f.get("id", "") for f in formulas if f.get("id") in fids]
        L.append("- 涉及计算：" + ("、".join(fnames) if fnames else "本章不含计算"))
        fams = "、".join(_fam_label(x, forms) for x in ch.get("forms", []))
        L.append("- 需要的资料：" + (fams or "无专项资料"))
        tbls = _clean_lines(ch.get("tables", []))
        if tbls:
            L.append("- 主要表格：" + "、".join(tbls))
        L.append("")
    return "\n".join(L) + "\n"


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
    L = [
        f"# 第{i}章「{ch.get('title', ch_id)}」编写说明",
        "",
        "> 本说明由系统按报告结构契约自动生成：这一章怎么写、依据哪些标准、"
        "涉及哪些计算、需要哪些资料、每节的上下文衔接。",
        "",
        "## 一、本章定位与上下文",
        "",
    ]
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
        L += [f"### {f.get('name') or f.get('id')}", f"- 算法：{_strip_mech_parens(f.get('expr', ''))}"]
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
        fnames = [f.get("name") or f.get("id", "") for f in formulas if f.get("id") in fids_s]
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
            p.write_bytes(buf.getvalue().encode("utf-8-sig"))  # write_bytes 免 Windows \n→\r\n 翻译（csv 自带 \r\n）
            paths.append(p)
    return paths


def _render_request(stage: dict, fams: list[str], csv_paths: list[Path], formulas: list[dict]) -> str:
    forms = stage.get("forms", {})
    known = [f for f in fams if f in forms]
    L = [
        "# 资料需求单",
        "",
        "> 请按下列条目准备资料：表格类条目已附 CSV 模板（Excel 打开、每行填一条、列顺序勿动，填完发回对话即可）；"
        "文字类条目直接在对话里告诉我。",
        "",
    ]
    for fam in known:
        spec = forms[fam]
        users = _formula_fam_users(fam, formulas)
        chs = "、".join(
            f"第{int(c[2:])}章" for c in spec.get("chapters", []) if str(c).startswith("ch") and c[2:].isdigit()
        )
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


_SRC_ZH = (
    ("derived:", "系统按公式计算"),
    ("user_monitoring", "您提供的监测数据"),
    ("analog_mine", "类比矿井实测"),
    ("user_docs", "您上传的文件"),
    ("form:", "您登记的资料"),
)


def _src_zh(src: str, forms: dict) -> str:
    for prefix, zh in _SRC_ZH:
        if src.startswith(prefix):
            if prefix == "form:":
                fam = src[len(prefix) :].split("(", 1)[0].strip()
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
    L = [
        "# 计算说明",
        "",
        f"> 报告中的数字由系统按公式统一核算。下列为{title}本次核算结果与数据来源（自动生成，未经人工改动）。",
    ]
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
            hit = next(
                (
                    o
                    for o in f.get("outputs", [])
                    if key == o.get("name") or key.startswith(o.get("name", "\0").split("[")[0])
                ),
                None,
            )
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
                txt = re.sub(rf"(\d*_)?{re.escape(fam)}\b", spec.get("label", fam), txt)
            L.append(f"- {txt}")
    return "\n".join(L) + "\n"


def cmd_calc_summary(ns) -> int:
    try:
        stage, stds, formulas = _ctx(ns)
        fx_path = Path(ns.formulas_file) if ns.formulas_file else refs_root() / "formulas.json"
        fx_doc = {"formulas": formulas, "derived_slots": _load_json(fx_path).get("derived_slots", [])}
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


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Agent 业务内容简报渲染器（机械渲染，零 LLM）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("outline", help="全书编写策划书")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_outline)

    p = sub.add_parser("chapter", help="第N章编写说明（含每节注记）")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--chapter", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_chapter)

    p = sub.add_parser("data-request", help="资料需求单 + 表格族 CSV 模板")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--families", default="")
    p.add_argument("--out-dir", required=True)
    p.set_defaults(fn=cmd_data_request)

    p = sub.add_parser("calc-summary", help="计算说明（冻结值 + 数据来源）")
    p.add_argument("--stage", required=True)
    p.add_argument("--standards-file", default="")
    p.add_argument("--formulas-file", default="")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--chapter", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_calc_summary)

    ns = ap.parse_args(argv)
    sys.exit(ns.fn(ns))


if __name__ == "__main__":
    main()
