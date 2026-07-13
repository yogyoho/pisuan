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
