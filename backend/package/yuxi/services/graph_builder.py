"""知识图谱构建服务：将领域工厂结构化数据写入 Neo4j 图谱

写作模具库架构（只存"形"，不存"神"）：

核心节点：
- Document：文档样例（根节点）
- Section：原始章节（骨架，记录真实章节层级）
- ParagraphTemplate：段落模板（模具，泛化后的文本）
- Slot：插槽（变量，模板里的挖孔）

关系设计：
- Document -[HAS_SECTION]-> Section
- Section -[HAS_CHILD]-> Section
- Section -[NEXT_SECTION]-> Section
- Section -[COMPOSED_OF {order}]-> ParagraphTemplate
- ParagraphTemplate -[HAS_SLOT]-> Slot
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from neo4j import GraphDatabase as Neo4jDriver

from yuxi.utils import hashstr, logger


class GraphBuilder:
    """将领域工厂结构化数据构建为知识图谱"""

    def __init__(self):
        self._driver: Neo4jDriver | None = None

    def _get_driver(self) -> Neo4jDriver | None:
        """获取或创建 Neo4j 驱动"""
        if self._driver is not None:
            return self._driver

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "0123456789")

        try:
            self._driver = Neo4jDriver.driver(uri, auth=(username, password))
            with self._driver.session() as session:
                session.run("RETURN 1")
            logger.info("GraphBuilder: Neo4j 连接成功")
            return self._driver
        except Exception as e:
            logger.warning(f"GraphBuilder: Neo4j 连接失败，图谱构建将不可用: {e}")
            return None

    def build_knowledge_graph(
        self,
        kb_id: str,
        doc_id: str,
        doc_title: str,
        source_paragraphs: list[dict[str, Any]],
        domain_label: str | None = None,
        base_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构建知识图谱

        Args:
            kb_id: 知识库ID，用于图谱数据隔离
            doc_id: 文档唯一标识符
            doc_title: 文档标题
            source_paragraphs: 源段落列表
            domain_label: 领域标签
            base_info: 基础信息字典

        Returns:
            构建结果统计
        """
        driver = self._get_driver()
        if not driver:
            logger.warning("Neo4j 未连接，跳过图谱构建")
            return {"nodes_created": 0, "relationships_created": 0, "skipped": True}

        stats = {"nodes_created": 0, "relationships_created": 0, "skipped": False}

        try:
            with driver.session() as session:
                # 步骤1: 创建 Document 节点
                doc_result = session.execute_write(self._create_document_node, kb_id, doc_id, doc_title, domain_label)
                stats["nodes_created"] += doc_result.get("nodes", 0)
                stats["relationships_created"] += doc_result.get("relationships", 0)

                # 步骤2: 构建 Section、ParagraphTemplate、Slot 节点和关系
                structure_result = session.execute_write(
                    self._build_sections_and_templates, kb_id, doc_id, source_paragraphs
                )
                stats["nodes_created"] += structure_result.get("nodes", 0)
                stats["relationships_created"] += structure_result.get("relationships", 0)

                # 步骤3: 构建 EntitySchema 节点，将 Slot 的 entity_ref 关联到实体定义
                entity_result = session.execute_write(self._build_entity_schema_nodes, kb_id, source_paragraphs)
                stats["nodes_created"] += entity_result.get("nodes", 0)
                stats["relationships_created"] += entity_result.get("relationships", 0)

                # 步骤3: 构建 EntitySchema 节点，将 Slot 的 entity_ref 关联到实体定义
                entity_result = session.execute_write(self._build_entity_schema_nodes, kb_id, source_paragraphs)
                stats["nodes_created"] += entity_result.get("nodes", 0)
                stats["relationships_created"] += entity_result.get("relationships", 0)

                logger.info(
                    f"图谱构建完成: 文档 {doc_id}, 节点 {stats['nodes_created']}, 关系 {stats['relationships_created']}"
                )
                return stats

        except Exception as exc:
            logger.error(f"构建知识图谱失败: {exc}", exc_info=True)
            return {"nodes_created": 0, "relationships_created": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # 步骤1: Document 节点
    # ------------------------------------------------------------------

    @staticmethod
    def _create_document_node(tx, kb_id, doc_id, doc_title, domain_label) -> dict:
        tx.run(
            """
            MERGE (d:Document {id: $doc_id})
            ON CREATE SET
                d.id = $doc_id,
                d.filename = $doc_title,
                d.title = $doc_title,
                d.domain = $domain_label,
                d.kb_id = $kb_id,
                d.score = 5,
                d.created_at = datetime()
            ON MATCH SET
                d.filename = COALESCE($doc_title, d.filename),
                d.title = COALESCE($doc_title, d.title),
                d.domain = COALESCE($domain_label, d.domain),
                d.kb_id = COALESCE($kb_id, d.kb_id)
            """,
            kb_id=kb_id,
            doc_id=doc_id,
            doc_title=doc_title,
            domain_label=domain_label or "",
        )
        return {"nodes": 1, "relationships": 0}

    # ------------------------------------------------------------------
    # 步骤2: Section / ParagraphTemplate / Slot 节点和关系
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sections_and_templates(tx, kb_id: str, doc_id: str, source_paragraphs: list[dict[str, Any]]) -> dict:
        nodes_created = 0
        relationships_created = 0

        created_sections: dict[str, bool] = {}
        created_templates: dict[str, bool] = {}
        section_map: dict[str, dict[str, Any]] = {}
        section_order_map: dict[str, list[str]] = {}
        section_template_order: dict[str, int] = {}

        # 第一遍：创建 Section 节点（从标题段落）
        for para in source_paragraphs:
            chunk_id = para.get("id") or ""
            content = para.get("content") or ""
            section_path = para.get("section_path") or para.get("path") or []
            is_title = para.get("is_title", False)
            title = para.get("title", "")

            if not chunk_id and not title:
                continue

            # 根据是否有 section_path 判断是否创建 Section
            if isinstance(section_path, list) and len(section_path) > 0:
                section_path_str = "/".join(str(p) for p in section_path)
                level = len(section_path)
            else:
                continue

            # 段落标题或 is_title 标记的段落作为 Section 节点
            section_title = title or (content[:500] if is_title else "")
            if not section_title:
                continue

            section_id = _generate_section_id(section_path, doc_id)
            if section_id in created_sections:
                continue

            parent_path_str = "/".join(str(p) for p in section_path[:-1]) if len(section_path) > 1 else "0"

            tx.run(
                """
                MERGE (s:Section {id: $section_id})
                ON CREATE SET
                    s.id = $section_id,
                    s.title = $title,
                    s.level = $level,
                    s.section_path = $section_path,
                    s.section_path_str = $section_path_str,
                    s.kb_id = $kb_id,
                    s.created_at = datetime()
                ON MATCH SET
                    s.title = COALESCE($title, s.title),
                    s.level = COALESCE($level, s.level)
                """,
                section_id=section_id,
                title=section_title,
                level=level,
                section_path=json.dumps(section_path, ensure_ascii=False),
                section_path_str=section_path_str,
                kb_id=kb_id,
            )
            nodes_created += 1
            created_sections[section_id] = True

            # Document -[HAS_SECTION]-> Section
            tx.run(
                """
                MATCH (d:Document {id: $doc_id})
                MATCH (s:Section {id: $section_id})
                MERGE (d)-[:HAS_SECTION]->(s)
                """,
                doc_id=doc_id,
                section_id=section_id,
            )
            relationships_created += 1

            section_map[section_path_str] = {
                "section_id": section_id,
                "level": level,
                "parent_path": parent_path_str,
            }

            if parent_path_str not in section_order_map:
                section_order_map[parent_path_str] = []
            section_order_map[parent_path_str].append(section_id)

        # 第二遍：创建 ParagraphTemplate 和 Slot 节点
        for para in source_paragraphs:
            chunk_id = para.get("id") or ""
            content = para.get("content") or ""
            section_path = para.get("section_path") or para.get("path") or []
            title = para.get("title", "")

            if not content:
                continue

            template_data = _normalize_template_data(para.get("template"))
            if not template_data:
                continue

            # 确定当前段落所属的 Section
            target_section_id = _find_target_section(section_path, section_map)
            if not target_section_id:
                continue

            # 创建 ParagraphTemplate 节点
            generalized = template_data.get("generalized") or template_data.get("generalized_pattern") or ""
            if not generalized:
                continue

            template_id = _generate_template_id(template_data, chunk_id)
            template_hash = hashstr(generalized, 12)

            if template_id not in created_templates:
                tx.run(
                    """
                    MERGE (pt:ParagraphTemplate {id: $template_id})
                    ON CREATE SET
                        pt.id = $template_id,
                        pt.text_pattern = $text_pattern,
                        pt.generalized_pattern = $generalized_pattern,
                        pt.hash = $hash,
                        pt.kb_id = $kb_id,
                        pt.created_at = datetime()
                    ON MATCH SET
                        pt.text_pattern = COALESCE($text_pattern, pt.text_pattern),
                        pt.generalized_pattern = COALESCE($generalized_pattern, pt.generalized_pattern)
                    """,
                    template_id=template_id,
                    text_pattern=generalized,
                    generalized_pattern=generalized,
                    hash=template_hash,
                    kb_id=kb_id,
                )
                nodes_created += 1
                created_templates[template_id] = True

                # Section -[COMPOSED_OF {order}]-> ParagraphTemplate
                if target_section_id not in section_template_order:
                    section_template_order[target_section_id] = 0
                order = section_template_order[target_section_id] + 1
                section_template_order[target_section_id] = order

                tx.run(
                    """
                    MATCH (s:Section {id: $section_id})
                    MATCH (pt:ParagraphTemplate {id: $template_id})
                    MERGE (s)-[r:COMPOSED_OF]->(pt)
                    ON CREATE SET r.order = $order
                    ON MATCH SET r.order = COALESCE($order, r.order)
                    """,
                    section_id=target_section_id,
                    template_id=template_id,
                    order=order,
                )
                relationships_created += 1

                # 创建 Slot 节点
                slots = template_data.get("slots", [])
                if isinstance(slots, list):
                    slot_stats = _create_slots_and_relationships(tx, template_id, slots, kb_id)
                    nodes_created += slot_stats["nodes"]
                    relationships_created += slot_stats["relationships"]

        # 第三遍：建立 Section 层级关系
        for parent_path_str, child_section_ids in section_order_map.items():
            if len(child_section_ids) < 1:
                continue

            # HAS_CHILD 关系
            if parent_path_str in section_map:
                parent_section_id = section_map[parent_path_str]["section_id"]
                for child_section_id in child_section_ids:
                    tx.run(
                        """
                        MATCH (parent:Section {id: $parent_id})
                        MATCH (child:Section {id: $child_id})
                        MERGE (parent)-[:HAS_CHILD]->(child)
                        """,
                        parent_id=parent_section_id,
                        child_id=child_section_id,
                    )
                    relationships_created += 1

            # NEXT_SECTION 关系（同级章节顺序）
            for i in range(len(child_section_ids) - 1):
                tx.run(
                    """
                    MATCH (prev:Section {id: $prev_id})
                    MATCH (next:Section {id: $next_id})
                    MERGE (prev)-[:NEXT_SECTION]->(next)
                    """,
                    prev_id=child_section_ids[i],
                    next_id=child_section_ids[i + 1],
                )
                relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤3: EntitySchema 节点（Slot → EntitySchema 约束关系）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_entity_schema_nodes(tx, kb_id: str, source_paragraphs: list[dict[str, Any]]) -> dict:
        """为具有 entity_ref 的 Slot 创建 EntitySchema 节点并建立约束关系

        扫描所有段落的模板插槽，如果插槽包含 entity_ref，
        则：
        1. 创建或合并 EntitySchema 节点（基于 entity_ref）
        2. 建立 Slot -[CONSTRAINS]-> EntitySchema 关系
        """
        from yuxi.services.entity_meta_service import EntityMetaLoader

        nodes_created = 0
        relationships_created = 0
        created_entities: dict[str, bool] = {}

        # 加载实体定义获取名称和分类
        loader = EntityMetaLoader()
        entity_meta = loader.load()

        for para in source_paragraphs:
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue

            slots = template.get("slots", [])
            if not isinstance(slots, list):
                continue

            for slot in slots:
                if not isinstance(slot, dict):
                    continue

                entity_ref = slot.get("entity_ref", "")
                if not entity_ref:
                    continue

                slot_name = slot.get("name", "")
                slot_id = _generate_slot_id(slot_name)
                entity_id = f"entity_{entity_ref}"

                # 创建 EntitySchema 节点（幂等）
                if entity_id not in created_entities:
                    entity_info = entity_meta.get(entity_ref, {})
                    entity_name = entity_info.get("name", entity_ref)
                    entity_category = entity_info.get("category", "")
                    entity_desc = entity_info.get("description", "")

                    tx.run(
                        """
                        MERGE (e:EntitySchema {id: $entity_id})
                        ON CREATE SET
                            e.id = $entity_id,
                            e.entity_key = $entity_ref,
                            e.name = $entity_name,
                            e.category = $entity_category,
                            e.description = $entity_desc,
                            e.kb_id = $kb_id,
                            e.created_at = datetime()
                        ON MATCH SET
                            e.name = COALESCE($entity_name, e.name),
                            e.category = COALESCE($entity_category, e.category),
                            e.description = COALESCE($entity_desc, e.description)
                        """,
                        entity_id=entity_id,
                        entity_ref=entity_ref,
                        entity_name=entity_name,
                        entity_category=entity_category,
                        entity_desc=entity_desc,
                        kb_id=kb_id,
                    )
                    nodes_created += 1
                    created_entities[entity_id] = True

                # Slot -[CONSTRAINS]-> EntitySchema
                tx.run(
                    """
                    MATCH (s:Slot {id: $slot_id})
                    MATCH (e:EntitySchema {id: $entity_id})
                    MERGE (s)-[:CONSTRAINS]->(e)
                    """,
                    slot_id=slot_id,
                    entity_id=entity_id,
                )
                relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    def close(self):
        """关闭 Neo4j 连接"""
        if self._driver:
            self._driver.close()
            self._driver = None


# ======================================================================
# 模块级辅助函数
# ======================================================================


def _generate_section_id(section_path: list, doc_id: str) -> str:
    """生成 Section 节点的唯一 ID"""
    if not section_path:
        return f"sec_{doc_id}_root"
    path_str = "/".join(str(p) for p in section_path)
    path_hash = hashstr(f"{doc_id}_{path_str}", 12)
    return f"sec_{doc_id}_{path_hash}"


def _generate_template_id(template_data: dict, chunk_id: str) -> str:
    """自动生成模板 ID（基于内容哈希，支持去重）"""
    existing_id = template_data.get("template_id")
    if existing_id:
        return existing_id

    generalized = template_data.get("generalized") or template_data.get("generalized_pattern") or ""
    slots = template_data.get("slots") or []
    slot_names = [s.get("name", "") for s in slots if isinstance(s, dict)]
    combined = f"{generalized}|{','.join(sorted(slot_names))}"
    hash_value = hashstr(combined, 12)
    return f"TPL_PARA_{hash_value}"


def _generate_slot_id(slot_name: str) -> str:
    """生成插槽的全局唯一标识符"""
    if not slot_name:
        return f"SLOT_UNKNOWN_{hashstr(str(uuid.uuid4()), 8)}"
    slot_name_upper = slot_name.upper().replace("-", "_").replace(" ", "_")
    return f"SLOT_{slot_name_upper}"


def _normalize_template_data(template_raw: Any) -> dict:
    """规范化 template 数据，确保返回字典"""
    if template_raw is None:
        return {}
    if isinstance(template_raw, dict):
        normalized = template_raw.copy()
        slots = normalized.get("slots")
        if isinstance(slots, str):
            try:
                normalized["slots"] = json.loads(slots)
            except (json.JSONDecodeError, TypeError):
                normalized["slots"] = []
        elif slots is None:
            normalized["slots"] = []
        return normalized
    if isinstance(template_raw, str):
        try:
            parsed = json.loads(template_raw) if template_raw else {}
            return _normalize_template_data(parsed)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _find_target_section(section_path: list, section_map: dict) -> str | None:
    """根据 section_path 向上查找最近的 Section ID"""
    if not section_path:
        return None

    # 精确匹配
    section_path_str = "/".join(str(p) for p in section_path)
    if section_path_str in section_map:
        return section_map[section_path_str]["section_id"]

    # 向上查找父级
    for i in range(len(section_path) - 1, 0, -1):
        parent_path = section_path[:i]
        parent_path_str = "/".join(str(p) for p in parent_path)
        if parent_path_str in section_map:
            return section_map[parent_path_str]["section_id"]

    return None


def _create_slots_and_relationships(tx, template_id: str, slots: list[dict], kb_id: str) -> dict:
    """创建 Slot 节点并建立关系

    如果插槽包含 entity_ref 字段（由 SlotEntityMapper 注入），
    会将实体引用写入 Slot 节点属性，方便图谱遍历查询。
    """
    nodes_created = 0
    relationships_created = 0

    for position, slot in enumerate(slots):
        slot_name = slot.get("name", "")
        if not slot_name:
            continue

        slot_id = _generate_slot_id(slot_name)
        description = slot.get("description", "")
        slot_type = slot.get("type", "string")
        required = slot.get("required", False)
        entity_ref = slot.get("entity_ref", "")

        # Slot 节点（含 entity_ref 实体引用）
        tx.run(
            """
            MERGE (s:Slot {id: $slot_id})
            ON CREATE SET
                s.id = $slot_id,
                s.name = $slot_name,
                s.description = $description,
                s.type = $slot_type,
                s.required = $required,
                s.entity_ref = $entity_ref,
                s.kb_id = $kb_id,
                s.created_at = datetime()
            ON MATCH SET
                s.description = COALESCE($description, s.description),
                s.type = COALESCE($slot_type, s.type),
                s.required = COALESCE($required, s.required),
                s.entity_ref = COALESCE($entity_ref, s.entity_ref)
            """,
            slot_id=slot_id,
            slot_name=slot_name,
            description=description,
            slot_type=slot_type,
            required=required,
            entity_ref=entity_ref,
            kb_id=kb_id,
        )
        nodes_created += 1

        # ParagraphTemplate -[HAS_SLOT]-> Slot
        tx.run(
            """
            MATCH (pt:ParagraphTemplate {id: $template_id})
            MATCH (s:Slot {id: $slot_id})
            MERGE (pt)-[r:HAS_SLOT]->(s)
            ON CREATE SET r.position = $position, r.is_required = $required
            ON MATCH SET r.position = COALESCE($position, r.position)
            """,
            template_id=template_id,
            slot_id=slot_id,
            position=position,
            required=required,
        )
        relationships_created += 1

    return {"nodes": nodes_created, "relationships": relationships_created}
