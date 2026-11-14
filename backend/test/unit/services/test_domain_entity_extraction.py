"""单元测试：实体构建器 AI 提取的比对/保存/校验（P0 重构）

覆盖：
- 覆盖度比对三态（matched/partial/new），属性为 dict 的历史形态不崩
- 保存只补 schema 定义，实例值不入库；无证据/无状态被拒
- 键校验、值类型词表、entity_key 禁改
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services.domain_entity_service import (
    PROPOSAL_SCHEMA_REF,
    DomainEntityService,
)

# 分类字典的允许集合（v23 起提案 category 以字典为准）
ALLOWED_CATEGORIES = {"project_basic", "measures_regulation", "natural_env"}


class FakeEntity:
    def __init__(self, entity_id: str, entity_key: str, properties=None, category="project_basic"):
        self.entity_id = entity_id
        self.entity_key = entity_key
        self.name_cn = entity_key
        self.category = category
        self.properties = properties or []

    def to_dict(self):
        return {
            "entity_id": self.entity_id,
            "entity_key": self.entity_key,
            "name_cn": self.name_cn,
            "category": self.category,
            "properties": self.properties,
        }


class FakeRepo:
    def __init__(self, entities=None):
        self.entities = {e.entity_key: e for e in (entities or [])}
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    async def get_by_id_or_key(self, identifier):
        for entity in self.entities.values():
            if entity.entity_id == identifier or entity.entity_key == identifier:
                return entity
        return None

    async def get_by_key(self, key):
        return self.entities.get(key)

    async def create(self, data):
        entity = FakeEntity(
            data["entity_id"],
            data["entity_key"],
            data.get("properties"),
            data.get("category", ""),
        )
        self.entities[entity.entity_key] = entity
        self.created.append(data)
        return entity

    async def update(self, entity_id, data):
        for entity in self.entities.values():
            if entity.entity_id == entity_id:
                for key, value in data.items():
                    if key == "properties":
                        entity.properties = value
                self.updated.append((entity_id, data))
                return entity
        return None


@pytest.fixture
def service(monkeypatch):
    svc = DomainEntityService()
    svc.repo = FakeRepo()
    monkeypatch.setattr(svc, "_remap_waiting_review_tasks", AsyncMock(return_value=0))
    return svc


def row(entity: FakeEntity) -> dict:
    return {
        "entity_id": entity.entity_id,
        "entity_key": entity.entity_key,
        "name_cn": entity.name_cn,
        "category": entity.category,
        "properties": entity.properties,
    }


# ------------------------------------------------------------------
# 比对矩阵
# ------------------------------------------------------------------

def test_compare_all_keys_defined_is_matched(service):
    existing = FakeEntity("e1", "coal_mine", [{"key": "capacity", "name_cn": "产能"}])
    extracted = [
        {"schema_ref": "coal_mine", "values": {"capacity": 120}, "extracted_text": "产能 120 万吨"}
    ]
    result = service._compare_extracted_with_entities(extracted, [row(existing)], ALLOWED_CATEGORIES)

    assert result[0]["_status"] == "matched"
    assert result[0]["_diff"]["add_properties"] == []
    assert result[0]["_entity_id"] == "e1"


def test_compare_new_keys_is_partial(service):
    existing = FakeEntity("e1", "coal_mine", [{"key": "capacity", "name_cn": "产能"}])
    extracted = [
        {"schema_ref": "coal_mine", "values": {"capacity": 120, "dust_control": "洒水"}}
    ]
    result = service._compare_extracted_with_entities(extracted, [row(existing)], ALLOWED_CATEGORIES)

    assert result[0]["_status"] == "partial"
    add = result[0]["_diff"]["add_properties"]
    assert [p["key"] for p in add] == ["dust_control"]
    assert add[0]["value_type"] == "String"
    assert add[0]["sample_value"] == "洒水"


def test_compare_tolerates_dict_shaped_properties(service):
    """历史/污染数据可能把 properties 写成 dict，比对不得抛异常。"""
    legacy = {
        "entity_id": "e2",
        "entity_key": "legacy_entity",
        "name_cn": "遗留实体",
        "category": "project_basic",
        "properties": {"排放量": "1200t/a"},
    }
    result = service._compare_extracted_with_entities(
        [{"schema_ref": "legacy_entity", "values": {"新属性": "x"}}],
        [legacy],
        ALLOWED_CATEGORIES,
    )

    assert result[0]["_status"] == "partial"
    assert result[0]["_diff"]["add_properties"][0]["key"] == "新属性"


def test_compare_unknown_schema_ref_is_rejected_proposal(service):
    result = service._compare_extracted_with_entities(
        [{"schema_ref": "typo_key", "name_cn": "错键", "values": {"a": 1}}],
        [],
        ALLOWED_CATEGORIES,
    )

    proposal = result[0]["_proposed_entity"]
    assert result[0]["_status"] == "new"
    assert any("不在实体库" in p for p in proposal["problems"])


def test_compare_explicit_proposal_is_clean(service):
    result = service._compare_extracted_with_entities(
        [
            {
                "schema_ref": PROPOSAL_SCHEMA_REF,
                "entity_key": "dust_facility",
                "name_cn": "除尘设施",
                "category": "measures_regulation",
                "values": {"效率": 95},
            }
        ],
        [],
        ALLOWED_CATEGORIES,
    )

    proposal = result[0]["_proposed_entity"]
    assert proposal["problems"] == []
    assert proposal["entity_key"] == "dust_facility"
    assert proposal["properties"][0]["value_type"] == "Float"


# ------------------------------------------------------------------
# 保存
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_rejects_ungrounded_item(service):
    result = await service.save_extracted_entities(
        [{"_status": "matched", "name_cn": "无证据", "grounded": False}], "general"
    )

    assert result["unchanged"] == 0
    assert result["rejected"][0]["reason"].startswith("原文未找到")


@pytest.mark.asyncio
async def test_save_partial_appends_definition_not_values(service):
    entity = FakeEntity("e1", "coal_mine", [{"key": "capacity", "name_cn": "产能"}])
    service.repo = FakeRepo([entity])

    result = await service.save_extracted_entities(
        [
            {
                "_status": "partial",
                "_entity_id": "e1",
                "name_cn": "煤矿",
                "grounded": True,
                "_diff": {
                    "add_properties": [
                        {"key": "dust_control", "name_cn": "除尘措施", "value_type": "String", "sample_value": "洒水"}
                    ]
                },
            }
        ],
        "general",
    )

    assert result["properties_added"] == 1
    definitions = service.repo.entities["coal_mine"].properties
    assert [p["key"] for p in definitions] == ["capacity", "dust_control"]
    assert definitions[1]["description"] == "由 AI 提取补充"
    assert "洒水" not in str(definitions)  # 实例值不入 schema


@pytest.mark.asyncio
async def test_save_new_creates_readable_key(service):
    result = await service.save_extracted_entities(
        [
            {
                "_status": "new",
                "name_cn": "除尘设施",
                "confidence": 0.8,
                "grounded": True,
                "_proposed_entity": {
                    "entity_key": "dust_facility",
                    "name_cn": "除尘设施",
                    "category": "measures_regulation",
                    "problems": [],
                    "properties": [{"key": "efficiency", "name_cn": "效率", "value_type": "Float"}],
                },
            }
        ],
        "general",
    )

    assert result["inserted"] == 1
    created = service.repo.created[0]
    assert created["entity_key"] == "dust_facility"
    assert created["metadata"]["source"] == "ai_extract"
    assert created["properties"][0]["key"] == "efficiency"


@pytest.mark.asyncio
async def test_save_new_with_problems_is_rejected(service):
    result = await service.save_extracted_entities(
        [
            {
                "_status": "new",
                "name_cn": "缺分类",
                "grounded": True,
                "_proposed_entity": {
                    "entity_key": "x_entity",
                    "problems": ["category 不属于六大分类"],
                    "properties": [],
                },
            }
        ],
        "general",
    )

    assert result["inserted"] == 0
    assert "提案不可导入" in result["rejected"][0]["reason"]


# ------------------------------------------------------------------
# 校验
# ------------------------------------------------------------------

def test_value_type_rejects_unknown():
    with pytest.raises(ValueError, match="未知值类型"):
        DomainEntityService.normalize_value_type("Money")


def test_value_type_maps_legacy_alias():
    assert DomainEntityService.normalize_value_type("Numeric") == "Float"
    assert DomainEntityService.normalize_value_type("Date") == "String"


def test_duplicate_property_key_rejected():
    with pytest.raises(ValueError, match="重复"):
        DomainEntityService.normalize_properties(
            [{"key": "capacity"}, {"key": "Capacity"}]
        )


def test_property_key_with_dot_rejected():
    with pytest.raises(ValueError, match="空白或点号"):
        DomainEntityService.normalize_properties([{"key": "coal.mine"}])


@pytest.mark.asyncio
async def test_update_entity_rejects_key_rename(service):
    entity = FakeEntity("e1", "coal_mine")
    service.repo = FakeRepo([entity])

    with pytest.raises(ValueError, match="不允许修改"):
        await service.update_entity("coal_mine", {"entity_key": "new_key"})
