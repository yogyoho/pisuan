# bug-355 ETL docx 入口防护实施计划（诊断 + zip 手术自动修复重试）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ETL 主解析与大纲提取两个 docx 消费面获得病态文件诊断、可救类自动修复重试、空产物守卫（spec：`docs/superpowers/specs/2026-10-06-bug355-etl-docx-guard-design.md`，方案 B 已批准）。

**Architecture:** 新模块 `yuxi/services/docx_guard.py`（纯 stdlib，守卫编排 + zip 手术 + 文案全在此），service 侧仅两处 ≤7 行调用。诊断四态 ok/dangling_rels/unidocsa/corrupt；悬空内部关系项剔除后重试解析恰一次；原文件永不修改。`unified.py`/`ocr_service` 零改动，零 schema 变更。

**Tech Stack:** Python 3.12+（stdlib: zipfile/io/posixpath/xml.etree/dataclasses/tempfile/pathlib）、python-docx（测试断言用，host 已装）、pytest（`--noconftest` 自包含模式，仿 `test_report_skeleton_fit.py` 先例）。

**背景速读（实现者必读）**：
- docx = zip 包；`word/_rels/document.xml.rels` 里 `Target="NULL"`（或 `/word/NULL`）指向不存在部件 → python-docx `KeyError` 崩溃。真实病例：`.wolf/corpus-census/patched/` 下九龙川（145MB）/巴拉素（39MB）两份手术副本，38 份完整章树含此二份。
- 仓库约束（CLAUDE.md）：提交用显式 `git add <files>` 禁 `git add -A`；Conventional Commits 中文 + `Co-Authored-By: Claude Code <noreply@anthropic.com>`；**禁碰清单**（严禁卷入任何提交）：`backend/package/yuxi/agents/buildin/chatbot/prompt.py`、`backend/server/utils/lifespan.py`、`web/src/components/AgentChatComponent.vue`、`web/src/components/SettingsModal.vue`、`docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md`、`docs/superpowers/plans/2026-09-30-coal-eia-writer-v2-port.md`、`docs/superpowers/plans/2026-10-05-w0-bugfix-and-usage-tracking.md`。
- 两处改动区域出处已判定（`git branch --contains`：均不在 main）：`_etl_parse_stage` 解析段出自 `484e5bf7`，`extract_outline_preview` 出自 `02419f2f`——pisuan-custom 领地，可改。

---

### Task 1: docx_guard 模块 + 单测（TDD）

**Files:**
- Create: `backend/package/yuxi/services/docx_guard.py`
- Test: `backend/test/unit/test_docx_guard.py`

- [x] **Step 1: 写测试（完整文件）**

```python
"""docx_guard 单测（bug-355）：全内存合成 fixture，不依赖外部文件。

宿主: python -m pytest backend/test/unit/test_docx_guard.py --noconftest -q
（自包含模式，不读 conftest；仿 test_report_skeleton_fit.py 先例）
"""

import asyncio
import io
import sys
import zipfile
from pathlib import Path

import pytest
from docx import Document

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "package"))

from yuxi.services import docx_guard  # noqa: E402

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

DOC_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>hello</w:t></w:r></w:p></w:body></w:document>"
).encode()

CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    "<Override PartName=\"/word/document.xml\" "
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
).encode()


def _rels_xml(rels: list[str]) -> bytes:
    body = "".join(rels)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{RELS_NS}">{body}</Relationships>'
    ).encode()


def _rel(rid: str, target: str, mode: str | None = None) -> str:
    mode_attr = f' TargetMode="{mode}"' if mode else ""
    return f'<Relationship Id="{rid}" Type="http://example.com/{rid}" Target="{target}"{mode_attr}/>'


def make_minimal_docx(doc_rels: bytes | None = None, extra: dict[str, bytes] | None = None) -> bytes:
    members: dict[str, bytes] = {
        "[Content_Types].xml": CONTENT_TYPES_XML,
        "_rels/.rels": _rels_xml([_rel("rId1", "word/document.xml")]),
        "word/document.xml": DOC_XML,
    }
    if doc_rels is not None:
        members["word/_rels/document.xml.rels"] = doc_rels
    if extra:
        members.update(extra)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return buf.getvalue()


# ---------- 诊断 ----------


def test_ok_docx():
    data = make_minimal_docx()
    assert docx_guard.diagnose_docx(data).kind == "ok"
    assert docx_guard.guard_docx_bytes(data, label="t.docx") is data  # 原样返回，零副本
    with pytest.raises(ValueError, match="仅处理"):
        docx_guard.repair_dangling_rels(data)


def test_null_target_variant_detected_and_repaired():
    broken = make_minimal_docx(
        _rels_xml([_rel("rId1", "word/document.xml"), _rel("rId7", "NULL")])
    )
    diag = docx_guard.diagnose_docx(broken)
    assert diag.kind == "dangling_rels"
    assert any("NULL" in detail for detail in diag.details)
    fixed = docx_guard.repair_dangling_rels(broken)
    assert docx_guard.diagnose_docx(fixed).kind == "ok"
    doc = Document(io.BytesIO(fixed))
    assert doc.paragraphs[0].text == "hello"


def test_absolute_null_target_variant():
    broken = make_minimal_docx(
        _rels_xml([_rel("rId1", "word/document.xml"), _rel("rId8", "/word/NULL")])
    )
    assert docx_guard.diagnose_docx(broken).kind == "dangling_rels"
    assert docx_guard.diagnose_docx(docx_guard.repair_dangling_rels(broken)).kind == "ok"


def test_absolute_legit_target_not_dangling():
    data = make_minimal_docx(_rels_xml([_rel("rId1", "/word/document.xml")]))
    assert docx_guard.diagnose_docx(data).kind == "ok"


def test_external_target_exempt():
    data = make_minimal_docx(
        _rels_xml(
            [
                _rel("rId1", "word/document.xml"),
                _rel("rId9", "http://example.com/x", mode="External"),
            ]
        )
    )
    assert docx_guard.diagnose_docx(data).kind == "ok"


def test_repair_preserves_other_members_byte_for_byte():
    extra = {"word/media/img1.png": b"\x89PNG-raw-bytes", "word/document.xml": DOC_XML}
    broken = make_minimal_docx(
        _rels_xml([_rel("rId1", "word/document.xml"), _rel("rId7", "NULL")]), extra=extra
    )
    fixed = docx_guard.repair_dangling_rels(broken)
    with zipfile.ZipFile(io.BytesIO(fixed)) as zf:
        assert zf.read("word/media/img1.png") == b"\x89PNG-raw-bytes"
        assert zf.read("word/document.xml") == DOC_XML


def test_unidocsa_header():
    payload = b"UniDocSa" + b"\x00" * 64
    assert docx_guard.diagnose_docx(payload).kind == "unidocsa"
    with pytest.raises(ValueError, match="UniDocSa"):
        docx_guard.guard_docx_bytes(payload, label="t.docx")


def test_corrupt_bytes():
    assert docx_guard.diagnose_docx(b"\xd0\xcf\x11\xe0not-a-zip-at-all").kind == "corrupt"


# ---------- guarded_reparse（异步；fake fetch + fake parse_fn） ----------


@pytest.fixture
def fake_fetch(monkeypatch):
    holder: dict[str, bytes] = {}
    calls = {"n": 0}

    async def _fetch(file_path: str) -> bytes:
        calls["n"] += 1
        return holder["data"]

    monkeypatch.setattr(docx_guard, "_fetch_file_bytes", _fetch)
    return holder, calls


def test_guarded_reparse_repairs_and_retries(fake_fetch):
    holder, calls = fake_fetch
    holder["data"] = make_minimal_docx(
        _rels_xml([_rel("rId1", "word/document.xml"), _rel("rId7", "NULL")])
    )
    seen_paths: list[str] = []

    async def parse_fn(path: str) -> str:
        seen_paths.append(path)
        return "# ok"

    result = asyncio.run(docx_guard.guarded_reparse("a.docx", RuntimeError("boom"), parse_fn))
    assert result == "# ok"
    assert all(not Path(p).exists() for p in seen_paths)  # 临时副本已清理
    assert calls["n"] == 1


def test_guarded_reparse_ok_reraises_original(fake_fetch):
    holder, _ = fake_fetch
    holder["data"] = make_minimal_docx()

    async def parse_fn(path: str) -> str:
        raise RuntimeError("unused")

    with pytest.raises(RuntimeError, match="minio timeout"):
        asyncio.run(docx_guard.guarded_reparse("a.docx", RuntimeError("minio timeout"), parse_fn))


def test_guarded_reparse_unidocsa_chinese_error(fake_fetch):
    holder, _ = fake_fetch
    holder["data"] = b"UniDocSa" + b"\x00" * 64

    async def parse_fn(path: str) -> str:
        raise RuntimeError("unused")

    with pytest.raises(ValueError, match="另存为标准"):
        asyncio.run(docx_guard.guarded_reparse("a.docx", RuntimeError("bad"), parse_fn))


def test_guarded_reparse_retry_still_fails(fake_fetch):
    holder, _ = fake_fetch
    holder["data"] = make_minimal_docx(
        _rels_xml([_rel("rId1", "word/document.xml"), _rel("rId7", "NULL")])
    )

    async def parse_fn(path: str) -> str:
        raise RuntimeError("still broken")

    with pytest.raises(ValueError, match="仍失败"):
        asyncio.run(docx_guard.guarded_reparse("a.docx", RuntimeError("first"), parse_fn))


def test_guarded_reparse_non_docx_passthrough(fake_fetch):
    _, calls = fake_fetch

    async def parse_fn(path: str) -> str:
        raise RuntimeError("pdf boom")

    with pytest.raises(RuntimeError, match="pdf boom"):
        asyncio.run(docx_guard.guarded_reparse("a.pdf", RuntimeError("pdf boom"), parse_fn))
    assert calls["n"] == 0  # 非 docx 不取字节
```

- [x] **Step 2: 跑测试确认失败（模块不存在）**

Run: `python -m pytest backend/test/unit/test_docx_guard.py --noconftest -q`（repo 根目录）
Expected: collection error —— `ModuleNotFoundError: No module named 'yuxi.services.docx_guard'`

- [x] **Step 3: 写实现（完整文件）**

```python
"""docx 入口防护：病态文件诊断 + 悬空关系项 zip 手术（bug-355）。

docx 实为 zip 包；WPS 等生成器可能写出指向不存在部件的关系项
（如 Target="NULL"），python-docx 严格解析时 KeyError 崩溃（Word 本身容错，
文件能打开，程序解析不了）。本模块提供：
- diagnose_docx：四态诊断 ok / dangling_rels / unidocsa / corrupt
- repair_dangling_rels：剔除悬空内部关系项，产出内存修复副本（原文件不动）
- guard_docx_bytes：同步守卫（大纲提取等直接以 bytes 打开的消费面）
- guarded_reparse：异步守卫（ETL 主解析失败后的诊断 + 修复重试恰一次）

设计 spec：docs/superpowers/specs/2026-10-06-bug355-etl-docx-guard-design.md
"""

import io
import logging
import posixpath
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

USER_MESSAGES = {
    "unidocsa": "文件为 WPS 私有格式（UniDocSa），非标准 docx 容器，无法解析；"
    "请用 Word/WPS 打开后另存为标准 .docx 再上传",
    "corrupt": "文件损坏或非标准 docx 容器，无法解析",
}


@dataclass
class DocxDiagnosis:
    kind: str  # "ok" | "dangling_rels" | "unidocsa" | "corrupt"
    details: list[str] = field(default_factory=list)  # 悬空条目清单（进日志，不进用户报错）


def _dangling_rels_in(member: str, payload: bytes, namelist: set[str]) -> list[tuple[str, str]]:
    """单个 .rels 内的悬空 (Id, Target) 列表；TargetMode="External" 豁免。

    Target 解析规则：以 "/" 开头按包根绝对路径；否则相对 .rels 所在部件的
    目录（word/_rels/document.xml.rels → base "word"；_rels/.rels → base ""）。
    """
    base = posixpath.dirname(posixpath.dirname(member))
    dangling: list[tuple[str, str]] = []
    for rel in ElementTree.fromstring(payload):
        if rel.get("TargetMode") == "External":
            continue
        raw_target = rel.get("Target") or ""
        if raw_target.startswith("/"):
            resolved = raw_target.lstrip("/")
        elif raw_target:
            resolved = posixpath.normpath(posixpath.join(base, raw_target))
        else:
            resolved = ""
        if resolved not in namelist:
            dangling.append((rel.get("Id") or "", raw_target))
    return dangling


def diagnose_docx(data: bytes) -> DocxDiagnosis:
    """诊断 docx bytes 的病类。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        if data[:8].startswith(b"UniDocSa"):
            return DocxDiagnosis("unidocsa", ["文件头为 WPS 私有格式 UniDocSa"])
        return DocxDiagnosis("corrupt", [f"非 zip 容器，头 8 字节 {data[:8]!r}"])

    namelist = set(zf.namelist())
    dangling: list[str] = []
    for member in zf.namelist():
        if not member.endswith(".rels"):
            continue
        for rel_id, target in _dangling_rels_in(member, zf.read(member), namelist):
            dangling.append(f"{member}: {rel_id} -> {target}")
    if dangling:
        return DocxDiagnosis("dangling_rels", dangling)
    return DocxDiagnosis("ok")


def _strip_dangling(member: str, payload: bytes, namelist: set[str]) -> bytes:
    dangling = set(_dangling_rels_in(member, payload, namelist))
    if not dangling:
        return payload
    root = ElementTree.fromstring(payload)
    for rel in list(root):
        if (rel.get("Id") or "", rel.get("Target") or "") in dangling:
            root.remove(rel)
    ElementTree.register_namespace("", RELS_NS)
    return ElementTree.tostring(root, xml_declaration=True, encoding="UTF-8")


def repair_dangling_rels(data: bytes) -> bytes:
    """剔除悬空内部关系项，返回修复副本（bytes→bytes，原数据不动）。

    其余 zip 条目逐字节原样复制（保留原 compress_type）。
    """
    diag = diagnose_docx(data)
    if diag.kind != "dangling_rels":
        raise ValueError(f"repair_dangling_rels 仅处理 dangling_rels 病类，收到 {diag.kind}")
    src = zipfile.ZipFile(io.BytesIO(data))
    namelist = set(src.namelist())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename.endswith(".rels"):
                payload = _strip_dangling(info.filename, payload, namelist)
            dst.writestr(info, payload)
    return buf.getvalue()


def guard_docx_bytes(data: bytes, label: str = "") -> bytes:
    """同步守卫：直接以 bytes 打开 docx 的消费面（大纲提取等）。

    ok → 原样返回；dangling_rels → 修复后返回（记 warning）；
    不可救病类 → ValueError(USER_MESSAGES[kind])。
    """
    diag = diagnose_docx(data)
    if diag.kind == "ok":
        return data
    if diag.kind == "dangling_rels":
        logger.warning(f"docx 存在悬空关系项，剔除后继续: {label}, 条目={diag.details}")
        return repair_dangling_rels(data)
    raise ValueError(USER_MESSAGES[diag.kind])


async def _fetch_file_bytes(file_path: str) -> bytes:
    """取任务文件 bytes：MinIO URL 走 adownload_file，本地路径走 aiofiles。"""
    from yuxi.knowledge.utils.kb_utils import is_minio_url, parse_minio_url

    if is_minio_url(file_path):
        from yuxi.storage.minio.client import get_minio_client

        bucket_name, object_name = parse_minio_url(file_path)
        return await get_minio_client().adownload_file(bucket_name, object_name)

    import aiofiles

    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


async def guarded_reparse(file_path: str, original_error: Exception, parse_fn) -> str:
    """解析失败后的 docx 守卫：诊断病类，可救则 zip 手术后重试恰一次（bug-355）。

    仅 .docx 后缀生效（剥 MinIO query 后判定，ocr_service 同款）。
    ok → 原样 re-raise（病不在文件，守卫不掩盖）；unidocsa/corrupt →
    ValueError(USER_MESSAGES) chain 原异常；dangling_rels → 修复副本重试
    一次，仍败则链式报错。原文件永不修改，临时副本 finally 清理。
    parse_fn 注入以便测试（生产传 parse_document）。
    """
    suffix = Path(file_path.split("?", 1)[0]).suffix.lower()
    if suffix != ".docx":
        raise original_error

    data = await _fetch_file_bytes(file_path)
    diag = diagnose_docx(data)
    if diag.kind == "ok":
        raise original_error
    if diag.kind in USER_MESSAGES:
        raise ValueError(USER_MESSAGES[diag.kind]) from original_error

    # dangling_rels：剔除悬空关系项后重试解析恰一次
    logger.warning(f"docx 存在悬空关系项，剔除后重试解析: {file_path}, 条目={diag.details}")
    fixed = repair_dangling_rels(data)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
            tf.write(fixed)
            temp_path = tf.name
        return await parse_fn(temp_path)
    except Exception as retry_error:  # noqa: BLE001
        raise ValueError(
            f"docx 解析失败，自动修复（剔除 {len(diag.details)} 个悬空关系项）后仍失败: {file_path}"
        ) from retry_error
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
```

- [x] **Step 4: 跑测试确认全过**

Run: `python -m pytest backend/test/unit/test_docx_guard.py --noconftest -q`
Expected: `13 passed`（若 host 导入 `yuxi` 失败，改用容器跑，见 Task 4 Step 1 的发现步骤；两者必须有一处绿）

- [x] **Step 5: 容器内复跑（依赖隔离验证）**

先发现容器内 yuxi 安装位置：`docker run --rm pisuan-api:0.7.3 python -c "import yuxi; print(yuxi.__file__)"`
- 若输出 `/app/package/yuxi/__init__.py`：`docker run --rm -v "C:\workspace\pisuan\backend:/app:ro" pisuan-api:0.7.3 python -m pytest /app/test/unit/test_docx_guard.py --noconftest -q`
- 若输出 site-packages 路径（pip 安装）：改挂单文件覆盖——`-v "C:\workspace\pisuan\backend\package\yuxi\services\docx_guard.py:<site-packages>/yuxi/services/docx_guard.py:ro"` + `-v "C:\workspace\pisuan\backend\test:/app/test:ro"`，`-w /app`
Expected: `13 passed`

- [x] **Step 6: Commit**

```bash
git add backend/package/yuxi/services/docx_guard.py backend/test/unit/test_docx_guard.py
git commit -m "fix(etl): docx_guard 模块——病态 docx 四态诊断 + 悬空关系项 zip 手术（bug-355）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

> 执行记录：实现者对计划测试 fixture 做两处必要修正（OFFICE_DOC_RELTYPE 真类型 + word/_rels 内相对目标改 document.xml，见 2d547e24 与 bug-368），实现文件逐字未改，双评审通过。

---

### Task 2: ETL 主解析接线 + 空产物守卫

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:577-587`（`_etl_parse_stage` 内）

- [x] **Step 1: 接线解析守卫（替换 ：577 单行为 try/except）**

现文件 ：570-577 上下文（`from yuxi.knowledge.parser.unified import ...` 之后）：

```python
        raw_markdown = await parse_document(file_path)
```

改为：

```python
        try:
            raw_markdown = await parse_document(file_path)
        except Exception as parse_error:  # noqa: BLE001
            # [pisuan-custom] bug-355 守卫：docx 病态文件诊断 + 悬空关系项修复重试（恰一次）
            from yuxi.services.docx_guard import guarded_reparse

            raw_markdown = await guarded_reparse(file_path, parse_error, parse_document)
```

- [x] **Step 2: 空产物守卫（:586 `paragraphs = ...` 之后紧跟）**

现文件 ：586-587：

```python
        paragraphs = self._parse_markdown_to_paragraphs(raw_markdown, html_content=raw_html)
        logger.info(f"文档切分完成，共 {len(paragraphs)} 个段落")
```

改为：

```python
        paragraphs = self._parse_markdown_to_paragraphs(raw_markdown, html_content=raw_html)
        if not paragraphs:
            raise ValueError(
                f"解析产物为空（0 段落）: {file_path}——文件可能为空壳或解析退化，请检查文件"
            )
        if len(raw_markdown) < 1000:
            logger.warning(f"解析产物疑似退化（Markdown 仅 {len(raw_markdown)} 字符）: {file_path}")
        logger.info(f"文档切分完成，共 {len(paragraphs)} 个段落")
```

（稀疏只告警不阻断——正常简本文件可能就是小。）

- [x] **Step 3: 语法验证 + diff 行数核对**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
git diff --stat backend/package/yuxi/services/domain_factory_service.py
```

Expected: `OK`；本任务后 diff 约 +14/-1 行。

- [x] **Step 4: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "fix(etl): ETL 主解析接 docx 守卫 + 空产物显式失败（bug-355）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 大纲提取接线

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:5085`（`extract_outline_preview` 内）

- [x] **Step 1: 守卫前置（`Document()` 所在的 `_extract_headings_from_docx` 本体零改动，守卫放有 `filename` 上下文的调用点）**

现文件 ：5085：

```python
        headings = self._extract_headings_from_docx(file_bytes)
```

改为：

```python
        from yuxi.services.docx_guard import guard_docx_bytes

        file_bytes = guard_docx_bytes(file_bytes, label=filename)
        headings = self._extract_headings_from_docx(file_bytes)
```

- [x] **Step 2: 语法验证 + 调用面核对**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
grep -rn "_extract_headings_from_docx" backend/ --include="*.py"
```

Expected: `OK`；grep 恰 2 处（def :5126 + 调用 :5085），无其他消费面遗漏。

- [x] **Step 3: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "fix(etl): 大纲提取接 docx 守卫（bug-355）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 真实文件冒烟 + 收尾

**Files:**
- Modify: `docs/develop-guides/changelog.md`、`.wolf/buglog.json`（worktree-only，不提交 .wolf）、`docs/superpowers/plans/2026-10-06-bug355-etl-docx-guard.md`（本文件勾账）

- [x] **Step 1: patched/ 真实病态文件冒烟（容器内，文件名 CJK 用 os.listdir 规避 CLI 转码）**

```bash
docker run --rm \
  -v "C:\workspace\pisuan\backend:/app:ro" \
  -v "C:\workspace\pisuan\.wolf\corpus-census\patched:/patched:ro" \
  pisuan-api:0.7.3 python -c "
import sys, io, os
sys.path.insert(0, '/app/package')
from yuxi.services import docx_guard
from docx import Document
for name in sorted(os.listdir('/patched')):
    if not name.endswith('.docx'):
        continue
    data = open(f'/patched/{name}', 'rb').read()
    diag = docx_guard.diagnose_docx(data)
    fixed = docx_guard.guard_docx_bytes(data, label=name)
    doc = Document(io.BytesIO(fixed))
    print(name[:20], '| diag =', diag.kind, '| paras =', len(doc.paragraphs), '| OK')
"
```

Expected: 两行输出，diag 均为 `dangling_rels`，paras 为千级正数，尾部 `OK`。若容器内 yuxi 不在 /app/package（Task 1 Step 5 已探明），按同一步骤的挂载变体调整。

- [x] **Step 2: 全量单测回归（防接线破坏既有面）**

```bash
python -m pytest backend/test/unit/test_docx_guard.py --noconftest -q
python -m pytest backend/test/unit/test_report_skeleton_fit.py --noconftest -q
```

Expected: `13 passed` + `37 passed`。

- [x] **Step 3: changelog 落账**

`docs/develop-guides/changelog.md` 新增小节（日期小节制，现有 `### pisuan 定制增量（2026-10-05）` 之后）：

```markdown
### pisuan 定制增量（2026-10-06）

- fix(etl): bug-355 docx 入口防护——`yuxi/services/docx_guard.py` 四态诊断（ok/dangling_rels/unidocsa/corrupt）+ 悬空关系项 zip 手术自动修复重试恰一次；ETL 主解析与大纲提取两消费面接线；空产物 0 段落显式失败。原文件永不修改，unified.py/ocr_service 零改动
```

- [x] **Step 4: buglog 更新（worktree-only，不提交）**

`.wolf/buglog.json` 的 bug-355 条目：`fix` 追加「；2026-10-06 ETL 侧落地：docx_guard 四态诊断 + 悬空关系项手术 + guarded_reparse 重试恰一次 + 空产物守卫（spec: docs/superpowers/specs/2026-10-06-bug355-etl-docx-guard-design.md）」；`last_seen` → `2026-10-06`；`tags` 追加 `etl-guard`。

- [x] **Step 5: 计划勾账 + Commit**

本文件全部 checkbox 勾选 + 末尾追加执行记录 blockquote（跑数实测：13/37 passed、冒烟 paras 数、diff 行数）。

```bash
git add docs/develop-guides/changelog.md docs/superpowers/plans/2026-10-06-bug355-etl-docx-guard.md
git commit -m "docs(etl): bug-355 收尾——changelog + 计划勾账（冒烟 2/2 PASS）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成定义（DoD）

1. `docx_guard.py` + 13 用例单测入库，宿主与容器双绿。
2. 两处接线 diff 合计 ≤ 25 行；`unified.py`/`ocr_service` 零 diff（`git diff <本计划首提交>^ HEAD -- backend/package/yuxi/knowledge/parser/unified.py backend/package/yuxi/services/ocr_service.py` 为空）。
3. patched/ 真实病态文件冒烟 2/2 PASS（诊断 dangling_rels + 修复后 python-docx 可开）。
4. changelog 落账；禁碰清单零卷入；.wolf 文件不进提交。

## Out of scope

- census 脚本转正（gap-audit 风险①独立挂账）；unified.py 底层防护（方案 C 否决）；非 docx 类型防护；复垦族/全量表单（O5/O2）。

> **W(bug-355) 执行记录（2026-10-06）**：Task1 de71785d（docx_guard 182 行 + 13 测试）→ 质量评审 1 Important（损坏 .rels 裸抛泄四态契约）→ 2d547e24（corrupt 态防护 + 3 补测 + 3 Minor，16 测试）；Task2 d0ac3525（ETL 接守卫 + 空守卫，+13/-1）；Task3 99a215b4（大纲接线，+3）；Task2+3 合并双焦点评审 APPROVED（接线与下发代码逐字节一致，异常传播链核验至驱动层 FAILED 落账 :1028-1030）。冒烟：patched/ 两份实为普查术后副本 diag=ok 直通零损伤（paras 4416/4808）；内存注入 Target="NULL" 复现原病灶 → dangling_rels 诊断命中 → 守卫剔除悬空项（日志 rIdNULLINJECT->NULL）→ 术后 ok、段落 4416/4808 与原件一致，2/2 PASS（容器 pisuan-api:0.7.3）。回归：53 passed（16 docx_guard + 37 report_skeleton_fit，--noconftest）。unified.py/ocr_service 零 diff（de71785d^..HEAD 实测 0 行）。
