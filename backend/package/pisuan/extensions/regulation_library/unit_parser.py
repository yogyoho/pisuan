"""按 doc_type 从 chunk 文本解析结构单元（条款/法条/章节/表格）。

纯函数模块，供 enrichment_service 调用。
"""

from __future__ import annotations

import re

# 表格标题: 表1 / 表 2-1
_TABLE_RE = re.compile(r"^表\s*(\d[\d\-]*)\s*(.*)$", re.MULTILINE)
# 标准条款: 4.2 标题
_CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$", re.MULTILINE)
# 法条: 第X条
_ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百千零〇]+条)\s*(.*)$", re.MULTILINE)
# 中文章节号: 三、 或 （一）
_CN_SECTION_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.*)$", re.MULTILINE)


def parse_chunk_unit(content: str, doc_type: str) -> dict | None:
    """从 chunk 内容解析结构单元信息。

    Returns:
        {unit_no, unit_type, parent_unit, title} 或 None（无结构线索）
    """
    text = (content or "").strip()
    if not text:
        return None

    # 表格优先（所有 doc_type 通用）
    m = _TABLE_RE.search(text[:200])
    if m and ("<table" in text or "|" in text):
        return {"unit_no": f"表{m.group(1)}", "unit_type": "table", "parent_unit": None, "title": m.group(2).strip()}

    if doc_type == "law" or doc_type.endswith("regulation") or doc_type.endswith("rule"):
        m = _ARTICLE_RE.search(text[:100])
        if m:
            return {
                "unit_no": m.group(1),
                "unit_type": "article",
                "parent_unit": None,
                "title": m.group(2).strip()[:100],
            }

    if doc_type in ("technical_standard",):
        m = _CLAUSE_RE.search(text[:100])
        if m:
            num = m.group(1)
            parent = ".".join(num.split(".")[:-1]) or None
            return {"unit_no": num, "unit_type": "clause", "parent_unit": parent, "title": m.group(2).strip()[:100]}

    # 规划/政策/项目资料: 中文编号章节
    m = _CN_SECTION_RE.search(text[:100])
    if m:
        return {"unit_no": m.group(1), "unit_type": "section", "parent_unit": None, "title": m.group(2).strip()[:100]}

    # fallback: 数字编号
    m = _CLAUSE_RE.search(text[:100])
    if m:
        num = m.group(1)
        parent = ".".join(num.split(".")[:-1]) or None
        return {"unit_no": num, "unit_type": "clause", "parent_unit": parent, "title": m.group(2).strip()[:100]}

    return None
