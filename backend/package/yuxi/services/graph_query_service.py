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

        通过先 MATCH ChapterTemplate(domain+report_type+key) 确认该 key 属于
        指定 domain/report_type,再 MATCH ParagraphTemplate —— 避免多 domain
        入库后返回其他 domain 的同名章节模板。
        """
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
