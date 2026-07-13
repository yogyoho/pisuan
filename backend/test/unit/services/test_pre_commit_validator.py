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


@pytest.mark.asyncio
async def test_slot_quality_empty_name_fails():
    """slot.name 为空 → 失败"""
    validator = PreCommitValidator()
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "type": "parameter",
                "template": {
                    "text_pattern": "{{}}",
                    "slots": [{"name": "", "type": "string"}],
                },
            }
        ]
    }
    result = await validator.validate(task_detail)
    assert result.passed is False
    assert any("slot名称" in e or "slot name" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_slot_quality_too_many_slots_warns():
    """slot 数量 > 15 → 警告(不阻塞)"""
    validator = PreCommitValidator()
    slots = [{"name": f"slot_{i}", "type": "string"} for i in range(20)]
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "type": "parameter",
                "template": {"text_pattern": "x", "slots": slots},
            }
        ]
    }
    result = await validator.validate(task_detail)
    assert result.passed is True  # 警告不阻塞
    assert any("slot 数量" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_slot_quality_pure_digit_name_fails():
    """slot.name 为纯数字 → 失败"""
    validator = PreCommitValidator()
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "type": "parameter",
                "template": {
                    "text_pattern": "{{123}}",
                    "slots": [{"name": "123", "type": "string"}],
                },
            }
        ]
    }
    result = await validator.validate(task_detail)
    assert result.passed is False
    assert any("纯数字" in e for e in result.errors)


@pytest.mark.asyncio
async def test_slot_quality_duplicate_signature_warns():
    """同段落两个 slot 同名 → 警告(重复 slot 签名)"""
    validator = PreCommitValidator()
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "type": "parameter",
                "template": {
                    "text_pattern": "{{矿区}}{{矿区}}",
                    "slots": [
                        {"name": "矿区", "type": "string"},
                        {"name": "矿区", "type": "string"},
                    ],
                },
            }
        ]
    }
    result = await validator.validate(task_detail)
    assert result.passed is True  # 警告不阻塞
    assert any("重复 slot 签名" in w for w in result.warnings)
