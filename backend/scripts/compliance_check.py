"""脚本化合规检查:对环评章节 markdown 执行 8 项 PASS/WARN/FAIL 检查。

检查项:
1. 标准引用完整性(必引导则)
2. 标准编号格式(GB/HJ + 版本)
3. 必填要素覆盖(key_elements)
4. 数值占位符残留({{MISSING}}/[XX])
5. 禁止用语检测(forbidden_phrases)
6. 章节字数下限(min_word_count)
7. 交叉引用完整性({{REF}} 解析)
8. 表格编号连续性

用法:
  python -m scripts.compliance_check --markdown-file chapter.md
  python -c "from scripts.compliance_check import ComplianceChecker; ..."
"""

from __future__ import annotations

import re
from typing import Any

# 必引导则:环评报告应引用的 HJ 系列导则标准编号
REQUIRED_GUIDANCE_RE = re.compile(r"HJ[/T]?\s*\d+")

# 必引导则清单(用于 warning 提示)
REQUIRED_GUIDANCE_HINT = "HJ/T 130"

# 标准编号格式正则:GB/T 1234、GB 1234、HJ 1234、HJ/T 1234
_STANDARD_FORMAT_RE = re.compile(r"(?:GB|HJ)/T\s*\d+|(?:GB|HJ)\s+\d+")

# 不规范格式:字母与数字之间无空格(如 GB3095)
_BAD_STANDARD_RE = re.compile(r"(?:GB|HJ)\d+")

# 占位符正则
_MISSING_PLACEHOLDER_RE = re.compile(r"\{\{MISSING:[^}]*\}\}")
_BRACKET_PLACEHOLDER_RE = re.compile(r"\[(?:XX|待补充|待填写|TBD)\]", re.IGNORECASE)

# 交叉引用未解析残留
_REF_PLACEHOLDER_RE = re.compile(r"\{\{REF:[^}]*\}\}")

# 表格编号:表3-1、表3-2 等
_TABLE_NUMBER_RE = re.compile(r"表(\d+)-(\d+)")


class ComplianceChecker:
    """环评章节 markdown 合规检查器。

    check(markdown, content_contract) 返回 {passed, checks} 结构化报告。
    每项检查状态: PASS / WARN / FAIL。
    passed=True 当且仅当无 FAIL 项(WARN 不阻塞)。
    """

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def check(self, markdown: str, content_contract: dict[str, Any] | None = None) -> dict[str, Any]:
        """执行全部 8 项检查,返回结构化报告。"""
        checks = [
            self.check_standard_reference(markdown),
            self.check_standard_format(markdown),
            self.check_key_elements(markdown, content_contract),
            self.check_placeholder(markdown),
            self.check_forbidden_phrases(markdown, content_contract),
            self.check_word_count(markdown, content_contract),
            self.check_cross_reference(markdown),
            self.check_table_numbering(markdown),
        ]
        passed = all(c["status"] != "FAIL" for c in checks)
        return {"passed": passed, "checks": checks}

    # ------------------------------------------------------------------
    # 1. 标准引用完整性
    # ------------------------------------------------------------------

    def check_standard_reference(self, markdown: str) -> dict[str, str]:
        """检查必引导则(HJ 系列导则)标准是否被引用。"""
        if not REQUIRED_GUIDANCE_RE.search(markdown):
            return {
                "name": "标准引用完整性",
                "status": "WARN",
                "detail": f"未引用必引导则(如 {REQUIRED_GUIDANCE_HINT})",
            }
        return {"name": "标准引用完整性", "status": "PASS", "detail": ""}

    # ------------------------------------------------------------------
    # 2. 标准编号格式
    # ------------------------------------------------------------------

    def check_standard_format(self, markdown: str) -> dict[str, str]:
        """检查标准编号格式是否规范(GB/HJ + 空格 + 数字)。"""
        bad = _BAD_STANDARD_RE.findall(markdown)
        if bad:
            return {
                "name": "标准编号格式",
                "status": "WARN",
                "detail": f"格式不规范(字母数字间缺空格): {bad}",
            }
        return {"name": "标准编号格式", "status": "PASS", "detail": ""}

    # ------------------------------------------------------------------
    # 3. 必填要素覆盖
    # ------------------------------------------------------------------

    def check_key_elements(self, markdown: str, content_contract: dict[str, Any] | None) -> dict[str, str]:
        """检查 content_contract.key_elements 是否在 markdown 中出现。"""
        if not content_contract:
            return {"name": "必填要素覆盖", "status": "PASS", "detail": "无 content_contract, 跳过"}
        key_elements = content_contract.get("key_elements") or []
        if not key_elements:
            return {"name": "必填要素覆盖", "status": "PASS", "detail": "无 key_elements, 跳过"}
        missing = [e for e in key_elements if e not in markdown]
        if missing:
            return {
                "name": "必填要素覆盖",
                "status": "FAIL",
                "detail": f"未覆盖要素: {missing}",
            }
        return {"name": "必填要素覆盖", "status": "PASS", "detail": ""}

    # ------------------------------------------------------------------
    # 4. 数值占位符残留
    # ------------------------------------------------------------------

    def check_placeholder(self, markdown: str) -> dict[str, str]:
        """检查是否有 {{MISSING:...}} 或 [XX]/[待补充] 等占位符残留。"""
        found = []
        for m in _MISSING_PLACEHOLDER_RE.finditer(markdown):
            found.append(m.group())
        for m in _BRACKET_PLACEHOLDER_RE.finditer(markdown):
            found.append(m.group())
        if found:
            return {
                "name": "数值占位符残留",
                "status": "FAIL",
                "detail": f"检测到占位符: {found}",
            }
        return {"name": "数值占位符残留", "status": "PASS", "detail": ""}

    # ------------------------------------------------------------------
    # 5. 禁止用语检测
    # ------------------------------------------------------------------

    def check_forbidden_phrases(self, markdown: str, content_contract: dict[str, Any] | None) -> dict[str, str]:
        """检查 content_contract.forbidden_phrases 是否出现。"""
        if not content_contract:
            return {"name": "禁止用语检测", "status": "PASS", "detail": "无 content_contract, 跳过"}
        forbidden = content_contract.get("forbidden_phrases") or []
        if not forbidden:
            return {"name": "禁止用语检测", "status": "PASS", "detail": "无 forbidden_phrases, 跳过"}
        detected = [p for p in forbidden if p in markdown]
        if detected:
            return {
                "name": "禁止用语检测",
                "status": "WARN",
                "detail": f"检测到禁止用语: {detected}",
            }
        return {"name": "禁止用语检测", "status": "PASS", "detail": ""}

    # ------------------------------------------------------------------
    # 6. 章节字数下限
    # ------------------------------------------------------------------

    def check_word_count(self, markdown: str, content_contract: dict[str, Any] | None) -> dict[str, str]:
        """检查 markdown 长度是否达到 content_contract.min_word_count。"""
        if not content_contract:
            return {"name": "章节字数下限", "status": "PASS", "detail": "无 content_contract, 跳过"}
        min_count = content_contract.get("min_word_count")
        if not min_count:
            return {"name": "章节字数下限", "status": "PASS", "detail": "无 min_word_count, 跳过"}
        actual = len(markdown)
        if actual < min_count:
            return {
                "name": "章节字数下限",
                "status": "WARN",
                "detail": f"字数 {actual} 低于下限 {min_count}",
            }
        return {"name": "章节字数下限", "status": "PASS", "detail": f"字数 {actual} >= {min_count}"}

    # ------------------------------------------------------------------
    # 7. 交叉引用完整性
    # ------------------------------------------------------------------

    def check_cross_reference(self, markdown: str) -> dict[str, str]:
        """检查是否有 {{REF:...}} 未解析残留。"""
        found = [m.group() for m in _REF_PLACEHOLDER_RE.finditer(markdown)]
        if found:
            return {
                "name": "交叉引用完整性",
                "status": "WARN",
                "detail": f"未解析引用: {found}",
            }
        return {"name": "交叉引用完整性", "status": "PASS", "detail": ""}

    # ------------------------------------------------------------------
    # 8. 表格编号连续性
    # ------------------------------------------------------------------

    def check_table_numbering(self, markdown: str) -> dict[str, str]:
        """检查同一章节前缀下表格编号是否连续。"""
        matches = _TABLE_NUMBER_RE.findall(markdown)
        if not matches:
            return {"name": "表格编号连续性", "status": "PASS", "detail": "无表格编号"}
        # 按 chapter prefix 分组,检查每组内编号是否连续
        by_chapter: dict[str, list[int]] = {}
        for chapter, num in matches:
            by_chapter.setdefault(chapter, []).append(int(num))
        gaps = []
        for chapter, nums in by_chapter.items():
            unique_sorted = sorted(set(nums))
            if len(unique_sorted) < 2:
                continue
            expected = set(range(unique_sorted[0], unique_sorted[-1] + 1))
            missing_nums = expected - set(unique_sorted)
            if missing_nums:
                gaps.append(f"表{chapter}-{sorted(missing_nums)}")
        if gaps:
            return {
                "name": "表格编号连续性",
                "status": "WARN",
                "detail": f"编号不连续, 缺失: {gaps}",
            }
        return {"name": "表格编号连续性", "status": "PASS", "detail": ""}


if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="环评章节 markdown 合规检查")
    parser.add_argument("--markdown-file", required=True, help="markdown 文件路径")
    parser.add_argument("--content-contract", default=None, help="content_contract JSON 字符串")
    args = parser.parse_args()

    md = Path(args.markdown_file).read_text(encoding="utf-8")
    cc = json.loads(args.content_contract) if args.content_contract else None

    checker = ComplianceChecker()
    result = checker.check(md, cc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["passed"] else 1)
