"""写作范式层草稿的数据访问边界（每资产 (asset_kind, asset_id) 至多一份活跃草稿）。

thin repository：同键保存走 upsert 覆盖；撤回即删行（文件锚点不受影响）。
"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import EiaParadigmDraft
from pisuan.utils.datetime_utils import utc_now_naive


class EiaParadigmRepository:
    """eia_paradigm_drafts 表访问（薄层）。"""

    async def list_drafts(self) -> list[EiaParadigmDraft]:
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaParadigmDraft).order_by(EiaParadigmDraft.id))).all()
            return list(rows)

    async def upsert_draft(
        self, asset_kind: str, asset_id: str, content: dict[str, Any], base_hash: str, username: str
    ) -> EiaParadigmDraft:
        now = utc_now_naive()
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                pg_insert(EiaParadigmDraft)
                .values(
                    asset_kind=asset_kind,
                    asset_id=asset_id,
                    content=content,
                    base_hash=base_hash,
                    created_by=username,
                    updated_by=username,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_epd_kind_asset",
                    set_={
                        "content": content,
                        "base_hash": base_hash,
                        "updated_by": username,
                        "updated_at": now,
                    },
                )
                .returning(EiaParadigmDraft)
            )
            row = (await session.scalars(stmt)).one()
            await session.commit()
            return row

    async def delete_draft(self, asset_kind: str, asset_id: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            res = await session.execute(
                delete(EiaParadigmDraft).where(
                    EiaParadigmDraft.asset_kind == asset_kind, EiaParadigmDraft.asset_id == asset_id
                )
            )
            await session.commit()
            return (res.rowcount or 0) > 0
