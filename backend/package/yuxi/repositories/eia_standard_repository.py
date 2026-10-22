"""环评标准条目人工核实裁决仓储（eia_standard_reviews，P3 运营唯一真相）。"""

from __future__ import annotations

from sqlalchemy import select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import (
    EiaLimitTableRegistry,
    EiaStandardLimitRow,
    EiaStandardReview,
)


class EiaStandardRepository:
    """标准核实裁决 CRUD（62 条量级全量内存操作足够）。"""

    async def list_reviews(self) -> list[EiaStandardReview]:
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaStandardReview))).all()
            return list(rows)

    async def get_review(self, code: str) -> EiaStandardReview | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaStandardReview, code)

    async def save_review(self, row: EiaStandardReview) -> EiaStandardReview:
        async with pg_manager.get_async_session_context() as session:
            await session.merge(row)
            await session.commit()
            return row

    # ── 限值查找表（P1 合流后仅存读取面：export_limit_rows 物化导出的行源）──

    async def list_rows(self) -> list[EiaStandardLimitRow]:
        """全量录入行（7 表 × 数十行量级，全量内存足够；id 序保证导出确定性）。"""
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaStandardLimitRow).order_by(EiaStandardLimitRow.id))).all()
            return list(rows)

    async def list_registry(self) -> list[EiaLimitTableRegistry]:
        """新表注册元数据（spec 2026-10-19 候选立表通道；list_limit_tables 合并露出）。"""
        async with pg_manager.get_async_session_context() as session:
            return list((await session.scalars(select(EiaLimitTableRegistry))).all())
