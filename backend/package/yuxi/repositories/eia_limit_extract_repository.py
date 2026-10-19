"""语料限值提取暂存仓储（eia_limit_extract_rows + eia_limit_table_registry，spec 2026-10-19）。"""

from __future__ import annotations

from sqlalchemy import select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaLimitExtractRow, EiaLimitTableRegistry


class EiaLimitExtractRepository:
    async def list_rows(
        self, table_key: str | None = None, status: str | None = None, confidence: str | None = None
    ) -> list[EiaLimitExtractRow]:
        stmt = select(EiaLimitExtractRow).order_by(EiaLimitExtractRow.id)
        if table_key:
            stmt = stmt.where(EiaLimitExtractRow.table_key == table_key)
        if status:
            stmt = stmt.where(EiaLimitExtractRow.status == status)
        if confidence:
            stmt = stmt.where(EiaLimitExtractRow.confidence == confidence)
        async with pg_manager.get_async_session_context() as session:
            return list((await session.scalars(stmt)).all())

    async def add_rows(self, rows: list[EiaLimitExtractRow]) -> int:
        async with pg_manager.get_async_session_context() as session:
            session.add_all(rows)
            await session.commit()
            return len(rows)

    async def get_row(self, row_id: int) -> EiaLimitExtractRow | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLimitExtractRow, row_id)

    async def save_row(self, row: EiaLimitExtractRow) -> EiaLimitExtractRow:
        async with pg_manager.get_async_session_context() as session:
            await session.merge(row)
            await session.commit()
            return row

    async def list_registry(self) -> list[EiaLimitTableRegistry]:
        async with pg_manager.get_async_session_context() as session:
            return list((await session.scalars(select(EiaLimitTableRegistry))).all())

    async def get_registry(self, table_key: str) -> EiaLimitTableRegistry | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLimitTableRegistry, table_key)

    async def save_registry(self, row: EiaLimitTableRegistry) -> EiaLimitTableRegistry:
        async with pg_manager.get_async_session_context() as session:
            await session.merge(row)
            await session.commit()
            return row
