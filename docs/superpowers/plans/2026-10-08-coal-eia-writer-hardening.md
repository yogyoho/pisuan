# coal-eia-writer 部分一硬化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 治理 coal-eia-writer 四类供给断链：schema linter（5 stage 体检）、样例库接通（41 份语料→切片+SL3 池+深度基线）、范式形态库与节级数值期望（语料统计驱动）、SKILL 接入写前对账。

**Architecture:** 技能侧离线管线（不触知识工厂/管线脚本/yuxi core）：`prepare_corpus.py`（docx→md）→ `bank_compile.py`（切片+SL3 池+per 矿种基线+两族新衍生物+stage 级聚合）→ `schema_linter.py`（独立体检）。产物进 `references/`（git 入库），中间 workdir 留 `.wolf/`（不入库）。

**Tech Stack:** Python 3.12+（stdlib + python-docx），pytest（容器内 `docker exec`），bank_compile 确定性编译惯例（sort_keys + `\n` + 幂等）。

**Spec:** `docs/superpowers/specs/2026-10-08-coal-eia-writer-hardening-design.md`

**技能根目录**（下文 `<SKILL>`）：`C:\workspace\pisuan\backend\package\yuxi\agents\skills\buildin\coal-eia-writer`

**运行栈拓扑**（执行类任务用）：容器名 `pisuan-localized-api-1`；技能运行时同步 = `docker cp` 进 `/app/skill-sources` 与 `/app/skill-projections` 两卷（先 `docker exec pisuan-localized-api-1 find /app/skill-sources -maxdepth 2 -name coal-eia-writer` 探实际挂点）。docker cp/exec 均需 `MSYS_NO_PATHCONV=1`。

---

## Task 1: schema_linter.py 骨架 + L1/L2 检查（TDD）

**Files:**
- Create: `<SKILL>/scripts/schema_linter.py`
- Test: `<SKILL>/scripts/tests/test_schema_linter.py`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
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
    forms = {"fam1": {"label": "族一", "fields": [
        {"name": "no_label", "type": "string", "required": True},
        {"name": "empty_label", "label": "  ", "type": "string"},
        {"name": "ok", "label": "正常字段", "type": "string"},
    ]}}
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l1 = [v for v in rep["violations"] if v["check"] == "L1"]
    assert len(l1) == 2
    assert {v["field"] for v in l1} == {"no_label", "empty_label"}


def test_l2_pipe_char(tmp_path):
    """label/note 含竖线 → L2 命中（bug-393 裂表根因）。"""
    forms = {"fam1": {"label": "族一", "fields": [
        {"name": "a", "label": "良好|含竖线", "type": "string"},
        {"name": "b", "label": "正常", "type": "string", "note": "备注|也禁"},
        {"name": "c", "label": "枚举族", "type": "enum:甲|乙|丙"},
    ]}}
    rep = lint_stage(_mk_stage(tmp_path, forms))
    l2 = [v for v in rep["violations"] if v["check"] == "L2"]
    assert len(l2) == 3
```

- [ ] **Step 2: 运行确认失败**

Run: `docker exec pisuan-localized-api-1 python -c "import ast; ast.parse(open('/dev/null').read())"`（容器可用性探针）
Run（宿主）: `PYTHONIOENCODING=utf-8 python -m pytest scripts/tests/test_schema_linter.py -v`（workdir `<SKILL>`；若宿主无 pytest 则 docker cp 后容器内跑，方式同 Task 1 Step 4）
Expected: FAIL — `ModuleNotFoundError: schema_linter`

- [ ] **Step 3: 实现 schema_linter.py（L1/L2 + 骨架）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema_linter.py — stage forms 资产静态体检（spec 2026-10-08-coal-eia-writer-hardening-design §4.3）。

五类检查（只报告不修复；stage JSON 修复另行立项）：
  L1 forms 族标量字段缺中文 label            （bug-366：135 字段）
  L2 label/note/type(enum 描述) 含 "|" 字符   （bug-393：28 组竖线枚举裂表）
  L3 数值型字段缺 unit（type number/int/float 开头且 unit/note 均无单位）
  L4 name 英文蛇形裸奔（无中文 label）        （bug-368：英文列键入文）
  L5 枚举值卫生：type "enum:..." 值含英文字母/重复段/单段超 20 字
用法：
  python -X utf8 schema_linter.py --references <refs目录> [--stage planning_eia]
  全量扫描 references/stages/*.json；有违规 exit 1，报告逐条 stderr + JSON 摘要 stdout。
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REFS_DEFAULT = SCRIPTS_DIR.parent / "references"

NUMERIC_TYPE_RE = re.compile(r"^(number|int|float)")
ENGLISH_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
HAS_CJK_RE = re.compile(r"[一-鿿]")
ENUM_PREFIX = "enum:"
UNIT_HINT_RE = re.compile(r"[一-鿿a-zA-Z]{1,6}(?:/[\u0000-\uFFFF]{1,6})?")  # 占位，L3 用 note 文本判定


def _iter_scalar_fields(forms: dict):
    """遍历 forms 树：yield (族名, 字段dict)。族内 fields[] 为字段清单。"""
    for fam_name, fam in forms.items():
        if not isinstance(fam, dict):
            continue
        for f in fam.get("fields", []):
            if isinstance(f, dict):
                yield fam_name, f


def lint_stage(stage_path: Path) -> dict:
    """单 stage 体检：返回 {"stage", "violations": [{check, family, field, detail}]}。"""
    doc = json.loads(stage_path.read_text(encoding="utf-8"))
    forms = doc.get("forms") or {}
    violations: list[dict] = []

    def add(check, fam, f, detail):
        violations.append({"check": check, "family": fam, "field": f.get("name", "?"), "detail": detail})

    for fam, f in _iter_scalar_fields(forms):
        label = str(f.get("label") or "")
        note = str(f.get("note") or "")
        ftype = str(f.get("type") or "")
        # L1 标量字段缺中文 label
        if not HAS_CJK_RE.search(label):
            add("L1", fam, f, f"label 缺失或非中文：{label!r}")
        # L2 竖线（label/note/type 全查）
        for src_name, src in (("label", label), ("note", note), ("type", ftype)):
            if "|" in src:
                add("L2", fam, f, f"{src_name} 含竖线：{src!r}")
        # L3 数值型缺单位（unit 字段或 note 均无）
        if NUMERIC_TYPE_RE.match(ftype):
            has_unit = bool(f.get("unit")) or _unit_in_note(note)
            if not has_unit:
                add("L3", fam, f, f"数值型无单位：type={ftype!r} note={note!r}")
        # L4 英文蛇形裸奔：name 全英文 且 label 也无中文（L1 已报缺 label；L4 报「label 是英文」形态）
        if ENGLISH_NAME_RE.match(str(f.get("name", ""))) and label and not HAS_CJK_RE.search(label):
            add("L4", fam, f, f"英文 label：{label!r}")
        # L5 枚举值卫生
        if ftype.startswith(ENUM_PREFIX):
            val = ftype[len(ENUM_PREFIX):]
            parts = [p for p in re.split(r"[、,，/；;]", val) if p.strip()]
            if any(re.search(r"[a-zA-Z]", p) for p in parts):
                add("L5", fam, f, f"枚举值含英文：{val!r}")
            if len(parts) != len(set(parts)):
                add("L5", fam, f, f"枚举值重复：{val!r}")
            if any(len(p.strip()) > 20 for p in parts):
                add("L5", fam, f, f"枚举段超 20 字：{val!r}")

    return {"stage": stage_path.stem, "violations": violations}


def _unit_in_note(note: str) -> bool:
    """note 是否含单位字样（常见单位词表命中即认）。"""
    UNITS = ("m³", "m2", "hm2", "km2", "dB", "mg/L", "μg", "μg/m³", "km", "万m³", "万t", "万 kW", "%", "：")
    return any(u in note for u in UNITS)
```

注意：`_unit_in_note` 的词表在 Task 2 按 L3 实跑结果校准（planning_eia 已人修三轮，L3 违规应为个位数——若误报过多，以 stage 内既有 note 惯例扩词表）。

- [ ] **Step 4: 跑通测试**

Run: 同 Step 2 方式 `pytest scripts/tests/test_schema_linter.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5: 提交**

```bash
cd C:/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/schema_linter.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_schema_linter.py
git commit -F <msg文件>   # "feat(skill): schema_linter L1/L2 检查与骨架（部分一 Task 1）" + Co-Authored-By: Claude Code <noreply@anthropic.com>
```

---

## Task 2: schema_linter L3 报告口径校准 + CLI 全量扫描

**Files:**
- Modify: `<SKILL>/scripts/schema_linter.py`（补 CLI main）
- Test: `<SKILL>/scripts/tests/test_schema_linter.py`（追加）

- [ ] **Step 1: 追加 CLI 测试（失败）**

```python
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
```

- [ ] **Step 2: 实现 main_with_args**

```python
def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="stage forms 五类静态体检（L1-L5，只报告不修复）")
    ap.add_argument("--references", default=str(REFS_DEFAULT), help="技能 references 目录")
    ap.add_argument("--stage", default=None, help="只查单个 stage（缺省全量 stages/*.json）")
    args = ap.parse_args(argv)
    stages_dir = Path(args.references) / "stages"
    paths = sorted(stages_dir.glob("*.json")) if not args.stage else [stages_dir / f"{args.stage}.json"]
    summary = {}
    total = 0
    for p in paths:
        rep = lint_stage(p)
        counts: dict[str, int] = {}
        for v in rep["violations"]:
            counts[v["check"]] = counts.get(v["check"], 0) + 1
            print(f"[{rep['stage']}] {v['check']} {v['family']}.{v['field']}: {v['detail']}", file=sys.stderr)
        summary[rep["stage"]] = counts
        total += len(rep["violations"])
    print(json.dumps({"stages": summary, "total": total}, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if total else 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 跑通测试**
- [ ] **Step 4: 实跑 5 stage，报告落档 `.wolf/linter-report-2026-10-08.md`**（人工速览：bug-366/393/394 项是否重发现；planning_eia 应近零——已三轮人修；其余 4 stage 结果即 N5 疑点答案）

Run: `PYTHONIOENCODING=utf-8 python -X utf8 scripts/schema_linter.py --references references > ../../../../../../../.wolf/linter-report-2026-10-08.json 2> ../../../.wolf/linter-report-2026-10-08.stderr.txt`（workdir `<SKILL>/scripts`；路径按实际调整，产物两份：JSON 摘要 + stderr 明细）
Expected: exit 1（有违规即预期），明细可读

- [ ] **Step 5: 提交**（含报告落 `.wolf/` 不入库；只提交代码+测试）

---

## Task 3: prepare_corpus.py — docx→md 转换器（TDD）

**Files:**
- Create: `<SKILL>/scripts/prepare_corpus.py`
- Test: `<SKILL>/scripts/tests/test_prepare_corpus.py`

- [ ] **Step 1: 失败测试（节号识别/目录剔除/表格 GFM）**

```python
# -*- coding: utf-8 -*-
"""prepare_corpus 测试：节号标题识别 / 目录页剔除 / 表格 GFM / 裁剪边界。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prepare_corpus import (SEC_LINE_RE, is_toc_line, strip_toc, table_to_gfm,
                            promote_headings)


def test_sec_line_levels():
    assert SEC_LINE_RE.match("6.5 声环境影响评价").groups() == ("6.5", "声环境影响评价")
    assert SEC_LINE_RE.match("1 总 论").groups() == ("1", "总 论")
    assert not SEC_LINE_RE.match("环境影响评价（无节号）")


def test_toc_line_and_strip():
    assert is_toc_line("1 总 论\t5")
    assert is_toc_line("2.1 评价目的 28")
    assert not is_toc_line("6.5 声环境影响评价")  # 正文标题无尾随页码
    body = "1 总 论\t5\n2 项目概况\t28\n6.5 声环境影响评价\n正文段落。\n"
    assert "总 论\t5" not in strip_toc(body)
    assert "6.5 声环境影响评价" in strip_toc(body)


def test_table_to_gfm_pad():
    """docx 表行（list[list[str]]）→ GFM：列数取齐（bug-393 反向杜绝）。"""
    rows = [["要素", "数值"], ["声级", "60", "多余列"]]
    md = table_to_gfm(rows)
    lines = md.splitlines()
    assert lines[1].count("|") == lines[0].count("|") == lines[2].count("|")
    assert "---" in lines[1]


def test_promote_headings():
    body = "6.5 声环境影响评价\n正文。\n6.5.1 点源预测\n子正文。\n"
    out = promote_headings(body)
    assert "### 6.5 声环境影响评价" in out   # 两段 → ###
    assert "#### 6.5.1 点源预测" in out      # 三段 → ####
    assert "## 6.5 声环境影响评价" not in out
```

- [ ] **Step 2: 确认失败**（ModuleNotFoundError）
- [ ] **Step 3: 实现**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_corpus.py — 样例语料 docx → bank_compile 输入格式（spec §五 解析边界）。

输入：<语料目录>/*.docx（41 份真实环评报告书，C:\\项目管理\\样例文件）
输出：<workdir>/<report_id>/source.md（UTF-8、节号标题 ##/###/#### 化、GFM 表格）
      + <workdir>/manifest.json 草稿（report_id/stage/mineral/file_name——stage 人工过目后定稿）
用法：
  python -X utf8 prepare_corpus.py --corpus-dir <语料目录> --workdir <输出目录> [--census <census.json>]
边界：
  - 节号标题：正文行 "数字(.数字)* + 空白 + 题名"（census 实测 679 标题仅 81 个有 style 标记）
  - 目录页剔除：「节号+题+尾随页码」行连续 ≥3 判为目录区段整段剔除
  - 表格：docx table → GFM，列数取 max 补空（杜绝裂表）
  - 范围裁剪：剔封面/编制单位页（前 2 页语义：首个节号标题之前的非目录内容丢弃）
  - 解析失败：逐份 stderr 警告 + 跳过（bank_compile 既有惯例）；census 可解析性已预验证
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SEC_LINE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*\S|\S)\s*$")
TOC_TAIL_RE = re.compile(r"\s\t?\d{1,3}\s*$")
GFM_SEP = "|"


def is_toc_line(line: str) -> bool:
    """目录行：节号标题形态 + 尾随独立页码。"""
    m = SEC_LINE_RE.match(line.strip())
    if not m:
        return False
    tail = line.rstrip()
    return bool(TOC_TAIL_RE.search(tail)) and not tail.rstrip().endswith(tuple("。；：，"))


def strip_toc(text: str) -> str:
    """连续 ≥3 行目录行 → 整段剔除（正文标题无页码不受影响）。"""
    out, run = [], []
    for ln in text.splitlines():
        if is_toc_line(ln):
            run.append(ln)
            continue
        if len(run) >= 3:
            run.clear()  # 丢弃目录区段
        else:
            out.extend(run)
            run.clear()
        out.append(ln)
    if len(run) < 3:
        out.extend(run)
    return "\n".join(out)


def promote_headings(body: str) -> str:
    """节号行加 markdown 标题前缀：2 段号→###，3+ 段号→####，单段→##（bank SEC_RE 认 ##~####）。"""
    out = []
    for ln in body.splitlines():
        m = SEC_LINE_RE.match(ln.strip())
        if m and len(m.group(1)) <= 12:
            depth = m.group(1).count(".")
            prefix = "##" if depth == 0 else ("###" if depth == 1 else "####")
            out.append(f"{prefix} {m.group(1)} {m.group(2)}")
        else:
            out.append(ln)
    return "\n".join(out)


def table_to_gfm(rows: list[list[str]]) -> str:
    """docx 表 → GFM；列数取 max 补空。"""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [list(r) + [""] * (width - len(r)) for r in rows]
    norm = [[c.replace("\n", " ").replace("|", "／").strip() for c in r] for r in norm]
    head = f"{GFM_SEP}" + f"{GFM_SEP}".join(norm[0]) + f"{GFM_SEP}"
    sep = f"{GFM_SEP}" + f"{GFM_SEP}".join(["---"] * width) + f"{GFM_SEP}"
    body = "\n".join(f"{GFM_SEP}" + f"{GFM_SEP}".join(r) + f"{GFM_SEP}" for r in norm[1:])
    return "\n".join([head, sep, body])


def iter_blocks(doc):
    """docx body 有序遍历（Paragraph/Table 混排；版本无关，不走 iter_inner_content）。"""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.ns import qn
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def docx_to_md(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts: list[str] = []
    for block in iter_blocks(doc):
        if block.__class__.__name__ == "Paragraph":
            t = unicodedata.normalize("NFKC", block.text).strip()
            if t:
                parts.append(t)
        else:
            rows = [[c.text for c in row.cells] for row in block.rows]
            gfm = table_to_gfm(rows)
            if gfm:
                parts.append(gfm)
    return strip_toc(promote_headings("\n\n".join(parts)))


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="语料 docx → bank_compile 输入（source.md + manifest 草稿）")
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--census", default=None, help="corpus-census/census.json——继承普查元数据")
    args = ap.parse_args(argv)
    corpus, workdir = Path(args.corpus_dir), Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    census = {}
    if args.census and Path(args.census).is_file():
        census = {Path(e["file"]).stem: e for e in json.loads(Path(args.census).read_text(encoding="utf-8"))}
    manifest, ok = [], 0
    for docx in sorted(corpus.glob("*.docx")):
        rid = re.sub(r"[^a-z0-9\-_]+", "-", unicodedata.normalize("NFKC", docx.stem).lower()).strip("-")[:60]
        try:
            md = docx_to_md(docx)
        except Exception as exc:  # 逐份警告+跳过惯例
            print(f"[prepare_corpus] {docx.name} 解析失败——跳过：{exc}", file=sys.stderr)
            continue
        if not SEC_LINE_RE.search(promote_headings(md)):
            print(f"[prepare_corpus] {docx.name} 零节号标题——跳过", file=sys.stderr)
            continue
        d = workdir / rid
        d.mkdir(exist_ok=True)
        (d / "source.md").write_text(md + "\n", encoding="utf-8", newline="\n")
        meta = census.get(docx.stem.replace(".docx", ""), {})
        manifest.append({"report_id": rid, "stage": "", "mineral": "coal",
                         "file_name": docx.name,
                         "chars": meta.get("chars", len(md))})
        ok += 1
        print(f"[prepare_corpus] {docx.name} -> {rid}（{len(md)} chars）")
    (workdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"PREPARED: {ok} report(s) -> {workdir}")
    return 0 if ok else 1
```

注意：manifest 的 `stage` 留空——**人工过目步骤**（Task 5）填 planning_eia/project_eia_underground/project_eia_openpit/post_eia；census 的族分布（planning 18/project 22/post 4）作底稿。

- [ ] **Step 4: 跑通测试**
- [ ] **Step 5: 提交**

---

## Task 4: 41 份语料实跑转换（执行步骤）

**Files:** 产物在 `C:/workspace/pisuan/.wolf/corpus-workdir/`（本地工作区，不入库）

- [ ] **Step 1: 实跑转换**

Run（宿主，workdir `<SKILL>/scripts`）: `PYTHONIOENCODING=utf-8 python -X utf8 prepare_corpus.py --corpus-dir "C:/项目管理/样例文件" --workdir "C:/workspace/pisuan/.wolf/corpus-workdir" --census "C:/workspace/pisuan/.wolf/corpus-census/census.json"`
Expected: `PREPARED: 40±2 report(s)`（跳过份在 stderr 有理由）；与 census 41 份对账，差份逐条列原因

- [ ] **Step 2: 抽查 3 份 source.md 质量**：节号标题层级正确（##/###）、目录页已剔、表格 GFM 列齐。发现解析缺陷回 Task 3 修（buglog 记录）
- [ ] **Step 3: manifest stage 人工过目定稿**：按 census 族分布（planning 18/project 22/post 4/tracking 0）+ 报告名逐份填 stage；project 族按井工/露天拆 underground/openpit。写入 `.wolf/corpus-workdir/manifest.json`

---

## Task 5: bank_compile 现有管线跑通（切片+SL3 池+per 矿种基线）

**Files:** 产物进 `<SKILL>/references/`（samples_bank/、samples/、depth_targets/<stage>/<mineral>.json）

- [ ] **Step 1: 跑编译**

Run: `PYTHONIOENCODING=utf-8 python -X utf8 scripts/bank_compile.py --workdir "C:/workspace/pisuan/.wolf/corpus-workdir" --references references`（workdir `<SKILL>`）
Expected: `BANK_COMPILED: N report(s), M slice(s), G group(s)`，零跳过（或跳过理由已过目）

- [ ] **Step 2: 验证 SL3 池就位**：`ls references/samples/*/ | head`——5 stage 中 4 个有 chN__*.md（tracking_eia 无语料为预期空）
- [ ] **Step 3: git 入库**：`git add backend/.../coal-eia-writer/references/samples_bank backend/.../coal-eia-writer/references/samples backend/.../coal-eia-writer/references/depth_targets`（explicit add，确认文件数合理后提交）

---

## Task 6: bank_compile 聚合 per 矿种基线 → stage 级 depth_targets（门形状，TDD）

**Files:**
- Modify: `<SKILL>/scripts/bank_compile.py`
- Test: `<SKILL>/scripts/tests/test_bank_compile_aggregate.py`（新建）

**背景**：门消费 `depth_targets/<stage>.json`（形状 `{"chapters": {"ch6": {"floor_chars": N}}}`，build_output.py:617）；calibrate 产出 `per_chapter.{ch}.median_eff` + `coefficient 0.6`。聚合换算：`floor_chars = median(各矿种 median_eff × coefficient)`。手维形状参照 `references/depth_targets/planning_eia.json`（stage/generated/confidence/source/chapters）。

- [ ] **Step 1: 失败测试**

```python
# -*- coding: utf-8 -*-
"""bank_compile 聚合测试：per 矿种 → stage 级 floor_chars（组间 median × coefficient）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import _aggregate_depth_targets


def test_aggregate_median_across_minerals(tmp_path):
    refs = tmp_path / "references"
    dt = refs / "depth_targets" / "stage_a"
    dt.mkdir(parents=True)
    (dt / "coal.json").write_text(json.dumps(
        {"coefficient": 0.6, "per_chapter": {"ch1": {"median_eff": 10000}, "ch2": {"median_eff": 20000}}}), encoding="utf-8")
    (dt / "coal2.json").write_text(json.dumps(
        {"coefficient": 0.6, "per_chapter": {"ch1": {"median_eff": 20000}}}), encoding="utf-8")
    _aggregate_depth_targets(refs, "stage_a", generated="2026-10-08")
    doc = json.loads((refs / "depth_targets" / "stage_a.json").read_text(encoding="utf-8"))
    assert doc["chapters"]["ch1"]["floor_chars"] == 9000   # median(6000, 12000)
    assert doc["chapters"]["ch2"]["floor_chars"] == 12000  # 单矿种 20000*0.6
    assert doc["stage"] == "stage_a"
    assert "coal" in doc["source"]
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（bank_compile.py 增函数 + main 标定循环后逐 stage 聚合）

```python
def _aggregate_depth_targets(refs: Path, stage: str, generated: str) -> None:
    """per 矿种基线 → depth_targets/<stage>.json（门形状 chapters.{ch}.floor_chars）。

    floor_chars = 组间 median(median_eff × coefficient)——「基线」取组间中位，
    单章缺失矿种不参与该章统计；产物形状与手维版兼容（门零改动）。"""
    import statistics
    mineral_dir = refs / "depth_targets" / stage
    docs = []
    for p in sorted(mineral_dir.glob("*.json")):
        try:
            docs.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[bank_compile] 聚合跳过损坏文件 {p.name}: {exc}", file=sys.stderr)
    if not docs:
        return
    chapters: dict[str, dict] = {}
    all_chs = sorted({ch for d in docs for ch in d.get("per_chapter", {})})
    for ch in all_chs:
        floors = [d["per_chapter"][ch]["median_eff"] * d.get("coefficient", 0.6)
                  for d in docs if ch in d.get("per_chapter", {})]
        if floors:
            chapters[ch] = {"floor_chars": int(statistics.median(floors))}
    doc = {"stage": stage, "generated": generated, "confidence": "calibrated",
           "source": f"bank_compile aggregate: {', '.join(p.name for p in sorted(mineral_dir.glob('*.json')))}",
           "chapters": chapters}
    _json_write(refs / "depth_targets" / f"{stage}.json", doc)
```

main 里 per (stage, mineral) 标定循环后（`for (stage, mineral), items in sorted(...)` 块之后）追加：

```python
    for stage in sorted({s for (s, _m) in groups}):
        _aggregate_depth_targets(refs, stage, generated=__import__("time").strftime("%Y-%m-%d"))
        print(f"  AGGREGATED depth_targets/{stage}.json")
```

（generated 用时间戳：此为维护者一次性产物非幂等复算对象；测试注入固定值。）

- [ ] **Step 4: 跑通测试；重跑 Task 5 编译验证 `depth_targets/<stage>.json` 生成**
- [ ] **Step 5: 提交**

---

## Task 7: bank_compile 扩展 forms_catalog.json 形态统计（TDD）

**Files:**
- Modify: `<SKILL>/scripts/bank_compile.py`
- Test: `<SKILL>/scripts/tests/test_bank_compile_forms.py`（新建）

- [ ] **Step 1: 失败测试（三形态分类与统计）**

```python
# -*- coding: utf-8 -*-
"""forms_catalog 形态统计测试：table_lead 三形态 / numeric_citation / 例句溯源。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import classify_table_lead, build_forms_catalog


def test_classify_table_lead():
    assert classify_table_lead("矿区主要噪声源及其源强如下表所列。") == "complete_sentence"
    assert classify_table_lead("评价标准如下表所示：") == "complete_sentence"
    assert classify_table_lead("各源强参数见下表。") == "complete_sentence"
    assert classify_table_lead("沉陷参数体系及其逐井输入条件以") == "dangling"  # bug-394 同款残句
    assert classify_table_lead("**表 6-1 源强**") == "standalone_caption"


def test_build_forms_catalog(tmp_path):
    segs = [("rid1", "矿区主要噪声源如下表所列。\n\n**表 6-1 源强**\n\n| 源 | 强度 |\n|---|---|\n| a | 1 |\n\n"
             "厂界噪声为 60 dB(A)。\n"),
            ("rid2", "评价标准详见表 6-2。\n\n**表 6-2 标准**\n\n| 指标 | 值 |\n|---|---|\n| b | 2 |\n\n"
             "源强为 95 dB(A)。")]
    cat = build_forms_catalog(segs, generated="2026-10-08")
    tl = cat["forms"]["table_lead"]
    assert tl["stats"]["complete_sentence"] == 1.0
    assert len(tl["examples"]) >= 1 and tl["examples"][0]["report_id"] in ("rid1", "rid2")
    nc = cat["forms"]["numeric_citation"]
    assert nc["stats"]["exact_with_unit"] == 1.0   # 两句数值均带 dB(A)
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（bank_compile.py 增三函数；main 切片循环收集 `seg_samples`（(rid, seg)），循环外编译）

```python
CAPTION_LINE_RE = re.compile(r"^\*\*[表图]\s*\d+-\d+")
DANGLING_RE = re.compile(r"[^。：；！？」）]$")
NUM_UNIT_SENT_RE = re.compile(r"([一-鿿A-Za-z]{2,12})为\s*(\d+(?:\.\d+)?)\s*([一-鿿A-Za-zμ/%°·()（）A-Z]{1,8})")


def classify_table_lead(prev_line: str) -> str:
    """表题行前一非空行形态：complete_sentence（句末收束）/ standalone_caption（表题行相邻）/
    dangling（残句——bug-394 形态）。"""
    s = prev_line.strip()
    if CAPTION_LINE_RE.match(s) or s.startswith("|"):
        return "standalone_caption"
    if not s:
        return "empty"
    if s.endswith(("。", "：", "；", "！", "？", "」", "）")):
        return "complete_sentence"
    return "dangling"


def build_forms_catalog(seg_samples, generated: str) -> dict:
    """三形态统计+例句池（spec §4.1）。seg_samples: [(rid, seg_text)]。"""
    from collections import Counter
    lead_counter: Counter = Counter()
    lead_examples: list[dict] = []
    num_counter: Counter = Counter()
    num_examples: list[dict] = []
    for rid, seg in seg_samples:
        lines = seg.splitlines()
        for i, ln in enumerate(lines):
            if CAPTION_LINE_RE.match(ln.strip()):
                prev = next((lines[j].strip() for j in range(i - 1, -1, -1) if lines[j].strip()), "")
                if prev:
                    form = classify_table_lead(prev)
                    lead_counter[form] += 1
                    if form in ("complete_sentence", "dangling") and len(lead_examples) < 40:
                        lead_examples.append({"report_id": rid, "form": form, "text": prev[:80]})
        for m in NUM_UNIT_SENT_RE.finditer(seg):
            num_counter["exact_with_unit"] += 1
            if len(num_examples) < 40:
                num_examples.append({"report_id": rid, "text": m.group(0)[:60]})
    total_lead = sum(lead_counter.values()) or 1
    total_num = sum(num_counter.values()) or 1
    return {
        "version": "1.0", "generated": generated,
        "source": f"corpus slices statistics ({len(seg_samples)} report(s))",
        "forms": {
            "table_lead": {
                "desc": "表题行前一非空行形态（正样本：complete_sentence 为主形态）",
                "stats": {k: round(lead_counter.get(k, 0) / total_lead, 3)
                          for k in ("complete_sentence", "colon_lead", "standalone_caption", "dangling")},
                "templates": ["……{主题}如下表所列。", "……{主题}详见表 {ch}-{seq}。", "……{主题}："],
                "examples": lead_examples,
            },
            "numeric_citation": {
                "desc": "数值引用形态（exact_with_unit 为主形态；dangling 残句零容忍）",
                "stats": {k: round(num_counter.get(k, 0) / total_num, 3) for k in ("exact_with_unit",)},
                "templates": ["{量}为 {value} {unit}。", "……介于 {v1}～{v2} {unit} 之间。"],
                "examples": num_examples,
            },
            "caliber_disambiguation": {
                "desc": "同标签多值消歧写法（v1 从「按…计/按…口径」句式抽取；templates 固化推荐写法）",
                "stats": {},
                "templates": ["按{口径A}为 {v1}，按{口径B}为 {v2}。", "…（{口径}）…"],
                "examples": [],
            },
        },
    }
```

main 里 `print(f"BANK_COMPILED: ...")` 前插入：

```python
    catalog = build_forms_catalog([(e["report_id"], text_map[e["report_id"]]) for e in reports if e["report_id"] in text_map],
                                  generated=__import__("time").strftime("%Y-%m-%d"))
    _json_write(refs / "paradigms" / "forms_catalog.json", catalog)
    print(f"FORMS_CATALOG: {len(catalog['forms']['table_lead']['examples'])} lead example(s)")
```

（main 的报告循环中维护 `text_map: dict[rid, text]`——已有 `text` 局部变量，循环内 `text_map[rid] = text` 即可。caliber_disambiguation v1 留空 stats——自动统计误报率高，验收时人工从语料补例句池，spec 已声明。）

- [ ] **Step 4: 跑通全部 bank_compile 测试**
- [ ] **Step 5: 提交**

---

## Task 8: bank_compile 扩展 section_expectations.json 节级期望（TDD）

**Files:**
- Modify: `<SKILL>/scripts/bank_compile.py`
- Test: `<SKILL>/scripts/tests/test_bank_compile_expectations.py`（新建）

**聚合规则**（spec §4.2）：逐切片节（sec/title）→ 句子抽「量词+数值+单位」→ 语境归并 field 路径（forms label 匹配优先，未命中进 unmapped 池）→ 频率 tier 划档。

- [ ] **Step 1: 失败测试**

```python
# -*- coding: utf-8 -*-
"""section_expectations 测试：数值抽取 / field 归并 / tier 划档 / unmapped 池。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank_compile import build_section_expectations


def test_build_section_expectations():
    # 两个切片同一节（title 匹配），各提一次「源强为 95 dB(A)」→ freq 1.0 required
    segs = [
        {"rid": "r1", "chapter": "6", "sec": "6.5", "title": "声环境影响评价",
         "text": "源强为 95 dB(A)。运输噪声源强为 75 dB(A)。"},
        {"rid": "r2", "chapter": "6", "sec": "6.5", "title": "声环境影响评价",
         "text": "主要声源源强为 92 dB(A)。"},
    ]
    forms_label_map = {"源强": "noise.source_level"}
    doc = build_section_expectations(segs, forms_label_map, stage="planning_eia", generated="2026-10-08")
    s = doc["sections"]["ch6_S01"]  # 归并键按章+节序（测试中单节归 S01）
    q = {e["caliber"]: e for e in s["expected_quantities"]}
    assert q["源强"]["corpus_freq"] == 1.0 and q["源强"]["tier"] == "required"
    assert q["源强"]["unit"] == "dB(A)"
    assert q["源强"]["field"] == "noise.source_level"


def test_unmapped_pool():
    segs = [{"rid": "r1", "chapter": "3", "sec": "3.2", "title": "某某分析", "text": "不确定量为 12 km。"}]
    doc = build_section_expectations(segs, {}, stage="planning_eia", generated="2026-10-08")
    assert doc["unmapped"], "未归并量应进 unmapped 池显式列出"
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**

```python
QUANTITY_RE = re.compile(r"([一-鿿]{2,8}?)(?:为|达|是)\s*(\d+(?:?:\.\d+)?)\s*(dB\(A\)|mg/L|μg/m³|km²|km|m²|hm²|万m³|万t|万kW|%|m|t|d)")


def build_section_expectations(seg_infos, forms_label_map: dict, stage: str, generated: str) -> dict:
    """节级数值-口径清单（spec §4.2）。seg_infos: [{rid, chapter, sec, title, text}]。

    field 归并：语境名词精确匹配 forms_label_map（bank_compile main 由 stage json forms
    fields label → "<族>.<name>" 构建传入）；未命中进 unmapped 池（spec：不静默丢弃）。
    tier：required ≥0.6 / optional 0.2-0.6 / contextual <0.2（按「节出现次数/该节切片数」）。"""
    from collections import defaultdict
    sec_hits: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    sec_reports: dict[tuple, set] = defaultdict(set)
    unmapped: list[dict] = []
    for si in seg_infos:
        key = (si["chapter"], si["sec"], si["title"])
        sec_reports[key].add(si["rid"])
        for m in QUANTITY_RE.finditer(si["text"]):
            label, value, unit = m.group(1), m.group(2), m.group(3)
            field = forms_label_map.get(label)
            if field:
                sec_hits[key][label].append({"field": field, "value": value, "unit": unit})
            elif len(unmapped) < 200:
                unmapped.append({"section": f"ch{si['chapter']}", "label": label,
                                 "value": value, "unit": unit, "sample": si["rid"]})
    sections = {}
    for key, hits in sec_hits.items():
        ch, sec, title = key
        n = len(sec_reports[key])
        quants = []
        for label, items in hits.items():
            freq = len({it["value"] for it in items}) / max(n, 1)  # 同节不同报告出现比例
            freq = min(freq, 1.0)
            quants.append({"field": items[0]["field"], "caliber": label,
                           "unit": items[0]["unit"],
                           "tier": "required" if freq >= 0.6 else ("optional" if freq >= 0.2 else "contextual"),
                           "corpus_freq": round(freq, 2)})
        quants.sort(key=lambda q: -q["corpus_freq"])
        sections[f"ch{ch}_S{sec.split('.')[-1] or '1'}"] = {"title": title, "expected_quantities": quants}
    return {"version": "1.0", "stage_scope": stage, "generated": generated,
            "sections": sections, "unmapped": unmapped}
```

main 里（forms_catalog 编译后）：

```python
    label_map = {}
    for e in reports:
        # stage json forms: label → "族.name"（对 planning_eia 33 族；跨 stage 同名 label 取先到）
        ...
    expectations = build_section_expectations(sec_infos, label_map, stage=..., generated=...)
    _json_write(refs / "section_expectations.json", expectations)
```

（实现注：label_map 从 **5 个 stage json 合并**构建——`json.loads((refs / "stages" / s).read_text())` 遍历 forms fields：`{f["label"]: f"{fam}.{f['name']}" ...}`；sec_infos 在切片循环收集（`{"rid", "chapter", "sec", "title", "text"}`，sec/title 从 slice_report 的 secs 取）。文件级单份输出（spec §4.2 全局一份，sections 键含章号已可区分）。）

- [ ] **Step 4: 跑通测试；重跑编译生成 `references/section_expectations.json`**
- [ ] **Step 5: 抽 3 节人工核对**（验收项）：抽 planning_eia 的 ch6/ch13 各节，对照对应切片原文核对清单数值——记录核对结论到提交信息
- [ ] **Step 6: 提交**

---

## Task 9: SKILL.md 轻改 + data_expectations GBK 修复

**Files:**
- Modify: `<SKILL>/SKILL.md`
- Modify: `<SKILL>/references/data_expectations.json`（仅编码）

- [ ] **Step 1: SKILL.md 三处轻改**
  1. references 清单节（v1 旧参考段附近）追加一行：`forms_catalog.json`（表格引导句/数值引用/口径消歧三形态正样本库——行文前按节角色取用）与 `section_expectations.json`（节级应引数值清单——写作前对账）
  2. 派发契约（4.1 节）写手纪律处追加一条：**写前对账**——开写一节前，先查 `section_expectations.json` 本节 expected_quantities（tier=required 逐项），与 data/ 现值对账；缺项在节稿对应位置标 `[待确认]（缺项：<字段>）`，不得臆造或四舍五入改写既有值
  3. 行文纪律处追加：数值引用以 `forms_catalog.json` 的 `numeric_citation.templates` 为主形态（「{量}为 {value} {unit}。」），表格引导句以 `table_lead.templates` 为主形态——与既有摆位纪律（标记独立成行）配套
- [ ] **Step 2: data_expectations.json 编码修复**：以 UTF-8 重读全文件，`stage_scope` 字段乱码处按现存结构重写为合法中文描述（内容据 per_chapter 现状归纳，不新增语义）；`python -c "import json; json.load(open(..., encoding='utf-8'))"` 验证通过
- [ ] **Step 3: 门回归**：容器内跑既有 4 个 bug 回归测试确认零退化（命令见 Task 10 Step 3）
- [ ] **Step 4: 提交**

---

## Task 10: 门逻辑系统性测试（build_output 门函数正反用例）

**Files:**
- Test: `<SKILL>/scripts/tests/test_gates_systematic.py`（新建）

**范围**：validate_section 链路的六类门（形状/节题/深度/槽位/残留/摆位）+ assemble 的落号合并——参数化正反用例，覆盖「三轮人修缺陷类」的机器可验形态。签名以 `scripts/build_output.py` 现状为准（写测试前先 `grep -n "^def _validate\|^def validate_section" scripts/build_output.py` 对齐实际函数名与参数，fixture 构造沿用 `test_build_output_bug394.py` 的 `_mk_stage` 模式）。

- [ ] **Step 1: 测试骨架**（用例组：`test_gate_shape_fail` 竖线枚举裂表 FAIL / `test_gate_slot_residue` `{{SLOT:` 残留 FAIL / `test_gate_table_placement` 摆位四例（句中嵌 FAIL×3 形态 + 独立行 PASS）/ `test_gate_caption_merge` 写手表题行合并（已有 bug394 覆盖，此处补「隔空行不合并」反例）/ `test_gate_depth_floor` 章深地板（低于 floor_chars FAIL、达标 PASS）/ `test_gate_section_title` 节题错序 FAIL）
- [ ] **Step 2: 容器内跑全部测试**

Run: `docker cp <SKILL>/scripts/tests pisuan-localized-api-1:/tmp/gatetests && docker exec -w /tmp/gatetests pisuan-localized-api-1 sh -c "cp /app/skill-sources/<挂点>/coal-eia-writer/scripts/*.py . && python -m pytest . -v"`
Expected: 全 PASS（含既有 bug393/394/395/bug3229 回归）

- [ ] **Step 3: 提交**

---

## Task 11: 运行栈同步 + test2 重跑对比验收（执行步骤）

**Files:** 运行时两卷（skill-sources / skill-projections）；test2 工作台 `/tmp/verify394/`（容器）

- [ ] **Step 1: 技能运行时同步**：宿主 `<SKILL>` 整目录 docker cp 到两卷挂点（先探挂点：`docker exec pisuan-localized-api-1 find /app/skill-sources /app/skill-projections -maxdepth 3 -name "coal-eia-writer" -type d 2>/dev/null`），同步后 `docker exec pisuan-localized-api-1 ls <挂点>/references/samples/` 确认切片可见
- [ ] **Step 2: test2 工作台重跑一致性门**：`docker exec pisuan-localized-api-1 python /tmp/verify394/build_output.py --gate-only ...`（复用 bug-394 验收的同款命令形态，data/state 用 test2 副本）
- [ ] **Step 3: 对比告警清单**：验收基准——**SL3 warn 消除**（指纹池就位）；SX2 数值告警数对比记录（section_expectations 是契约面 v1，SX2 不要求机器降级，但须确认新增未引入 NR/摆位误报）；**fail 0 保持**
- [ ] **Step 4: ch6_S05 复验**：以新 SKILL 纪律+期望清单重写一节（同 bug-394 页面验证法），单章门一次过 + 写前对账能暴露缺项
- [ ] **Step 5: changelog 更新**：`docs/develop-guides/changelog.md` 追加本批（schema_linter/prepare_corpus/bank_compile 扩展/新衍生物×2/SKILL 纪律/门测试）；**提交**（含 references 新产物全量入库确认）

---

## Self-Review 结论（计划完成后自检）

- **Spec 覆盖**：spec §2 做 7 项 ↔ Task 1-2（linter）/3-4（prepare_corpus+实跑）/5-8（bank_compile 四步）/9（SKILL+GBK）/10（门测试）/11（同步+验收）；spec §7 验收 8 条 ↔ Task 2 Step 4（N5）/11 Step 3（SL3、fail 0）/6 Step 1（深度基线 diff）/7 Step 5（三节核对）/11 Step 4（ch6_S05）
- **已知简化**（写计划时的显式决策，非占位符）：caliber_disambiguation v1 stats 留空（自动统计误报率高，spec §8 已声明人工补充）；section_expectations 单文件全局输出（spec 允许）；forms_catalog 的 examples 上限 40 条（防产物爆炸）
- **类型一致性**：`_aggregate_depth_targets(refs, stage, generated)` / `build_forms_catalog(seg_samples, generated)` / `build_section_expectations(seg_infos, forms_label_map, stage, generated)` 在测试与实现间一致
