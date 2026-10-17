"""eia_library_service 单测：sha1 命名/去重、越限拒收、移动、删除、清单过滤（仓储以内存桩替身）。"""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from yuxi.services.eia_library_service import (
    EiaLibraryService,
    LibraryFileTooLarge,
    _safe_filename,
)

SHA1_HELLO = "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"  # sha1(b"hello")


class FakeRepo:
    def __init__(self):
        self.folders = {1: SimpleNamespace(id=1, name="规划环评"), 2: SimpleNamespace(id=2, name="后评价")}
        self.files: list = []
        self._next = 1

    async def get_folder(self, folder_id):
        return self.folders.get(folder_id)

    async def get_file_by_sha1(self, sha1):
        return next((f for f in self.files if f.content_sha1 == sha1), None)

    async def list_files(self, *, folder_id=None, q=None):
        rows = self.files
        if folder_id is not None:
            rows = [f for f in rows if f.folder_id == folder_id]
        if q:
            rows = [f for f in rows if q.lower() in f.original_filename.lower()]
        return [
            {**f.to_dict(), "folder_name": self.folders[f.folder_id].name if f.folder_id in self.folders else None}
            for f in rows
        ]

    async def insert_file(self, row):
        row.id = self._next
        self._next += 1
        self.files.append(row)
        return row

    async def get_file(self, file_id):
        return next((f for f in self.files if f.id == file_id), None)

    async def move_file(self, file_id, folder_id):
        row = await self.get_file(file_id)
        if row is not None:
            row.folder_id = folder_id
        return row

    async def delete_file(self, file_id):
        row = await self.get_file(file_id)
        if row is None:
            return False
        self.files.remove(row)
        return True


def make_service(tmp_path, max_size=None):
    return EiaLibraryService(repo=FakeRepo(), storage_root=tmp_path, max_size_bytes=max_size)


def make_upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


def test_upload_stores_sha1_named_file(tmp_path):
    svc = make_service(tmp_path)
    row = asyncio.run(svc.upload(make_upload(b"hello", "某矿区报告书.docx"), folder_id=1, uploaded_by="admin"))
    assert row["content_sha1"] == SHA1_HELLO
    assert row["stored_path"] == f"{SHA1_HELLO[:12]}__某矿区报告书.docx"
    assert row["size_bytes"] == 5
    assert (tmp_path / row["stored_path"]).read_bytes() == b"hello"
    assert row["status"] == "stored"


def test_upload_duplicate_sha1_rejected_and_tmp_cleaned(tmp_path):
    svc = make_service(tmp_path)
    asyncio.run(svc.upload(make_upload(b"hello", "a.docx"), folder_id=None, uploaded_by="admin"))
    with pytest.raises(FileExistsError):
        asyncio.run(svc.upload(make_upload(b"hello", "b.docx"), folder_id=None, uploaded_by="admin"))
    assert len(svc.repo.files) == 1
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]


def test_upload_oversize_raises_too_large(tmp_path):
    svc = make_service(tmp_path, max_size=4)
    with pytest.raises(LibraryFileTooLarge):
        asyncio.run(svc.upload(make_upload(b"0123456789", "big.docx"), folder_id=None, uploaded_by="admin"))
    assert svc.repo.files == []


def test_upload_to_unknown_folder_rejected(tmp_path):
    svc = make_service(tmp_path)
    with pytest.raises(ValueError, match="目标文件夹不存在"):
        asyncio.run(svc.upload(make_upload(b"x", "a.docx"), folder_id=99, uploaded_by="admin"))


def test_move_updates_folder(tmp_path):
    svc = make_service(tmp_path)
    row = asyncio.run(svc.upload(make_upload(b"hello", "a.docx"), folder_id=1, uploaded_by="admin"))
    out = asyncio.run(svc.move(row["id"], 2))
    assert out["folder_id"] == 2


def test_delete_removes_row_and_disk_file(tmp_path):
    svc = make_service(tmp_path)
    row = asyncio.run(svc.upload(make_upload(b"hello", "a.docx"), folder_id=None, uploaded_by="admin"))
    asyncio.run(svc.delete(row["id"]))
    assert svc.repo.files == []
    assert not (tmp_path / row["stored_path"]).exists()
    with pytest.raises(FileNotFoundError):
        asyncio.run(svc.delete(row["id"]))


def test_list_files_joins_folder_name(tmp_path):
    svc = make_service(tmp_path)
    asyncio.run(svc.upload(make_upload(b"hello", "alpha.docx"), folder_id=1, uploaded_by="admin"))
    asyncio.run(svc.upload(make_upload(b"world", "beta.docx"), folder_id=None, uploaded_by="admin"))
    all_files = asyncio.run(svc.list_files())
    assert len(all_files) == 2
    names = {f["original_filename"]: f["folder_name"] for f in all_files}
    assert names["alpha.docx"] == "规划环评"
    assert names["beta.docx"] is None
    hit = asyncio.run(svc.list_files(q="alp"))
    assert [f["original_filename"] for f in hit] == ["alpha.docx"]


def test_safe_filename_strips_unsafe_chars():
    assert _safe_filename(r"report\v2:final?.docx") == "report_v2_final_.docx"
    assert _safe_filename("..") == "unnamed"
