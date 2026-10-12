"""EiaEntityService 单测（P3-2：sample_entities 仅添加 + 文本级导出物化注册表 + _index）。

字节纪律：registry/_index 实况 CRLF + indent2；实体数组条目 6 空格缩进、
空数组为内联 []；导出仅追加目标数组尾 + _index counts 数字，禁止全文件重写。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from yuxi.services import eia_entity_service as svc_mod
from yuxi.services.eia_entity_service import EiaEntityService

# 实况同构最小夹具（CRLF、2 空格缩进、无尾换行——与 baiyinhua2.json 实测一致）
_REGISTRY_TEXT = (
    "{\r\n"
    '  "sample_slug": "demo_a",\r\n'
    '  "source": ".wolf/tmp/eia-samples/demo_a-outline.md",\r\n'
    '  "entities": {\r\n'
    '    "projects": [\r\n'
    '      "某矿区一号井田",\r\n'
    '      "某矿区二号井田"\r\n'
    "    ],\r\n"
    '    "mines": [],\r\n'
    '    "orgs": [\r\n'
    '      "某旗自然资源局"\r\n'
    "    ],\r\n"
    '    "places": [],\r\n'
    '    "sensitive": []\r\n'
    "  },\r\n"
    '  "generic_terms": [],\r\n'
    '  "aux": {"people": [], "doc_numbers": [], "privacy_notes": []},\r\n'
    '  "notes": []\r\n'
    "}"
)

_INDEX_TEXT = (
    "{\r\n"
    '  "generated": "2026-09-06",\r\n'
    '  "purpose": "per-sample 实体注册表",\r\n'
    '  "schema": "{sample_slug, entities, ...}",\r\n'
    '  "samples": [\r\n'
    "    {\r\n"
    '      "slug": "demo_a",\r\n'
    '      "file": "sample_entities/demo_a.json",\r\n'
    '      "counts": {"projects": 2, "mines": 0, "orgs": 1, "places": 0, "sensitive": 0},\r\n'
    '      "aux": {"people": 0, "doc_numbers": 0, "privacy_notes": 0}\r\n'
    "    },\r\n"
    "    {\r\n"
    '      "slug": "tarangaole",\r\n'
    '      "file": "sample_entities/tarangaole.json",\r\n'
    '      "counts": {"projects": 0, "mines": 0, "orgs": 0, "places": 0, "sensitive": 0},\r\n'
    '      "aux": {"people": 0, "doc_numbers": 0, "privacy_notes": 0}\r\n'
    "    }\r\n"
    "  ],\r\n"
    '  "skipped": [\r\n'
    '    {"slug": "tarangaole", "reason": "outline 无 entities 节，跳过"}\r\n'
    "  ]\r\n"
    "}"
)


class _FakeRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserts = []
        self.deletes = []

    async def list_additions(self, sample_slug=None):
        return [r for r in self.rows if sample_slug is None or r.sample_slug == sample_slug]

    async def insert_addition(self, sample_slug, etype, name, rid, note, username):
        self.inserts.append((sample_slug, etype, name, rid, note, username))
        return SimpleNamespace(
            id=len(self.inserts),
            sample_slug=sample_slug,
            etype=etype,
            name=name,
            rid=rid,
            note=note,
            decided_by=username,
            updated_at="2026-10-12T00:00:00",
        )

    async def delete_addition(self, addition_id):
        self.deletes.append(addition_id)
        return True


def _row(slug="demo_a", etype="places", name="呼日热音高勒", rid="012-x", note=None):
    return SimpleNamespace(
        id=1,
        sample_slug=slug,
        etype=etype,
        name=name,
        rid=rid,
        note=note,
        decided_by="admin",
        updated_at="2026-10-12T00:00:00",
    )


@pytest.fixture
def entities_dir(tmp_path, monkeypatch):
    d = tmp_path / "sample_entities"
    d.mkdir()
    (d / "_index.json").write_text(_INDEX_TEXT, encoding="utf-8", newline="")
    (d / "demo_a.json").write_text(_REGISTRY_TEXT, encoding="utf-8", newline="")
    monkeypatch.setattr(svc_mod, "SAMPLE_ENTITIES_DIR", d)
    monkeypatch.setattr(svc_mod, "ENTITY_INDEX_PATH", d / "_index.json")
    return d


def _svc(repo=None) -> EiaEntityService:
    return EiaEntityService(repo=repo or _FakeRepo())


@pytest.mark.asyncio
async def test_list_samples_reads_index(entities_dir):
    out = await _svc().list_samples()
    assert [s["slug"] for s in out["samples"]] == ["demo_a", "tarangaole"]
    assert out["samples"][0]["counts"]["projects"] == 2
    assert out["skipped"] == [{"slug": "tarangaole", "reason": "outline 无 entities 节，跳过"}]


@pytest.mark.asyncio
async def test_get_registry_merges_pending_additions(entities_dir):
    repo = _FakeRepo([_row(etype="places", name="新敏感点", rid="012-x")])
    out = await EiaEntityService(repo=repo).get_registry("demo_a")
    assert out["sample_slug"] == "demo_a"
    assert out["entities"]["projects"] == [
        {"name": "某矿区一号井田", "pending": False, "id": None},
        {"name": "某矿区二号井田", "pending": False, "id": None},
    ]
    assert out["entities"]["places"] == [
        {"name": "新敏感点", "pending": True, "id": 1, "rid": "012-x", "note": None, "decided_by": "admin"}
    ]
    assert out["entities"]["mines"] == []


@pytest.mark.asyncio
async def test_add_entity_validates(entities_dir):
    repo = _FakeRepo()
    await _svc(repo).add_entity("demo_a", "mines", "某露天矿", "012-x", "补充", "admin")
    assert repo.inserts == [("demo_a", "mines", "某露天矿", "012-x", "补充", "admin")]

    with pytest.raises(KeyError, match="未知样例"):
        await _svc(_FakeRepo()).add_entity("nope", "mines", "x", None, None, "admin")
    with pytest.raises(ValueError, match="skipped"):
        await _svc(_FakeRepo()).add_entity("tarangaole", "mines", "x", None, None, "admin")
    with pytest.raises(ValueError, match="etype"):
        await _svc(_FakeRepo()).add_entity("demo_a", "rivers", "x", None, None, "admin")
    with pytest.raises(ValueError, match="已存在"):
        await _svc(_FakeRepo()).add_entity("demo_a", "projects", "某矿区一号井田", None, None, "admin")
    with pytest.raises(ValueError, match="参考值|名称"):
        await _svc(_FakeRepo()).add_entity("demo_a", "mines", "  ", None, None, "admin")


@pytest.mark.asyncio
async def test_export_appends_nonempty_and_empty_arrays(entities_dir):
    repo = _FakeRepo([_row(etype="projects", name="某矿区三号井田"), _row(etype="places", name="新敏感点")])
    out = await _svc(repo).export_entities("admin")
    assert out["results"] == {"demo_a": {"materialized": 2, "skipped": 0}}

    text = (entities_dir / "demo_a.json").read_text(encoding="utf-8", newline="")
    assert '\r\n      "某矿区三号井田"\r\n    ],' in text
    assert '"places": [\r\n      "新敏感点"\r\n    ]' in text
    assert '"mines": []' in text
    assert text.startswith("{\r\n")
    assert not text.endswith("\r\n")
    doc = json.loads(text)
    assert doc["entities"]["projects"] == ["某矿区一号井田", "某矿区二号井田", "某矿区三号井田"]
    assert doc["entities"]["places"] == ["新敏感点"]


@pytest.mark.asyncio
async def test_export_updates_index_counts_and_is_idempotent(entities_dir):
    repo = _FakeRepo([_row(etype="projects", name="某矿区三号井田"), _row(etype="places", name="新敏感点")])
    svc = _svc(repo)
    await svc.export_entities("admin")
    idx_text = (entities_dir / "_index.json").read_text(encoding="utf-8", newline="")
    assert '"projects": 3' in idx_text
    assert '"places": 1' in idx_text
    assert '"mines": 0' in idx_text

    out2 = await svc.export_entities("admin")
    idx_text2 = (entities_dir / "_index.json").read_text(encoding="utf-8", newline="")
    assert idx_text2 == idx_text
    assert out2["results"] == {"demo_a": {"materialized": 0, "skipped": 2}}


@pytest.mark.asyncio
async def test_withdraw_entity_deletes_row(entities_dir):
    repo = _FakeRepo()
    assert await _svc(repo).withdraw_entity(7) is True
    assert repo.deletes == [7]
