import pytest
from yuxi.services.pre_commit_validator import PreCommitValidator, ValidationResult


@pytest.mark.asyncio
async def test_structure_valid_paragraphs_pass():
    """有效段落(有模板+text_pattern非空) → 通过"""
    validator = PreCommitValidator()
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "type": "parameter",
                "template": {"generalized": "{{矿区}}位于{{位置}}", "text_pattern": "{{矿区}}位于{{位置}}"},
            }
        ]
    }
    result = await validator.validate(task_detail)
    assert result.passed is True
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_structure_empty_text_pattern_fails():
    """text_pattern 为空 → 失败"""
    validator = PreCommitValidator()
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "type": "parameter",
                "template": {"generalized": "", "text_pattern": ""},
            }
        ]
    }
    result = await validator.validate(task_detail)
    assert result.passed is False
    assert any("text_pattern" in e for e in result.errors)


@pytest.mark.asyncio
async def test_structure_no_paragraphs_fails():
    """无段落 → 失败"""
    validator = PreCommitValidator()
    result = await validator.validate({"source_paragraphs": []})
    assert result.passed is False
    assert any("无段落" in e for e in result.errors)
