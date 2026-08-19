"""Test formula detection and formula block merging in _post_process_paragraphs."""

from yuxi.services.domain_factory_service import DomainFactoryService


def _service():
    return DomainFactoryService.__new__(DomainFactoryService)


def test_simple_formula_detected():
    """P=Ci/Co should be detected as a formula expression."""
    assert _service()._is_formula("P=Ci/Co") is True
    assert _service()._is_formula("v=q/A") is True
    assert _service()._is_formula("Q=C×V") is True
    assert _service()._is_formula("P=Ci÷Co") is True
    # Not a formula: narrative sentence with =
    assert _service()._is_formula("结果表明=该区域环境质量良好。") is False


def test_formula_block_merged():
    """Formula lead-in + expression + variable defs should merge into one block."""
    md = (
        "#### 3.3.1 test\n"
        "本次评价采用单因子污染指数法，计算公式为：\n"
        "\n"
        "P=Ci/Co\n"
        "\n"
        "式中：P－单因子污染指数（无量纲）；\n"
        "\n"
        "Ci―污染物的浓度值（mg/Nm3）；\n"
        "\n"
        "Co－标准浓度限值（mg/Nm3）。\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)

    formulas = [p for p in paras if p.get("classify_type") == "formula"]
    assert len(formulas) == 1, f"Expected 1 formula block, got {len(formulas)}: {[p.get('content','')[:50] for p in paras]}"

    f = formulas[0]
    content = f.get("content", "")
    assert "单因子污染指数法" in content
    assert "P=Ci/Co" in content
    assert "式中：P" in content
    assert "Ci―" in content
    assert "Co－" in content


def test_formula_no_merge_without_lead():
    """Formula expression without lead-in should NOT trigger merge (but still detected by classify)."""
    md = (
        "#### 3.3.1 test\n"
        "some text.\n"
        "P=Ci/Co\n"
        "more text.\n"
    )
    svc = _service()
    paras = svc._parse_markdown_to_paragraphs(md)
    # classify_paragraphs runs separately; _is_formula detects standalone formula lines
    classified = svc.classify_paragraphs(paras)
    formulas = [p for p in classified if p.get("classify_type") == "formula"]
    assert len(formulas) == 1  # classified as formula, but standalone


def test_formula_block_classified_via_classify_paragraphs():
    """classify_paragraphs should preserve the formula type set by post-processing."""
    md = (
        "#### 3.3.1 test\n"
        "计算公式为：\n"
        "P=Ci/Co\n"
        "式中：P－指数；\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)
    # classify_paragraphs skips paragraphs with pre-set classify_type
    classified = _service().classify_paragraphs(paras)
    formulas = [p for p in classified if p.get("classify_type") == "formula"]
    assert len(formulas) == 1, f"Formula type lost during classify: {[p.get('classify_type') for p in classified]}"
