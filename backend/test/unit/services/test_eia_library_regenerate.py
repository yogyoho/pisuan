"""eia_library regenerate_md 单测：md_sha1 只在推送成功时刷新，重产不覆写（bug-4010）。

md_sha1 语义=「最近一次推送确认的 KB 内容指纹」；regenerate_md 若覆写它，_push_one 的
no-op 捷径（kb_file_id + indexed + md_sha1 相同）会被新指纹误命中，KB 永久陈旧。
"""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest

from yuxi.services import eia_library_service as svc


class FakeRepo:
    def __init__(self, row):
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
    def __init__(self):
        self.puts: list[tuple[str, bytes]] = []

    async def adownload_file(self, bucket, obj):
        return b"docx-bytes"

    async def aupload_file(self, bucket, obj, data, content_type):
        self.puts.append((obj, data))


def make_row(**kw):
    base = dict(
        id=1,
        original_filename="样例报告.docx",
        stored_path="abc__样例报告.docx",
        object_key="eia-library/abc__样例报告.docx",
        md_object_key="eia-library/.canonical/abc__样例报告.docx.md",
        md_status="ready",
        md_chars=100,
        md_sha1="pushed-sha",
        kb_file_id=7,
        kb_status="indexed",
    )
    base.update(kw)
    row = SimpleNamespace(**base)
    row.to_dict = lambda: {"md_status": row.md_status, "md_chars": row.md_chars}
    return row


@pytest.fixture
def env(monkeypatch):
    minio = FakeMinIO()
    monkeypatch.setattr(svc, "get_minio_client", lambda: minio)
    monkeypatch.setattr(
        svc,
        "docx_bytes_to_canonical_md",
        lambda data, label="": SimpleNamespace(chars=120, md="# 1 总论\n正文", front_paras=[]),
    )
    return minio


def test_regenerate_pushed_row_keeps_pushed_md_sha1(env):
    row = make_row()
    service = svc.EiaLibraryService(repo=FakeRepo(row))
    out = asyncio.run(service.regenerate_md(row.id, "qa"))
    assert out["md_status"] == "ready"
    assert row.md_sha1 == "pushed-sha"  # 指纹未被重产覆写（bug-4010）
    assert all("md_sha1" not in u for u in service.repo.updates)


def test_regenerate_unpushed_row_also_keeps_sha(env):
    """未推送行同样不覆写：指纹语义统一为「推送确认」，上传初值之外只在推送刷新。"""
    row = make_row(kb_file_id=None, kb_status=None)
    service = svc.EiaLibraryService(repo=FakeRepo(row))
    asyncio.run(service.regenerate_md(row.id, "qa"))
    assert all("md_sha1" not in u for u in service.repo.updates)


def test_regenerated_row_would_not_noop_on_push(env):
    """重产后 MinIO 现态指纹 ≠ 行指纹 → _push_one 的 no-op 三条件不再全真（走删旧登新）。"""
    row = make_row()
    service = svc.EiaLibraryService(repo=FakeRepo(row))
    asyncio.run(service.regenerate_md(row.id, "qa"))
    md_bytes = env.puts[-1][1]
    assert hashlib.sha1(md_bytes).hexdigest() != row.md_sha1


def test_regenerate_writes_new_md_object(env):
    row = make_row()
    service = svc.EiaLibraryService(repo=FakeRepo(row))
    asyncio.run(service.regenerate_md(row.id, "qa"))
    assert env.puts == [("eia-library/.canonical/abc__样例报告.docx.md", "# 1 总论\n正文".encode())]
