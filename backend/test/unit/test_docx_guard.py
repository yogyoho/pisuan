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

# python-docx 打开包时按此精确 Type 找主文档部件，fixture 必须用真类型
OFFICE_DOC_RELTYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)

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
    return f'<Relationship Id="{rid}" Type="{OFFICE_DOC_RELTYPE}" Target="{target}"{mode_attr}/>'


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
        _rels_xml([_rel("rId1", "document.xml"), _rel("rId7", "NULL")])
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
        _rels_xml([_rel("rId1", "document.xml"), _rel("rId8", "/word/NULL")])
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
                _rel("rId1", "document.xml"),
                _rel("rId9", "http://example.com/x", mode="External"),
            ]
        )
    )
    assert docx_guard.diagnose_docx(data).kind == "ok"


def test_repair_preserves_other_members_byte_for_byte():
    extra = {"word/media/img1.png": b"\x89PNG-raw-bytes", "word/document.xml": DOC_XML}
    broken = make_minimal_docx(
        _rels_xml([_rel("rId1", "document.xml"), _rel("rId7", "NULL")]), extra=extra
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
        _rels_xml([_rel("rId1", "document.xml"), _rel("rId7", "NULL")])
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
        _rels_xml([_rel("rId1", "document.xml"), _rel("rId7", "NULL")])
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
