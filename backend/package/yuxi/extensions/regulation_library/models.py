"""标准规范库数据模型 - standard_indicators 表（唯一新表）"""

from __future__ import annotations

from sqlalchemy import text

from yuxi.storage.postgres.manager import pg_manager

_DDL = """
CREATE TABLE IF NOT EXISTS standard_indicators (
    id          VARCHAR(64) PRIMARY KEY,
    doc_code    VARCHAR(128) NOT NULL,
    unit_no     VARCHAR(64),
    chunk_id    VARCHAR(128),
    pollutant   VARCHAR(128),
    metric      VARCHAR(128),
    limit_value NUMERIC,
    unit        VARCHAR(32),
    condition   VARCHAR(255)
);
CREATE INDEX IF NOT EXISTS idx_std_ind_doc_code ON standard_indicators(doc_code);
CREATE INDEX IF NOT EXISTS idx_std_ind_pollutant ON standard_indicators(pollutant);
"""

_schema_ready = False


async def ensure_schema() -> None:
    """惰性建表：首次使用时执行 DDL（幂等）"""
    global _schema_ready
    if _schema_ready:
        return
    async with pg_manager.get_async_session_context() as session:
        for stmt in _DDL.strip().split(";"):
            if stmt.strip():
                await session.execute(text(stmt))
    _schema_ready = True
