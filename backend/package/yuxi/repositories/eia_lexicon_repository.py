"""环评数值护栏词表数据访问层 - Repository"""


from sqlalchemy import select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaDatasetSwitch, EiaLexiconEntry
from yuxi.utils.datetime_utils import utc_now_naive


class EiaLexiconRepository:
    """eia_lexicon_entries / eia_dataset_switches 两表的访问边界（89 条量级，内存过滤足够）。"""

    async def list_entries(self) -> list[EiaLexiconEntry]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EiaLexiconEntry).order_by(
                    EiaLexiconEntry.category, EiaLexiconEntry.stage, EiaLexiconEntry.caliber
                )
            )
            return list(result.scalars().all())

    async def get_entry(self, entry_id: int) -> EiaLexiconEntry | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EiaLexiconEntry).where(EiaLexiconEntry.id == entry_id))
            return result.scalar_one_or_none()

    async def find_key(self, stage: str, caliber: str, unit: str) -> EiaLexiconEntry | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EiaLexiconEntry).where(
                    EiaLexiconEntry.stage == stage,
                    EiaLexiconEntry.caliber == caliber,
                    EiaLexiconEntry.unit == unit,
                )
            )
            return result.scalar_one_or_none()

    async def existing_keys(self) -> set[tuple[str, str, str]]:
        """全部 (stage, caliber, unit) 指纹——导入流幂等判重用。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EiaLexiconEntry.stage, EiaLexiconEntry.caliber, EiaLexiconEntry.unit))
            return {(r[0], r[1], r[2]) for r in result.all()}

    async def add_entries(self, entries: list[EiaLexiconEntry]) -> None:
        async with pg_manager.get_async_session_context() as session:
            session.add_all(entries)

    async def add_entry(self, entry: EiaLexiconEntry) -> None:
        async with pg_manager.get_async_session_context() as session:
            session.add(entry)

    async def save_entry(self, entry: EiaLexiconEntry) -> None:
        """持久化对（可能已脱离会话的）ORM 实例的字段修改。"""
        async with pg_manager.get_async_session_context() as session:
            await session.merge(entry)

    # ========== 数据集开关 ==========

    async def list_switches(self) -> list[EiaDatasetSwitch]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EiaDatasetSwitch))
            return list(result.scalars().all())

    async def save_switch(self, dataset_key: str, enabled: bool, updated_by: str | None) -> EiaDatasetSwitch:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EiaDatasetSwitch).where(EiaDatasetSwitch.dataset_key == dataset_key))
            switch = result.scalar_one_or_none()
            if switch is None:
                switch = EiaDatasetSwitch(dataset_key=dataset_key, enabled=enabled, updated_by=updated_by)
                session.add(switch)
            else:
                switch.enabled = enabled
                switch.updated_by = updated_by
                switch.updated_at = utc_now_naive()
        return switch
