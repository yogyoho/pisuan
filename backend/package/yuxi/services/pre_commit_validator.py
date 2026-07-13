"""提交前验证关卡:commit 前校验任务数据质量,校验失败阻止提交。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PreCommitValidator:
    """提交前校验任务数据完整性。"""

    async def validate(self, task_detail: dict[str, Any]) -> ValidationResult:
        """校验任务详情,返回 ValidationResult。"""
        if task_detail is None:
            return ValidationResult(passed=False, errors=["任务不存在"])
        errors: list[str] = []
        warnings: list[str] = []

        paragraphs = task_detail.get("source_paragraphs", [])
        if not paragraphs:
            errors.append("无段落数据,无法入库")
            return ValidationResult(passed=False, errors=errors, warnings=warnings)

        for para in paragraphs:
            if para.get("type") != "parameter":
                continue
            para_id = para.get("id", "?")
            tmpl = para.get("template") or {}
            text_pattern = (tmpl.get("text_pattern") or "").strip()
            if not text_pattern:
                errors.append(f"段落 {para_id}: text_pattern 为空")
                continue

            slots = tmpl.get("slots") or []
            if len(slots) > 15:
                warnings.append(f"段落 {para_id}: slot 数量 {len(slots)} 超过 15")

            seen: set[str] = set()
            for slot in slots:
                slot_name = (slot.get("name") or "").strip()
                if not slot_name:
                    errors.append(f"段落 {para_id}: slot名称为空")
                    continue
                if slot_name.isdigit():
                    errors.append(f"段落 {para_id}: slot名称不能为纯数字: {slot_name}")
                if slot_name in seen:
                    warnings.append(f"段落 {para_id}: 重复 slot 签名: {slot_name}")
                seen.add(slot_name)

        return ValidationResult(
            passed=len(errors) == 0, errors=errors, warnings=warnings
        )
