"""从 outlines/ MD 的写作骨架段解析标准子章节, seed 到图谱作为 level=2 合并锚点。

用法:
  python -m scripts.seed_standard_subchapters --dry-run   # 预览
  python -m scripts.seed_standard_subchapters             # 执行
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from neo4j import GraphDatabase

OUTLINES_DIR = (
    Path(__file__).resolve().parent.parent
    / "package"
    / "yuxi"
    / "agents"
    / "skills"
    / "buildin"
    / "coal-eia-writer"
    / "outlines"
)
DOMAIN = "coal"
REPORT_TYPE = "eia_report"


def parse_skeleton(md_text: str, parent_order: int) -> list[dict]:
    """解析写作骨架段, 提取 level=2 标准子章节。

    格式:
      5.1 环境影响识别        ← level=2 子章节(无前导空格, 两级编号)
        5.1.1 识别方法        ← level=3 细节(有前导空格, 跳过)
    """
    m = re.search(r"## 写作骨架\s*\n(.*?)(?=\n## |\Z)", md_text, re.DOTALL)
    if not m:
        return []
    skeleton = m.group(1)
    subs: list[dict] = []
    for line in skeleton.strip().split("\n"):
        line = line.rstrip()
        if not line:
            continue
        # level=2 行: "5.1 环境影响识别" (无前导空格, 两级编号)
        m2 = re.match(r"^(\d+)\.(\d+)\s+(.+)$", line)
        if not m2:
            continue
        parent_num = int(m2.group(1))
        sub_num = int(m2.group(2))
        title_text = m2.group(3).strip()
        if parent_num != parent_order:
            continue
        key = _derive_key(title_text)
        subs.append(
            {
                "parent_order": parent_order,
                "sub_order": sub_num,
                "key": key,
                "title": f"{parent_order}.{sub_num} {title_text}",
            }
        )
    return subs


def _derive_key(title: str) -> str:
    """从子章节标题推导 canonical_chapter_key(去编号的纯标题)。"""
    text = title.strip()
    m = re.match(r"^\d+(?:\.\d+)*\s+(.+)$", text)
    if m:
        text = m.group(1)
    return text.strip()


def _build_standard_subchapters() -> list[dict]:
    """从全部13章 outlines/ MD 解析标准子章节。"""
    all_subs: list[dict] = []
    for order in range(1, 14):
        md_files = list(OUTLINES_DIR.glob(f"ch{order:02d}-*.md"))
        if not md_files:
            continue
        text = md_files[0].read_text(encoding="utf-8")
        subs = parse_skeleton(text, parent_order=order)
        all_subs.extend(subs)
    return all_subs


STANDARD_SUBCHAPTERS = _build_standard_subchapters()


def seed(driver, dry_run: bool = False) -> int:
    """将标准子章节 seed 到图谱, 并建 HAS_CHILD 关系到标准父章节。"""
    count = 0
    with driver.session() as session:
        for sub in STANDARD_SUBCHAPTERS:
            parent_id = f"CH_{DOMAIN}_{REPORT_TYPE}_std_{sub['parent_order']}"
            sub_id = f"CH_{DOMAIN}_{REPORT_TYPE}_std_{sub['parent_order']}_{sub['sub_order']}"
            if dry_run:
                count += 1
                continue
            session.run(
                """
                MERGE (sub:ChapterTemplate {id: $sub_id})
                ON CREATE SET
                    sub.id = $sub_id,
                    sub.title = $title,
                    sub.canonical_chapter_key = $key,
                    sub.level = 2,
                    sub.`order` = $sub_order,
                    sub.rigidity = 'rigid',
                    sub.domain = $domain,
                    sub.report_type = $rt,
                    sub.created_at = datetime()
                ON MATCH SET
                    sub.canonical_chapter_key = $key,
                    sub.title = $title
                """,
                sub_id=sub_id,
                title=sub["title"],
                key=sub["key"],
                sub_order=sub["sub_order"],
                domain=DOMAIN,
                rt=REPORT_TYPE,
            )
            session.run(
                """
                MATCH (parent:ChapterTemplate {id: $parent_id})
                MATCH (sub:ChapterTemplate {id: $sub_id})
                MERGE (parent)-[:HAS_CHILD]->(sub)
                """,
                parent_id=parent_id,
                sub_id=sub_id,
            )
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Seed 标准子章节到图谱")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uri", default="bolt://graph:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="0123456789")
    args = parser.parse_args()
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    count = seed(driver, dry_run=args.dry_run)
    driver.close()
    print(f"模式: {'dry-run' if args.dry_run else '执行'}")
    print(f"标准子章节数: {count}")


if __name__ == "__main__":
    main()
