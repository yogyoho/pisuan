"""归属隔离集成测试：真实 PostgreSQL 校验一库一归属与模板/大纲唯一身份。"""

import uuid

import pytest
from sqlalchemy import delete, select

from pisuan.repositories.domain_factory_repository import DomainFactoryRepository
from pisuan.services.domain_factory_region import attribution_scope_key
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryKnowledgeBaseAttribution,
    DomainFactoryLearnedTemplate,
    DomainFactoryOutline,
    DomainFactoryTask,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _dispose_engine_after():
    yield
    await pg_manager.close()
    pg_manager.async_engine = None
    pg_manager.AsyncSession = None
    pg_manager._initialized = False


async def _create_task(
    task_id: str,
    kb_id: str | None,
    *,
    region_key: str,
    scope: str = "regional",
    project_name: str | None = None,
) -> None:
    async with pg_manager.get_async_session_context() as session:
        domain_id = await session.scalar(select(DomainFactoryDomain.id).limit(1))
        if domain_id is None:
            domain = DomainFactoryDomain(code="attribution_test", name="归属测试")
            session.add(domain)
            await session.flush()
            domain_id = domain.id
        session.add(
            DomainFactoryTask(
                id=task_id,
                domain_id=domain_id,
                file_name="attribution.docx",
                storage_path="/tmp/attribution.docx",
                status="WAITING_REVIEW",
                knowledge_base_id=kb_id,
                region_key=region_key,
                scope=scope,
                project_name=project_name,
            )
        )
        await session.commit()


async def _cleanup(task_ids: list[str], *, domain: str, report_type: str, chapter: str) -> None:
    async with pg_manager.get_async_session_context() as session:
        await session.execute(delete(DomainFactoryTask).where(DomainFactoryTask.id.in_(task_ids)))
        await session.execute(
            delete(DomainFactoryOutline).where(
                DomainFactoryOutline.domain_code == domain,
                DomainFactoryOutline.report_type_code == report_type,
                DomainFactoryOutline.canonical_chapter_key == chapter,
            )
        )
        await session.execute(
            delete(DomainFactoryLearnedTemplate).where(
                DomainFactoryLearnedTemplate.domain_code == domain,
                DomainFactoryLearnedTemplate.report_type_code == report_type,
                DomainFactoryLearnedTemplate.chapter == chapter,
            )
        )
        await session.commit()


async def test_same_kb_rejects_second_attribution():
    """同一知识库已绑定归属后，第二归属必须 fail-closed，不能写入同一向量集合。"""
    suffix = uuid.uuid4().hex[:10]
    kb_id = f"kb_attr_conflict_{suffix}"
    task_a = f"task_attr_a_{suffix}"
    task_b = f"task_attr_b_{suffix}"
    domain = f"attr_domain_{suffix}"
    chapter = f"章节_{suffix}"
    await _create_task(task_a, kb_id, region_key="hengcheng")
    await _create_task(task_b, None, region_key="other_region")
    repo = DomainFactoryRepository()
    try:
        await repo.begin_ingest(task_a, knowledge_base_id=kb_id)
        with pytest.raises(ValueError, match="其他归属占用"):
            await repo.begin_ingest(task_b, knowledge_base_id=kb_id)
        with pytest.raises(ValueError, match="其他归属占用"):
            await repo.assert_kb_attribution_compatible(
                kb_id,
                task_id=task_b,
                region_key="other_region",
                scope="regional",
                project_name=None,
            )
        async with pg_manager.get_async_session_context() as session:
            rows = (
                await session.execute(
                    select(DomainFactoryTask.id, DomainFactoryTask.status, DomainFactoryTask.knowledge_base_id)
                    .where(DomainFactoryTask.id.in_([task_a, task_b]))
                )
            ).all()
        by_id = {row.id: row for row in rows}
        assert by_id[task_a].status == "INGESTING"
        assert by_id[task_a].knowledge_base_id == kb_id
        assert by_id[task_b].status == "WAITING_REVIEW"
        assert by_id[task_b].knowledge_base_id is None
        await repo.delete_task(task_a)
        info = await repo.get_kb_attribution(kb_id)
        assert info["bound"] is True
        assert info["mixed"] is False
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(DomainFactoryKnowledgeBaseAttribution).where(
                    DomainFactoryKnowledgeBaseAttribution.kb_id == kb_id
                )
            )
            await session.commit()
        await _cleanup([task_a, task_b], domain=domain, report_type="eia_report", chapter=chapter)


async def test_outline_and_learned_template_unique_identity_include_attribution():
    """同 domain/report/chapter 在不同归属下必须并存，按归属读取互不覆盖。"""
    suffix = uuid.uuid4().hex[:10]
    domain = f"attr_domain_{suffix}"
    report_type = "eia_report"
    chapter = f"章节_{suffix}"
    kb_a = f"kb_attr_a_{suffix}"
    kb_b = f"kb_attr_b_{suffix}"
    attr_a = attribution_scope_key(kb_a, "hengcheng", "regional", None)
    attr_b = attribution_scope_key(kb_b, "other_region", "regional", None)
    repo = DomainFactoryRepository()
    try:
        await repo.upsert_outline(
            domain_code=domain,
            report_type_code=report_type,
            canonical_chapter_key=chapter,
            purpose="甲区域目的",
            source_task_ids=["t-a"],
            attribution=attr_a,
        )
        await repo.upsert_outline(
            domain_code=domain,
            report_type_code=report_type,
            canonical_chapter_key=chapter,
            purpose="乙区域目的",
            source_task_ids=["t-b"],
            attribution=attr_b,
        )
        got_a = await repo.get_outline(domain, report_type, chapter, attribution=attr_a)
        got_b = await repo.get_outline(domain, report_type, chapter, attribution=attr_b)
        assert got_a["purpose"] == "甲区域目的"
        assert got_b["purpose"] == "乙区域目的"

        template_a = await repo.upsert_learned_template(
            domain_code=domain,
            chapter=chapter,
            generalized="甲区域模板",
            slots=[],
            slot_signature="",
            report_type_code=report_type,
            attribution=attr_a,
        )
        template_b = await repo.upsert_learned_template(
            domain_code=domain,
            chapter=chapter,
            generalized="乙区域模板",
            slots=[],
            slot_signature="",
            report_type_code=report_type,
            attribution=attr_b,
        )
        assert template_a != template_b
        rows_a = await repo.list_learned_templates_by_key(domain, report_type, attribution=attr_a)
        rows_b = await repo.list_learned_templates_by_key(domain, report_type, attribution=attr_b)
        assert [row["generalized"] for row in rows_a] == ["甲区域模板"]
        assert [row["generalized"] for row in rows_b] == ["乙区域模板"]
    finally:
        await _cleanup([], domain=domain, report_type=report_type, chapter=chapter)


async def test_kb_attribution_diagnostics_classifies_bound_mixed_and_retained():
    """绑定诊断必须区分正常绑定、任务冲突和任务删除后的保留绑定。"""
    suffix = uuid.uuid4().hex[:10]
    kb_bound = f"kb_diag_bound_{suffix}"
    kb_mixed = f"kb_diag_mixed_{suffix}"
    kb_retained = f"kb_diag_retained_{suffix}"
    task_ids = [
        f"task_diag_bound_{suffix}",
        f"task_diag_mixed_a_{suffix}",
        f"task_diag_mixed_b_{suffix}",
    ]
    bindings = []
    async with pg_manager.get_async_session_context() as session:
        domain_id = await session.scalar(select(DomainFactoryDomain.id).limit(1))
        if domain_id is None:
            domain = DomainFactoryDomain(code="attribution_diag_test", name="归属诊断测试")
            session.add(domain)
            await session.flush()
            domain_id = domain.id
        bindings = [
            DomainFactoryKnowledgeBaseAttribution(
                kb_id=kb_id,
                region_key="hengcheng",
                scope="regional",
                project_name=None,
                attribution=attribution_scope_key(kb_id, "hengcheng", "regional", None),
            )
            for kb_id in (kb_bound, kb_mixed, kb_retained)
        ]
        session.add_all(bindings)
        await session.commit()
    await _create_task(task_ids[0], kb_bound, region_key="hengcheng")
    await _create_task(task_ids[1], kb_mixed, region_key="hengcheng")
    await _create_task(task_ids[2], kb_mixed, region_key="other_region")

    repo = DomainFactoryRepository()
    try:
        items, _total = await repo.list_kb_attributions(page=1, page_size=100)
        by_kb = {item["kb_id"]: item for item in items}
        assert by_kb[kb_bound]["status"] == "bound"
        assert by_kb[kb_bound]["task_count"] == 1
        assert by_kb[kb_mixed]["status"] == "mixed"
        assert by_kb[kb_mixed]["task_count"] == 2
        assert by_kb[kb_retained]["status"] == "retained"
        assert by_kb[kb_retained]["task_count"] == 0
        assert "阻止知识库复用" in by_kb[kb_retained]["status_reason"]

        items, _total = await repo.list_kb_attributions(status="mixed", page=1, page_size=100)
        assert {item["kb_id"] for item in items} == {kb_mixed}
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(DomainFactoryKnowledgeBaseAttribution).where(
                    DomainFactoryKnowledgeBaseAttribution.kb_id.in_([kb_bound, kb_mixed, kb_retained])
                )
            )
            await session.commit()
        await _cleanup(task_ids, domain=f"attr_domain_{suffix}", report_type="eia_report", chapter="unused")
