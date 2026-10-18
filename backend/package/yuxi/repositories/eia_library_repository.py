"""环评文件库仓储（eia_library_folders / eia_library_files，P1 进料区）。"""

from __future__ import annotations

from sqlalchemy import func, select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaLibraryFile, EiaLibraryFolder


class EiaLibraryRepository:
    """文件库 CRUD（百份量级全量内存操作足够）。"""

    async def list_folders(self) -> list[dict]:
        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(EiaLibraryFolder, func.count(EiaLibraryFile.id))
                .outerjoin(EiaLibraryFile, EiaLibraryFile.folder_id == EiaLibraryFolder.id)
                .group_by(EiaLibraryFolder.id)
                .order_by(EiaLibraryFolder.sort)
            )
            return [{**folder.to_dict(), "file_count": count} for folder, count in rows.all()]

    async def get_folder(self, folder_id: int) -> EiaLibraryFolder | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLibraryFolder, folder_id)

    async def list_files(
        self, *, folder_id: int | None = None, q: str | None = None, uncategorized: bool = False
    ) -> list[dict]:
        """folder_id 定向；uncategorized=未归类（folder_id IS NULL）；q 文件名模糊。"""
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                select(EiaLibraryFile, EiaLibraryFolder.name)
                .outerjoin(EiaLibraryFolder, EiaLibraryFile.folder_id == EiaLibraryFolder.id)
                .order_by(EiaLibraryFile.created_at.desc(), EiaLibraryFile.id.desc())
            )
            if folder_id is not None:
                stmt = stmt.where(EiaLibraryFile.folder_id == folder_id)
            elif uncategorized:
                stmt = stmt.where(EiaLibraryFile.folder_id.is_(None))
            if q:
                stmt = stmt.where(EiaLibraryFile.original_filename.ilike(f"%{q}%"))
            rows = (await session.execute(stmt)).all()
            return [{**row.to_dict(), "folder_name": name} for row, name in rows]

    async def count_files(self) -> int:
        async with pg_manager.get_async_session_context() as session:
            return await session.scalar(select(func.count(EiaLibraryFile.id)))

    async def get_file(self, file_id: int) -> EiaLibraryFile | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLibraryFile, file_id)

    async def get_file_by_sha1(self, sha1: str) -> EiaLibraryFile | None:
        async with pg_manager.get_async_session_context() as session:
            scalar = await session.scalars(select(EiaLibraryFile).where(EiaLibraryFile.content_sha1 == sha1))
            return scalar.first()

    async def insert_file(self, row: EiaLibraryFile) -> EiaLibraryFile:
        async with pg_manager.get_async_session_context() as session:
            session.add(row)
            await session.commit()
            return row

    async def update_file(self, file_id: int, fields: dict) -> EiaLibraryFile | None:
        """白名单字段增量更新（md/kb/加工/rid 元数据，P2）。"""
        allowed = {
            "object_key",
            "md_object_key",
            "md_status",
            "md_chars",
            "md_sha1",
            "md_failed_reason",
            "front_meta",
            "report_id",
            "stage",
            "mineral",
            "kb_id",
            "kb_file_id",
            "kb_status",
            "pushed_at",
            "push_error",
            "processed_at",
        }
        fields = {k: v for k, v in fields.items() if k in allowed}
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(EiaLibraryFile, file_id)
            if row is None:
                return None
            for k, v in fields.items():
                setattr(row, k, v)
            await session.commit()
            return row

    async def move_file(self, file_id: int, folder_id: int | None) -> EiaLibraryFile | None:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(EiaLibraryFile, file_id)
            if row is None:
                return None
            row.folder_id = folder_id
            await session.commit()
            return row

    async def delete_file(self, file_id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(EiaLibraryFile, file_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True
