"""环评 stages forms 口径字段裁决的数据访问边界（P2；DB 运营唯一真相）。

thin repository：路由/服务不绕过此处直接碰 session；行键 (stage, family_key, field_name)
唯一（uq_esfe_stage_family_field），同键重裁决走 upsert 覆盖。
"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaStageFieldEdit
from yuxi.utils.datetime_utils import utc_now_naive


class EiaStageRepository:
    """eia_stage_field_edits 表访问（薄层）。"""

    async def list_edits(self, stage: str | None = None) -> list[EiaStageFieldEdit]:
        """裁决行全量（per-stage 或全库；id 序保证导出确定性）。"""
        async with pg_manager.get_async_session_context() as session:
            stmt = select(EiaStageFieldEdit).order_by(EiaStageFieldEdit.id)
            if stage is not None:
                stmt = stmt.where(EiaStageFieldEdit.stage == stage)
            rows = (await session.scalars(stmt)).all()
            return list(rows)

    async def upsert_edit(
        self,
        stage: str,
        family_key: str,
        field_name: str,
        edit_kind: str,
        field_json: dict[str, Any],
        username: str,
    ) -> EiaStageFieldEdit:
        """同键覆盖（重裁决），时间戳随写刷新。"""
        now = utc_now_naive()
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                pg_insert(EiaStageFieldEdit)
                .values(
                    stage=stage,
                    family_key=family_key,
                    field_name=field_name,
                    edit_kind=edit_kind,
                    field_json=field_json,
                    decided_by=username,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_esfe_stage_family_field",
                    set_={
                        "edit_kind": edit_kind,
                        "field_json": field_json,
                        "decided_by": username,
                        "updated_at": now,
                    },
                )
                .returning(EiaStageFieldEdit)
            )
            row = (await session.scalars(stmt)).one()
            await session.commit()
            return row

    async def delete_edit(self, stage: str, family_key: str, field_name: str) -> bool:
        """撤回未物化裁决行；无此行返回 False。"""
        async with pg_manager.get_async_session_context() as session:
            res = await session.execute(
                delete(EiaStageFieldEdit).where(
                    EiaStageFieldEdit.stage == stage,
                    EiaStageFieldEdit.family_key == family_key,
                    EiaStageFieldEdit.field_name == field_name,
                )
            )
            await session.commit()
            return (res.rowcount or 0) > 0
