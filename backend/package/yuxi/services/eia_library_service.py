"""环评文件库服务（P1 进料区：上传即登记，加工属 P2 显式触发）。

溯源契约：content_sha1 全库唯一，是 P2 语料管线产物 source 字段的对账锚点
（spec 2026-10-17-eia-file-library-design.md 决策 D1）。
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from yuxi.repositories.eia_library_repository import EiaLibraryRepository
from yuxi.storage.postgres.models_domain_factory import EiaLibraryFile
from yuxi.utils.upload_utils import MAX_UPLOAD_SIZE_BYTES, write_upload_to_path


class LibraryFileTooLarge(ValueError):
    """上传文件超过大小上限（路由层映射 HTTP 413）。"""


class EiaLibraryService:
    def __init__(
        self,
        repo: EiaLibraryRepository | None = None,
        storage_root: str | Path | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        self.repo = repo or EiaLibraryRepository()
        self.storage_root = Path(storage_root or os.environ.get("EIA_LIBRARY_DIR", "/app/eia-library"))
        self.max_size_bytes = max_size_bytes or MAX_UPLOAD_SIZE_BYTES

    async def list_folders(self) -> list[dict]:
        return await self.repo.list_folders()

    async def count_files(self) -> int:
        return await self.repo.count_files()

    async def list_files(self, folder_id: int | None = None, q: str | None = None) -> list[dict]:
        return await self.repo.list_files(folder_id=folder_id, q=q)

    async def upload(self, file: UploadFile, folder_id: int | None, uploaded_by: str | None) -> dict:
        original = file.filename or ""
        if not original:
            raise ValueError("文件名不能为空")
        if folder_id is not None and await self.repo.get_folder(folder_id) is None:
            raise ValueError(f"目标文件夹不存在: {folder_id}")
        self.storage_root.mkdir(parents=True, exist_ok=True)
        tmp_path = self.storage_root / f".tmp-{os.getpid()}-{uuid.uuid4().hex}"
        try:
            try:
                await write_upload_to_path(
                    file,
                    tmp_path,
                    max_size_bytes=self.max_size_bytes,
                    too_large_message=f"文件超过大小上限（{self.max_size_bytes // (1024 * 1024)}MB）",
                )
            except ValueError as e:
                raise LibraryFileTooLarge(str(e)) from e
            sha1 = _sha1_of(tmp_path)
            existing = await self.repo.get_file_by_sha1(sha1)
            if existing is not None:
                folder = await self.repo.get_folder(existing.folder_id) if existing.folder_id is not None else None
                where = folder.name if folder else "未归类"
                raise FileExistsError(f"{existing.original_filename}（位于〈{where}〉）")
            stored_name = f"{sha1[:12]}__{_safe_filename(original)}"
            dest = self.storage_root / stored_name
            os.replace(tmp_path, dest)
            row = EiaLibraryFile(
                folder_id=folder_id,
                original_filename=original,
                stored_path=stored_name,
                content_sha1=sha1,
                size_bytes=dest.stat().st_size,
                content_type=file.content_type,
                status="stored",
                uploaded_by=uploaded_by,
            )
            try:
                await self.repo.insert_file(row)
            except IntegrityError:
                raise FileExistsError(original) from None  # 并发兜底：唯一约束再拦
            return row.to_dict()
        finally:
            tmp_path.unlink(missing_ok=True)

    async def move(self, file_id: int, folder_id: int | None) -> dict:
        if folder_id is not None and await self.repo.get_folder(folder_id) is None:
            raise ValueError(f"目标文件夹不存在: {folder_id}")
        row = await self.repo.move_file(file_id, folder_id)
        if row is None:
            raise FileNotFoundError(file_id)
        return row.to_dict()

    async def delete(self, file_id: int) -> None:
        row = await self.repo.get_file(file_id)
        if row is None:
            raise FileNotFoundError(file_id)
        await self.repo.delete_file(file_id)
        (self.storage_root / row.stored_path).unlink(missing_ok=True)

    async def download(self, file_id: int) -> tuple:
        row = await self.repo.get_file(file_id)
        if row is None:
            raise FileNotFoundError(file_id)
        path = self.storage_root / row.stored_path
        if not path.is_file():
            raise FileNotFoundError(f"磁盘文件缺失: {row.stored_path}")
        return row, path


def _safe_filename(name: str) -> str:
    """去掉路径分隔与文件系统非法字符，保留 CJK；空名与点目录名兜底。"""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", Path(name).name).strip()
    # ".." 经 Path.name 原样透出（pathlib 不视其为普通名），作为文件名属非法路径组件
    return cleaned if cleaned not in ("", ".", "..") else "unnamed"


def _sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_service: EiaLibraryService | None = None


def get_eia_library_service() -> EiaLibraryService:
    global _service
    if _service is None:
        _service = EiaLibraryService()
    return _service
