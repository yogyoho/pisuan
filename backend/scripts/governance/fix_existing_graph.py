"""存量图谱数据治理脚本(幂等)。

修复:
1. 合并 report_type='通用' 分支到 eia_report
2. 清洗 ChapterTemplate.title 双编号
3. 回填 ChapterTemplate.canonical_chapter_key
4. 回填 ParagraphTemplate.canonical_chapter_key(通过 Section 反查 ChapterTemplate)

用法:
  python -m scripts.governance.fix_existing_graph --dry-run   # 预览
  python -m scripts.governance.fix_existing_graph             # 执行
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass


def clean_chapter_title(title: str) -> str:
    """清洗章节标题:去所有前导编号(双编号/单编号),只留纯标题。纯编号返回空。"""
    text = (title or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)*", text):
        return ""
    # 反复去掉前导"数字.数字. "直到剩下纯标题
    while True:
        m = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", text)
        if not m:
            break
        text = m.group(2).strip()
    return text


def derive_canonical_key(clean_title: str) -> str:
    """从清洗后的标题推导 canonical_chapter_key(目前等于标题本身)。"""
    return (clean_title or "").strip()


@dataclass
class GovernanceReport:
    fixed_keys: int = 0
    fixed_para_keys: int = 0
    merged_branches: int = 0
    cleaned_titles: int = 0


class GraphGovernance:
    """存量图谱治理器。dry_run=True 时只统计不写入。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.report = GovernanceReport()

    def merge_general_branch(self, driver) -> None:
        """Step 1: 合并 coal/通用 → coal/eia_report。"""
        with driver.session() as session:
            result = session.run(
                "MATCH (d:DomainOutline {domain:'coal', report_type:'通用'})"
                "-[:HAS_CHAPTER]->(ch:ChapterTemplate) "
                "RETURN count(ch) AS cnt"
            )
            rec = result.single()
            count = rec["cnt"] if rec else 0

            if self.dry_run:
                self.report.merged_branches = count
                return

            session.run(
                "MATCH (ch:ChapterTemplate {domain:'coal', report_type:'通用'}) SET ch.report_type = 'eia_report'"
            )
            # 去重:相同 (domain, report_type, canonical_chapter_key) 的 ChapterTemplate 只保留一条。
            # 分步迁移关系(保留关系类型),再删除重复节点。
            session.run(
                """
                MATCH (ch:ChapterTemplate {domain:'coal', report_type:'eia_report'})
                WHERE ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                WITH ch.canonical_chapter_key AS key, collect(ch) AS nodes
                WHERE size(nodes) > 1
                UNWIND nodes[1..] AS dup
                WITH nodes[0] AS keep, dup
                MATCH (dup)-[:HAS_CHILD]->(sub:ChapterTemplate)
                MERGE (keep)-[:HAS_CHILD]->(sub)
                """
            )
            session.run(
                """
                MATCH (ch:ChapterTemplate {domain:'coal', report_type:'eia_report'})
                WHERE ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                WITH ch.canonical_chapter_key AS key, collect(ch) AS nodes
                WHERE size(nodes) > 1
                UNWIND nodes[1..] AS dup
                WITH nodes[0] AS keep, dup
                MATCH (dup)-[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
                MERGE (keep)-[:REQUIRES_PARAGRAPH_ROLE]->(pr)
                """
            )
            session.run(
                """
                MATCH (ch:ChapterTemplate {domain:'coal', report_type:'eia_report'})
                WHERE ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                WITH ch.canonical_chapter_key AS key, collect(ch) AS nodes
                WHERE size(nodes) > 1
                UNWIND nodes[1..] AS dup
                DETACH DELETE dup
                """
            )
            session.run("MATCH (d:DomainOutline {domain:'coal', report_type:'通用'}) DETACH DELETE d")
            self.report.merged_branches = count

    def clean_titles(self, driver) -> None:
        """Step 2: 清洗 ChapterTemplate.title。"""
        with driver.session() as session:
            result = session.run(
                "MATCH (ch:ChapterTemplate) WHERE ch.title IS NOT NULL RETURN ch.id AS id, ch.title AS title"
            )
            for record in result:
                original = record["title"]
                cleaned = clean_chapter_title(original)
                if cleaned != original and not self.dry_run:
                    session.run(
                        "MATCH (ch:ChapterTemplate {id:$id}) SET ch.title = $title",
                        id=record["id"],
                        title=cleaned,
                    )
                if cleaned != original:
                    self.report.cleaned_titles += 1

    def backfill_keys(self, driver) -> None:
        """Step 3: 回填 canonical_chapter_key。"""
        with driver.session() as session:
            result = session.run(
                "MATCH (ch:ChapterTemplate) "
                "WHERE ch.canonical_chapter_key IS NULL OR ch.canonical_chapter_key = '' "
                "RETURN ch.id AS id, ch.title AS title"
            )
            for record in result:
                key = derive_canonical_key(clean_chapter_title(record["title"]))
                if key and not self.dry_run:
                    session.run(
                        "MATCH (ch:ChapterTemplate {id:$id}) SET ch.canonical_chapter_key = $key",
                        id=record["id"],
                        key=key,
                    )
                if key:
                    self.report.fixed_keys += 1

    def backfill_para_keys(self, driver) -> None:
        """Step 4: 回填 ParagraphTemplate.canonical_chapter_key。

        通过 Section(COMPOSED_OF) 反查所属 ChapterTemplate：
        Section.title 带双编号(如 '1.1.1 3.1.1 地形地貌')，ChapterTemplate.canonical_chapter_key
        是纯标题(如 '地形地貌')，用 ENDS WITH 匹配。匹配不到时从 Section/Chapter title 推导。
        """
        with driver.session() as session:
            result = session.run(
                """
                MATCH (pt:ParagraphTemplate)
                WHERE pt.canonical_chapter_key IS NULL OR pt.canonical_chapter_key = ''
                OPTIONAL MATCH (s:Section)-[:COMPOSED_OF]->(pt)
                WITH pt, s
                OPTIONAL MATCH (ch:ChapterTemplate)
                WHERE ch.canonical_chapter_key IS NOT NULL
                  AND ch.canonical_chapter_key <> ''
                  AND s IS NOT NULL
                  AND s.title ENDS WITH ch.canonical_chapter_key
                RETURN pt.id AS pt_id,
                       collect(DISTINCT ch.canonical_chapter_key) AS ch_keys,
                       collect(DISTINCT ch.title) AS ch_titles
                """
            )
            for record in result:
                pt_id = record["pt_id"]
                ch_keys = [k for k in (record["ch_keys"] or []) if k]
                ch_titles = [t for t in (record["ch_titles"] or []) if t]
                if ch_keys:
                    key = ch_keys[0]
                elif ch_titles:
                    key = derive_canonical_key(clean_chapter_title(ch_titles[0]))
                else:
                    key = ""
                if key and not self.dry_run:
                    session.run(
                        "MATCH (pt:ParagraphTemplate {id:$id}) SET pt.canonical_chapter_key = $key",
                        id=pt_id,
                        key=key,
                    )
                if key:
                    self.report.fixed_para_keys += 1

    def run_all(self, driver) -> GovernanceReport:
        """执行全部治理步骤。"""
        self.merge_general_branch(driver)
        self.clean_titles(driver)
        self.backfill_keys(driver)
        self.backfill_para_keys(driver)
        return self.report


def main():
    parser = argparse.ArgumentParser(description="存量图谱治理(幂等)")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    parser.add_argument("--uri", default="bolt://graph:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j 用户名")
    parser.add_argument("--password", default="0123456789", help="Neo4j 密码")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    gov = GraphGovernance(dry_run=args.dry_run)

    print(f"模式: {'dry-run(预览)' if args.dry_run else '执行'}")
    report = gov.run_all(driver)
    driver.close()

    print("\n========== 治理报告 ==========")
    print(f"合并'通用'分支章节数: {report.merged_branches}")
    print(f"清洗 title 数: {report.cleaned_titles}")
    print(f"回填 canonical_key 数: {report.fixed_keys}")
    print(f"回填 ParagraphTemplate key 数: {report.fixed_para_keys}")
    print("==============================")


if __name__ == "__main__":
    main()
