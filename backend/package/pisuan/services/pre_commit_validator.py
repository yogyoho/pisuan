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
            # [pisuan-custom] spec-W1 (2026-10-06, D7 裁决): generalized 门收敛 prose/parameter 两类。
            # narrative 不入门——它仅存 legacy 值（旧摘要形态模板无 generalized，bug-336 产物），
            # 纳入会让 legacy 任务新增性提交失败（违反消费面双读不回归）；新分类器不再产出 narrative。
            # 原 text_pattern 检查改查 generalized：text_pattern 在段落侧无任何写入方（bug-370 恒假门，
            # bug-354 修复激活 L1 门后凡含参数段任务必 COMMIT_FAILED）。
            if para.get("classify_type") not in ("prose", "parameter"):
                continue
            para_id = para.get("id", "?")
            tmpl = para.get("template") or {}
            generalized = (tmpl.get("generalized") or "").strip()
            if not generalized:
                errors.append(f"段落 {para_id}: generalized 为空")
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

        return ValidationResult(passed=len(errors) == 0, errors=errors, warnings=warnings)
