"""环评标准条目人工核实裁决仓储（eia_standard_reviews，P3 运营唯一真相）。"""

from __future__ import annotations

from sqlalchemy import select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaStandardReview


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
