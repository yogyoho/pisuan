"""Domain Entity Builder 数据访问层 - Repository"""

import uuid
from typing import Any

from sqlalchemy import func, select

from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_entity import DomainEntitySchema, ReportType
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryLearnedTemplate,
    DomainFactoryRegionalFact,
    DomainFactoryReport,
    DomainFactoryReportPps,
    DomainFactoryTask,
)
from yuxi.utils.datetime_utils import format_utc_datetime


class DomainEntityRepository:
    """领域实体 Schema 数据访问层"""

    # ========== Taxonomy ==========

    async def list_distinct_categories(self, domain_code: str | None = None) -> list[str]:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainEntitySchema.category).distinct()
            if domain_code:
                query = query.where(DomainEntitySchema.domain_code == domain_code)
            result = await session.execute(query)
            return sorted([r[0] for r in result.all()])

    async def count_by_category(self, category: str, domain_code: str | None = None) -> int:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainEntitySchema).where(DomainEntitySchema.category == category)
            if domain_code:
                query = query.where(DomainEntitySchema.domain_code == domain_code)
            result = await session.execute(query)
            return len(result.scalars().all())

    async def counts_by_category(self, domain_code: str | None = None) -> dict[str, int]:
        """一次分组取各分类实体数（分类管理/树渲染用）。"""
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainEntitySchema.category, func.count(DomainEntitySchema.entity_id)).group_by(
                DomainEntitySchema.category
            )
            if domain_code:
                query = query.where(DomainEntitySchema.domain_code == domain_code)
            result = await session.execute(query)
            return {row[0]: int(row[1]) for row in result.all()}

    # ========== CRUD ==========

    async def list_all(
        self,
        category: str | None = None,
        domain_code: str | None = None,
    ) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainEntitySchema).order_by(
                DomainEntitySchema.category, DomainEntitySchema.name_cn
            )
            if category:
                query = query.where(DomainEntitySchema.category == category)
            if domain_code:
                query = query.where(DomainEntitySchema.domain_code == domain_code)
            result = await session.execute(query)
            return [e.to_dict() for e in result.scalars().all()]

    async def get_by_id(self, entity_id: str) -> DomainEntitySchema | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainEntitySchema).where(DomainEntitySchema.entity_id == entity_id)
            )
            return result.scalar_one_or_none()

    async def get_by_key(self, entity_key: str, domain_code: str | None = None) -> DomainEntitySchema | None:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainEntitySchema).where(DomainEntitySchema.entity_key == entity_key)
            if domain_code:
                query = query.where(DomainEntitySchema.domain_code == domain_code)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_by_id_or_key(self, identifier: str) -> DomainEntitySchema | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainEntitySchema).where(
                    (DomainEntitySchema.entity_id == identifier)
                    | (DomainEntitySchema.entity_key == identifier)
                )
            )
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> DomainEntitySchema:
        async with pg_manager.get_async_session_context() as session:
            entity = DomainEntitySchema(
                entity_id=data.get("entity_id", str(uuid.uuid4())),
                entity_key=data["entity_key"],
                name_cn=data["name_cn"],
                category=data.get("category", ""),
                domain_code=data.get("domain_code", "coal"),
                value_type=data.get("value_type", "String"),
                unit=data.get("unit"),
                is_list_type=data.get("is_list_type", False),
                description=data.get("description", ""),
                synonyms=data.get("synonyms", []),
                properties=data.get("properties", []),
                relation_rules=data.get("relation_rules", []),
                extra_meta=data.get("metadata", data.get("extra_meta", {})),
            )
            session.add(entity)
        return entity

    async def update(self, entity_id: str, data: dict[str, Any]) -> DomainEntitySchema | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainEntitySchema).where(DomainEntitySchema.entity_id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity is None:
                return None

            # entity_key 是模板 entity_ref 的前缀，改名会使存量引用悬空，不在可更新列中
            updatable = [
                "name_cn", "category", "domain_code",
                "value_type", "unit", "is_list_type", "description", "synonyms",
                "properties", "relation_rules",
            ]
            for key in updatable:
                if key in data and data[key] is not None:
                    setattr(entity, key, data[key])
            if "metadata" in data and data["metadata"] is not None:
                entity.extra_meta = data["metadata"]
            elif "extra_meta" in data and data["extra_meta"] is not None:
                entity.extra_meta = data["extra_meta"]

        return entity

    async def delete(self, entity_id: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainEntitySchema).where(DomainEntitySchema.entity_id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity is None:
                return False
            await session.delete(entity)
        return True

    async def upsert_all(self, entities: list[dict[str, Any]]) -> int:
        """批量 upsert 实体（用于导入/初始化）。

        按 entity_key 对齐：它是 entity_ref 的实际标识；entity_id 只是环境内代理键，
        跨环境导入时对不上，直接复用还会撞主键。调用方负责校验 entity_key/name_cn。
        """
        count = 0
        async with pg_manager.get_async_session_context() as session:
            existing = await session.execute(select(DomainEntitySchema))
            existing_by_key = {row.entity_key: row for row in existing.scalars().all()}
            for data in entities:
                entity = existing_by_key.get(data["entity_key"])
                if entity is None:
                    entity = DomainEntitySchema(
                        entity_id=data.get("entity_id") or str(uuid.uuid4()),
                        entity_key=data["entity_key"],
                        name_cn=data["name_cn"],
                        category=data.get("category", ""),
                        domain_code=data.get("domain_code", "coal"),
                        value_type=data.get("value_type", "String"),
                        unit=data.get("unit"),
                        is_list_type=data.get("is_list_type", False),
                        description=data.get("description", ""),
                        synonyms=data.get("synonyms", []),
                        properties=data.get("properties", []),
                        relation_rules=data.get("relation_rules", []),
                        extra_meta=data.get("metadata", data.get("extra_meta", {})),
                    )
                    session.add(entity)
                    existing_by_key[entity.entity_key] = entity
                else:
                    for key in ["name_cn", "category",
                                "value_type", "unit", "is_list_type",
                                "description", "synonyms", "properties", "relation_rules"]:
                        if key in data and data[key] is not None:
                            setattr(entity, key, data[key])
                    if "metadata" in data and data["metadata"] is not None:
                        entity.extra_meta = data["metadata"]
                    elif "extra_meta" in data and data["extra_meta"] is not None:
                        entity.extra_meta = data["extra_meta"]
                count += 1
        return count

    async def export_all(self, domain_code: str | None = None) -> dict[str, Any]:
        """导出实体配置（taxonomy 由 service 从分类字典统一渲染，这里不再复制映射）。"""
        entities = await self.list_all(domain_code=domain_code)
        return {
            "entity_schemas": {e["entity_id"]: e for e in entities},
            "version": "1.0.0",
        }

    # ========== Usage / References ==========

    async def list_usage_learned_templates(self, domain_code: str) -> list[dict[str, Any]]:
        """引用扫描：已学习段落模板的 slots（含 entity_ref）。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(
                    DomainFactoryLearnedTemplate.id,
                    DomainFactoryLearnedTemplate.chapter,
                    DomainFactoryLearnedTemplate.report_type_code,
                    DomainFactoryLearnedTemplate.source_count,
                    DomainFactoryLearnedTemplate.updated_at,
                    DomainFactoryLearnedTemplate.slots,
                )
                .where(DomainFactoryLearnedTemplate.domain_code == domain_code)
                .order_by(DomainFactoryLearnedTemplate.updated_at.desc())
            )
            return [
                {
                    "id": row.id,
                    "chapter": row.chapter,
                    "report_type_code": row.report_type_code,
                    "source_count": row.source_count,
                    "updated_at": format_utc_datetime(row.updated_at),
                    "slots": row.slots or [],
                }
                for row in result.all()
            ]

    async def list_usage_pending_tasks(self, domain_code: str) -> list[dict[str, Any]]:
        """引用扫描：待审核任务的 source_paragraphs[].template.slots。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(
                    DomainFactoryTask.id,
                    DomainFactoryTask.file_name,
                    DomainFactoryTask.source_paragraphs,
                )
                .join(DomainFactoryDomain, DomainFactoryTask.domain_id == DomainFactoryDomain.id)
                .where(
                    DomainFactoryDomain.code == domain_code,
                    DomainFactoryTask.status == "WAITING_REVIEW",
                )
                .order_by(DomainFactoryTask.updated_at.desc())
            )
            return [
                {
                    "id": row.id,
                    "file_name": row.file_name,
                    "source_paragraphs": row.source_paragraphs or [],
                }
                for row in result.all()
            ]

    async def list_usage_report_pps(self, domain_code: str) -> list[dict[str, Any]]:
        """引用扫描：写作侧报告参数（entity_key 裸键或点号形态）。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryReportPps.report_id, DomainFactoryReportPps.entity_key)
                .join(DomainFactoryReport, DomainFactoryReportPps.report_id == DomainFactoryReport.id)
                .where(DomainFactoryReport.domain_code == domain_code)
            )
            return [{"report_id": row.report_id, "entity_key": row.entity_key} for row in result.all()]

    async def list_usage_regional_facts(self) -> list[dict[str, Any]]:
        """引用扫描：区域事实（无 domain_code，按 entity_key 全局统计）。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryRegionalFact.entity_key, DomainFactoryRegionalFact.status).where(
                    DomainFactoryRegionalFact.entity_key.isnot(None)
                )
            )
            return [{"entity_key": row.entity_key, "status": row.status} for row in result.all()]

    # ========== Report Types ==========

    async def list_report_types(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(ReportType).where(ReportType.is_active.is_(True)).order_by(ReportType.sort_order)
            if domain_code:
                query = query.where(ReportType.domain_code == domain_code)
            result = await session.execute(query)
            return [r[0].to_dict() for r in result.all()]

    async def list_domains_in_use(self) -> list[dict[str, Any]]:
        """列出 domain_factory_domains 字典表行业（去领域化：仅暴露通用域，历史域行冻结保留不外露）"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain)
                .where(DomainFactoryDomain.code == GENERAL_DOMAIN_CODE)
                .order_by(DomainFactoryDomain.id)
            )
            return [r[0].to_dict() for r in result.all()]
