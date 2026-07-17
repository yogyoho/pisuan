"""确定性 Neo4j 图谱写入: RegDocument → RegUnit → Indicator"""

from __future__ import annotations

import os
from typing import Any

from neo4j import GraphDatabase as Neo4jDriver

from yuxi.utils import logger


class RegulationGraphWriter:
    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is not None:
            return self._driver
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "0123456789")
        try:
            self._driver = Neo4jDriver.driver(uri, auth=(username, password))
            with self._driver.session() as session:
                session.run("RETURN 1")
            return self._driver
        except Exception as e:
            logger.warning(f"RegulationGraphWriter: Neo4j 连接失败: {e}")
            return None

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def write_document_graph(
        self,
        doc_code: str,
        doc_name: str,
        doc_type: str,
        units: list[dict[str, Any]],
        indicators: list[dict[str, Any]],
    ) -> dict[str, int]:
        """幂等写入单个规范文档的图谱结构"""
        driver = self._get_driver()
        if driver is None:
            return {"nodes": 0, "relationships": 0}

        stats = {"nodes": 0, "relationships": 0}
        with driver.session() as session:
            session.run(
                "MERGE (d:RegDocument {doc_code: $code}) SET d.name = $name, d.doc_type = $dtype",
                code=doc_code,
                name=doc_name,
                dtype=doc_type,
            )
            stats["nodes"] += 1

            for u in units:
                unit_id = f"{doc_code}#{u['unit_no']}"
                session.run(
                    "MERGE (u:RegUnit {id: $uid}) "
                    "SET u.unit_no = $no, u.unit_type = $utype, u.title = $title, "
                    "    u.chunk_id = $chunk_id, u.doc_code = $code "
                    "WITH u MATCH (d:RegDocument {doc_code: $code}) "
                    "MERGE (d)-[:HAS_UNIT]->(u)",
                    uid=unit_id,
                    no=u["unit_no"],
                    utype=u["unit_type"],
                    title=u.get("title", ""),
                    chunk_id=u.get("chunk_id", ""),
                    code=doc_code,
                )
                stats["nodes"] += 1
                stats["relationships"] += 1
                if u.get("parent_unit"):
                    session.run(
                        "MATCH (p:RegUnit {id: $pid}), (c:RegUnit {id: $cid}) MERGE (p)-[:HAS_CHILD]->(c)",
                        pid=f"{doc_code}#{u['parent_unit']}",
                        cid=unit_id,
                    )
                    stats["relationships"] += 1

            for ind in indicators:
                ind_id = f"{doc_code}#{ind.get('unit_no', '')}#{ind['pollutant']}#{ind['metric']}"
                session.run(
                    "MERGE (i:Indicator {id: $iid}) "
                    "SET i.pollutant = $p, i.metric = $m, i.limit_value = $v, "
                    "    i.unit = $u, i.condition = $c "
                    "WITH i MATCH (ru:RegUnit {id: $uid}) "
                    "MERGE (ru)-[:HAS_INDICATOR]->(i)",
                    iid=ind_id,
                    p=ind["pollutant"],
                    m=ind["metric"],
                    v=ind.get("limit_value"),
                    u=ind.get("unit", ""),
                    c=ind.get("condition", ""),
                    uid=f"{doc_code}#{ind.get('unit_no', '')}",
                )
                stats["nodes"] += 1
                stats["relationships"] += 1

        return stats
