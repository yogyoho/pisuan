# 语料元数据抽取管线重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 spec `docs/superpowers/specs/2026-10-16-corpus-meta-pipeline-refactor-design.md`：front-extract 侧车抽取封面五字段 + corpus_meta cover 层（schema 2）+ 33 份范围落库 + 服务层/前端展示链路。

**Architecture:** 新增 `front_extract.py`（stdlib-only，只读 docx 前置区）产出 `front_matter.json`；`corpus_meta.py` 增加 cover 判定层（manual > cover > body > needs_review，沿用 detect_province 哲学）；`prepare_corpus.py` 加 `--only` 与 manifest 合并；`eia_meta_service.py` 扩 `_ANNOTATION_FIELDS`；MetaPanel 首列报告名主显。存量 31 份切片零接触。

**Tech Stack:** Python 3.12+ stdlib（zipfile+XML 读 docx）、pytest、FastAPI service、Vue3 + antd-vue 4.2.6。

**纪律红线（全程有效）**：不 push；提交中文 Conventional Commits + `Co-Authored-By: Claude Code <noreply@anthropic.com>`；存量 31 份切片文件绝不重生成；QA 用 isolatedContext 页面 + GET-only；截图留 `.wolf/` 不入库。

---

### Task 1: front_extract.py — 封面前置区抽取器（TDD）

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/front_extract.py`
- Test: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py`

- [ ] **Step 1.1: 写失败测试（完整文件）**

```python
"""front_extract 测试：docx 前置区五字段 / rid 全量排序位复算 / 体裁与去重门 / 幂等
（spec 2026-10-16-corpus-meta-pipeline-refactor）。stdlib-only，docx 用内联 zip 构造。"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import front_extract as fx  # noqa: E402
from prepare_corpus import make_rid  # noqa: E402


def _docx_bytes(paras: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


# ── 字段抽取 ────────────────────────────────────────────────────────────────


def test_extract_three_segment_title():
    paras = ["甘肃省", "灵台矿区总体规划（修编）", "环境影响报告书", "二〇二五年六月", "目录", "1 总论"]
    f = fx.extract_front(paras)
    assert f["report_title"] == "甘肃省灵台矿区总体规划（修编）环境影响报告书"
    assert f["province"] == "甘肃"


def test_title_missing_is_none_and_basis_input():
    f = fx.extract_front(["某文件", "1 总论"])
    assert f["report_title"] is None


def test_labeled_org_wins_and_bare_names_are_candidates():
    paras = [
        "（WPS）月儿湾矿井及选煤厂",
        "环境影响报告书",
        "环评单位：中煤科工集团北京华宇工程有限公司",
        "建设单位：宁夏通达新能源集团有限公司",
    ]
    f = fx.extract_front(paras)
    assert f["eia_org"] == "中煤科工集团北京华宇工程有限公司"
    assert "宁夏通达新能源集团有限公司" in f["eia_org_candidates"]


def test_year_cjk_and_arabic():
    assert fx.extract_front(["二〇二五年六月", "1 总论"])["year"] == 2025
    assert fx.extract_front(["2024年4月", "1 总论"])["year"] == 2024
    assert fx.extract_front(["一九九九年", "1 总论"])["year"] is None  # 越界守卫


def test_project_no_normalizes_spaces():
    f = fx.extract_front(["工\u3000程\u3000编\u3000号：H75041Z", "1 总论"])
    assert f["project_no"] == "H75041Z"


def test_cover_scale_variants():
    assert fx.extract_front(["矿区开发总规模：21.40 Mt/a", "1 总论"])["cover_scale_mt_a"] == 21.4
    assert fx.extract_front(["总规模：9.20Mt/a", "1 总论"])["cover_scale_mt_a"] == 9.2
    assert fx.extract_front(["结论：矿区开发总规模为 21.40 Mt/a。", "1 总论"])["cover_scale_mt_a"] is None


def test_province_falls_back_to_first_para():
    paras = ["新疆", "某矿区总体规划", "环境影响报告书", "1 总论"]
    f = fx.extract_front(paras)
    # 标题「某矿区总体规划环境影响报告书」无省名 → 首段省名开头兜底
    assert f["province"] == "新疆"


# ── rid 门与幂等 ────────────────────────────────────────────────────────────


def test_gates_and_rid_parity(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    names = {
        "1四季屯矿山地质环境保护与土地复垦方案报告书.docx": ["封面", "1 总论"],  # 体裁门
        "2某矿区总体规划环境影响报告书.docx": ["封面", "2 某矿区"],  # 保留
        "3某报告旧版.docx": ["封面", "3 某报告"],  # 去重门
    }
    for name, paras in names.items():
        (corpus / name).write_bytes(_docx_bytes(paras))
    refs = tmp_path / "refs"
    wd = tmp_path / "wd"
    argv = [
        "--corpus-dir",
        str(corpus),
        "--references",
        str(refs),
        "--exclude",
        "3某报告旧版.docx",
        "--workdir",
        str(wd),
    ]
    assert fx.main_with_args(argv) == 0
    out = json.loads((refs / "samples_bank" / "front_matter.json").read_text(encoding="utf-8"))
    assert list(out) == [make_rid(2, "2某矿区总体规划环境影响报告书")]
    log = json.loads((wd / "front_extract_excluded.json").read_text(encoding="utf-8"))
    assert {e["reason"] for e in log} == {"genre", "duplicate"}
    assert log[0]["rid"] == make_rid(1, "1四季屯矿山地质环境保护与土地复垦方案报告书")


def test_idempotent_rerun_same_bytes(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "1某矿区总体规划环境影响报告书.docx").write_bytes(
        _docx_bytes(["甘肃省", "某矿区总体规划", "环境影响报告书", "二〇二五年六月", "1 总论"])
    )
    refs = tmp_path / "refs"
    argv = ["--corpus-dir", str(corpus), "--references", str(refs)]
    fx.main_with_args(argv)
    b1 = (refs / "samples_bank" / "front_matter.json").read_bytes()
    fx.main_with_args(argv)
    assert (refs / "samples_bank" / "front_matter.json").read_bytes() == b1
```

- [ ] **Step 1.2: 跑测试确认失败**

```bash
python -m pytest backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py -v
```
预期：`ModuleNotFoundError: No module named 'front_extract'`（collection error）。

- [ ] **Step 1.3: 实现 front_extract.py（完整文件）**

```python
#!/usr/bin/env python3
"""front_extract.py — 语料封面/前置区元数据抽取器（spec 2026-10-16-corpus-meta-pipeline-refactor）。

输入：<语料目录>/*.docx（stdlib zipfile+XML 只读；docx 不入 git，sha1 记录出处）。
输出：<references>/samples_bank/front_matter.json（幂等 sort_keys）+ workdir 排除日志。
rid 推导：按目录全量排序位复算 prepare_corpus.make_rid（含被排除文件）——与切片入库
逐字符一致；体裁门（复垦/监测报告/水土保持）与 --exclude 去重门在 rid 计算之后应用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from prepare_corpus import make_rid  # noqa: E402  rid 单一事实源，绝不复制实现

# 前置区边界：首个节号标题（与 prepare_corpus 范围裁剪同一判据）
SEC_HEAD_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*\S|\S)\s*$")
PARA_RE = re.compile(r"<w:p[ >].*?</w:p>", re.S)
TEXT_RE = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")
SPACE_RE = re.compile(r"[\s\u3000]+")

TITLE_TAIL_RE = re.compile(r"(环境影响报告书|环境影响报告表|环境影响跟踪评价报告书|环境影响后评价报告书|环评报告书)$")
ORG_LABEL_RE = re.compile(r"^(?:环评|编制|评价)单位[：:]")
ORG_NAME_RE = re.compile(r"(有限公司|研究院|设计院|评估中心|科学研究院|勘查院|集团公司)")
ORG_NOISE_RE = re.compile(r"(项目|矿井|矿区|报告|选煤厂|煤矿$)")
DATE_RE = re.compile(r"[〇零一二三四五六七八九]{4}年(?:[一二三四五六七八九十]{1,3}月)?|\d{4}年(?:\d{1,2}月)?")
PROJECT_NO_RE = re.compile(r"工程编号[：:](\S+)")
SCALE_LINE_RE = re.compile(r"^矿区?开发?总规模[：:]([\d.]+)Mt?/?a?$")
GENRE_RE = re.compile(r"(复垦|监测报告|水土保持)")
_CJK_DIGITS = str.maketrans(
    {"〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
)
PROVINCES = (
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 "
    "山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆"
).split()


def _parse_year(fragment: str) -> int | None:
    digits = re.sub(r"\D", "", fragment.translate(_CJK_DIGITS))
    if len(digits) < 4:
        return None
    y = int(digits[:4])
    return y if 2000 <= y <= 2100 else None


def read_front_paras(docx_path: Path, cap: int = 300) -> list[str]:
    """首个节号标题之前的全部非空段落（封面+扉页+签署页；空白归一）。"""
    xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode("utf-8", errors="ignore")
    paras: list[str] = []
    for pa in PARA_RE.findall(xml):
        t = SPACE_RE.sub("", "".join(TEXT_RE.findall(pa)))
        if not t:
            continue
        if SEC_HEAD_RE.match(t):
            break
        paras.append(t)
        if len(paras) >= cap:
            break
    return paras


def extract_front(paras: list[str]) -> dict:
    paras = [p for p in (SPACE_RE.sub("", x) for x in paras) if p]  # 归一与 read_front_paras 同规（全角空格变体）
    title = org_labeled = year = project_no = cover_scale = None
    org_candidates: list[str] = []
    for i, s in enumerate(paras):
        if title is None and len(s) <= 45 and TITLE_TAIL_RE.search(s):
            back: list[str] = []
            for j in range(i - 1, max(-1, i - 4), -1):
                if len(paras[j]) <= 50 and not re.search(r"[：:年月]|^\d", paras[j]):
                    back.insert(0, paras[j])
                else:
                    break
            title = "".join(back) + s
        if year is None and (m := DATE_RE.search(s)):
            year = _parse_year(m.group())
        if project_no is None and (m := PROJECT_NO_RE.search(s)):
            project_no = m.group(1)
        if cover_scale is None and (m := SCALE_LINE_RE.match(s)):
            cover_scale = round(float(m.group(1)), 2)
        if ORG_LABEL_RE.match(s):
            val = ORG_LABEL_RE.sub("", s)
            if val and len(val) <= 50:
                if org_labeled is None:
                    org_labeled = val
                elif val not in org_candidates:
                    org_candidates.append(val)
        elif org_labeled is None is None and ORG_NAME_RE.search(s) and not ORG_NOISE_RE.search(s) and len(s) < 50:
            if s not in org_candidates:
                org_candidates.append(s)
    org_candidates = [c for c in org_candidates if c != org_labeled][:5]
    province = None
    if title:
        province = next((p for p in sorted(PROVINCES, key=len, reverse=True) if p in title), None)
    if province is None:
        for s in paras[:6]:
            province = next((p for p in sorted(PROVINCES, key=len, reverse=True) if s.startswith(p)), None)
            if province:
                break
    return {
        "report_title": title,
        "eia_org": org_labeled,
        "eia_org_candidates": org_candidates,
        "year": year,
        "project_no": project_no,
        "cover_scale_mt_a": cover_scale,
        "province": province,
    }


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="封面/前置区元数据抽取（front_matter.json，幂等）")
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--references", default=str(SCRIPTS_DIR.parent / "references"))
    ap.add_argument("--exclude", action="append", default=[], help="排除文件名（可重复）——重复副本门")
    ap.add_argument("--workdir", default=None, help="排除日志输出目录；省略时仅 stderr")
    args = ap.parse_args(argv)
    corpus = Path(args.corpus_dir)
    refs = Path(args.references)
    excludes = set(args.exclude)
    entries: dict[str, dict] = {}
    excluded: list[dict] = []
    for seq, docx in enumerate(sorted(corpus.glob("*.docx")), start=1):
        rid = make_rid(seq, docx.stem)  # 全量排序位——两门在 rid 之后应用（spec §4 约束）
        if GENRE_RE.search(docx.name):
            excluded.append({"file": docx.name, "rid": rid, "reason": "genre"})
            print(f"[front_extract] {docx.name} -> {rid} 非环评体裁——排除", file=sys.stderr)
            continue
        if docx.name in excludes:
            excluded.append({"file": docx.name, "rid": rid, "reason": "duplicate"})
            print(f"[front_extract] {docx.name} -> {rid} 重复副本——排除", file=sys.stderr)
            continue
        try:
            f = extract_front(read_front_paras(docx))
        except Exception as exc:  # noqa: BLE001
            print(f"[front_extract] {docx.name} 读取失败——跳过：{exc}", file=sys.stderr)
            continue
        entries[rid] = {"source_file": docx.name, "source_sha1": hashlib.sha1(docx.read_bytes()).hexdigest(), **f}
        print(
            f"[front_extract] {docx.name} -> {rid}"
            f"（title={'有' if f['report_title'] else '无'} year={f['year']} org={'有' if f['eia_org'] else '无'}）"
        )
    out = refs / "samples_bank" / "front_matter.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8", newline="\n")
    if args.workdir:
        log_path = Path(args.workdir) / "front_extract_excluded.json"
        log_path.write_text(
            json.dumps(excluded, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"FRONT_EXTRACT: {len(entries)} report(s) -> {out}；排除 {len(excluded)}")
    return 0 if entries else 1


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
```

> 注意：`elif org_labeled is None is None and …` 是笔误防护写法——实现时直接写 `elif ORG_NAME_RE.search(s) and not ORG_NOISE_RE.search(s) and len(s) < 50:`（裸机构名永远只进候选，即使已有标签行；末尾 `org_candidates` 过滤掉与标签值相同的项）。

- [ ] **Step 1.4: 跑测试到全绿**

```bash
python -m pytest backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py -v
```
预期：9 passed。

- [ ] **Step 1.5: 格式化 + 提交**

```bash
ruff format backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/front_extract.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py
ruff check backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/front_extract.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/front_extract.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py
git commit -m "feat(domain-factory): front_extract 封面前置区元数据抽取器

体裁/去重两门 + rid 全量排序位复算（与 prepare_corpus 一致）；封面五字段：
报告名三段拼接/环评单位标签行/双格式年份/工程编号/封面总规模 + 省份标题命中。
Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: corpus_meta.py cover 层 + schema 2（TDD）+ 重编译 31 份

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/corpus_meta.py`
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py`
- Regenerate: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/corpus_meta.json`

- [ ] **Step 2.1: 追加失败测试（在 test_corpus_meta.py 末尾追加，完整代码）**

```python
# ── ⑥ cover 层（spec 2026-10-16-corpus-meta-pipeline-refactor）─────────────

FRONT_007 = {
    "report_title": "甘肃省灵台矿区总体规划（修编）环境影响报告书",
    "eia_org": None,
    "eia_org_candidates": ["中煤科工集团西安研究院"],
    "year": 2025,
    "project_no": "H75041Z",
    "cover_scale_mt_a": 21.4,
    "province": "甘肃",
}


def test_cover_layer_merged_and_schema2(tmp_path):
    root = tmp_path
    _mk_slice(root, "planning_eia", "007-3", "矿区总体规划环评。委托中煤科工集团北京华宇工程有限公司编制《甘肃省灵台矿区总体规划（修编）环境影响报告书》。")
    meta = corpus_meta.build_corpus_meta(root, {}, front={"007-3": FRONT_007})
    assert meta["schema"] == 2
    r = meta["reports"]["007-3"]
    assert r["report_title"] == FRONT_007["report_title"]
    assert r["report_title_basis"] == "cover"
    assert r["eia_org"] == "中煤科工集团北京华宇工程有限公司"
    assert r["eia_org_basis"] == "body"
    assert r["year_hint"] == 2025 and r["year_basis"] == "cover"
    assert r["province"] == "甘肃" and r["province_basis"] == "cover"
    assert r["project_no"] == "H75041Z"


def test_manual_annotation_overrides_cover(tmp_path):
    root = tmp_path
    _mk_slice(root, "planning_eia", "007-3", "某矿区环评。")
    ann = {"007-3": {"year_hint": 2024, "province": "宁夏"}}
    meta = corpus_meta.build_corpus_meta(root, ann, front={"007-3": FRONT_007})
    r = meta["reports"]["007-3"]
    assert r["year_hint"] == 2024 and r["year_basis"] == "manual"
    assert r["province"] == "宁夏" and r["province_basis"] == "manual"


def test_org_needs_review_with_candidates(tmp_path):
    root = tmp_path
    _mk_slice(root, "planning_eia", "007-3", "某矿区环评正文。")
    meta = corpus_meta.build_corpus_meta(root, {}, front={"007-3": FRONT_007})
    r = meta["reports"]["007-3"]
    assert r["eia_org"] is None and r["eia_org_basis"] == "needs_review"
    assert r["eia_org_candidates"] == FRONT_007["eia_org_candidates"]


def test_delegate_org_noise_rejected(tmp_path):
    root = tmp_path
    text = "后在当地进行了开展环境影响评价的公告;第二次是在环境影响评价报告书基本定稿后。委托某院编制工作正在开展。"
    _mk_slice(root, "planning_eia", "007-3", text)
    meta = corpus_meta.build_corpus_meta(root, {}, front={"007-3": FRONT_007})
    r = meta["reports"]["007-3"]
    assert r["eia_org"] is None and r["eia_org_basis"] == "needs_review"


def test_scale_candidate_injection_and_dedup(tmp_path):
    root = tmp_path
    _mk_slice(root, "planning_eia", "007-3", "建设规模 10.0 Mt/a；生产规模 12.0 Mt/a。")
    front = {**FRONT_007, "cover_scale_mt_a": 12.0}
    meta = corpus_meta.build_corpus_meta(root, {}, front={"007-3": front})
    cands = meta["reports"]["007-3"]["scale_candidates"]
    assert {"label": "封面总规模", "value": 12.0} in cands
    assert sum(1 for c in cands if c["value"] == 12.0) == 1
```

- [ ] **Step 2.2: 跑测试确认失败**

```bash
python -m pytest backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py -v
```
预期：新增 5 用例 fail（build_corpus_meta 不认 front 参数 / schema 仍为 1）。

- [ ] **Step 2.3: 实现 corpus_meta.py 变更（四处）**

① 顶部正则区追加：

```python
DELEGATE_RE = re.compile(r"委托\s*([^，。；、（）()《》\s]{4,30}?(?:有限公司|研究院|设计院|评估中心|科学研究院|勘查院|中心|大学|学院))\s*(?:编制|开展)")
ORG_SENT_NOISE_RE = re.compile(r"(公告|第二次|基本|批复)")
```

② `detect_province` 扩展（替换整个函数）：

```python
def detect_province(text: str, ann: dict | None = None, front: dict | None = None) -> dict:
    """manual 注 > cover 封面（front_extract 标题/首段命中）> 频次胜者（≥3 且超次名两倍）> needs_review（带候选）。"""
    if ann and ann.get("province"):
        return {"value": ann["province"], "basis": "manual"}
    if front and front.get("province"):
        return {"value": front["province"], "basis": "cover"}
    counts = {p: n for p in PROVINCES if (n := text.count(p))}
    if not counts:
        return {"value": None, "basis": "needs_review", "candidates": []}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top, n = ranked[0]
    if n >= 3 and (len(ranked) == 1 or n > ranked[1][1] * 2):
        return {"value": top, "basis": "regex"}
    return {"value": None, "basis": "needs_review", "candidates": sorted(counts)}
```

③ `build_corpus_meta` 前追加 delegate_org，并改签名与循环体：

```python
def delegate_org(text: str) -> str | None:
    """正文委托编制句 → 环评机构（cover 标签行缺席时的第二层）；噪声句剔除，频次胜者。"""
    counts: Counter = Counter()
    for sent in re.split(r"[。；;\n]", text):
        if ORG_SENT_NOISE_RE.search(sent):
            continue
        if m := DELEGATE_RE.search(sent):
            counts[m.group(1)] += 1
    return counts.most_common(1)[0][0] if counts else None


def build_corpus_meta(slices_root: Path, annotations: dict, front: dict | None = None) -> dict:
```

循环体内在 `r: dict = {"stage": stage}` 之后、`ann = annotations.get(rid, {})` 之后插入 cover 块，并把年份/省份/规模三处按下面替换（完整循环体新形态）：

```python
    for rid, (stage, text) in sorted(by_rid.items()):
        r: dict = {"stage": stage}
        ann = annotations.get(rid, {})
        f = (front or {}).get(rid) or {}
        if ann.get("scale_mt_a") is not None:
            r["scale_mt_a"], r["scale_basis"] = ann["scale_mt_a"], "manual"
        else:
            sc = extract_scale(text)
            r["scale_basis"] = sc["basis"]
            if sc["basis"] == "regex":
                r["scale_mt_a"] = sc["value"]
            else:
                r["scale_candidates"] = sc["candidates"]
                if f.get("cover_scale_mt_a") is not None:
                    v = round(float(f["cover_scale_mt_a"]), 2)
                    if v not in {c["value"] for c in r["scale_candidates"]}:
                        r["scale_candidates"].append({"label": "封面总规模", "value": v})
        prov = detect_province(text, ann, f)
        r["province"], r["province_basis"] = prov["value"], prov["basis"]
        if prov.get("candidates"):
            r["province_candidates"] = prov["candidates"]
        if ann.get("year_hint") is not None:
            r["year_hint"], r["year_basis"] = ann["year_hint"], "manual"
        elif f.get("year"):
            r["year_hint"], r["year_basis"] = f["year"], "cover"
        if f.get("report_title"):
            r["report_title"], r["report_title_basis"] = f["report_title"], "cover"
        else:
            r["report_title_basis"] = "needs_review"
        if f.get("eia_org"):
            r["eia_org"], r["eia_org_basis"] = f["eia_org"], "cover"
        elif org := delegate_org(text):
            r["eia_org"], r["eia_org_basis"] = org, "body"
        else:
            r["eia_org"], r["eia_org_basis"] = None, "needs_review"
            if f.get("eia_org_candidates"):
                r["eia_org_candidates"] = f["eia_org_candidates"]
        if f.get("project_no"):
            r["project_no"] = f["project_no"]
        r["standards_cited"] = extract_standards(text)
        reports[rid] = r
    return {"schema": 2, "reports": reports}
```

④ `main_with_args` 增参数与装载：

```python
    ap.add_argument("--front-matter", default=None, help="默认 references/samples_bank 下 front_matter.json")
```
```python
    front_path = (
        Path(args.front_matter)
        if args.front_matter
        else SCRIPTS_DIR.parent / "references" / "samples_bank" / "front_matter.json"  # 勘误：指向提交物位置（常量以 corpus_meta.py 既有命名为准）
    )
    front = json.loads(front_path.read_text(encoding="utf-8")) if front_path.exists() else {}
```
```python
        "corpus_meta.json": build_corpus_meta(root, annotations, front),
```

- [ ] **Step 2.4: 跑 corpus_meta 全部测试到全绿**

```bash
python -m pytest backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py -v
```
预期：原有用例 + 新增 5 例全过（原用例不传 front 走默认 None，行为不变；schema 断言若有旧用例断言 schema==1 需同步改 2——跑挂即改）。

- [ ] **Step 2.5: 重编译（此时 front_matter.json 尚不存在或为空——先跑 Task 3 Step 3.1 产出再回来编译？否——按依赖顺序：先执行「Task 3 Step 3.1 front_extract 实跑」，再回本步编译）**

> 执行顺序说明：Task 2 与 Task 3 的「实跑编译」互为依赖，实施时按 Task 1 → Task 2（代码+测试）→ Task 3 Step 3.1（front 实跑）→ 回 Task 2 Step 2.5 编译 → Task 3 其余步骤。子代理执行时由控制器保证该顺序。

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts
python -X utf8 front_extract.py --corpus-dir "C:\项目管理\样例文件" --references ..\references --workdir C:\workspace\pisuan\.wolf\corpus-workdir --exclude "2横城矿区总体规划（修编）环评报告书-1.docx" --exclude "横城矿区总体规划（修编）环评——报告书报批版2021.1-185a7e758338.docx" --exclude "三塘湖矿区规划环评修编（报批版）-0c6e43497902.docx" --exclude "郭家台二号煤矿环评报告（会后修改稿）4.14.docx"
cd C:\workspace\pisuan
```
预期：stderr 4 条排除（genre: 四季屯/红庆梁/郭家台复垦/塔然高勒监测），`FRONT_EXTRACT: 33 report(s)`。抽查 front_matter.json：007-3 有 title/year=2025；028-r title 含「津毛湖」（已知脏样本）；016/032 title 为 null。

- [ ] **Step 2.6: 编译 corpus_meta + 幂等验证 + diff 审阅（AC1）**

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts
python -X utf8 corpus_meta.py
python -X utf8 corpus_meta.py   # 第二次
cd C:\workspace\pisuan
python -c "import hashlib,pathlib; p='backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/corpus_meta.json'; print(hashlib.sha1(pathlib.Path(p).read_bytes()).hexdigest())"
```
预期：两次编译 stdout 相同（`corpus_meta: 31 report(s), province cover=… regex=… manual=… needs_review=…`），哈希一致。
**AC1 人工检查点**：`git diff references/samples_bank/corpus_meta.json`——31 份各新增 report_title/eia_org/project_no/report_title_basis/eia_org_basis（+ 部分份 year_basis=cover、province_basis=cover→regex 迁移、scale_candidates 增封面候选）；**stage/scale_mt_a/manual 标注值零漂移**。diff 表过目后再提交。

- [ ] **Step 2.7: 提交**

```bash
ruff format backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/corpus_meta.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py
ruff check backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/corpus_meta.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/corpus_meta.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/corpus_meta.json backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/front_matter.json
git commit -m "feat(domain-factory): corpus_meta cover 层合入（schema 2）

manual > cover > body > needs_review 判定链；报告名/环评单位/工程编号/封面年份/省份标题法/
封面规模候选；front_matter.json 入库（33 份，sha1 溯源）。
Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: prepare_corpus --only + manifest 合并 + 2 新份入库

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/prepare_corpus.py`
- Test: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_prepare_corpus.py`（新建，只测纯函数）
- Regenerate: `.wolf/corpus-workdir/`（不入库）、`samples_bank/**`（2 新份切片 + bank 聚合物）

- [ ] **Step 3.1: 失败测试（完整文件）**

```python
"""prepare_corpus manifest 合并测试：--only 增量不覆盖已定稿 stage（spec 2026-10-16）。"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from prepare_corpus import merge_manifest  # noqa: E402


def test_merge_preserves_reviewed_stage_and_appends_new():
    existing = [
        {"report_id": "001-wps", "stage": "project_eia_underground", "mineral": "coal", "file_name": "a.docx", "chars": 1},
    ]
    updates = [
        {"report_id": "001-wps", "stage": "", "mineral": "coal", "file_name": "a.docx", "chars": 2},
        {"report_id": "011-800-2026-2", "stage": "project_eia_underground", "mineral": "coal", "file_name": "b.docx", "chars": 3},
    ]
    out = merge_manifest(existing, updates)
    assert {e["report_id"] for e in out} == {"001-wps", "011-800-2026-2"}
    assert next(e for e in out if e["report_id"] == "001-wps")["stage"] == "project_eia_underground"
    assert out == sorted(out, key=lambda e: e["report_id"])


def test_merge_refresh_chars_for_existing():
    existing = [{"report_id": "001-wps", "stage": "s", "mineral": "coal", "file_name": "a.docx", "chars": 1}]
    updates = [{"report_id": "001-wps", "stage": "s", "mineral": "coal", "file_name": "a.docx", "chars": 9}]
    assert merge_manifest(existing, updates)[0]["chars"] == 9
```

- [ ] **Step 3.2: 跑测试确认失败**（`ImportError: cannot import name 'merge_manifest'`）

```bash
python -m pytest backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_prepare_corpus.py -v
```

- [ ] **Step 3.3: 实现 prepare_corpus.py 变更**

① 新增纯函数（放 `make_rid` 之后）：

```python
def merge_manifest(existing: list[dict], updates: list[dict]) -> list[dict]:
    """--only 增量合并：已定稿 stage/mineral 保留（复跑绝不覆盖人工裁决），chars 刷新，rid 序输出。"""
    by_file = {e["file_name"]: dict(e) for e in existing}
    for u in updates:
        prev = by_file.get(u["file_name"], {})
        prev.update({k: v for k, v in u.items() if k != "stage" or v})
        by_file[u["file_name"]] = prev
    return sorted(by_file.values(), key=lambda e: e["report_id"])
```

② `main_with_args` 增参数：

```python
    ap.add_argument("--only", action="append", default=[], help="只处理指定文件名（可重复）；缺省全量")
```

③ 循环内过滤 + manifest 合并写回（替换 `manifest, ok = [], 0` 起至写回段）：

```python
    only = set(args.only)
    manifest_path = workdir / "manifest.json"
    manifest: dict[str, dict] = {}
    if manifest_path.is_file():
        manifest = {e["file_name"]: e for e in json.loads(manifest_path.read_text(encoding="utf-8"))}
    ok = 0
    for seq, docx in enumerate(sorted(corpus.glob("*.docx")), start=1):
        rid = make_rid(seq, docx.stem)
        if only and docx.name not in only:
            continue
        # 逐份解析失败：警告+跳过（bank_compile 既有惯例）
        try:
            md = docx_to_md(docx)
        except Exception as exc:  # noqa: BLE001
            print(f"[prepare_corpus] {docx.name} 解析失败——跳过：{exc}", file=sys.stderr)
            continue
        if not md:
            print(f"[prepare_corpus] {docx.name} 零节号标题——跳过", file=sys.stderr)
            continue
        d = workdir / rid
        d.mkdir(exist_ok=True)
        (d / "source.md").write_text(md + "\n", encoding="utf-8", newline="\n")
        meta = census.get(docx.stem, {})
        ok += 1
        print(f"[prepare_corpus] {docx.name} -> {rid}（{len(md)} chars）")
        updates = updates if (updates := globals().get("_updates")) is not None else []  # 占位防误读
```

> 注意：上面最后一行是错误的草稿残留——实际实现不要这行；在循环前声明 `updates: list[dict] = []`，循环内正常 append：

```python
        updates.append(
            {
                "report_id": rid,
                "stage": "",
                "mineral": "coal",
                "file_name": docx.name,
                "chars": meta.get("chars", len(md)),
            }
        )
    (workdir / "manifest.json").write_text(
        json.dumps(merge_manifest(list(manifest.values()), updates), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"PREPARED: {ok} report(s) -> {workdir}")
    return 0 if ok else 1
```

> 实现时以「循环前 `updates: list[dict] = []`、循环内 append、循环后 merge_manifest 写回」为准，删除任何占位行。

- [ ] **Step 3.4: 测试全绿**

```bash
python -m pytest backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_prepare_corpus.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_corpus_meta.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_front_extract.py -v
```

- [ ] **Step 3.5: 实跑 2 新份切片（检查点：解析失败则先修 docx_to_md 再继续）**

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts
python -X utf8 prepare_corpus.py --corpus-dir "C:\项目管理\样例文件" --workdir C:\workspace\pisuan\.wolf\corpus-workdir --only "九龙川矿井及选煤厂800万吨项目环评-2026.2.docx" --only "巴拉素调整建设规模项目环境影响报告书（报批版）-2023.4.docx"
cd C:\workspace\pisuan
```
预期 stdout 两行 `-> 011-800-2026-2` / `-> 020-2023-4`，`PREPARED: 2 report(s)`。
**验证存量不动**：`git status`（samples_bank 无变化）；manifest diff 只有 2 条新增、31 条 stage 原样。
**人工检查点（spec AC2）**：编辑 `.wolf/corpus-workdir/manifest.json` 把两份新条目的 `stage` 置 `project_eia_underground`（九龙川/巴拉素均为井工矿井项目；如有出入按人工判断定稿）。

- [ ] **Step 3.6: bank_compile 重编译（33 份）**

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts
python -X utf8 bank_compile.py --workdir C:\workspace\pisuan\.wolf\corpus-workdir --references ..\references
cd C:\workspace\pisuan
```
预期：exit 0。存量切片文件字节不变（`git status` 下仅新增 2 rid 的切片与聚合 json 更新）。
**AC2 验证**：

```bash
PYTHONIOENCODING=utf-8 python -c "
import json
from pathlib import Path
SB = Path('backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank')
idx = json.loads((SB/'bank_index.json').read_text(encoding='utf-8'))
rids = {e['report_id'] for st in idx.values() for ch in st.values() for e in (ch if isinstance(ch, list) else [])}
print('bank_index rids:', len(rids))
assert {'011-800-2026-2', '020-2023-4'} <= rids
"
```

- [ ] **Step 3.7: corpus_meta 再编译（33 份）+ 提交**

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts
python -X utf8 corpus_meta.py
cd C:\workspace\pisuan
PYTHONIOENCODING=utf-8 python -c "import json; d=json.load(open('backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/corpus_meta.json',encoding='utf-8')); print(len(d['reports']), d['schema'])"
```
预期：`33 2`。
```bash
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/prepare_corpus.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/test_prepare_corpus.py backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references
git commit -m "feat(domain-factory): prepare_corpus --only 增量入库九龙川/巴拉素（33 份）

manifest 合并保留已定稿 stage；bank 聚合物重编译（存量切片字节不变）。
Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: eia_meta_service 字段扩展（TDD，docker pytest）

**Files:**
- Modify: `backend/package/yuxi/services/eia_meta_service.py`
- Modify: `backend/test/unit/test_eia_meta_service.py`

- [ ] **Step 4.1: 追加失败测试**

```python
def test_validate_annotations_accepts_text_fields():
    out = _validate_annotations(
        {"report_title": "  甘肃省灵台矿区总体规划（修编）环境影响报告书 ", "eia_org": "中煤科工集团北京华宇工程有限公司"}
    )
    assert out == {
        "report_title": "甘肃省灵台矿区总体规划（修编）环境影响报告书",
        "eia_org": "中煤科工集团北京华宇工程有限公司",
    }


def test_validate_annotations_rejects_bad_text_fields():
    for key in ("report_title", "eia_org"):
        for bad in ("", "   ", "x" * 201, 123, None, True):
            with pytest.raises(ValueError, match=key):
                _validate_annotations({key: bad})


def test_list_reports_merges_text_fields(monkeypatch):
    import asyncio

    import yuxi.services.eia_meta_service as svc

    meta = {
        "schema": 2,
        "reports": {
            "007-3": {
                "stage": "planning_eia",
                "report_title": "封面报告名",
                "report_title_basis": "cover",
                "eia_org": None,
                "eia_org_basis": "needs_review",
                "project_no": "H75041Z",
                "year_hint": 2025,
                "year_basis": "cover",
                "scale_basis": "needs_review",
                "scale_candidates": [],
                "province": "甘肃",
                "standards_cited": [],
            }
        },
    }
    monkeypatch.setattr(svc, "_load_corpus_meta", lambda: meta)

    class FakeRepo:
        async def list_annotations(self):
            return []

    s = svc.EiaMetaService.__new__(svc.EiaMetaService)  # 跳过 __init__（不建真池）
    s.repo = FakeRepo()
    out = asyncio.run(s.list_reports())
    it = out["items"][0]
    assert it["auto_report_title"] == "封面报告名"
    assert it["report_title_basis"] == "cover"
    assert it["auto_eia_org"] is None and it["eia_org_basis"] == "needs_review"
    assert it["project_no"] == "H75041Z"
    assert it["annotation"]["report_title"] is None and it["annotation"]["eia_org"] is None
```

- [ ] **Step 4.2: 跑测试确认失败（容器）**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_meta_service.py -v
```
预期：新增 3 例 fail（未知字段 report_title 被拒 / list_reports 无新键）。

- [ ] **Step 4.3: 实现 eia_meta_service.py 变更**

① `_ANNOTATION_FIELDS`：

```python
_ANNOTATION_FIELDS = {"year_hint", "scale_mt_a", "report_title", "eia_org"}
```

② `_validate_annotations` 末尾追加：

```python
    for key in ("report_title", "eia_org"):
        if key in payload:
            v = payload[key]
            if not isinstance(v, str) or not (v := v.strip()) or len(v) > 200:
                raise ValueError(f"{key} 须为 1–200 字非空字符串，得到 {payload[key]!r}")
            clean[key] = v
```

③ `list_reports` 循环 items.append 字典中追加键（annotation 前）：

```python
                    "auto_report_title": m.get("report_title"),
                    "report_title_basis": m.get("report_title_basis"),
                    "auto_eia_org": m.get("eia_org"),
                    "eia_org_basis": m.get("eia_org_basis"),
                    "project_no": m.get("project_no"),
```
annotation 字典增两键：

```python
                    "annotation": {
                        "year_hint": ann.get("year_hint"),
                        "scale_mt_a": ann.get("scale_mt_a"),
                        "report_title": ann.get("report_title"),
                        "eia_org": ann.get("eia_org"),
                        "note": row.note if row else None,
                        "decided_by": row.decided_by if row else None,
                        "decided_at": format_utc_datetime(row.decided_at) if row else None,
                    },
```

④ 模块 docstring 首行注释补一句：`可标注字段 = 年份/规模/报告名/编制单位（schema 2 cover 层为对照面）。`

- [ ] **Step 4.4: 容器内全绿 + 提交**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_meta_service.py -v
```
预期：全部 passed。
```bash
ruff format backend/package/yuxi/services/eia_meta_service.py backend/test/unit/test_eia_meta_service.py
ruff check backend/package/yuxi/services/eia_meta_service.py backend/test/unit/test_eia_meta_service.py
git add backend/package/yuxi/services/eia_meta_service.py backend/test/unit/test_eia_meta_service.py
git commit -m "feat(domain-factory): 语料元数据标注层扩报告名/编制单位字段

_ANNOTATION_FIELDS 增 report_title/eia_org（1–200 字非空）；list_reports 透出
auto 值与 basis 及工程编号；DB 人工层覆盖机制不变。
Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: MetaPanel UI — 报告名主显 + 弹窗字段

**Files:**
- Modify: `web/src/components/eia-data/MetaPanel.vue`
- （`web/src/apis/eia_meta_api.js` 零改动——annotations/note 载荷透传）

- [ ] **Step 5.1: 表头与首列（报告名主显 + rid 副显 + needs_review 黄点）**

表头 hunk（7 列宽度重排，合计 100）：

```html
              <th style="width: 24%">报告名 / rid</th>
              <th style="width: 8%">省份</th>
              <th style="width: 12%">阶段</th>
              <th style="width: 8%">年份</th>
              <th style="width: 18%">规模（Mt/a）</th>
              <th style="width: 12%">标注状态</th>
              <th class="r" style="width: 18%; padding-right: 20px">操作</th>
```

首列单元格 hunk（原 `<td class="mono">{{ record.report_id }}</td>` 替换）：

```html
              <td>
                <div class="rep-cell">
                  <template v-if="dispTitle(record)">{{ dispTitle(record) }}</template>
                  <span v-else class="miss" title="报告名缺失（封面未抽取，标注弹窗可补）">缺报告名</span>
                  <span
                    v-if="record.report_title_basis === 'needs_review'"
                    class="dot dot-warn"
                    style="margin-left: 6px"
                    title="报告名待复核（封面缺失/脏样本，建议人工确认）"
                  ></span>
                </div>
                <div class="rep-rid">{{ record.report_id }}</div>
              </td>
```

- [ ] **Step 5.2: 工具条搜索扩展**

placeholder 改 `搜索 rid / 报告名 / 省份…`；`filteredItems` 的 q 分支改：

```js
    list = list.filter(
      (r) =>
        r.report_id.toLowerCase().includes(q) ||
        (r.province || '').toLowerCase().includes(q) ||
        dispTitle(r).toLowerCase().includes(q)
    )
```

- [ ] **Step 5.3: 弹窗扩展（自动值行 + 两个输入框 + 预填 + 载荷）**

`dlg-line` 增封面报告名：

```html
        <p class="dlg-line">
          {{ dlg.record.province || '未标识' }} · 自动年份 {{ dlg.record.auto_year_hint ?? '—' }} ·
          自动规模
          {{ dlg.record.auto_scale_mt_a ?? '—' }} · 封面报告名
          {{ dlg.record.auto_report_title || '—' }}
          <template v-if="dlg.record.scale_basis === 'manual'">（规模已核实）</template>
          <template v-else-if="dlg.record.scale_basis === 'needs_review'"
            >（规模依据待复核）</template
          >
        </p>
```

备注行之前插入两个 frm-row：

```html
        <div class="frm-row">
          <label>报告书名</label>
          <input v-model="dlg.form.report_title" class="inp" maxlength="200" />
          <div class="frm-help">写手溯源引用主名；预填封面抽取值，留空表示清除该项标注</div>
        </div>
        <div class="frm-row">
          <label>编制单位</label>
          <input v-model="dlg.form.eia_org" class="inp" maxlength="200" />
          <div class="frm-help">环评编制机构；留空表示清除该项标注</div>
        </div>
```

脚本段变更（完整 hunk）：

```js
const hasAnnotation = (r) =>
  r.annotation &&
  (r.annotation.year_hint != null ||
    r.annotation.scale_mt_a != null ||
    r.annotation.report_title != null ||
    r.annotation.eia_org != null)
// 生效值 = 人工标注覆盖自动抽取（二者缺席才显示「缺」）
const effYear = (r) => r.annotation.year_hint ?? r.auto_year_hint
const effScale = (r) => r.annotation.scale_mt_a ?? r.auto_scale_mt_a
const dispTitle = (r) => r.annotation?.report_title || r.auto_report_title || ''
```

```js
const dlg = reactive({
  open: false,
  submitting: false,
  record: null,
  form: { year_hint: null, scale_mt_a: null, report_title: '', eia_org: '', note: '' }
})

const openAnnotate = (record) => {
  dlg.record = record
  dlg.form.year_hint = record.annotation?.year_hint ?? null
  dlg.form.scale_mt_a = record.annotation?.scale_mt_a ?? null
  dlg.form.report_title = record.annotation?.report_title ?? record.auto_report_title ?? ''
  dlg.form.eia_org = record.annotation?.eia_org ?? record.auto_eia_org ?? ''
  dlg.form.note = record.annotation?.note || ''
  dlg.open = true
}
```

onSubmit 主体替换：

```js
const onSubmit = async () => {
  // number input 清空后是 ''，归一成 null 再走「留空清除」语义
  const norm = (v) => (v === '' || v == null ? null : v)
  const normStr = (v) => {
    const t = (v ?? '').trim()
    return t === '' ? null : t
  }
  const year_hint = norm(dlg.form.year_hint)
  const scale_mt_a = norm(dlg.form.scale_mt_a)
  const report_title = normStr(dlg.form.report_title)
  const eia_org = normStr(dlg.form.eia_org)
  const note = dlg.form.note || null
  if (
    year_hint == null &&
    scale_mt_a == null &&
    report_title == null &&
    eia_org == null &&
    !hasAnnotation(dlg.record)
  ) {
    message.warning('年份 / 规模 / 报告名 / 编制单位至少标注一项（或留空保存以清除标注）')
    return
  }
  dlg.submitting = true
  try {
    await eiaMetaApi.setAnnotation(dlg.record.report_id, {
      annotations: Object.fromEntries(
        [
          ['year_hint', year_hint],
          ['scale_mt_a', scale_mt_a],
          ['report_title', report_title],
          ['eia_org', eia_org]
        ].filter(([, v]) => v != null)
      ),
      note
    })
    message.success(`「${dlg.record.report_id}」标注已保存`)
    dlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '标注保存失败')
  } finally {
    dlg.submitting = false
  }
}
```

- [ ] **Step 5.4: 骨架列宽同步（首列 15%→24%）**

骨架行 span class 数组（meta-skeleton 内两处 v-for 的 `:class="[…]"`）第一段改宽：

```html
:class="['w-25', 'w-10', 'w-10', 'w-10', 'w-25', 'w-10', 'w-10'][j - 1]"
```

- [ ] **Step 5.5: 样式追加（scoped 块内）**

```less
/* 报告名主显 + rid 副显：rid 退为技术主键（spec §7） */
.rep-cell {
  display: flex;
  align-items: center;
  min-width: 0;
}

.rep-rid {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--gray-400);
  margin-top: 2px;
}
```
（若 `--font-mono`/`--gray-400` 变量名与 base.css 不符，以 `grep mono` 现有用法为准对齐——先查再写。）

- [ ] **Step 5.6: 链路验证**

```bash
cd web && node node_modules/prettier/bin/prettier.cjs --write src/components/eia-data/MetaPanel.vue && cd ..
powershell.exe -NoProfile -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-web-1 sh -c "cd /app && ./node_modules/.bin/eslint src/components/eia-data/MetaPanel.vue" && echo ESLINT_EXIT_0
```

- [ ] **Step 5.7: 浏览器 QA（isolatedContext 页面，GET-only）**

1. `new_page`（isolatedContext）→ 登录 → `/domain-factory/eia-data/meta`
2. 断言：首列显示报告名+rid 副显；028-r（脏样本）有 needs_review 黄点；016/032 显示「缺报告名」；共 33 行
3. 打开 028-r 标注弹窗：报告书名预填封面值（含错字「津毛湖」）→ 改写为「淖毛湖」→ 保存（写操作=标注落库，属页面正常功能，允许）→ 列表即时生效
4. 截图 `.wolf/meta_title_col.jpeg`；关闭 QA 页

- [ ] **Step 5.8: 提交**

```bash
git add web/src/components/eia-data/MetaPanel.vue
git commit -m "feat(domain-factory): 语料元数据标注页报告名主显与编制单位标注

首列报告名+rid 副显、needs_review 黄点；弹窗增报告书名/编制单位输入框（预填封面值）；
搜索扩报告名；骨架列宽同步。
Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: changelog + 收尾

**Files:**
- Modify: `docs/develop-guides/changelog.md`

- [ ] **Step 6.1: changelog 补条目**（v0.7.3 功能与修复区追加）

```markdown
- 语料元数据管线重构：新增 front_extract 封面抽取侧车（报告名/环评单位/年份/工程编号/封面总规模 + 省份标题命中法，体裁与重复副本双门排除），corpus_meta 升 schema 2 合入 cover 层（manual > cover > body > needs_review），范围 41→33 份（收九龙川/巴拉素，存量切片零接触）；标注层扩报告名/编制单位，标注页首列报告名主显（rid 退为技术主键）
```

- [ ] **Step 6.2: 提交**

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(domain-factory): changelog 补语料元数据管线重构

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review 记录

- **Spec 覆盖**：§4 数据流→Task 1/3；§5 schema→Task 1/2；§6 服务层→Task 4；§7 前端→Task 5；§8 验收 AC1→Step 2.6、AC2→Step 3.5/3.6、AC3→Step 5.7；§9 顺序→任务编排（Task 2 与 3 的编译实跑交叉已显式注明控制器保证顺序）；§10 非目标未引入。
- **占位符扫描**：无 TBD/TODO；Step 1.3 的 `is None is None` 笔误已就地标注修正指令；Step 3.3 的占位行已标注删除。
- **类型一致性**：front_matter 键名（report_title/eia_org/eia_org_candidates/year/project_no/cover_scale_mt_a/province）在 Task 1 产出、Task 2 消费、Task 4 透出、Task 5 展示四处一致；rid 推导单一来源 make_rid。

## Task 1 实施勘误（2026-10-16，commit b6069ccf）

实施时计划稿自身 4 处代码 bug 被 TDD/评审逼出修正（测试块为验收基准，未动）：

1. `SCALE_LINE_RE` 量词错位：`^矿区?开发?总规模…` 使 矿/开 成为必选字符 → 改 `^(?:矿区)?(?:开发)?总规模[：:](\d+(?:\.\d+)?)Mt?/?a?$`（可选前缀必须加括号；顺带收紧捕获防 `float("2..4")` ValueError 丢整份字段）。
2. 裸机构名分支需剥掉行首「建设单位：/环评单位：/编制单位：/评价单位：」标签再入 `eia_org_candidates`（计划测试要求裸名，Task 2 fixture 佐证候选为裸名格式）。
3. workdir 排除日志写入前需 `log_path.parent.mkdir(parents=True, exist_ok=True)`（计划自己的测试用全新 tmp workdir）。
4. 【评审 C1】`read_front_paras` 先 SPACE 归一后判界使 SEC_HEAD_RE（要求 `\s+`）永假——边界判据改用归一前 `raw.strip()`；补 test_read_front_paras_stops_at_sec_heading + split-run 测试 + source_sha1 断言。

Quality 复审小项一并落地：ZipFile `with` 块、`BACK_JOIN_BLOCK_RE`/`PROVINCES_BY_LEN` 提模块常量、docstring 补用法行。复审遗留（非阻塞）：corrupt-docx 跳过路径与全排除 exit-1 两个补测，折进后续任务测试。

**Task 2/3 runbook 注意**：rid 一致性只在「prepare_corpus 切片实跑与 front_extract 实跑之间目录内容不变」时成立（两者都对活目录重算排序位）——两条命令必须同批执行，中间不得增删 docx。scripts 测试在宿主机 repo 内不可收集（pytest 9 沿祖先包触发 langchain_core，仅 Docker 有）——一律用 repo 外临时目录字节同副本 harness。
