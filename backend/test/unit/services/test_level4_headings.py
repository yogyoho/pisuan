"""Test that level-4 headings (e.g., ##### 3.3.1.1) get proper 4-level section_path."""

from yuxi.services.domain_factory_service import DomainFactoryService


def _service():
    return DomainFactoryService.__new__(DomainFactoryService)


def test_level4_heading_section_path():
    """Level-4 heading (#####) should have 4-element section_path."""
    md = (
        "## 3 test\n"
        "### 3.3 sub\n"
        "#### 3.3.1 child\n"
        "##### 3.3.1.1 leaf\n"
        "body content.\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)

    # Find the level-4 heading
    headings = [p for p in paras if p.get("is_title")]
    assert len(headings) == 4, f"Expected 4 headings, got {len(headings)}"

    l4 = headings[3]  # The ##### heading
    assert l4["level"] == 4, f"Expected level 4, got {l4['level']}"
    assert l4["section_path"] == ["3", "3.3", "3.3.1", "3.3.1.1"], (
        f"Expected 4-level section_path, got {l4['section_path']}"
    )

    # Body paragraph under level-4 heading should have 4-level section_path
    body = [p for p in paras if not p.get("is_title")][0]
    assert body["section_path"] == ["3", "3.3", "3.3.1", "3.3.1.1"], (
        f"Body paragraph should inherit 4-level path, got {body['section_path']}"
    )


def test_level3_still_works():
    """Existing level-3 behavior should be unchanged."""
    md = (
        "## 3 test\n"
        "### 3.3 sub\n"
        "#### 3.3.1 child\n"
        "body.\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)
    headings = [p for p in paras if p.get("is_title")]
    l3 = headings[2]
    assert l3["level"] == 3
    assert l3["section_path"] == ["3", "3.3", "3.3.1"]
