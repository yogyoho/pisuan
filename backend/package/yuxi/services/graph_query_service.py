"""图谱查询服务:封装 Cypher,供工具直查 Neo4j 图谱。"""

from __future__ import annotations

import os
from typing import Any

from neo4j import GraphDatabase


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
                RETURN DISTINCT ch.canonical_chapter_key AS key
                ORDER BY key
                """,
                domain=domain,
                rt=report_type,
            )
            return [r["key"] for r in result if r["key"]]
