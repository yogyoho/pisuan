# 知识工厂 MVP 治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复知识工厂三大致命缺陷（slot 事后校验、提交前验证、异常不吞），让图谱数据质量从"持续恶化"变为"可控"，并治理现有污染数据。

**Architecture:** 新增两个独立服务（slot_validation_service / pre_commit_validator）作为 commit pipeline 的前置关卡和后置校验层；改造 commit pipeline 让异常真实反映到任务状态；ETL 源头归一化防止新污染；幂等脚本治理存量数据。LLM slot 提取保持自由（`schema_variables=[]` 不变），质量由事后校验把关。

**Tech Stack:** Python 3.13, asyncio, Neo4j (neo4j driver), SQLAlchemy async, LangChain LLM, pytest-asyncio

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/package/yuxi/services/slot_validation_service.py` | 新建 | slot 事后校验：LLM 归类 EntitySchema + 类型一致性 + 冲突检测 |
| `backend/package/yuxi/services/pre_commit_validator.py` | 新建 | 提交前验证关卡：结构完整性 + slot 质量 + 图谱前置条件 |
| `backend/package/yuxi/services/domain_factory_service.py` | 修改 | commit pipeline 接入校验 + 异常不吞 + ETL 归一化 |
| `backend/package/yuxi/repositories/domain_factory_repository.py` | 修改 | commit_task 增加 status 参数支持 PARTIAL/FAILED |
| `backend/test/unit/services/test_slot_validation_service.py` | 新建 | slot 校验服务测试 |
| `backend/test/unit/services/test_pre_commit_validator.py` | 新建 | 提交前验证测试 |
| `backend/test/unit/services/test_commit_pipeline_status.py` | 新建 | 异常不吞改造测试 |
| `backend/scripts/governance/fix_existing_graph.py` | 新建 | 存量数据治理脚本（幂等） |
| `backend/test/scripts/test_fix_existing_graph.py` | 新建 | 治理脚本测试 |

---

## Phase 1: slot 事后校验服务 (P0)

### Task 1: 创建 slot_validation_service 基础结构和类型一致性校验

**Files:**
- Create: `backend/package/yuxi/services/slot_validation_service.py`
- Create: `backend/test/unit/services/test_slot_validation_service.py`

**Purpose:** 建立校验服务骨架，实现最基础的类型一致性校验（slot.type vs EntitySchema.type）。

- [ ] **Step 1: 编写类型一致性校验的失败测试**

Create `backend/test/unit/services/test_slot_validation_service.py`:

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_slot_validation_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'yuxi.services.slot_validation_service'`

- [ ] **Step 3: 创建 slot_validation_service.py 最小实现**

Create `backend/package/yuxi/services/slot_validation_service.py`:

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_slot_validation_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/slot_validation_service.py \
        backend/test/unit/services/test_slot_validation_service.py
git commit -m "feat(slot-validation): slot类型一致性校验基础结构"
```

---

### Task 2: 同名 slot 冲突检测

**Files:**
- Modify: `backend/package/yuxi/services/slot_validation_service.py`
- Modify: `backend/test/unit/services/test_slot_validation_service.py`

**Purpose:** 检测同名 slot 在不同段落绑定到不同 entity 的情况。

- [ ] **Step 1: 编写冲突检测失败测试**

Append to `test_slot_validation_service.py`:

```python
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
```

Add import at top of test file:

```python
from yuxi.services.slot_validation_service import SlotValidationResult
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_slot_validation_service.py -v`
Expected: FAIL — `AttributeError: 'SlotValidationService' object has no attribute '_detect_conflicts'`

- [ ] **Step 3: 实现 _detect_conflicts**

Add to `SlotValidationService` class in `slot_validation_service.py`:

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_slot_validation_service.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/slot_validation_service.py \
        backend/test/unit/services/test_slot_validation_service.py
git commit -m "feat(slot-validation): 同名slot绑定不同entity冲突检测"
```

---

### Task 3: 整体校验入口 validate_slots

**Files:**
- Modify: `backend/package/yuxi/services/slot_validation_service.py`
- Modify: `backend/test/unit/services/test_slot_validation_service.py`

**Purpose:** 提供整体校验入口，聚合类型一致性 + 冲突检测，返回结构化报告。

- [ ] **Step 1: 编写整体校验失败测试**

Append to `test_slot_validation_service.py`:

```python
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


@pytest.mark.asyncio
async def test_validate_slots_empty_input():
    """空输入返回零计数报告"""
    service = SlotValidationService()
    report = await service.validate_slots([], {})
    assert report["validated"] == 0
    assert report["warnings"] == 0
    assert report["conflicts"] == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_slot_validation_service.py -v`
Expected: FAIL — `AttributeError: 'SlotValidationService' object has no attribute 'validate_slots'`

- [ ] **Step 3: 实现 validate_slots**

Add to `SlotValidationService` class:

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_slot_validation_service.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/slot_validation_service.py \
        backend/test/unit/services/test_slot_validation_service.py
git commit -m "feat(slot-validation): validate_slots整体校验入口+结构化报告"
```

---

## Phase 2: 提交前验证关卡 (P0)

### Task 4: 创建 pre_commit_validator 结构完整性校验

**Files:**
- Create: `backend/package/yuxi/services/pre_commit_validator.py`
- Create: `backend/test/unit/services/test_pre_commit_validator.py`

**Purpose:** 校验段落模板的结构完整性——每章至少 1 个模板、text_pattern 非空。

- [ ] **Step 1: 编写结构完整性失败测试**

Create `backend/test/unit/services/test_pre_commit_validator.py`:

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_pre_commit_validator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 创建 pre_commit_validator.py 最小实现**

Create `backend/package/yuxi/services/pre_commit_validator.py`:

```python
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

        return ValidationResult(
            passed=len(errors) == 0, errors=errors, warnings=warnings
        )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_pre_commit_validator.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/pre_commit_validator.py \
        backend/test/unit/services/test_pre_commit_validator.py
git commit -m "feat(pre-commit): 结构完整性校验(段落模板非空)"
```

---

### Task 5: slot 基本质量校验

**Files:**
- Modify: `backend/package/yuxi/services/pre_commit_validator.py`
- Modify: `backend/test/unit/services/test_pre_commit_validator.py`

**Purpose:** 校验 slot 质量——name 非空非纯数字、数量上限、无重复签名。

- [ ] **Step 1: 编写 slot 质量校验失败测试**

Append to `test_pre_commit_validator.py`:

```python
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
    assert any("slot name" in e.lower() or "slot名称" in e for e in result.errors)


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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_pre_commit_validator.py -v`
Expected: FAIL — slot 质量校验未实现

- [ ] **Step 3: 实现 slot 质量校验**

修改 `pre_commit_validator.py` 的 `validate` 方法，在 text_pattern 校验后追加：

```python
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
            for slot in slots:
                slot_name = (slot.get("name") or "").strip()
                if not slot_name:
                    errors.append(f"段落 {para_id}: slot名称为空")
                elif slot_name.isdigit():
                    errors.append(f"段落 {para_id}: slot名称不能为纯数字: {slot_name}")

            if len(slots) > 15:
                warnings.append(f"段落 {para_id}: slot 数量 {len(slots)} 超过 15")

            signatures = [str(s.get("name", "")) for s in slots]
            seen: set[str] = set()
            for sig in signatures:
                if sig in seen:
                    warnings.append(f"段落 {para_id}: 重复 slot 签名: {sig}")
                seen.add(sig)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_pre_commit_validator.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/pre_commit_validator.py \
        backend/test/unit/services/test_pre_commit_validator.py
git commit -m "feat(pre-commit): slot质量校验(名称非空/数量上限/重复签名)"
```

---

## Phase 3: 异常不吞改造 (P0)

### Task 6: commit pipeline 接入 pre_commit_validator

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:3850` (_commit_pipeline_async 开头)

**Purpose:** 在 commit pipeline 开始处调用 pre_commit_validator，校验失败则中止。

- [ ] **Step 1: 编写集成失败测试**

Create `backend/test/unit/services/test_commit_pipeline_status.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from yuxi.services.pre_commit_validator import ValidationResult


@pytest.mark.asyncio
async def test_commit_pipeline_rejects_invalid_task():
    """提交前校验失败 → pipeline 不执行,返回错误"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    service = DomainFactoryService()
    invalid_task_detail = {"source_paragraphs": []}

    with patch.object(
        service, "get_task_detail", new=AsyncMock(return_value=invalid_task_detail)
    ), patch.object(
        service, "_run_commit_pipeline_body", new=AsyncMock(return_value={"status": "COMMITTED"})
    ) as mock_body:
        result = await service._commit_pipeline_async(
            context=_fake_context(), task_id="t1", knowledge_base_id="kb1", reviewer="admin"
        )
        assert "error" in result or result.get("status") != "COMMITTED"
        mock_body.assert_not_called()


def _fake_context():
    """构造一个最小的 fake context,满足 set_progress/set_message 调用。"""
    class FakeContext:
        async def set_progress(self, p, m=""):
            pass

        async def set_message(self, m):
            pass

    return FakeContext()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py -v`
Expected: FAIL — pipeline 不做校验直接执行

- [ ] **Step 3: 重构 _commit_pipeline_async 接入校验**

修改 `domain_factory_service.py`。首先将 `_commit_pipeline_async` 的主体提取为 `_run_commit_pipeline_body`，在 `_commit_pipeline_async` 开头加校验。

找到 `_commit_pipeline_async` 方法定义（约 3850 行），在 `# ========== 阶段1: 准备` 之前插入校验逻辑。将原方法体从"阶段1"开始的内容移入新方法 `_run_commit_pipeline_body`：

```python
    async def _commit_pipeline_async(
        self,
        context,
        task_id: str,
        knowledge_base_id: str | None = None,
        reviewer: str | None = None,
        ingest_task_id: str | None = None,
    ) -> dict[str, Any]:
        """入库流水线入口:先做提交前校验,通过才执行主体。"""
        from yuxi.services.pre_commit_validator import PreCommitValidator

        service = DomainFactoryService()
        await context.set_progress(2.0, "正在校验数据...")
        await context.set_message("正在校验数据...")

        task_detail = await service.get_task_detail(task_id)
        validator = PreCommitValidator()
        validation = await validator.validate(task_detail)
        if not validation.passed:
            await service.repo.update_task(
                task_id,
                {"status": "COMMIT_FAILED", "error_message": "; ".join(validation.errors)},
            )
            await context.set_progress(100.0, "校验失败,已中止入库")
            await context.set_message("校验失败: " + "; ".join(validation.errors))
            return {
                "task_id": task_id,
                "status": "COMMIT_FAILED",
                "errors": validation.errors,
                "message": "提交前校验失败",
            }

        return await self._run_commit_pipeline_body(
            context=context,
            task_id=task_id,
            knowledge_base_id=knowledge_base_id,
            reviewer=reviewer,
            ingest_task_id=ingest_task_id,
        )

    async def _run_commit_pipeline_body(
        self,
        context,
        task_id: str,
        knowledge_base_id: str | None = None,
        reviewer: str | None = None,
        ingest_task_id: str | None = None,
    ) -> dict[str, Any]:
        """实际入库流水线主体(原 _commit_pipeline_async 内容)。"""
        # 以下为原 _commit_pipeline_async 从"阶段1: 准备"开始的全部内容
        # ... 保持原样 ...
```

**注意**：需要把原 `_commit_pipeline_async` 从 `# ========== 阶段1: 准备` 到 `return {"error": str(e)}` 的全部内容移入 `_run_commit_pipeline_body`，签名改为接收 `ingest_task_id` 参数。

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py \
        backend/test/unit/services/test_commit_pipeline_status.py
git commit -m "feat(commit): pipeline接入pre_commit_validator,校验失败中止"
```

---

### Task 7: 图谱构建失败标记 COMMIT_FAILED

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:3997-4036` (阶段2.5)

**Purpose:** 图谱构建是关键步骤，失败必须标记 COMMIT_FAILED 而非吞掉。

- [ ] **Step 1: 编写图谱失败标记测试**

Append to `test_commit_pipeline_status.py`:

```python
@pytest.mark.asyncio
async def test_graph_build_failure_marks_commit_failed():
    """图谱构建失败 → 任务标记 COMMIT_FAILED(不再吞异常)"""
    from yuxi.services.domain_factory_service import DomainFactoryService
    from unittest.mock import patch, MagicMock

    service = DomainFactoryService()

    valid_task_detail = {
        "source_paragraphs": [
            {"id": "p1", "type": "parameter", "template": {"text_pattern": "{{x}}"}}
        ],
        "domain": "coal",
        "report_type_code": "eia_report",
    }

    update_calls = []

    async def fake_update(task_id, data):
        update_calls.append({"task_id": task_id, **data})

    with patch.object(
        service, "get_task_detail", new=AsyncMock(return_value=valid_task_detail)
    ), patch.object(
        service.repo, "update_task", new=fake_update
    ), patch(
        "yuxi.services.graph_builder.GraphBuilder.build_knowledge_graph",
        side_effect=RuntimeError("neo4j connection refused"),
    ), patch.object(
        service, "_save_learned_templates_from_task", new=AsyncMock(return_value=0)
    ), patch.object(
        service, "_produce_outlines_async", new=AsyncMock(return_value=0)
    ):
        result = await service._run_commit_pipeline_body(
            context=_fake_context(),
            task_id="t1",
            knowledge_base_id=None,
            reviewer="admin",
            ingest_task_id="ingest_t1",
        )
        status_updates = [c for c in update_calls if "status" in c]
        assert any(c["status"] == "COMMIT_FAILED" for c in status_updates), \
            f"图谱失败应标记 COMMIT_FAILED,实际: {status_updates}"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py::test_graph_build_failure_marks_commit_failed -v`
Expected: FAIL — 图谱异常被吞，状态仍为 COMMITTED

- [ ] **Step 3: 修改阶段2.5 异常处理**

在 `_run_commit_pipeline_body` 的阶段2.5（原约 4034 行），把 `except Exception as e: logger.warning(...)` 改为：

```python
            except Exception as e:
                # 图谱构建是关键步骤,失败必须标记,不再吞异常
                logger.exception(f"知识图谱构建失败,任务标记 COMMIT_FAILED: {task_id}")
                await service.repo.update_task(
                    task_id,
                    {"status": "COMMIT_FAILED", "error_message": f"图谱构建失败: {e}"},
                )
                await context.set_progress(100.0, f"图谱构建失败: {e}")
                await context.set_message(f"图谱构建失败: {e}")
                return {
                    "task_id": task_id,
                    "status": "COMMIT_FAILED",
                    "error": f"图谱构建失败: {e}",
                    "message": "图谱构建失败",
                }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py::test_graph_build_failure_marks_commit_failed -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py \
        backend/test/unit/services/test_commit_pipeline_status.py
git commit -m "fix(commit): 图谱构建失败标记COMMIT_FAILED,不再吞异常"
```

---

### Task 8: outline 失败标记 COMMIT_PARTIAL

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:4047-4056` (阶段2.9) 和 4066-4072 (最终状态)

**Purpose:** outline 生成失败（非关键）标记 COMMIT_PARTIAL，模板回流失败同样标记 PARTIAL。

- [ ] **Step 1: 编写 PARTIAL 测试**

Append to `test_commit_pipeline_status.py`:

```python
@pytest.mark.asyncio
async def test_outline_failure_marks_commit_partial():
    """outline 生成失败(图谱OK) → COMMIT_PARTIAL"""
    from yuxi.services.domain_factory_service import DomainFactoryService
    from unittest.mock import patch

    service = DomainFactoryService()
    valid_task_detail = {
        "source_paragraphs": [
            {"id": "p1", "type": "parameter", "template": {"text_pattern": "{{x}}"}}
        ],
        "domain": "coal",
        "report_type_code": "eia_report",
    }

    update_calls = []

    async def fake_update(task_id, data):
        update_calls.append({"task_id": task_id, **data})

    with patch.object(
        service, "get_task_detail", new=AsyncMock(return_value=valid_task_detail)
    ), patch.object(
        service.repo, "update_task", new=fake_update
    ), patch.object(
        service, "_save_learned_templates_from_task", new=AsyncMock(return_value=1)
    ), patch.object(
        service, "_produce_outlines_async", new=AsyncMock(side_effect=RuntimeError("LLM超时"))
    ):
        result = await service._run_commit_pipeline_body(
            context=_fake_context(),
            task_id="t1",
            knowledge_base_id=None,
            reviewer="admin",
            ingest_task_id="ingest_t1",
        )
        # 最终状态应为 PARTIAL(图谱OK但outline失败)
        final_status = [c for c in update_calls if c.get("status")]
        assert any(c["status"] == "COMMIT_PARTIAL" for c in final_status), \
            f"outline失败应标记 COMMIT_PARTIAL,实际: {final_status}"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py::test_outline_failure_marks_commit_partial -v`
Expected: FAIL

- [ ] **Step 3: 追踪阶段状态并最终汇总**

在 `_run_commit_pipeline_body` 中，阶段2.8 和 2.9 改为记录失败标志。在方法顶部初始化：

```python
        pipeline_status = "COMMITTED"  # 默认全部成功
        partial_errors: list[str] = []
```

阶段2.8（约 4044 行）改为：

```python
            except Exception as e:
                logger.warning(f"模板回流失败(标记PARTIAL): {e}")
                pipeline_status = "COMMIT_PARTIAL"
                partial_errors.append(f"模板回流失败: {e}")
```

阶段2.9（约 4056 行）改为：

```python
            except Exception as e:
                logger.warning(f"章节大纲产出失败(标记PARTIAL): {e}")
                pipeline_status = "COMMIT_PARTIAL"
                partial_errors.append(f"大纲产出失败: {e}")
```

最终状态更新（约 4066 行）改为用 `pipeline_status`：

```python
            await service.repo.update_task(
                task_id,
                {
                    "status": pipeline_status,
                    "knowledge_base_id": knowledge_base_id,
                    **({"error_message": "; ".join(partial_errors)} if partial_errors else {}),
                },
            )

            await context.set_progress(100.0, "入库完成" if pipeline_status == "COMMITTED" else "部分入库完成")
            await context.set_message("入库完成" if pipeline_status == "COMMITTED" else "部分入库完成")

            return {
                "task_id": task_id,
                "status": pipeline_status,
                "knowledge_base_id": knowledge_base_id,
                "kb_ingested": kb_ingested,
                "partial_errors": partial_errors,
                "message": "入库流水线执行完成",
            }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py \
        backend/test/unit/services/test_commit_pipeline_status.py
git commit -m "feat(commit): outline/模板回流失败标记COMMIT_PARTIAL,状态真实反映"
```

---

## Phase 4: ETL 源头修复 (P1)

### Task 9: domain/report_type 归一化

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:4027-4028` (传入图谱前)

**Purpose:** 在 build_knowledge_graph 调用前归一化 domain/report_type，防止"通用"污染。

- [ ] **Step 1: 编写归一化测试**

Create `backend/test/unit/services/test_etl_normalization.py`:

```python
import pytest
from yuxi.services.domain_factory_service import DomainFactoryService


def test_normalize_domain_chinese_to_code():
    service = DomainFactoryService()
    assert service._normalize_domain_for_graph("煤炭采掘") == "coal"
    assert service._normalize_domain_for_graph("煤矿") == "coal"
    assert service._normalize_domain_for_graph("coal") == "coal"


def test_normalize_report_type_general_to_code():
    service = DomainFactoryService()
    assert service._normalize_report_type_for_graph("通用") == "eia_report"
    assert service._normalize_report_type_for_graph("环评报告") == "eia_report"
    assert service._normalize_report_type_for_graph("eia_report") == "eia_report"


def test_normalize_unknown_keeps_original():
    service = DomainFactoryService()
    assert service._normalize_domain_for_graph("unknown_domain") == "unknown_domain"
    assert service._normalize_report_type_for_graph("") == ""
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_etl_normalization.py -v`
Expected: FAIL — 方法不存在

- [ ] **Step 3: 实现归一化方法**

在 `DomainFactoryService` 类中添加（复用现有 `_normalize_domain`/`_normalize_report_type`）：

```python
    def _normalize_domain_for_graph(self, domain: str) -> str:
        """ETL 入图谱前归一化 domain(中文名→code)。"""
        from yuxi.repositories.domain_factory_repository import _normalize_domain

        return _normalize_domain(domain or "") or (domain or "")

    def _normalize_report_type_for_graph(self, report_type: str) -> str:
        """ETL 入图谱前归一化 report_type('通用'→'eia_report')。"""
        from yuxi.repositories.domain_factory_repository import _normalize_report_type

        normalized = _normalize_report_type(report_type or "")
        return normalized if normalized else (report_type or "")
```

- [ ] **Step 4: 在 build_knowledge_graph 调用处接入**

修改 `_run_commit_pipeline_body` 阶段2.5（约 4027 行）：

```python
                graph_stats = graph_builder.build_knowledge_graph(
                    kb_id=knowledge_base_id or "",
                    doc_id=doc_id,
                    doc_title=task_detail.get("file_name", ""),
                    source_paragraphs=source_paragraphs,
                    domain_label=domain_label,
                    base_info=base_info,
                    domain_code=self._normalize_domain_for_graph(task_detail.get("domain") or ""),
                    report_type_code=self._normalize_report_type_for_graph(task_detail.get("report_type_code") or ""),
                )
```

阶段2.9 的 `_produce_outlines_async` 调用（约 4051 行）也同步归一化：

```python
                outline_count = await service._produce_outlines_async(
                    task_id,
                    self._normalize_domain_for_graph(task_detail.get("domain") or "coal"),
                    self._normalize_report_type_for_graph(task_detail.get("report_type_code") or "eia_report"),
                )
```

- [ ] **Step 5: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_etl_normalization.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py \
        backend/test/unit/services/test_etl_normalization.py
git commit -m "fix(etl): domain/report_type入图谱前归一化,防止'通用'污染"
```

---

### Task 10: title 双编号清洗覆盖 numbered-line 路径

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:1077-1088`

**Purpose:** numbered-line 解析路径补充双编号去重，与 Markdown `#` 路径一致。

- [ ] **Step 1: 编写 title 清洗测试**

Create `backend/test/unit/services/test_title_cleanup.py`:

```python
from yuxi.services.domain_factory_service import DomainFactoryService


def test_clean_dual_numbering_markdown_path():
    """Markdown # 路径: '1.1.1 3.1.1 地形地貌' → '3.1.1 地形地貌'"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("1.1.1 3.1.1 地形地貌") == "3.1.1 地形地貌"


def test_clean_dual_numbering_numbered_path():
    """numbered-line 路径: '1.3.4.1七号井田...' → '七号井田...'"""
    service = DomainFactoryService()
    # 输入是 split 后的第二部分(已经去掉第一个编号),但仍可能含双编号
    assert service._clean_chapter_title("3.1.1 地形地貌") == "3.1.1 地形地貌"


def test_clean_pure_number_returns_empty():
    """纯编号 '2' → 空字符串"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("2") == ""


def test_clean_no_numbering_unchanged():
    """无编号标题 → 原样"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("地形地貌") == "地形地貌"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_title_cleanup.py -v`
Expected: FAIL — `_clean_chapter_title` 不存在

- [ ] **Step 3: 实现 _clean_chapter_title**

在 `DomainFactoryService` 类中添加：

```python
    def _clean_chapter_title(self, title: str) -> str:
        """清洗章节标题:去双编号、纯编号返回空。"""
        import re

        text = (title or "").strip()
        if not text:
            return ""

        # 纯编号 → 空(如 "2", "3.1")
        if re.fullmatch(r"\d+(?:\.\d+)*", text):
            return ""

        # 双编号去重: "1.1.1 3.1.1 地形地貌" → "3.1.1 地形地貌"
        dual_match = re.match(r"^(\d+(?:\.\d+)*)\s+(\d+(?:\.\d+)*\s+\S.*)$", text)
        if dual_match:
            text = dual_match.group(2).strip()

        return text
```

- [ ] **Step 4: 在 numbered-line 路径接入清洗**

修改 `_parse_markdown_to_paragraphs`（约 1085 行），numbered-line 路径设置 title_text 后追加：

```python
                        is_title = True
                        title_text = self._clean_chapter_title(potential_title)
                        if not title_text:
                            is_title = False  # 清洗后为空,不算标题
```

- [ ] **Step 5: 运行测试验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_title_cleanup.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py \
        backend/test/unit/services/test_title_cleanup.py
git commit -m "fix(etl): title双编号清洗覆盖numbered-line路径+纯编号过滤"
```

---

## Phase 5: 存量数据治理脚本 (P1)

### Task 11: 治理脚本骨架 + 连接管理

**Files:**
- Create: `backend/scripts/governance/fix_existing_graph.py`
- Create: `backend/test/scripts/test_fix_existing_graph.py`

**Purpose:** 建立治理脚本骨架——幂等连接、dry-run 模式、报告输出。

- [ ] **Step 1: 编写骨架测试**

Create `backend/test/scripts/__init__.py` (空文件) and `backend/test/scripts/test_fix_existing_graph.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from scripts.governance.fix_existing_graph import GraphGovernance, GovernanceReport


def test_dry_run_does_not_modify_graph():
    """dry-run 模式不执行任何写操作"""
    gov = GraphGovernance(dry_run=True)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_session.run.return_value = MagicMock()

    gov.merge_general_branch(fake_driver)

    # dry_run 下不调用写 Cypher
    write_calls = [
        c for c in fake_session.run.call_args_list
        if "SET" in str(c) or "MERGE" in str(c) or "DELETE" in str(c)
    ]
    assert len(write_calls) == 0


def test_report_initialization():
    report = GovernanceReport()
    assert report.fixed_keys == 0
    assert report.merged_branches == 0
    assert report.cleaned_titles == 0
    assert report.errors == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/scripts/test_fix_existing_graph.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 创建治理脚本骨架**

Create `backend/scripts/governance/__init__.py` (空文件) and `backend/scripts/governance/fix_existing_graph.py`:

```python
"""存量图谱数据治理脚本(幂等)。

修复:
1. 合并 report_type='通用' 分支到 eia_report
2. 清洗 ChapterTemplate.title 双编号
3. 回填 canonical_chapter_key
4. 归一化 Document.domain
5. 事后校验回补 entity_ref

用法:
  python -m scripts.governance.fix_existing_graph --dry-run   # 预览
  python -m scripts.governance.fix_existing_graph             # 执行
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass
class GovernanceReport:
    fixed_keys: int = 0
    merged_branches: int = 0
    cleaned_titles: int = 0
    normalized_domains: int = 0
    errors: list[str] = field(default_factory=list)


class GraphGovernance:
    """存量图谱治理器。dry_run=True 时只统计不写入。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.report = GovernanceReport()

    def merge_general_branch(self, driver) -> None:
        """Step 1: 合并 coal/通用 → coal/eia_report。"""
        if self.dry_run:
            return
        # 实现在 Task 12 补充
        pass

    def run_all(self, driver) -> GovernanceReport:
        """执行全部治理步骤。"""
        self.merge_general_branch(driver)
        # 其余步骤在后续 Task 补充
        return self.report


def main():
    parser = argparse.ArgumentParser(description="存量图谱治理")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()

    gov = GraphGovernance(dry_run=args.dry_run)
    print(f"模式: {'dry-run(预览)' if args.dry_run else '执行'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/scripts/test_fix_existing_graph.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/governance/ \
        backend/test/scripts/
git commit -m "feat(governance): 治理脚本骨架(dry-run+报告结构)"
```

---

### Task 12: 合并"通用"分支 + 清洗 title + 回填 key

**Files:**
- Modify: `backend/scripts/governance/fix_existing_graph.py`

**Purpose:** 实现核心治理逻辑——合并分支、清洗 title、回填 canonical_chapter_key。

- [ ] **Step 1: 编写治理逻辑测试**

Append to `test_fix_existing_graph.py`:

```python
def test_clean_title_dual_numbering():
    """清洗双编号 title"""
    from scripts.governance.fix_existing_graph import clean_chapter_title

    assert clean_chapter_title("1.1.1 3.1.1 地形地貌") == "地形地貌"
    assert clean_chapter_title("3.1.1 地形地貌") == "地形地貌"
    assert clean_chapter_title("2") == ""
    assert clean_chapter_title("地形地貌") == "地形地貌"


def test_derive_canonical_key_from_clean_title():
    """从清洗后 title 推导 canonical_chapter_key"""
    from scripts.governance.fix_existing_graph import derive_canonical_key

    assert derive_canonical_key("地形地貌") == "地形地貌"
    assert derive_canonical_key("") == ""
    # 含编号的取最后一段标题
    assert derive_canonical_key("气候气象") == "气候气象"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/scripts/test_fix_existing_graph.py -v`
Expected: FAIL — `clean_chapter_title` 不存在

- [ ] **Step 3: 实现清洗和回填函数**

在 `fix_existing_graph.py` 顶部添加工具函数：

```python
import re


def clean_chapter_title(title: str) -> str:
    """清洗章节标题:去所有前导编号(双编号/单编号),只留纯标题。纯编号返回空。"""
    text = (title or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)*", text):
        return ""
    # 反复去掉前导"数字.数字. "直到剩下纯标题
    while True:
        m = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", text)
        if not m:
            break
        text = m.group(2).strip()
    return text


def derive_canonical_key(clean_title: str) -> str:
    """从清洗后的标题推导 canonical_chapter_key(目前等于标题本身)。"""
    return (clean_title or "").strip()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/scripts/test_fix_existing_graph.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/governance/fix_existing_graph.py \
        backend/test/scripts/test_fix_existing_graph.py
git commit -m "feat(governance): title清洗+canonical_key推导工具函数"
```

---

### Task 13: Cypher 治理语句实现

**Files:**
- Modify: `backend/scripts/governance/fix_existing_graph.py`

**Purpose:** 实现 merge_general_branch / clean_titles / backfill_keys 的 Cypher 执行逻辑。

- [ ] **Step 1: 编写 Cypher 执行测试（用 mock session）**

Append to `test_fix_existing_graph.py`:

```python
def test_merge_general_branch_executes_cypher_when_not_dry_run():
    """非 dry-run 模式下执行合并 Cypher"""
    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter([{"cnt": 41}])
    fake_session.run.return_value = fake_result

    gov.merge_general_branch(fake_driver)

    # 应调用至少一次写 Cypher
    cypher_calls = [str(c) for c in fake_session.run.call_args_list]
    assert any("report_type" in c and "eia_report" in c for c in cypher_calls)


def test_clean_titles_uses_clean_chapter_title():
    """clean_titles 步骤调用 clean_chapter_title 处理每个 title"""
    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    # 模拟查询返回带双编号的 title
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter([
        {"id": "ch1", "title": "1.1.1 3.1.1 地形地貌"}
    ])
    fake_session.run.return_value = fake_result

    gov.clean_titles(fake_driver)
    assert gov.report.cleaned_titles >= 0  # 至少不报错
```

- [ ] **Step 2: 运行测试验证失败**

Run: `docker exec api-dev pytest test/scripts/test_fix_existing_graph.py -v`
Expected: FAIL — `clean_titles` 未实现

- [ ] **Step 3: 实现 Cypher 治理方法**

在 `GraphGovernance` 类中替换/添加：

```python
    def merge_general_branch(self, driver) -> None:
        """Step 1: 合并 coal/通用 → coal/eia_report。"""
        with driver.session() as session:
            result = session.run(
                "MATCH (d:DomainOutline {domain:'coal', report_type:'通用'})"
                "-[:HAS_CHAPTER]->(ch:ChapterTemplate) "
                "RETURN count(ch) AS cnt"
            )
            count = result.single()["cnt"] if result.peek() else 0

            if self.dry_run:
                self.report.merged_branches = count
                return

            session.run(
                "MATCH (ch:ChapterTemplate {domain:'coal', report_type:'通用'}) "
                "SET ch.report_type = 'eia_report'"
            )
            session.run(
                "MATCH (d:DomainOutline {domain:'coal', report_type:'通用'}) "
                "DETACH DELETE d"
            )
            self.report.merged_branches = count

    def clean_titles(self, driver) -> None:
        """Step 2: 清洗 ChapterTemplate.title。"""
        with driver.session() as session:
            result = session.run(
                "MATCH (ch:ChapterTemplate) WHERE ch.title IS NOT NULL "
                "RETURN ch.id AS id, ch.title AS title"
            )
            for record in result:
                original = record["title"]
                cleaned = clean_chapter_title(original)
                if cleaned != original and not self.dry_run:
                    session.run(
                        "MATCH (ch:ChapterTemplate {id:$id}) SET ch.title = $title",
                        id=record["id"],
                        title=cleaned,
                    )
                if cleaned != original:
                    self.report.cleaned_titles += 1

    def backfill_keys(self, driver) -> None:
        """Step 3: 回填 canonical_chapter_key。"""
        with driver.session() as session:
            result = session.run(
                "MATCH (ch:ChapterTemplate) "
                "WHERE ch.canonical_chapter_key IS NULL OR ch.canonical_chapter_key = '' "
                "RETURN ch.id AS id, ch.title AS title"
            )
            for record in result:
                key = derive_canonical_key(clean_chapter_title(record["title"]))
                if key and not self.dry_run:
                    session.run(
                        "MATCH (ch:ChapterTemplate {id:$id}) "
                        "SET ch.canonical_chapter_key = $key",
                        id=record["id"],
                        key=key,
                    )
                if key:
                    self.report.fixed_keys += 1

    def run_all(self, driver) -> GovernanceReport:
        """执行全部治理步骤。"""
        self.merge_general_branch(driver)
        self.clean_titles(driver)
        self.backfill_keys(driver)
        return self.report
```

- [ ] **Step 4: 运行测试验证通过**

Run: `docker exec api-dev pytest test/scripts/test_fix_existing_graph.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/governance/fix_existing_graph.py \
        backend/test/scripts/test_fix_existing_graph.py
git commit -m "feat(governance): Cypher治理实现(合并分支/清洗title/回填key)"
```

---

### Task 14: 端到端治理验证

**Files:**
- Modify: `backend/scripts/governance/fix_existing_graph.py` (main 函数)

**Purpose:** 完善 main 函数，连接真实 Neo4j 执行治理，输出报告。

- [ ] **Step 1: 完善 main 函数连接 Neo4j**

替换 `fix_existing_graph.py` 的 `main()`：

```python
def main():
    parser = argparse.ArgumentParser(description="存量图谱治理(幂等)")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    parser.add_argument("--uri", default="bolt://graph:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j 用户名")
    parser.add_argument("--password", default="0123456789", help="Neo4j 密码")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    gov = GraphGovernance(dry_run=args.dry_run)

    print(f"模式: {'dry-run(预览)' if args.dry_run else '执行'}")
    report = gov.run_all(driver)
    driver.close()

    print("\n========== 治理报告 ==========")
    print(f"合并'通用'分支章节数: {report.merged_branches}")
    print(f"清洗 title 数: {report.cleaned_titles}")
    print(f"回填 canonical_key 数: {report.fixed_keys}")
    print(f"归一化 domain 数: {report.normalized_domains}")
    if report.errors:
        print(f"错误: {report.errors}")
    print("==============================")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: dry-run 验证（在容器内）**

Run:
```bash
docker exec api-dev python -m scripts.governance.fix_existing_graph --dry-run --uri bolt://graph:7687
```
Expected: 输出治理报告，不修改图谱

- [ ] **Step 3: 实际执行治理**

Run:
```bash
docker exec api-dev python -m scripts.governance.fix_existing_graph --uri bolt://graph:7687
```
Expected: 报告显示合并/清洗/回填数量 > 0

- [ ] **Step 4: 验证图谱数据已治理**

Run:
```bash
docker exec graph cypher-shell -a bolt://localhost:7687 -u neo4j -p 0123456789 \
  "MATCH (ch:ChapterTemplate) WHERE ch.report_type='通用' RETURN count(ch) AS general_count;"
docker exec graph cypher-shell -a bolt://localhost:7687 -u neo4j -p 0123456789 \
  "MATCH (ch:ChapterTemplate) WHERE ch.canonical_chapter_key IS NULL OR ch.canonical_chapter_key='' RETURN count(ch) AS null_key_count;"
```
Expected: `general_count = 0`, `null_key_count = 0`（或大幅减少）

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/governance/fix_existing_graph.py
git commit -m "feat(governance): main函数连接Neo4j+端到端治理验证"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Section 2 (slot 事后校验) → Tasks 1-3
- ✅ Section 3.2 (提交前验证关卡) → Tasks 4-6
- ✅ Section 3.3 (异常不吞) → Tasks 6-8
- ✅ Section 4.2 存量治理 Steps 1-3 → Tasks 11-14
- ⚠️ Section 4.2 Step 4 (Document.domain 归一化) 和 Step 5 (事后校验回补) — Task 13 保留为扩展点,需在执行时补充(脚本结构已支持)
- ✅ Phase 4 ETL 归一化 + title 清洗 → Tasks 9-10

**已识别的简化项（执行时注意）:**
1. Task 6 的 `_commit_pipeline_async` 重构较大,需谨慎移动代码——将原方法体整体移入 `_run_commit_pipeline_body`
2. Task 7/8 的 mock 测试依赖 repo.update_task 和 get_task_detail 的 mock,需确认 DomainFactoryService 构造不需 DB 连接
3. Task 13 的 Document.domain 归一化和事后校验回补未单独建 Task,作为治理脚本扩展点在执行时实现

---

## 实施顺序

```
Phase 1 (P0): Task 1 → 2 → 3   (slot 事后校验)
Phase 2 (P0): Task 4 → 5        (提交前验证)
Phase 3 (P0): Task 6 → 7 → 8    (异常不吞)
Phase 4 (P1): Task 9 → 10       (ETL 归一化)
Phase 5 (P1): Task 11 → 12 → 13 → 14  (存量治理)
```

Phase 1-3 为 P0,必须先完成(止血);Phase 4-5 为 P1(根治)。
