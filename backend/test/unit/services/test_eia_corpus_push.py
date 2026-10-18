"""eia_corpus_push 单测：no-op/首推/替换/失败镜像/绑定校验（knowledge_base 与 MinIO 全打桩）。"""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest

from yuxi.services import eia_corpus_task_service as svc


class FakeRepo:
    def __init__(self, row=None):
        self.row = row
        self.updates: list[dict] = []

    async def get_file(self, file_id):
        return self.row

    async def update_file(self, file_id, fields):
        self.updates.append(dict(fields))
        for k, v in fields.items():
            setattr(self.row, k, v)
        return self.row


class FakeMinIO:
    def __init__(self, md_bytes: bytes):
        self.md_bytes = md_bytes
        self.public_endpoint = "minio:9000"

    async def adownload_file(self, bucket, obj):
        return self.md_bytes


def make_row(**kw):
    row = SimpleNamespace(
        id=1,
        original_filename="样例报告.docx",
        md_status="ready",
        md_object_key="eia-library/.canonical/x.md",
        md_sha1=None,
        kb_id=None,
        kb_file_id=None,
        kb_status=None,
    )
    for k, v in kw.items():
        setattr(row, k, v)
    return row


@pytest.fixture()
def kb_spy(monkeypatch):
    calls = {"add": 0, "parse": 0, "index": 0, "delete": 0}

    async def fake_add(kb_id, item, params=None, operator_id=None):
        calls["add"] += 1
        assert params["content_type"] == "file"
        assert params["source_path"] == "样例报告.md"
        assert item.startswith("http://minio:9000/knowledgebases/eia-library/.canonical/")
        return {"file_id": "file_abc"}

    async def fake_parse(kb_id, file_id, operator_id=None, **owner):
        calls["parse"] += 1

    async def fake_index(kb_id, file_id, operator_id=None, **kw):
        calls["index"] += 1

    async def fake_delete(kb_id, file_id):
        calls["delete"] += 1

    monkeypatch.setattr(svc.knowledge_base, "add_file_record", fake_add)
    monkeypatch.setattr(svc.knowledge_base, "parse_file", fake_parse)
    monkeypatch.setattr(svc.knowledge_base, "index_file", fake_index)
    monkeypatch.setattr(svc.knowledge_base, "delete_file", fake_delete)
    return calls


@pytest.fixture()
def minio_spy(monkeypatch):
    md = "# 1 概述\n正文。\n".encode()
    fake = FakeMinIO(md)
    monkeypatch.setattr(svc, "get_minio_client", lambda: fake)
    monkeypatch.setattr(svc, "_md_minio_url", lambda key: f"http://minio:9000/knowledgebases/{key}")
    return fake


def test_push_noop_when_unchanged(monkeypatch, kb_spy, minio_spy):
    md_sha1 = hashlib.sha1(minio_spy.md_bytes).hexdigest()
    row = make_row(kb_file_id="file_old", kb_status="indexed", md_sha1=md_sha1)
    repo = FakeRepo(row)
    monkeypatch.setattr(svc, "_repo", repo)
    status = asyncio.run(svc._push_one(row, "kb_test", "tester"))
    assert status == "indexed"
    assert kb_spy == {"add": 0, "parse": 0, "index": 0, "delete": 0}  # md 未变 → no-op


def test_push_first_upload_full_chain(monkeypatch, kb_spy, minio_spy):
    row = make_row()
    repo = FakeRepo(row)
    monkeypatch.setattr(svc, "_repo", repo)
    status = asyncio.run(svc._push_one(row, "kb_test", "tester"))
    assert status == "indexed"
    assert kb_spy == {"add": 1, "parse": 1, "index": 1, "delete": 0}
    assert row.kb_file_id == "file_abc"
    assert row.md_sha1 == hashlib.sha1(minio_spy.md_bytes).hexdigest()
    assert [u["kb_status"] for u in repo.updates] == ["pushed", "parsing", "indexing", "indexed"]


def test_push_replace_when_md_changed(monkeypatch, kb_spy, minio_spy):
    row = make_row(kb_file_id="file_old", kb_status="indexed", md_sha1="stale-sha1")
    repo = FakeRepo(row)
    monkeypatch.setattr(svc, "_repo", repo)
    status = asyncio.run(svc._push_one(row, "kb_test", "tester"))
    assert status == "indexed"
    assert kb_spy["delete"] == 1  # md 已重产 → 替换（删旧登新）
    assert kb_spy["add"] == 1 and row.kb_file_id == "file_abc"


def test_push_retry_after_failed_replaces_stale_kb_record(monkeypatch, kb_spy, minio_spy):
    md_sha1 = hashlib.sha1(minio_spy.md_bytes).hexdigest()
    row = make_row(kb_file_id="file_old", kb_status="failed", md_sha1=md_sha1)
    repo = FakeRepo(row)
    monkeypatch.setattr(svc, "_repo", repo)
    status = asyncio.run(svc._push_one(row, "kb_test", "tester"))
    assert status == "indexed"
    assert kb_spy["delete"] == 1  # failed 半途登记须清理，否则 KB 侧重复文档
    assert kb_spy["add"] == 1 and row.kb_file_id == "file_abc"


def test_push_parse_failure_marks_failed(monkeypatch, kb_spy, minio_spy):
    async def boom(kb_id, file_id, operator_id=None, **owner):
        raise RuntimeError("解析引擎不可用")

    monkeypatch.setattr(svc.knowledge_base, "parse_file", boom)
    row = make_row()
    monkeypatch.setattr(svc, "_repo", FakeRepo(row))
    with pytest.raises(RuntimeError, match="解析引擎不可用"):
        asyncio.run(svc._push_one(row, "kb_test", "tester"))


def test_run_push_task_failure_mirror(monkeypatch, kb_spy, minio_spy):
    """run_eia_corpus_push 对逐文件异常容错并镜像 kb_status=failed。"""
    async def boom(kb_id, file_id, operator_id=None, **owner):
        raise RuntimeError("索引失败")

    monkeypatch.setattr(svc.knowledge_base, "index_file", boom)
    monkeypatch.setattr(svc, "_repo", FakeRepo(make_row()))
    monkeypatch.setattr(svc, "_resolve_kb_id", _fake_resolve)

    class FakeContext:
        payload = {"file_ids": [1], "operator_id": "tester"}
        task_id = "t1"
        worker_id = "w1"

        async def raise_if_cancelled(self):
            pass

        async def set_progress(self, pct, msg):
            pass

        async def set_result(self, result):
            FakeContext.result = result

    summary = asyncio.run(svc.run_eia_corpus_push(FakeContext()))
    assert summary["failed"] == 1
    assert summary["items"][0]["status"] == "failed"


async def _fake_resolve():
    return "kb_test"


def test_resolve_kb_id_unbound(monkeypatch):
    async def fake_get():
        return ""

    monkeypatch.setattr(svc, "get_bound_kb_id", fake_get)
    with pytest.raises(ValueError, match="未绑定环评语料知识库"):
        asyncio.run(svc._resolve_kb_id())


def test_bind_corpus_kb_validates_and_persists(monkeypatch):
    persisted = {}

    async def fake_ensure(kb_id):
        if kb_id == "kb_missing":
            raise ValueError(f"绑定的知识库不存在: {kb_id}")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def commit(self):
            persisted["committed"] = True

    def fake_ctx():
        return FakeSession()

    async def fake_update(session, key, value, updated_by):
        persisted.update(value)

    monkeypatch.setattr(svc, "_ensure_kb_exists", fake_ensure)
    monkeypatch.setattr(svc.pg_manager, "get_async_session_context", fake_ctx)
    monkeypatch.setattr(svc, "update_option_value", fake_update)
    assert asyncio.run(svc.bind_corpus_kb("kb_target", "tester")) == "kb_target"
    assert persisted.get("eia_corpus_kb_id") == "kb_target"
    with pytest.raises(ValueError, match="绑定的知识库不存在"):
        asyncio.run(svc.bind_corpus_kb("kb_missing", "tester"))
