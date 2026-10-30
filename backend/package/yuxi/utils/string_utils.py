"""通用字符串处理工具。"""

import re

TRUNCATION_MARKER = "\n[内容已截断]"


def truncate_utf8(value: object, max_bytes: int) -> tuple[str, bool]:
    """在 UTF-8 字节预算内截断文本并返回是否发生截断。"""
    text_value = str(value or "")
    encoded = text_value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text_value, False

    marker_bytes = TRUNCATION_MARKER.encode("utf-8")
    if max_bytes < len(marker_bytes):
        return "", True

    prefix = encoded[: max_bytes - len(marker_bytes)].decode("utf-8", errors="ignore")
    if not prefix:
        return TRUNCATION_MARKER.strip(), True
    return f"{prefix}{TRUNCATION_MARKER}", True


def normalize_chapter_key(title: str) -> str:
    """章节标题归一化：去前导多级编号 + 去所有内部空白（半角空格、全角空格、制表符等）。

    作为章节聚合身份键（canonical_chapter_key）的统一收口，如「1  总  则」→「总则」。纯编号返回空串。
    """
    text = (title or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)*", text):
        return ""
    while True:
        m = re.match(r"^(\d+(?:\.\d+)*)\s*(\S.*)$", text)
        if not m:
            break
        text = m.group(2).strip()
    # \s 对 str 模式为 Unicode 语义,已覆盖全角空格(U+3000)与制表符
    return re.sub(r"\s+", "", text)
