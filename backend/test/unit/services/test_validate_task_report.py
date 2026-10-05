"""bug-354 同族：validate_task 报告统计/L2 过滤应读 classify_type（原读 type 全部落空）。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuxi.services.domain_factory_service import DomainFactoryService


def _fake_detail() -> dict:
    return {
        "source_paragraphs": [
            {"id": "p1", "classify_type": "parameter",
             "template": {"text_pattern": "矿区规模 {{规模}} Mt/a", "slots": [{"name": "规模"}]}},
            {"id": "p2", "classify_type": "narrative"},
        ],
    }


@pytest.mark.asyncio
async def test_validate_task_counts_parameter_paragraphs():
    """修复前 parameter_paragraphs 恒为 0（段落无 type 字段）→ 断言失败；修复后应为 1"""
    svc = DomainFactoryService()
    svc.repo = MagicMock()
    svc.repo.update_task = AsyncMock()
    with patch.object(svc, "get_task_detail", new=AsyncMock(return_value=_fake_detail())):
        report = await svc.validate_task("t1")
    assert report["summary"]["parameter_paragraphs"] == 1
    assert report["passed"] is True
    svc.repo.update_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_task_sends_parameter_slots_to_l2():
    """L2 过滤钉住：只有 classify_type=parameter 的段落进入 SlotValidationService"""
    svc = DomainFactoryService()
    svc.repo = MagicMock()
    svc.repo.update_task = AsyncMock()
    with patch.object(svc, "get_task_detail", new=AsyncMock(return_value=_fake_detail())), \
         patch("yuxi.services.slot_validation_service.SlotValidationService") as mock_cls:
        mock_cls.return_value.validate_slots = AsyncMock(return_value={"conflicts": [], "warnings": 0})
        report = await svc.validate_task("t1")
    mock_cls.return_value.validate_slots.assert_awaited_once()
    slots_arg = mock_cls.return_value.validate_slots.await_args.args[0]
    assert [s["paragraph_id"] for s in slots_arg] == ["p1"]
    assert report["passed"] is True
