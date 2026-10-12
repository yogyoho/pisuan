"""环评 formulas 参数参考值裁决的数据访问边界（P3；DB 运营唯一真相）。

thin repository：行键 (formula_id, input_name) 唯一（uq_efo_formula_input），
同键重裁决走 upsert 覆盖。
"""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaFormulaOverride
from yuxi.utils.datetime_utils import utc_now_naive


class EiaFormulaRepository:
    """eia_formula_overrides 表访问（薄层）。"""

    async def list_overrides(self) -> list[EiaFormulaOverride]:
        """覆盖行全量（id 序保证导出确定性）。"""
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaFormulaOverride).order_by(EiaFormulaOverride.id))).all()
            return list(rows)

    async def upsert_override(
        self,
        formula_id: str,
        input_name: str,
        value: str,
        note: str | None,
        username: str,
    ) -> EiaFormulaOverride:
        """同键覆盖（重裁决），时间戳随写刷新。"""
        now = utc_now_naive()
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                pg_insert(EiaFormulaOverride)
                .values(
                    formula_id=formula_id,
                    input_name=input_name,
                    value=value,
                    note=note,
                    decided_by=username,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_efo_formula_input",
                    set_={
                        "value": value,
                        "note": note,
                        "decided_by": username,
                        "updated_at": now,
                    },
                )
                .returning(EiaFormulaOverride)
            )
            row = (await session.scalars(stmt)).one()
            await session.commit()
            return row

    async def delete_override(self, formula_id: str, input_name: str) -> bool:
        """撤回覆盖行；无此行返回 False。"""
        async with pg_manager.get_async_session_context() as session:
            res = await session.execute(
                delete(EiaFormulaOverride).where(
                    EiaFormulaOverride.formula_id == formula_id,
                    EiaFormulaOverride.input_name == input_name,
                )
            )
            await session.commit()
            return (res.rowcount or 0) > 0
