"""Docling DOCX 转换子进程入口。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    """执行单个 DOCX 转换并把 Markdown 写入输出文件。"""
    if len(argv) != 4:
        print("usage: docx_docling_worker.py <file> <params-json> <output>", file=sys.stderr)
        return 2

    from yuxi.knowledge.parser.unified import _convert_with_docling

    file_path = Path(argv[1])
    params = json.loads(argv[2])
    output_path = Path(argv[3])
    markdown = _convert_with_docling(file_path, params=params)
    output_path.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
