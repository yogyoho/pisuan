from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import pytest
from PIL import Image

import pisuan.knowledge.parser.paddleocr_vl_local as mod
from pisuan.knowledge.parser.paddleocr_vl_local import (
    PaddleOCRVLLocalParser,
    _convert_table_markers,
)

pytestmark = pytest.mark.unit


@dataclass
class FakeResponse:
    status_code: int
    json_body: dict[str, Any] | None = None
    text: str = ""

    def json(self) -> dict[str, Any]:
        assert self.json_body is not None
        return self.json_body


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="PNG")
    return buf.getvalue()


# ── 表格标记流转换 ──


def test_convert_passthrough_without_markers() -> None:
    text = "# 标题\n\n普通正文，没有任何表格标记。"
    assert _convert_table_markers(text) == text


def test_convert_plain_table() -> None:
    converted = _convert_table_markers("<fcel>项目<fcel>数值<nl><fcel>产能<fcel>100<nl>")
    assert converted == ("<table><tr><td>项目</td><td>数值</td></tr><tr><td>产能</td><td>100</td></tr></table>")


def test_convert_colspan_via_lcel() -> None:
    converted = _convert_table_markers("<fcel>表头<lcel><fcel>尾<nl><fcel>1<ecel><fcel>2<nl>")
    assert converted == (
        '<table><tr><td colspan="2">表头</td><td>尾</td></tr><tr><td>1</td><td></td><td>2</td></tr></table>'
    )


def test_convert_rowspan_via_ucel() -> None:
    converted = _convert_table_markers("<fcel>类<fcel>值<nl><ucel><fcel>a<nl>")
    assert converted == ('<table><tr><td rowspan="2">类</td><td>值</td></tr><tr><td>a</td></tr></table>')


def test_convert_aborts_on_prose_literal() -> None:
    text = "前置说明文字 <fcel>A<nl>"
    assert _convert_table_markers(text) == text


def test_convert_escapes_html_in_cells() -> None:
    converted = _convert_table_markers("<fcel><b>&<nl>")
    assert "<td>&lt;b&gt;&amp;</td>" in converted


# ── 解析器装配与请求构造 ──


def test_default_and_env_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = PaddleOCRVLLocalParser()
    assert parser.chat_url == "http://host.docker.internal:8111/v1/chat/completions"
    assert parser.model == "PaddleOCR-VL-1.6-GGUF.gguf"

    monkeypatch.setenv("PADDLEOCR_VL_LOCAL_BASE_URL", "http://127.0.0.1:8111/v1/")
    monkeypatch.setenv("PADDLEOCR_VL_LOCAL_MODEL", "custom.gguf")
    parser = PaddleOCRVLLocalParser()
    assert parser.chat_url == "http://127.0.0.1:8111/v1/chat/completions"
    assert parser.model == "custom.gguf"


def test_check_health_uses_models_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_get(url, timeout=None):
        seen["url"] = url
        return FakeResponse(200, {"data": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)
    health = PaddleOCRVLLocalParser().check_health()
    assert health["status"] == "healthy"
    assert seen["url"] == "http://host.docker.internal:8111/v1/models"


def test_process_image_sends_official_ocr_instruction(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_path = tmp_path / "page.png"
    file_path.write_bytes(_png_bytes())
    submitted: dict[str, Any] = {}

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        submitted["url"] = url
        submitted["payload"] = json
        content = "<fcel>采区<fcel>100<nl>"
        return FakeResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    monkeypatch.setattr(mod.requests, "post", fake_post)
    result = PaddleOCRVLLocalParser().process_file(str(file_path))

    assert submitted["url"] == "http://host.docker.internal:8111/v1/chat/completions"
    messages = submitted["payload"]["messages"]
    assert messages[0]["content"][1] == {"type": "text", "text": "OCR:"}
    assert submitted["payload"]["temperature"] == 0.0
    assert submitted["payload"]["max_tokens"] == 8192
    assert submitted["payload"]["model"] == "PaddleOCR-VL-1.6-GGUF.gguf"
    assert messages[0]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    # 输出经过表格标记流转换
    assert result == "<table><tr><td>采区</td><td>100</td></tr></table>"


def test_process_file_rejects_unsupported_extension(tmp_path) -> None:
    file_path = tmp_path / "doc.docx"
    file_path.write_bytes(b"fake")
    with pytest.raises(Exception, match="Unsupported file type"):
        PaddleOCRVLLocalParser().process_file(str(file_path))
