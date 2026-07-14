"""补充13章标准结构 ChapterTemplate 到图谱（幂等）。

环评导则 HJ/T 130-2019 规定的13章标准结构，作为顶级章节模板，
确保 get_chapter_outline("环境影响识别") 等标准章节名能命中。

用法:
  python -m scripts.seed_standard_chapters --dry-run   # 预览
  python -m scripts.seed_standard_chapters             # 执行
"""

from __future__ import annotations

import argparse

from neo4j import GraphDatabase

STANDARD_CHAPTERS = [
    ("总则", 1),
    ("规划方案概况及分析", 2),
    ("区域自然和社会经济概况", 3),
    ("矿区开发环境影响回顾性评价", 4),
    ("环境影响识别与评价指标体系", 5),
    ("规划实施环境影响预测与评价", 6),
    ("矿区资源、环境承载力分析", 7),
    ("规划方案综合论证及优化调整建议", 8),
    ("规划实施环境影响减缓措施", 9),
    ("环境管理、监测计划与跟踪评价", 10),
    ("矿区清洁生产与循环经济分析", 11),
    ("公众参与", 12),
    ("结论与建议", 13),
]

DOMAIN = "coal"
REPORT_TYPE = "eia_report"
OUTLINE_ID = f"OUTLINE_{DOMAIN}_{REPORT_TYPE}"


def seed(driver, dry_run: bool = False) -> int:
    count = 0
    with driver.session() as session:
        # 确保 DomainOutline 存在
        session.run(
            "MERGE (dol:DomainOutline {id: $id}) "
            "SET dol.domain = $domain, dol.report_type = $rt",
            id=OUTLINE_ID, domain=DOMAIN, rt=REPORT_TYPE,
        )

        for title, order in STANDARD_CHAPTERS:
            chapter_id = f"CH_{DOMAIN}_{REPORT_TYPE}_std_{order}"
            if dry_run:
                count += 1
                continue
            session.run(
                """
                MERGE (ch:ChapterTemplate {id: $chapter_id})
                ON CREATE SET
                    ch.id = $chapter_id,
                    ch.title = $title,
                    ch.canonical_chapter_key = $title,
                    ch.level = 1,
                    ch.`order` = $order,
                    ch.rigidity = 'rigid',
                    ch.frequency = 1.0,
                    ch.domain = $domain,
                    ch.report_type = $rt,
                    ch.created_at = datetime()
                ON MATCH SET
                    ch.canonical_chapter_key = COALESCE(ch.canonical_chapter_key, $title),
                    ch.title = $title,
                    ch.`order` = $order
                """,
                chapter_id=chapter_id, title=title, order=order,
                domain=DOMAIN, rt=REPORT_TYPE,
            )
            session.run(
                """
                MATCH (dol:DomainOutline {id: $outline_id})
                MATCH (ch:ChapterTemplate {id: $chapter_id})
                MERGE (dol)-[:HAS_CHAPTER]->(ch)
                """,
                outline_id=OUTLINE_ID, chapter_id=chapter_id,
            )
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="补充13章标准结构到图谱")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uri", default="bolt://graph:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="0123456789")
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    count = seed(driver, dry_run=args.dry_run)
    driver.close()
    print(f"模式: {'dry-run' if args.dry_run else '执行'}")
    print(f"标准章节处理数: {count}")


if __name__ == "__main__":
    main()
