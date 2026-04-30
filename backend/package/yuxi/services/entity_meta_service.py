"""实体元数据服务：加载实体类型定义，增强 Schema 变量和插槽映射

功能：
1. EntityMetaLoader: 加载实体类型 JSON 文件
2. EntityMetaAdapter: 将实体类型转换为 Schema 变量格式
3. EntityMetaMatcher: 根据段落内容匹配相关实体
4. SlotEntityMapper: 将泛化插槽映射到实体属性
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from yuxi.utils.logging_config import logger

# 默认实体类型文件路径
ENTITY_TYPES_DIR = Path(__file__).parent.parent.parent.parent / "server"


class EntityMetaLoader:
    """实体元数据加载器，带缓存"""

    def __init__(self, entity_types_path: Path | None = None):
        self.entity_types_path = entity_types_path or ENTITY_TYPES_DIR / "coal_eia_entity_types.json"
        self._cache: dict[str, dict[str, Any]] | None = None

    def load(self) -> dict[str, dict[str, Any]]:
        """加载实体类型定义，返回 {entity_id: entity_data}"""
        if self._cache is not None:
            return self._cache

        if not self.entity_types_path.exists():
            logger.warning(f"实体类型文件不存在: {self.entity_types_path}")
            self._cache = {}
            return self._cache

        try:
            with open(self.entity_types_path, encoding="utf-8-sig") as f:
                data = json.load(f)

            if isinstance(data, dict):
                self._cache = data
            elif isinstance(data, list):
                self._cache = {e.get("id", str(i)): e for i, e in enumerate(data)}
            else:
                self._cache = {}

            logger.info(f"加载了 {len(self._cache)} 个实体类型定义")
            return self._cache
        except Exception as e:
            logger.error(f"加载实体类型文件失败: {e}")
            self._cache = {}
            return self._cache

    def get_entities_by_category(self, category: str) -> list[dict[str, Any]]:
        """按分类获取实体列表"""
        return [e for e in self.load().values() if e.get("category") == category]

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """按 ID 获取实体"""
        return self.load().get(entity_id)

    def get_all_categories(self) -> list[str]:
        """获取所有分类"""
        seen = set()
        result = []
        for e in self.load().values():
            cat = e.get("category", "")
            if cat and cat not in seen:
                seen.add(cat)
                result.append(cat)
        return result

    def clear_cache(self) -> None:
        self._cache = None


class EntityMetaAdapter:
    """将实体类型转换为 Schema 变量格式，增强现有的 Schema"""

    def enhance_schema_variables(self, variables: list[dict], entities: dict[str, dict]) -> list[dict]:
        """用实体定义增强 Schema 变量列表

        为变量补充 extraction_hint、unit、entity_ref 等字段，
        并将缺少的实体属性作为新变量追加。
        """
        if not entities:
            return variables

        # 建立已有变量的 key 集合
        existing_keys = {v.get("key", "") for v in variables}

        # 建立实体关键词 → entity_id 的映射，用于变量匹配
        keyword_to_entity = self._build_keyword_map(entities)

        # 增强：为已有变量补充实体信息
        enhanced = []
        for var in variables:
            ev = dict(var)
            key = var.get("key", "")
            matched_entity = self._find_matching_entity(key, keyword_to_entity, entities)

            if matched_entity:
                # 补充 extraction_hint
                if not ev.get("prompt") and matched_entity.get("description"):
                    ev["prompt"] = matched_entity["description"]
                # 标记实体来源
                ev["_entity_id"] = matched_entity["id"]
                ev["_entity_category"] = matched_entity.get("category", "")

            enhanced.append(ev)

        # 追加：实体中有但 Schema 中没有的关键属性
        for entity_id, entity in entities.items():
            entity_keywords = entity.get("keywords", [])
            entity_name = entity.get("name", "")
            # 只追加分类级别的变量（不逐个追加 examples）
            if entity_id not in existing_keys and entity_name not in existing_keys:
                enhanced.append(
                    {
                        "key": entity_id,
                        "label": entity_name,
                        "data_type": "string",
                        "widget": "Input",
                        "unit": "",
                        "group": entity.get("category", "基础信息"),
                        "required": False,
                        "prompt": entity.get("description", ""),
                        "source": "entity_meta",
                        "sample": ", ".join(entity.get("examples", [])[:3]),
                        "_entity_id": entity_id,
                        "_entity_category": entity.get("category", ""),
                    }
                )

        return enhanced

    def _build_keyword_map(self, entities: dict[str, dict]) -> dict[str, str]:
        """构建关键词 → entity_id 的映射"""
        mapping: dict[str, str] = {}
        for eid, entity in entities.items():
            for kw in entity.get("keywords", []):
                mapping[kw] = eid
            for ex in entity.get("examples", []):
                mapping[ex] = eid
        return mapping

    def _find_matching_entity(
        self, var_key: str, keyword_map: dict[str, str], entities: dict[str, dict]
    ) -> dict[str, Any] | None:
        """根据变量 key 查找匹配的实体"""
        key_lower = var_key.lower()

        # 直接匹配 entity_id
        if key_lower in entities:
            return entities[key_lower]

        # 关键词匹配
        if key_lower in keyword_map:
            return entities.get(keyword_map[key_lower])

        # 部分匹配
        for eid, entity in entities.items():
            for kw in entity.get("keywords", []):
                if kw in var_key or var_key in kw:
                    return entity

        return None


class EntityMetaMatcher:
    """根据段落内容匹配相关实体"""

    def __init__(self, loader: EntityMetaLoader | None = None):
        self.loader = loader or EntityMetaLoader()

    def match_paragraph(self, title: str, content: str) -> list[dict[str, Any]]:
        """匹配段落标题和内容中出现的实体

        返回匹配到的实体列表，按匹配度排序。
        """
        entities = self.loader.load()
        if not entities:
            return []

        text = f"{title} {content}"
        results: list[tuple[float, dict[str, Any]]] = []

        for eid, entity in entities.items():
            score = self._calc_match_score(text, entity)
            if score > 0:
                results.append((score, entity))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results]

    def _calc_match_score(self, text: str, entity: dict[str, Any]) -> float:
        """计算实体与文本的匹配度"""
        score = 0.0
        name = entity.get("name", "")

        # 名称精确匹配
        if name and name in text:
            score += 1.0
        # 关键词匹配
        for kw in entity.get("keywords", []):
            if kw in text:
                score += 0.5
        # 示例匹配
        for ex in entity.get("examples", []):
            if ex in text:
                score += 0.3

        return score


class SlotEntityMapper:
    """将泛化结果中的插槽映射到实体属性"""

    def __init__(self, loader: EntityMetaLoader | None = None):
        self.loader = loader or EntityMetaLoader()
        self._matcher = EntityMetaMatcher(self.loader)

    def map_slots(self, slots: list[dict[str, Any]], paragraph_context: str = "") -> list[dict[str, Any]]:
        """为插槽补充 entity_ref 信息

        当插槽名称匹配到实体关键词时，自动添加 entity_ref 字段。
        """
        entities = self.loader.load()
        if not entities:
            return slots

        keyword_to_entity = self._build_slot_keyword_map(entities)

        mapped = []
        for slot in slots:
            s = dict(slot)
            slot_name = slot.get("name", "")

            # 已有 entity_ref 的跳过
            if s.get("entity_ref"):
                mapped.append(s)
                continue

            # 尝试匹配
            entity_id = keyword_to_entity.get(slot_name)
            if not entity_id:
                # 模糊匹配
                for kw, eid in keyword_to_entity.items():
                    if kw in slot_name or slot_name in kw:
                        entity_id = eid
                        break

            if entity_id and entity_id in entities:
                s["entity_ref"] = entity_id

            mapped.append(s)

        return mapped

    def _build_slot_keyword_map(self, entities: dict[str, dict]) -> dict[str, str]:
        """构建插槽关键词 → entity_id 的映射"""
        mapping: dict[str, str] = {}
        for eid, entity in entities.items():
            mapping[eid] = eid
            mapping[entity.get("name", "")] = eid
            for kw in entity.get("keywords", []):
                mapping[kw] = eid
            for ex in entity.get("examples", []):
                mapping[ex] = eid
        return mapping
