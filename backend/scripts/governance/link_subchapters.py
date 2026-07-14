"""存量 ETL 子章节归一化: 按标题匹配标准子章节, 建 HAS_CHILD, 归一化 canonical_chapter_key。

用法:
  python -m scripts.governance.link_subchapters --dry-run   # 预览
  python -m scripts.governance.link_subchapters             # 执行
"""

from __future__ import annotations

import argparse

from neo4j import GraphDatabase

DOMAIN = "coal"
REPORT_TYPE = "eia_report"


def match_etl_to_standard(etl_title: str, std_subs: list[dict]) -> dict | None:
    """将 ETL 子章节标题匹配到标准子章节。

    匹配策略(优先级递减):
    1. 精确匹配: ETL标题 == 标准key
    2. 包含匹配: ETL标题包含标准key(或反向)
    3. 无匹配: 返回 None
    """
    etl = (etl_title or "").strip()
    if not etl:
        return None
    # 1. 精确匹配
    for s in std_subs:
        if etl == s["key"]:
            return s
    # 2. 包含匹配(双向)
    for s in std_subs:
        if s["key"] in etl or etl in s["key"]:
            return s
    return None


def link(driver, dry_run: bool = False) -> dict:
    """对每个 ETL level=2 子章节, 匹配标准子章节并建 HAS_CHILD + 归一化 key。

    返回统计: {matched, unmatched, normalized}
    """
    stats = {"matched": 0, "unmatched": 0, "normalized": 0}
    with driver.session() as session:
        # 查所有标准子章节(level=2, std_ 前缀)
        std_result = session.run(
            "MATCH (s:ChapterTemplate) WHERE s.id STARTS WITH 'CH_coal_eia_report_std_' "
            "AND s.level = 2 "
            "RETURN s.id AS sub_id, s.canonical_chapter_key AS key, s.title AS title"
        )
        std_subs = [
            {"sub_id": r["sub_id"], "key": r["key"], "title": r["title"]}
            for r in std_result
        ]

        # 查所有 ETL level=2 子章节(非 std_)
        etl_result = session.run(
            "MATCH (ch:ChapterTemplate {domain: $d, report_type: $rt}) "
            "WHERE ch.level = 2 AND NOT ch.id STARTS WITH 'CH_coal_eia_report_std_' "
            "RETURN ch.id AS etl_id, ch.title AS title, ch.canonical_chapter_key AS key",
            d=DOMAIN,
            rt=REPORT_TYPE,
        )
        for rec in etl_result:
            etl_title = rec["title"] or ""
            match = match_etl_to_standard(etl_title, std_subs)
            if match:
                stats["matched"] += 1
                if not dry_run:
                    session.run(
                        "MATCH (std:ChapterTemplate {id: $std_id}) "
                        "MATCH (etl:ChapterTemplate {id: $etl_id}) "
                        "MERGE (std)-[:HAS_CHILD]->(etl) "
                        "SET etl.canonical_chapter_key = $key",
                        std_id=match["sub_id"],
                        etl_id=rec["etl_id"],
                        key=match["key"],
                    )
                    if rec["key"] != match["key"]:
                        stats["normalized"] += 1
            else:
                stats["unmatched"] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description="存量 ETL 子章节归一化关联")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uri", default="bolt://graph:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="0123456789")
    args = parser.parse_args()
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    stats = link(driver, dry_run=args.dry_run)
    driver.close()
    mode = "dry-run" if args.dry_run else "执行"
    print(f"模式: {mode}")
    print(f"匹配: {stats['matched']}, 未匹配: {stats['unmatched']}, 归一化: {stats['normalized']}")


if __name__ == "__main__":
    main()
