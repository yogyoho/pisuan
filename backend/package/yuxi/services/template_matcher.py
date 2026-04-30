"""模板匹配引擎：根据章节标题匹配预定义模板

匹配策略：
1. 按模板优先级排序，逐个尝试
2. 正则匹配（regex_anchor）+ 命名捕获组提取插槽
3. 语义锚点验证（is_anchor 插槽必须包含关键词）
4. 置信度计算 + 阈值过滤
5. 回退：关键词子串匹配
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from yuxi.utils.logging_config import logger


@dataclass
class MatchResult:
    """模板匹配结果"""

    matched: bool
    template_id: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    routing: dict[str, Any] | None = None
    template_name: str | None = None


class TemplateMatcher:
    """模板匹配引擎：将章节标题与模板库中的模板进行匹配

    用法：
        library = TemplateLibrary("templates/coal_mining/headers")
        matcher = TemplateMatcher(library.get_all_templates())
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "coal_mining"})
    """

    def __init__(self, templates: list[dict[str, Any]]):
        # 按优先级降序排列，高优先级模板先匹配
        self.templates = sorted(
            templates,
            key=lambda t: t.get("priority", 0),
            reverse=True,
        )

    def match(self, title: str, context: dict[str, Any] | None = None) -> MatchResult:
        """对给定章节标题进行模板匹配

        Args:
            title: 章节标题文本
            context: 可选上下文，包含 domain 等过滤条件

        Returns:
            MatchResult，包含是否匹配、模板ID、提取的插槽等信息
        """
        if not title or not title.strip():
            return MatchResult(matched=False)

        title = title.strip()
        context = context or {}

        for template in self.templates:
            # 领域过滤
            tpl_domain = template.get("domain", "")
            ctx_domain = context.get("domain", "")
            if tpl_domain and ctx_domain and tpl_domain != ctx_domain:
                continue

            result = self._try_match_template(title, template, context)
            if result.matched:
                return result

        return MatchResult(matched=False)

    def _try_match_template(self, title: str, template: dict[str, Any], context: dict[str, Any]) -> MatchResult:
        """尝试用单个模板匹配标题"""
        match_rule = template.get("match_rule", {})
        strategy = match_rule.get("strategy", "regex_anchor")
        threshold = match_rule.get("confidence_threshold", 0.8)
        fallback_keywords = match_rule.get("fallback_keywords", [])

        # Step 1: 正则匹配
        regex_pattern = match_rule.get("regex", "")
        regex_matched = False
        captured_slots: dict[str, Any] = {}

        if regex_pattern and strategy == "regex_anchor":
            try:
                m = re.match(regex_pattern, title)
                if m:
                    regex_matched = True
                    captured_slots = self._extract_slots(m, template.get("slots", []))
            except re.error as e:
                logger.debug(f"正则表达式错误 template={template.get('template_id')}: {e}")

        if regex_matched:
            # Step 2: 语义锚点验证
            if not self._validate_semantic_anchors(captured_slots, template.get("slots", [])):
                return MatchResult(matched=False)

            # Step 3: 置信度计算
            confidence = self._calculate_confidence(title, captured_slots, template.get("slots", []), fallback_keywords)

            # Step 4: 阈值检查
            if confidence >= threshold:
                return MatchResult(
                    matched=True,
                    template_id=template.get("template_id"),
                    slots=captured_slots,
                    confidence=confidence,
                    routing=template.get("semantic_routing"),
                    template_name=template.get("name"),
                )

        # 回退：关键词匹配
        if fallback_keywords:
            matched_kw = [kw for kw in fallback_keywords if kw in title]
            if matched_kw:
                return MatchResult(
                    matched=True,
                    template_id=template.get("template_id"),
                    slots={"title": title, "matched_keywords": matched_kw},
                    confidence=0.6,
                    routing=template.get("semantic_routing"),
                    template_name=template.get("name"),
                )

        return MatchResult(matched=False)

    def _extract_slots(self, regex_match: re.Match, slot_defs: list[dict]) -> dict[str, Any]:
        """从正则命名捕获组中提取插槽值"""
        slots: dict[str, Any] = {}
        group_dict = regex_match.groupdict()

        for slot_def in slot_defs:
            slot_name = slot_def.get("name", "")
            if slot_name and slot_name in group_dict and group_dict[slot_name] is not None:
                slots[slot_name] = group_dict[slot_name].strip()

        return slots

    def _validate_semantic_anchors(self, captured_slots: dict[str, Any], slot_defs: list[dict]) -> bool:
        """验证语义锚点：is_anchor=true 的插槽值必须包含至少一个语义关键词"""
        for slot_def in slot_defs:
            if not slot_def.get("is_anchor", False):
                continue

            slot_name = slot_def.get("name", "")
            semantic_check = slot_def.get("semantic_check", [])

            if not semantic_check or not slot_name:
                continue

            slot_value = captured_slots.get(slot_name, "")
            if not slot_value:
                return False

            # 至少一个关键词是插槽值的子串
            if not any(kw in slot_value for kw in semantic_check):
                return False

        return True

    def _calculate_confidence(
        self,
        title: str,
        captured_slots: dict[str, Any],
        slot_defs: list[dict],
        fallback_keywords: list[str],
    ) -> float:
        """计算匹配置信度

        基础分 0.8（正则匹配成功）+ 关键词加分 + 插槽完整性加分
        """
        score = 0.8

        # 关键词加分：每个匹配的回退关键词 +0.05，上限 +0.15
        keyword_hits = sum(1 for kw in fallback_keywords if kw in title)
        score += min(keyword_hits * 0.05, 0.15)

        # 插槽完整性加分：实际提取数/期望数 * 0.05，上限 +0.05
        expected_slots = [s for s in slot_defs if s.get("is_variable", False)]
        if expected_slots:
            actual = len(captured_slots)
            score += min((actual / len(expected_slots)) * 0.05, 0.05)

        return min(max(score, 0.0), 1.0)
