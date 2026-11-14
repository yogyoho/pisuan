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
- ParagraphTemplate -[CITES]-> LegalReference（起点必须是具体来源段落模板）
- ParagraphTemplate -[HAS_TABLE_SCHEMA]-> TableSchema
- ParagraphTemplate -[HAS_FORMULA]-> FormulaTemplate
- Slot -[CONSTRAINS]-> EntitySchema
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from neo4j import GraphDatabase as Neo4jDriver

from pisuan.utils import hashstr, logger, normalize_chapter_key
from pisuan.services.domain_factory_region import attribution_scope_key

_RELATION_LABEL_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _sanitize_relation_label(raw: Any) -> str:
    """把规则里的关系名规整成合法的 Neo4j 关系类型（大写 ASCII）。非法返回空。"""
    label = re.sub(r"[^A-Za-z0-9_]", "_", str(raw or "").strip()).upper()
    label = re.sub(r"_+", "_", label).strip("_")[:64]
    if not label:
        return ""
    if label[0].isdigit():
        label = f"R_{label}"
    return label if _RELATION_LABEL_RE.match(label) else ""


def _collect_paragraph_entity_values(slots: Any) -> dict[str, dict[str, Any]]:
    """从段落模板的 slot 汇总 {entity_key: {prop_key: value}}。

    entity_ref 形如 `entity_key.prop_key`；无点号时视为实体级实例，属性键记为 `*`。
    """
    instances: dict[str, dict[str, Any]] = {}
    if not isinstance(slots, list):
        return instances
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        ref = str(slot.get("entity_ref") or "").strip()
        if not ref:
            continue
        entity_key, _, prop_key = ref.rpartition(".")
        if not entity_key:
            entity_key, prop_key = ref, "*"
        value = slot.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        instances.setdefault(entity_key, {})[prop_key] = value
    return instances


def _comparable(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return text


def _condition_matches(condition: dict[str, Any], props: dict[str, Any]) -> bool:
    """规则条件逐项比对：属性值相等，或列表属性包含期望值。缺值一律不命中。"""
    if not condition:
        return False
    for prop_key, expected in condition.items():
        actual = props.get(str(prop_key))
        if actual is None:
            return False
        if isinstance(actual, list):
            if not any(_comparable(item) == _comparable(expected) for item in actual):
                return False
        elif _comparable(actual) != _comparable(expected):
            return False
    return True


def _derive_canonical_key(title: str) -> str:
    """从章节标题推导 canonical_chapter_key:去前导编号与所有内部空白,只留纯标题。纯编号返回空。"""
    return normalize_chapter_key(title)


def _derive_chapter_no(section_path: list) -> str:
    """由 section_path 推导章节编号（如 [1, 4] → "1.4"、["1", "1.4.2"] → "1.4.2"）。

    ETL 解析路径末段即完整点分编号,直接取用;计数栈路径逐级以'.'连接。
    """
    parts = [str(p) for p in (section_path or [])]
    if not parts:
        return ""
    last = parts[-1]
    if "." in last:
        return last
    return ".".join(parts)


def resolve_chapter_id(
    domain_code: str,
    report_type_code: str,
    norm_canonical: str,
    level: int,
    parent_resolved_id: str,
    std_index: dict[tuple[str, str, int], str],
    attribution: str = "",
) -> str:
    """按聚合身份键解析 ChapterTemplate 节点 id（纯函数,std 索引由调用方预构建）。

    身份 = (domain, report_type, 归一canonical, level, 父节点解析id)：
    - std_index 命中 → 复用 std id（键为 (归一canonical, 父解析id, level),level=1 父解析id 固定空串）
    - 未命中 → CH_{domain}_{rt}_{level}_{hashstr(归一canonical + '|' + 父解析id)}
    同构章节树跨文档解析出相同 id → MERGE 幂等;不同父同名单独成点。
    """
    if not attribution:
        std_id = std_index.get((norm_canonical, parent_resolved_id, level))
        if std_id:
            return std_id
    identity = f"{norm_canonical}|{parent_resolved_id}"
    if attribution:
        identity = f"{identity}|{attribution}"
    return f"CH_{domain_code}_{report_type_code}_{level}_{hashstr(identity, 10)}"


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
        document_key: str | None = None,
        project_name: str | None = None,
        region_key: str | None = None,
        scope: str | None = None,
        entity_rules: dict[str, dict[str, Any]] | None = None,
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
            document_key: 稳定文档身份（内容哈希）；缺省时按 source_paragraphs 推导
            project_name: 项目归属；与 region/scope 一起构成图谱隔离身份
            region_key: 区域归属键
            scope: universal|regional|project
            entity_rules: 实体关系推理规则，{entity_key: {name, category, rules}}

        Returns:
            构建结果统计
        """
        driver = self._get_driver()
        if not driver:
            logger.warning("Neo4j 未连接，跳过图谱构建")
            return {"nodes_created": 0, "relationships_created": 0, "skipped": True}

        stats = {"nodes_created": 0, "relationships_created": 0, "skipped": False}
        document_key = document_key or document_content_key(source_paragraphs)
        attribution = attribution_scope_key(kb_id, region_key, scope, project_name)

        try:
            with driver.session() as session:
                # 步骤1: 创建 Document 节点
                doc_result = session.execute_write(
                    self._create_document_node,
                    kb_id,
                    doc_id,
                    doc_title,
                    domain_label,
                    domain_code,
                    report_type_code,
                    document_key,
                    project_name or "",
                    region_key or "",
                    scope or "",
                    attribution,
                )
                stats["nodes_created"] += doc_result.get("nodes", 0)
                stats["relationships_created"] += doc_result.get("relationships", 0)

                # 步骤2: 构建 Section、ParagraphTemplate、Slot 节点和关系
                structure_result = session.execute_write(
                    self._build_sections_and_templates,
                    kb_id,
                    doc_id,
                    source_paragraphs,
                    domain_code or "",
                    report_type_code or "",
                    project_name or "",
                    region_key or "",
                    scope or "",
                    attribution,
                )
                stats["nodes_created"] += structure_result.get("nodes", 0)
                stats["relationships_created"] += structure_result.get("relationships", 0)

                # 步骤3: 构建 EntitySchema 节点，将 Slot 的 entity_ref 关联到实体定义
                entity_result = session.execute_write(
                    self._build_entity_schema_nodes,
                    kb_id,
                    source_paragraphs,
                    domain_code or "",
                    attribution,
                )
                stats["nodes_created"] += entity_result.get("nodes", 0)
                stats["relationships_created"] += entity_result.get("relationships", 0)
                stats["unresolved_entity_refs"] = entity_result.get("unresolved_entity_refs", 0)

                # 步骤4: 构建 LegalReference 节点
                legal_result = session.execute_write(
                    self._build_legal_reference_nodes,
                    kb_id,
                    doc_id,
                    source_paragraphs,
                    structure_result.get("section_map") or {},
                    domain_code or "",
                    report_type_code or "",
                    attribution,
                )
                stats["nodes_created"] += legal_result.get("nodes", 0)
                stats["relationships_created"] += legal_result.get("relationships", 0)
                stats["citations_created"] = legal_result.get("citations_created", 0)
                stats["source_templates_created"] = legal_result.get("source_templates_created", 0)

                # 步骤5: 构建 TableSchema 节点
                table_result = session.execute_write(
                    self._build_table_schema_nodes,
                    kb_id, doc_id, source_paragraphs,
                    structure_result.get("section_map") or {},
                    domain_code or "", report_type_code or "",
                    project_name or "",
                    region_key or "",
                    scope or "",
                    attribution,
                )
                stats["nodes_created"] += table_result.get("nodes", 0)
                stats["relationships_created"] += table_result.get("relationships", 0)

                # 步骤6: 构建 FormulaTemplate 节点
                formula_result = session.execute_write(
                    self._build_formula_template_nodes,
                    kb_id, doc_id, source_paragraphs,
                    structure_result.get("section_map") or {},
                    domain_code or "", report_type_code or "",
                    project_name or "",
                    region_key or "",
                    scope or "",
                    attribution,
                )
                stats["nodes_created"] += formula_result.get("nodes", 0)
                stats["relationships_created"] += formula_result.get("relationships", 0)

                # 步骤7: 构建 ProcessFlow 节点（图片多模态提取结果）
                flow_result = session.execute_write(
                    self._build_process_flow_nodes,
                    kb_id, doc_id, source_paragraphs,
                    structure_result.get("section_map") or {},
                    attribution,
                )
                stats["nodes_created"] += flow_result.get("nodes", 0)
                stats["relationships_created"] += flow_result.get("relationships", 0)

                # 步骤8: 骨架聚合（DomainOutline / ChapterTemplate）
                if domain_code and report_type_code:
                    skeleton_result = session.execute_write(
                        self._build_skeleton_aggregation,
                        kb_id, domain_code, report_type_code, doc_id, doc_title,
                        source_paragraphs, document_key,
                        project_name or "",
                        region_key or "",
                        scope or "",
                        attribution,
                    )
                    stats["nodes_created"] += skeleton_result.get("nodes", 0)
                    stats["relationships_created"] += skeleton_result.get("relationships", 0)

                # 步骤9: 逻辑关系节点（CausalChain / ConditionRule / DataFlow）
                # 从 task 的 logical_relations 字段读取（由 ETL pipeline 提取后传入）
                logical_result = session.execute_write(
                    self._build_logical_relationship_nodes,
                    kb_id,
                    source_paragraphs,
                    base_info or {},
                    attribution,
                )
                stats["nodes_created"] += logical_result.get("nodes", 0)
                stats["relationships_created"] += logical_result.get("relationships", 0)

                # 步骤10: 实体关系推理规则（实体构建器维护，按段落 slot 值求值后落边）
                if entity_rules:
                    rule_result = session.execute_write(
                        self._build_entity_relation_rule_edges,
                        kb_id,
                        source_paragraphs,
                        entity_rules,
                        attribution,
                    )
                    stats["rule_edges_created"] = rule_result.get("edges", 0)
                    stats["rule_matches"] = rule_result.get("matches", 0)
                    stats["rule_skipped_actions"] = rule_result.get("skipped_actions", 0)

                logger.info(
                    f"图谱构建完成: 文档 {doc_id}, 节点 {stats['nodes_created']}, 关系 {stats['relationships_created']}"
                )
                return stats

        except Exception as exc:
            logger.error("构建知识图谱失败: {}", exc, exc_info=True)
            return {"nodes_created": 0, "relationships_created": 0, "error": str(exc)}

    @staticmethod
    def rebuild_legal_citations(
        session,
        kb_id: str,
        doc_id: str,
        source_paragraphs: list[dict[str, Any]],
        section_map: dict[str, dict[str, Any]],
        domain_code: str = "",
        report_type_code: str = "",
        attribution: str = "",
    ) -> dict:
        """在已存在的文档结构上重算 LegalReference/CITES（供存量治理脚本复用）。"""
        return session.execute_write(
            GraphBuilder._build_legal_reference_nodes,
            kb_id, doc_id, source_paragraphs, section_map, domain_code, report_type_code, attribution,
        )

    # ------------------------------------------------------------------
    # 步骤1: Document 节点
    # ------------------------------------------------------------------

    @staticmethod
    def _create_document_node(
        tx, kb_id, doc_id, doc_title, domain_label,
        domain_code=None, report_type_code=None, document_key=None,
        project_name="", region_key="", scope="", attribution="",
    ) -> dict:
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
                d.document_key = COALESCE($document_key, $doc_id),
                d.kb_id = $kb_id,
                d.project_name = $project_name,
                d.region_key = $region_key,
                d.scope = $scope,
                d.attribution = $attribution,
                d.score = 5,
                d.created_at = datetime()
            ON MATCH SET
                d.filename = COALESCE($doc_title, d.filename),
                d.title = COALESCE($doc_title, d.title),
                d.domain = COALESCE($domain_label, d.domain),
                d.domain_code = CASE WHEN $domain_code <> '' THEN $domain_code ELSE COALESCE(d.domain_code, '') END,
                d.report_type_code = CASE
                    WHEN $report_type_code <> '' THEN $report_type_code
                    ELSE COALESCE(d.report_type_code, '')
                END,
                d.document_key = COALESCE(d.document_key, $document_key, $doc_id),
                d.kb_id = COALESCE($kb_id, d.kb_id),
                d.project_name = CASE WHEN $project_name <> '' THEN $project_name ELSE d.project_name END,
                d.region_key = CASE WHEN $region_key <> '' THEN $region_key ELSE d.region_key END,
                d.scope = CASE WHEN $scope <> '' THEN $scope ELSE d.scope END,
                d.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE d.attribution END
            """,
            kb_id=kb_id,
            doc_id=doc_id,
            doc_title=doc_title,
            domain_label=domain_label or "",
            domain_code=domain_code or "",
            report_type_code=report_type_code or "",
            document_key=document_key or doc_id,
            project_name=project_name,
            region_key=region_key,
            scope=scope,
            attribution=attribution,
        )
        return {"nodes": 1, "relationships": 0}

    # ------------------------------------------------------------------
    # 步骤2: Section / ParagraphTemplate / Slot 节点和关系
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sections_and_templates(
        tx, kb_id: str, doc_id: str, source_paragraphs: list[dict[str, Any]],
        domain_code: str = "", report_type_code: str = "",
        project_name: str = "", region_key: str = "", scope: str = "", attribution: str = "",
    ) -> dict:
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
                    s.project_name = $project_name,
                    s.region_key = $region_key,
                    s.scope = $scope,
                    s.attribution = $attribution,
                    s.created_at = datetime()
                ON MATCH SET
                    s.title = COALESCE($title, s.title),
                    s.level = COALESCE($level, s.level),
                    s.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE s.attribution END
                """,
                section_id=section_id,
                title=section_title,
                level=level,
                section_path=json.dumps(section_path, ensure_ascii=False),
                section_path_str=section_path_str,
                kb_id=kb_id,
                project_name=project_name,
                region_key=region_key,
                scope=scope,
                attribution=attribution,
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

            template_id = _generate_template_id(template_data, chunk_id, attribution)
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
                        pt.domain = $domain_code,
                        pt.report_type = $report_type_code,
                        pt.kb_id = $kb_id,
                        pt.project_name = $project_name,
                        pt.region_key = $region_key,
                        pt.scope = $scope,
                        pt.attribution = $attribution,
                        pt.created_at = datetime()
                    ON MATCH SET
                        pt.text_pattern = COALESCE($text_pattern, pt.text_pattern),
                        pt.generalized_pattern = COALESCE($generalized_pattern, pt.generalized_pattern),
                        pt.classify_type = COALESCE($classify_type, pt.classify_type),
                        pt.domain = COALESCE(pt.domain, $domain_code),
                        pt.report_type = COALESCE(pt.report_type, $report_type_code),
                        pt.canonical_chapter_key = COALESCE(pt.canonical_chapter_key, $canonical_key),
                        pt.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE pt.attribution END
                    """,
                    template_id=template_id,
                    text_pattern=generalized,
                    generalized_pattern=generalized,
                    canonical_key=para_canonical_key,
                    hash=template_hash,
                    classify_type=classify_type,
                    domain_code=domain_code,
                    report_type_code=report_type_code,
                    kb_id=kb_id,
                    project_name=project_name,
                    region_key=region_key,
                    scope=scope,
                    attribution=attribution,
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
                    slot_stats = _create_slots_and_relationships(
                        tx,
                        template_id,
                        slots,
                        kb_id,
                        project_name,
                        region_key,
                        scope,
                        attribution,
                    )
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

        return {
            "nodes": nodes_created,
            "relationships": relationships_created,
            "section_map": section_map,
        }

    # ------------------------------------------------------------------
    # 步骤3: EntitySchema 节点（Slot → EntitySchema 约束关系）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_entity_schema_nodes(
        tx,
        kb_id: str,
        source_paragraphs: list[dict[str, Any]],
        domain_code: str = "",
        attribution: str = "",
    ) -> dict:
        """只为精确命中实体元数据的 Slot 建立 EntitySchema 与 CONSTRAINS。

        未命中的 entity_ref 保留在 Slot.unresolved_entity_ref 并计入结构化告警，
        不创建占位实体，避免把属性路径或模型幻觉写成实体定义。
        """
        from pisuan.services.entity_meta_service import EntityMetaLoader

        nodes_created = 0
        relationships_created = 0
        unresolved_entity_refs = 0
        created_entities: dict[str, bool] = {}

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

                entity_ref = str(slot.get("entity_ref") or "").strip()
                if not entity_ref:
                    continue

                slot_name = str(slot.get("name") or "").strip()
                if not slot_name:
                    continue
                slot_id = _generate_slot_id(
                    slot_name,
                    slot.get("type", ""),
                    slot.get("unit", ""),
                    entity_ref,
                    attribution,
                )
                entity_info = entity_meta.get(entity_ref)
                if entity_info is None:
                    unresolved_entity_refs += 1
                    tx.run(
                        """
                        MATCH (s:Slot {id: $slot_id})
                        SET s.unresolved_entity_ref = $entity_ref
                        """,
                        slot_id=slot_id,
                        entity_ref=entity_ref,
                    )
                    continue

                entity_id = f"entity_{entity_ref}"

                if entity_id not in created_entities:
                    entity_name = entity_info.get("name") or entity_ref
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
                            e.metadata_source = 'coal_eia_entity_types',
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

        return {
            "nodes": nodes_created,
            "relationships": relationships_created,
            "unresolved_entity_refs": unresolved_entity_refs,
        }

    # ------------------------------------------------------------------
    # 步骤10: 实体关系推理规则（relation_rules → 图谱边）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_entity_relation_rule_edges(
        tx,
        kb_id: str,
        source_paragraphs: list[dict[str, Any]],
        entity_rules: dict[str, dict[str, Any]],
        attribution: str = "",
    ) -> dict:
        """按实体 relation_rules 在段落模板上求值，命中后落一条证据边。

        规则形态：{"rule_name", "condition": {prop_key: 期望值},
                  "actions": [{"type": "create_edge", "relation": "CONFLICT_WITH", "target": "entity_key"}]}

        条件在段落的 slot 值上求值（slot.entity_ref = entity_key.prop_key）；
        命中后生成 (ParagraphTemplate)-[<relation>]->(EntitySchema 目标)，
        边属性记录 rule_id/rule_name/source_entity/matched_props，便于回溯。
        """
        edges = 0
        matches = 0
        skipped_actions = 0
        seen_edges: set[tuple[str, str, str]] = set()
        ensured_targets: set[str] = set()

        for para in source_paragraphs:
            template_data = _normalize_template_data(para.get("template"))
            if not template_data:
                continue
            generalized = template_data.get("generalized") or template_data.get("generalized_pattern") or ""
            if not generalized:
                continue

            instances = _collect_paragraph_entity_values(template_data.get("slots"))
            if not instances:
                continue

            template_id = _generate_template_id(template_data, para.get("id") or "", attribution)

            for entity_key, props in instances.items():
                rule_set = entity_rules.get(entity_key) or {}
                for rule in rule_set.get("rules") or []:
                    if not isinstance(rule, dict):
                        continue
                    condition = rule.get("condition")
                    if not isinstance(condition, dict) or not _condition_matches(condition, props):
                        continue
                    matches += 1

                    for action in rule.get("actions") or []:
                        if not isinstance(action, dict) or action.get("type") != "create_edge":
                            skipped_actions += 1
                            continue
                        relation = _sanitize_relation_label(action.get("relation"))
                        target_key = str(action.get("target") or "").strip()
                        if not relation or not target_key:
                            skipped_actions += 1
                            continue

                        edge_key = (template_id, relation, target_key)
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)

                        target_id = f"entity_{target_key}"
                        if target_id not in ensured_targets:
                            target_meta = entity_rules.get(target_key) or {}
                            tx.run(
                                """
                                MERGE (e:EntitySchema {id: $entity_id})
                                ON CREATE SET
                                    e.entity_key = $entity_key,
                                    e.name = $name,
                                    e.category = $category,
                                    e.metadata_source = 'relation_rule',
                                    e.kb_id = $kb_id,
                                    e.created_at = datetime()
                                """,
                                entity_id=target_id,
                                entity_key=target_key,
                                name=target_meta.get("name") or target_key,
                                category=target_meta.get("category") or "",
                                kb_id=kb_id,
                            )
                            ensured_targets.add(target_id)

                        tx.run(
                            f"""
                            MATCH (pt:ParagraphTemplate {{id: $template_id}})
                            MATCH (t:EntitySchema {{id: $target_id}})
                            MERGE (pt)-[r:{relation}]->(t)
                            ON CREATE SET r.created_at = datetime()
                            SET r.rule_id = $rule_id,
                                r.rule_name = $rule_name,
                                r.source_entity = $source_entity,
                                r.matched_props = $matched_props
                            """,
                            template_id=template_id,
                            target_id=target_id,
                            rule_id=str(rule.get("rule_id") or ""),
                            rule_name=str(rule.get("rule_name") or ""),
                            source_entity=entity_key,
                            matched_props=json.dumps(condition, ensure_ascii=False),
                        )
                        edges += 1

        return {"edges": edges, "matches": matches, "skipped_actions": skipped_actions}

    # ------------------------------------------------------------------
    # 步骤4: LegalReference 节点（法律/法规/标准引用）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_legal_reference_nodes(
        tx,
        kb_id: str,
        doc_id: str,
        source_paragraphs: list[dict[str, Any]],
        section_map: dict[str, dict[str, Any]] | None = None,
        domain_code: str = "",
        report_type_code: str = "",
        attribution: str = "",
    ) -> dict:
        """创建 LegalReference，并按具体来源段落模板建立 CITES。

        引用来源由 source_para_id（缺失时回退承载段落）确定：有泛化模板的段落复用
        步骤2已建模板；法规清单等无泛化模板的段落物化为 TPL_SRC_* 来源专用模板，
        不挂 ParagraphRole，不进入普通模板推荐。来源段落或所属 Section 无法定位时
        跳过，禁止按知识库全量匹配模板。
        """
        if section_map is None:
            section_map = _section_id_map_from_paragraphs(source_paragraphs, doc_id)

        plan = plan_legal_citations(source_paragraphs, doc_id, section_map, attribution)
        nodes_created = 0
        relationships_created = 0
        citations_created = 0
        source_templates_created = 0

        for template_id, source in plan["templates"].items():
            result = tx.run(
                """
                MATCH (s:Section {id: $section_id})
                MERGE (pt:ParagraphTemplate {id: $template_id})
                ON CREATE SET
                    pt.id = $template_id,
                    pt.text_pattern = $text_pattern,
                    pt.generalized_pattern = '',
                    pt.classify_type = $classify_type,
                    pt.source_only = true,
                    pt.source_para_id = $source_para_id,
                    pt.domain = $domain_code,
                    pt.report_type = $report_type_code,
                    pt.kb_id = $kb_id,
                    pt.attribution = $attribution,
                    pt.created_at = datetime()
                ON MATCH SET
                    pt.text_pattern = $text_pattern,
                    pt.classify_type = $classify_type,
                    pt.source_para_id = $source_para_id,
                    pt.source_only = true,
                    pt.domain = COALESCE(pt.domain, $domain_code),
                    pt.report_type = COALESCE(pt.report_type, $report_type_code),
                    pt.kb_id = $kb_id,
                    pt.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE pt.attribution END
                MERGE (s)-[r:COMPOSED_OF]->(pt)
                ON CREATE SET r.order = $order
                """,
                section_id=source["section_id"],
                template_id=template_id,
                text_pattern=source["text_pattern"],
                classify_type=source["classify_type"],
                source_para_id=source["source_para_id"],
                domain_code=domain_code,
                report_type_code=report_type_code,
                kb_id=kb_id,
                attribution=attribution,
                order=source["order"],
            )
            counters = result.consume().counters
            nodes_created += counters.nodes_created
            relationships_created += counters.relationships_created
            source_templates_created += counters.nodes_created

        created_refs: set[str] = set()
        for citation in plan["citations"]:
            ref_id = citation["ref_id"]
            if ref_id in created_refs:
                continue
            created_refs.add(ref_id)
            ref = citation["ref"]
            result = tx.run(
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
                name=ref["name"],
                code=ref["code"],
                type=ref["type"],
                scope=ref["scope"],
                authority=ref["authority"],
                effective_date=ref["effective_date"],
                kb_id=kb_id,
            )
            nodes_created += result.consume().counters.nodes_created

        for citation in plan["citations"]:
            result = tx.run(
                """
                MATCH (pt:ParagraphTemplate {id: $template_id})
                MATCH (lr:LegalReference {id: $ref_id})
                MERGE (pt)-[:CITES]->(lr)
                """,
                template_id=citation["template_id"],
                ref_id=citation["ref_id"],
            )
            created = result.consume().counters.relationships_created
            citations_created += created
            relationships_created += created

        return {
            "nodes": nodes_created,
            "relationships": relationships_created,
            "citations_created": citations_created,
            "source_templates_created": source_templates_created,
            "planned_citations": len(plan["citations"]),
            "planned_source_templates": len(plan["templates"]),
            "skipped": plan["skipped"],
        }

    # ------------------------------------------------------------------
    # 步骤5: TableSchema 节点（表格结构模板）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_table_schema_nodes(
        tx,
        kb_id: str,
        doc_id: str,
        source_paragraphs: list[dict[str, Any]],
        section_map: dict[str, dict[str, Any]] | None = None,
        domain_code: str = "",
        report_type_code: str = "",
        project_name: str = "",
        region_key: str = "",
        scope: str = "",
        attribution: str = "",
    ) -> dict:
        """创建 TableSchema，并同时挂到精确 Section 与具体来源段落模板。"""
        if section_map is None:
            section_map = _section_id_map_from_paragraphs(source_paragraphs, doc_id)

        nodes_created = 0
        relationships_created = 0

        for position, para in enumerate(source_paragraphs, 1):
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

            section_path = para.get("section_path") or para.get("path") or []
            section_id = _find_target_section(section_path, section_map)
            if not section_id:
                continue

            template_id = _ensure_paragraph_template(
                tx,
                kb_id,
                doc_id,
                para,
                section_id,
                position,
                domain_code,
                report_type_code,
                attribution,
            )
            if not template_id:
                continue

            schema_id = f"TBL_{hashstr(f'{schema_name}_{table_type}|{attribution}', 12)}"
            result = tx.run(
                """
                MERGE (ts:TableSchema {id: $schema_id})
                ON CREATE SET
                    ts.id = $schema_id,
                    ts.name = $name,
                    ts.table_type = $table_type,
                    ts.columns = $columns,
                    ts.kb_id = $kb_id,
                    ts.project_name = $project_name,
                    ts.region_key = $region_key,
                    ts.scope = $scope,
                    ts.attribution = $attribution,
                    ts.created_at = datetime()
                ON MATCH SET
                    ts.name = COALESCE($name, ts.name),
                    ts.columns = COALESCE($columns, ts.columns)
                WITH ts
                MATCH (pt:ParagraphTemplate {id: $template_id})
                MATCH (s:Section {id: $section_id})
                MERGE (pt)-[:HAS_TABLE_SCHEMA]->(ts)
                MERGE (s)-[:HAS_TABLE_SCHEMA]->(ts)
                """,
                schema_id=schema_id,
                name=schema_name,
                table_type=table_type,
                columns=json.dumps(columns, ensure_ascii=False),
                template_id=template_id,
                section_id=section_id,
                kb_id=kb_id,
                project_name=project_name,
                region_key=region_key,
                scope=scope,
                attribution=attribution,
            )
            counters = result.consume().counters
            nodes_created += counters.nodes_created
            relationships_created += counters.relationships_created

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤8: 骨架聚合（DomainOutline / ChapterTemplate / ParagraphRole）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_skeleton_aggregation(
        tx, kb_id: str, domain_code: str, report_type_code: str,
        doc_id: str, doc_title: str, source_paragraphs: list[dict[str, Any]],
        document_key: str | None = None,
        project_name: str = "", region_key: str = "", scope: str = "", attribution: str = "",
    ) -> dict:
        """跨文档骨架聚合：创建 DomainOutline / ChapterTemplate / ParagraphRole 节点。

        聚合逻辑：
        1. 以 Document.document_key 去重，重算 DomainOutline.source_count
        2. 用 Document -[CONTAINS_CHAPTER]-> ChapterTemplate 记录文档章节成员
        3. 从成员关系重算 frequency/rigidity，而不是按构建次数累加
        4. 从 parameter 段落提取 ParagraphRole
        5. 重算 REALIZED_BY.frequency 为来源文档数
        """
        nodes_created = 0
        relationships_created = 0
        document_key = document_key or doc_id

        tx.run(
            """
            MATCH (d:Document {id: $doc_id})
            SET d.document_key = COALESCE(d.document_key, $document_key)
            """,
            doc_id=doc_id,
            document_key=document_key,
        )
        tx.run(
            "MATCH (d:Document {id: $doc_id})-[old:CONTAINS_CHAPTER]->() DELETE old",
            doc_id=doc_id,
        )
        tx.run(
            "MATCH (d:Document {id: $doc_id})-[old:CONTRIBUTES_TO]->() DELETE old",
            doc_id=doc_id,
        )

        # 1. DomainOutline 节点
        outline_id = f"OUTLINE_{domain_code}_{report_type_code}"
        if attribution:
            outline_id = f"{outline_id}_{attribution}"
        tx.run(
            """
            MERGE (dol:DomainOutline {id: $outline_id})
            ON CREATE SET
                dol.id = $outline_id,
                dol.domain = $domain_code,
                dol.report_type = $report_type_code,
                dol.source_count = 0,
                dol.last_updated = datetime(),
                dol.kb_id = $kb_id,
                dol.project_name = $project_name,
                dol.region_key = $region_key,
                dol.scope = $scope,
                dol.attribution = $attribution
            ON MATCH SET
                dol.last_updated = datetime(),
                dol.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE dol.attribution END
            """,
            outline_id=outline_id,
            domain_code=domain_code,
            report_type_code=report_type_code,
            kb_id=kb_id,
            project_name=project_name,
            region_key=region_key,
            scope=scope,
            attribution=attribution,
        )
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

        tx.run(
            """
            MATCH (dol:DomainOutline {id: $outline_id})<-[:CONTRIBUTES_TO]-(d:Document)
            WITH dol, count(DISTINCT COALESCE(d.document_key, d.id)) AS sc
            SET dol.source_count = sc
            """,
            outline_id=outline_id,
        )

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

            chapter_id = ""
            canonical_key = _derive_canonical_key(title)
            chapter_map[section_path_str] = {
                "chapter_id": chapter_id,
                "title": title,
                "canonical_key": canonical_key,
                "chapter_no": _derive_chapter_no(sp),
                "level": level,
                "order": order_int,
                "section_path_str": section_path_str,
            }

        # std 节点索引: (归一canonical, 父解析id, level) → std id，供身份键解析复用标准章节
        std_index: dict[tuple[str, str, int], str] = {}
        std_rows = tx.run(
            """
            MATCH (std:ChapterTemplate)
            WHERE std.id STARTS WITH $prefix AND std.domain = $domain AND std.report_type = $rt
            OPTIONAL MATCH (parent:ChapterTemplate)-[:HAS_CHILD]->(std)
            RETURN std.id AS id, std.canonical_chapter_key AS key, std.level AS level, parent.id AS parent_id
            """,
            prefix=f"CH_{domain_code}_{report_type_code}_std_",
            domain=domain_code,
            rt=report_type_code,
        )
        for row in std_rows:
            key = normalize_chapter_key(row["key"] or "")
            std_level = row["level"]
            if not key or std_level is None:
                continue
            std_index[(key, row["parent_id"] or "", int(std_level))] = row["id"]

        # 自根逐级解析聚合身份（父节点先于子节点），同构章节树跨文档解析出相同 id → MERGE 幂等
        for sp_str, ch_info in sorted(chapter_map.items(), key=lambda item: item[1]["level"]):
            level = ch_info["level"]

            # 父节点解析 id（level=1 挂 DomainOutline，父 id 记空串）
            sp_parts = sp_str.split("/")
            parent_sp_str = "/".join(sp_parts[:-1]) if len(sp_parts) > 1 else ""
            parent_resolved_id = chapter_map[parent_sp_str]["chapter_id"] if parent_sp_str in chapter_map else ""

            # 身份键解析：先复用 std，未命中落聚合键 id；回写映射供子章节 HAS_CHILD 与段落角色挂载
            chapter_id = resolve_chapter_id(
                domain_code,
                report_type_code,
                ch_info["canonical_key"],
                level,
                parent_resolved_id,
                std_index,
                attribution,
            )
            is_std_reuse = chapter_id.startswith(f"CH_{domain_code}_{report_type_code}_std_")
            chapter_map[sp_str]["chapter_id"] = chapter_id

            # std 命中复用：种子节点的 frequency/rigidity/meta 由 seed 体系所有，不参与语料覆盖重算。
            if not is_std_reuse:
                tx.run(
                    """
                    MERGE (ch:ChapterTemplate {id: $chapter_id})
                    ON CREATE SET
                        ch.id = $chapter_id,
                        ch.title = $title,
                        ch.chapter_no = $chapter_no,
                        ch.canonical_chapter_key = $canonical_key,
                        ch.level = $level,
                        ch.`order` = $order,
                        ch.frequency = 0.0,
                        ch.domain = $domain_code,
                        ch.report_type = $report_type_code,
                        ch.kb_id = $kb_id,
                        ch.project_name = $project_name,
                        ch.region_key = $region_key,
                        ch.scope = $scope,
                        ch.attribution = $attribution,
                        ch.created_at = datetime()
                    ON MATCH SET
                        ch.canonical_chapter_key = COALESCE(ch.canonical_chapter_key, $canonical_key),
                        ch.chapter_no = CASE
                            WHEN ch.chapter_no IS NULL OR ch.chapter_no = '' THEN $chapter_no
                            ELSE ch.chapter_no
                        END
                    """,
                    chapter_id=chapter_id,
                    title=ch_info["canonical_key"] or ch_info["title"].strip(),
                    chapter_no=ch_info["chapter_no"],
                    canonical_key=ch_info["canonical_key"],
                    level=level,
                    order=ch_info["order"],
                    domain_code=domain_code,
                    report_type_code=report_type_code,
                    kb_id=kb_id,
                    project_name=project_name,
                    region_key=region_key,
                    scope=scope,
                    attribution=attribution,
                )
            nodes_created += 1

            tx.run(
                """
                MATCH (d:Document {id: $doc_id})
                MATCH (ch:ChapterTemplate {id: $chapter_id})
                MERGE (d)-[:CONTAINS_CHAPTER]->(ch)
                """,
                doc_id=doc_id,
                chapter_id=chapter_id,
            )
            relationships_created += 1

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

            # 建立 ChapterTemplate 层级关系（HAS_CHILD，挂解析后节点）
            if parent_sp_str and parent_resolved_id:
                tx.run(
                    """
                    MATCH (parent:ChapterTemplate {id: $parent_id})
                    MATCH (child:ChapterTemplate {id: $child_id})
                    MERGE (parent)-[:HAS_CHILD]->(child)
                    """,
                    parent_id=parent_resolved_id,
                    child_id=chapter_id,
                )
                relationships_created += 1

        std_prefix = f"CH_{domain_code}_{report_type_code}_std_"
        tx.run(
            """
            MATCH (dol:DomainOutline {id: $outline_id})-[:HAS_CHAPTER]->(ch:ChapterTemplate)
            WHERE NOT ch.id STARTS WITH $std_prefix
            OPTIONAL MATCH (d:Document)-[:CONTAINS_CHAPTER]->(ch)
            WITH dol, ch, count(DISTINCT COALESCE(d.document_key, d.id)) AS covered
            SET ch.frequency = CASE
                    WHEN COALESCE(dol.source_count, 0) = 0 THEN 0.0
                    ELSE toFloat(covered) / dol.source_count
                END,
                ch.rigidity = CASE
                    WHEN COALESCE(dol.source_count, 0) = 0 THEN 'conditional'
                    WHEN toFloat(covered) / dol.source_count >= 0.9 THEN 'rigid'
                    WHEN toFloat(covered) / dol.source_count >= 0.5 THEN 'flexible'
                    ELSE 'conditional'
                END
            """,
            outline_id=outline_id,
            std_prefix=std_prefix,
        )

        # 3. ParagraphRole 节点（从散文段落提取段落角色，spec-W1 三值）
        para_order = 0
        for para in source_paragraphs:
            ct = para.get("classify_type", "")
            if ct not in ("prose", "parameter", "narrative"):  # spec-W1 散文三值
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

            role_id = f"ROLE_{hashstr(f'{target_ch_id}_{role_name}|{attribution}', 10)}"
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
                    pr.project_name = $project_name,
                    pr.region_key = $region_key,
                    pr.scope = $scope,
                    pr.attribution = $attribution,
                    pr.created_at = datetime()
                """,
                role_id=role_id,
                role_name=role_name,
                order=para_order,
                typical_length=f"{len(para.get('content', ''))}字",
                required_slots=json.dumps(required_slots, ensure_ascii=False),
                kb_id=kb_id,
                project_name=project_name,
                region_key=region_key,
                scope=scope,
                attribution=attribution,
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
                template_id = _generate_template_id(template_data, para.get("id", ""), attribution)
                quality_score = template.get("quality_score", 0.5)
                tx.run(
                    """
                    MATCH (pr:ParagraphRole {id: $role_id})
                    MATCH (pt:ParagraphTemplate {id: $template_id})
                    MERGE (pr)-[r:REALIZED_BY]->(pt)
                    ON CREATE SET r.confidence = $confidence, r.frequency = 0
                    """,
                    role_id=role_id,
                    template_id=template_id,
                    confidence=quality_score,
                )
                relationships_created += 1

        tx.run(
            """
            MATCH (dol:DomainOutline {id: $outline_id})-[:HAS_CHAPTER]->(:ChapterTemplate)
                  -[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
            MATCH (pr)-[r:REALIZED_BY]->(pt:ParagraphTemplate)
            OPTIONAL MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:COMPOSED_OF]->(pt)
            WITH r, count(DISTINCT COALESCE(d.document_key, d.id)) AS doc_count
            SET r.frequency = doc_count
            """,
            outline_id=outline_id,
        )

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤9: 逻辑关系节点（CausalChain / ConditionRule / DataFlow）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_logical_relationship_nodes(
        tx,
        kb_id: str,
        source_paragraphs: list[dict[str, Any]],
        base_info: dict,
        attribution: str = "",
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

            chain_id = f"CAUSAL_{hashstr(f'{cause_id}_{effect_id}|{attribution}', 10)}"
            tx.run(
                """
                MERGE (cc:CausalChain {id: $chain_id})
                ON CREATE SET
                    cc.id = $chain_id,
                    cc.relation = $relation,
                    cc.kb_id = $kb_id,
                    cc.attribution = $attribution,
                    cc.created_at = datetime()
                """,
                chain_id=chain_id,
                relation=relation,
                kb_id=kb_id,
                attribution=attribution,
            )
            nodes_created += 1

            # ParagraphTemplate -[CAUSES]-> CausalChain -> ParagraphTemplate
            # Build para_id -> template_id mapping from source_paragraphs
            cause_template_id = _find_template_id_for_para(cause_id, source_paragraphs, attribution)
            effect_template_id = _find_template_id_for_para(effect_id, source_paragraphs, attribution)
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

            cond_id = f"COND_{hashstr(f'{expression}_{consequence}|{attribution}', 10)}"
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
                    cr.attribution = $attribution,
                    cr.created_at = datetime()
                ON MATCH SET
                    cr.frequency = cr.frequency + 1,
                    cr.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE cr.attribution END
                """,
                cond_id=cond_id,
                expression=expression,
                consequence=consequence,
                kb_id=kb_id,
                attribution=attribution,
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

            flow_id = f"DFLOW_{hashstr(f'{para_id}_{source}|{attribution}', 10)}"
            tx.run(
                """
                MERGE (df:DataFlow {id: $flow_id})
                ON CREATE SET
                    df.id = $flow_id,
                    df.source = $source,
                    df.data_fields = $data_fields,
                    df.kb_id = $kb_id,
                    df.attribution = $attribution,
                    df.created_at = datetime()
                """,
                flow_id=flow_id,
                source=source,
                data_fields=(
                    json.dumps(data_fields, ensure_ascii=False)
                    if isinstance(data_fields, list)
                    else str(data_fields)
                ),
                kb_id=kb_id,
                attribution=attribution,
            )
            nodes_created += 1

            # ParagraphTemplate -[DERIVED_FROM]-> TableSchema or ParagraphTemplate
            if source.startswith("table"):
                tx.run(
                    """
                    MATCH (df:DataFlow {id: $flow_id})
                    MATCH (ts:TableSchema)
                    WHERE ts.kb_id = $kb_id AND ts.attribution = $attribution
                    WITH df, ts
                    LIMIT 1
                    MERGE (df)-[:SOURCED_FROM]->(ts)
                    """,
                    flow_id=flow_id,
                    kb_id=kb_id,
                    attribution=attribution,
                )
                relationships_created += 1

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤6: FormulaTemplate 节点（公式结构+变量映射）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_formula_template_nodes(
        tx,
        kb_id: str,
        doc_id: str,
        source_paragraphs: list[dict[str, Any]],
        section_map: dict[str, dict[str, Any]] | None = None,
        domain_code: str = "",
        report_type_code: str = "",
        project_name: str = "",
        region_key: str = "",
        scope: str = "",
        attribution: str = "",
    ) -> dict:
        """创建 FormulaTemplate、USES_VARIABLE，并挂到精确 Section 与来源段落模板。"""
        from pisuan.services.entity_meta_service import EntityMetaLoader

        if section_map is None:
            section_map = _section_id_map_from_paragraphs(source_paragraphs, doc_id)

        entity_meta = EntityMetaLoader().load()
        nodes_created = 0
        relationships_created = 0

        for position, para in enumerate(source_paragraphs, 1):
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
            formula_id = f"FORMULA_{hashstr(f'{original[:200]}|{attribution}', 12)}"

            section_path = para.get("section_path") or para.get("path") or []
            section_id = _find_target_section(section_path, section_map)
            if not section_id:
                continue

            template_id = _ensure_paragraph_template(
                tx,
                kb_id,
                doc_id,
                para,
                section_id,
                position,
                domain_code,
                report_type_code,
                attribution,
            )
            if not template_id:
                continue

            result = tx.run(
                """
                MERGE (f:FormulaTemplate {id: $formula_id})
                ON CREATE SET
                    f.id = $formula_id,
                    f.original = $original,
                    f.format = $format,
                    f.purpose = $purpose,
                    f.kb_id = $kb_id,
                    f.project_name = $project_name,
                    f.region_key = $region_key,
                    f.scope = $scope,
                    f.attribution = $attribution,
                    f.created_at = datetime()
                ON MATCH SET
                    f.purpose = COALESCE($purpose, f.purpose)
                WITH f
                MATCH (pt:ParagraphTemplate {id: $template_id})
                MATCH (s:Section {id: $section_id})
                MERGE (pt)-[:HAS_FORMULA]->(f)
                MERGE (s)-[:HAS_FORMULA]->(f)
                """,
                formula_id=formula_id,
                original=original[:500],
                format=fmt,
                purpose=purpose,
                template_id=template_id,
                section_id=section_id,
                kb_id=kb_id,
                project_name=project_name,
                region_key=region_key,
                scope=scope,
                attribution=attribution,
            )
            counters = result.consume().counters
            nodes_created += counters.nodes_created
            relationships_created += counters.relationships_created

            for var in variables:
                if not isinstance(var, dict):
                    continue
                sym = str(var.get("symbol") or "").strip()
                entity_ref = str(var.get("entity_ref") or "").strip()
                var_name = str(var.get("name") or sym).strip()
                var_unit = str(var.get("unit") or "").strip()
                var_type = str(var.get("type") or "").strip()
                if not var_name:
                    continue
                unresolved_entity_ref = ""
                if entity_ref and entity_ref not in entity_meta:
                    unresolved_entity_ref = entity_ref
                    entity_ref = ""
                slot_id = _generate_slot_id(var_name, var_type, var_unit, entity_ref, attribution)
                slot_result = tx.run(
                    """
                    MERGE (s:Slot {id: $slot_id})
                    ON CREATE SET
                        s.id = $slot_id,
                        s.name = $var_name,
                        s.type = $type,
                        s.unit = $unit,
                        s.entity_ref = $entity_ref,
                        s.unresolved_entity_ref = $unresolved_entity_ref,
                        s.signature_version = 2,
                        s.kb_id = $kb_id,
                        s.created_at = datetime()
                    ON MATCH SET
                        s.type = COALESCE(s.type, $type),
                        s.unit = COALESCE(s.unit, $unit),
                        s.entity_ref = COALESCE(s.entity_ref, $entity_ref),
                        s.unresolved_entity_ref = CASE
                            WHEN $unresolved_entity_ref <> '' THEN $unresolved_entity_ref
                            ELSE s.unresolved_entity_ref
                        END,
                        s.signature_version = 2
                    """,
                    slot_id=slot_id,
                    var_name=var_name,
                    type=var_type,
                    unit=var_unit,
                    entity_ref=entity_ref,
                    unresolved_entity_ref=unresolved_entity_ref,
                    kb_id=kb_id,
                )
                nodes_created += slot_result.consume().counters.nodes_created
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

        return {"nodes": nodes_created, "relationships": relationships_created}

    # ------------------------------------------------------------------
    # 步骤7: ProcessFlow 节点（图片多模态提取结果）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_process_flow_nodes(
        tx,
        kb_id: str,
        doc_id: str,
        source_paragraphs: list[dict[str, Any]],
        section_map: dict[str, dict[str, Any]] | None = None,
        attribution: str = "",
    ) -> dict:
        """为 figure 类型段落中的多模态提取结果创建 ProcessFlow / ProcessStep 节点。"""
        if section_map is None:
            section_map = _section_id_map_from_paragraphs(source_paragraphs, doc_id)

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

            flow_id = f"FLOW_{hashstr(f'{caption[:200]}|{attribution}', 12)}"
            if flow_id not in created_flows:
                tx.run(
                    """
                    MERGE (pf:ProcessFlow {id: $flow_id})
                    ON CREATE SET
                        pf.id = $flow_id,
                        pf.name = $caption,
                        pf.figure_type = $figure_type,
                        pf.kb_id = $kb_id,
                        pf.attribution = $attribution,
                        pf.created_at = datetime()
                    """,
                    flow_id=flow_id,
                    caption=caption,
                    figure_type=figure_type,
                    kb_id=kb_id,
                    attribution=attribution,
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

                section_path = para.get("section_path") or para.get("path") or []
                section_id = _find_target_section(section_path, section_map)
                if section_id:
                    tx.run(
                        """
                        MATCH (pf:ProcessFlow {id: $flow_id})
                        MATCH (s:Section {id: $section_id})
                        MERGE (s)-[:HAS_PROCESS_FLOW]->(pf)
                        """,
                        flow_id=flow_id,
                        section_id=section_id,
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


def _find_template_id_for_para(
    para_id: str, source_paragraphs: list[dict[str, Any]], attribution: str = ""
) -> str | None:
    """从 source_paragraphs 中找到段落的 template_id"""
    for para in source_paragraphs:
        if para.get("id") == para_id:
            template_data = _normalize_template_data(para.get("template"))
            if template_data and template_data.get("generalized"):
                return _generate_template_id(template_data, para_id, attribution)
    return None


def _generate_section_id(section_path: list, doc_id: str) -> str:
    """生成 Section 节点的唯一 ID"""
    if not section_path:
        return f"sec_{doc_id}_root"
    path_str = "/".join(str(p) for p in section_path)
    path_hash = hashstr(f"{doc_id}_{path_str}", 12)
    return f"sec_{doc_id}_{path_hash}"


def _generate_template_id(template_data: dict, chunk_id: str, attribution: str = "") -> str:
    """自动生成模板 ID（基于内容哈希，支持去重）"""
    existing_id = template_data.get("template_id")
    if existing_id:
        return f"{existing_id}_{attribution}" if attribution else existing_id

    generalized = template_data.get("generalized") or template_data.get("generalized_pattern") or ""
    slots = template_data.get("slots") or []
    slot_names = [s.get("name", "") for s in slots if isinstance(s, dict)]
    combined = f"{generalized}|{','.join(sorted(slot_names))}"
    if attribution:
        combined = f"{combined}|{attribution}"
    hash_value = hashstr(combined, 12)
    return f"TPL_PARA_{hash_value}"


def document_content_key(source_paragraphs: list[dict[str, Any]]) -> str:
    """按段落内容生成稳定文档身份；同一内容重复入库不产生新的统计口径。"""
    payload = json.dumps(source_paragraphs, ensure_ascii=False, sort_keys=True, default=str)
    return f"content_{hashstr(payload, 16)}"


def _generate_slot_id(
    slot_name: str,
    slot_type: str = "",
    unit: str = "",
    entity_ref: str = "",
    attribution: str = "",
) -> str:
    """按名称、类型、单位和实体引用生成插槽语义 ID。"""
    name = str(slot_name or "").strip()
    if not name:
        return ""
    signature = {
        "name": name,
        "type": str(slot_type or "").strip(),
        "unit": str(unit or "").strip(),
        "entity_ref": str(entity_ref or "").strip(),
        "attribution": attribution,
    }
    digest = hashstr(json.dumps(signature, ensure_ascii=False, sort_keys=True), 12)
    return f"SLOT_{digest}"


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


def _ensure_paragraph_template(
    tx,
    kb_id: str,
    doc_id: str,
    para: dict[str, Any],
    section_id: str,
    order: int,
    domain_code: str,
    report_type_code: str,
    attribution: str = "",
) -> str:
    """确保表格/公式段落有来源模板，并精确挂到当前文档 Section。"""
    template_data = _normalize_template_data(para.get("template"))
    generalized = str(
        template_data.get("generalized") or template_data.get("generalized_pattern") or ""
    ).strip()
    source_para_id = str(para.get("id") or "").strip()
    content = str(para.get("content") or "").strip()
    classify_type = str(para.get("classify_type") or "").strip()

    if generalized:
        template_id = _generate_template_id(template_data, source_para_id, attribution)
        text_pattern = generalized
        source_only = False
    else:
        if not source_para_id or not content:
            return ""
        template_id = generate_source_template_id(doc_id, source_para_id)
        text_pattern = content
        source_only = True

    tx.run(
        """
        MATCH (s:Section {id: $section_id})
        MERGE (pt:ParagraphTemplate {id: $template_id})
        ON CREATE SET
            pt.id = $template_id,
            pt.text_pattern = $text_pattern,
            pt.generalized_pattern = $generalized_pattern,
            pt.classify_type = $classify_type,
            pt.source_only = $source_only,
            pt.source_para_id = $source_para_id,
            pt.domain = $domain_code,
            pt.report_type = $report_type_code,
            pt.kb_id = $kb_id,
            pt.attribution = $attribution,
            pt.created_at = datetime()
        ON MATCH SET
            pt.text_pattern = COALESCE(pt.text_pattern, $text_pattern),
            pt.classify_type = COALESCE(pt.classify_type, $classify_type),
            pt.source_only = COALESCE(pt.source_only, $source_only),
            pt.domain = COALESCE(pt.domain, $domain_code),
            pt.report_type = COALESCE(pt.report_type, $report_type_code),
            pt.kb_id = COALESCE(pt.kb_id, $kb_id),
            pt.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE pt.attribution END
        MERGE (s)-[r:COMPOSED_OF]->(pt)
        ON CREATE SET r.order = $order
        """,
        section_id=section_id,
        template_id=template_id,
        text_pattern=text_pattern,
        generalized_pattern=generalized,
        classify_type=classify_type,
        source_only=source_only,
        source_para_id=source_para_id,
        domain_code=domain_code,
        report_type_code=report_type_code,
        kb_id=kb_id,
        attribution=attribution,
        order=order,
    )
    return template_id


def _create_slots_and_relationships(
    tx,
    template_id: str,
    slots: list[dict],
    kb_id: str,
    project_name: str = "",
    region_key: str = "",
    scope: str = "",
    attribution: str = "",
) -> dict:
    """创建 Slot 节点并建立关系

    如果插槽包含 entity_ref 字段（由 SlotEntityMapper 注入），
    会将实体引用写入 Slot 节点属性，方便图谱遍历查询。
    """
    nodes_created = 0
    relationships_created = 0

    for position, slot in enumerate(slots):
        slot_name = str(slot.get("name") or "").strip()
        if not slot_name:
            continue

        description = slot.get("description", "")
        slot_type = str(slot.get("type") or "").strip()
        required = slot.get("required", False)
        unit = str(slot.get("unit") or "").strip()
        entity_ref = str(slot.get("entity_ref") or "").strip()
        unresolved_entity_ref = str(slot.get("unresolved_entity_ref") or "").strip()
        slot_id = _generate_slot_id(slot_name, slot_type, unit, entity_ref, attribution)
        if not slot_id:
            continue

        # Slot 节点（含 entity_ref 实体引用）
        tx.run(
            """
            MERGE (s:Slot {id: $slot_id})
            ON CREATE SET
                s.id = $slot_id,
                s.name = $slot_name,
                s.description = $description,
                s.type = $slot_type,
                s.unit = $unit,
                s.required = $required,
                s.entity_ref = $entity_ref,
                s.unresolved_entity_ref = $unresolved_entity_ref,
                s.signature_version = 2,
                s.kb_id = $kb_id,
                s.project_name = $project_name,
                s.region_key = $region_key,
                s.scope = $scope,
                s.attribution = $attribution,
                s.created_at = datetime()
            ON MATCH SET
                s.description = COALESCE($description, s.description),
                s.type = COALESCE($slot_type, s.type),
                s.unit = COALESCE($unit, s.unit),
                s.required = COALESCE($required, s.required),
                s.entity_ref = COALESCE($entity_ref, s.entity_ref),
                s.unresolved_entity_ref = CASE
                    WHEN $unresolved_entity_ref <> '' THEN $unresolved_entity_ref
                    ELSE s.unresolved_entity_ref
                END,
                s.signature_version = 2,
                s.attribution = CASE WHEN $attribution <> '' THEN $attribution ELSE s.attribution END
            """,
            slot_id=slot_id,
            slot_name=slot_name,
            description=description,
            slot_type=slot_type,
            unit=unit,
            required=required,
            entity_ref=entity_ref,
            unresolved_entity_ref=unresolved_entity_ref,
            kb_id=kb_id,
            project_name=project_name,
            region_key=region_key,
            scope=scope,
            attribution=attribution,
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


def generate_source_template_id(doc_id: str, para_id: str) -> str:
    """生成来源专用段落模板 ID（按文档 + 段落稳定，不复用泛化模板身份）。"""
    return f"TPL_SRC_{hashstr(f'{doc_id}|{para_id}', 12)}"


def _section_id_map_from_paragraphs(source_paragraphs: list[dict[str, Any]], doc_id: str) -> dict:
    """按标题段落重建 section_path → Section id 映射，规则与步骤2建节一致。"""
    section_map: dict[str, dict[str, Any]] = {}
    for para in source_paragraphs:
        section_path = para.get("section_path") or para.get("path") or []
        if not isinstance(section_path, list) or not section_path:
            continue
        title = para.get("title", "")
        content = para.get("content") or ""
        section_title = title or (content[:500] if para.get("is_title") else "")
        if not section_title:
            continue
        path_str = "/".join(str(p) for p in section_path)
        section_map[path_str] = {
            "section_id": _generate_section_id(section_path, doc_id),
            "level": len(section_path),
        }
    return section_map


def plan_legal_citations(
    source_paragraphs: list[dict[str, Any]],
    doc_id: str,
    section_map: dict[str, dict[str, Any]],
    attribution: str = "",
) -> dict[str, Any]:
    """计算来源段落模板与法规引用之间的 CITES 边（纯函数，不访问数据库）。

    引用来源由 ref.source_para_id 决定，缺失时回退承载段落 id。来源段落有泛化
    模板时复用步骤2的 TPL_PARA_*；无泛化模板时生成 TPL_SRC_* 来源专用模板。
    来源段落、所属 Section 或引用本身不合法时跳过并计数，不做知识库级回退。
    """
    para_by_id = {
        str(para.get("id")): para
        for para in source_paragraphs
        if para.get("id")
    }
    templates: dict[str, dict[str, Any]] = {}
    citations: list[dict[str, Any]] = []
    skipped = {
        "missing_source_paragraph": 0,
        "missing_section": 0,
        "empty_source_content": 0,
        "invalid_reference": 0,
        "duplicate_citation": 0,
    }
    seen: set[tuple[str, str]] = set()

    for para_index, para in enumerate(source_paragraphs):
        template_data = _normalize_template_data(para.get("template"))
        refs = template_data.get("legal_references")
        if not isinstance(refs, list):
            continue

        for ref in refs:
            if not isinstance(ref, dict):
                skipped["invalid_reference"] += 1
                continue

            ref_name = str(ref.get("name") or "").strip()
            ref_code = str(ref.get("code") or "").strip()
            # 校验 name 合法性(长度≤100, 不含表格分隔符)，与旧实现保持一致
            if not ref_name or len(ref_name) > 100 or "|" in ref_name:
                skipped["invalid_reference"] += 1
                continue

            source_para_id = str(ref.get("source_para_id") or para.get("id") or "")
            source_para = para_by_id.get(source_para_id)
            if source_para is None:
                skipped["missing_source_paragraph"] += 1
                continue

            section_path = source_para.get("section_path") or source_para.get("path") or []
            section_id = _find_target_section(section_path, section_map)
            if not section_id:
                skipped["missing_section"] += 1
                continue

            source_template = _normalize_template_data(source_para.get("template"))
            generalized = source_template.get("generalized") or source_template.get("generalized_pattern") or ""
            content = (source_para.get("content") or "").strip()
            if not content:
                skipped["empty_source_content"] += 1
                continue

            if generalized:
                template_id = _generate_template_id(source_template, source_para_id, attribution)
            else:
                template_id = generate_source_template_id(doc_id, source_para_id)
                templates.setdefault(
                    template_id,
                    {
                        "section_id": section_id,
                        "order": para_index + 1,
                        "text_pattern": content,
                        "classify_type": source_para.get("classify_type", ""),
                        "source_para_id": source_para_id,
                    },
                )

            ref_key = f"{ref_name}_{ref_code}" if ref_code else ref_name
            ref_id = f"LEGAL_{hashstr(ref_key, 12)}"
            citation_key = (template_id, ref_id)
            if citation_key in seen:
                skipped["duplicate_citation"] += 1
                continue
            seen.add(citation_key)
            citations.append(
                {
                    "template_id": template_id,
                    "ref_id": ref_id,
                    "source_para_id": source_para_id,
                    "ref": {
                        "name": ref_name,
                        "code": ref_code,
                        "type": ref.get("type", "technical_standard"),
                        "scope": ref.get("scope", "national"),
                        "authority": ref.get("authority", ""),
                        "effective_date": ref.get("effective_date", ""),
                    },
                }
            )

    return {"templates": templates, "citations": citations, "skipped": skipped}


def load_document_section_map(session, doc_id: str) -> dict[str, dict[str, Any]]:
    """从图中读取文档实际 Section 的 section_path → id 映射（供存量重算）。"""
    result = session.run(
        """
        MATCH (d:Document {id: $doc_id})-[:HAS_SECTION]->(s:Section)
        RETURN s.id AS section_id, s.section_path AS section_path
        """,
        doc_id=doc_id,
    )
    section_map: dict[str, dict[str, Any]] = {}
    for record in result:
        raw_path = record["section_path"]
        if isinstance(raw_path, str):
            try:
                section_path = json.loads(raw_path)
            except (json.JSONDecodeError, TypeError):
                continue
        else:
            section_path = raw_path
        if not isinstance(section_path, list) or not section_path:
            continue
        path_str = "/".join(str(p) for p in section_path)
        section_map[path_str] = {"section_id": record["section_id"]}
    return section_map
