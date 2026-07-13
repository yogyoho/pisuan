import pytest
from yuxi.services.slot_validation_service import SlotValidationService, ValidationLevel


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
