from __future__ import annotations

import sys
from pathlib import Path

import pytest

from yuxi.storage.postgres.manager import pg_manager

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
async def _dispose_pg_pools():
    """psycopg 连接池的后台建连任务必须在其所属循环内显式关闭。

    pytest-asyncio 每用例新建事件循环；循环拆卸时 `_scoped_runner.close()`
    的 `_cancel_all_tasks` 对仍在重试建连的池 worker 取消无效，`gather`
    会永久挂起（unit 与 integration 段都触发过）。在夹具拆卸阶段（循环
    仍存活）关闭池即可规避。清理是尽力而为的：close 的超时/取消竞态
    （CancelledError 属 BaseException，除 Exception 外须一并吞掉）不应
    让拆卸阶段报 error。
    """
    yield
    pool = pg_manager.langgraph_pool
    if pool is not None:
        try:
            await pool.close(timeout=2)
        except BaseException:
            pass


def pytest_configure(config: pytest.Config) -> None:
    """Register shared markers without binding every test to a live environment."""
    config.addinivalue_line("markers", "unit: marks tests that run without live services")
    config.addinivalue_line("markers", "auth: marks tests that require authentication")
    config.addinivalue_line("markers", "integration: marks tests that hit the live API service")
    config.addinivalue_line("markers", "e2e: marks tests that exercise an end-to-end workflow")
    config.addinivalue_line("markers", "slow: marks tests as slow")


pytest_plugins = ["pytest_asyncio"]
