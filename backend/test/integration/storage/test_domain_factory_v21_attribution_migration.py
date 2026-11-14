"""真实 PostgreSQL v20→v21 归属迁移升级证据。"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pisuan.services.domain_factory_region import attribution_scope_key
from pisuan.storage.postgres.manager import pg_manager

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _create_v20_tables(schema: str) -> list[str]:
    return [
        f"""
        CREATE TABLE {schema}.pisuan_schema_migrations (
            domain VARCHAR(64) PRIMARY KEY,
            version INTEGER NOT NULL,
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
        CREATE TABLE {schema}.domain_factory_learned_templates (
            id SERIAL PRIMARY KEY,
            domain_code VARCHAR(64) NOT NULL,
            report_type_code VARCHAR(64) NOT NULL DEFAULT '通用',
            chapter VARCHAR(255) NOT NULL DEFAULT '',
            slot_signature TEXT NOT NULL DEFAULT '',
            CONSTRAINT uq_dflt_domain_chapter_sig
                UNIQUE (domain_code, chapter, slot_signature)
        )
        """,
        f"""
        CREATE TABLE {schema}.domain_factory_outlines (
            id SERIAL PRIMARY KEY,
            domain_code VARCHAR(64) NOT NULL,
            report_type_code VARCHAR(64) NOT NULL DEFAULT '通用',
            canonical_chapter_key TEXT NOT NULL,
            CONSTRAINT uq_dfo_domain_rt_key
                UNIQUE (domain_code, report_type_code, canonical_chapter_key)
        )
        """,
        f"INSERT INTO {schema}.pisuan_schema_migrations (domain, version) VALUES ('business', 20)",
        f"""
        INSERT INTO {schema}.domain_factory_tasks (id, knowledge_base_id, region_key, scope)
        VALUES ('task_v20_single', 'kb_v20_bound', 'hengcheng', 'regional'),
               ('task_v20_mixed_a', 'kb_v20_mixed', 'region-a', 'regional'),
               ('task_v20_mixed_b', 'kb_v20_mixed', 'region-b', 'regional')
        """,
        f"""
        INSERT INTO {schema}.domain_factory_learned_templates (domain_code, chapter, slot_signature)
        VALUES ('general', '旧章节', '')
        """,
        f"""
        INSERT INTO {schema}.domain_factory_outlines (domain_code, report_type_code, canonical_chapter_key)
        VALUES ('general', 'eia_report', '旧章节')
        """,
    ]


async def test_v20_to_v21_upgrades_and_persists_unique_kb_binding():
    """v20 存量库升级后旧唯一键删除、跨归属并存、绑定持久化且幂等。"""
    schema = f"migration_v21_{uuid.uuid4().hex[:10]}"
    db_url = os.environ["POSTGRES_URL"]
    pg_manager.initialize()
    original_engine = pg_manager.async_engine
    assert original_engine is not None
    async with original_engine.connect() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        for statement in _create_v20_tables(schema):
            await conn.execute(text(statement))
        await conn.commit()

    isolated_engine = create_async_engine(
        db_url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    pg_manager.async_engine = isolated_engine
    try:
        await pg_manager.upgrade_business_v20_to_v21()

        async with isolated_engine.connect() as conn:
            version = await conn.scalar(
                text("SELECT version FROM pisuan_schema_migrations WHERE domain = 'business'")
            )
            assert version == 21
            assert await conn.scalar(
                text("SELECT attribution FROM domain_factory_learned_templates WHERE chapter = '旧章节'")
            ) == ""
            assert await conn.scalar(
                text("SELECT attribution FROM domain_factory_outlines WHERE canonical_chapter_key = '旧章节'")
            ) == ""
            old_constraints = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE conname IN "
                    "('uq_dflt_domain_chapter_sig', 'uq_dfo_domain_rt_key') "
                    "AND conrelid IN (CAST(:learned_table AS regclass), CAST(:outline_table AS regclass))"
                ),
                {
                    "learned_table": f"{schema}.domain_factory_learned_templates",
                    "outline_table": f"{schema}.domain_factory_outlines",
                },
            )
            assert old_constraints == 0
            assert await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE schemaname = :schema "
                    "AND indexname = 'uq_dflt_domain_rt_chapter_sig_attr'"
                ),
                {"schema": schema},
            ) == 1
            assert await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE schemaname = :schema "
                    "AND indexname = 'uq_dfo_domain_rt_key_attr'"
                ),
                {"schema": schema},
            ) == 1
            binding = (
                await conn.execute(
                text(
                    "SELECT region_key, scope, project_name, attribution "
                    "FROM domain_factory_kb_attributions WHERE kb_id = 'kb_v20_bound'"
                )
                )
            ).one()
            assert binding.region_key == "hengcheng"
            assert binding.scope == "regional"
            assert binding.project_name is None
            assert binding.attribution == attribution_scope_key(
                "kb_v20_bound", "hengcheng", "regional", None
            )
            assert await conn.scalar(
                text("SELECT count(*) FROM domain_factory_kb_attributions WHERE kb_id = 'kb_v20_mixed'")
            ) == 0

            await conn.execute(
                text(
                    "INSERT INTO domain_factory_learned_templates "
                    "(domain_code, report_type_code, chapter, slot_signature, attribution) "
                    "VALUES ('general', 'eia_report', '旧章节', '', 'attr_a'), "
                    "('general', 'eia_report', '旧章节', '', 'attr_b')"
                )
            )
            assert await conn.scalar(
                text("SELECT count(*) FROM domain_factory_learned_templates WHERE chapter = '旧章节'")
            ) == 3

        await pg_manager.upgrade_business_v20_to_v21()
        async with isolated_engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT version FROM pisuan_schema_migrations WHERE domain = 'business'")
            ) == 21
    finally:
        pg_manager.async_engine = original_engine
        await isolated_engine.dispose()
        async with original_engine.connect() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            await conn.commit()
