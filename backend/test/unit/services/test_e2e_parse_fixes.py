"""E2E verification of _parse_markdown_to_paragraphs fixes:
1. Title duplication in Markdown headings
2. Table context merging (bold title/number)
3. Sub-point merging
"""

from yuxi.services.domain_factory_service import DomainFactoryService


def _service() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


def test_title_no_duplication():
    """Markdown heading body paragraphs should have correct title without duplication."""
    md = "#### 3.1.1 title-content\nparagraph content here.\n"
    paras = _service()._parse_markdown_to_paragraphs(md)

    heading = [p for p in paras if p.get("is_title")][0]
    body = [p for p in paras if not p.get("is_title") and not p.get("is_table")][0]

    assert heading["title"] == "title-content", f"heading title: {heading['title']}"
    assert body["title"] == "3.1.1 title-content", f"body title: {body['title']}"
    assert "3.1.1 3.1.1" not in body["title"], f"duplicated numbering in: {body['title']}"


def test_table_context_merged():
    """Standalone bold lines before a table should merge as table_context.

    Uses HTML tables (production path): real ETL always provides html_content.
    """
    html = "<table><tr><th>col1</th><th>col2</th></tr><tr><td>a</td><td>b</td></tr></table>"
    md = (
        "#### 3.1.2 test\n"
        "intro text.\n\n"
        "**table-title**\n\n"
        "**table-3.1-1**\n\n"
        "| col1 | col2 |\n"
        "| a    | b    |\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md, html_content=html)

    # Bold standalone lines should NOT appear as separate body paragraphs
    body_contents = [
        (p.get("content") or "")
        for p in paras
        if not p.get("is_title") and not p.get("is_table")
    ]
    for content in body_contents:
        assert "**table-title**" not in content, f"bold title still standalone: {content[:60]}"
        assert "**table-3.1-1**" not in content, f"table number still standalone: {content[:60]}"

    # Table should have table_context
    tables = [p for p in paras if p.get("is_table")]
    assert len(tables) == 1
    ctx = tables[0].get("table_context", [])
    assert "table-title" in ctx, f"table missing title context: {ctx}"
    assert "table-3.1-1" in ctx, f"table missing number context: {ctx}"


def test_subpoint_merged():
    """Sub-point markers like '1）xxx' should merge with following content."""
    md = (
        "#### 3.1.3 test\n"
        "1）river-name\n"
        "river-description with details.\n"
        "2）another-river\n"
        "another description.\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)

    merged = [p for p in paras if p.get("subpoint_merged")]
    assert len(merged) == 2, f"expected 2 merged sub-points, got {len(merged)}"
    assert "river-name" in merged[0]["content"]
    assert "river-description" in merged[0]["content"]
    assert "another-river" in merged[1]["content"]
    assert "another description" in merged[1]["content"]


def test_subpoint_no_merge_with_heading():
    """Sub-point followed by a heading should NOT merge."""
    md = (
        "#### 3.1.3 test\n"
        "1）sub-point\n"
        "#### 3.1.4 next-section\n"
        "content here.\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)
    merged = [p for p in paras if p.get("subpoint_merged")]
    assert len(merged) == 0, f"should not merge with heading, got {len(merged)}"


def test_table_context_no_merge_across_heading():
    """Bold lines before table but separated by heading should NOT merge."""
    html = "<table><tr><td>x</td></tr></table>"
    md = (
        "**bold-title**\n\n"
        "#### 3.1.2 heading\n"
        "text\n\n"
        "| x |\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md, html_content=html)
    tables = [p for p in paras if p.get("is_table")]
    # The bold line is before a heading, not directly before the table
    ctx = tables[0].get("table_context", []) if tables else []
    assert "bold-title" not in ctx, f"should not merge across heading: {ctx}"
