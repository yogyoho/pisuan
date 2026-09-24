"""unit 测试共享夹具：在事件循环销毁前释放绑定该循环的异步资源。"""
from __future__ import annotations

import pytest

from yuxi.storage.postgres.manager import pg_manager


@pytest.fixture(autouse=True)
async def _dispose_pg_pools():
    """psycopg 连接池的后台建连任务必须在其所属循环内显式关闭。

    pytest-asyncio 每用例新建事件循环；循环拆卸时 `_cancel_all_tasks`
    对仍在重试建连的池任务取消无效，`gather` 会永久挂起。
    在夹具拆卸阶段（循环仍存活）关闭池即可规避。
    """
    yield
    pool = pg_manager.langgraph_pool
    if pool is not None:
        try:
            await pool.close(timeout=2)
        except Exception:
            pass
