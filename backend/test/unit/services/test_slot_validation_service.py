import pytest
from yuxi.services.slot_validation_service import (
    SlotValidationResult,
    SlotValidationService,
    ValidationLevel,
)


@pytest.mark.asyncio
async def test_type_consistency_number_slot_vs_number_entity_passes():
    """slot.type=number, entity.type=number → 一致,通过"""
    service = SlotValidationService()
    slot = {"name": "产能", "type": "number"}
    entity_schema = {"name": "项目主体", "type": "number"}
    result = service._check_type_consistency(slot, entity_schema)
    assert result.level == ValidationLevel.PASS


@pytest.mark.asyncio
async def test_type_consistency_number_slot_vs_text_entity_warns():
    """slot.type=number, entity.type=string(法规标准) → 类型冲突警告"""
    service = SlotValidationService()
    slot = {"name": "排放浓度", "type": "number"}
    entity_schema = {"name": "法规标准", "type": "string"}
    result = service._check_type_consistency(slot, entity_schema)
    assert result.level == ValidationLevel.WARN
    assert "类型冲突" in result.message


@pytest.mark.asyncio
async def test_type_consistency_no_entity_ref_passes():
    """slot 无 entity_ref → 跳过类型检查,通过"""
    service = SlotValidationService()
    slot = {"name": "未知参数", "type": "string"}
    result = service._check_type_consistency(slot, None)
    assert result.level == ValidationLevel.PASS


@pytest.mark.asyncio
async def test_conflict_detection_same_slot_different_entities():
    """同名 slot 绑不同 entity → 冲突"""
    service = SlotValidationService()
    slot_validations = [
        SlotValidationResult(slot_name="面积", level=ValidationLevel.PASS, message="", entity_ref="工程参数"),
        SlotValidationResult(slot_name="面积", level=ValidationLevel.PASS, message="", entity_ref="空间边界"),
        SlotValidationResult(slot_name="产能", level=ValidationLevel.PASS, message="", entity_ref="项目主体"),
    ]
    conflicts = service._detect_conflicts(slot_validations)
    assert len(conflicts) == 1
    assert conflicts[0].slot_name == "面积"
    assert conflicts[0].level == ValidationLevel.WARN


@pytest.mark.asyncio
async def test_conflict_detection_no_conflict():
    """无冲突场景"""
    service = SlotValidationService()
    slot_validations = [
        SlotValidationResult(slot_name="产能", level=ValidationLevel.PASS, message="", entity_ref="项目主体"),
        SlotValidationResult(slot_name="面积", level=ValidationLevel.PASS, message="", entity_ref="工程参数"),
    ]
    conflicts = service._detect_conflicts(slot_validations)
    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_conflict_detection_same_slot_same_entity_no_conflict():
    """同名 slot 绑相同 entity → 无冲突"""
    service = SlotValidationService()
    slot_validations = [
        SlotValidationResult(slot_name="产能", level=ValidationLevel.PASS, message="", entity_ref="项目主体"),
        SlotValidationResult(slot_name="产能", level=ValidationLevel.PASS, message="", entity_ref="项目主体"),
    ]
    conflicts = service._detect_conflicts(slot_validations)
    assert len(conflicts) == 0
