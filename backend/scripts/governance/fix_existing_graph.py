"""存量图谱数据治理脚本(幂等)。

修复:
1. 合并 report_type='通用' 分支到 eia_report
2. 清洗 ChapterTemplate.title 双编号
3. 回填 canonical_chapter_key

用法:
  python -m scripts.governance.fix_existing_graph --dry-run   # 预览
  python -m scripts.governance.fix_existing_graph             # 执行
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass
class GovernanceReport:
    fixed_keys: int = 0
    merged_branches: int = 0
    cleaned_titles: int = 0
    normalized_domains: int = 0
    errors: list[str] = field(default_factory=list)


class GraphGovernance:
    """存量图谱治理器。dry_run=True 时只统计不写入。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.report = GovernanceReport()

    def merge_general_branch(self, driver) -> None:
        """Step 1: 合并 coal/通用 → coal/eia_report。"""
        if self.dry_run:
            return
        # 实现在 Task 13 补充
        pass

    def run_all(self, driver) -> GovernanceReport:
        """执行全部治理步骤。"""
        self.merge_general_branch(driver)
        return self.report


def main():
    parser = argparse.ArgumentParser(description="存量图谱治理")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()
    print(f"模式: {'dry-run(预览)' if args.dry_run else '执行'}")


if __name__ == "__main__":
    main()
