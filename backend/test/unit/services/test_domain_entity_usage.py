"""实体引用影响面统计（DomainEntityService.get_entity_usage）单元测试。

覆盖：四类引用来源、中文名后缀归一、悬空引用、未使用属性、其他实体引用不计入。
"""
from __future__ import annotations

import pytest

from yuxi.services.domain_entity_service import DomainEntityService

pytestmark = pytest.mark.asyncio


class _FakeEntity:
    def __init__(self, payload: dict):
        self._payload = payload

    def to_dict(self) -> dict:
        return dict(self._payload)


class _FakeRepo:
    def __init__(self, entity, templates=(), tasks=(), pps=(), facts=()):
        self.entity = entity
        self.templates = list(templates)
        self.tasks = list(tasks)
        self.pps = list(pps)
        self.facts = list(facts)

    async def get_by_id_or_key(self, identifier):
        return self.entity

    async def list_usage_learned_templates(self, domain_code):
        return self.templates

    async def list_usage_pending_tasks(self, domain_code):
        return self.tasks

    async def list_usage_report_pps(self, domain_code):
        return self.pps

    async def list_usage_regional_facts(self):
        return self.facts


def _entity():
    return _FakeEntity(
        {
            "entity_id": "e-1",
            "entity_key": "noise_equipment",
            "name_cn": "噪声源",
            "properties": [
                {"key": "equipment_name", "name_cn": "设备名称"},
                {"key": "location", "name_cn": "位置"},
                {"key": "noise_level", "name_cn": "噪声级"},
            ],
        }
    )


def _service(repo) -> DomainEntityService:
    service = DomainEntityService()
    service.repo = repo
    return service


def _template(template_id, *refs):
    return {
        "id": template_id,
        "chapter": f"章节-{template_id}",
        "report_type_code": "eia_report",
        "source_count": 2,
        "updated_at": "2026-11-14T10:00:00",
        "slots": [{"entity_ref": ref} for ref in refs],
    }


def _task(task_id, *refs):
    return {
        "id": task_id,
        "file_name": "report.doc",
        "source_paragraphs": [{"template": {"slots": [{"entity_ref": ref} for ref in refs]}}],
    }


async def test_usage_counts_all_sources_and_normalizes_names():
    repo = _FakeRepo(
        _entity(),
        templates=[
            _template(1, "noise_equipment.equipment_name", "other_entity.name"),
            _template(2, "noise_equipment.设备名称", "noise_equipment.removed_prop"),
        ],
        tasks=[_task("t-1", "noise_equipment.location", "noise_equipment")],
        pps=[{"report_id": "r-1", "entity_key": "noise_equipment.equipment_name"}],
        facts=[{"entity_key": "noise_equipment", "status": "confirmed"}],
    )

    usage = await _service(repo).get_entity_usage("noise_equipment")

    assert usage["totals"] == {
        "templates": 2,
        "pending_tasks": 1,
        "report_pps": 1,
        "facts": 1,
        "dangling_refs": 1,
    }
    # 中文名后缀「设备名称」归一到 equipment_name，与 key 后缀累计
    assert usage["properties"]["equipment_name"]["templates"] == 2
    assert usage["properties"]["equipment_name"]["report_pps"] == 1
    assert usage["properties"]["location"]["pending_tasks"] == 1
    assert usage["unused_properties"] == ["noise_level"]
    assert usage["dangling_refs"] == ["noise_equipment.removed_prop"]
    assert [item["id"] for item in usage["template_refs"]] == [1, 2]
    assert usage["pending_task_refs"][0]["refs"] == ["noise_equipment.location", "noise_equipment"]


async def test_usage_ignores_refs_of_other_entities():
    repo = _FakeRepo(
        _entity(),
        templates=[_template(1, "other_entity.name", "noise_source.name")],
        pps=[{"report_id": "r-1", "entity_key": "other_entity"}],
    )

    usage = await _service(repo).get_entity_usage("noise_equipment")

    assert usage["totals"]["templates"] == 0
    assert usage["totals"]["report_pps"] == 0
    assert usage["template_refs"] == []
    assert usage["unused_properties"] == ["equipment_name", "location", "noise_level"]


async def test_usage_missing_entity_raises():
    repo = _FakeRepo(None)

    with pytest.raises(ValueError, match="不存在"):
        await _service(repo).get_entity_usage("ghost")
