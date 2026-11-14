"""实体配置导入（DomainEntityService.import_all）单元测试。

覆盖：按 entity_key 对齐（跨环境 entity_id 不同）、无 entity_id 可创建、
异域/缺键/缺名/文件内重复拒绝、dry_run 不写库、值类型归一、有更新才重映射。
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pisuan.services.domain_entity_service import DomainEntityService

pytestmark = pytest.mark.asyncio


class _FakeRepo:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.written: list[dict] = []

    async def list_all(self, domain_code=None, category=None):
        return self.existing

    async def upsert_all(self, entities):
        self.written.extend(entities)
        return len(entities)


def _service(repo) -> DomainEntityService:
    service = DomainEntityService()
    service.repo = repo
    service._remap_waiting_review_tasks = AsyncMock(return_value=2)
    return service


def _entity(**overrides) -> dict:
    data = {
        "entity_id": "env-b-noise",
        "entity_key": "noise_equipment",
        "name_cn": "噪声源",
        "category": "env_quality",
        "domain_code": "general",
        "value_type": "String",
        "properties": [{"key": "noise_level", "name_cn": "噪声级", "value_type": "String"}],
    }
    data.update(overrides)
    return data


def _config(*entities) -> dict:
    return {"entity_schemas": {f"k{index}": item for index, item in enumerate(entities)}}


async def test_import_matches_by_entity_key_across_env():
    repo = _FakeRepo(existing=[{"entity_id": "env-a", "entity_key": "noise_equipment"}])
    result = await _service(repo).import_all(_config(_entity()))

    assert (result["created"], result["updated"], result["rejected"]) == (0, 1, [])
    assert repo.written[0]["entity_key"] == "noise_equipment"


async def test_import_creates_entry_without_entity_id():
    repo = _FakeRepo()
    entity = _entity()
    entity.pop("entity_id")
    result = await _service(repo).import_all(_config(entity))

    assert (result["created"], result["updated"]) == (1, 0)
    assert "entity_id" not in repo.written[0]


async def test_import_rejects_foreign_domain_code():
    repo = _FakeRepo()
    result = await _service(repo).import_all(_config(_entity(domain_code="coal")))

    assert (result["created"], result["updated"]) == (0, 0)
    assert repo.written == []
    reason = result["rejected"][0]["reason"]
    assert "coal" in reason and "general" in reason


async def test_import_rejects_missing_key_and_name():
    repo = _FakeRepo()
    result = await _service(repo).import_all(_config(_entity(entity_key=""), _entity(name_cn=" ")))

    assert len(result["rejected"]) == 2
    assert "entity_key不能为空" in result["rejected"][0]["reason"]
    assert "name_cn 不能为空" in result["rejected"][1]["reason"]
    assert repo.written == []


async def test_import_rejects_duplicate_key_in_file():
    repo = _FakeRepo()
    result = await _service(repo).import_all(_config(_entity(), _entity(name_cn="噪声源二")))

    assert (result["created"], result["updated"]) == (1, 0)
    assert "重复" in result["rejected"][0]["reason"]
    assert len(repo.written) == 1


async def test_import_dry_run_does_not_write_or_remap():
    repo = _FakeRepo(existing=[{"entity_id": "env-a", "entity_key": "noise_equipment"}])
    service = _service(repo)
    result = await service.import_all(_config(_entity()), dry_run=True)

    assert (result["created"], result["updated"], result["dry_run"]) == (0, 1, True)
    assert repo.written == []
    service._remap_waiting_review_tasks.assert_not_awaited()


async def test_import_normalizes_legacy_value_type():
    repo = _FakeRepo()
    await _service(repo).import_all(
        _config(
            _entity(
                value_type="Numeric",
                properties=[{"key": "noise_level", "name_cn": "噪声级", "value_type": "Number"}],
            )
        )
    )

    assert repo.written[0]["value_type"] == "Float"
    assert repo.written[0]["properties"][0]["value_type"] == "Float"


async def test_import_remaps_only_when_some_entity_updated():
    repo = _FakeRepo()
    service = _service(repo)
    await service.import_all(_config(_entity()))
    service._remap_waiting_review_tasks.assert_not_awaited()

    repo.existing = [{"entity_id": "env-a", "entity_key": "noise_equipment"}]
    await service.import_all(_config(_entity()))
    service._remap_waiting_review_tasks.assert_awaited_once()
