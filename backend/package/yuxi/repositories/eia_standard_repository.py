"""环评标准条目人工核实裁决仓储（eia_standard_reviews，P3 运营唯一真相）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaStandardLimitRow, EiaStandardReview
from yuxi.utils.datetime_utils import utc_now_naive


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

    # ── 限值查找表录入行（P1）─────────────────────────────

    async def list_rows(self) -> list[EiaStandardLimitRow]:
        """全量录入行（7 表 × 数十行量级，全量内存足够；id 序保证导出确定性）。"""
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaStandardLimitRow).order_by(EiaStandardLimitRow.id))).all()
            return list(rows)

    async def replace_rows(self, table_key: str, rows: list[dict[str, Any]], username: str) -> int:
        """整表替换录入行（先删后插单事务；DB 即导出真源）。"""
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EiaStandardLimitRow).where(EiaStandardLimitRow.table_key == table_key))
            now = utc_now_naive()
            for r in rows:
                session.add(
                    EiaStandardLimitRow(
                        table_key=table_key, row_json=r, decided_by=username, created_at=now, updated_at=now
                    )
                )
            await session.commit()
            return len(rows)
