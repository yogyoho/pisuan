"""{{REF:chXX/表X-Y}} 位置编号解析器。assemble 时扫各章 content_md 现算。"""

import re

_REF_RE = re.compile(r"\{\{REF:([^/]+)/([^}]+)\}\}")
_CAP_TABLE_RE = re.compile(r"\*\*(表[\d\-\.]+)\s*[^*\n]*\*\*")
_CAP_FIGURE_RE = re.compile(r"!\[(图[\d\-\.]+)[^\]]*\]")
_CAP_SECTION_RE = re.compile(r"^#{1,6}\s*((?:\d+(?:\.\d+)*)\s+\S.*)$", re.MULTILINE)


def _chapter_alias(order: int) -> str:
    return f"ch{order:02d}"


def _build_target_map(chapters: list[dict]) -> dict[str, set[str]]:
    """{chXX: {可引用目标集合}}"""
    targets: dict[str, set[str]] = {}
    for ch in chapters:
        order = ch.get("chapter_order")
        if order is None:
            continue
        alias = _chapter_alias(order)
        md = ch.get("content_md") or ""
        s = set()
        s.update(m for m in _CAP_TABLE_RE.findall(md))
        s.update(m for m in _CAP_FIGURE_RE.findall(md))
        s.update(_CAP_SECTION_RE.findall(md))  # "N.N 标题"
        targets[alias] = s
    return targets


def resolve_refs(chapters: list[dict]) -> tuple[str, list[dict]]:
    """按 chapter_order 合并章节,解析 {{REF}}。返回 (merged_markdown, unresolved_refs)。"""
    ordered = sorted([c for c in chapters if c.get("content_md")], key=lambda c: c.get("chapter_order") or 9999)
    merged = "\n\n".join(c["content_md"] for c in ordered)
    targets = _build_target_map(ordered)
    unresolved: list[dict] = []

    def _replace(m: re.Match) -> str:
        ch_alias, target = m.group(1).strip(), m.group(2).strip()
        avail = targets.get(ch_alias)
        if avail is None:
            unresolved.append({"ref": m.group(0), "reason": f"章节 {ch_alias} 未写入"})
            return m.group(0)  # 保留可见占位符
        # 精确或包含匹配目标
        if target in avail or any(target in t for t in avail):
            return f"见{target}"
        unresolved.append({"ref": m.group(0), "reason": f"{ch_alias} 中未找到 {target}"})
        return m.group(0)

    resolved = _REF_RE.sub(_replace, merged)
    return resolved, unresolved
