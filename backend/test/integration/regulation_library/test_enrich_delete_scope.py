"""enrich 删旧插新不得波及专家行（P1 合流 Task 5；集成测试直连运行栈 PG）。

enrich_regulation_file 全函数依赖文档与 LLM，不可直跑；DELETE 语句提为模块常量后
以常量真源验证语义：enrich 行被清、expert 行幸存。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text as sql_text

from yuxi.extensions.regulation_library.enrichment_service import ENRICH_DELETE_SQL
from yuxi.storage.postgres.manager import pg_manager


def _run(coro) -> None:
    """在同一事件循环内跑完协程并显式关停 pg_manager。

    initialize() 会在当前 loop 拉起 psycopg 后台池 worker/scheduler 任务，
    它们不随 asyncio.run 的取消收尾退出，必须在 loop 存续期内走池自身的
    graceful close，否则 asyncio.run 永久挂死。
    """

    async def wrapper():
        try:
            await coro
        finally:
            await pg_manager.close()

    asyncio.run(wrapper())


async def _seed():
    async with pg_manager.get_async_session_context() as s:
        await s.execute(
            sql_text(
                "INSERT INTO standard_indicators (id, doc_code, pollutant, metric, limit_value, unit,"
                " condition, category, period, source, table_key, page_row_id)"
                " VALUES ('t5-expert', 'T5-DOC', 'p', '', 1, '', '', '', '', 'expert',"
                " 'gb3838_category_limits', 'pr1'),"
                " ('t5-enrich', 'T5-DOC', 'p', '', 2, '', '', '', '', 'enrich', NULL, NULL)"
            )
        )


async def _cleanup():
    async with pg_manager.get_async_session_context() as s:
        await s.execute(sql_text("DELETE FROM standard_indicators WHERE id IN ('t5-expert','t5-enrich')"))


def test_enrich_delete_spares_expert_rows():
    _run(_seed())
    try:

        async def main():
            async with pg_manager.get_async_session_context() as s:
                await s.execute(sql_text(ENRICH_DELETE_SQL), {"code": "T5-DOC"})
                rows = (
                    await s.execute(sql_text("SELECT id, source FROM standard_indicators WHERE doc_code='T5-DOC'"))
                ).all()
                assert rows == [("t5-expert", "expert")]

        _run(main())
    finally:
        _run(_cleanup())
