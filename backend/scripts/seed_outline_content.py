"""把 outlines/ MD 静态大纲内容写入图谱标准章节节点（幂等）。

解析 13 章 MD 文件的 写作要求/法规依据/写作骨架/数据需求清单，
写入 ChapterTemplate 节点的 purpose/key_points/regulations/writing_hints 属性。

用法:
  python -m scripts.seed_outline_content            # 执行
  python -m scripts.seed_outline_content --dry-run   # 预览
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from neo4j import GraphDatabase

OUTLINES_DIR = Path(__file__).resolve().parent.parent / "package" / "yuxi" / "agents" / "skills" / "buildin" / "coal-eia-writer" / "outlines"


def parse_md(md_path: Path) -> dict:
    """解析大纲 MD 文件,提取 purpose/key_points/regulations/writing_hints。"""
    text = md_path.read_text(encoding="utf-8")
    result: dict = {"purpose": "", "key_points": [], "regulations": [], "writing_hints": ""}

    # 写作要求 → purpose
    m = re.search(r"## 写作要求\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if m:
        result["purpose"] = m.group(1).strip()

    # 法规依据 → regulations (每行一个)
    m = re.search(r"## 法规依据\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if m:
        regs = [line.strip().lstrip("- ") for line in m.group(1).strip().split("\n") if line.strip().startswith("-")]
        result["regulations"] = regs

    # 写作骨架 → key_points (每行一个,去缩进)
    m = re.search(r"## 写作骨架\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if m:
        points = [line.strip() for line in m.group(1).strip().split("\n") if line.strip()]
        result["key_points"] = points

    # 数据需求清单 → writing_hints
    m = re.search(r"## 数据需求清单\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if m:
        result["writing_hints"] = m.group(1).strip()

    return result


def seed(driver, dry_run: bool = False) -> int:
    count = 0
    with driver.session() as session:
        for order in range(1, 14):
            # 找 ch{NN}-*.md 文件
            pattern = f"ch{order:02d}-*.md"
            md_files = list(OUTLINES_DIR.glob(pattern))
            if not md_files:
                print(f"  order={order}: 未找到 {pattern}")
                continue

            content = parse_md(md_files[0])
            chapter_id = f"CH_coal_eia_report_std_{order}"

            if dry_run:
                print(f"  order={order}: {md_files[0].name} → purpose={len(content['purpose'])}字, key_points={len(content['key_points'])}项, regulations={len(content['regulations'])}项")
                count += 1
                continue

            import json
            session.run(
                """
                MATCH (ch:ChapterTemplate {id: $chapter_id})
                SET ch.purpose = $purpose,
                    ch.key_points = $key_points,
                    ch.regulations = $regulations,
                    ch.writing_hints = $writing_hints
                """,
                chapter_id=chapter_id,
                purpose=content["purpose"],
                key_points=json.dumps(content["key_points"], ensure_ascii=False),
                regulations=json.dumps(content["regulations"], ensure_ascii=False),
                writing_hints=content["writing_hints"],
            )
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="写入大纲内容到图谱标准章节")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uri", default="bolt://graph:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="0123456789")
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    count = seed(driver, dry_run=args.dry_run)
    driver.close()
    print(f"模式: {'dry-run' if args.dry_run else '执行'}")
    print(f"写入章节数: {count}")


if __name__ == "__main__":
    main()
