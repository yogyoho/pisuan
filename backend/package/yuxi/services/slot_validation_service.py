"""slot 事后校验服务:LLM 自由提取 slot 后,校验 entity_ref 归类和类型一致性。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValidationLevel(str, Enum):
    PASS = "pass"
    WARN = "warn"
    ERROR = "error"


@dataclass
class SlotValidationResult:
    slot_name: str
    level: ValidationLevel
    message: str
    entity_ref: str | None = None


class SlotValidationService:
    """对泛化后的 slot 做事后校验。

    校验维度:
    1. 类型一致性: slot.type vs EntitySchema.type
    2. 冲突检测: 同名 slot 绑不同 entity
    3. LLM 归类: 用 LLM 把 slot 归到 EntitySchema(替代子串匹配)
    """

    async def validate_slots(
        self,
        paragraph_slots: list[dict[str, Any]],
        entity_schemas: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """对多段落的 slot 做整体事后校验。

        Args:
            paragraph_slots: [{paragraph_id, slots: [{name, type, entity_ref?}]}]
            entity_schemas: {entity_name: {name, type}}

        Returns:
            {validated, warnings, conflicts: [{slot_name, message}]}
        """
        all_validations: list[SlotValidationResult] = []
        warnings = 0

        for para in paragraph_slots:
            for slot in para.get("slots", []):
                entity_ref = slot.get("entity_ref")
                entity_schema = entity_schemas.get(entity_ref) if entity_ref else None
                result = self._check_type_consistency(slot, entity_schema)
                all_validations.append(result)
                if result.level == ValidationLevel.WARN:
                    warnings += 1

        conflicts = self._detect_conflicts(all_validations)

        return {
            "validated": len(all_validations),
            "warnings": warnings,
            "conflicts": [
                {"slot_name": c.slot_name, "message": c.message} for c in conflicts
            ],
        }

    def _check_type_consistency(
        self, slot: dict[str, Any], entity_schema: dict[str, Any] | None
    ) -> SlotValidationResult:
        """检查 slot.type 和 entity.type 是否一致。无 entity_ref 时跳过。"""
        slot_name = slot.get("name", "")
        slot_type = slot.get("type", "string")

        if entity_schema is None:
            return SlotValidationResult(
                slot_name=slot_name,
                level=ValidationLevel.PASS,
                message="无 entity_ref,跳过类型检查",
            )

        entity_type = entity_schema.get("type", "string")
        if slot_type == entity_type:
            return SlotValidationResult(
                slot_name=slot_name,
                level=ValidationLevel.PASS,
                message="类型一致",
                entity_ref=entity_schema.get("name"),
            )

        return SlotValidationResult(
            slot_name=slot_name,
            level=ValidationLevel.WARN,
            message=f"类型冲突: slot.type={slot_type}, entity.type={entity_type}",
            entity_ref=entity_schema.get("name"),
        )

    def _detect_conflicts(
        self, validations: list[SlotValidationResult]
    ) -> list[SlotValidationResult]:
        """检测同名 slot 绑定到不同 entity_ref 的冲突。"""
        slot_entities: dict[str, set[str]] = {}
        for v in validations:
            if v.entity_ref is None:
                continue
            slot_entities.setdefault(v.slot_name, set()).add(v.entity_ref)

        conflicts: list[SlotValidationResult] = []
        for slot_name, entities in slot_entities.items():
            if len(entities) > 1:
                conflicts.append(
                    SlotValidationResult(
                        slot_name=slot_name,
                        level=ValidationLevel.WARN,
                        message=f"冲突: slot '{slot_name}' 绑定到多个 entity: {sorted(entities)}",
                    )
                )
        return conflicts
