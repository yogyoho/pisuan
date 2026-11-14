"""Domain Entity Builder Service - 领域实体构建服务"""

from __future__ import annotations

import re
import uuid
from typing import Any

from pisuan.repositories.domain_entity_category_repository import DomainEntityCategoryRepository
from pisuan.repositories.domain_entity_repository import DomainEntityRepository
from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from pisuan.utils import logger
from pisuan.utils.datetime_utils import format_utc_datetime, utc_now_naive

VALID_VALUE_TYPES = ("String", "Integer", "Float", "Boolean", "Enum", "Object", "List")

# 历史数据兼容别名：显式映射，未知值一律拒绝（不再静默转 String）
LEGACY_VALUE_TYPE_ALIASES = {
    "Numeric": "Float",
    "Number": "Float",
    "Date": "String",
    "Text": "String",
}

# AI 提取：模型只看到前 N 个字符，响应里必须回传覆盖信息
EXTRACTION_CONTENT_LIMIT = 12000
# 前端默认勾选门槛（后端只记录，不做硬拒绝）
EXTRACTION_CONFIDENCE_DEFAULT = 0.6
# 新实体提案的标记值
PROPOSAL_SCHEMA_REF = "__proposal__"

_KEY_FORBIDDEN_CHARS = re.compile(r"[\s.。]")


def validate_key(value: Any, label: str) -> str:
    """校验实体键/属性键的契约必需项：非空、无空白与点号、长度受限。"""
    key = str(value or "").strip()
    if not key:
        raise ValueError(f"{label}不能为空")
    if len(key) > 64:
        raise ValueError(f"{label} `{key[:20]}…` 超过 64 字符")
    if _KEY_FORBIDDEN_CHARS.search(key):
        raise ValueError(f"{label} `{key}` 含空白或点号（entity_ref 用点号分隔），示例：coal_usage")
    return key


def canonical_property_key(raw: Any) -> str:
    """把模型给出的属性键规整成可作为 entity_ref 后缀的键。"""
    key = re.sub(r"[\s.。\-/]+", "_", str(raw or "").strip()).strip("_")
    return key[:64]


def infer_value_type(values: list[Any]) -> str:
    """按样本值推断值类型，只做保守推断。"""
    if not values:
        return "String"
    if all(isinstance(v, bool) for v in values):
        return "Boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "Float"
    if all(isinstance(v, list) for v in values):
        return "List"
    return "String"


def _strip_whitespace(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def is_grounded(quote: str, content: str) -> bool:
    """原文字面回查：空白归一化后 quote 必须是 content 的子串。"""
    normalized_quote = _strip_whitespace(quote)
    return bool(normalized_quote) and normalized_quote in _strip_whitespace(content)

class DomainEntityService:
    """领域实体 Schema 服务"""

    def __init__(self):
        self.repo = DomainEntityRepository()
        self.category_repo = DomainEntityCategoryRepository()

    # ========== Taxonomy ==========

    async def get_taxonomy(self, domain_code: str | None = None) -> dict[str, Any]:
        """分类体系：分类字典按 sort_order 渲染（含空分类），字典外历史分类兜底追加。

        停用且无实体的分类不渲染；停用但仍有实体的分类保留，避免存量实体从树上消失。
        """
        counts = await self.repo.counts_by_category(domain_code)
        domains = []
        known: set[str] = set()
        for item in await self.category_repo.list_categories():
            code = item["code"]
            entity_count = counts.get(code, 0)
            if not item["is_active"] and entity_count == 0:
                continue
            domains.append(self._taxonomy_domain(item, entity_count))
            known.add(code)

        # 字典外的分类（历史导入可能留下）仍须在树上可见，按 code 字母序附在末尾
        for code in sorted(set(counts) - known):
            domains.append(
                self._taxonomy_domain(
                    {
                        "code": code,
                        "name_cn": code,
                        "description": "",
                        "sort_order": 10**6,
                        "is_active": True,
                    },
                    counts[code],
                )
            )
        return {"domains": domains}

    @staticmethod
    def _taxonomy_domain(item: dict[str, Any], entity_count: int) -> dict[str, Any]:
        code = item["code"]
        domain_key = "".join(part.capitalize() for part in code.split("_"))
        return {
            "domain_id": code,
            "domain_name": item["name_cn"],
            "domain_key": domain_key,
            "description": item.get("description") or "",
            "is_active": item["is_active"],
            "sort_order": item["sort_order"],
            "entity_count": entity_count,
            "categories": [
                {
                    "category_id": f"{code}_category",
                    "category_name": code,
                    "category_label": item["name_cn"],
                    "category_key": domain_key,
                    "description": item.get("description") or "",
                    "entity_count": entity_count,
                }
            ],
        }

    # ========== Category Dictionary ==========

    async def list_categories(self) -> list[dict[str, Any]]:
        counts = await self.repo.counts_by_category()
        return [
            {**row, "entity_count": counts.get(row["code"], 0)}
            for row in await self.category_repo.list_categories()
        ]

    async def create_category(self, data: dict[str, Any]) -> dict[str, Any]:
        row = await self.category_repo.create(data)
        return {**row, "entity_count": 0}

    async def update_category(self, code: str, data: dict[str, Any]) -> dict[str, Any]:
        """分类 code 不可改（它是实体 category 的存储值），只改名称/描述/排序/启用。"""
        if data.get("code") and data["code"] != code:
            raise ValueError("分类 code 不允许修改（它是实体分类的存储值）")
        row = await self.category_repo.update(code, data)
        counts = await self.repo.counts_by_category()
        return {**row, "entity_count": counts.get(code, 0)}

    async def delete_category(self, code: str) -> None:
        entity_count = await self.repo.count_by_category(code)
        if entity_count:
            raise ValueError(f"分类 `{code}` 下还有 {entity_count} 个实体，先迁走或删除实体后再删分类")
        await self.category_repo.delete(code)

    async def reorder_categories(self, codes: list[str]) -> list[dict[str, Any]]:
        rows = await self.category_repo.reorder(codes)
        counts = await self.repo.counts_by_category()
        return [{**row, "entity_count": counts.get(row["code"], 0)} for row in rows]

    async def _category_codes(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await self.category_repo.list_categories(include_inactive=include_inactive)

    async def _validate_category(self, code: str) -> None:
        if not code:
            raise ValueError("category 不能为空")
        if await self.category_repo.get(code):
            return
        options = "、".join(
            f"{item['code']}（{item['name_cn']}）" for item in await self._category_codes()
        )
        raise ValueError(f"分类 `{code}` 不在分类字典中，可选：{options}")

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
        data = dict(data)
        entity_key = validate_key(data.get("entity_key"), "entity_key")
        if not str(data.get("name_cn") or "").strip():
            raise ValueError("name_cn 不能为空")
        category = str(data.get("category") or "").strip()
        await self._validate_category(category)

        existing = await self.repo.get_by_key(entity_key)
        if existing:
            raise ValueError(f"实体键 {entity_key} 已存在")

        data["entity_key"] = entity_key
        data["entity_id"] = data.get("entity_id") or str(uuid.uuid4())
        # 去领域化：实体归属恒通用域，缺省不得落到 repo 的 legacy "coal"
        if not data.get("domain_code"):
            from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE

            data["domain_code"] = GENERAL_DOMAIN_CODE
        data["value_type"] = self.normalize_value_type(data.get("value_type", "String"))
        data["properties"] = self.normalize_properties(data.get("properties") or [])

        entity = await self.repo.create(data)
        return entity.to_dict()

    async def update_entity(self, identifier: str, data: dict[str, Any]) -> dict[str, Any]:
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")

        # entity_key 是模板 entity_ref 的前缀，改名会让存量引用悬空；改名走 clone
        if data.get("entity_key") and data["entity_key"] != entity.entity_key:
            raise ValueError("entity_key 不允许修改（改名会使模板 entity_ref 失效），请克隆后删除旧实体")
        data = {k: v for k, v in data.items() if k != "entity_key"}

        if "value_type" in data:
            data["value_type"] = self.normalize_value_type(data["value_type"])
        if data.get("properties") is not None:
            data["properties"] = self.normalize_properties(data["properties"])

        updated = await self.repo.update(entity.entity_id, data)
        remapped = await self._remap_waiting_review_tasks()
        if remapped:
            logger.info(f"实体 {identifier} 更新后重映射 {remapped} 个待审核任务")
        return updated.to_dict()

    async def delete_entity(self, identifier: str) -> bool:
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")
        return await self.repo.delete(entity.entity_id)

    async def clone_entity(self, identifier: str, new_key: str, new_name: str) -> dict[str, Any]:
        """克隆实体"""
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")

        new_key = validate_key(new_key, "entity_key")
        if not str(new_name or "").strip():
            raise ValueError("name_cn 不能为空")
        existing = await self.repo.get_by_key(new_key)
        if existing:
            raise ValueError(f"实体键 {new_key} 已存在")

        entity_dict = entity.to_dict()
        entity_dict["entity_id"] = str(uuid.uuid4())
        entity_dict["entity_key"] = new_key
        entity_dict["name_cn"] = new_name

        new_entity = await self.repo.create(entity_dict)
        return new_entity.to_dict()

    # ========== Usage / References ==========

    async def get_entity_usage(self, identifier: str) -> dict[str, Any]:
        """统计实体及属性在存量模板/待审核任务/报告参数/区域事实中的引用。

        entity_ref 契约：以第一个点号切分，前缀 entity_key、后缀属性 key；
        历史数据有中文名后缀，按 name_cn → key 归一。属性已不存在的后缀计入
        dangling_refs（下游会静默降质）；无后缀的引用按实体级引用计数。
        """
        entity = await self.repo.get_by_id_or_key(identifier)
        if not entity:
            raise ValueError(f"实体 {identifier} 不存在")
        data = entity.to_dict()
        entity_key = str(data.get("entity_key") or "")

        properties: dict[str, dict[str, int]] = {}
        prop_key_by_folded: dict[str, str] = {}
        prop_key_by_name: dict[str, str] = {}
        for prop in data.get("properties") or []:
            if not isinstance(prop, dict) or not prop.get("key"):
                continue
            key = str(prop["key"])
            properties[key] = {"templates": 0, "pending_tasks": 0, "report_pps": 0, "facts": 0}
            prop_key_by_folded[key.casefold()] = key
            name = str(prop.get("name_cn") or "").strip()
            if name:
                prop_key_by_name.setdefault(name, key)

        dangling: set[str] = set()

        def tally(ref: str, source: str) -> bool:
            head, sep, suffix = ref.partition(".")
            if head != entity_key:
                return False
            if sep:
                prop_key = prop_key_by_folded.get(suffix.casefold()) or prop_key_by_name.get(suffix)
                if prop_key:
                    properties[prop_key][source] += 1
                else:
                    dangling.add(ref)
            return True

        def refs_of(slots: Any) -> list[str]:
            return [
                str(slot.get("entity_ref") or "").strip()
                for slot in slots or []
                if isinstance(slot, dict) and str(slot.get("entity_ref") or "").strip()
            ]

        template_items = []
        for row in await self.repo.list_usage_learned_templates(GENERAL_DOMAIN_CODE):
            matched = [ref for ref in refs_of(row.get("slots")) if tally(ref, "templates")]
            if matched:
                template_items.append(
                    {
                        "id": row.get("id"),
                        "chapter": row.get("chapter") or "",
                        "report_type_code": row.get("report_type_code") or "",
                        "source_count": row.get("source_count") or 0,
                        "updated_at": row.get("updated_at") or "",
                        "refs": matched,
                    }
                )

        task_items = []
        for row in await self.repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
            slots: list[Any] = []
            for para in row.get("source_paragraphs") or []:
                template = para.get("template") if isinstance(para, dict) else None
                if isinstance(template, dict):
                    slots.extend(template.get("slots") or [])
            matched = [ref for ref in refs_of(slots) if tally(ref, "pending_tasks")]
            if matched:
                task_items.append(
                    {"id": row.get("id"), "file_name": row.get("file_name") or "", "refs": matched}
                )

        pps_count = 0
        for row in await self.repo.list_usage_report_pps(GENERAL_DOMAIN_CODE):
            ref = str(row.get("entity_key") or "").strip()
            if ref and tally(ref, "report_pps"):
                pps_count += 1

        fact_count = 0
        for row in await self.repo.list_usage_regional_facts():
            ref = str(row.get("entity_key") or "").strip()
            if ref and tally(ref, "facts"):
                fact_count += 1

        return {
            "entity_id": data.get("entity_id"),
            "entity_key": entity_key,
            "name_cn": data.get("name_cn"),
            "totals": {
                "templates": len(template_items),
                "pending_tasks": len(task_items),
                "report_pps": pps_count,
                "facts": fact_count,
                "dangling_refs": len(dangling),
            },
            "properties": properties,
            "unused_properties": [
                key for key, counts in properties.items() if not any(counts.values())
            ],
            "dangling_refs": sorted(dangling),
            "template_refs": template_items[:20],
            "pending_task_refs": task_items,
        }

    # ========== Import / Export ==========

    async def export_all(self, domain_code: str | None = None) -> dict[str, Any]:
        """导出实体配置；taxonomy 与页面/选择器共用同一份字典渲染结果。"""
        data = await self.repo.export_all(domain_code)
        data["taxonomy"] = await self.get_taxonomy(domain_code)
        return data

    async def import_all(self, config: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        """导入实体配置：按 entity_key 对齐，先算新增/更新/拒绝，dry_run 只算不写。

        entity_id 是环境内代理键，跨环境不可复用；entity_key 才是 entity_ref 的契约标识，
        因此对齐键取 entity_key，更新时保留本地 entity_id。归属其他行业域的条目直接拒绝，
        避免落成通用域读不到的幽灵实体。分类字典独立管理（v23），导入文件里的
        taxonomy 字段仅作参考、不参与导入；实体 category 原样落库，字典外分类在树上兜底可见。
        """
        schemas = config.get("entity_schemas", {})
        entities = list(schemas.values()) if isinstance(schemas, dict) else schemas
        if not isinstance(entities, list):
            raise ValueError("entity_schemas 必须是对象或数组")

        existing_keys = {row["entity_key"] for row in await self.repo.list_all()}
        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()

        for index, raw in enumerate(entities):
            label = raw if isinstance(raw, dict) else {}
            try:
                data = self._normalize_import_entity(raw)
                if data["entity_key"] in seen:
                    raise ValueError("文件内 entity_key 重复")
            except ValueError as exc:
                rejected.append(
                    {
                        "index": index,
                        "entity_key": str(label.get("entity_key") or ""),
                        "name_cn": str(label.get("name_cn") or ""),
                        "reason": str(exc),
                    }
                )
                continue
            seen.add(data["entity_key"])
            if data["entity_key"] in existing_keys:
                updated.append(data)
            else:
                created.append(data)

        if not dry_run and (created or updated):
            await self.repo.upsert_all(created + updated)
        remapped = await self._remap_waiting_review_tasks() if updated and not dry_run else 0

        return {
            "total": len(entities),
            "created": len(created),
            "updated": len(updated),
            "rejected": rejected,
            "remapped_tasks": remapped,
            "dry_run": dry_run,
        }

    def _normalize_import_entity(self, raw: Any) -> dict[str, Any]:
        """校验并归一一条导入实体；不复用 create 的 category 校验，导入文件可能缺分类。"""
        if not isinstance(raw, dict):
            raise ValueError("条目不是对象")
        data = dict(raw)
        data["entity_key"] = validate_key(raw.get("entity_key"), "entity_key")
        name_cn = str(raw.get("name_cn") or "").strip()
        if not name_cn:
            raise ValueError("name_cn 不能为空")
        data["name_cn"] = name_cn
        declared_domain = str(raw.get("domain_code") or "").strip()
        if declared_domain and declared_domain != GENERAL_DOMAIN_CODE:
            raise ValueError(
                f"归属行业域 `{declared_domain}`，构建器只服务通用域 `{GENERAL_DOMAIN_CODE}`"
            )
        data["domain_code"] = GENERAL_DOMAIN_CODE
        data["value_type"] = self.normalize_value_type(raw.get("value_type", "String"))
        data["properties"] = self.normalize_properties(raw.get("properties") or [])
        return data

    async def get_domains_in_use(self) -> list[dict[str, Any]]:
        return await self.repo.list_domains_in_use()

    # ========== Report Types ==========

    async def list_report_types(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        return await self.repo.list_report_types(domain_code)

    # ========== Helpers ==========

    @staticmethod
    def normalize_value_type(value_type: Any) -> str:
        if not isinstance(value_type, str) or not value_type.strip():
            raise ValueError(f"值类型不能为空，可选：{', '.join(VALID_VALUE_TYPES)}")
        raw = value_type.strip()
        if raw.startswith("List") and "<" in raw:
            return "Object" if "<Object>" in raw else "String"
        normalized = LEGACY_VALUE_TYPE_ALIASES.get(raw, raw)
        if normalized not in VALID_VALUE_TYPES:
            raise ValueError(f"未知值类型 `{raw}`，可选：{', '.join(VALID_VALUE_TYPES)}")
        return normalized

    @classmethod
    def normalize_property(cls, prop: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(prop)
        normalized["value_type"] = cls.normalize_value_type(
            normalized.get("value_type", "String")
        )
        if "options" in normalized and "enum_options" not in normalized:
            normalized["enum_options"] = normalized.pop("options")
        return normalized

    @classmethod
    def normalize_properties(cls, properties: Any) -> list[dict[str, Any]]:
        if not isinstance(properties, list):
            raise ValueError("properties 必须是数组")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, prop in enumerate(properties, start=1):
            if not isinstance(prop, dict):
                raise ValueError(f"第 {index} 个属性不是对象")
            item = cls.normalize_property(prop)
            key = validate_key(item.get("key"), f"第 {index} 个属性的 key")
            folded = key.casefold()
            if folded in seen:
                raise ValueError(f"属性 key `{key}` 重复")
            seen.add(folded)
            item["key"] = key
            normalized.append(item)
        return normalized

    async def _remap_waiting_review_tasks(self) -> int:
        """实体定义变更后，刷新同域待审核任务的 entity_ref。"""
        from pisuan.repositories.domain_factory_repository import (
            GENERAL_DOMAIN_CODE,
        )
        from pisuan.services.domain_factory_service import (
            get_domain_factory_service,
        )

        try:
            return await get_domain_factory_service().remap_waiting_review_tasks(
                GENERAL_DOMAIN_CODE
            )
        except Exception as exc:  # 重映射失败不影响实体保存本身
            logger.warning(f"实体变更后重映射待审核任务失败: {exc}")
            return 0

    # ========== AI Entity Extraction ==========

    async def extract_entities_from_document(
        self, content: str, domain_code: str
    ) -> dict[str, Any]:
        """从文档内容中提取实体对象，并与现有实体比对"""

        schemas = await self.repo.list_all(domain_code=domain_code)
        if not schemas:
            return {"entities": [], "comparison": [], "message": "当前行业下没有实体 Schema 定义"}

        categories = await self._category_codes()
        prompt = self._build_extraction_prompt(schemas, content, domain_code, categories)

        try:
            from pisuan.models.chat import select_model
            from pisuan.config.options import system_options
            model = select_model(model_spec=(await system_options.get())["default_model"])
            response = await model.call(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise RuntimeError(f"AI 模型调用失败: {e}")

        extracted = [
            item for item in self._parse_extraction_response(response_text) if isinstance(item, dict)
        ]
        for item in extracted:
            item["grounded"] = is_grounded(item.get("extracted_text", ""), content)

        comparison = self._compare_extracted_with_entities(
            extracted, schemas, {item["code"] for item in categories}
        )
        scanned = min(len(content), EXTRACTION_CONTENT_LIMIT)

        return {
            "entities": extracted,
            "comparison": comparison,
            "total": len(extracted),
            "coverage": {
                "content_chars": len(content),
                "scanned_chars": scanned,
                "truncated": len(content) > scanned,
            },
            "confidence_threshold": EXTRACTION_CONFIDENCE_DEFAULT,
            "prompt": prompt,
        }

    async def save_extracted_entities(
        self, entities: list[dict[str, Any]], domain_code: str
    ) -> dict[str, Any]:
        """保存用户确认的提取结果。

        提取结果只用于生成/补全 schema 定义，实例值不入库：
        matched 不写、partial 追加属性、new 建实体。
        """
        result: dict[str, Any] = {
            "inserted": 0,
            "updated_entities": 0,
            "properties_added": 0,
            "unchanged": 0,
            "rejected": [],
        }

        for index, item in enumerate(entities):
            label = str(item.get("name_cn") or item.get("schema_ref") or f"第 {index + 1} 条")
            reason = ""

            status = item.get("_status")
            if status not in {"matched", "partial", "new"}:
                reason = "缺少比对状态，请重新提取后再导入"
            elif item.get("grounded") is not True:
                reason = "原文未找到对应片段（无证据），不予导入"
            elif status == "matched":
                result["unchanged"] += 1
                continue
            else:
                try:
                    if status == "partial":
                        await self._append_properties_from_diff(item, result)
                    else:
                        await self._create_entity_from_proposal(item, domain_code, result)
                except ValueError as exc:
                    reason = str(exc)

            if reason:
                result["rejected"].append({"index": index, "name": label, "reason": reason})

        written = (
            result["inserted"] + result["updated_entities"] + result["properties_added"]
        )
        if written:
            await self._remap_waiting_review_tasks()
        result["total"] = result["inserted"] + result["updated_entities"]
        return result

    @staticmethod
    def _property_definitions(diff: list[dict[str, Any]]) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for prop in diff:
            key = canonical_property_key(prop.get("key"))
            if not key or key.casefold() in seen:
                continue
            seen.add(key.casefold())
            definitions.append(
                {
                    "key": key,
                    "name_cn": str(prop.get("name_cn") or key).strip(),
                    "value_type": DomainEntityService.normalize_value_type(
                        prop.get("value_type") or "String"
                    ),
                    "unit": "",
                    "description": "由 AI 提取补充",
                }
            )
        return definitions

    async def _append_properties_from_diff(
        self, item: dict[str, Any], result: dict[str, Any]
    ) -> None:
        entity_id = item.get("_entity_id")
        entity = await self.repo.get_by_id_or_key(entity_id) if entity_id else None
        if not entity:
            raise ValueError("目标实体不存在，可能已被删除，请重新提取")

        existing = {
            str(p.get("key")).casefold()
            for p in (entity.properties or [])
            if isinstance(p, dict) and p.get("key")
        }
        added = [
            prop
            for prop in self._property_definitions(
                (item.get("_diff") or {}).get("add_properties") or []
            )
            if prop["key"].casefold() not in existing
        ]
        if not added:
            result["unchanged"] += 1
            return

        await self.repo.update(
            entity.entity_id, {"properties": list(entity.properties or []) + added}
        )
        result["updated_entities"] += 1
        result["properties_added"] += len(added)

    async def _create_entity_from_proposal(
        self, item: dict[str, Any], domain_code: str, result: dict[str, Any]
    ) -> None:
        proposal = item.get("_proposed_entity") or {}
        problems = proposal.get("problems") or []
        if problems:
            raise ValueError(f"提案不可导入：{'；'.join(problems)}")

        entity_key = validate_key(proposal.get("entity_key"), "entity_key")
        if await self.repo.get_by_key(entity_key):
            raise ValueError(f"实体键 {entity_key} 已存在，请改为补属性后重试")

        name_cn = str(proposal.get("name_cn") or "").strip()
        if not name_cn:
            raise ValueError("提案缺少实体中文名")

        properties = self._property_definitions(proposal.get("properties") or [])
        await self.repo.create(
            {
                "entity_id": str(uuid.uuid4()),
                "entity_key": entity_key,
                "name_cn": name_cn,
                "category": proposal.get("category", ""),
                "domain_code": domain_code,
                "value_type": "String",
                "is_list_type": False,
                "description": "",
                "synonyms": [],
                "properties": properties,
                "relation_rules": [],
                "metadata": {
                    "source": "ai_extract",
                    "confidence": item.get("confidence", 0),
                    "extracted_at": format_utc_datetime(utc_now_naive()),
                },
            }
        )
        result["inserted"] += 1

    @staticmethod
    def _property_keys_of(entity: dict[str, Any]) -> set[str]:
        """已有实体已定义的属性键（兼容 list[dict] 与 dict 两种历史形态）。"""
        props = entity.get("properties")
        if isinstance(props, dict):
            keys = list(props.keys())
        elif isinstance(props, list):
            keys = [p.get("key") for p in props if isinstance(p, dict)]
        else:
            keys = []
        return {str(k).casefold() for k in keys if k}

    def _compare_extracted_with_entities(
        self,
        extracted: list[dict],
        existing_entities: list[dict],
        allowed_categories: set[str],
    ) -> list[dict]:
        """覆盖度比对：提取结果的属性键集合 vs 已有 schema 的属性键集合。

        matched  = 提取到的属性都已在 schema 中，无需写入
        partial  = 有 schema 未定义的新属性，建议补充
        new      = schema_ref 不在实体库（必须显式标注 __proposal__），建议建实体
        """
        existing_by_key: dict[str, dict] = {}
        for entity in existing_entities:
            key = str(entity.get("entity_key") or "")
            existing_by_key.setdefault(key, entity)

        comparison: list[dict] = []
        for item in extracted:
            schema_ref = str(item.get("schema_ref") or "").strip()
            values = item.get("values") if isinstance(item.get("values"), dict) else {}
            entry = {**item, "schema_ref": schema_ref, "values": values}
            existing = existing_by_key.get(schema_ref)

            if existing:
                defined = self._property_keys_of(existing)
                add_properties: list[dict[str, Any]] = []
                seen: set[str] = set()
                for raw_key, value in values.items():
                    key = canonical_property_key(raw_key)
                    if not key or key.casefold() in defined or key.casefold() in seen:
                        continue
                    seen.add(key.casefold())
                    add_properties.append(
                        {
                            "key": key,
                            "name_cn": str(raw_key).strip() or key,
                            "value_type": infer_value_type([value]),
                            "sample_value": value,
                        }
                    )
                entry.update(
                    {
                        "_status": "partial" if add_properties else "matched",
                        "_entity_id": existing.get("entity_id"),
                        "_diff": {"add_properties": add_properties},
                        "_existing": {
                            "entity_id": existing.get("entity_id"),
                            "entity_key": schema_ref,
                            "name_cn": existing.get("name_cn"),
                            "category": existing.get("category"),
                            "property_keys": sorted(defined),
                        },
                        "_proposed_entity": None,
                    }
                )
                comparison.append(entry)
                continue

            entry.update(
                {
                    "_status": "new",
                    "_entity_id": None,
                    "_diff": {"add_properties": []},
                    "_existing": None,
                    "_proposed_entity": self._build_entity_proposal(
                        item, schema_ref, values, allowed_categories
                    ),
                }
            )
            comparison.append(entry)

        return comparison

    @staticmethod
    def _build_entity_proposal(
        item: dict[str, Any],
        schema_ref: str,
        values: dict[str, Any],
        allowed_categories: set[str],
    ) -> dict[str, Any]:
        problems: list[str] = []
        if schema_ref not in ("", PROPOSAL_SCHEMA_REF):
            problems.append(
                f"schema_ref `{schema_ref}` 不在实体库中（疑似写错），新实体请用 `{PROPOSAL_SCHEMA_REF}`"
            )

        raw_key = str(item.get("entity_key") or "").strip()
        entity_key = re.sub(r"[^a-z0-9_]", "_", raw_key.lower()).strip("_")[:64]
        if not entity_key:
            problems.append("新实体提案缺少 entity_key（snake_case 英文）")

        category = str(item.get("category") or "").strip()
        if category not in allowed_categories:
            problems.append("category 不在分类字典中")

        properties = [
            {
                "key": canonical_property_key(raw_key),
                "name_cn": str(raw_key).strip(),
                "value_type": infer_value_type([value]),
                "sample_value": value,
            }
            for raw_key, value in values.items()
            if canonical_property_key(raw_key)
        ]
        if not properties:
            problems.append("提案没有任何属性")

        return {
            "entity_key": entity_key,
            "name_cn": str(item.get("name_cn") or "").strip(),
            "category": category,
            "properties": properties,
            "problems": problems,
        }

    def _build_extraction_prompt(
        self,
        schemas: list[dict[str, Any]],
        content: str,
        domain_code: str,
        categories: list[dict[str, Any]],
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
            negative_examples = ((s.get("metadata") or {}).get("negative_examples")) or []
            if negative_examples:
                lines.append(f"- 不计入本实体的内容: {'；'.join(map(str, negative_examples[:6]))}")
            if properties:
                lines.append("- 属性字段:")
                for p in properties[:10]:
                    pk = p.get("key", "")
                    pn = p.get("name_cn", "")
                    pt = p.get("value_type", "String")
                    pd = p.get("description", "")
                    hint = p.get("extraction_hint") or pd
                    mark = "（必填）" if p.get("required") else ""
                    lines.append(f"  - `{pk}` ({pn}){mark}: {pt} — {hint}")
            schema_desc_parts.append("\n".join(lines))

        schema_text = "\n\n".join(schema_desc_parts)

        domain_name = {"coal": "煤炭采掘", "chem": "石油化工", "transport": "交通运输"}.get(
            domain_code, domain_code
        )

        categories = "、".join(f"{item['code']}（{item['name_cn']}）" for item in categories)
        system_prompt = (
            "你是一个专业的领域实体提取助手。"
            "你的任务是从文档中识别符合预定义 Schema 的实体对象，并为 Schema 未覆盖的内容提出提案。"
            "提取规则：\n"
            "1. 实体对象是独立的概念，拥有自己的属性，能在知识图谱中建立关系\n"
            "2. 实体的属性（如名称、数值、状态等）不能独立成为实体\n"
            "3. 列表类型实体需提取文档中提到的每一个实例\n"
            "4. 只提取文档中明确提到的信息，不要推断；extracted_text 必须是原文片段，原文里没有的不要输出\n"
            "5. 以下内容不是实体：标准编号（如 GB 1234）、法规条款序号、纯数值与单位、表格表头、章节标题\n"
            "6. schema_ref 只能取上面列出的 entity_key；文档中出现了 Schema 未覆盖的实体时，"
            f"schema_ref 固定写 `{PROPOSAL_SCHEMA_REF}`，并在 entity_key 给出 snake_case 英文键\n"
            f"7. 提案的 category 只能取：{categories}\n"
            "8. values 的键优先使用 Schema 中已定义的属性 key；确需新增的用 snake_case 英文\n"
            "9. 严格按 JSON 格式输出，不要包含其他文字"
        )

        user_prompt = (
            f"## 行业领域: {domain_name}\n\n"
            f"## 实体Schema定义:\n\n{schema_text}\n\n"
            f"## 文档内容:\n\n{content[:12000]}\n\n"
            "## 输出要求:\n"
            "请以 JSON 数组格式返回结果，格式如下：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "schema_ref": "已有实体的 entity_key，或 __proposal__",\n'
            '    "entity_key": "仅提案时给出：snake_case 英文键",\n'
            '    "name_cn": "实体中文名",\n'
            '    "category": "所属分类（提案时必填，取分类字典之一）",\n'
            '    "confidence": 0.0-1.0,\n'
            '    "extracted_text": "文档中的原文片段（必须逐字摘录）",\n'
            '    "values": {\n'
            '      "属性key": "提取到的属性值"\n'
            "    }\n"
            "  }\n"
            "]\n"
            "```\n\n"
            "只返回 JSON 数组，不要有其他内容。"
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
