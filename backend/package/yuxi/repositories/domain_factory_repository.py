"""Domain Factory 数据访问层 - Repository"""

from typing import Any

from sqlalchemy import func, select, text

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryTask,
    DomainFactoryLearnedTemplate,
    DomainFactoryOutline,
    DomainFactoryPromptConfig,
)
from yuxi.utils.datetime_utils import utc_now_naive


class DomainFactoryRepository:
    """领域知识工厂数据访问层"""

    # ========== Domain ==========

    async def count_committed_tasks(self, domain_code: str) -> int:
        """统计指定领域已 COMMIT 的任务数量"""
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryDomain, DomainFactoryTask

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(DomainFactoryTask.id))
                .join(DomainFactoryDomain, DomainFactoryTask.domain_id == DomainFactoryDomain.id)
                .where(
                    DomainFactoryDomain.code == domain_code,
                    DomainFactoryTask.status == "COMMITTED",
                )
            )
            return result.scalar() or 0

    async def get_domain_by_code(self, code: str) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.code == code))
            return result.scalar_one_or_none()

    async def get_domain_by_id(self, id: int) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.id == id))
            return result.scalar_one_or_none()

    async def list_domains(self) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).order_by(DomainFactoryDomain.created_at.desc()))
            domains = result.scalars().all()
            return [d.to_dict() for d in domains]

    async def create_domain(self, code: str, name: str, description: str | None = None) -> DomainFactoryDomain:
        async with pg_manager.get_async_session_context() as session:
            domain = DomainFactoryDomain(code=code, name=name, description=description)
            session.add(domain)
        return domain

    async def update_domain(self, id: int, data: dict[str, Any]) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.id == id))
            domain = result.scalar_one_or_none()
            if domain is None:
                return None
            for key, value in data.items():
                if key not in ("id",):
                    setattr(domain, key, value)
        return domain

    async def delete_domain(self, id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.id == id))
            domain = result.scalar_one_or_none()
            if domain is None:
                return False
            await session.delete(domain)
        return True

    # ========== Report Types ==========

    async def list_report_types(self) -> list[dict[str, Any]]:
        """查询所有报告类型"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                text(
                    "SELECT code, name, domain_code, sort_order FROM report_types WHERE is_active = true ORDER BY sort_order"
                )
            )
            return [
                {"code": row.code, "name": row.name, "domain_code": row.domain_code, "sort_order": row.sort_order}
                for row in result.fetchall()
            ]

    # ========== Task ==========

    async def get_task(self, task_id: str) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
            return result.scalar_one_or_none()

    async def get_task_with_domain(self, task_id: str) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            return result.unique().scalar_one_or_none()

    async def list_pending_tasks(self, domain_id: int | None = None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            query = (
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(
                    DomainFactoryTask.status.in_(
                        ["UPLOADED", "PENDING", "PARSING", "EXTRACTING", "GENERALIZING", "WAITING_REVIEW", "FAILED"]
                    )
                )
                .order_by(DomainFactoryTask.created_at.desc())
            )
            if domain_id is not None:
                query = query.where(DomainFactoryTask.domain_id == domain_id)
            result = await session.execute(query)
            tasks = result.unique().scalars().all()
            return [t.to_summary_dict() for t in tasks]

    async def list_history_tasks(self, domain_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            query = (
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.status.in_(["COMMITTED", "REJECTED"]))
                .order_by(DomainFactoryTask.committed_at.desc().nullslast())
                .limit(limit)
            )
            if domain_id is not None:
                query = query.where(DomainFactoryTask.domain_id == domain_id)
            result = await session.execute(query)
            tasks = result.unique().scalars().all()
            return [t.to_history_dict() for t in tasks]

    async def create_task(
        self,
        task_id: str,
        domain_id: int,
        file_name: str,
        storage_path: str,
        uploaded_by: str | None = None,
    ) -> DomainFactoryTask:
        async with pg_manager.get_async_session_context() as session:
            task = DomainFactoryTask(
                id=task_id,
                domain_id=domain_id,
                file_name=file_name,
                storage_path=storage_path,
                status="UPLOADED",
                uploaded_by=uploaded_by,
            )
            session.add(task)
        return task

    async def update_task(self, task_id: str, data: dict[str, Any]) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            for key, value in data.items():
                if key not in ("id",):
                    setattr(task, key, value)
        return task

    async def commit_task(
        self, task_id: str, reviewer: str | None = None, ingest_task_id: str | None = None
    ) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            task.status = "COMMITTED"
            task.committed_at = utc_now_naive()
            if reviewer:
                task.reviewer = reviewer
            if ingest_task_id:
                task.ingest_task_id = ingest_task_id
        return task

    async def delete_task(self, task_id: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                return False
            await session.delete(task)
        return True

    async def list_pending_tasks_by_domain(self, domain_code: str) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .join(DomainFactoryDomain, DomainFactoryTask.domain_id == DomainFactoryDomain.id)
                .where(
                    DomainFactoryDomain.code == domain_code,
                    DomainFactoryTask.status == "WAITING_REVIEW",
                )
            )
            tasks = result.unique().scalars().all()
            return [t.to_summary_dict() for t in tasks]

    # ========== Learned Templates ==========

    async def upsert_learned_template(
        self,
        domain_code: str,
        chapter: str,
        generalized: str,
        slots: list,
        slot_signature: str,
        sample_original: str | None = None,
        extra_meta: dict | None = None,
        report_type_code: str | None = None,
    ) -> DomainFactoryLearnedTemplate | None:
        async with pg_manager.get_async_session_context() as session:
            conditions = [
                DomainFactoryLearnedTemplate.domain_code == domain_code,
                DomainFactoryLearnedTemplate.chapter == chapter,
                DomainFactoryLearnedTemplate.slot_signature == slot_signature,
            ]
            if report_type_code:
                conditions.append(DomainFactoryLearnedTemplate.report_type_code == report_type_code)
            result = await session.execute(select(DomainFactoryLearnedTemplate).where(*conditions))
            existing = result.scalar_one_or_none()

            if existing is None:
                template = DomainFactoryLearnedTemplate(
                    domain_code=domain_code,
                    report_type_code=report_type_code or "通用",
                    chapter=chapter,
                    generalized=generalized,
                    slots=slots,
                    slot_signature=slot_signature,
                    sample_original=sample_original,
                    extra_meta=extra_meta,
                )
                session.add(template)
            else:
                existing.source_count += 1
                if len(generalized) > len(existing.generalized or ""):
                    existing.generalized = generalized
                if sample_original and len(sample_original) > len(existing.sample_original or ""):
                    existing.sample_original = sample_original
                if extra_meta:
                    existing.extra_meta = extra_meta
        return existing if existing else template

    # ========== Outline ==========

    async def upsert_outline(
        self,
        *,
        domain_code,
        report_type_code,
        canonical_chapter_key,
        chapter_id=None,
        chapter_title=None,
        purpose=None,
        overview=None,
        key_points=None,
        content_requirements=None,
        regulations=None,
        entity_bindings=None,
        writing_example=None,
        writing_hints=None,
        expected_tables=None,
        expected_charts=None,
        expected_formulas=None,
        expected_figures=None,
        source_task_ids=None,
        source_count=1,
        prose_based_on_source_count=None,
    ) -> DomainFactoryOutline:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                    DomainFactoryOutline.canonical_chapter_key == canonical_chapter_key,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = DomainFactoryOutline(
                    domain_code=domain_code,
                    report_type_code=report_type_code or "通用",
                    canonical_chapter_key=canonical_chapter_key,
                    chapter_id=chapter_id,
                    chapter_title=chapter_title,
                    purpose=purpose,
                    overview=overview,
                    key_points=key_points or [],
                    content_requirements=content_requirements or [],
                    regulations=regulations or [],
                    entity_bindings=entity_bindings or [],
                    writing_example=writing_example,
                    writing_hints=writing_hints,
                    expected_tables=expected_tables or [],
                    expected_charts=expected_charts or [],
                    expected_formulas=expected_formulas or [],
                    expected_figures=expected_figures or [],
                    source_task_ids=source_task_ids or [],
                    source_count=source_count,
                    prose_based_on_source_count=prose_based_on_source_count,
                )
                session.add(row)
            else:
                # Tier1 单报告：直接覆盖确定性字段；聚合合并在后续版本
                row.chapter_id = chapter_id or row.chapter_id
                row.chapter_title = chapter_title or row.chapter_title
                row.purpose = purpose or row.purpose
                row.overview = overview or row.overview
                row.key_points = key_points or row.key_points
                row.content_requirements = content_requirements or row.content_requirements
                row.regulations = regulations or row.regulations
                row.entity_bindings = entity_bindings or row.entity_bindings
                row.writing_example = writing_example or row.writing_example
                row.writing_hints = writing_hints or row.writing_hints
                row.expected_tables = expected_tables or row.expected_tables
                row.expected_charts = expected_charts or row.expected_charts
                row.expected_formulas = expected_formulas or row.expected_formulas
                row.expected_figures = expected_figures or row.expected_figures
                row.prose_based_on_source_count = prose_based_on_source_count
            await session.commit()
            return row

    async def get_outline(self, domain_code, report_type_code, canonical_chapter_key) -> dict[str, Any] | None:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                    DomainFactoryOutline.canonical_chapter_key == canonical_chapter_key,
                )
            )
            row = result.scalar_one_or_none()
            return row.to_dict() if row else None

    async def list_chapter_keys(self, domain_code, report_type_code) -> list[str]:
        from sqlalchemy import distinct
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline.canonical_chapter_key).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                )
            )
            return [r[0] for r in result.all() if r[0]]

    async def backfill_template_chapter_key(
        self, domain_code, report_type_code, chapter_raw, canonical_chapter_key
    ) -> int:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryLearnedTemplate
        from sqlalchemy import update

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                update(DomainFactoryLearnedTemplate)
                .where(
                    DomainFactoryLearnedTemplate.domain_code == domain_code,
                    DomainFactoryLearnedTemplate.report_type_code == report_type_code,
                    DomainFactoryLearnedTemplate.chapter == chapter_raw,
                )
                .values(canonical_chapter_key=canonical_chapter_key)
            )
            await session.commit()
            return result.rowcount or 0

    async def list_learned_templates(self, domain_code: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = (
                select(DomainFactoryLearnedTemplate)
                .order_by(DomainFactoryLearnedTemplate.source_count.desc())
                .limit(limit)
            )
            if domain_code:
                query = query.where(DomainFactoryLearnedTemplate.domain_code == domain_code)
            result = await session.execute(query)
            templates = result.scalars().all()
            return [t.to_dict() for t in templates]

    async def delete_learned_template(self, template_id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryLearnedTemplate).where(DomainFactoryLearnedTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()
            if template is None:
                return False
            await session.delete(template)
        return True

    async def count_learned_templates(self, domain_code: str | None = None) -> int:
        async with pg_manager.get_async_session_context() as session:
            query = select(func.count(DomainFactoryLearnedTemplate.id))
            if domain_code:
                query = query.where(DomainFactoryLearnedTemplate.domain_code == domain_code)
            result = await session.execute(query)
            return result.scalar() or 0

    # ========== Prompt Config ==========

    async def get_prompt_config(self, domain_code: str | None, prompt_type: str) -> DomainFactoryPromptConfig | None:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainFactoryPromptConfig).where(DomainFactoryPromptConfig.prompt_type == prompt_type)
            if domain_code:
                query = query.where(DomainFactoryPromptConfig.domain_code == domain_code)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def upsert_prompt_config(
        self, domain_code: str | None, prompt_type: str, template: str
    ) -> DomainFactoryPromptConfig:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryPromptConfig).where(
                    DomainFactoryPromptConfig.domain_code == domain_code,
                    DomainFactoryPromptConfig.prompt_type == prompt_type,
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                config = DomainFactoryPromptConfig(domain_code=domain_code, prompt_type=prompt_type, template=template)
                session.add(config)
            else:
                config.template = template
        return config

    async def list_prompt_configs(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainFactoryPromptConfig)
            if domain_code:
                query = query.where(DomainFactoryPromptConfig.domain_code == domain_code)
            result = await session.execute(query)
            configs = result.scalars().all()
            return [c.to_dict() for c in configs]
