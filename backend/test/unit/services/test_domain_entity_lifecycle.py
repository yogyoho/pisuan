"""实体软删 / 回收站 / 乐观锁（DomainEntityService）单元测试。

覆盖：删除=软删、恢复与彻底删除的状态约束、回收站键占位（新建/克隆）、
乐观锁参数透传、列表带回收站数量。SQL 层的行锁比对与 API 的 409 由集成测试覆盖。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.services.domain_entity_service import DomainEntityService

pytestmark = pytest.mark.asyncio


def _entity(**overrides):
    data = {
        "entity_id": "ent-1",
        "entity_key": "noise_equipment",
        "name_cn": "噪声源",
        "category": "env_quality",
        "deleted_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data, to_dict=lambda: dict(data))


def _service(**repo_methods):
    names = [
        "get_by_id_or_key",
        "get_by_key",
        "get_by_id",
        "update",
        "soft_delete",
        "restore",
        "purge",
        "list_all",
        "list_deleted",
        "count_deleted",
        "create",
    ]
    repo = SimpleNamespace(**{name: AsyncMock() for name in names})
    for name, value in repo_methods.items():
        getattr(repo, name).return_value = value
    service = DomainEntityService()
    service.repo = repo
    service.category_repo = SimpleNamespace(get=AsyncMock(return_value={"code": "env_quality"}))
    service._remap_waiting_review_tasks = AsyncMock(return_value=0)
    return service, repo


async def test_delete_entity_moves_to_trash_instead_of_removing_row():
    service, repo = _service(get_by_id_or_key=_entity(), soft_delete=True)

    assert await service.delete_entity("noise_equipment") is True
    repo.soft_delete.assert_awaited_once_with("ent-1")


async def test_delete_entity_missing_entity_raises():
    service, repo = _service(get_by_id_or_key=None)

    with pytest.raises(ValueError, match="不存在"):
        await service.delete_entity("ghost")
    repo.soft_delete.assert_not_awaited()


async def test_restore_rejects_entity_not_in_trash():
    service, repo = _service(get_by_id_or_key=_entity(deleted_at=None))

    with pytest.raises(ValueError, match="不在回收站中"):
        await service.restore_entity("noise_equipment")
    repo.restore.assert_not_awaited()


async def test_restore_reloads_restored_entity_after_clearing_deleted_at():
    trashed = _entity(deleted_at="2026-11-15T01:00:00+00:00")
    service, repo = _service(get_by_id_or_key=trashed)
    repo.get_by_id.return_value = _entity(deleted_at=None)

    restored = await service.restore_entity("noise_equipment")

    repo.restore.assert_awaited_once_with("ent-1")
    assert restored["deleted_at"] is None


async def test_purge_requires_row_already_in_trash():
    service, repo = _service(get_by_id_or_key=_entity(deleted_at=None))

    with pytest.raises(ValueError, match="先删除再彻底删除"):
        await service.purge_entity("noise_equipment")
    repo.purge.assert_not_awaited()


async def test_purge_removes_trashed_row():
    service, repo = _service(get_by_id_or_key=_entity(deleted_at="2026-11-15T01:00:00+00:00"), purge=True)

    assert await service.purge_entity("noise_equipment") is True
    repo.purge.assert_awaited_once_with("ent-1")


async def test_create_rejects_key_living_in_trash():
    service, repo = _service(get_by_key=_entity(deleted_at="2026-11-15T01:00:00+00:00"))

    with pytest.raises(ValueError, match="回收站"):
        await service.create_entity({"entity_key": "noise_equipment", "name_cn": "噪声源", "category": "env_quality"})
    repo.create.assert_not_awaited()


async def test_clone_rejects_key_living_in_trash():
    service, repo = _service(get_by_id_or_key=_entity(), get_by_key=_entity(deleted_at="2026-11-15T01:00:00+00:00"))

    with pytest.raises(ValueError, match="回收站"):
        await service.clone_entity("noise_equipment", "noise_equipment_v2", "噪声源 V2")


async def test_update_passes_optimistic_lock_arguments_to_repository():
    service, repo = _service(get_by_id_or_key=_entity(), update=_entity(name_cn="噪声源（改）"))

    await service.update_entity(
        "noise_equipment",
        {"name_cn": "噪声源（改）", "properties": []},
        expected_updated_at="2026-11-15T00:00:00+00:00",
        force=False,
    )

    _, kwargs = repo.update.await_args
    assert kwargs == {"expected_updated_at": "2026-11-15T00:00:00+00:00", "force": False}


async def test_update_raises_when_row_vanished_before_write():
    service, _ = _service(get_by_id_or_key=_entity(), update=None)

    with pytest.raises(ValueError, match="移入回收站"):
        await service.update_entity("noise_equipment", {"name_cn": "噪声源"})


async def test_list_entities_reports_trash_total():
    service, repo = _service(list_all=[], count_deleted=2)

    result = await service.list_entities(domain_code="general")

    assert result == {"entity_schemas": [], "total": 0, "trash_total": 2}
