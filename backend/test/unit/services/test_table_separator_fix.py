"""Test that markdown tables with separator lines are correctly detected and
bold/plain table context lines are merged into table_context.
"""

from yuxi.services.domain_factory_service import DomainFactoryService


def _service():
    return DomainFactoryService.__new__(DomainFactoryService)


def test_table_with_separator_detected_and_context_merged():
    """Table with |---|---| separator should be detected, and preceding bold lines merged."""
    html = "<table><tr><th>col1</th><th>col2</th></tr><tr><td>a</td><td>b</td></tr></table>"
    md = (
        "#### 3.1.2 test\n"
        "intro text.\n\n"
        "**table-title**\n\n"
        "**table-3.1-1**\n\n"
        "| item | unit | city1 | city2 |\n"
        "|------|------|-------|-------|\n"
        "| temp | C    | 9.2   | 9.1   |\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md, html_content=html)

    tables = [p for p in paras if p.get("is_table")]
    assert len(tables) == 1, f"Expected 1 table, got {len(tables)}"

    ctx = tables[0].get("table_context", [])
    assert "table-title" in ctx, f"Missing title in context: {ctx}"
    assert "table-3.1-1" in ctx, f"Missing number in context: {ctx}"

    for p in paras:
        if not p.get("is_title") and not p.get("is_table"):
            content = p.get("content") or ""
            assert "**table-title**" not in content, f"Still standalone: {content[:60]}"
            assert "**table-3.1-1**" not in content, f"Still standalone: {content[:60]}"


def test_table_separator_not_confused_with_data():
    """Single separator-like line should not be counted as a table row."""
    md = "#### 3.1 test\n|----------------|\nnormal text\n"
    paras = _service()._parse_markdown_to_paragraphs(md)

    tables = [p for p in paras if p.get("is_table")]
    assert len(tables) == 0, f"Separator alone should NOT be a table"


def test_plain_table_number_merged():
    """Plain (non-bold) table number like '表3.3-4' should also be merged as table context."""
    html = "<table><tr><td>x</td></tr></table>"
    md = (
        "#### 3.3.1 test\n"
        "**table-title**\n"
        "\n"
        "表3.3-4\n"
        "\n"
        "| data |\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md, html_content=html)

    tables = [p for p in paras if p.get("is_table")]
    assert len(tables) == 1

    ctx = tables[0].get("table_context", [])
    assert "table-title" in ctx, f"Missing bold title: {ctx}"
    assert "表3.3-4" in ctx, f"Missing plain table number: {ctx}"

    # Both should NOT appear as standalone paragraphs
    for p in paras:
        if not p.get("is_title") and not p.get("is_table"):
            content = p.get("content") or ""
            assert "**table-title**" not in content, f"Bold title still standalone: {content[:60]}"
            assert "表3.3-4" not in content, f"Plain number still standalone: {content[:60]}"


def test_bold_table_number_merged():
    """Bold table number like '**表3.1-1**' should be merged."""
    html = "<table><tr><td>x</td></tr></table>"
    md = (
        "#### 3.1.2 test\n"
        "**气象资料表**\n"
        "\n"
        "**表3.1-1**\n"
        "\n"
        "| item | value |\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md, html_content=html)

    tables = [p for p in paras if p.get("is_table")]
    assert len(tables) == 1

    ctx = tables[0].get("table_context", [])
    assert "气象资料表" in ctx
    assert "表3.1-1" in ctx
