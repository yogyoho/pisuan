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
    slot = {"name": "产能", "type": "number", "entity_ref": "project_main"}
    entity_schema = {"name": "项目主体", "type": "number"}
    result = service._check_type_consistency(slot, entity_schema)
    assert result.level == ValidationLevel.PASS


@pytest.mark.asyncio
async def test_type_consistency_number_slot_vs_text_entity_warns():
    """slot.type=number, entity.type=string(法规标准) → 类型冲突警告"""
    service = SlotValidationService()
    slot = {"name": "排放浓度", "type": "number", "entity_ref": "regulation"}
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
async def test_type_consistency_entity_ref_set_but_schema_missing_warns():
    """entity_ref 有值但在 entity_schemas 中找不到 → WARN(可能是陈旧/不一致)"""
    service = SlotValidationService()
    slot = {"name": "产能", "type": "number", "entity_ref": "stale_entity"}
    result = service._check_type_consistency(slot, None)
    assert result.level == ValidationLevel.WARN
    assert "stale_entity" in result.message


@pytest.mark.asyncio
async def test_type_consistency_real_entity_schema_no_type_field_passes():
    """真实 EntitySchema 结构(来自 coal_eia_entity_types.json)无 type 字段 → 跳过类型检查,PASS"""
    service = SlotValidationService()
    slot = {"name": "生产能力", "type": "number", "entity_ref": "engineering_params"}
    # 从 backend/server/coal_eia_entity_types.json 复制的真实结构
    entity_schema = {
        "id": "engineering_params",
        "name": "工程参数",
        "category": "基础工程实体",
        "description": "生产能力（万吨/年）、设计服务年限、井田面积、开采深度、煤层厚度",
        "examples": ["生产能力", "设计服务年限", "井田面积", "开采深度", "煤层厚度"],
        "keywords": ["生产能力", "服务年限", "井田面积", "开采深度", "煤层厚度", "工程参数"],
    }
    result = service._check_type_consistency(slot, entity_schema)
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


@pytest.mark.asyncio
async def test_validate_slots_returns_structured_report():
    """validate_slots 返回 {validated, warnings, conflicts}"""
    service = SlotValidationService()
    paragraph_slots = [
        {
            "paragraph_id": "p1",
            "slots": [
                {"name": "产能", "type": "number", "entity_ref": "项目主体"},
                {"name": "面积", "type": "number", "entity_ref": "工程参数"},
            ],
        },
        {
            "paragraph_id": "p2",
            "slots": [
                {"name": "面积", "type": "number", "entity_ref": "空间边界"},
            ],
        },
    ]
    entity_schemas = {
        "项目主体": {"name": "项目主体", "type": "number"},
        "工程参数": {"name": "工程参数", "type": "number"},
        "空间边界": {"name": "空间边界", "type": "number"},
    }
    report = await service.validate_slots(paragraph_slots, entity_schemas)
    assert report["validated"] == 3
    assert report["warnings"] == 0
    assert len(report["conflicts"]) == 1
    assert report["conflicts"][0]["slot_name"] == "面积"
    assert report["conflicts"][0]["paragraph_ids"] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_validate_slots_empty_input():
    """空输入返回零计数报告"""
    service = SlotValidationService()
    report = await service.validate_slots([], {})
    assert report["validated"] == 0
    assert report["warnings"] == 0
    assert report["conflicts"] == []


@pytest.mark.asyncio
async def test_validate_slots_real_structure_no_false_warnings():
    """使用 coal_eia_entity_types.json 真实结构(entity_schemas 无 type 字段)集成测试。

    真实 EntitySchema 没有 type 字段,不应产生类型冲突的误报。
    冲突检测仍正常工作(同名 slot 绑不同 entity)。
    """
    service = SlotValidationService()
    # 从 backend/server/coal_eia_entity_types.json 复制的真实结构
    entity_schemas = {
        "engineering_params": {
            "id": "engineering_params",
            "name": "工程参数",
            "category": "基础工程实体",
            "description": "生产能力（万吨/年）、设计服务年限、井田面积、开采深度、煤层厚度",
            "examples": ["生产能力", "设计服务年限", "井田面积", "开采深度", "煤层厚度"],
            "keywords": ["生产能力", "服务年限", "井田面积", "开采深度", "煤层厚度", "工程参数"],
        },
        "spatial_boundary": {
            "id": "spatial_boundary",
            "name": "空间边界",
            "category": "敏感目标与空间实体",
            "description": "矿区范围、井田边界、错动线、首采区、辅助生产区",
            "examples": ["矿区范围", "井田边界", "错动线"],
            "keywords": ["矿区范围", "井田边界", "错动线", "空间边界"],
        },
    }
    paragraph_slots = [
        {
            "paragraph_id": "para_001",
            "slots": [
                {"name": "井田面积", "type": "number", "entity_ref": "engineering_params"},
                {"name": "矿区范围", "type": "string", "entity_ref": "spatial_boundary"},
            ],
        },
        {
            "paragraph_id": "para_002",
            "slots": [
                {"name": "井田面积", "type": "number", "entity_ref": "spatial_boundary"},
            ],
        },
    ]
    report = await service.validate_slots(paragraph_slots, entity_schemas)
    assert report["validated"] == 3
    # 真实 EntitySchema 无 type 字段 → 不产生类型冲突误报
    assert report["warnings"] == 0
    # 但冲突检测仍工作: "井田面积" 绑了两个不同 entity
    assert len(report["conflicts"]) == 1
    assert report["conflicts"][0]["slot_name"] == "井田面积"
    assert sorted(report["conflicts"][0]["paragraph_ids"]) == ["para_001", "para_002"]


@pytest.mark.asyncio
async def test_validate_slots_entity_ref_missing_from_schemas_warns():
    """entity_ref 有值但在 entity_schemas 中找不到 → WARN"""
    service = SlotValidationService()
    paragraph_slots = [
        {
            "paragraph_id": "p1",
            "slots": [
                {"name": "产能", "type": "number", "entity_ref": "stale_ref"},
            ],
        },
    ]
    entity_schemas = {}
    report = await service.validate_slots(paragraph_slots, entity_schemas)
    assert report["validated"] == 1
    assert report["warnings"] == 1
    assert report["conflicts"] == []
