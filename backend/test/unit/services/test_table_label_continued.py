"""Test that table labels with (continued) suffix are recognized and merged."""

from yuxi.services.domain_factory_service import DomainFactoryService


def _service():
    return DomainFactoryService.__new__(DomainFactoryService)


def test_table_label_with_continued_merged():
    """Table label '表3.3-6（续表）' should be recognized as table context."""
    html = "<table><tr><td>x</td></tr></table>"
    md = (
        "#### 3.3.2 test\n"
        "**地表水环境质量现状监测结果一览表**\n"
        "\n"
        "表3.3-6（续表）\n"
        "\n"
        "| data | value |\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md, html_content=html)

    tables = [p for p in paras if p.get("is_table")]
    assert len(tables) == 1

    ctx = tables[0].get("table_context", [])
    assert "地表水环境质量现状监测结果一览表" in ctx, f"Missing bold title: {ctx}"
    assert "表3.3-6（续表）" in ctx, f"Missing continued label: {ctx}"

    # Verify these are NOT standalone paragraphs
    for p in paras:
        if not p.get("is_title") and not p.get("is_table"):
            content = p.get("content") or ""
            assert "监测结果一览表" not in content, f"Bold title still standalone"
            assert "表3.3-6" not in content, f"Table number still standalone"
