"""去领域化图谱侧存量迁移：ChapterTemplate / DomainOutline 的 domain 'coal' → 'general'，并重写内嵌域的节点 id。

设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md §4.1 的图谱侧补遗——
plans/2026-10-29-dedomain-behavioral.md Task 6 只覆盖 PG 7 表，漏掉 Neo4j，导致
去领域化上线后大纲模板页面（list_outline_templates 按 domain='general' 查图谱）
返回空目录，页面显示「无匹配章节」。

迁移内容:
  1. ChapterTemplate: n.domain → 'general'；id 前缀 'CH_coal_' → 'CH_general_'
     （level-1 std id 与 ETL 哈希 id 内嵌域；level-2 std id 形如 std_{p}_{s} 不含域，仅改 domain 属性）
  2. DomainOutline: n.domain → 'general'；id 前缀 'OUTLINE_coal_' → 'OUTLINE_general_'
     （骨架聚合按 id MERGE，不改则下次构建分裂出第二个投影节点）
  3. HAS_CHILD / HAS_CHAPTER / CONTRIBUTES_TO 等关系连接节点本体，不受 id 属性重写影响，无需处理
  4. Document 节点无按域读取（读取均按 id/kb_id），domain 属性一并收敛保持图内零 coal 残留

幂等可重跑：所有步骤以 domain='coal' 或旧前缀 id 存在为前提，重跑即零动作。
默认 dry-run 只统计；--apply 才落写。

用法（容器内 backend 工作目录）:
  python -m scripts.governance.dedomain_chapter_templates_graph            # dry-run 预览（默认）
  python -m scripts.governance.dedomain_chapter_templates_graph --apply    # 执行落写
"""

from __future__ import annotations

import argparse
import json

OLD_DOMAIN = "coal"
NEW_DOMAIN = "general"
# id 前缀重写规则：(旧前缀, 新前缀)。前缀互不重叠，先计数后写库与先后顺序均不影响结果。
ID_PREFIX_REWRITES = (
    (f"CH_{OLD_DOMAIN}_", f"CH_{NEW_DOMAIN}_"),
    (f"OUTLINE_{OLD_DOMAIN}_", f"OUTLINE_{NEW_DOMAIN}_"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="执行落写（缺省 dry-run 只统计）")
    parser.add_argument("--uri", default="bolt://graph:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j 用户名")
    parser.add_argument("--password", default="0123456789", help="Neo4j 密码")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    report: dict[str, object] = {"mode": "apply" if args.apply else "dry-run"}
    try:
        with driver.session() as session:
            # 迁移前状态：旧域节点分布
            report["before"] = session.run(
                "MATCH (n) WHERE n.domain = $old RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY label",
                old=OLD_DOMAIN,
            ).data()

            # 冲突守卫：新前缀 id 已被非旧域节点占用 → 混合状态（防半迁移下覆盖重名）
            collisions = session.run(
                "MATCH (n) WHERE n.id STARTS WITH $p AND n.domain <> $old RETURN count(*) AS cnt",
                p=f"CH_{NEW_DOMAIN}_", old=OLD_DOMAIN,
            ).single()["cnt"]
            if collisions:
                report["collision_guard"] = (
                    f"发现 {collisions} 个已占用的新前缀 id，疑似半迁移状态"
                    + ("，中止。请人工核查。" if args.apply else "（dry-run 仅提示）")
                )
                if args.apply:
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                    raise SystemExit(1)

            # ① id 前缀重写：replace() 整串替换，不做 substring 索引算术
            # （本栈 Neo4j 的 substring 起始索引实测 0 基，size+1 算式会多删一位——bug-4175）
            renamed: dict[str, int] = {}
            for old_prefix, new_prefix in ID_PREFIX_REWRITES:
                renamed[old_prefix] = session.run(
                    "MATCH (n) WHERE n.id STARTS WITH $old AND n.domain = $old_domain "
                    "RETURN count(*) AS cnt",
                    old=old_prefix, old_domain=OLD_DOMAIN,
                ).single()["cnt"]
                if args.apply:
                    session.run(
                        "MATCH (n) WHERE n.id STARTS WITH $old AND n.domain = $old_domain "
                        "SET n.id = replace(n.id, $old, $new)",
                        old=old_prefix, new=new_prefix, old_domain=OLD_DOMAIN,
                    )
            report["id_rewritten"] = renamed

            # ② domain 属性收敛（剩余未改 id 的节点如 std_{p}_{s} 子章节也在此覆盖）
            report["domain_set"] = session.run(
                "MATCH (n) WHERE n.domain = $old RETURN count(*) AS cnt", old=OLD_DOMAIN,
            ).single()["cnt"]
            if args.apply:
                session.run(
                    "MATCH (n) WHERE n.domain = $old SET n.domain = $new",
                    old=OLD_DOMAIN, new=NEW_DOMAIN,
                )

            # 迁移后校验：新域两类节点数量 + 旧域残留（dry-run 时与迁移前同值）
            report["after"] = session.run(
                "MATCH (n) WHERE n.domain = $new AND labels(n)[0] IN ['ChapterTemplate', 'DomainOutline'] "
                "RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY label",
                new=NEW_DOMAIN,
            ).data()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
