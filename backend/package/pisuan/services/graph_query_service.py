"""图谱查询服务:封装 Cypher,供工具直查 Neo4j 图谱。"""

from __future__ import annotations

import json
import os
from typing import Any

from neo4j import GraphDatabase


def _parse_json_field(value: Any) -> list[str] | None:
    """Neo4j 存的 JSON 字符串解析为 list, None/空返回 None。"""
    if not value:
        return None
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _chapter_scope_filter(
    alias: str,
    domain: str,
    report_type: str,
    attribution: str = "",
    kb_id: str = "",
) -> tuple[str, dict[str, Any]]:
    """章节节点归属过滤：有归属按归属键，否则按知识库；std 种子始终共享。"""
    if attribution:
        return (
            f" AND ({alias}.attribution = $attribution OR {alias}.id STARTS WITH $std_prefix)",
            {"attribution": attribution, "std_prefix": f"CH_{domain}_{report_type}_std_"},
        )
    if kb_id:
        return (
            f" AND ({alias}.kb_id = $kb_id OR {alias}.id STARTS WITH $std_prefix)",
            {"kb_id": kb_id, "std_prefix": f"CH_{domain}_{report_type}_std_"},
        )
    return "", {}


def _template_scope_filter(alias: str, attribution: str = "", kb_id: str = "") -> tuple[str, dict[str, Any]]:
    """段落模板归属过滤：模板不共享，命中归属/知识库才返回。"""
    if attribution:
        return f" AND {alias}.attribution = $attribution", {"attribution": attribution}
    if kb_id:
        return f" AND {alias}.kb_id = $kb_id", {"kb_id": kb_id}
    return "", {}


def _render_cypher(template: str, **parts: str) -> str:
    """按 __NAME__ 占位符注入过滤片段，避免 f-string 误解析 Cypher 的 map 花括号。"""
    for name, value in parts.items():
        template = template.replace(f"__{name.upper()}__", value)
    return template


def flatten_leaf_sections(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把章节节点展开为叶子节，保留完整父路径与稳定节点身份。"""
    by_id = {node["id"]: dict(node) for node in nodes if node.get("id")}
    for node in by_id.values():
        node["_children"] = []

    roots: list[dict[str, Any]] = []
    for node in by_id.values():
        parent_id = node.get("parent_id")
        if parent_id is None:
            roots.append(node)
        else:
            parent = by_id.get(parent_id)
            if parent is None:
                raise ValueError(f"ChapterTemplate 层级断链: {node['id']} -> {parent_id}")
            parent["_children"].append(node)

    def sort_key(node: dict[str, Any]) -> tuple[bool, int, str, str]:
        order = node.get("order")
        return (order is None, order if order is not None else 0, node.get("chapter_no") or "", node["id"])

    for node in by_id.values():
        node["_children"].sort(key=sort_key)
    roots.sort(key=sort_key)

    leaves: list[dict[str, Any]] = []
    walked: set[str] = set()

    def walk(node: dict[str, Any], ancestors: tuple[str, ...]) -> None:
        section_key = node["id"]
        if section_key in ancestors:
            raise ValueError(f"ChapterTemplate 层级存在环: {section_key}")
        canonical = node.get("canonical_chapter_key") or node.get("title") or section_key
        path = (*ancestors, canonical)
        walked.add(section_key)
        children = node["_children"]
        if children:
            for child in children:
                walk(child, path)
            return
        leaves.append(
            {
                "section_key": section_key,
                "canonical_chapter_key": canonical,
                "title": node.get("title") or canonical,
                "chapter_no": node.get("chapter_no"),
                "level": node.get("level"),
                "order": node.get("order"),
                "path": list(path),
                "parent_section_key": node.get("parent_id"),
                "is_leaf": True,
            }
        )

    for root in roots:
        walk(root, ())
    if by_id and len(walked) != len(by_id):
        raise ValueError("ChapterTemplate 层级存在环")
    return leaves


class GraphQueryService:
    """查询知识图谱的 ChapterTemplate/ParagraphTemplate/Slot/LegalReference。

    替代工具层对 DB 的直接查询,图谱作为单一数据源。
    """

    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://graph:7687")
        user = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "0123456789")
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    async def list_chapter_keys(
        self, domain: str, report_type: str, *, attribution: str = "", kb_id: str = ""
    ) -> list[str]:
        """列出某 domain+report_type 下所有 canonical_chapter_key(去重、非空)。"""
        scope_filter, scope_params = _chapter_scope_filter("ch", domain, report_type, attribution, kb_id)
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt})
                WHERE ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                  AND ch.level = 1
                  __SCOPE_FILTER__
                RETURN DISTINCT ch.canonical_chapter_key AS key, ch.`order` AS ord
                ORDER BY ord
                """,
                    scope_filter=scope_filter,
                ),
                domain=domain,
                rt=report_type,
                **scope_params,
            )
            return [r["key"] for r in result if r["key"]]

    async def list_leaf_sections(
        self, domain: str, report_type: str, *, attribution: str = "", kb_id: str = ""
    ) -> list[dict[str, Any]]:
        """列出叶子章节，返回稳定 section_key、完整路径和章节定位信息。"""
        scope_filter, scope_params = _chapter_scope_filter("ch", domain, report_type, attribution, kb_id)
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt})
                WHERE ch.id IS NOT NULL
                  AND ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                  __SCOPE_FILTER__
                OPTIONAL MATCH (parent:ChapterTemplate)-[:HAS_CHILD]->(ch)
                RETURN ch.id AS id, ch.canonical_chapter_key AS canonical_chapter_key,
                       ch.title AS title, ch.chapter_no AS chapter_no, ch.level AS level,
                       ch.`order` AS `order`, parent.id AS parent_id
                ORDER BY ch.level, ch.`order`, ch.id
                """,
                    scope_filter=scope_filter,
                ),
                domain=domain,
                rt=report_type,
                **scope_params,
            )
            nodes = [dict(record) for record in result]
        return flatten_leaf_sections(nodes)

    async def get_chapter_outline(
        self,
        domain: str,
        report_type: str,
        canonical_key: str,
        *,
        attribution: str = "",
        kb_id: str = "",
    ) -> dict[str, Any] | None:
        """查询单个章节大纲,含子章节和段落角色预览。

        canonical_key 支持 "canonical||level" 复合格式(list_outline_templates 返回)，
        按 (canonical, level) 精确匹配；纯 canonical 时按 canonical 匹配(向后兼容)。
        同 canonical 多节点并存时确定性选取:std 种子节点优先,其次按 id 升序(与 update_chapter_template 同款)。
        """
        parts = (canonical_key or "").split("||")
        canonical = parts[0]
        level = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        scope_filter, scope_params = _chapter_scope_filter("ch", domain, report_type, attribution, kb_id)
        child_filter, child_params = _chapter_scope_filter("sub", domain, report_type, attribution, kb_id)
        role_filter = ""
        role_params: dict[str, Any] = {}
        if attribution:
            role_filter, role_params = " AND pr.attribution = $attribution", {"attribution": attribution}
        elif kb_id:
            role_filter, role_params = " AND pr.kb_id = $kb_id", {"kb_id": kb_id}
        query_params = {**scope_params, **child_params, **role_params}
        with self._driver.session() as session:
            if level is not None:
                result = session.run(
                    _render_cypher(
                        """
                    MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key, level: $lvl})
                    WHERE true __SCOPE_FILTER__
                    WITH ch
                    ORDER BY CASE WHEN ch.id STARTS WITH $std_prefix THEN 0 ELSE 1 END, ch.id
                    LIMIT 1
                    OPTIONAL MATCH (ch)-[:HAS_CHILD]->(sub:ChapterTemplate)
                    WHERE true __CHILD_FILTER__
                    OPTIONAL MATCH (ch)-[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
                    WHERE true __ROLE_FILTER__
                    RETURN ch.canonical_chapter_key AS key, ch.title AS title,
                           ch.level AS level, ch.`order` AS `order`,
                           ch.rigidity AS rigidity, ch.frequency AS frequency,
                           ch.content_contract AS content_contract,
                           ch.purpose AS purpose,
                           ch.key_points AS key_points,
                           ch.regulations AS regulations,
                           ch.writing_hints AS writing_hints,
                           ch.extraction_regex AS extraction_regex,
                           ch.expected_tables AS expected_tables,
                           ch.expected_charts AS expected_charts,
                           ch.expected_formulas AS expected_formulas,
                           collect(DISTINCT {title: sub.title, key: sub.canonical_chapter_key,
                                             chapter_no: sub.chapter_no}) AS children,
                           collect(DISTINCT pr.name) AS roles
                    """,
                        scope_filter=scope_filter,
                        child_filter=child_filter,
                        role_filter=role_filter,
                    ),
                    domain=domain, rt=report_type, key=canonical, lvl=level,
                    std_prefix=f"CH_{domain}_{report_type}_std_",
                    **query_params,
                )
            else:
                result = session.run(
                    _render_cypher(
                        """
                    MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                    WHERE true __SCOPE_FILTER__
                    WITH ch
                    ORDER BY CASE WHEN ch.id STARTS WITH $std_prefix THEN 0 ELSE 1 END, ch.id
                    LIMIT 1
                OPTIONAL MATCH (ch)-[:HAS_CHILD]->(sub:ChapterTemplate)
                WHERE true __CHILD_FILTER__
                OPTIONAL MATCH (ch)-[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
                WHERE true __ROLE_FILTER__
                RETURN ch.canonical_chapter_key AS key, ch.title AS title,
                       ch.level AS level, ch.`order` AS `order`,
                       ch.rigidity AS rigidity, ch.frequency AS frequency,
                       ch.content_contract AS content_contract,
                       ch.purpose AS purpose,
                       ch.key_points AS key_points,
                       ch.regulations AS regulations,
                       ch.writing_hints AS writing_hints,
                       ch.extraction_regex AS extraction_regex,
                       ch.expected_tables AS expected_tables,
                       ch.expected_charts AS expected_charts,
                       ch.expected_formulas AS expected_formulas,
                       collect(DISTINCT {title: sub.title, key: sub.canonical_chapter_key,
                                         chapter_no: sub.chapter_no}) AS children,
                       collect(DISTINCT pr.name) AS roles
                """,
                    scope_filter=scope_filter,
                    child_filter=child_filter,
                    role_filter=role_filter,
                ),
                domain=domain,
                rt=report_type,
                key=canonical,
                std_prefix=f"CH_{domain}_{report_type}_std_",
                **query_params,
            )
            rec = result.single()
            if rec is None or rec["key"] is None:
                return None
            return {
                "canonical_chapter_key": rec["key"],
                "title": rec["title"],
                "level": rec["level"],
                "order": rec["order"],
                "rigidity": rec["rigidity"],
                "frequency": rec["frequency"],
                "content_contract": rec["content_contract"],
                "purpose": rec["purpose"],
                "key_points": _parse_json_field(rec["key_points"]),
                "regulations": _parse_json_field(rec["regulations"]),
                "writing_hints": rec["writing_hints"],
                "extraction_regex": rec["extraction_regex"],
                "expected_tables": _parse_json_field(rec["expected_tables"]),
                "expected_charts": _parse_json_field(rec["expected_charts"]),
                "expected_formulas": _parse_json_field(rec["expected_formulas"]),
                "child_chapters": [c for c in rec["children"] if c and c.get("title")],
                "paragraph_roles": [r for r in (rec["roles"] or []) if r],
            }

    @staticmethod
    def _derive_content_contract(key_points: list[str] | None, expected_tables: list[str] | None) -> dict[str, Any] | None:
        """从 key_points / expected_tables 推导初始 content_contract。

        供治理脚本回填 content_contract 到图谱节点时使用。
        两者均为空时返回 None(无推导依据)。
        """
        kp = key_points or []
        et = expected_tables or []
        if not kp and not et:
            return None
        return {
            "key_elements": list(kp),
            "structure_type": "narrative_text",
        }

    async def get_templates(
        self,
        domain: str,
        report_type: str,
        canonical_key: str | None = None,
        *,
        section_key: str | None = None,
        attribution: str = "",
        kb_id: str = "",
    ) -> list[dict[str, Any]]:
        """查询某章节下的段落模板,含 Slot 和 LegalReference。

        section_key 精确匹配章节节点，只返回该节点段落角色关联的模板；
        canonical_key 保留旧的按名称递归查询，同名跨父路径时不保证唯一。
        顶级章节无模板时递归查子章节(HAS_CHILD*1..3),去重返回。
        """
        if section_key:
            return self._query_section_templates(
                domain, report_type, section_key, attribution=attribution, kb_id=kb_id
            )
        if not canonical_key:
            return []
        templates = self._query_templates(domain, report_type, canonical_key, attribution=attribution, kb_id=kb_id)
        if templates:
            return templates
        child_keys = self._query_child_canonical_keys(
            domain, report_type, canonical_key, attribution=attribution, kb_id=kb_id
        )
        all_templates = []
        seen_patterns: set[str] = set()
        for child_key in child_keys:
            for t in self._query_templates(
                domain, report_type, child_key, attribution=attribution, kb_id=kb_id
            ):
                pattern = t.get("text_pattern", "")
                if pattern and pattern not in seen_patterns:
                    seen_patterns.add(pattern)
                    all_templates.append(t)
        return all_templates

    def _query_templates(
        self, domain: str, report_type: str, canonical_key: str, *, attribution: str = "", kb_id: str = ""
    ) -> list[dict[str, Any]]:
        """查询单个 canonical_chapter_key 的段落模板(不递归)。"""
        chapter_filter, chapter_params = _chapter_scope_filter(
            "ch", domain, report_type, attribution, kb_id
        )
        template_filter, template_params = _template_scope_filter("pt", attribution, kb_id)
        query_params = {**chapter_params, **template_params}
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                WHERE true __CHAPTER_FILTER__
                MATCH (pt:ParagraphTemplate {
                    canonical_chapter_key: $key,
                    domain: $domain,
                    report_type: $rt
                })
                WHERE true __TEMPLATE_FILTER__
                OPTIONAL MATCH (pt)-[:HAS_SLOT]->(s:Slot)
                OPTIONAL MATCH (s)-[:CONSTRAINS]->(es:EntitySchema)
                OPTIONAL MATCH (pt)-[:CITES]->(lr:LegalReference)
                RETURN pt.id AS pt_id, pt.text_pattern AS pattern,
                       collect(DISTINCT {name: s.name, type: s.type, entity: es.name}) AS slots,
                       collect(DISTINCT {code: lr.code, name: lr.name}) AS refs
                """,
                    chapter_filter=chapter_filter,
                    template_filter=template_filter,
                ),
                domain=domain,
                rt=report_type,
                key=canonical_key,
                **query_params,
            )
            templates = []
            for rec in result:
                pattern = rec["pattern"]
                if not pattern:
                    continue
                slots = [
                    {"name": s["name"], "type": s["type"], "entity_ref": s["entity"]}
                    for s in rec["slots"]
                    if s and s.get("name")
                ]
                refs = [{"code": r["code"], "name": r["name"]} for r in rec["refs"] if r and r.get("code")]
                templates.append(
                    {
                        "text_pattern": pattern,
                        "slots": slots,
                        "legal_references": refs,
                    }
                )
            return templates

    def _query_section_templates(
        self, domain: str, report_type: str, section_key: str, *, attribution: str = "", kb_id: str = ""
    ) -> list[dict[str, Any]]:
        """按章节节点精确查询模板，模板元数据携带所属叶子节身份。"""
        chapter_filter, chapter_params = _chapter_scope_filter(
            "ch", domain, report_type, attribution, kb_id
        )
        template_filter, template_params = _template_scope_filter("pt", attribution, kb_id)
        query_params = {**chapter_params, **template_params}
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, id: $section_key})
                WHERE true __CHAPTER_FILTER__
                MATCH (ch)-[:REQUIRES_PARAGRAPH_ROLE]->(:ParagraphRole)-[:REALIZED_BY]->(pt:ParagraphTemplate)
                WHERE pt.domain = $domain AND pt.report_type = $rt __TEMPLATE_FILTER__
                OPTIONAL MATCH (pt)-[:HAS_SLOT]->(s:Slot)
                OPTIONAL MATCH (s)-[:CONSTRAINS]->(es:EntitySchema)
                OPTIONAL MATCH (pt)-[:CITES]->(lr:LegalReference)
                RETURN pt.id AS pt_id, pt.text_pattern AS pattern,
                       ch.id AS section_key, ch.canonical_chapter_key AS canonical_chapter_key,
                       ch.title AS chapter_title, ch.chapter_no AS chapter_no, ch.level AS section_level,
                       collect(DISTINCT {name: s.name, type: s.type, entity: es.name}) AS slots,
                       collect(DISTINCT {code: lr.code, name: lr.name}) AS refs
                ORDER BY pt_id
                """,
                    chapter_filter=chapter_filter,
                    template_filter=template_filter,
                ),
                domain=domain,
                rt=report_type,
                section_key=section_key,
                **query_params,
            )
            templates = []
            for rec in result:
                pattern = rec["pattern"]
                if not pattern:
                    continue
                slots = [
                    {"name": slot["name"], "type": slot["type"], "entity_ref": slot["entity"]}
                    for slot in rec["slots"]
                    if slot and slot.get("name")
                ]
                refs = [{"code": ref["code"], "name": ref["name"]} for ref in rec["refs"] if ref and ref.get("code")]
                templates.append(
                    {
                        "template_id": rec["pt_id"],
                        "text_pattern": pattern,
                        "slots": slots,
                        "legal_references": refs,
                        "section_key": rec["section_key"],
                        "canonical_chapter_key": rec["canonical_chapter_key"],
                        "chapter_title": rec["chapter_title"],
                        "chapter_no": rec["chapter_no"],
                        "section_level": rec["section_level"],
                    }
                )
            return templates

    def _query_child_canonical_keys(
        self, domain: str, report_type: str, canonical_key: str, *, attribution: str = "", kb_id: str = ""
    ) -> list[str]:
        """查询某章节的所有子章节 canonical_chapter_key(去重, HAS_CHILD*1..3)。"""
        chapter_filter, chapter_params = _chapter_scope_filter(
            "ch", domain, report_type, attribution, kb_id
        )
        child_filter, child_params = _chapter_scope_filter(
            "sub", domain, report_type, attribution, kb_id
        )
        query_params = {**chapter_params, **child_params}
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                WHERE true __CHAPTER_FILTER__
                OPTIONAL MATCH (ch)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
                WHERE sub.canonical_chapter_key IS NOT NULL AND sub.canonical_chapter_key <> ''
                  __CHILD_FILTER__
                RETURN DISTINCT sub.canonical_chapter_key AS key
                """,
                    chapter_filter=chapter_filter,
                    child_filter=child_filter,
                ),
                domain=domain, rt=report_type, key=canonical_key,
                **query_params,
            )
            return [r["key"] for r in result if r["key"]]

    async def list_outline_templates(
        self, domain: str, report_type: str, *, attribution: str = "", kb_id: str = ""
    ) -> list[dict[str, Any]]:
        """列出大纲模板完整目录树(含子章节),供页面左侧树形展示。

        查所有 std_ 节点(不限 level) + HAS_CHILD 父子关系,按 level/order 构建树。
        返回根节点列表,每个节点含 {key, title, order, level, children, ...}。
        """
        chapter_filter, chapter_params = _chapter_scope_filter(
            "ch", domain, report_type, attribution, kb_id
        )
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt})
                WHERE true __CHAPTER_FILTER__
                OPTIONAL MATCH (parent)-[:HAS_CHILD]->(ch)
                WITH ch, parent
                ORDER BY ch.level, ch.`order`
                RETURN ch.canonical_chapter_key AS key, ch.title AS title,
                       ch.`order` AS `order`, ch.level AS level,
                       ch.chapter_no AS chapter_no,
                       ch.frequency AS frequency, ch.rigidity AS rigidity,
                       ch.purpose AS purpose, ch.content_contract AS content_contract,
                       parent.canonical_chapter_key AS parent_key, parent.level AS parent_level
                """,
                    chapter_filter=chapter_filter,
                ),
                domain=domain, rt=report_type,
                **chapter_params,
            )
            # 用 (canonical, level) 作内部 key，避免同 canonical 跨 level 合并错乱；
            # 返回的 node.key 编码为 "canonical||level" 保证前端唯一 + 可回查。
            nodes: dict[tuple[str, int], dict[str, Any]] = {}
            roots: list[dict[str, Any]] = []
            for r in result:
                canonical = r["key"]
                level = r["level"]
                if not canonical:
                    continue
                nkey = (canonical, level)
                if nkey in nodes:
                    continue
                cc = r["content_contract"]
                if isinstance(cc, str):
                    try:
                        cc = json.loads(cc)
                    except (json.JSONDecodeError, TypeError):
                        cc = None
                node = {
                    "key": f"{canonical}||{level}",
                    "title": r["title"] or canonical,
                    "order": r["order"],
                    "level": level,
                    "chapter_no": r["chapter_no"],
                    "frequency": r["frequency"],
                    "rigidity": r["rigidity"],
                    "is_universal": r["rigidity"] == "rigid",
                    "purpose_preview": (r["purpose"] or "")[:80],
                    "content_contract_summary": {
                        "required_count": len((cc or {}).get("required_elements", [])),
                        "optional_count": len((cc or {}).get("optional_elements", [])),
                        "total_reports": (cc or {}).get("total_reports", 0),
                    } if cc else None,
                    "children": [],
                }
                nodes[nkey] = node
                pk = r["parent_key"]
                pl = r["parent_level"]
                if pk is not None and pl is not None and (pk, pl) in nodes:
                    nodes[(pk, pl)]["children"].append(node)
                else:
                    roots.append(node)
            return roots

    async def update_chapter_template(
        self,
        domain: str,
        report_type: str,
        canonical_key: str,
        updates: dict[str, Any],
        *,
        attribution: str = "",
        kb_id: str = "",
    ) -> bool:
        """更新章节模板字段，按 (canonical, level) 身份匹配（与 get_chapter_outline 同款拆分）。"""
        import json as _json

        allowed_fields = {
            "purpose", "key_points", "writing_hints", "regulations",
            "content_contract", "extraction_regex",
            "expected_tables", "expected_charts", "expected_formulas",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return False

        # chapter_key 支持 "canonical||level" 复合格式(list_outline_templates 返回)，纯 canonical 时不限 level
        parts = (canonical_key or "").split("||")
        canonical = parts[0]
        level = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

        set_clauses = []
        params: dict[str, Any] = {"domain": domain, "rt": report_type, "key": canonical}
        if level is not None:
            params["lvl"] = level
        for field, value in filtered.items():
            if field in ("key_points", "regulations", "expected_tables", "expected_charts", "expected_formulas", "content_contract"):
                params[field] = _json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
            else:
                params[field] = value
            set_clauses.append(f"ch.{field} = ${field}")

        level_clause = "AND ch.level = $lvl" if level is not None else ""
        scope_clause = ""
        if attribution:
            scope_clause = "AND ch.attribution = $attribution"
            params["attribution"] = attribution
        elif kb_id:
            scope_clause = "AND ch.kb_id = $kb_id"
            params["kb_id"] = kb_id
        # 与 GET 同款确定性选取:同 canonical 多节点时只更新 std 优先的那个,保证保存→刷新读回同一节点
        params["std_prefix"] = f"CH_{domain}_{report_type}_std_"
        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH (ch:ChapterTemplate)
                WHERE ch.domain = $domain AND ch.report_type = $rt
                  AND ch.canonical_chapter_key = $key
                  {level_clause}
                  {scope_clause}
                WITH ch
                ORDER BY CASE WHEN ch.id STARTS WITH $std_prefix THEN 0 ELSE 1 END, ch.id
                LIMIT 1
                SET {', '.join(set_clauses)}
                RETURN count(ch) AS cnt
                """,
                **params,
            )
            rec = result.single()
            return rec is not None and rec["cnt"] > 0

    async def lookup_chapter_order(
        self, domain: str, report_type: str, canonical_key: str, *, attribution: str = "", kb_id: str = ""
    ) -> int | None:
        """查询章节顺序号。"""
        chapter_filter, chapter_params = _chapter_scope_filter(
            "ch", domain, report_type, attribution, kb_id
        )
        with self._driver.session() as session:
            result = session.run(
                _render_cypher(
                    """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                WHERE true __CHAPTER_FILTER__
                RETURN ch.`order` AS `order`
                ORDER BY ch.`order`, ch.id
                LIMIT 1
                """,
                    chapter_filter=chapter_filter,
                ),
                domain=domain,
                rt=report_type,
                key=canonical_key,
                **chapter_params,
            )
            rec = result.single()
            if rec is None:
                return None
            order = rec["order"]
            return int(order) if order is not None else None
