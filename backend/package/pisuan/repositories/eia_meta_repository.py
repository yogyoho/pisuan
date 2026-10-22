"""环评语料元数据人工标注仓储（eia_meta_annotations，P2 运营唯一真相）。"""

from __future__ import annotations

from sqlalchemy import select

from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import EiaMetaAnnotation


class EiaMetaRepository:
    """元数据人工标注 CRUD（31 份量级全量内存操作足够）。"""

    async def list_annotations(self) -> list[EiaMetaAnnotation]:
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaMetaAnnotation))).all()
            return list(rows)

    async def get_annotation(self, report_id: str) -> EiaMetaAnnotation | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaMetaAnnotation, report_id)

    async def existing_ids(self) -> set[str]:
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaMetaAnnotation.report_id))).all()
            return set(rows)

    async def save_annotation(self, row: EiaMetaAnnotation) -> EiaMetaAnnotation:
        async with pg_manager.get_async_session_context() as session:
            await session.merge(row)
            await session.commit()
            return row
