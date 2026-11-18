"""标准规范库数据模型 - standard_indicators 表（唯一新表）"""

from __future__ import annotations

from sqlalchemy import text

from pisuan.storage.postgres.manager import pg_manager

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
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS category VARCHAR(64);
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS period VARCHAR(64);
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS verified_by TEXT;
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'enrich';
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS doc_name TEXT;
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS table_key VARCHAR(64);
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS page_row_id VARCHAR(32);
CREATE INDEX IF NOT EXISTS ix_si_table_key ON standard_indicators (table_key);
CREATE TABLE IF NOT EXISTS regulation_enrich_runs (
    id            BIGSERIAL PRIMARY KEY,
    run_id        VARCHAR(32) NOT NULL UNIQUE,
    kb_id         VARCHAR(80) NOT NULL,
    file_id       VARCHAR(64) NOT NULL,
    doc_code      VARCHAR(128) NOT NULL,
    doc_name      TEXT,
    doc_type      VARCHAR(64) NOT NULL DEFAULT 'technical_standard',
    status        VARCHAR(32) NOT NULL,
    started_by    TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    error_message TEXT,
    result        JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rer_file_started ON regulation_enrich_runs(file_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_rer_kb_status ON regulation_enrich_runs(kb_id, status);
CREATE TABLE IF NOT EXISTS eia_taxonomy_rows (
    id          VARCHAR(64) PRIMARY KEY,
    doc_code    VARCHAR(128) NOT NULL,
    unit_no     VARCHAR(64),
    chunk_id    VARCHAR(128),
    code        VARCHAR(64) NOT NULL,
    name        VARCHAR(128),
    meaning     TEXT,
    parent_code VARCHAR(64),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_tax_doc_code UNIQUE (doc_code, code)
);
CREATE INDEX IF NOT EXISTS ix_tax_doc_code ON eia_taxonomy_rows(doc_code);
CREATE INDEX IF NOT EXISTS ix_tax_name ON eia_taxonomy_rows(name);
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
