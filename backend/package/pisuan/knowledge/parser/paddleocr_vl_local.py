"""
PaddleOCR-VL Local Parser

对接本机自部署的 PaddleOCR-VL（llama.cpp GGUF）OpenAI 兼容服务，例如
http://127.0.0.1:8111/v1（容器内经 host.docker.internal 访问宿主）。
PDF 逐页渲染为图片后，用模型官方训练指令提示词 `OCR:` 整页转写。
"""

import base64
import io
import os
import re
import time
from html import escape as html_escape
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import requests
from PIL import Image

from pisuan.knowledge.parser.base import BaseDocumentProcessor, DocumentParserException
from pisuan.knowledge.parser.table_merge import merge_split_tables
from pisuan.knowledge.parser.capabilities import get_parser_capability
from pisuan.utils import logger

_CAPABILITY = get_parser_capability("paddleocr_vl_local")

# PaddleOCR-VL 表格原生输出是单元格标记流而非 HTML（部署实测，DEPLOY_PLAN「第三方直调必读」）：
# <fcel>有值格 <ecel>空格 <lcel>与左侧合并 <ucel>与上方合并 <nl>行结束
_TABLE_TOKEN_RE = re.compile(r"<fcel>|<ecel>|<lcel>|<ucel>|<nl>")
_TABLE_MARKERS = ("<fcel>", "<ecel>", "<lcel>", "<ucel>", "<nl>")


def _convert_table_markers(text: str) -> str:
    """把单元格标记流转成带 colspan/rowspan 的 HTML 表格；无标记时原样返回。

    仅处理纯表格标记流：一旦出现标记流之外的非空白正文字面量，说明不是表格
    输出（模型自发混排等），放弃转换原样返回，避免误伤普通文本。
    """
    if not any(marker in text for marker in _TABLE_MARKERS):
        return text

    rows: list[list[dict]] = []
    row: list[dict] = []
    open_cells: dict[int, dict] = {}  # 列号 -> 该列最近的跨行单元格
    current: dict | None = None  # 等待填充文本的 <fcel> 单元
    col = 0
    pos = 0
    for match in _TABLE_TOKEN_RE.finditer(text):
        literal = text[pos : match.start()]
        pos = match.end()
        if current is not None:
            current["text"] += literal
        elif literal.strip():
            return text

        marker = match.group()
        if marker == "<fcel>":
            current = {"col": col, "colspan": 1, "rowspan": 1, "text": ""}
            row.append(current)
            open_cells[col] = current
        elif marker == "<ecel>":
            current = None
            row.append({"col": col, "colspan": 1, "rowspan": 1, "text": ""})
            open_cells[col] = row[-1]
        elif marker == "<lcel>":
            if not row:
                return text
            row[-1]["colspan"] += 1
            open_cells[row[-1]["col"] + row[-1]["colspan"] - 1] = row[-1]
        elif marker == "<ucel>":
            above = open_cells.get(col)
            if above is not None:
                above["rowspan"] += 1
            else:
                row.append({"col": col, "colspan": 1, "rowspan": 1, "text": ""})
        elif marker == "<nl>":
            if row:
                rows.append(row)
                row = []
            current = None
            col = -1  # 行结束，列号归位（循环尾统一 +1 回到第 0 列）
        col += 1

    tail = text[pos:]
    if current is not None:
        current["text"] += tail
    elif tail.strip():
        return text
    if row:
        rows.append(row)

    html_rows = []
    for r in rows:
        cells = []
        for c in r:
            content = html_escape(c["text"].strip())
            span = f' colspan="{c["colspan"]}"' if c["colspan"] > 1 else ""
            span += f' rowspan="{c["rowspan"]}"' if c["rowspan"] > 1 else ""
            cells.append(f"<td{span}>{content}</td>")
        html_rows.append(f"<tr>{''.join(cells)}</tr>")
    return "<table>" + "".join(html_rows) + "</table>"


class PaddleOCRVLLocalParser(BaseDocumentProcessor):
    """PaddleOCR-VL 本地部署解析器（llama.cpp OpenAI 兼容服务，无鉴权）。"""

    service_name = _CAPABILITY.service_name
    display_name = _CAPABILITY.display_name
    supported_extensions = list(_CAPABILITY.supported_extensions)

    def __init__(self, base_url: str | None = None, model: str | None = None):
        # 默认地址面向 Docker 容器访问宿主服务；宿主本机进程可配 127.0.0.1:8111
        self.base_url = (
            base_url or os.getenv("PADDLEOCR_VL_LOCAL_BASE_URL") or "http://host.docker.internal:8111/v1"
        ).rstrip("/")
        self.model = model or os.getenv("PADDLEOCR_VL_LOCAL_MODEL", "PaddleOCR-VL-1.6-GGUF.gguf")
        self.chat_url = f"{self.base_url}/chat/completions"

    def check_health(self) -> dict[str, Any]:
        """探测模型列表端点判断服务可用性。"""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=10)
        except Exception as e:
            return {"status": "unavailable", "message": f"Connection failed: {e}", "details": {"error": str(e)}}
        if response.status_code == 200:
            return {
                "status": "healthy",
                "message": "PaddleOCR-VL local server is available",
                "details": {"base_url": self.base_url, "model": self.model},
            }
        return {
            "status": "unhealthy",
            "message": f"API Error: {response.status_code}",
            "details": {"status_code": response.status_code},
        }

    def process_file(self, file_path: str, params: dict[str, Any] | None = None) -> str:
        if not os.path.exists(file_path):
            raise DocumentParserException(f"File not found: {file_path}", self.get_service_name(), "file_not_found")

        file_ext = Path(file_path).suffix.lower()
        if not self.supports_file_type(file_ext):
            raise DocumentParserException(
                f"Unsupported file type: {file_ext}", self.get_service_name(), "unsupported_file_type"
            )

        try:
            start_time = time.time()
            logger.info(f"PaddleOCR-VL local starting: {os.path.basename(file_path)}")

            params = params or {}
            if file_ext == ".pdf":
                content = self._process_pdf(file_path, params)
            else:
                content = self._process_image(file_path, params)

            processing_time = time.time() - start_time
            logger.info(
                f"PaddleOCR-VL local finished: {os.path.basename(file_path)} - "
                f"{len(content)} chars ({processing_time:.2f}s)"
            )
            return content
        except Exception as e:
            if isinstance(e, DocumentParserException):
                raise
            error_msg = f"PaddleOCR-VL local failed: {e}"
            logger.error(error_msg)
            raise DocumentParserException(error_msg, self.get_service_name(), "processing_failed")

    def _process_pdf(self, file_path: str, params: dict[str, Any]) -> str:
        """PDF 逐页渲染为 PNG 后整页转写（约 15 秒/页，服务端 mmproj 像素上限自动压缩）。"""
        pdf = pdfium.PdfDocument(file_path)
        try:
            scale = int(params.get("pdf_dpi", 200)) / 72
            full_text = []
            for i in range(len(pdf)):
                logger.debug(f"Processing page {i + 1}/{len(pdf)}")
                bitmap = pdf[i].render(scale=scale).to_pil()
                buf = io.BytesIO()
                bitmap.save(buf, format="PNG")
                full_text.append(self._call_api(buf.getvalue(), params))
            merged_text, merged_count = merge_split_tables("\n\n".join(full_text))
            if merged_count:
                logger.info(f"已合并 {merged_count} 处跨页断表碎片")
            return merged_text
        finally:
            pdf.close()

    def _process_image(self, file_path: str, params: dict[str, Any]) -> str:
        """图片统一经 PIL 归一化为 PNG（覆盖 bmp/tiff 等后端不直接支持的格式）。"""
        with Image.open(file_path) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return self._call_api(buf.getvalue(), params)

    def _call_api(self, png_bytes: bytes, params: dict[str, Any]) -> str:
        data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        # 必须用官方训练指令 `OCR:`：自然语言提问不在训练分布内，
                        # temp 0 贪心解码会死循环重复（部署实测，DEPLOY_PLAN 注意事项）
                        {"type": "text", "text": "OCR:"},
                    ],
                }
            ],
            "max_tokens": int(params.get("max_tokens", 8192)),
            "temperature": float(params.get("temperature", 0.0)),
        }

        # 实测约 15.7 秒/页，大页表格更久，超时给足余量
        response = requests.post(self.chat_url, json=payload, timeout=int(params.get("timeout_seconds", 300)))
        if response.status_code != 200:
            error_msg = f"API Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise DocumentParserException(error_msg, self.get_service_name(), f"http_{response.status_code}")

        choice = response.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            logger.warning("PaddleOCR-VL local output truncated at max_tokens; page content may be incomplete")
        return _convert_table_markers(choice["message"]["content"]).strip()
