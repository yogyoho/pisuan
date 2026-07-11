import pytest

from yuxi.repositories.agent_repository import AgentRepository
from yuxi.storage.postgres.manager import pg_manager


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await pg_manager.close()
    pg_manager._initialized = False


@pytest.mark.asyncio
async def test_ensure_chapter_writer_subagent_idempotent():
    async with pg_manager.get_async_session_context() as session:
        repo = AgentRepository(session)
        a1 = await repo.ensure_chapter_writer_subagent()
        a2 = await repo.ensure_chapter_writer_subagent()
        assert a1.slug == "chapter-writer"
        assert a1.id == a2.id  # 幂等
