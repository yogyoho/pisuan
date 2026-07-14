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

    async def list_chapter_keys(self, domain: str, report_type: str) -> list[str]:
        """列出某 domain+report_type 下所有 canonical_chapter_key(去重、非空)。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt})
                WHERE ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                  AND ch.level = 1
                RETURN DISTINCT ch.canonical_chapter_key AS key, ch.`order` AS ord
                ORDER BY ord
                """,
                domain=domain,
                rt=report_type,
            )
            return [r["key"] for r in result if r["key"]]

    async def get_chapter_outline(self, domain: str, report_type: str, canonical_key: str) -> dict[str, Any] | None:
        """查询单个章节大纲,含子章节和段落角色预览。

        content_contract 字段从图谱节点属性读取(治理回填后存在);
        节点暂无此属性时返回 None,留好字段位置供后续填充。
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                WITH ch LIMIT 1
                OPTIONAL MATCH (ch)-[:HAS_CHILD]->(sub:ChapterTemplate)
                OPTIONAL MATCH (ch)-[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
                RETURN ch.canonical_chapter_key AS key, ch.title AS title,
                       ch.level AS level, ch.`order` AS `order`,
                       ch.rigidity AS rigidity, ch.frequency AS frequency,
                       ch.content_contract AS content_contract,
                       ch.purpose AS purpose,
                       ch.key_points AS key_points,
                       ch.regulations AS regulations,
                       ch.writing_hints AS writing_hints,
                       collect(DISTINCT {title: sub.title, key: sub.canonical_chapter_key}) AS children,
                       collect(DISTINCT pr.name) AS roles
                """,
                domain=domain,
                rt=report_type,
                key=canonical_key,
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

    async def get_templates(self, domain: str, report_type: str, canonical_key: str) -> list[dict[str, Any]]:
        """查询某章节下的段落模板,含 Slot 和 LegalReference。

        顶级章节无模板时递归查子章节(HAS_CHILD*1..3),去重返回。
        """
        templates = self._query_templates(domain, report_type, canonical_key)
        if templates:
            return templates
        child_keys = self._query_child_canonical_keys(domain, report_type, canonical_key)
        all_templates = []
        seen_patterns: set[str] = set()
        for child_key in child_keys:
            for t in self._query_templates(domain, report_type, child_key):
                pattern = t.get("text_pattern", "")
                if pattern and pattern not in seen_patterns:
                    seen_patterns.add(pattern)
                    all_templates.append(t)
        return all_templates

    def _query_templates(self, domain: str, report_type: str, canonical_key: str) -> list[dict[str, Any]]:
        """查询单个 canonical_chapter_key 的段落模板(不递归)。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                MATCH (pt:ParagraphTemplate {canonical_chapter_key: $key})
                OPTIONAL MATCH (pt)-[:HAS_SLOT]->(s:Slot)
                OPTIONAL MATCH (s)-[:CONSTRAINS]->(es:EntitySchema)
                OPTIONAL MATCH (pt)-[:CITES]->(lr:LegalReference)
                RETURN pt.id AS pt_id, pt.text_pattern AS pattern,
                       collect(DISTINCT {name: s.name, type: s.type, entity: es.name}) AS slots,
                       collect(DISTINCT {code: lr.code, name: lr.name}) AS refs
                """,
                domain=domain,
                rt=report_type,
                key=canonical_key,
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

    def _query_child_canonical_keys(self, domain: str, report_type: str, canonical_key: str) -> list[str]:
        """查询某章节的所有子章节 canonical_chapter_key(去重, HAS_CHILD*1..3)。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                OPTIONAL MATCH (ch)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
                WHERE sub.canonical_chapter_key IS NOT NULL AND sub.canonical_chapter_key <> ''
                RETURN DISTINCT sub.canonical_chapter_key AS key
                """,
                domain=domain, rt=report_type, key=canonical_key,
            )
            return [r["key"] for r in result if r["key"]]

    async def list_outline_templates(self, domain: str, report_type: str) -> list[dict[str, Any]]:
        """列出13章大纲模板概要(用于页面左侧列表)。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, level: 1})
                WHERE ch.id STARTS WITH 'CH_' + $domain + '_' + $rt + '_std_'
                RETURN ch.canonical_chapter_key AS key, ch.title AS title,
                       ch.`order` AS `order`, ch.purpose AS purpose,
                       ch.content_contract AS content_contract
                ORDER BY ch.`order`
                """,
                domain=domain, rt=report_type,
            )
            items = []
            for r in result:
                cc = r["content_contract"]
                if isinstance(cc, str):
                    try:
                        cc = json.loads(cc)
                    except (json.JSONDecodeError, TypeError):
                        cc = None
                items.append({
                    "key": r["key"],
                    "title": r["title"],
                    "order": r["order"],
                    "purpose_preview": (r["purpose"] or "")[:80],
                    "content_contract_summary": {
                        "required_count": len((cc or {}).get("required_elements", [])),
                        "optional_count": len((cc or {}).get("optional_elements", [])),
                        "total_reports": (cc or {}).get("total_reports", 0),
                    } if cc else None,
                })
            return items

    async def update_chapter_template(self, domain: str, report_type: str, canonical_key: str, updates: dict[str, Any]) -> bool:
        """更新标准章节节点的模板字段。"""
        import json as _json

        allowed_fields = {
            "purpose", "key_points", "writing_hints", "regulations",
            "content_contract", "extraction_regex",
            "expected_tables", "expected_charts", "expected_formulas",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return False

        set_clauses = []
        params: dict[str, Any] = {}
        for field, value in filtered.items():
            if field in ("key_points", "regulations", "expected_tables", "expected_charts", "expected_formulas", "content_contract"):
                params[field] = _json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
            else:
                params[field] = value
            set_clauses.append(f"ch.{field} = ${field}")

        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH (ch:ChapterTemplate)
                WHERE ch.domain = $domain AND ch.report_type = $rt
                  AND ch.canonical_chapter_key = $key
                  AND ch.level = 1
                  AND ch.id STARTS WITH 'CH_' + $domain + '_' + $rt + '_std_'
                SET {', '.join(set_clauses)}
                RETURN ch.id AS id
                """,
                domain=domain, rt=report_type, key=canonical_key, **params,
            )
            return result.single() is not None

    async def lookup_chapter_order(self, domain: str, report_type: str, canonical_key: str) -> int | None:
        """查询章节顺序号。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                RETURN ch.`order` AS `order`
                """,
                domain=domain,
                rt=report_type,
                key=canonical_key,
            )
            rec = result.single()
            if rec is None:
                return None
            order = rec["order"]
            return int(order) if order is not None else None
