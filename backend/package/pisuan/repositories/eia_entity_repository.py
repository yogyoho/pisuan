"""环评 sample_entities 实体补充的数据访问边界（P3；DB 运营唯一真相，仅添加）。

thin repository：行键 (sample_slug, etype, name) 唯一（uq_eea_slug_etype_name）；
禁删既有条目指文件锚点——DB 待导出行仍可撤回（delete_addition）。
"""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import EiaEntityAddition
from pisuan.utils.datetime_utils import utc_now_naive


class EiaEntityRepository:
    """eia_entity_additions 表访问（薄层）。"""

    async def list_additions(self, sample_slug: str | None = None) -> list[EiaEntityAddition]:
        """补充行全量（per-slug 或全库；id 序保证导出确定性）。"""
        async with pg_manager.get_async_session_context() as session:
            stmt = select(EiaEntityAddition).order_by(EiaEntityAddition.id)
            if sample_slug is not None:
                stmt = stmt.where(EiaEntityAddition.sample_slug == sample_slug)
            rows = (await session.scalars(stmt)).all()
            return list(rows)

    async def insert_addition(
        self,
        sample_slug: str,
        etype: str,
        name: str,
        rid: str | None,
        note: str | None,
        username: str,
    ) -> EiaEntityAddition:
        """仅添加语义：同键冲突由唯一约束拒绝（服务层先行校验锚点/待导出重复）。"""
        now = utc_now_naive()
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                pg_insert(EiaEntityAddition)
                .values(
                    sample_slug=sample_slug,
                    etype=etype,
                    name=name,
                    rid=rid,
                    note=note,
                    decided_by=username,
                    created_at=now,
                    updated_at=now,
                )
                .returning(EiaEntityAddition)
            )
            row = (await session.scalars(stmt)).one()
            await session.commit()
            return row

    async def delete_addition(self, addition_id: int) -> bool:
        """撤回 DB 补充行（文件锚点不受影响）；无此行返回 False。"""
        async with pg_manager.get_async_session_context() as session:
            res = await session.execute(delete(EiaEntityAddition).where(EiaEntityAddition.id == addition_id))
            await session.commit()
            return (res.rowcount or 0) > 0
