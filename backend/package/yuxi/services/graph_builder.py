"""知识图谱构建服务：将领域工厂结构化数据写入 Neo4j 图谱

写作模具库架构（只存"形"，不存"神"）：

核心节点：
- Document：文档样例（根节点）
- Section：原始章节（骨架，记录真实章节层级）
- ParagraphTemplate：段落模板（模具，泛化后的文本，含 classify_type）
- Slot：插槽（变量，模板里的挖孔）
- LegalReference：法律/法规/标准引用
- EntitySchema：实体定义
- DomainOutline：领域骨架模板（按 domain × report_type 聚合）
- ChapterTemplate：章节模板（跨文档聚合，含 rigidity/frequency）
- ParagraphRole：段落角色（章节内的固定叙述顺序）

关系设计：
- Document -[HAS_SECTION]-> Section
- Document -[CONTRIBUTES_TO]-> DomainOutline
- Section -[HAS_CHILD]-> Section
- Section -[NEXT_SECTION]-> Section
- Section -[COMPOSED_OF {order}]-> ParagraphTemplate
- DomainOutline -[HAS_CHAPTER]-> ChapterTemplate
- ChapterTemplate -[REQUIRES_PARAGRAPH_ROLE {order}]-> ParagraphRole
- ParagraphRole -[REALIZED_BY {confidence, frequency}]-> ParagraphTemplate
- ChapterTemplate -[APPLIES_STANDARD {usage}]-> LegalReference
- ParagraphTemplate -[HAS_SLOT]-> Slot
- ParagraphTemplate -[CITES]-> LegalReference
- Slot -[CONSTRAINS]-> EntitySchema
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from neo4j import GraphDatabase as Neo4jDriver

from yuxi.utils import hashstr, logger


def _derive_canonical_key(title: str) -> str:
    """从章节标题推导 canonical_chapter_key:去所有前导编号,只留纯标题。纯编号返回空。"""
    text = (title or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)*", text):
        return ""
    while True:
        m = re.match(r"^(\d+(?:\.\d+)*)\s*(\S.*)$", text)
        if not m:
            break
        text = m.group(2).strip()
    return text


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
        domain_code: str | None = None,
        report_type_code: str | None = None,
    ) -> dict[str, Any]:
        """构建知识图谱

        Args:
            kb_id: 知识库ID，用于图谱数据隔离
            doc_id: 文档唯一标识符
            doc_title: 文档标题
            source_paragraphs: 源段落列表
            domain_label: 领域标签
            base_info: 基础信息字典
            domain_code: 领域编码（如 coal、chem）
            report_type_code: 报告类型编码（如 eia_report）

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
                doc_result = session.execute_write(
                    self._create_document_node, kb_id, doc_id, doc_title,
                    domain_label, domain_code, report_type_code,
                )
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

                # 步骤4: 构建 LegalReference 节点
                legal_result = session.execute_write(self._build_legal_reference_nodes, kb_id, source_paragraphs)
                stats["nodes_created"] += legal_result.get("nodes", 0)
                stats["relationships_created"] += legal_result.get("relationships", 0)

                # 步骤5: 构建 TableSchema 节点
                table_result = session.execute_write(self._build_table_schema_nodes, kb_id, source_paragraphs)
                stats["nodes_created"] += table_result.get("nodes", 0)
                stats["relationships_created"] += table_result.get("relationships", 0)

                # 步骤6: 构建 FormulaTemplate 节点
                formula_result = session.execute_write(self._build_formula_template_nodes, kb_id, source_paragraphs)
                stats["nodes_created"] += formula_result.get("nodes", 0)
                stats["relationships_created"] += formula_result.get("relationships", 0)

                # 步骤7: 构建 ProcessFlow 节点（图片多模态提取结果）
                flow_result = session.execute_write(self._build_process_flow_nodes, kb_id, source_paragraphs)
                stats["nodes_created"] += flow_result.get("nodes", 0)
                stats["relationships_created"] += flow_result.get("relationships", 0)

                # 步骤8: 骨架聚合（DomainOutline / ChapterTemplate）
                if domain_code and report_type_code:
                    skeleton_result = session.execute_write(
                        self._build_skeleton_aggregation,
                        kb_id, domain_code, report_type_code, doc_id, doc_title, source_paragraphs,
                    )
                    stats["nodes_created"] += skeleton_result.get("nodes", 0)
                    stats["relationships_created"] += skeleton_result.get("relationships", 0)

                # 步骤9: 逻辑关系节点（CausalChain / ConditionRule / DataFlow）
                # 从 task 的 logical_relations 字段读取（由 ETL pipeline 提取后传入）
                logical_result = session.execute_write(
                    self._build_logical_relationship_nodes, kb_id, source_paragraphs, base_info or {},
                )
                stats["nodes_created"] += logical_result.get("nodes", 0)
                stats["relationships_created"] += logical_result.get("relationships", 0)

                logger.info(
                    f"图谱构建完成: 文档 {doc_id}, 节点 {stats['nodes_created']}, 关系 {stats['relationships_created']}"
                )
                return stats

        except Exception as exc:
            logger.error("构建知识图谱失败: {}", exc, exc_info=True)
            return {"nodes_created": 0, "relationships_created": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # 步骤1: Document 节点
    # ------------------------------------------------------------------

    @staticmethod
    def _create_document_node(tx, kb_id, doc_id, doc_title, domain_label, domain_code=None, report_type_code=None) -> dict:
        tx.run(
            """
            MERGE (d:Document {id: $doc_id})
            ON CREATE SET
                d.id = $doc_id,
                d.filename = $doc_title,
                d.title = $doc_title,
                d.domain = $domain_label,
                d.domain_code = $domain_code,
                d.report_type_code = $report_type_code,
                d.kb_id = $kb_id,
                d.score = 5,
                d.created_at = datetime()
            ON MATCH SET
                d.filename = COALESCE($doc_title, d.filename),
                d.title = COALESCE($doc_title, d.title),
                d.domain = COALESCE($domain_label, d.domain),
                d.domain_code = COALESCE($domain_code, d.domain_code),
                d.report_type_code = COALESCE($report_type_code, d.report_type_code),
                d.kb_id = COALESCE($kb_id, d.kb_id)
            """,
            kb_id=kb_id,
            doc_id=doc_id,
            doc_title=doc_title,
            domain_label=domain_label or "",
            domain_code=domain_code or "",
            report_type_code=report_type_code or "",
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
        # 构建 section_path_str → 标题 映射(用于回填 ParagraphTemplate.canonical_chapter_key)
        section_title_map: dict[str, str] = {}
        for para in source_paragraphs:
            if not para.get("is_title"):
                continue
            sp = para.get("section_path") or para.get("path") or []
            if not sp:
                continue
            sp_str = "/".join(str(p) for p in sp)
            section_title_map[sp_str] = para.get("title", "")

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

            # 推导所属章节的 canonical_chapter_key(从 section_path 反查最近标题)
            para_canonical_key = ""
            sp_list = section_path if isinstance(section_path, list) else []
            for i in range(len(sp_list), 0, -1):
                parent_sp_str = "/".join(str(p) for p in sp_list[:i])
                if parent_sp_str in section_title_map:
                    para_canonical_key = _derive_canonical_key(section_title_map[parent_sp_str])
                    break

            # 创建 ParagraphTemplate 节点
            generalized = template_data.get("generalized") or template_data.get("generalized_pattern") or ""
            if not generalized:
                continue

            template_id = _generate_template_id(template_data, chunk_id)
            template_hash = hashstr(generalized, 12)

            if template_id not in created_templates:
                classify_type = para.get("classify_type", "")
                tx.run(
                    """
                    MERGE (pt:ParagraphTemplate {id: $template_id})
                    ON CREATE SET
                        pt.id = $template_id,
                        pt.text_pattern = $text_pattern,
                        pt.generalized_pattern = $generalized_pattern,
                        pt.canonical_chapter_key = $canonical_key,
                        pt.hash = $hash,
                        pt.classify_type = $classify_type,
                        pt.kb_id = $kb_id,
                        pt.created_at = datetime()
                    ON MATCH SET
                        pt.text_pattern = COALESCE($text_pattern, pt.text_pattern),
                        pt.generalized_pattern = COALESCE($generalized_pattern, pt.generalized_pattern),
                        pt.classify_type = COALESCE($classify_type, pt.classify_type),
                        pt.canonical_chapter_key = COALESCE(pt.canonical_chapter_key, $canonical_key)
                    """,
                    template_id=template_id,
                    text_pattern=generalized,
                    generalized_pattern=generalized,
                    canonical_key=para_canonical_key,
                    hash=template_hash,
                    classify_type=classify_type,
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

    # ------------------------------------------------------------------
    # 步骤4: LegalReference 节点（法律/法规/标准引用）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_legal_reference_nodes(tx, kb_id: str, source_paragraphs: list[dict[str, Any]]) -> dict:
        """为 legal_reference 段落中的法律引用创建 LegalReference 节点

        并建立 ParagraphTemplate -[CITES]-> LegalReference 关系。
        """
        nodes_created = 0
        relationships_created = 0
        created_refs: dict[str, bool] = {}

        for para in source_paragraphs:
            if para.get("classify_type") != "legal_reference":
                continue

            template = para.get("template", {})
            if not isinstance(template, dict):
                continue

            legal_refs = template.get("legal_references", [])
            if not isinstance(legal_refs, list):
                continue

            para_id = para.get("id", "")

            for ref in legal_refs:
                if not isinstance(ref, dict):
                    continue

                ref_name = ref.get("name", "")
                ref_code = ref.get("code", "")
                if not ref_name:
                    continue

                # 生成唯一 ID：基于 name + code
                ref_key = f"{ref_name}_{ref_code}" if ref_code else ref_name
                ref_id = f"LEGAL_{hashstr(ref_key, 12)}"

                ref_type = ref.get("type", "technical_standard")
                scope = ref.get("scope", "national")
                authority = ref.get("authority", "")

                if ref_id not in created_refs:
                    effective_date = ref.get("effective_date", "")
                    tx.run(
                        """
                        MERGE (lr:LegalReference {id: $ref_id})
                        ON CREATE SET
                            lr.id = $ref_id,
                            lr.name = $name,
                            lr.code = $code,
                            lr.type = $type,
                            lr.scope = $scope,
                            lr.authority = $authority,
                            lr.effective_date = $effective_date,
                            lr.status = 'effective',
                            lr.superseded_by = null,
                            lr.kb_id = $kb_id,
                            lr.frequency = 1,
                            lr.created_at = datetime()
                        ON MATCH SET
                            lr.name = COALESCE($name, lr.name),
                            lr.code = COALESCE($code, lr.code),
                            lr.type = COALESCE($type, lr.type),
                            lr.scope = COALESCE($scope, lr.scope),
                            lr.authority = COALESCE($authority, lr.authority),
                            lr.effective_date = COALESCE($effective_date, lr.effective_date),
                            lr.frequency = lr.frequency + 1
                        // 时效性检测：同 code 但更新 effective_date → 标记旧版本 superseded
                        WITH lr
                        OPTIONAL MATCH (old:LegalReference {code: $code, status: 'effective'})
                        WHERE old.id <> $ref_id AND old.effective_date < $effective_date
                        SET old.status = 'superseded', old.superseded_by = $ref_id
                        """,
                        ref_id=ref_id,
                        name=ref_name,
                        code=ref_code,
                        type=ref_type,
                        scope=scope,
                        authority=authority,
                        effective_date=effective_date or "",
                        kb_id=kb_id,
                    )
                    nodes_created += 1
                    created_refs[ref_id] = True

                # 如果有对应的 ParagraphTemplate，建立 CITES 关系
                if para_id:
                    tx.run(
                        """
                        MATCH (lr:LegalReference {id: $ref_id})
                        MATCH (s:Section)
                        WHERE s.kb_id = $kb_id
                        WITH lr, s
                        MATCH (s)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
                        WHERE pt.id STARTS WITH 'TPL_PARA_'
                        WITH lr, pt
                        MERGE (pt)-[:CITES]->(lr)
                        """,
                        ref_id=ref_id,
                        kb_id=kb_id,
                    )
                    relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤5: TableSchema 节点（表格结构模板）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_table_schema_nodes(tx, kb_id: str, source_paragraphs: list[dict[str, Any]]) -> dict:
        """为 table 类型段落中的 table_schema 创建 TableSchema 节点"""
        nodes_created = 0
        relationships_created = 0
        created_schemas: dict[str, bool] = {}

        for para in source_paragraphs:
            if para.get("classify_type") != "table":
                continue

            template = para.get("template", {})
            if not isinstance(template, dict):
                continue

            table_schema = template.get("table_schema")
            if not isinstance(table_schema, dict):
                continue

            schema_name = table_schema.get("name", "")
            table_type = table_schema.get("table_type", "general")
            columns = table_schema.get("columns", [])
            if not columns:
                continue

            schema_id = f"TBL_{hashstr(f'{schema_name}_{table_type}', 12)}"

            if schema_id not in created_schemas:
                tx.run(
                    """
                    MERGE (ts:TableSchema {id: $schema_id})
                    ON CREATE SET
                        ts.id = $schema_id,
                        ts.name = $name,
                        ts.table_type = $table_type,
                        ts.columns = $columns,
                        ts.kb_id = $kb_id,
                        ts.created_at = datetime()
                    ON MATCH SET
                        ts.name = COALESCE($name, ts.name),
                        ts.columns = COALESCE($columns, ts.columns)
                    """,
                    schema_id=schema_id,
                    name=schema_name,
                    table_type=table_type,
                    columns=json.dumps(columns, ensure_ascii=False),
                    kb_id=kb_id,
                )
                nodes_created += 1
                created_schemas[schema_id] = True

                # 关联到 Section
                para_id = para.get("id", "")
                if para_id:
                    section_path = para.get("section_path", [])
                    if section_path:
                        section_path_str = "/".join(str(p) for p in section_path)
                        tx.run(
                            """
                            MATCH (ts:TableSchema {id: $schema_id})
                            MATCH (s:Section)
                            WHERE s.section_path_str = $section_path_str AND s.kb_id = $kb_id
                            MERGE (s)-[:HAS_TABLE_SCHEMA]->(ts)
                            """,
                            schema_id=schema_id,
                            section_path_str=section_path_str,
                            kb_id=kb_id,
                        )
                        relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤8: 骨架聚合（DomainOutline / ChapterTemplate / ParagraphRole）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_skeleton_aggregation(
        tx, kb_id: str, domain_code: str, report_type_code: str,
        doc_id: str, doc_title: str, source_paragraphs: list[dict[str, Any]],
    ) -> dict:
        """跨文档骨架聚合：创建 DomainOutline / ChapterTemplate / ParagraphRole 节点。

        聚合逻辑：
        1. 创建或更新 DomainOutline 节点（按 domain × report_type 唯一）
        2. 从当前文档的 Section 树构建 ChapterTemplate 节点
        3. 对已存在的 ChapterTemplate 更新 frequency 和 rigidity
        4. 从 parameter 段落提取 ParagraphRole
        5. 建立 Document -[CONTRIBUTES_TO]-> DomainOutline 关系
        """
        nodes_created = 0
        relationships_created = 0

        # 1. DomainOutline 节点
        outline_id = f"OUTLINE_{domain_code}_{report_type_code}"
        result = tx.run(
            """
            MERGE (dol:DomainOutline {id: $outline_id})
            ON CREATE SET
                dol.id = $outline_id,
                dol.domain = $domain_code,
                dol.report_type = $report_type_code,
                dol.source_count = 1,
                dol.last_updated = datetime(),
                dol.kb_id = $kb_id
            ON MATCH SET
                dol.source_count = dol.source_count + 1,
                dol.last_updated = datetime()
            RETURN dol.source_count AS sc
            """,
            outline_id=outline_id,
            domain_code=domain_code,
            report_type_code=report_type_code,
            kb_id=kb_id,
        ).single()
        source_count = result["sc"] if result else 1
        nodes_created += 1

        # Document -[CONTRIBUTES_TO]-> DomainOutline
        tx.run(
            """
            MATCH (d:Document {id: $doc_id})
            MATCH (dol:DomainOutline {id: $outline_id})
            MERGE (d)-[:CONTRIBUTES_TO]->(dol)
            """,
            doc_id=doc_id,
            outline_id=outline_id,
        )
        relationships_created += 1

        # 2. 从 Section 树构建 ChapterTemplate 节点
        # 收集所有标题段落的 section_path → title 映射
        chapter_map: dict[str, dict] = {}
        for para in source_paragraphs:
            if not para.get("is_title"):
                continue
            sp = para.get("section_path", [])
            if not sp:
                continue
            section_path_str = "/".join(str(p) for p in sp)
            title = para.get("title", "")
            level = len(sp)
            order_in_parent = sp[-1] if sp else 0
            try:
                order_int = int(str(order_in_parent).split(".")[0].split(" ")[0])
            except (ValueError, IndexError):
                order_int = 0

            chapter_id = f"CH_{domain_code}_{report_type_code}_{hashstr(section_path_str, 10)}"
            canonical_key = _derive_canonical_key(title)
            chapter_map[section_path_str] = {
                "chapter_id": chapter_id,
                "title": title,
                "canonical_key": canonical_key,
                "level": level,
                "order": order_int,
                "section_path_str": section_path_str,
            }

        # 创建 ChapterTemplate 节点并关联到 DomainOutline
        for sp_str, ch_info in chapter_map.items():
            chapter_id = ch_info["chapter_id"]
            title = ch_info["title"]
            level = ch_info["level"]
            order = ch_info["order"]

            # 计算 frequency：查询同 outline 下同名章节出现次数
            rigidity = "flexible"
            if source_count >= 2:
                # 在已有 ChapterTemplate 中查找同名章节
                count_result = tx.run(
                    """
                    MATCH (dol:DomainOutline {id: $outline_id})-[:HAS_CHAPTER]->(ch:ChapterTemplate {title: $title})
                    RETURN count(ch) AS cnt
                    """,
                    outline_id=outline_id,
                    title=title,
                ).single()
                existing_count = count_result["cnt"] if count_result else 0
                freq = (existing_count + 1) / source_count
                if freq >= 0.9:
                    rigidity = "rigid"
                elif freq >= 0.5:
                    rigidity = "flexible"
                else:
                    rigidity = "conditional"
            else:
                freq = 1.0
                rigidity = "rigid"  # 第一篇文档，默认刚性

            tx.run(
                """
                MERGE (ch:ChapterTemplate {id: $chapter_id})
                ON CREATE SET
                    ch.id = $chapter_id,
                    ch.title = $title,
                    ch.canonical_chapter_key = $canonical_key,
                    ch.level = $level,
                    ch.`order` = $order,
                    ch.rigidity = $rigidity,
                    ch.frequency = $frequency,
                    ch.domain = $domain_code,
                    ch.report_type = $report_type_code,
                    ch.kb_id = $kb_id,
                    ch.created_at = datetime()
                ON MATCH SET
                    ch.frequency = $frequency,
                    ch.rigidity = $rigidity,
                    ch.canonical_chapter_key = COALESCE(ch.canonical_chapter_key, $canonical_key)
                """,
                chapter_id=chapter_id,
                title=title,
                canonical_key=ch_info["canonical_key"],
                level=level,
                order=order,
                rigidity=rigidity,
                frequency=freq,
                domain_code=domain_code,
                report_type_code=report_type_code,
                kb_id=kb_id,
            )
            nodes_created += 1

            # DomainOutline -[HAS_CHAPTER]-> ChapterTemplate
            tx.run(
                """
                MATCH (dol:DomainOutline {id: $outline_id})
                MATCH (ch:ChapterTemplate {id: $chapter_id})
                MERGE (dol)-[:HAS_CHAPTER]->(ch)
                """,
                outline_id=outline_id,
                chapter_id=chapter_id,
            )
            relationships_created += 1

            # 建立 ChapterTemplate 层级关系（HAS_CHILD）
            sp_parts = sp_str.split("/")
            if len(sp_parts) > 1:
                parent_sp_str = "/".join(sp_parts[:-1])
                if parent_sp_str in chapter_map:
                    parent_ch_id = chapter_map[parent_sp_str]["chapter_id"]
                    tx.run(
                        """
                        MATCH (parent:ChapterTemplate {id: $parent_id})
                        MATCH (child:ChapterTemplate {id: $child_id})
                        MERGE (parent)-[:HAS_CHILD]->(child)
                        """,
                        parent_id=parent_ch_id,
                        child_id=chapter_id,
                    )
                    relationships_created += 1

            # ETL 子章节映射到标准子章节 (level=2 时按标题匹配)
            if level == 2 and domain_code and report_type_code:
                std_prefix = f"CH_{domain_code}_{report_type_code}_std_"
                tx.run(
                    """
                    MATCH (etl:ChapterTemplate {id: $etl_id})
                    MATCH (std:ChapterTemplate)
                    WHERE std.id STARTS WITH $std_prefix
                      AND std.level = 2
                      AND (std.canonical_chapter_key = etl.canonical_chapter_key
                           OR etl.canonical_chapter_key CONTAINS std.canonical_chapter_key
                           OR std.canonical_chapter_key CONTAINS etl.canonical_chapter_key)
                    WITH etl, std LIMIT 1
                    MERGE (std)-[:HAS_CHILD]->(etl)
                    SET etl.canonical_chapter_key = std.canonical_chapter_key
                    """,
                    etl_id=chapter_id,
                    std_prefix=std_prefix,
                )

        # 3. ParagraphRole 节点（从 parameter 段落提取段落角色）
        para_order = 0
        for para in source_paragraphs:
            ct = para.get("classify_type", "")
            if ct not in ("parameter",):
                continue
            sp = para.get("section_path", [])
            if not sp:
                continue

            # 找到所属 ChapterTemplate
            sp_str = "/".join(str(p) for p in sp)
            # 查找最近的章节
            target_ch_id = None
            for i in range(len(sp), 0, -1):
                parent_sp = "/".join(str(p) for p in sp[:i])
                if parent_sp in chapter_map:
                    target_ch_id = chapter_map[parent_sp]["chapter_id"]
                    break
            if not target_ch_id:
                continue

            template = para.get("template", {})
            if not isinstance(template, dict):
                continue

            # 从 generalized 文本推断角色名称
            generalized = template.get("generalized", "")
            if not generalized:
                continue

            # 角色名称从 section title 或 generalized 首个 slot 推断
            section_title = para.get("title", "") or para.get("parent_title", "")
            slots = template.get("slots", [])
            role_name = section_title
            if not role_name and slots:
                role_name = slots[0].get("name", "未知参数") + "描述"
            if not role_name:
                role_name = f"参数描述_{para_order}"

            role_id = f"ROLE_{hashstr(f'{target_ch_id}_{role_name}', 10)}"
            para_order += 1

            required_slots = [s.get("name", "") for s in slots if isinstance(s, dict) and s.get("name")]

            tx.run(
                """
                MERGE (pr:ParagraphRole {id: $role_id})
                ON CREATE SET
                    pr.id = $role_id,
                    pr.role = $role_name,
                    pr.order = $order,
                    pr.typical_length = $typical_length,
                    pr.contains_data = true,
                    pr.required_slots = $required_slots,
                    pr.kb_id = $kb_id,
                    pr.created_at = datetime()
                """,
                role_id=role_id,
                role_name=role_name,
                order=para_order,
                typical_length=f"{len(para.get('content', ''))}字",
                required_slots=json.dumps(required_slots, ensure_ascii=False),
                kb_id=kb_id,
            )
            nodes_created += 1

            # ChapterTemplate -[REQUIRES_PARAGRAPH_ROLE {order}]-> ParagraphRole
            tx.run(
                """
                MATCH (ch:ChapterTemplate {id: $chapter_id})
                MATCH (pr:ParagraphRole {id: $role_id})
                MERGE (ch)-[r:REQUIRES_PARAGRAPH_ROLE]->(pr)
                ON CREATE SET r.order = $order
                """,
                chapter_id=target_ch_id,
                role_id=role_id,
                order=para_order,
            )
            relationships_created += 1

            # ParagraphRole -[REALIZED_BY {confidence, frequency}]-> ParagraphTemplate
            template_data = _normalize_template_data(template)
            if template_data and template_data.get("generalized"):
                template_id = _generate_template_id(template_data, para.get("id", ""))
                quality_score = template.get("quality_score", 0.5)
                tx.run(
                    """
                    MATCH (pr:ParagraphRole {id: $role_id})
                    MATCH (pt:ParagraphTemplate {id: $template_id})
                    MERGE (pr)-[r:REALIZED_BY]->(pt)
                    ON CREATE SET r.confidence = $confidence, r.frequency = 1
                    ON MATCH SET r.frequency = r.frequency + 1
                    """,
                    role_id=role_id,
                    template_id=template_id,
                    confidence=quality_score,
                )
                relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤9: 逻辑关系节点（CausalChain / ConditionRule / DataFlow）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_logical_relationship_nodes(
        tx, kb_id: str, source_paragraphs: list[dict[str, Any]], base_info: dict,
    ) -> dict:
        """从段落的 logical_relations 元数据创建逻辑关系节点。

        逻辑关系由 ETL pipeline 的 extract_logical_relationships 提取，
        存储在 task 的 logical_relations 字段中。
        此方法从段落的 template.logical_refs 读取并写入图谱。
        """
        nodes_created = 0
        relationships_created = 0

        # 从段落中读取逻辑关系（由 ETL 写入 para.template.logical_refs）
        causal_chains = []
        conditions = []
        data_refs = []

        for para in source_paragraphs:
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue
            lr = template.get("logical_refs", {})
            if not isinstance(lr, dict):
                continue
            for chain in lr.get("causal_chains", []):
                if isinstance(chain, dict):
                    chain["source_para_id"] = para.get("id", "")
                    causal_chains.append(chain)
            for cond in lr.get("conditions", []):
                if isinstance(cond, dict):
                    cond["source_para_id"] = para.get("id", "")
                    conditions.append(cond)
            for dref in lr.get("data_refs", []):
                if isinstance(dref, dict):
                    dref["source_para_id"] = para.get("id", "")
                    data_refs.append(dref)

        # 创建因果链节点
        for chain in causal_chains:
            cause_id = chain.get("cause_para_id", "")
            effect_id = chain.get("effect_para_id", "")
            relation = chain.get("relation", "")
            if not cause_id or not effect_id:
                continue

            chain_id = f"CAUSAL_{hashstr(f'{cause_id}_{effect_id}', 10)}"
            tx.run(
                """
                MERGE (cc:CausalChain {id: $chain_id})
                ON CREATE SET
                    cc.id = $chain_id,
                    cc.relation = $relation,
                    cc.kb_id = $kb_id,
                    cc.created_at = datetime()
                """,
                chain_id=chain_id,
                relation=relation,
                kb_id=kb_id,
            )
            nodes_created += 1

            # ParagraphTemplate -[CAUSES]-> CausalChain -> ParagraphTemplate
            # Build para_id -> template_id mapping from source_paragraphs
            cause_template_id = _find_template_id_for_para(cause_id, source_paragraphs)
            effect_template_id = _find_template_id_for_para(effect_id, source_paragraphs)
            if cause_template_id:
                tx.run(
                    """
                    MATCH (cc:CausalChain {id: $chain_id})
                    MATCH (pt:ParagraphTemplate {id: $template_id})
                    MERGE (pt)-[:CAUSES]->(cc)
                    """,
                    chain_id=chain_id,
                    template_id=cause_template_id,
                )
                relationships_created += 1
            if effect_template_id:
                tx.run(
                    """
                    MATCH (cc:CausalChain {id: $chain_id})
                    MATCH (pt:ParagraphTemplate {id: $template_id})
                    MERGE (cc)-[:CAUSES]->(pt)
                    """,
                    chain_id=chain_id,
                    template_id=effect_template_id,
                )
                relationships_created += 1

        # 创建条件分支节点
        for cond in conditions:
            expression = cond.get("expression", "")
            consequence = cond.get("consequence", "")
            if not expression:
                continue

            cond_id = f"COND_{hashstr(f'{expression}_{consequence}', 10)}"
            tx.run(
                """
                MERGE (cr:ConditionRule {id: $cond_id})
                ON CREATE SET
                    cr.id = $cond_id,
                    cr.expression = $expression,
                    cr.consequence = $consequence,
                    cr.source = 'learned',
                    cr.frequency = 1,
                    cr.kb_id = $kb_id,
                    cr.created_at = datetime()
                ON MATCH SET
                    cr.frequency = cr.frequency + 1
                """,
                cond_id=cond_id,
                expression=expression,
                consequence=consequence,
                kb_id=kb_id,
            )
            nodes_created += 1

            # 关联到 ChapterTemplate
            source_para_id = cond.get("source_para_id", "")
            if source_para_id:
                tx.run(
                    """
                    MATCH (cr:ConditionRule {id: $cond_id})
                    MATCH (s:Section)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
                    WHERE s.kb_id = $kb_id
                    WITH cr, s
                    MATCH (dol:DomainOutline)-[:HAS_CHAPTER]->(ch:ChapterTemplate)
                    WHERE ch.kb_id = $kb_id
                    WITH cr, collect(DISTINCT ch) AS chapters
                    FOREACH (ch IN chapters |
                        MERGE (ch)-[r:REQUIRED_WHEN]->(cr)
                        ON CREATE SET r.condition = $expression
                    )
                    """,
                    cond_id=cond_id,
                    kb_id=kb_id,
                    expression=expression,
                )
                relationships_created += 1

        # 创建数据引用链节点
        for dref in data_refs:
            para_id = dref.get("para_id", "")
            source = dref.get("source", "")
            data_fields = dref.get("data_fields", [])
            if not para_id:
                continue

            flow_id = f"DFLOW_{hashstr(f'{para_id}_{source}', 10)}"
            tx.run(
                """
                MERGE (df:DataFlow {id: $flow_id})
                ON CREATE SET
                    df.id = $flow_id,
                    df.source = $source,
                    df.data_fields = $data_fields,
                    df.kb_id = $kb_id,
                    df.created_at = datetime()
                """,
                flow_id=flow_id,
                source=source,
                data_fields=json.dumps(data_fields, ensure_ascii=False) if isinstance(data_fields, list) else str(data_fields),
                kb_id=kb_id,
            )
            nodes_created += 1

            # ParagraphTemplate -[DERIVED_FROM]-> TableSchema or ParagraphTemplate
            if source.startswith("table"):
                tx.run(
                    """
                    MATCH (df:DataFlow {id: $flow_id})
                    MATCH (ts:TableSchema)
                    WHERE ts.kb_id = $kb_id
                    WITH df, ts
                    LIMIT 1
                    MERGE (df)-[:SOURCED_FROM]->(ts)
                    """,
                    flow_id=flow_id,
                    kb_id=kb_id,
                )
                relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤6: FormulaTemplate 节点（公式结构+变量映射）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_formula_template_nodes(tx, kb_id: str, source_paragraphs: list[dict[str, Any]]) -> dict:
        """为 formula 类型段落中的公式创建 FormulaTemplate 节点，并建立 USES_VARIABLE 关系到 Slot 节点。"""
        nodes_created = 0
        relationships_created = 0
        created_formulas: dict[str, bool] = {}

        for para in source_paragraphs:
            if para.get("classify_type") != "formula":
                continue
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue
            formula_data = template.get("formula")
            if not isinstance(formula_data, dict):
                continue

            original = formula_data.get("original", "")
            purpose = formula_data.get("purpose", "通用计算")
            fmt = formula_data.get("format", "text")
            variables = formula_data.get("variables", [])
            formula_id = f"FORMULA_{hashstr(original[:200], 12)}"

            if formula_id not in created_formulas:
                tx.run(
                    """
                    MERGE (f:FormulaTemplate {id: $formula_id})
                    ON CREATE SET
                        f.id = $formula_id,
                        f.original = $original,
                        f.format = $format,
                        f.purpose = $purpose,
                        f.kb_id = $kb_id,
                        f.created_at = datetime()
                    ON MATCH SET
                        f.purpose = COALESCE($purpose, f.purpose)
                    """,
                    formula_id=formula_id,
                    original=original[:500],
                    format=fmt,
                    purpose=purpose,
                    kb_id=kb_id,
                )
                nodes_created += 1
                created_formulas[formula_id] = True

                for var in variables:
                    if not isinstance(var, dict):
                        continue
                    sym = var.get("symbol", "")
                    entity_ref = var.get("entity_ref", "")
                    var_name = var.get("name", sym)
                    var_unit = var.get("unit", "")
                    if entity_ref:
                        slot_id = f"SLOT_{entity_ref.upper()}"
                    else:
                        slot_id = f"SLOT_{var_name.upper().replace(' ', '_')}"
                    tx.run(
                        """
                        MERGE (s:Slot {id: $slot_id})
                        ON CREATE SET
                            s.id = $slot_id,
                            s.name = $var_name,
                            s.kb_id = $kb_id,
                            s.created_at = datetime()
                        """,
                        slot_id=slot_id,
                        var_name=var_name,
                        kb_id=kb_id,
                    )
                    nodes_created += 1
                    tx.run(
                        """
                        MATCH (f:FormulaTemplate {id: $formula_id})
                        MATCH (s:Slot {id: $slot_id})
                        MERGE (f)-[r:USES_VARIABLE {symbol: $symbol}]->(s)
                        ON CREATE SET r.unit = $unit
                        """,
                        formula_id=formula_id,
                        slot_id=slot_id,
                        symbol=sym,
                        unit=var_unit,
                    )
                    relationships_created += 1

                section_path = para.get("section_path", [])
                if section_path:
                    section_path_str = "/".join(str(p) for p in section_path)
                    tx.run(
                        """
                        MATCH (f:FormulaTemplate {id: $formula_id})
                        MATCH (s:Section)
                        WHERE s.section_path_str = $section_path_str AND s.kb_id = $kb_id
                        MERGE (s)-[:HAS_FORMULA]->(f)
                        """,
                        formula_id=formula_id,
                        section_path_str=section_path_str,
                        kb_id=kb_id,
                    )
                    relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤7: ProcessFlow 节点（图片多模态提取结果）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_process_flow_nodes(tx, kb_id: str, source_paragraphs: list[dict[str, Any]]) -> dict:
        """为 figure 类型段落中的多模态提取结果创建 ProcessFlow / ProcessStep 节点"""
        nodes_created = 0
        relationships_created = 0
        created_flows: dict[str, bool] = {}

        for para in source_paragraphs:
            if para.get("classify_type") != "figure":
                continue
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue
            figure_data = template.get("figure")
            if not isinstance(figure_data, dict):
                continue

            figure_type = figure_data.get("figure_type", "")
            steps = figure_data.get("steps", [])
            caption = figure_data.get("caption", para.get("title", ""))
            if figure_type != "process_flow" or not steps:
                continue

            flow_id = f"FLOW_{hashstr(caption[:200], 12)}"
            if flow_id not in created_flows:
                tx.run(
                    """
                    MERGE (pf:ProcessFlow {id: $flow_id})
                    ON CREATE SET
                        pf.id = $flow_id,
                        pf.name = $caption,
                        pf.figure_type = $figure_type,
                        pf.kb_id = $kb_id,
                        pf.created_at = datetime()
                    """,
                    flow_id=flow_id,
                    caption=caption,
                    figure_type=figure_type,
                    kb_id=kb_id,
                )
                nodes_created += 1
                created_flows[flow_id] = True

                for order, step in enumerate(steps, 1):
                    if isinstance(step, str):
                        step_name = step
                        step_type = "unknown"
                    elif isinstance(step, dict):
                        step_name = step.get("name", "")
                        step_type = step.get("type", "unknown")
                    else:
                        continue
                    if not step_name:
                        continue
                    step_id = f"STEP_{hashstr(f'{flow_id}_{step_name}', 12)}"
                    tx.run(
                        """
                        MERGE (ps:ProcessStep {id: $step_id})
                        ON CREATE SET
                            ps.id = $step_id,
                            ps.name = $step_name,
                            ps.type = $step_type,
                            ps.kb_id = $kb_id,
                            ps.created_at = datetime()
                        """,
                        step_id=step_id,
                        step_name=step_name,
                        step_type=step_type,
                        kb_id=kb_id,
                    )
                    nodes_created += 1
                    tx.run(
                        """
                        MATCH (pf:ProcessFlow {id: $flow_id})
                        MATCH (ps:ProcessStep {id: $step_id})
                        MERGE (pf)-[r:STEP]->(ps)
                        ON CREATE SET r.order = $order
                        """,
                        flow_id=flow_id,
                        step_id=step_id,
                        order=order,
                    )
                    relationships_created += 1

                section_path = para.get("section_path", [])
                if section_path:
                    section_path_str = "/".join(str(p) for p in section_path)
                    tx.run(
                        """
                        MATCH (pf:ProcessFlow {id: $flow_id})
                        MATCH (s:Section)
                        WHERE s.section_path_str = $section_path_str AND s.kb_id = $kb_id
                        MERGE (s)-[:HAS_PROCESS_FLOW]->(pf)
                        """,
                        flow_id=flow_id,
                        section_path_str=section_path_str,
                        kb_id=kb_id,
                    )
                    relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    def backfill_canonical_keys(self, outline_map: dict, kb_id: str = "") -> int:
        """用 outline_map({chapter_id: canonical_key}) 更新 ChapterTemplate.canonical_chapter_key。

        供 _produce_outlines_async 在 LLM 算出 key 后回写图谱（LLM key 覆盖 ETL 推导 key）。
        """
        if not outline_map:
            return 0
        driver = self._get_driver()
        if not driver:
            logger.warning("backfill_canonical_keys: Neo4j 未连接，跳过")
            return 0
        updated = 0
        with driver.session() as session:
            for chapter_id, canonical_key in outline_map.items():
                if not canonical_key:
                    continue
                session.run(
                    "MATCH (ch:ChapterTemplate {id:$id}) "
                    "SET ch.canonical_chapter_key = $key",
                    id=chapter_id, key=canonical_key,
                )
                updated += 1
        logger.info(f"backfill_canonical_keys: 更新 {updated} 个 ChapterTemplate")
        return updated

    def close(self):
        """关闭 Neo4j 连接"""
        if self._driver:
            self._driver.close()
            self._driver = None


# ======================================================================
# 模块级辅助函数
# ======================================================================


def _find_template_id_for_para(para_id: str, source_paragraphs: list[dict[str, Any]]) -> str | None:
    """从 source_paragraphs 中找到段落的 template_id"""
    for para in source_paragraphs:
        if para.get("id") == para_id:
            template_data = _normalize_template_data(para.get("template"))
            if template_data and template_data.get("generalized"):
                return _generate_template_id(template_data, para_id)
    return None


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
