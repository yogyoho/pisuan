import pytest

from pisuan.agents.presets.subagents.chapter_writer import PRESET as CHAPTER_WRITER_PRESET
from pisuan.repositories.agent_repository import AgentRepository
from pisuan.storage.postgres.manager import pg_manager


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await pg_manager.close()
    pg_manager._initialized = False


@pytest.mark.asyncio
async def test_ensure_chapter_writer_subagent_idempotent():
    async with pg_manager.get_async_session_context() as session:
        repo = AgentRepository(session)
        a1 = await repo.ensure_preset(CHAPTER_WRITER_PRESET)
        a2 = await repo.ensure_preset(CHAPTER_WRITER_PRESET)
        assert a1.slug == "chapter-writer"
        assert a1.id == a2.id  # 幂等
