# merge_entity_into / merge_property_into 单测（fake repo + fake session，无真实 DB）。
# 验证：引用改写（裸键+前缀）、属性并集去重、synonym 沉淀、软删、版本返回。
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from yuxi.services.domain_entity_service import DomainEntityService


def ent(key, name, props, synonyms=None, domain_code="general", deleted_at=None):
    return SimpleNamespace(
        entity_id=f"id-{key}",
        entity_key=key,
        name_cn=name,
        deleted_at=deleted_at,
        to_dict=lambda: {
            "entity_id": f"id-{key}",
            "entity_key": key,
            "name_cn": name,
            "domain_code": domain_code,
            "synonyms": list(synonyms or []),
            "properties": [dict(p) for p in props],
            "updated_at": "2026-11-18T00:00:00",
            "deleted_at": deleted_at,
        }
    )


def slot(ref):
    return {"name": "x", "entity_ref": ref}


def para(ref):
    return {"title": "t", "template": {"slots": [slot(ref)]}}


class FakeSession:
    """execute(select(Pps)) → 返回带 entity_key 的假行。"""

    def __init__(self, pps_rows):
        self._rows = pps_rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    async def execute(self, _query):
        return FakeSession._Result(self._rows)

    async def commit(self):
        return None


class FakeFactoryRepo:
    def __init__(self, tasks, learned):
        self.tasks = tasks
        self.learned = learned
        self.updated_tasks = []
        self.rewritten = None

    async def list_usage_pending_tasks(self, _domain):
        return self.tasks

    async def update_task(self, task_id, payload):
        self.updated_tasks.append(task_id)
        return True

    async def list_usage_learned_templates(self, _domain):
        return self.learned

    async def rewrite_learned_template_slot_refs(self, ref_map):
        self.rewritten = dict(ref_map)
        return len(ref_map)


class FakePps:
    def __init__(self, entity_key):
        self.entity_key = entity_key


@pytest.fixture()
def service(monkeypatch):
    svc = DomainEntityService()
    svc.update_entity = asyncio.run  # 占位，具体用例里覆写
    return svc


def _patch_common(monkeypatch, svc, entities, tasks, learned, pps_rows, calls, trashed=None):
    from yuxi.repositories import domain_factory_repository as factory_module
    from yuxi.storage.postgres import manager as manager_module

    class FakeRepo:
        trashed: list = []

        async def get_by_id_or_key(self, key, include_deleted=False):
            pool = list(entities) + list(self.trashed)
            for e in pool:
                d = e.to_dict()
                if d["entity_key"] == key or d["entity_id"] == key:
                    if not include_deleted and d in [x.to_dict() for x in self.trashed]:
                        return None
                    return e
            return None

        async def list_all(self, domain_code=None, category=None):
            return list(entities)

        async def soft_delete(self, entity_id):
            calls.setdefault("deleted", []).append(entity_id)
            return True

        async def restore(self, entity_id):
            calls.setdefault("restored", []).append(entity_id)
            return True

        async def get_by_id(self, entity_id):
            for e in list(entities) + list(self.trashed):
                if e.to_dict()["entity_id"] == entity_id:
                    return e
            return None

    fake_factory = FakeFactoryRepo(tasks, learned)

    async def fake_update(self, identifier, payload, expected_updated_at=None, force=False):
        calls.setdefault("updates", []).append((identifier, payload))
        return {"entity_key": identifier, "updated_at": "2026-11-18T01:00:00", **payload}

    async def fake_delete(self, identifier):
        calls.setdefault("deleted", []).append(identifier)
        return True

    async def fake_remap(self):
        calls.setdefault("remaps", []).append(1)
        return 1

    monkeypatch.setattr(factory_module, "DomainFactoryRepository", lambda: fake_factory)

    @asynccontextmanager
    async def fake_ctx():
        yield FakeSession(pps_rows)

    monkeypatch.setattr(manager_module.pg_manager, "get_async_session_context", fake_ctx)
    fake_repo = FakeRepo()
    fake_repo.trashed = list(trashed or [])
    fake_repo.rewritten = None
    svc.repo = fake_repo
    svc.update_entity = fake_update.__get__(svc, type(svc)) if False else (
        lambda identifier, payload, expected_updated_at=None, force=False: fake_update(svc, identifier, payload)
    )
    svc.delete_entity = lambda identifier: fake_delete(svc, identifier)
    svc._remap_waiting_review_tasks = lambda: fake_remap(None)
    return fake_factory, fake_repo


def test_merge_entity_into_rewrites_and_merges(monkeypatch):
    svc = DomainEntityService()
    entities = [
        ent("src", "源实体", [{"key": "dup", "name_cn": "重复属性"}, {"key": "uniq", "name_cn": "独有属性"}]),
        ent("tgt", "目标实体", [{"key": "keep", "name_cn": "重复属性"}]),
    ]
    tasks = [{"id": "t1", "source_paragraphs": [para("src.dup"), para("src.uniq"), para("src"), para("tgt.keep")]}]
    learned = [{"id": "l1", "slots": [slot("src.uniq")]}]
    pps = [FakePps("src.uniq"), FakePps("tgt.keep")]
    calls = {}
    fake_factory, fake_repo = _patch_common(monkeypatch, svc, entities, tasks, learned, pps, calls)

    result = asyncio.run(svc.merge_entity_into("src", "tgt"))

    # 引用改写：src.* → tgt.*，裸键 src → tgt，tgt.* 不动
    slots = [s["entity_ref"] for p in tasks[0]["source_paragraphs"] for s in p["template"]["slots"]]
    assert slots == ["tgt.dup", "tgt.uniq", "tgt", "tgt.keep"]
    assert fake_factory.rewritten == {"src.uniq": "tgt.uniq"}
    assert pps[0].entity_key == "tgt.uniq" and pps[1].entity_key == "tgt.keep"
    # 属性并集：dup 跳过、uniq 追加；synonym 沉淀源实体名
    payload = calls["updates"][0][1]
    names = [p["name_cn"] for p in payload["properties"]]
    assert names == ["重复属性", "独有属性"]
    assert "源实体" in payload["synonyms"]
    # 软删 + remap
    assert calls["deleted"] == ["src"]
    assert result["moved_props"] == 1 and result["tasks_touched"] == 1 and result["remapped"] == 1


def test_merge_entity_into_validations(monkeypatch):
    svc = DomainEntityService()
    entities = [
        ent("a", "A", [{"key": "x", "name_cn": "甲"}]),
        ent("b", "B", [{"key": "x", "name_cn": "甲"}], domain_code="other"),
    ]
    _patch_common(monkeypatch, svc, entities, [], [], [], {})
    with pytest.raises(ValueError, match="相同"):
        asyncio.run(svc.merge_entity_into("a", "a"))
    with pytest.raises(ValueError, match="不存在"):
        asyncio.run(svc.merge_entity_into("a", "ghost"))
    with pytest.raises(ValueError, match="跨域"):
        asyncio.run(svc.merge_entity_into("a", "b"))


def test_merge_property_into_deposits_synonyms(monkeypatch):
    svc = DomainEntityService()
    e = ent(
        "demo",
        "演示实体",
        [
            {"key": "old_key", "name_cn": "旧名", "synonyms": ["旧别名"]},
            {"key": "new_key", "name_cn": "新名", "synonyms": []},
        ],
    )
    tasks = [{"id": "t1", "source_paragraphs": [para("demo.old_key")]}]
    pps = [FakePps("demo.old_key")]
    calls = {}
    _patch_common(monkeypatch, svc, [e], tasks, [], pps, calls)

    result = asyncio.run(svc.merge_property_into("demo", "old_key", "new_key"))

    payload = calls["updates"][0][1]
    assert [p["key"] for p in payload["properties"]] == ["new_key"]
    target = payload["properties"][0]
    assert "旧名" in target["synonyms"] and "旧别名" in target["synonyms"]
    assert tasks[0]["source_paragraphs"][0]["template"]["slots"][0]["entity_ref"] == "demo.new_key"
    assert pps[0].entity_key == "demo.new_key"
    assert result["tasks_touched"] == 1 and result["pps_rewritten"] == 1


def test_restore_blocked_when_merged(monkeypatch):
    svc = DomainEntityService()
    tgt = ent("tgt", "目标实体", [{"key": "keep", "name_cn": "重复属性"}], synonyms=["源实体"])
    trashed_src = ent("src", "源实体", [{"key": "dup", "name_cn": "重复属性"}], deleted_at="2026-11-18T00:00:00")
    calls = {}
    _, fake_repo = _patch_common(monkeypatch, svc, [tgt], [], [], [], calls, trashed=[trashed_src])

    with pytest.raises(ValueError, match="已被归并"):
        asyncio.run(svc.restore_entity("src"))
    assert calls.get("restored") is None


def test_restore_passes_without_merge_signature(monkeypatch):
    svc = DomainEntityService()
    tgt = ent("tgt", "目标实体", [{"key": "keep", "name_cn": "重复属性"}])
    trashed_x = ent("xx", "无关实体", [{"key": "k", "name_cn": "别的属性"}], deleted_at="2026-11-18T00:00:00")
    calls = {}
    _, fake_repo = _patch_common(monkeypatch, svc, [tgt], [], [], [], calls, trashed=[trashed_x])

    result = asyncio.run(svc.restore_entity("xx"))
    assert calls.get("restored") == ["id-xx"]
    assert result["entity_key"] == "xx"


def test_merge_property_into_validations(monkeypatch):
    svc = DomainEntityService()
    e = ent("demo", "演示实体", [{"key": "a", "name_cn": "甲"}, {"key": "b", "name_cn": "乙"}])
    _patch_common(monkeypatch, svc, [e], [], [], [], {})
    with pytest.raises(ValueError, match="相同"):
        asyncio.run(svc.merge_property_into("demo", "a", "a"))
    with pytest.raises(ValueError, match="不存在"):
        asyncio.run(svc.merge_property_into("demo", "a", "ghost"))
