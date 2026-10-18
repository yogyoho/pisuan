# 环评文件库 P2：canonical md 正源（方案 B）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 文件库成为 canonical md 正源——上传 docx 即秒级产 canonical md（正文与离线产线 33 份金标准逐字节一致），双消费方 KB（.md 直通推送）与 P2 语料管线（bank_compile 在线重编译）零规则重调接入。

**Architecture:** 新内核模块 `eia_canonical_md`（纯函数，移植技能三脚本）→ 数据层 v19（eia_library_files 扩列 + 台账表）→ 上传流接 MinIO + md 同步产出 → KB 推送走既有 add→parse→index 链（后台任务）→ P2 加工 = temp workdir 物化 + importlib 调 bank_compile 原脚本（零复制实现）→ 路由/前端增量。

**Tech Stack:** python-docx 1.x、MinIO（`yuxi.storage.minio`）、SQLAlchemy async + PG、FastAPI tasker（task_registry）、Vue3 + ant-design-vue（less + base.css 变量）。

**Spec:** `docs/superpowers/specs/2026-10-18-eia-library-p2-canonical-md-design.md`

---

## 契约锚点（已实测 file:line）

| 契约 | 位置 |
|---|---|
| P1 上传流（sha1 查重/命名/落盘） | `backend/package/yuxi/services/eia_library_service.py:49-92` |
| EiaLibraryFile 模型 / to_dict | `models_domain_factory.py:750-779`；仓储 `repositories/eia_library_repository.py` |
| 路由库段 | `server/routers/domain_factory_router.py:1304-1391`（download 用 FileResponse） |
| 迁移模式 v18 | `storage/postgres/manager.py:791-831`；版本号 `manager.py:54`；门 `storage_migration.py:124-193` |
| 任务注册表 | `services/task_registry.py:44-108`；ingest 链样板 `services/knowledge_task_service.py:35-174` |
| KB 推送链 | `knowledge/manager.py:564`（add_file_record）、`:581`（parse_file）、`:605`（index_file）、`:994`（delete_file） |
| add_file_record 参数契约 | `knowledge/utils/kb_utils.py:61-168`：item 必须 MinIO URL（首段∈{knowledgebases, kb-images, public}）；`params.content_hashes[item]` 必填（sha256）；`params.source_path` 覆盖显示名；`content_type:"file"` |
| MinIO 客户端 | `storage/minio/client.py`：`get_minio_client()`，`aupload_file(bucket,object,data,ct)->UploadResult(url,…)`、`adownload_file`、`adelete_file`、`astat_file`；URL 形如 `http://{public_endpoint}/{bucket}/{object}`（client.py:146） |
| 系统配置 KV | `config/options.py:87`（system_options）；`update_option_value` 部分字段合并（options.py:373-391） |
| bank_compile 在线调用 | `scripts/bank_compile.py:449` `main_with_args(argv)`（importlib 调用先例 `eia_data_service.py:88-89`）；`--workdir --references --prune` |
| corpus_meta rid 全集权威 | `services/eia_meta_service.py:79-87`（未知 rid 导入跳过 → 新报告必须合并进 corpus_meta.json） |
| corpus_meta 条目形态 | `references/samples_bank/corpus_meta.json`（reports.{rid}：eia_org/eia_org_basis/project_no/province/province_basis/report_title/report_title_basis/scale_basis/scale_candidates/stage…） |
| docx 病态守卫 | `services/docx_guard.py:128` `guard_docx_bytes(data,label)`（dangling_rels 自动手术） |
| 任务队列入口 | `services/task_service.py` `tasker.enqueue(name, task_type, payload)`；worker 容器执行 |

**金标准实证（2026-10-18，宿主机 33/33 全绿）**：canonical md 正文与 `.wolf/corpus-workdir/<rid>/source.md` 逐字节一致；`extract_front(RAW 前置段落)` 与 `front_matter.json` 同 rid 字段全等；两份悬空关系病态 docx 经 `guard_docx_bytes` 自动修复。验证脚本：`.wolf/corpus-workdir/_front_parity_check.py`（临时件，不入 git）。

## 红线（执行全程有效）

1. **绝不**对运行栈执行 `backend/test/integration/services/test_eia_lexicon_service_flow.py`（会清空 eia_lexicon_entries 表）。
2. 运行栈容器名：`pisuan-localized-api-1` / `pisuan-localized-web-1` / `pisuan-localized-worker-1`；改动到运行栈用 `.\scripts\sync-dev.ps1`；迁移由 `python -m yuxi.storage_migration` 执行（docker-compose.yml:211 专用服务，栈重建时自动跑；热验证可 `docker exec pisuan-localized-api-1 uv run --no-sync --no-dev python -m yuxi.storage_migration`）。
3. 提交信息：中文 Conventional Commits + 结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`；只有用户明示才 push。
4. 管理员凭据 `admin`/`123` 只出现在登录表单，绝不写入文件/提交/报告。生产库严禁 seed。
5. QA 浏览器一律 isolatedContext；GET-only 纪律（刻意的页面功能保存除外）。
6. 截图/临时件留在 `.wolf/`（gitignored）；绝不 `git add .wolf`。
7. 容器测试命令统一 `docker exec pisuan-localized-api-1 pytest /app/test/... -p no:cacheprovider`（跑前先 sync-dev）。

---

### Task 1: canonical md 内核模块

**Files:**
- Create: `backend/package/yuxi/services/eia_canonical_md.py`

移植源（同仓库，逐行复制函数体，禁止"凭记忆重写"）：
- `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/prepare_corpus.py` → `SEC_LINE_RE/TOC_TAIL_RE/SENT_PUNCT_RE/BOOK_MARK_RE/GFM_SEP/is_toc_line/strip_toc/is_policy_conform_title/promote_headings/table_to_gfm/iter_blocks/make_rid`
- `.../scripts/front_extract.py` → `extract_front` 及其私有正则/表（`SPACE_RE/TITLE_TAIL_RE/BACK_JOIN_BLOCK_RE/ORG_LABEL_RE/ORG_NAME_RE/ORG_NOISE_RE/DATE_RE/PROJECT_NO_RE/SCALE_LINE_RE/_CJK_DIGITS/PROVINCES/PROVINCES_BY_LEN/_parse_year`）；`read_front_paras` **不移植**（退役）
- `.../scripts/bank_compile.py` → `SEC_RE/_heading_title/slice_report`

- [ ] **Step 1: 创建模块**（完整内容如下）

```python
"""eia_canonical_md.py — 环评文件库 canonical md 内核（方案 B 正源，纯函数模块）。

docx → canonical md：正文与离线产线 prepare_corpus.docx_to_md 逐字节一致（33 份
金标准回归守护），唯一差异是封面/扉页区保留为前置区 + EIA-FRONT-MATTER-END 标记行。
前置区 RAW 段落喂 extract_front 与技能 front_extract（docx-XML 路径）字段全等
（2026-10-18 宿主机实证 33/33），front_extract.read_front_paras 的 docx zip 直读自此退役。

规则函数逐行移植自技能三脚本（原地保留，离线产线不动）：
  - prepare_corpus.py: strip_toc / promote_headings / table_to_gfm / iter_blocks / make_rid
  - front_extract.py:  extract_front（纯函数部分）
  - bank_compile.py:   slice_report（P2 加工切片计数）
docx 病态守卫复用 yuxi.services.docx_guard（悬空关系手术，bug-355）。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from yuxi.services.docx_guard import guard_docx_bytes

FRONT_MARKER = "<!-- EIA-FRONT-MATTER-END -->"

# ---------------------------------------------------------------- prepare_corpus 移植

SEC_LINE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*\S|\S)\s*$")
TOC_TAIL_RE = re.compile(r"\s\t?\d{1,3}\s*$")
SENT_PUNCT_RE = re.compile(r"[。；，]")  # 句读标点（顿号「、」除外——真标题可含）
BOOK_MARK_RE = re.compile(r"[《》]")
GFM_SEP = "|"


def is_toc_line(line: str) -> bool: ...          # ← prepare_corpus.py:33-38 逐行复制
def strip_toc(text: str) -> str: ...             # ← prepare_corpus.py:41-66 逐行复制
def is_policy_conform_title(number: str, title: str) -> bool: ...  # ← :69-74
def promote_headings(body: str) -> str: ...      # ← :77-100
def table_to_gfm(rows: list[list[str]]) -> str: ...  # ← :103-113
def iter_blocks(doc): ...                        # ← :116-126
def make_rid(seq: int, stem: str) -> str: ...    # ← :154-160


# ---------------------------------------------------------------- front_extract 移植（纯函数部分）

SPACE_RE = re.compile(r"[\s　]+")
TITLE_TAIL_RE = re.compile(r"(环境影响报告书|环境影响报告表|环境影响跟踪评价报告书|环境影响后评价报告书|环评报告书)$")
BACK_JOIN_BLOCK_RE = re.compile(r"[：:年月]|^\d")
ORG_LABEL_RE = re.compile(r"^(?:环评|编制|评价)单位[：:]")
ORG_NAME_RE = re.compile(r"(有限公司|研究院|设计院|评估中心|科学研究院|勘查院|集团公司)")
ORG_NOISE_RE = re.compile(r"(项目|矿井|矿区|报告|选煤厂|煤矿$)")
DATE_RE = re.compile(r"[〇零一二三四五六七八九]{4}年(?:[一二三四五六七八九十]{1,3}月)?|\d{4}年(?:\d{1,2}月)?")
PROJECT_NO_RE = re.compile(r"工程编号[：:](\S+)")
SCALE_LINE_RE = re.compile(r"^(?:矿区)?(?:开发)?总规模[：:](\d+(?:\.\d+)?)Mt?/?a?$")
_CJK_DIGITS = str.maketrans({"〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"})
PROVINCES = (
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 "
    "山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆"
).split()
PROVINCES_BY_LEN = sorted(PROVINCES, key=len, reverse=True)


def _parse_year(fragment: str) -> int | None: ...  # ← front_extract.py:63-68 逐行复制
def extract_front(paras: list[str]) -> dict: ...   # ← front_extract.py:89-136 逐行复制


# ---------------------------------------------------------------- bank_compile 移植（切片内核）

SEC_RE = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\s", re.MULTILINE)


def _heading_title(line: str) -> str: ...        # ← bank_compile.py:105-108 逐行复制
def slice_report(text: str) -> tuple[list[dict], list[str]]: ...  # ← bank_compile.py:111-157 逐行复制


# ---------------------------------------------------------------- 本模块新逻辑

@dataclass(frozen=True)
class CanonicalMd:
    """canonical md 产物：md 全文（前置区+标记+正文）、RAW 前置段落、字符数。"""

    md: str
    front_paras: list[str]
    chars: int


def docx_bytes_to_canonical_md(data: bytes, label: str = "") -> CanonicalMd | None:
    """docx bytes → canonical md；零节号标题返回 None（调用方记 md_status=failed）。

    前置段落走 RAW 变体（与 front_extract.read_front_paras 逐字符同构）：
    python-docx 块序、含表格单元段落、不做 NFKC、cap=300——extract_front 内部
    自做 SPACE 归一，故与技能金标准字段全等（33/33 实证）。
    病态 docx 经 guard_docx_bytes（悬空关系自动手术）；不可救病类 ValueError 透出。
    """
    from docx import Document
    from io import BytesIO

    guarded = guard_docx_bytes(data, label)
    doc = Document(BytesIO(guarded))
    parts: list[str] = []
    raw_paras: list[str] = []
    boundary_hit = False
    for block in iter_blocks(doc):
        if block.__class__.__name__ == "Paragraph":
            t = unicodedata.normalize("NFKC", block.text).strip()
            if t:
                parts.append(t)
            if not boundary_hit and len(raw_paras) < 300:
                raw = block.text.strip()
                if raw:
                    if SEC_LINE_RE.match(raw):
                        boundary_hit = True
                    else:
                        raw_paras.append(raw)
        else:
            rows = [[c.text for c in row.cells] for row in block.rows]
            gfm = table_to_gfm(rows)
            if gfm:
                parts.append(gfm)
            if not boundary_hit:
                for row in block.rows:
                    for cell in row.cells:
                        t = cell.text.strip()
                        if t and len(raw_paras) < 300:
                            raw_paras.append(t)
    # 先剔目录后升标题：与 prepare_corpus.docx_to_md 完全一致（bug-398 A1 顺序约束）
    text = promote_headings(strip_toc("\n\n".join(parts)))
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#") and SEC_LINE_RE.match(ln.lstrip("#").strip()):
            front_lines = [x for x in lines[:i] if x.strip()]
            body = "\n".join(lines[i:])
            head = ("\n\n".join(front_lines) + "\n\n") if front_lines else ""
            md = f"{head}{FRONT_MARKER}\n\n{body}\n"
            return CanonicalMd(md=md, front_paras=raw_paras, chars=len(md))
    return None


def split_canonical_md(md: str) -> tuple[list[str], str]:
    """canonical md → (前置区非空行, 正文含末换行)；正文即 source.md 等价物。"""
    _, _, body = md.partition(FRONT_MARKER)
    body = body.lstrip("\n")
    front = [ln for ln in md.partition(FRONT_MARKER)[0].splitlines() if ln.strip()]
    return front, body
```

> 执行注：`...` 处必须逐行复制源脚本函数体（本计划不给转述版，防转录漂移；源码就在仓库内）。

- [ ] **Step 2: 语法与导入验证**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/eia_canonical_md.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add backend/package/yuxi/services/eia_canonical_md.py
git commit -m "feat(domain-factory): canonical md 内核模块（方案 B 正源，移植技能三脚本）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 内核单测（合成 docx，容器跑）

**Files:**
- Test: `backend/test/unit/services/test_eia_canonical_md.py`

- [ ] **Step 1: 写测试**（合成 docx 夹具，不依赖真实语料）

```python
from __future__ import annotations

import pytest
from docx import Document

from yuxi.services.eia_canonical_md import (
    FRONT_MARKER,
    docx_bytes_to_canonical_md,
    extract_front,
    make_rid,
    slice_report,
    split_canonical_md,
)


def _docx_bytes(cover: list[str], toc: list[str], body: list[str], table: list[list[str]] | None = None) -> bytes:
    """合成 docx：封面段 + 目录行（≥3 触发剔除）+ 正文节号标题 + 可选表格。"""
    doc = Document()
    for t in cover:
        doc.add_paragraph(t)
    for t in toc:
        doc.add_paragraph(t)
    if table is not None:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for i, row in enumerate(table):
            for j, cell in enumerate(row):
                t.rows[i].cells[j].text = cell
    for t in body:
        doc.add_paragraph(t)
    import io

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


COVER = ["某煤矿矿井及选煤厂项目", "环境影响报告书", "工程编号：H95011-2-BG", "二〇二四年三月"]
TOC = ["1 概述\t1", "2 场址与地质\t5", "3 环境影响分析\t12"]
BODY = ["1 概述", "项目背景与内容。", "2.1 地质特征", "构造简单。", "3.2.1 与《宁夏十四五规划》的符合性分析", "符合。"]


def test_canonical_md_body_marker_and_toc_strip():
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY), label="t.docx")
    assert cm is not None
    front, body = split_canonical_md(cm.md)
    assert FRONT_MARKER in cm.md
    assert not any("\t1" in ln or "\t5" in ln for ln in body)  # 目录区段已剔
    assert body.startswith("# 1 概述")  # 首个节号标题起为正文
    assert cm.md.endswith("\n")


def test_canonical_md_heading_promotion_and_policy_exempt():
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY), label="t.docx")
    _, body = split_canonical_md(cm.md)
    assert "### 2.1 地质特征" in body  # 两段号 → ###
    assert "#### 3.2.1 与《宁夏十四五规划》的符合性分析" in body  # 书名号豁免（题名>30字）


def test_canonical_md_front_paras_raw_and_table_cells():
    table = [["建设单位", "某矿业有限公司"], ["编制单位", "某环科院"]]
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY, table), label="t.docx")
    assert "某煤矿矿井及选煤厂项目" in cm.front_paras
    assert "某矿业有限公司" in cm.front_paras  # 封面表格单元段进入 RAW 前置段


def test_canonical_md_zero_heading_returns_none():
    cm = docx_bytes_to_canonical_md(_docx_bytes(["只有封面没有正文"], [], []), label="t.docx")
    assert cm is None


def test_extract_front_from_raw_paras():
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY), label="t.docx")
    f = extract_front(cm.front_paras)
    assert f["project_no"] == "H95011-2-BG"
    assert f["year"] == 2024
    assert f["report_title"].endswith("环境影响报告书")


def test_slice_report_merges_subsections():
    text = "# 1 概述\n甲。\n## 1.1 背景\n乙。\n## 2 现状\n丙。\n"
    kept, dup = slice_report(text)
    assert [s["chapter"] for s in kept] == ["1", "2"]
    assert "## 1.1 背景" in kept[0]["seg"]  # 子节归父片
    assert dup == []


def test_make_rid_ascii_slug_and_fallback():
    assert make_rid(1, "plain-stem") == "001-plain-stem"
    assert make_rid(2, "纯中文名") == "002-r"
    assert make_rid(3, "a" * 100) == ("003-" + "a" * 56)
```

- [ ] **Step 2: sync-dev 后容器跑**

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_canonical_md.py -p no:cacheprovider -v
```
Expected: 7 passed

- [ ] **Step 3: 提交**

```bash
git add backend/test/unit/services/test_eia_canonical_md.py
git commit -m "test(domain-factory): canonical md 内核合成 docx 单测

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 金标准回归（宿主机，33 份真实语料）

**Files:**
- Test: `backend/test/unit/services/test_eia_canonical_md_goldens.py`

- [ ] **Step 1: 写测试**（语料/workdir 路径参数化，缺环境 skip）

```python
"""金标准回归：canonical md 正文 == 离线 workdir source.md（逐字节）；
extract_front(前置段落) == 技能 front_matter.json 同 rid 字段；
slice_report 切片章号集 == bank_index.json 同 rid 章号集。

仅开发机可跑（语料与 workdir 不入 git）；缺环境 pytest.skip 显式声明。宿主机运行：
  python -X utf8 -m pytest backend/test/unit/services/test_eia_canonical_md_goldens.py -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from yuxi.services.eia_canonical_md import (
    docx_bytes_to_canonical_md,
    extract_front,
    slice_report,
)

WORKDIR = Path(os.environ.get("EIA_GOLDENS_WORKDIR", r"C:\workspace\pisuan\.wolf\corpus-workdir"))
CORPUS = Path(os.environ.get("EIA_GOLDENS_CORPUS", r"C:\项目管理\样例文件"))
SKILL_REFS = Path(
    r"C:\workspace\pisuan\backend\package\yuxi\agents\skills\buildin\coal-eia-writer\references"
)

pytestmark = pytest.mark.skipif(
    not (WORKDIR / "manifest.json").is_file() or not CORPUS.is_dir(),
    reason="金标准环境缺失（EIA_GOLDENS_WORKDIR/EIA_GOLDENS_CORPUS）",
)


def _manifest():
    return json.loads((WORKDIR / "manifest.json").read_text(encoding="utf-8"))


def _front_matter():
    return json.loads((SKILL_REFS / "samples_bank" / "front_matter.json").read_text(encoding="utf-8"))


def _bank_index():
    return json.loads((SKILL_REFS / "samples_bank" / "bank_index.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", _manifest(), ids=lambda e: e["report_id"])
def test_golden_entry(entry):
    rid, fname = entry["report_id"], entry["file_name"]
    src = CORPUS / fname
    if not src.is_file():
        pytest.skip(f"语料缺失: {fname}")
    cm = docx_bytes_to_canonical_md(src.read_bytes(), label=fname)
    assert cm is not None, f"{rid} 零节号标题"

    # ① 正文逐字节 == workdir source.md
    golden_body = (WORKDIR / rid / "source.md").read_text(encoding="utf-8")
    from yuxi.services.eia_canonical_md import split_canonical_md

    _, body = split_canonical_md(cm.md)
    assert body == golden_body, f"{rid} 正文漂移"

    # ② extract_front == front_matter.json 同 rid
    golden_front = _front_matter().get(rid)
    if golden_front is not None:
        f = extract_front(cm.front_paras)
        for field in ("report_title", "eia_org", "eia_org_candidates", "year", "project_no", "cover_scale_mt_a", "province"):
            assert f.get(field) == golden_front.get(field), f"{rid}.{field}: {f.get(field)!r} != {golden_front.get(field)!r}"

    # ③ slice_report 章号集 == bank_index.json 同 rid
    golden_index = _bank_index().get(entry["stage"], {})
    expected_chs = sorted({item["file"].rsplit("/", 1)[-1].rsplit("__", 1)[1].split(".")[0]
                            for files in golden_index.values() for item in files
                            if rid in item["file"]})
    if expected_chs:
        kept, _dup = slice_report(body)
        assert sorted(s["chapter"] for s in kept) == expected_chs, f"{rid} 章号集漂移"
```

- [ ] **Step 2: 宿主机跑**

```bash
python -X utf8 -m pytest backend/test/unit/services/test_eia_canonical_md_goldens.py -v
```
Expected: 33 passed（缺语料环境则 skipped 并显式声明）

- [ ] **Step 3: 提交**

```bash
git add backend/test/unit/services/test_eia_canonical_md_goldens.py
git commit -m "test(domain-factory): canonical md 33 份金标准回归（正文/前置/切片三断言）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 数据层 v19（扩列 + 台账表 + 迁移）

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py:750-779`（EiaLibraryFile 扩列 + 新表 EiaCorpusProcessLog）
- Modify: `backend/package/yuxi/storage/postgres/manager.py:54`（版本 18→19）+ `:831` 后（upgrade_business_v18_to_v19）
- Modify: `backend/package/yuxi/storage_migration.py:141`（upgrade_from 补 18）+ `:193` 后（v19 门）

- [ ] **Step 1: 模型扩列**（EiaLibraryFile 新列；stored_path 转遗留）

```python
class EiaLibraryFile(Base):
    """Domain Factory - 环评文件库文件（P2 起 canonical md 正源；content_sha1 全库唯一）"""

    __tablename__ = "eia_library_files"
    __table_args__ = (
        Index("ix_eia_library_files_folder", "folder_id"),
        Index("ux_eia_library_files_report_id", "report_id", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_id = Column(Integer, ForeignKey("eia_library_folders.id"), nullable=True)  # NULL = 未归类
    original_filename = Column(String(500), nullable=False)
    stored_path = Column(String(1000), nullable=True)  # [遗留] P1 本地卷相对名；v19 起新行仅作展示安全名
    content_sha1 = Column(String(40), nullable=False, unique=True)
    size_bytes = Column(BigInteger, nullable=False)
    content_type = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="stored")
    uploaded_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    # ---- P2 canonical md 正源（spec 2026-10-18 D1/D5/D6）----
    object_key = Column(String(500), nullable=True)  # MinIO 源文件定位（knowledgebases 桶内）；NULL=未迁移存量
    md_object_key = Column(String(500), nullable=True)  # canonical md 定位；NULL=未产出
    md_status = Column(String(20), nullable=False, default="pending_backfill")  # ready/failed/not_applicable/pending_backfill
    md_chars = Column(Integer, nullable=True)
    md_sha1 = Column(String(40), nullable=True)  # md 内容 sha1（KB 重推变更判定锚）
    md_failed_reason = Column(String(500), nullable=True)
    front_meta = Column(JSON, nullable=True)  # extract_front 七字段（上传时抽取，加工时并 corpus_meta.json）
    report_id = Column(String(80), nullable=True)  # rid（D6：bootstrap 保留人工裁决；新上传 make_rid(id, stem)）
    stage = Column(String(50), nullable=True)  # 加工前置（bank_compile manifest 语义）
    mineral = Column(String(50), nullable=True)  # 缺省 coal
    kb_id = Column(String(30), nullable=True)
    kb_file_id = Column(String(100), nullable=True)
    kb_status = Column(String(30), nullable=True)  # pushed/parsing/indexing/indexed/failed
    pushed_at = Column(DateTime, nullable=True)
    push_error = Column(String(1000), nullable=True)
    processed_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "folder_id": self.folder_id,
            "original_filename": self.original_filename,
            "stored_path": self.stored_path,
            "content_sha1": self.content_sha1,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "status": self.status,
            "uploaded_by": self.uploaded_by,
            "created_at": format_utc_datetime(self.created_at),
            "object_key": self.object_key,
            "md_status": self.md_status,
            "md_chars": self.md_chars,
            "report_id": self.report_id,
            "stage": self.stage,
            "mineral": self.mineral,
            "kb_id": self.kb_id,
            "kb_status": self.kb_status,
            "pushed_at": format_utc_datetime(self.pushed_at),
            "push_error": self.push_error,
            "processed_at": format_utc_datetime(self.processed_at),
        }


class EiaCorpusProcessLog(Base):
    """Domain Factory - P2 加工台账（slice/recompile/kb_push/bootstrap/migrate）"""

    __tablename__ = "eia_corpus_process_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, nullable=True)  # 批量/全库动作为 NULL
    content_sha1 = Column(String(40), nullable=True)
    action = Column(String(30), nullable=False)
    detail = Column(JSON, nullable=True)  # 产物摘要（切片数/rid/任务 id 等）
    operator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
```

> `JSON` 从 sqlalchemy 已有导入方式对齐该文件现状（查看文件头既有 import；该文件其它模型如已用 JSON 则沿用）。

- [ ] **Step 2: 迁移函数**（manager.py，紧跟 upgrade_business_v17_to_v18 之后；对照 v18 模板）

```python
    async def upgrade_business_v18_to_v19(self) -> None:
        """[pisuan-custom] v19：环评文件库 P2 扩列 + 加工台账表（canonical md 正源）。

        create_all 只补新表不补列，存量行逐列显式 ALTER（IF NOT EXISTS 幂等）；
        stored_path 转 nullable（本地卷语义退役，spec D1）；report_id 唯一索引（D6）。
        """
        self._check_initialized()
        async with self.async_engine.begin() as conn:
            version = await conn.scalar(
                text(f"SELECT version FROM {SCHEMA_VERSION_TABLE} WHERE domain = 'business' FOR UPDATE")
            )
            if version == 19:
                return
            if version not in (None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18):
                raise RuntimeError(f"Unsupported business schema version: {version}")
            statements = [
                "ALTER TABLE eia_library_files ALTER COLUMN stored_path DROP NOT NULL",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS object_key VARCHAR(500)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS md_object_key VARCHAR(500)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS md_status VARCHAR(20) NOT NULL DEFAULT 'pending_backfill'",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS md_chars INTEGER",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS md_sha1 VARCHAR(40)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS md_failed_reason VARCHAR(500)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS front_meta JSON",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS report_id VARCHAR(80)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS stage VARCHAR(50)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS mineral VARCHAR(50)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS kb_id VARCHAR(30)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS kb_file_id VARCHAR(100)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS kb_status VARCHAR(30)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMP",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS push_error VARCHAR(1000)",
                "ALTER TABLE eia_library_files ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP",
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_eia_library_files_report_id ON eia_library_files (report_id)",
            ]
            for statement in statements:
                await conn.execute(text(statement))
            await conn.run_sync(
                lambda sync_conn: DomainFactoryBase.metadata.create_all(
                    sync_conn, tables=[EiaCorpusProcessLog.__table__]
                )
            )
            await conn.execute(
                text(f"""
                    INSERT INTO {SCHEMA_VERSION_TABLE} (domain, version, applied_at)
                    VALUES ('business', 19, CURRENT_TIMESTAMP)
                    ON CONFLICT (domain) DO UPDATE SET version = 19, applied_at = EXCLUDED.applied_at
                """)
            )
```

> 新表/列的模型 import 对齐 manager.py 现状（v18 已 import EiaLibraryFile 等，补 EiaCorpusProcessLog）。

- [ ] **Step 3: 版本与门**（manager.py:54 `BUSINESS_SCHEMA_VERSION = 18` → `19`；storage_migration.py upgrade_from 元组补 `18`，v18 门之后追加）

```python
            # [pisuan-custom] v19：环评文件库 P2 扩列 + 加工台账表（存量库显式补列补表，幂等）
            if business_version in {None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}:
                await pg_manager.upgrade_business_v18_to_v19()
```

- [ ] **Step 4: 验证**（PG 方言迁移无 sqlite 单测先例，在运行栈实证）

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 uv run --no-sync --no-dev python -m yuxi.storage_migration
docker exec pisuan-localized-api-1 python -c "
import asyncio
from yuxi.storage.postgres.manager import pg_manager
async def main():
    pg_manager.initialize()
    async with pg_manager.get_async_session_context() as s:
        v = await s.execute(text(\"SELECT version FROM schema_versions WHERE domain='business'\"))
        print('business version =', v.scalar())
asyncio.run(main())
"
# 再跑一遍迁移验证幂等（rc=0、无异常）
```
Expected: business version = 19；二次执行 rc=0。

- [ ] **Step 5: 提交**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/storage_migration.py
git commit -m "feat(domain-factory): 文件库 P2 数据层 v19（canonical md 扩列 + 加工台账表）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 上传流改造（MinIO 正源 + md 同步产出）

**Files:**
- Modify: `backend/package/yuxi/services/eia_library_service.py`（upload 重写 + delete/download/get_md 扩展）
- Modify: `backend/package/yuxi/repositories/eia_library_repository.py`（update_file 增量更新）

- [ ] **Step 1: 服务层改造**（关键新增/变更；upload 保持 409/413 语义与临时文件清理不变）

常量与导入（模块头）：

```python
from yuxi.config.options import system_options
from yuxi.knowledge.utils.kb_utils import calculate_content_hash
from yuxi.services.eia_canonical_md import CanonicalMd, docx_bytes_to_canonical_md, make_rid, split_canonical_md
from yuxi.storage.minio import get_minio_client

MINIO_BUCKET = "knowledgebases"  # is_minio_url 白名单桶（kb_utils.py:254）；库对象统一 eia-library/ 前缀
```

upload 变更（伪码定位，落在既有 upload 方法内）：

```python
# —— 既有逻辑不动：文件名/folder 校验、write_upload_to_path、sha1、get_file_by_sha1 查重 ——
stored_name = f"{sha1[:12]}__{_safe_filename(original)}"
data = tmp_path.read_bytes()
object_key = f"eia-library/{stored_name}"
await get_minio_client().aupload_file(MINIO_BUCKET, object_key, data, file.content_type)

md_status, md_object_key, md_chars, md_sha1, md_failed_reason, front_meta = "not_applicable", None, None, None, None, None
if original.lower().endswith(".docx"):
    try:
        cm = docx_bytes_to_canonical_md(data, label=original)
    except ValueError as e:
        cm, md_failed_reason = None, str(e)[:500]
    if cm is None:
        md_status, md_failed_reason = "failed", md_failed_reason or "零节号标题"
    else:
        md_object_key = f"eia-library/.canonical/{stored_name}.md"
        md_status, md_chars = "ready", cm.chars
        md_sha1 = hashlib.sha1(cm.md.encode("utf-8")).hexdigest()
        front_meta = extract_front(cm.front_paras)
        await get_minio_client().aupload_file(
            MINIO_BUCKET, md_object_key, cm.md.encode("utf-8"), "text/markdown"
        )

folder = await self.repo.get_folder(folder_id) if folder_id is not None else None  # 既有存在性校验复用其结果
row = EiaLibraryFile(
    ...既有字段...,
    stored_path=stored_name,            # 遗留展示安全名
    object_key=object_key,
    md_object_key=md_object_key, md_status=md_status, md_chars=md_chars,
    md_sha1=md_sha1, md_failed_reason=md_failed_reason, front_meta=front_meta,
    stage=folder.stage_key if folder is not None else None,  # 文件夹 stage_key 作加工默认
    mineral="coal",
)
row = await self.repo.insert_file(row)   # IntegrityError → FileExistsError 语义不变
await self.repo.update_file(row.id, {"report_id": make_rid(row.id, Path(original).stem)})
return (await self.repo.get_file(row.id)).to_dict()
```

> 模块 docstring 的溯源契约补一句：object_key/md_object_key 为 MinIO 正源定位（v19 起）。

新增/变更方法：

```python
async def get_canonical_md(self, file_id: int) -> tuple[EiaLibraryFile, bytes]:
    row = await self.repo.get_file(file_id)
    if row is None or row.md_status != "ready" or not row.md_object_key:
        raise FileNotFoundError("canonical md 不存在")
    return row, await get_minio_client().adownload_file(MINIO_BUCKET, row.md_object_key)

async def regenerate_md(self, file_id: int, operator: str | None) -> dict:
    """重产 canonical md（md_status=failed 行的手工修复动作）。"""
    row = await self.repo.get_file(file_id)
    if row is None:
        raise FileNotFoundError(file_id)
    if not (row.original_filename or "").lower().endswith(".docx") or not row.object_key:
        raise ValueError("仅 docx 且已迁移 MinIO 的文件可重产 md")
    data = await get_minio_client().adownload_file(MINIO_BUCKET, row.object_key)
    ...同 upload 的 md 产出段（抽私有方法 _produce_md(data, stored_name) 复用）...
    await self.repo.update_file(file_id, {...md 字段...})
    return (await self.repo.get_file(file_id)).to_dict()
```

> upload 与 regenerate_md 共用私有 `_produce_md(data: bytes, stored_name: str) -> dict`（返回 md 各字段 + 已 put 对象），两处调用——避免复制 md 产出段。

delete 变更：

```python
await self.repo.delete_file(file_id)
if row.object_key:
    await get_minio_client().adelete_file(MINIO_BUCKET, row.object_key)
if row.md_object_key:
    await get_minio_client().adelete_file(MINIO_BUCKET, row.md_object_key)
else:  # 存量未迁移行：本地卷清理（迁移完成后自然绝迹）
    (self.storage_root / row.stored_path).unlink(missing_ok=True)
```

download 变更：返回 `(row, Path | bytes)` 联合——object_key 行走 `adownload_file`，路由层据此选 FileResponse 或 Response(bytes)。

- [ ] **Step 2: 仓储 update_file**

```python
async def update_file(self, file_id: int, fields: dict) -> EiaLibraryFile | None:
    """白名单字段增量更新（md/kb/加工/rid 元数据）。"""
    allowed = {
        "object_key", "md_object_key", "md_status", "md_chars", "md_sha1", "md_failed_reason",
        "front_meta", "report_id", "stage", "mineral",
        "kb_id", "kb_file_id", "kb_status", "pushed_at", "push_error", "processed_at",
    }
    fields = {k: v for k, v in fields.items() if k in allowed}
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(EiaLibraryFile, file_id)
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        await session.commit()
        return row
```

- [ ] **Step 3: 单测**（既有 `backend/test/unit/test_eia_library_service.py` 模式：内存桩仓储 + monkeypatch MinIO/docx 生成）

在既有测试文件追加（模式对照既有用例的桩仓储写法）：

```python
def _fake_minio(monkeypatch):
    store = {}

    class FakeUploadResult:
        def __init__(self, url):
            self.url = url

    class FakeClient:
        public_endpoint = "minio:9000"
        async def aupload_file(self, bucket, obj, data, ct=None):
            store[obj] = bytes(data); return FakeUploadResult(f"http://minio:9000/{bucket}/{obj}")
        async def adownload_file(self, bucket, obj):
            if obj not in store: raise FileNotFoundError(obj)
            return store[obj]
        async def adelete_file(self, bucket, obj):
            store.pop(obj, None); return True
        async def astat_file(self, bucket, obj):
            return len(store[obj]) if obj in store else None

    monkeypatch.setattr("yuxi.services.eia_library_service.get_minio_client", lambda: FakeClient())
    return store


def _docx_upload(service, monkeypatch, name="demo.docx"):
    ...合成 docx bytes（复用 Task 2 的 _docx_bytes 或内联简化版），构造 UploadFile 样板（对照既有用例）...


@pytest.mark.asyncio
async def test_upload_docx_produces_canonical_md_and_rid(monkeypatch):
    _fake_minio(monkeypatch)
    service = _service_with_stub_repo(monkeypatch)
    row = await service.upload(_upload_file("样例报告.docx", _docx_bytes()), None, "tester")
    assert row["md_status"] == "ready" and row["md_chars"] > 0
    assert row["report_id"].startswith("001-")  # make_rid(id, stem)
    assert row["md_status"] != "pending_backfill"


@pytest.mark.asyncio
async def test_upload_non_docx_not_applicable(monkeypatch):
    _fake_minio(monkeypatch)
    service = _service_with_stub_repo(monkeypatch)
    row = await service.upload(_upload_file("说明.pdf", b"%PDF-1.4"), None, "tester")
    assert row["md_status"] == "not_applicable"


@pytest.mark.asyncio
async def test_upload_md_failure_keeps_registration(monkeypatch):
    _fake_minio(monkeypatch)
    monkeypatch.setattr("yuxi.services.eia_library_service.docx_bytes_to_canonical_md", lambda *a, **k: None)
    service = _service_with_stub_repo(monkeypatch)
    row = await service.upload(_upload_file("坏文档.docx", _docx_bytes()), None, "tester")
    assert row["md_status"] == "failed" and "零节号标题" in row["md_failed_reason"]  # 登记照记
```

> 桩仓储需含 `update_file`；既有桩文件里补最小实现。

- [ ] **Step 4: 容器跑 + 提交**

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_library_service.py -p no:cacheprovider -v
git add backend/package/yuxi/services/eia_library_service.py backend/package/yuxi/repositories/eia_library_repository.py backend/test/unit/test_eia_library_service.py
git commit -m "feat(domain-factory): 上传流接 MinIO 正源 + canonical md 同步产出

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 存量迁移（本地卷 → MinIO）+ md 回填

**Files:**
- Modify: `backend/package/yuxi/services/eia_library_service.py`（`migrate_storage_to_minio`）
- Modify: `backend/server/routers/domain_factory_router.py`（admin 端点，库段末尾）

- [ ] **Step 1: 服务方法**

```python
async def migrate_storage_to_minio(self, operator: str | None) -> dict:
    """存量本地卷文件一次性迁移：put MinIO → sha1 校验 → 回填 object_key → 重产 md。

    幂等：object_key 已置的行跳过；本地文件缺失的行 stderr 式记入 result 并跳过。
    """
    client = get_minio_client()
    migrated, failed, md_ready = [], [], 0
    for row in await self.repo.list_files():
        if row.object_key:
            continue
        local = self.storage_root / row.stored_path
        if not local.is_file():
            failed.append({"id": row.id, "reason": f"本地文件缺失: {row.stored_path}"})
            continue
        data = local.read_bytes()
        if hashlib.sha1(data).hexdigest() != row.content_sha1:
            failed.append({"id": row.id, "reason": "sha1 不符，拒绝迁移"})
            continue
        object_key = f"eia-library/{row.stored_path}"
        await client.aupload_file(MINIO_BUCKET, object_key, data, row.content_type)
        fields = {"object_key": object_key, "md_status": "pending_backfill"}
        if (row.original_filename or "").lower().endswith(".docx"):
            md = self._produce_md(data, row.stored_path)  # Task 5 私有方法
            fields.update(md)
            if md.get("md_status") == "ready":
                md_ready += 1
        await self.repo.update_file(row.id, fields)
        migrated.append({"id": row.id, "object_key": object_key})
    await self._log(action="migrate", detail={"migrated": migrated, "failed": failed}, operator=operator)
    return {"migrated": len(migrated), "md_ready": md_ready, "failed": failed}
```

> `_log` = 台账写助手（`repo.insert_process_log(EiaCorpusProcessLog(...))`），Task 6 一并加入仓储。

- [ ] **Step 2: 路由**（domain_factory_router.py 库段末尾，`get_admin_user`）

```python
@domain_factory.post("/eia/library/admin/migrate-storage")
async def migrate_eia_library_storage(current_user: User = Depends(get_admin_user)) -> dict[str, Any]:
    """存量本地卷 → MinIO 一次性迁移（幂等；含 docx md 回填）。"""
    result = await get_eia_library_service().migrate_storage_to_minio(current_user.username)
    return {"success": True, **result}
```

- [ ] **Step 3: 验证 + 提交**

```bash
.\scripts\sync-dev.ps1
# 运行栈实证（存量行数少，直接触发）：
docker exec pisuan-localized-api-1 curl -s -X POST http://localhost:5050/api/domain-factory/eia/library/admin/migrate-storage -H "Authorization: Bearer $TOKEN"
# $TOKEN 取法：curl -s -X POST http://localhost:5050/api/auth/token -d "username=admin&password=123" → .access_token
docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_library_service.py -p no:cacheprovider
git add backend/package/yuxi/services/eia_library_service.py backend/package/yuxi/repositories/eia_library_repository.py backend/server/routers/domain_factory_router.py
git commit -m "feat(domain-factory): 文件库存量本地卷→MinIO 迁移端点（幂等，含 md 回填）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: KB 绑定 Option + 推送任务链（D5 直通）

**Files:**
- Modify: `backend/package/yuxi/config/options.py:87+`（system_options 增字段 `eia_corpus_kb_id`）
- Modify: `backend/package/yuxi/services/task_registry.py`（注册 `eia_corpus_push`）
- Create: `backend/package/yuxi/services/eia_corpus_task_service.py`（推送 handler + 推送核心）
- Test: `backend/test/unit/services/test_eia_corpus_push.py`

- [ ] **Step 1: Option 字段**（system_options.params.fields 追加）

```python
{
    "key": "eia_corpus_kb_id",
    "label": "环评语料知识库 ID",
    "type": "string",
    "default": "",
    "des": "环评文件库 canonical md 推送的目标知识库（kb_xxx）；留空=未绑定",
},
```

- [ ] **Step 2: 推送服务模块**

```python
"""eia_corpus_task_service.py — 环评文件库 P2 后台任务（KB 推送 / 语料加工 / 全库重编译）。

KB 推送走既有公开链（D5 直通）：add_file_record（MinIO URL + content_hashes + source_path
显示名 `<原名>.md`）→ parse_file（.md 原生直读，unified.py:164）→ index_file。
对照样板：knowledge_task_service.run_knowledge_ingest。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from yuxi.config.options import system_options
from yuxi.knowledge.runtime import knowledge_base
from yuxi.repositories.eia_library_repository import EiaLibraryRepository
from yuxi.services.eia_canonical_md import split_canonical_md
from yuxi.services.eia_library_service import MINIO_BUCKET
from yuxi.services.task_service import TaskContext
from yuxi.storage.minio import get_minio_client
from yuxi.utils.logging_config import logger

_repo = EiaLibraryRepository()


async def _resolve_kb_id() -> str:
    config = await system_options.get()
    kb_id = (config.get("eia_corpus_kb_id") or "").strip()
    if not kb_id:
        raise ValueError("未绑定环评语料知识库：请先在文件库「绑定语料知识库」中设置")
    await _ensure_kb_exists(kb_id)
    return kb_id


async def _ensure_kb_exists(kb_id: str) -> None:
    """存在性校验；实际异常类型以 KnowledgeManager.get_database_info 签名为准（抛 KBNotFoundError 则捕获转 ValueError）。"""
    try:
        info = await knowledge_base.get_database_info(kb_id)
    except Exception as exc:  # noqa: BLE001 — 执行时按实际异常类型收窄
        raise ValueError(f"绑定的知识库不存在: {kb_id}") from exc
    if info is None:
        raise ValueError(f"绑定的知识库不存在: {kb_id}")


async def bind_corpus_kb(kb_id: str) -> None:
    """绑定目标 KB（存在性校验）→ system_options.eia_corpus_kb_id 持久化。"""
    await _ensure_kb_exists(kb_id.strip())
    await update_option_value("system_options", {"eia_corpus_kb_id": kb_id.strip()})


def _md_minio_url(object_key: str) -> str:
    client = get_minio_client()
    return f"http://{client.public_endpoint}/{MINIO_BUCKET}/{object_key}"


async def _push_one(row, kb_id: str, operator_id: str | None) -> str:
    """单文件推送；返回终态 kb_status（indexed/failed）。no-op 返回现态。"""
    if row.md_status != "ready" or not row.md_object_key:
        raise ValueError(f"md 不可推送（md_status={row.md_status}）")
    client = get_minio_client()
    md_bytes = await client.adownload_file(MINIO_BUCKET, row.md_object_key)
    md_sha1_now = hashlib.sha1(md_bytes).hexdigest()
    if row.kb_file_id and row.kb_status == "indexed" and md_sha1_now == row.md_sha1:
        return row.kb_status  # 已推送且 md 未变 → no-op

    item = _md_minio_url(row.md_object_key)
    params = {
        "content_type": "file",
        "content_hashes": {item: calculate_content_hash(md_bytes)},
        "file_sizes": {item: len(md_bytes)},
        "source_path": f"{Path(row.original_filename).stem}.md",  # KB 显示名
    }
    if row.kb_file_id and row.kb_status == "indexed" and md_sha1_now != row.md_sha1:
        await knowledge_base.delete_file(kb_id, row.kb_file_id)  # md 已重产 → 替换（删旧登新）

    await _repo.update_file(row.id, {"kb_id": kb_id, "kb_status": "pushed", "push_error": None,
                                     "pushed_at": utc_now_naive()})
    file_meta = await knowledge_base.add_file_record(kb_id, item, params=params, operator_id=operator_id)
    file_id = file_meta["file_id"]
    await _repo.update_file(row.id, {"kb_file_id": file_id, "kb_status": "parsing"})
    await knowledge_base.parse_file(kb_id, file_id, operator_id=operator_id)
    await _repo.update_file(row.id, {"kb_status": "indexing"})
    await knowledge_base.index_file(kb_id, file_id, operator_id=operator_id)
    await _repo.update_file(row.id, {"kb_status": "indexed", "md_sha1": md_sha1_now})
    return "indexed"


async def run_eia_corpus_push(context: TaskContext) -> dict:
    """按 file_ids 推送 canonical md 到绑定 KB（逐文件容错，进度/结果入任务中心）。"""
    payload = context.payload
    file_ids: list[int] = payload["file_ids"]
    operator_id = payload.get("operator_id")
    kb_id = await _resolve_kb_id()
    items = []
    failed = 0
    for i, fid in enumerate(file_ids, 1):
        await context.raise_if_cancelled()
        await context.set_progress(5.0 + (i / len(file_ids)) * 90.0, f"推送 {i}/{len(file_ids)}")
        row = await _repo.get_file(fid)
        if row is None:
            items.append({"file_id": fid, "status": "failed", "error": "文件不存在"})
            failed += 1
            continue
        try:
            status = await _push_one(row, kb_id, operator_id)
            items.append({"file_id": fid, "status": status})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[eia-push] {row.original_filename} 推送失败: {exc}")
            await _repo.update_file(fid, {"kb_status": "failed", "push_error": str(exc)[:1000]})
            items.append({"file_id": fid, "status": "failed", "error": str(exc)})
            failed += 1
    summary = {"kb_id": kb_id, "submitted": len(file_ids), "failed": failed, "items": items}
    await context.set_result(summary)
    await context.set_progress(100.0, f"推送完成，失败 {failed} 个" if failed else "推送完成")
    return summary
```

> imports 补齐：`calculate_content_hash`（kb_utils）、`utc_now_naive`（storage.postgres 既有工具，对照 models_domain_factory 用法）、`update_option_value`（config.options）。`get_database_info` 行为以 manager 实际签名为准（抛 KBNotFoundError 则捕获转 ValueError，见 `_ensure_kb_id` 注）。

- [ ] **Step 3: 注册任务类型**（task_registry.py `_TASK_DEFINITIONS` 追加，注释风格对照 domain_factory 条目）

```python
        # [pisuan-custom] 环评文件库 P2 任务：canonical md 推 KB / 语料加工（pisuan 领域扩展）
        TaskDefinition(
            "eia_corpus_push",
            "yuxi.services.eia_corpus_task_service",
            "run_eia_corpus_push",
        ),
```

- [ ] **Step 3b: 单测补绑定用例**（`_resolve_kb_id` 未绑定报错 / bind_corpus_kb 正常持久化与不存在库报错；system_options.get / update_option_value / knowledge_base.get_database_info 全打桩）

- [ ] **Step 4: 单测**（mock knowledge_base + 桩仓储；容器跑）

```python
"""test_eia_corpus_push.py — 推送链单测（no-op/首推/替换/失败镜像）。"""
from __future__ import annotations

import pytest

from yuxi.services import eia_corpus_task_service as svc


class _Row:
    def __init__(self, **kw):
        self.id = 1
        self.original_filename = "样例报告.docx"
        self.md_status = "ready"
        self.md_object_key = "eia-library/.canonical/x.md"
        self.md_sha1 = None
        self.kb_id = None
        self.kb_file_id = None
        self.kb_status = None
        self.__dict__.update(kw)


@pytest.mark.asyncio
async def test_push_noop_when_unchanged(monkeypatch):
    row = _Row(kb_file_id="file_abc", kb_status="indexed", md_sha1="deadbeef")
    called = {"delete": 0, "add": 0}
    async def fake_download(bucket, obj):
        return b"md-bytes"
    import hashlib
    monkeypatch.setattr(svc, "_repo", _FakeRepo(row))
    monkeypatch.setattr(svc, "get_minio_client", lambda: _FakeMinio(fake_download))
    monkeypatch.setattr(svc, "hashlib", hashlib)  # 原模块即 hashlib；此行仅示意保持
    monkeypatch.setattr(svc.knowledge_base, "delete_file", _counting(called, "delete"))
    monkeypatch.setattr(svc.knowledge_base, "add_file_record", _counting(called, "add"))
    status = await svc._push_one(row, "kb_test", "tester")
    assert status == "indexed"
    assert called == {"delete": 0, "add": 0}  # md 未变 → no-op
```

> 同文件补：首推（add→parse→index 全链被调、状态镜像 indexed）、md 变更替换（delete 恰一次）、parse 抛错 → kb_status=failed。`_FakeRepo/_FakeMinio/_counting` 为文件内最小桩。**system_options.get 打桩**返回 `{"eia_corpus_kb_id": "kb_test"}`（测 `_resolve_kb_id` 未绑定报错与正常路径）。

- [ ] **Step 5: 容器跑 + 提交**

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_corpus_push.py -p no:cacheprovider -v
git add backend/package/yuxi/config/options.py backend/package/yuxi/services/task_registry.py backend/package/yuxi/services/eia_corpus_task_service.py backend/test/unit/services/test_eia_corpus_push.py
git commit -m "feat(domain-factory): canonical md 推送 KB 后台任务链（D5 直通，重推幂等）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: P2 加工 + 全库重编译（bank_compile 在线化，零复制）

**Files:**
- Modify: `backend/package/yuxi/services/eia_corpus_task_service.py`（process handler）
- Modify: `backend/package/yuxi/services/task_registry.py`（注册 `eia_corpus_process`）
- Modify: `backend/package/yuxi/repositories/eia_library_repository.py`（`insert_process_log`、`list_ready_for_compile`）
- Test: `backend/test/unit/services/test_eia_corpus_process.py`

- [ ] **Step 1: 加工 handler**（追加到 eia_corpus_task_service.py）

```python
def _load_bank_compile():
    """importlib 动态加载技能脚本（先例：eia_data_service.py:88-89）。"""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "agents" / "skills" / "buildin" / "coal-eia-writer" / "scripts" / "bank_compile.py"
    spec = importlib.util.spec_from_file_location("eia_bank_compile", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _materialize_workdir(tmp: Path, client, rows) -> list[dict]:
    """DB manifest → temp workdir（<rid>/source.md + manifest.json）。"""
    import json

    entries = []
    for row in rows:
        _, body = split_canonical_md((await client.adownload_file(MINIO_BUCKET, row.md_object_key)).decode("utf-8"))
        d = tmp / row.report_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "source.md").write_text(body, encoding="utf-8", newline="\n")
        entries.append({"report_id": row.report_id, "stage": row.stage, "mineral": row.mineral or "coal",
                        "file_name": row.original_filename})
    (tmp / "manifest.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return entries


def _merge_corpus_meta(entries: list[dict], rows) -> None:
    """DB 封面元数据 → 技能 corpus_meta.json reports 合并（新 rid 增量；既有条目不动）。

    eia_meta_service 以 corpus_meta.reports 为 rid 全集权威（eia_meta_service.py:79-87），
    新报告不合并即被 meta 面跳过——此步是加工闭环的必需动作，不是可选物化。
    """
    import json

    meta_path = _SKILL_REFS / "samples_bank" / "corpus_meta.json"
    doc = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {"reports": {}}
    reports = doc.setdefault("reports", {})
    front_by_rid = {r.report_id: (r.front_meta or {}) for r in rows if r.report_id}
    for rid, stage, mineral in entries:
        f = front_by_rid.get(rid, {})
        if rid in reports:
            continue
        reports[rid] = {
            "report_title": f.get("report_title"),
            "report_title_basis": "cover",
            "eia_org": f.get("eia_org"),
            "eia_org_basis": "cover",
            "project_no": f.get("project_no"),
            "province": f.get("province"),
            "province_basis": "cover",
            "year": f.get("year"),
            "cover_scale_mt_a": f.get("cover_scale_mt_a"),
            "scale_basis": "needs_review",
            "scale_candidates": [],
            "stage": stage,
            "mineral": mineral,
        }
    meta_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


_SKILL_REFS = Path(__file__).resolve().parents[1] / "agents" / "skills" / "buildin" / "coal-eia-writer" / "references"


async def run_eia_corpus_process(context: TaskContext) -> dict:
    """P2 加工：校验 → 全库重编译（bank_compile --prune）→ corpus_meta 合并 → 台账。

    payload: {file_ids?: [int], scope?: "all", operator_id}
    校验失败（md 非 ready / stage 未填）→ fail fast 列缺项清单（绝不静默跳过）。
    """
    payload = context.payload
    operator_id = payload.get("operator_id")
    repo = _repo
    if payload.get("scope") == "all":
        targets = [r for r in await repo.list_files() if r.md_status == "ready"]
    else:
        targets = [r for r in (await repo.get_file(f) for f in payload["file_ids"]) if r is not None]

    missing = [f"id={r.id} {r.original_filename}: md_status={r.md_status}" + ("" if r.stage else "，stage 未填")
               for r in targets if r.md_status != "ready" or not r.stage]
    if missing:
        raise ValueError("加工前置不满足：" + "；".join(missing))

    await context.set_progress(10.0, "物化临时 workdir")
    compile_rows = [r for r in await repo.list_files() if r.md_status == "ready" and r.report_id and r.stage]
    bank = _load_bank_compile()
    import tempfile

    with tempfile.TemporaryDirectory(prefix="eia_compile_") as td:
        tmp = Path(td)
        entries = await _materialize_workdir(tmp, get_minio_client(), compile_rows)
        await context.set_progress(40.0, f"bank_compile（{len(entries)} 份，--prune）")
        rc = await asyncio.to_thread(
            bank.main_with_args,
            ["--workdir", str(tmp), "--references", str(_SKILL_REFS), "--prune"],
        )
        if rc != 0:
            raise RuntimeError(f"bank_compile 失败（rc={rc}）：产物保留原状，详见 worker 日志")
    _merge_corpus_meta(
        [(e["report_id"], e["stage"], e["mineral"]) for e in entries],
        compile_rows,
    )
    now = utc_now_naive()
    for r in targets:
        await repo.update_file(r.id, {"processed_at": now})
    await repo.insert_process_log(file_id=None, action="recompile",
                                  detail={"reports": len(entries)}, operator=operator_id)
    summary = {"compiled": len(entries)}
    await context.set_result(summary)
    await context.set_progress(100.0, f"加工完成（{len(entries)} 份入编）")
    return summary
```

> - `main_with_args` 里的 argparse 在非 argv 传参下安全（list 传参即离线 CLI 同路径）。
> - bank_compile rc=1（全零切片拒绝空 bank_index）→ 任务失败、产物保留——spec §5 语义。
> - imports：`asyncio`；`_SKILL_REFS` 与 `eia_data_service._SKILL_ROOT` 同根（可 `from yuxi.services.eia_data_service import _SKILL_ROOT` 复用路径常量，避免第三处硬编码——**首选此法**，`_SKILL_REFS = _SKILL_ROOT / "references"`）。

- [ ] **Step 2: 仓储补充**

```python
async def insert_process_log(self, *, file_id: int | None, action: str, detail: dict | None, operator: str | None) -> None:
    async with pg_manager.get_async_session_context() as session:
        session.add(EiaCorpusProcessLog(file_id=file_id, action=action, detail=detail, operator=operator))
        await session.commit()
```

- [ ] **Step 3: 注册任务类型**（Task 7 的 registry 追加）

```python
        TaskDefinition(
            "eia_corpus_process",
            "yuxi.services.eia_corpus_task_service",
            "run_eia_corpus_process",
        ),
```

- [ ] **Step 4: 单测**（temp workdir 物化 + corpus_meta 合并 + 前置校验 fail fast；bank_compile 以迷你合成 md 走真编译断言 bank_index 产出）

```python
"""test_eia_corpus_process.py — 加工任务单测（合成迷你语料走真 bank_compile）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yuxi.services import eia_corpus_task_service as svc


def _mini_md(title: str) -> str:
    return (
        "封面段\n\n" + svc.FRONT_MARKER  # 占位：FRONT_MARKER 不在 svc 命名空间时应自 eia_canonical_md 导入
        + "\n\n# 1 概述\n内容甲。\n## 1.1 背景\n内容乙。\n# 2 现状\n内容丙。\n"
    )


def test_materialize_workdir_and_real_compile(tmp_path, monkeypatch):
    rows = [_make_row(report_id="001-demo", stage="planning_eia", md=_mini_md("t"))]
    client = _FakeMinio(rows)
    entries = asyncio_run(svc._materialize_workdir(tmp_path / "wd", client, rows))
    assert (tmp_path / "wd" / "001-demo" / "source.md").is_file()
    manifest = json.loads((tmp_path / "wd" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["report_id"] == "001-demo"
    refs = tmp_path / "refs"
    (refs / "stages").mkdir(parents=True)
    # stages/*.json 为 bank_compile label_map 输入，最小夹具参照 references/stages/planning_eia.json 结构（forms.fields[].label/name）
    rc = svc._load_bank_compile.__wrapped__ if False else _run_compile(tmp_path / "wd", refs)
    assert rc == 0
    index = json.loads((refs / "samples_bank" / "bank_index.json").read_text(encoding="utf-8"))
    assert set(index["planning_eia"].keys()) == {"ch1", "ch2"}


def test_merge_corpus_meta_adds_new_rid_only(tmp_path, monkeypatch):
    ...  # _SKILL_REFS 打桩到 tmp_path：预置 reports={"001-old": {...}}，断言新增 001-demo、001-old 原样


def test_process_fails_fast_on_missing_stage(...):
    ...  # stage=None 行 → ValueError 且清单含 "stage 未填"
```

> 执行注：`asyncio_run` 用 `asyncio.run`；`_make_row/_FakeMinio/_run_compile` 为文件内最小桩（`_run_compile` 直接调 `bank.main_with_args([...])`）。测试**不改技能真 references**（`_SKILL_REFS`/`meta_path` 全部 monkeypatch 到 tmp_path）。

- [ ] **Step 5: 容器跑 + 提交**

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_corpus_process.py -p no:cacheprovider -v
git add backend/package/yuxi/services/eia_corpus_task_service.py backend/package/yuxi/services/task_registry.py backend/package/yuxi/repositories/eia_library_repository.py backend/test/unit/services/test_eia_corpus_process.py
git commit -m "feat(domain-factory): P2 语料加工任务（temp workdir 物化 + bank_compile 在线重编译 + corpus_meta 合并）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 路由层（推送/加工/md 预览/元数据/bootstrap）

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（库段末尾追加；导入区补 `tasker`、`eia_corpus_task_service` 按需）

- [ ] **Step 1: 端点**（全部 admin；模式对照既有 409/413 映射与任务化端点 knowledge_router.py:715-757）

```python
@domain_factory.post("/eia/library/files/{file_id}/md")
async def get_eia_library_file_md(file_id: int, current_user: User = Depends(get_required_user)):
    """canonical md 预览（text/markdown）。"""
    try:
        row, data = await get_eia_library_service().get_canonical_md(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="canonical md 不存在")
    return Response(content=data, media_type="text/markdown; charset=utf-8")


@domain_factory.post("/eia/library/files/{file_id}/regenerate-md")
async def regenerate_eia_library_md(file_id: int, current_user: User = Depends(get_admin_user)) -> dict[str, Any]:
    """重产 canonical md（failed 行手工修复）。"""
    try:
        return await get_eia_library_service().regenerate_md(file_id, current_user.username)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.patch("/eia/library/files/{file_id}/meta")
async def update_eia_library_file_meta(
    file_id: int, body: dict[str, Any] = Body(...), current_user: User = Depends(get_admin_user)
) -> dict[str, Any]:
    """stage/mineral 行内编辑（白名单；值域守卫 stage ∈ 五阶段 slug）。"""
    fields = {k: body[k] for k in ("stage", "mineral") if k in body}
    if not fields:
        raise HTTPException(status_code=400, detail="无可更新字段")
    try:
        return await get_eia_library_service().update_meta(file_id, fields)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.post("/eia/library/kb/bind")
async def bind_eia_corpus_kb(
    body: dict[str, Any] = Body(...), current_user: User = Depends(get_admin_user)
) -> dict[str, Any]:
    """绑定环评语料目标知识库（存在性校验 → system_options.eia_corpus_kb_id）。"""
    kb_id = (body.get("kb_id") or "").strip()
    if not kb_id:
        raise HTTPException(status_code=400, detail="kb_id 不能为空")
    try:
        await eia_corpus_tasks.bind_corpus_kb(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "kb_id": kb_id}


@domain_factory.post("/eia/library/push-kb")
async def push_eia_library_to_kb(
    body: dict[str, Any] = Body(...), current_user: User = Depends(get_admin_user)
) -> dict[str, Any]:
    """推送 canonical md 到绑定 KB（后台任务）。body: {file_ids: [int]}"""
    file_ids = body.get("file_ids")
    if not isinstance(file_ids, list) or not file_ids:
        raise HTTPException(status_code=400, detail="file_ids 不能为空")
    task = await tasker.enqueue(
        name="环评语料推送知识库",
        task_type="eia_corpus_push",
        payload={"file_ids": file_ids, "operator_id": _operator_id(current_user)},
    )
    return {"status": "queued", "task_id": task.id}


@domain_factory.post("/eia/library/process")
async def process_eia_library(
    body: dict[str, Any] = Body(...), current_user: User = Depends(get_admin_user)
) -> dict[str, Any]:
    """P2 加工（后台任务）。body: {file_ids?: [int], scope?: "all"}"""
    payload = {"operator_id": _operator_id(current_user)}
    if body.get("scope") == "all":
        payload["scope"] = "all"
    elif isinstance(body.get("file_ids"), list) and body["file_ids"]:
        payload["file_ids"] = body["file_ids"]
    else:
        raise HTTPException(status_code=400, detail="须提供 file_ids 或 scope=all")
    task = await tasker.enqueue(name="环评语料加工", task_type="eia_corpus_process", payload=payload)
    return {"status": "queued", "task_id": task.id}


@domain_factory.post("/eia/library/admin/bootstrap-manifest")
async def bootstrap_eia_library_manifest(
    file: UploadFile = File(...), current_user: User = Depends(get_admin_user)
) -> dict[str, Any]:
    """既有 manifest.json 导入：按 file_name 匹配登记 → 回填 report_id/stage/mineral（D6 人工裁决保留）。"""
    import json as _json

    try:
        manifest = _json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"manifest.json 非法: {e}")
    try:
        result = await get_eia_library_service().bootstrap_from_manifest(manifest, current_user.username)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, **result}
```

- [ ] **Step 2: 服务方法**（eia_library_service.py）

```python
ALLOWED_STAGES = {"planning_eia", "project_eia_underground", "project_eia_openpit", "post_eia", "tracking_eia"}

async def update_meta(self, file_id: int, fields: dict) -> dict:
    if "stage" in fields and fields["stage"] not in ALLOWED_STAGES:
        raise ValueError(f"非法 stage: {fields['stage']}")
    if "mineral" in fields and not (fields["mineral"] or "").strip():
        raise ValueError("mineral 不能为空")
    row = await self.repo.update_file(file_id, fields)
    if row is None:
        raise FileNotFoundError(file_id)
    return row.to_dict()

async def bootstrap_from_manifest(self, manifest: list[dict], operator: str | None) -> dict:
    """manifest（prepare_corpus 产物）按 file_name 回填 report_id/stage/mineral。"""
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest 须为非空数组")
    files = {f.original_filename: f for f in await self.repo.list_files()}  # ORM 行，属性访问
    matched, unmatched = [], []
    for e in manifest:
        row = files.get(e.get("file_name", ""))
        if row is None:
            unmatched.append(e.get("file_name"))
            continue
        await self.repo.update_file(row.id, {
            "report_id": e["report_id"], "stage": e["stage"], "mineral": e.get("mineral") or "coal",
        })
        matched.append(e["report_id"])
    await self._log(action="bootstrap", detail={"matched": matched, "unmatched": unmatched}, operator=operator)
    if unmatched:
        raise FileNotFoundError(f"以下文件未在文件库登记（请先上传后再引导）: {', '.join(unmatched)}")
    return {"matched": len(matched)}
```

> 顺序注：先回填全部匹配项再对 unmatched 报 404——部分成功落库 + 明确缺项清单，符合「管理员可补传后重跑」的幂等语义（update 幂等）。
> 路由导入区补：`from yuxi.services.task_service import tasker`、`from yuxi.services import eia_corpus_task_service as eia_corpus_tasks`、`Response`（fastapi）。`_operator_id(current_user)` 为模块内一行助手，operator 标识字段（`uid`/`username`）以 `knowledge_router.py:715-757` 既有 enqueue 调用实测为准——执行时先 grep 确认再定稿。

- [ ] **Step 3: 验证 + 提交**

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_library_service.py /app/test/unit/services/ -p no:cacheprovider
# 冒烟（运行栈，GET-only 起步）：/api/domain-factory/eia/library/files 列表含新字段
git add backend/server/routers/domain_factory_router.py backend/package/yuxi/services/eia_library_service.py
git commit -m "feat(domain-factory): 文件库 P2 路由（推送/加工/md 预览/元数据/bootstrap 引导）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: 前端 LibraryPanel 增量

**Files:**
- Modify: `web/src/apis/eia_data_api.js`（library API 组追加）
- Modify: `web/src/components/eia-data/LibraryPanel.vue`

- [ ] **Step 1: API 封装**（eia_data_api.js，对照 uploadLibraryFile 风格）

```javascript
  // —— P2 canonical md 正源（spec 2026-10-18）——
  getFileMd: (fileId) => http.post(`/domain-factory/eia/library/files/${fileId}/md`),
  regenerateMd: (fileId) => http.post(`/domain-factory/eia/library/files/${fileId}/regenerate-md`),
  updateFileMeta: (fileId, fields) => http.patch(`/domain-factory/eia/library/files/${fileId}/meta`, fields),
  pushToKb: (fileIds) => http.post(`/domain-factory/eia/library/push-kb`, { file_ids: fileIds }),
  processCorpus: (payload) => http.post(`/domain-factory/eia/library/process`, payload),
  bootstrapManifest: (file) => {
    const form = new FormData()
    form.append('file', file)
    return http.post(`/domain-factory/eia/library/admin/bootstrap-manifest`, form)
  },
  migrateStorage: () => http.post(`/domain-factory/eia/library/admin/migrate-storage`),
```

> http 实例命名以该文件现状为准（对照同文件既有方法）。

- [ ] **Step 2: LibraryPanel.vue**（增量，全部沿用既有表格/徽标/确认对话框惯例）

1. 列表列追加（对照 size/created_at 列写法 93-109）：
   - `stage`（空显示 `—`；行内下拉编辑，选项五阶段 slug 中文映射，change 即 `updateFileMeta`）
   - `md_status` 徽标：ready=成功（绿）/ failed=失败（红，tooltip md_failed_reason）/ not_applicable=不适用（灰）/ pending_backfill=待迁移（橙）
   - `kb_status` 徽标：indexed=已入库（绿）/ failed=失败（红，tooltip push_error）/ 其余中间态=进行中（蓝）/ 未推=灰
2. 行操作区追加（对照既有下载/删除按钮）：
   - 「查看 md」：`getFileMd` 新窗口/抽屉展示（GET 语义用 POST 路由已定，前端直接展示返回文本）
   - 「推送知识库」/「重推」（kb_status=indexed 且已推显示重推）：单选行 `pushToKb([row.id])`，成功提示去任务中心看进度
   - 「加工」：单行 `processCorpus({ file_ids: [row.id] })`
   - md_status=failed 行显示「重产 md」：`regenerateMd(row.id)`
3. 工具栏追加（对照既有上传按钮区）：
   - 「绑定语料知识库」（未绑定时常显）：对话框输入 kb_id → `bindCorpusKb`（API 封装加 `bindCorpusKb: (kbId) => http.post(\`/domain-factory/eia/library/kb/bind\`, { kb_id: kbId })`）；已绑定时显示当前 kb_id 可改绑
   - 勾选批量推送 / 批量加工（复用既有表格勾选或按当前文件夹过滤）
   - 「全库加工重编译」：`processCorpus({ scope: 'all' })`，二次确认
   - 「引导导入 manifest」（折叠在更多菜单）：上传 manifest.json → `bootstrapManifest`
4. 颜色只用 `base.css` 变量（`--color-success/-color-error/-color-warning/--gray-*`），样式用 less scoped。

- [ ] **Step 3: 验证 + 提交**

```bash
cd web && pnpm run lint && pnpm run format
.\scripts\sync-dev.ps1   # web 热重载自动生效
git add web/src/apis/eia_data_api.js web/src/components/eia-data/LibraryPanel.vue
git commit -m "feat(domain-factory): 文件库面板 P2 增量（md/KB 状态列、推送/加工动作、全库重编译入口）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: changelog + 运行栈端到端 QA

- [ ] **Step 1:** `make format`（ruff）+ `cd web && pnpm run lint`，零告警
- [ ] **Step 2:** 更新 `docs/develop-guides/changelog.md`（P2 小节：canonical md 正源/KB 直通/在线重编译/迁移端点；引用 spec）
- [ ] **Step 3:** 全量容器测试：

```bash
.\scripts\sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_canonical_md.py /app/test/unit/services/test_eia_corpus_push.py /app/test/unit/services/test_eia_corpus_process.py /app/test/unit/test_eia_library_service.py -p no:cacheprovider
python -X utf8 -m pytest backend/test/unit/services/test_eia_canonical_md_goldens.py -v   # 宿主机 33 份
```
- [ ] **Step 4:** 运行栈 E2E（管理员 admin/123，浏览器 isolatedContext）：
  1. 若存在 v18 存量登记行 → 调 `migrate-storage`（一次性）
  2. 上传 1–2 份真实 docx → 列表 md_status=ready、report_id 自动生成、stage 继承文件夹
  3. 「查看 md」确认前置区+标记+正文结构
  4. 一键创建/绑定语料 KB（设 eia_corpus_kb_id）→ 推送 → KB 文档出现 `<原名>.md` 且可检索
  5. 上传其余存量 docx 批量 → bootstrap-manifest（.wolf/corpus-workdir/manifest.json）→ 回填 rid/stage
  6. 全库加工 → 任务中心成功 → 技能 references 产物刷新（bank_index/切片/corpus_meta）；词表/meta 页面 rid 全集含新报告
  7. 台账抽查：eia_corpus_process_log 有 recompile/bootstrap/migrate 记录
- [ ] **Step 5:** 提交 changelog；OpenWolf 簿记（memory/cerebrum/buglog/anatomy）收尾

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(domain-factory): 文件库 P2 canonical md 正源 changelog

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 任务依赖

Task 1 → 2 → 3（内核线）；Task 4 → 5 → 6（数据/存储线，依赖 1 的 `_produce_md` 所需内核）；Task 7、8 依赖 4/5；Task 9 依赖 7/8；Task 10 依赖 9；Task 11 收尾。

## Spec 偏差记录（实现中契约修正，均已在对应任务落地）

| # | spec 原文 | 实现定稿 | 原因 |
|---|---|---|---|
| R1 | 封面抽取「加工时入 DB」 | `front_meta` 列**上传时**抽取入库，加工时合并 corpus_meta.json | 免重复解析 docx；corpus_meta.reports 是 meta 面 rid 全集权威（eia_meta_service.py:79-87），必合并 |
| R2 | 重推判定「md sha1 变化」 | 增列 `md_sha1` 存推送时指纹 | spec 列表未含该列，语义落地必需 |
| R3 | 台账「产物摘要」 | `eia_corpus_process_log.detail JSON` | 结构化留痕，服务清单展示 |
| R4 | 库对象 MinIO 定位 | 复用 `knowledgebases` 桶 + `eia-library/` 前缀（object_key 存桶内路径） | is_minio_url 白名单（kb_utils.py:254）零共享代码改动 |
