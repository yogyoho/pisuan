"""eia_library delete 级联 + 上传同名 stem 守卫单测（bug-4012 / bug-4013）。

#2 库删除须级联删 KB 文档（先于本地删除）：孤儿文档会让下次编译 fail fast 全局阻断；
#3 同名 stem 上传即拦（409）：否则编译期 rows_by_stem 无法唯一定位，晚爆炸在链路最痛点。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuxi.services import eia_library_service as svc


class FakeRepo:
    def __init__(self, rows=None, by_sha=None):
        self.rows = {r["id"]: r for r in (rows or [])}
        self.by_sha = by_sha
        self.deleted: list[int] = []

    async def get_file(self, file_id):
        row = self.rows.get(file_id)
        return SimpleNamespace(**row) if row else None

    async def delete_file(self, file_id):
        self.deleted.append(file_id)
        self.rows.pop(file_id, None)

    async def get_file_by_sha1(self, sha1):
        return self.by_sha

    async def list_files(self):
        return [dict(r, id=r["id"]) for r in self.rows.values()]


class FakeMinIO:
    def __init__(self):
        self.deleted: list[str] = []

    async def adelete_file(self, bucket, obj):
        self.deleted.append(obj)

    async def adownload_file(self, bucket, obj):
        return b"docx-bytes"

    async def aupload_file(self, bucket, obj, data, content_type):
        pass


class FakeKB:
    def __init__(self, fail=False):
        self.deleted: list[tuple[str, str]] = []
        self.fail = fail

    async def delete_file(self, kb_id, file_id):
        if self.fail:
            raise RuntimeError("kb down")
        self.deleted.append((kb_id, file_id))


def make_row(**kw):
    base = dict(
        id=1,
        original_filename="样例报告.docx",
        stored_path="abc__样例报告.docx",
        object_key="eia-library/abc__样例报告.docx",
        md_object_key="eia-library/.canonical/abc__样例报告.docx.md",
        kb_id="kb_x",
        kb_file_id="f9",
    )
    base.update(kw)
    return base


@pytest.fixture
def io_env(monkeypatch):
    minio = FakeMinIO()
    monkeypatch.setattr(svc, "get_minio_client", lambda: minio)
    return minio


def test_delete_cascades_kb_before_local(io_env, monkeypatch):
    log: list[str] = []
    kb = FakeKB()

    async def kb_del(kb_id, file_id):
        log.append(f"kb:{kb_id}:{file_id}")
        await kb.delete_file(kb_id, file_id)

    monkeypatch.setattr(svc, "knowledge_base", SimpleNamespace(delete_file=kb_del))
    repo = FakeRepo(rows=[make_row()])
    service = svc.EiaLibraryService(repo=repo, storage_root="unused")

    orig_delete = repo.delete_file

    async def tracked_delete(fid):
        log.append("db")
        await orig_delete(fid)

    repo.delete_file = tracked_delete
    asyncio.run(service.delete(1))
    assert kb.deleted == [("kb_x", "f9")]
    assert log == ["kb:kb_x:f9", "db"]  # KB 先于 DB/MinIO
    assert io_env.deleted == ["eia-library/abc__样例报告.docx", "eia-library/.canonical/abc__样例报告.docx.md"]


def test_delete_skips_cascade_when_never_pushed(io_env, monkeypatch):
    kb = FakeKB()
    monkeypatch.setattr(svc, "knowledge_base", kb)
    repo = FakeRepo(rows=[make_row(kb_id=None, kb_file_id=None)])
    service = svc.EiaLibraryService(repo=repo, storage_root="unused")
    asyncio.run(service.delete(1))
    assert kb.deleted == []
    assert repo.deleted == [1]


def test_delete_aborts_when_kb_delete_fails(io_env, monkeypatch):
    """KB 删除失败 → 中止：DB 行与 MinIO 对象保持原状（重试语义干净）。"""
    kb = FakeKB(fail=True)
    monkeypatch.setattr(svc, "knowledge_base", kb)
    repo = FakeRepo(rows=[make_row()])
    service = svc.EiaLibraryService(repo=repo, storage_root="unused")
    with pytest.raises(RuntimeError, match="kb down"):
        asyncio.run(service.delete(1))
    assert repo.deleted == [] and io_env.deleted == []


def test_upload_rejects_duplicate_stem(tmp_path, monkeypatch):
    async def fake_write(file, path, max_size_bytes=None, too_large_message=None):
        Path(path).write_bytes(b"new-bytes")

    monkeypatch.setattr(svc, "write_upload_to_path", fake_write)
    repo = FakeRepo(rows=[make_row(id=2, original_filename="旧报告.docx", object_key="k", md_object_key="m")])
    service = svc.EiaLibraryService(repo=repo, storage_root=tmp_path)
    file = SimpleNamespace(filename="旧报告.pdf", content_type="application/pdf")
    with pytest.raises(FileExistsError, match="旧报告"):
        asyncio.run(service.upload(file, None, "qa"))


def test_upload_allows_distinct_stem(tmp_path, monkeypatch):
    async def fake_write(file, path, max_size_bytes=None, too_large_message=None):
        Path(path).write_bytes(b"new-bytes")

    monkeypatch.setattr(svc, "write_upload_to_path", fake_write)
    minio = FakeMinIO()
    monkeypatch.setattr(svc, "get_minio_client", lambda: minio)
    monkeypatch.setattr(
        svc,
        "docx_bytes_to_canonical_md",
        lambda data, label="": SimpleNamespace(chars=120, md="# 1 总论\n正文", front_paras=[]),
    )

    class InsertRepo(FakeRepo):
        def __init__(self, rows=None, by_sha=None):
            super().__init__(rows, by_sha)
            self.inserted = None

        async def insert_file(self, row):
            row.id = 99  # 模拟 DB 自增
            self.inserted = row
            return row

        async def get_file(self, file_id):
            if file_id == 99:
                return self.inserted
            return await super().get_file(file_id)

        async def update_file(self, file_id, fields):
            for k, v in fields.items():
                setattr(self.inserted, k, v)
            return self.inserted

    repo = InsertRepo(rows=[make_row(id=2, original_filename="别的名字.docx", object_key="k", md_object_key="m")])
    service = svc.EiaLibraryService(repo=repo, storage_root=tmp_path)
    file = SimpleNamespace(filename="新报告.docx", content_type="application/octet-stream")
    out = asyncio.run(service.upload(file, None, "qa"))
    assert out["md_status"] == "ready"
