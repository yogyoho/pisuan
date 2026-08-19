"""Domain Entity Builder Service - 领域实体构建服务"""

from __future__ import annotations

import uuid
from typing import Any

from yuxi.repositories.domain_entity_repository import DomainEntityRepository
from yuxi.utils import logger

# 六大领域分类映射
CATEGORY_DOMAIN_MAP = {
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


class DomainEntityService:
    """领域实体 Schema 服务"""

    def __init__(self):
        self.repo = DomainEntityRepository()

    # ========== Taxonomy ==========

    async def get_taxonomy(self, domain_code: str | None = None) -> dict[str, Any]:
        categories = await self.repo.list_distinct_categories(domain_code)
        domains = []

        notified_categories = set()
        for cat in categories:
            info = CATEGORY_DOMAIN_MAP.get(cat, self._build_default_domain_info(cat))
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
            notified_categories.add(cat)

        for cat, info in CATEGORY_DOMAIN_MAP.items():
            if cat not in notified_categories:
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

        return {"domains": domains}

    @staticmethod
    def _build_default_domain_info(category: str) -> dict[str, str]:
        clean = category.replace(" ", "").replace("与", "")
        return {
            "domain_id": clean.lower(),
            "domain_name": category,
            "domain_key": clean,
            "description": category,
        }

    # ========== Entity CRUD ==========

    async def list_entities(
        self,
        category: str | None = None,
        domain_code: str | None = None,
    ) -> dict[str, Any]:
        schemas = await self.repo.list_all(category, domain_code)
        return {
            "entity_schemas": schemas,
            "total": len(schemas),
        }

    async def get_entity(self, identifier: str) -> dict[str, Any] | None:
        entity = await self.repo.get_by_id_or_key(identifier)
        return entity.to_dict() if entity else None

    async def create_entity(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("entity_key") or not data.get("name_cn"):
            raise ValueError("entity_key 和 name_cn 不能为空")

        existing = await self.repo.get_by_key(data["entity_key"])
        if existing:
            raise ValueError(f"实体键 {data['entity_key']} 已存在")

        entity_id = data.get("entity_id") or str(uuid.uuid4())
        data["entity_id"] = entity_id

        value_type = data.get("value_type", "String")
        data["value_type"] = self._normalize_value_type(value_type)

        if "properties" in data:
            data["properties"] = [
                self._normalize_property(p) for p in data["properties"]
            ]

        entity = await self.repo.create(data)
        return entity.to_dict()

    async def update_entity(self, identifier: str, data: dict[str, Any]) -> dict[str, Any]:
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")

        if "value_type" in data:
            data["value_type"] = self._normalize_value_type(data["value_type"])
        if "properties" in data and data["properties"] is not None:
            data["properties"] = [
                self._normalize_property(p) for p in data["properties"]
            ]

        updated = await self.repo.update(entity.entity_id, data)
        return updated.to_dict()

    async def delete_entity(self, identifier: str) -> bool:
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")
        return await self.repo.delete(entity.entity_id)

    async def delete_entities_batch(self, identifiers: list[str]) -> int:
        """批量删除实体，返回删除数量"""
        entity_ids = []
        for identifier in identifiers:
            entity = await self.repo.get_by_id_or_key(identifier)
            if entity:
                entity_ids.append(entity.entity_id)
        if not entity_ids:
            return 0
        return await self.repo.delete_many(entity_ids)

    async def clone_entity(self, identifier: str, new_key: str, new_name: str) -> dict[str, Any]:
        """克隆实体"""
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")

        existing = await self.repo.get_by_key(new_key)
        if existing:
            raise ValueError(f"实体键 {new_key} 已存在")

        entity_dict = entity.to_dict()
        entity_dict["entity_id"] = str(uuid.uuid4())
        entity_dict["entity_key"] = new_key
        entity_dict["name_cn"] = new_name

        new_entity = await self.repo.create(entity_dict)
        return new_entity.to_dict()

    # ========== Import / Export ==========

    async def export_all(self, domain_code: str | None = None) -> dict[str, Any]:
        return await self.repo.export_all(domain_code)

    async def import_all(self, config: dict[str, Any]) -> int:
        schemas = config.get("entity_schemas", {})
        entities = list(schemas.values()) if isinstance(schemas, dict) else schemas
        return await self.repo.upsert_all(entities)

    async def get_domains_in_use(self) -> list[dict[str, Any]]:
        return await self.repo.list_domains_in_use()

    # ========== Report Types ==========

    async def list_report_types(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        return await self.repo.list_report_types(domain_code)

    # ========== Seed Default Data ==========

    async def seed_default_entities(self) -> int:
        """从 coal_eia_entity_types.json 导入默认实体类型"""
        import json
        from pathlib import Path

        json_path = Path(__file__).parent.parent.parent.parent / "server" / "coal_eia_entity_types.json"
        if not json_path.exists():
            logger.warning(f"默认实体类型文件不存在: {json_path}")
            return 0

        with open(json_path, encoding="utf-8-sig") as f:
            entity_types = json.load(f)

        existing_count = len(await self.repo.list_all())
        if existing_count >= len(entity_types):
            return 0

        entities = []
        for entity_id, entity_data in entity_types.items():
            entity_key = entity_data.get("id", entity_id)
            name_cn = entity_data.get("name", "")
            category = entity_data.get("category", "")
            description = entity_data.get("description", "")
            examples = entity_data.get("examples", [])
            keywords = entity_data.get("keywords", [])

            value_type = "String"
            is_list_type = False
            if entity_key in ("residential", "pollutant", "spatial_boundary",
                              "ecological_redline", "water_resource", "cultural_relic",
                              "linear_engineering"):
                value_type = "Object"
                is_list_type = True

            properties = []
            if examples:
                for i, example in enumerate(examples[:5]):
                    properties.append({
                        "key": f"item_{i + 1}" if len(examples) > 1 else "name",
                        "name_cn": example,
                        "value_type": "String",
                        "required": False,
                        "description": f"{name_cn}的{example}属性",
                    })

            entities.append({
                "entity_id": f"{entity_key}_schema",
                "entity_key": entity_key,
                "name_cn": name_cn,
                "category": category,
                "domain_code": "coal",
                "value_type": value_type,
                "is_list_type": is_list_type,
                "description": description,
                "synonyms": list(set(keywords + examples))[:10],
                "properties": properties,
                "relation_rules": [],
                "metadata": {"legacy_id": entity_id, "legacy_category": category},
            })

        return await self.repo.upsert_all(entities)

    # ========== Helpers ==========

    @staticmethod
    def _normalize_value_type(value_type: str) -> str:
        if not isinstance(value_type, str):
            return "String"
        if value_type.startswith("List"):
            if "<Object>" in value_type:
                return "Object"
            return "String"
        valid = {"String", "Integer", "Float", "Boolean", "Enum", "Object", "List"}
        return value_type if value_type in valid else "String"

    @staticmethod
    def _normalize_property(prop: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(prop)
        if "value_type" in normalized:
            normalized["value_type"] = DomainEntityService._normalize_value_type(
                normalized["value_type"]
            )
        if "options" in normalized and "enum_options" not in normalized:
            normalized["enum_options"] = normalized.pop("options")
        return normalized

    # ========== AI Entity Extraction ==========

    async def extract_entities_from_document(
        self, content: str, domain_code: str
    ) -> dict[str, Any]:
        """从文档内容中提取实体对象，并与现有实体比对"""

        schemas = await self.repo.list_all(domain_code=domain_code)
        if not schemas:
            return {"entities": [], "comparison": [], "message": "当前行业下没有实体 Schema 定义"}

        prompt = self._build_extraction_prompt(schemas, content, domain_code)

        try:
            from yuxi.models.chat import select_model
            model = select_model()
            response = await model.call(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise RuntimeError(f"AI 模型调用失败: {e}")

        extracted = self._parse_extraction_response(response_text)

        # 与现有同行业实体比对
        existing = await self.repo.list_all(domain_code=domain_code)
        comparison = self._compare_extracted_with_entities(extracted, existing)

        return {
            "entities": extracted,
            "comparison": comparison,
            "total": len(extracted),
            "prompt": prompt,
        }

    async def save_extracted_entities(
        self, entities: list[dict[str, Any]], domain_code: str
    ) -> dict[str, Any]:
        """保存用户确认的提取实体到数据库"""
        import uuid

        inserted = 0
        updated = 0

        for item in entities:
            schema_ref = item.get("schema_ref", "")
            status = item.get("_status", "new")
            entity_id = item.get("_entity_id")

            if status == "new":
                entity_data = {
                    "entity_id": str(uuid.uuid4()),
                    "entity_key": f"{schema_ref}_{domain_code}_{uuid.uuid4().hex[:8]}",
                    "name_cn": item.get("name_cn", schema_ref),
                    "category": item.get("category", ""),
                    "domain_code": domain_code,
                    "value_type": "String",
                    "is_list_type": False,
                    "description": item.get("extracted_text", ""),
                    "synonyms": [],
                    "properties": item.get("values", {}),
                    "relation_rules": [],
                    "metadata": {"extracted_at": "", "confidence": item.get("confidence", 0), "source": "ai_extract"},
                }
                await self.repo.create(entity_data)
                inserted += 1

            elif status == "updated" and entity_id:
                # 更新现有实体
                update_data = {
                    "name_cn": item.get("name_cn"),
                    "description": item.get("extracted_text", ""),
                    "properties": item.get("values", {}),
                }
                await self.repo.update(entity_id, update_data)
                updated += 1

        return {"inserted": inserted, "updated": updated, "total": inserted + updated}

    def _compare_extracted_with_entities(
        self, extracted: list[dict], existing_entities: list[dict]
    ) -> list[dict]:
        """比对提取结果与已有实体"""
        # 构建已有实体索引（按 entity_key 分组）
        existing_by_key = {}
        for e in existing_entities:
            key = e.get("entity_key", "")
            if key not in existing_by_key:
                existing_by_key[key] = []
            existing_by_key[key].append(e)

        comparison = []
        for item in extracted:
            schema_ref = item.get("schema_ref", "")
            existing_list = existing_by_key.get(schema_ref, [])

            if not existing_list:
                comparison.append({
                    **item,
                    "_status": "new",
                    "_entity_id": None,
                    "_diff": None,
                    "_existing": None,
                })
            else:
                # 取第一个匹配的已有实体进行比对
                existing = existing_list[0]
                item_values = item.get("values", {}) or {}
                existing_values = existing.get("properties", {}) or {}

                # 简单对比：value 是否有差异
                diff = {}
                all_keys = set(list(item_values.keys()) + list(existing_values.keys()))
                for k in all_keys:
                    new_val = item_values.get(k)
                    old_val = existing_values.get(k)
                    if str(new_val) != str(old_val):
                        diff[k] = {"extracted": new_val, "existing": old_val}

                status = "different" if diff else "matched"
                comparison.append({
                    **item,
                    "_status": status,
                    "_entity_id": existing.get("entity_id"),
                    "_diff": diff if diff else None,
                    "_existing": {
                        "entity_id": existing.get("entity_id"),
                        "entity_key": existing.get("entity_key"),
                        "name_cn": existing.get("name_cn"),
                        "category": existing.get("category"),
                        "properties": existing_values,
                    } if status == "different" else None,
                })

        return comparison

    def _build_extraction_prompt(
        self, schemas: list[dict[str, Any]], content: str, domain_code: str
    ) -> list[dict]:
        """构建实体提取 Prompt"""
        schema_desc_parts = []
        for s in schemas:
            entity_key = s.get("entity_key", "")
            name_cn = s.get("name_cn", "")
            category = s.get("category", "")
            description = s.get("description", "")
            value_type = s.get("value_type", "String")
            is_list = s.get("is_list_type", False)
            unit = s.get("unit", "")
            properties = s.get("properties", [])
            synonyms = s.get("synonyms", [])

            lines = [f"### {name_cn} (`{entity_key}`)"]
            lines.append(f"- 分类: {category}")
            if description:
                lines.append(f"- 描述: {description}")
            lines.append(f"- 值类型: {value_type}")
            if is_list:
                lines.append("- **列表类型**: 文档中可能出现多个实例")
            if unit:
                lines.append(f"- 单位: {unit}")
            if synonyms:
                lines.append(f"- 同义词/别称: {', '.join(synonyms[:8])}")
            if properties:
                lines.append("- 属性字段:")
                for p in properties[:10]:
                    pk = p.get("key", "")
                    pn = p.get("name_cn", "")
                    pt = p.get("value_type", "String")
                    pd = p.get("description", "")
                    lines.append(f"  - `{pk}` ({pn}): {pt} — {pd}")
            schema_desc_parts.append("\n".join(lines))

        schema_text = "\n\n".join(schema_desc_parts)

        domain_name = {"coal": "煤炭采掘", "chem": "石油化工", "transport": "交通运输"}.get(
            domain_code, domain_code
        )

        system_prompt = (
            "你是一个专业的领域实体提取助手。"
            "你的任务是从文档中识别和提取符合预定义Schema的实体对象。"
            "提取规则：\n"
            "1. 实体对象是独立的概念，拥有自己的属性，能在知识图谱中建立关系\n"
            "2. 实体的属性（如名称、数值、状态等）不能独立成为实体\n"
            "3. 列表类型实体需提取文档中提到的每一个实例\n"
            "4. 只提取文档中明确提到的信息，不要推断\n"
            "5. 如果某个实体在文档中没有找到，不要凭空创建\n"
            "6. 严格按JSON格式输出，不要包含其他文字"
        )

        user_prompt = (
            f"## 行业领域: {domain_name}\n\n"
            f"## 实体Schema定义:\n\n{schema_text}\n\n"
            f"## 文档内容:\n\n{content[:12000]}\n\n"
            "## 输出要求:\n"
            "请以JSON数组格式返回提取到的实体实例，格式如下：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "schema_ref": "对应的entity_key",\n'
            '    "name_cn": "实体实例名称",\n'
            '    "category": "所属分类",\n'
            '    "confidence": 0.0-1.0之间的置信度,\n'
            '    "extracted_text": "文档中对应的原文片段",\n'
            '    "values": {\n'
            '      "属性key": "提取到的属性值",\n'
            '      ...\n'
            "    }\n"
            "  }\n"
            "]\n"
            "```\n\n"
            "只返回JSON数组，不要有其他内容。"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_extraction_response(self, response_text: str) -> list[dict[str, Any]]:
        """解析 LLM 提取响应"""
        import json
        import re

        # 尝试提取 JSON 数组
        json_match = re.search(r"\[[\s\S]*\]", response_text)
        if not json_match:
            # 尝试提取 JSON 对象
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                try:
                    obj = json.loads(json_match.group())
                    return [obj] if isinstance(obj, dict) else obj
                except json.JSONDecodeError:
                    pass
            logger.warning(f"无法解析提取响应中的 JSON: {response_text[:500]}")
            return []

        try:
            result = json.loads(json_match.group())
            if isinstance(result, list):
                return result
            return [result] if isinstance(result, dict) else []
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}, 原文: {response_text[:500]}")
            return []


_entity_service: DomainEntityService | None = None


def get_entity_service() -> DomainEntityService:
    global _entity_service
    if _entity_service is None:
        _entity_service = DomainEntityService()
    return _entity_service
