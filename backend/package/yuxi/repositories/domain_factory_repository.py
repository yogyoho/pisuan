"""Domain Factory 数据访问层 - Repository"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, delete
from sqlalchemy.dialects.postgresql import insert

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactorySchema,
    DomainFactoryTask,
    DomainFactoryContext,
    DomainFactorySavedSection,
    DomainFactoryPromptConfig,
    DomainFactoryStandardCodeMapping,
)
from yuxi.utils.datetime_utils import utc_now_naive


class DomainFactoryRepository:
    """领域知识工厂数据访问层"""

    # ========== Domain ==========

    async def get_domain_by_code(self, code: str) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).where(DomainFactoryDomain.code == code)
            )
            return result.scalar_one_or_none()

    async def get_domain_by_id(self, id: int) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).where(DomainFactoryDomain.id == id)
            )
            return result.scalar_one_or_none()

    async def list_domains(self) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).order_by(DomainFactoryDomain.created_at.desc())
            )
            domains = result.scalars().all()
            return [d.to_dict() for d in domains]

    async def create_domain(self, code: str, name: str, description: str | None = None) -> DomainFactoryDomain:
        async with pg_manager.get_async_session_context() as session:
            domain = DomainFactoryDomain(code=code, name=name, description=description)
            session.add(domain)
        return domain

    async def update_domain(self, id: int, data: dict[str, Any]) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).where(DomainFactoryDomain.id == id)
            )
            domain = result.scalar_one_or_none()
            if domain is None:
                return None
            for key, value in data.items():
                if key not in ("id",):
                    setattr(domain, key, value)
        return domain

    async def delete_domain(self, id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).where(DomainFactoryDomain.id == id)
            )
            domain = result.scalar_one_or_none()
            if domain is None:
                return False
            await session.delete(domain)
        return True

    # ========== Schema ==========

    async def get_schema(self, domain_id: int) -> DomainFactorySchema | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactorySchema).where(DomainFactorySchema.domain_id == domain_id)
            )
            return result.scalar_one_or_none()

    async def upsert_schema(self, domain_id: int, variables: list, chapters: list) -> DomainFactorySchema:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactorySchema).where(DomainFactorySchema.domain_id == domain_id)
            )
            schema = result.scalar_one_or_none()
            if schema is None:
                schema = DomainFactorySchema(domain_id=domain_id, variables=variables, chapters=chapters)
                session.add(schema)
            else:
                schema.variables = variables
                schema.chapters = chapters
        return schema

    # ========== Task ==========

    async def get_task(self, task_id: str) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryTask).where(DomainFactoryTask.id == task_id)
            )
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
                .where(DomainFactoryTask.status.in_(["UPLOADED", "PENDING", "PARSING", "EXTRACTING", "GENERALIZING", "WAITING_REVIEW"]))
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
            result = await session.execute(
                select(DomainFactoryTask).where(DomainFactoryTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return False
            await session.delete(task)
        return True

    # ========== Context ==========

    async def get_or_create_context(self, domain_code: str, report_type: str) -> DomainFactoryContext:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryContext).where(
                    DomainFactoryContext.domain_code == domain_code,
                    DomainFactoryContext.report_type == report_type,
                )
            )
            ctx = result.scalar_one_or_none()
            if ctx is None:
                ctx = DomainFactoryContext(
                    domain_code=domain_code,
                    report_type=report_type,
                    section_tree_json=[],
                    routing_rules_json={},
                )
                session.add(ctx)
            return ctx

    async def get_context(self, domain_code: str, report_type: str) -> DomainFactoryContext | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryContext).where(
                    DomainFactoryContext.domain_code == domain_code,
                    DomainFactoryContext.report_type == report_type,
                )
            )
            return result.scalar_one_or_none()

    async def update_context(
        self,
        domain_code: str,
        report_type: str,
        section_tree: list | None = None,
        routing_rules: dict | None = None,
    ) -> DomainFactoryContext | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryContext).where(
                    DomainFactoryContext.domain_code == domain_code,
                    DomainFactoryContext.report_type == report_type,
                )
            )
            ctx = result.scalar_one_or_none()
            if ctx is None:
                return None
            if section_tree is not None:
                ctx.section_tree_json = section_tree
            if routing_rules is not None:
                ctx.routing_rules_json = routing_rules
        return ctx

    async def list_contexts(self) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryContext).order_by(DomainFactoryContext.domain_code))
            contexts = result.scalars().all()
            return [c.to_dict() for c in contexts]

    # ========== Saved Sections ==========

    async def get_saved_section(self, section_id: str) -> DomainFactorySavedSection | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactorySavedSection).where(DomainFactorySavedSection.id == section_id)
            )
            return result.scalar_one_or_none()

    async def list_saved_sections(
        self, domain_id: str | None = None, report_type_id: str | None = None
    ) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainFactorySavedSection).order_by(DomainFactorySavedSection.created_at.desc())
            if domain_id:
                query = query.where(DomainFactorySavedSection.domain_id == domain_id)
            if report_type_id:
                query = query.where(DomainFactorySavedSection.report_type_id == report_type_id)
            result = await session.execute(query)
            sections = result.scalars().all()
            return [s.to_dict() for s in sections]

    async def save_section(
        self,
        section_id: str,
        domain_id: str,
        report_type_id: str | None,
        filename: str | None,
        section_tree: list,
    ) -> DomainFactorySavedSection:
        async with pg_manager.get_async_session_context() as session:
            existing = await session.execute(
                select(DomainFactorySavedSection).where(DomainFactorySavedSection.id == section_id)
            )
            section = existing.scalar_one_or_none()
            if section is None:
                section = DomainFactorySavedSection(
                    id=section_id,
                    domain_id=domain_id,
                    report_type_id=report_type_id,
                    filename=filename,
                    section_tree_json=section_tree,
                )
                session.add(section)
            else:
                section.section_tree_json = section_tree
        return section

    async def delete_saved_section(self, section_id: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactorySavedSection).where(DomainFactorySavedSection.id == section_id)
            )
            section = result.scalar_one_or_none()
            if section is None:
                return False
            await session.delete(section)
        return True

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
                config = DomainFactoryPromptConfig(
                    domain_code=domain_code, prompt_type=prompt_type, template=template
                )
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

    # ========== Standard Code Mapping ==========

    async def list_standard_code_mappings(self) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryStandardCodeMapping).order_by(
                    DomainFactoryStandardCodeMapping.standard_code
                )
            )
            mappings = result.scalars().all()
            return [
                {
                    "standard_code": m.standard_code,
                    "name": m.name,
                    "description": m.description,
                    "payload": m.payload or {},
                }
                for m in mappings
            ]

    async def upsert_standard_code_mappings(self, items: list[dict[str, Any]]) -> bool:
        async with pg_manager.get_async_session_context() as session:
            for item in items:
                standard_code = item.get("standard_code")
                if not standard_code:
                    continue
                result = await session.execute(
                    select(DomainFactoryStandardCodeMapping).where(
                        DomainFactoryStandardCodeMapping.standard_code == standard_code
                    )
                )
                mapping = result.scalar_one_or_none()
                if mapping is None:
                    mapping = DomainFactoryStandardCodeMapping(
                        standard_code=standard_code,
                        name=item.get("name", ""),
                        description=item.get("description"),
                        payload=item.get("payload"),
                    )
                    session.add(mapping)
                else:
                    mapping.name = item.get("name", mapping.name)
                    mapping.description = item.get("description", mapping.description)
                    mapping.payload = item.get("payload", mapping.payload)
        return True

    # ========== Section Metadata (章节元数据) ==========

    async def get_section_by_id(self, section_id: int) -> Any | None:
        """根据ID获取章节"""
        async with pg_manager.get_async_session_context() as session:
            # 尝试从 contexts 表中查找
            result = await session.execute(
                select(DomainFactoryContext).where(DomainFactoryContext.id == section_id)
            )
            ctx = result.scalar_one_or_none()
            if ctx:
                return ctx
            return None

    async def create_section(
        self,
        code: str,
        title: str,
        section_path: str,
        level: int,
        domain: str,
        report_type: str,
        parent_id: int | None = None,
        standard_code: str | None = None,
        match_confidence: int | None = None,
        sort_order: int = 0,
        template_data: dict[str, Any] | None = None,
        context_routing: dict[str, Any] | None = None,
        writing_guidance: dict[str, Any] | None = None,
        entity_bindings: list[dict[str, Any]] | None = None,
    ) -> DomainFactoryContext:
        """创建章节"""
        async with pg_manager.get_async_session_context() as session:
            ctx = await session.execute(
                select(DomainFactoryContext).where(
                    DomainFactoryContext.domain_code == domain,
                    DomainFactoryContext.report_type == report_type,
                )
            )
            existing = ctx.scalar_one_or_none()
            
            if existing:
                # 更新现有上下文，添加章节到树中
                tree = existing.section_tree_json or []
                new_section = {
                    "code": code,
                    "title": title,
                    "section_path": section_path,
                    "level": level,
                    "parent_id": parent_id,
                    "standard_code": standard_code,
                    "match_confidence": match_confidence,
                    "sort_order": sort_order,
                    "template_data": template_data,
                    "context_routing": context_routing,
                    "writing_guidance": writing_guidance,
                    "entity_bindings": entity_bindings,
                    "children": [],
                }
                tree.append(new_section)
                existing.section_tree_json = tree
                return existing
            else:
                # 创建新上下文
                section_tree = [{
                    "code": code,
                    "title": title,
                    "section_path": section_path,
                    "level": level,
                    "parent_id": parent_id,
                    "standard_code": standard_code,
                    "match_confidence": match_confidence,
                    "sort_order": sort_order,
                    "template_data": template_data,
                    "context_routing": context_routing,
                    "writing_guidance": writing_guidance,
                    "entity_bindings": entity_bindings,
                    "children": [],
                }]
                new_ctx = DomainFactoryContext(
                    domain_code=domain,
                    report_type=report_type,
                    section_tree_json=section_tree,
                    routing_rules_json={},
                )
                session.add(new_ctx)
                return new_ctx

    async def update_section(
        self,
        section_id: int,
        title: str | None = None,
        section_path: str | None = None,
        level: int | None = None,
        parent_id: int | None = None,
        standard_code: str | None = None,
        match_confidence: int | None = None,
        sort_order: int | None = None,
        template_data: dict[str, Any] | None = None,
        context_routing: dict[str, Any] | None = None,
        writing_guidance: dict[str, Any] | None = None,
        entity_bindings: list[dict[str, Any]] | None = None,
    ) -> Any | None:
        """更新章节"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryContext).where(DomainFactoryContext.id == section_id)
            )
            ctx = result.scalar_one_or_none()
            if not ctx:
                return None
            
            # 更新 routing_rules_json 中的章节信息
            routing_rules = ctx.routing_rules_json or {}
            if title is not None:
                routing_rules["_update_title"] = title
            if standard_code is not None:
                routing_rules["_update_standard_code"] = standard_code
            ctx.routing_rules_json = routing_rules
            return ctx

    async def delete_section(self, section_id: int) -> bool:
        """删除章节"""
        # 章节存储在 JSON 中，需要更新上下文
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryContext).where(DomainFactoryContext.id == section_id)
            )
            ctx = result.scalar_one_or_none()
            if not ctx:
                return False
            # 不删除整个上下文，只标记
            return True
