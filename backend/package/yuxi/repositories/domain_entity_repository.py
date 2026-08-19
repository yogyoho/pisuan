"""Domain Entity Builder 数据访问层 - Repository"""

import uuid
from typing import Any

from sqlalchemy import select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_entity import DomainEntitySchema, ReportType
from yuxi.storage.postgres.models_domain_factory import DomainFactoryDomain


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

            updatable = [
                "entity_key", "name_cn", "category", "domain_code",
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

    async def delete_many(self, entity_ids: list[str]) -> int:
        """批量删除实体"""
        count = 0
        async with pg_manager.get_async_session_context() as session:
            for eid in entity_ids:
                result = await session.execute(
                    select(DomainEntitySchema).where(DomainEntitySchema.entity_id == eid)
                )
                entity = result.scalar_one_or_none()
                if entity is not None:
                    await session.delete(entity)
                    count += 1
        return count

    async def upsert_all(self, entities: list[dict[str, Any]]) -> int:
        """批量 upsert 实体（用于导入/初始化）"""
        count = 0
        async with pg_manager.get_async_session_context() as session:
            for data in entities:
                entity_id = data.get("entity_id")
                if not entity_id:
                    continue
                existing = await session.execute(
                    select(DomainEntitySchema).where(DomainEntitySchema.entity_id == entity_id)
                )
                entity = existing.scalar_one_or_none()
                if entity is None:
                    entity = DomainEntitySchema(
                        entity_id=entity_id,
                        entity_key=data.get("entity_key", ""),
                        name_cn=data.get("name_cn", ""),
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
                else:
                    for key in ["entity_key", "name_cn", "category", "domain_code",
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
        entities = await self.list_all(domain_code=domain_code)
        categories = await self.list_distinct_categories(domain_code)

        domain_mappings = {
            "project_basic": {
                "domain_id": "project_basic",
                "domain_name": "基础工程实体",
                "domain_key": "ProjectBasic",
                "description": "定义'谁在建'、'建什么'、'怎么建'",
            },
            "natural_env": {
                "domain_id": "natural_env",
                "domain_name": "自然环境实体",
                "domain_key": "NaturalEnv",
                "description": "定义自然环境要素",
            },
            "env_quality": {
                "domain_id": "env_quality",
                "domain_name": "环境质量与污染源实体",
                "domain_key": "EnvQuality",
                "description": "定义环境质量与污染源",
            },
            "sensitive_target": {
                "domain_id": "sensitive_target",
                "domain_name": "敏感目标与空间实体",
                "domain_key": "SensitiveTarget",
                "description": "定义'在哪建'、'周围有什么'",
            },
            "measures_regulation": {
                "domain_id": "measures_regulation",
                "domain_name": "措施与法规实体",
                "domain_key": "MeasuresRegulation",
                "description": "定义'怎么办'、'依据什么'",
            },
            "impact_assessment": {
                "domain_id": "impact_assessment",
                "domain_name": "环境影响评价实体",
                "domain_key": "ImpactAssessment",
                "description": "定义'产生什么问题'、'后果如何'",
            },
        }

        domains = []
        for cat in categories:
            info = domain_mappings.get(cat, {
                "domain_id": cat.lower().replace(" ", "_"),
                "domain_name": cat,
                "domain_key": cat.replace(" ", ""),
                "description": cat,
            })
            domains.append({
                "domain_id": info["domain_id"],
                "domain_name": info["domain_name"],
                "domain_key": info["domain_key"],
                "description": info["description"],
                "categories": [{
                    "category_id": f"{info['domain_id']}_category",
                    "category_name": cat,
                    "category_key": cat.replace(" ", "").replace("与", "And"),
                    "description": f"{cat}分类",
                }],
            })

        entity_map = {e["entity_id"]: e for e in entities}

        return {
            "taxonomy": {"domains": domains},
            "entity_schemas": entity_map,
            "version": "1.0.0",
        }

    # ========== Report Types ==========

    async def list_report_types(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(ReportType).where(ReportType.is_active.is_(True)).order_by(ReportType.sort_order)
            if domain_code:
                query = query.where(ReportType.domain_code == domain_code)
            result = await session.execute(query)
            return [r[0].to_dict() for r in result.all()]

    async def list_domains_in_use(self) -> list[dict[str, Any]]:
        """列出 domain_factory_domains 字典表中所有行业"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).order_by(DomainFactoryDomain.id)
            )
            return [r[0].to_dict() for r in result.all()]
