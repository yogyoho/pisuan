"""真实 PostgreSQL v21→v22 区域事实归属迁移证据。"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from yuxi.services.domain_factory_region import attribution_scope_key
from yuxi.storage.postgres.manager import pg_manager

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _dispose_engine_after():
    yield
    await pg_manager.close()
    pg_manager.async_engine = None
    pg_manager.AsyncSession = None
    pg_manager._initialized = False


async def _prepare_v21_schema(engine, schema: str) -> None:
    statements = [
        f"CREATE SCHEMA {schema}",
        f"""
        CREATE TABLE {schema}.yuxi_schema_migrations (
            domain VARCHAR(64) PRIMARY KEY, version INTEGER NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE {schema}.domain_factory_tasks (
            id VARCHAR(64) PRIMARY KEY,
            knowledge_base_id VARCHAR(128) NOT NULL DEFAULT '',
            region_key VARCHAR(128),
            scope VARCHAR(32),
            project_name VARCHAR(255)
        )
        """,
        f"""
        CREATE TABLE {schema}.domain_factory_kb_attributions (
            kb_id VARCHAR(128) PRIMARY KEY,
            region_key VARCHAR(128), scope VARCHAR(32) NOT NULL,
            project_name VARCHAR(255), attribution VARCHAR(64) NOT NULL
        )
        """,
        f"""
        CREATE TABLE {schema}.domain_factory_regional_facts (
            id SERIAL PRIMARY KEY,
            fact_type VARCHAR(32) NOT NULL,
            region_key VARCHAR(128),
            content TEXT NOT NULL,
            source_task_id VARCHAR(64) REFERENCES {schema}.domain_factory_tasks(id) ON DELETE SET NULL,
            entity_key VARCHAR(255), status VARCHAR(32) NOT NULL DEFAULT 'draft',
            year INTEGER, source_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"INSERT INTO {schema}.yuxi_schema_migrations (domain, version) VALUES ('business', 21)",
        f"""
        INSERT INTO {schema}.domain_factory_tasks (id, knowledge_base_id, region_key, scope)
        VALUES ('t_bound', 'kb_bound', 'hengcheng', 'regional'),
               ('t_conflict', 'kb_conflict', 'other-region', 'regional')
        """,
        f"""
        INSERT INTO {schema}.domain_factory_kb_attributions
            (kb_id, region_key, scope, project_name, attribution)
        VALUES
            ('kb_bound', 'hengcheng', 'regional', NULL, 'attr_bound'),
            ('kb_conflict', 'hengcheng', 'regional', NULL, 'attr_conflict_binding')
        """,
        f"""
        INSERT INTO {schema}.domain_factory_regional_facts
            (fact_type, region_key, content, source_task_id, status)
        VALUES
            ('monitoring', 'hengcheng', '可证明归属', 't_bound', 'confirmed'),
            ('measure', 'other-region', '任务与绑定冲突', 't_conflict', 'confirmed'),
            ('constraint', 'hengcheng', '来源丢失', NULL, 'confirmed')
        """,
    ]
    async with engine.connect() as conn:
        for statement in statements:
            await conn.execute(text(statement))
        await conn.commit()


async def test_v21_to_v22_binds_provable_facts_and_retires_unprovable_facts():
    """v22 迁移只保留可证明归属的 confirmed 事实；冲突/来源丢失必须 fail-closed。"""
    schema = f"migration_v22_{uuid.uuid4().hex[:10]}"
    db_url = os.environ["POSTGRES_URL"]
    pg_manager.initialize()
    original_engine = pg_manager.async_engine
    assert original_engine is not None
    async with original_engine.connect() as conn:
        await _prepare_v21_schema(original_engine, schema)

    isolated_engine = create_async_engine(
        db_url, connect_args={"server_settings": {"search_path": schema}}
    )
    pg_manager.async_engine = isolated_engine
    expected = attribution_scope_key("kb_bound", "hengcheng", "regional", None)
    try:
        await pg_manager.upgrade_business_v21_to_v22()
        async with isolated_engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT version FROM pisuan_schema_migrations WHERE domain = 'business'")
            ) == 22
            proven = (
                await conn.execute(
                    text(
                        "SELECT kb_id, attribution, status FROM domain_factory_regional_facts "
                        "WHERE content = '可证明归属'"
                    )
                )
            ).one()
            assert proven.kb_id == "kb_bound"
            assert proven.attribution == expected
            assert proven.status == "confirmed"
            assert (
                await conn.scalar(
                    text("SELECT status FROM domain_factory_regional_facts WHERE content = '任务与绑定冲突'")
                )
            ) == "retired"
            assert (
                await conn.scalar(
                    text("SELECT status FROM domain_factory_regional_facts WHERE content = '来源丢失'")
                )
            ) == "retired"
            assert await conn.scalar(
                text("SELECT count(*) FROM domain_factory_regional_facts WHERE kb_id <> '' AND attribution = ''")
            ) == 0

        await pg_manager.upgrade_business_v21_to_v22()
        async with isolated_engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT version FROM pisuan_schema_migrations WHERE domain = 'business'")
            ) == 22
    finally:
        pg_manager.async_engine = original_engine
        await isolated_engine.dispose()
        async with original_engine.connect() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            await conn.commit()
