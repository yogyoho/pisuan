"""模板生成器：当模板匹配失败时，使用 LLM 参考已有模板生成新模板

生成策略：
1. 从模板库中获取同领域的参考模板（按优先级取 top 5）
2. 构建中文 Prompt，指导 LLM 生成符合模板 schema 的 JSON
3. 三阶段 JSON 解析（直接解析 → 去 fence → 大括号提取）
4. 规范化：补全默认字段、生成 template_id
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from yuxi.services.template_library import TemplateLibrary
from yuxi.utils import hashstr
from yuxi.utils.logging_config import logger


class TemplateGenerator:
    """模板生成器：LLM 参考已有模板为未匹配的章节标题生成模板

    用法：
        generator = TemplateGenerator(template_library=library)
        tpl = await generator.generate_template_for_title("7.1 矿区碳排放分析", ["7", "1"])
    """

    def __init__(self, template_library: TemplateLibrary | None = None):
        self.library = template_library

    async def generate_template_for_title(
        self,
        title: str,
        section_path: list[str] | None = None,
        domain: str = "coal_mining",
    ) -> dict[str, Any] | None:
        """为未匹配的章节标题生成模板

        Args:
            title: 章节标题
            section_path: 章节路径，如 ["7", "1"]
            domain: 领域标识

        Returns:
            生成的模板字典，失败时返回 None
        """
        try:
            # 1. 获取参考模板
            references = self._get_reference_templates(domain)

            # 2. 构建 Prompt
            prompt = self._build_generation_prompt(title, section_path, references)

            # 3. 调用 LLM
            raw_response = await self._call_llm_for_generation(prompt)
            if not raw_response:
                return None

            # 4. 解析 JSON
            template_info = self._parse_llm_json(raw_response)
            if not template_info:
                logger.warning(f"LLM 返回的模板 JSON 解析失败: {raw_response[:200]}")
                return None

            # 5. 规范化
            normalized = self._normalize_generated_template(template_info, title, section_path, domain)
            return normalized

        except Exception as e:
            logger.warning(f"模板生成失败 title={title}: {e}")
            return None

    def _get_reference_templates(self, domain: str, max_examples: int = 5) -> list[dict]:
        """获取参考模板（精简版，只保留关键字段）"""
        if not self.library:
            return []

        templates = self.library.get_templates_by_domain(domain)
        if not templates:
            templates = self.library.get_all_templates()

        # 按优先级排序取 top N
        templates.sort(key=lambda t: t.get("priority", 0), reverse=True)
        slim = []

        for tpl in templates[:max_examples]:
            slots = tpl.get("slots", [])
            routing = tpl.get("semantic_routing", {})
            slim.append(
                {
                    "template_id": tpl.get("template_id", ""),
                    "generalized_pattern": tpl.get("generalized_pattern", ""),
                    "match_rule": {
                        "strategy": tpl.get("match_rule", {}).get("strategy", "regex_anchor"),
                        "regex": tpl.get("match_rule", {}).get("regex", ""),
                    },
                    "slots": [{"name": s.get("name", ""), "description": s.get("description", "")} for s in slots[:3]],
                    "semantic_routing": {
                        "standard_code": routing.get("standard_code", ""),
                        "category": routing.get("category", ""),
                        "required_skills": routing.get("required_skills", [])[:3],
                    },
                }
            )
        return slim

    def _build_generation_prompt(
        self,
        title: str,
        section_path: list[str] | None,
        reference_templates: list[dict],
    ) -> str:
        """构建模板生成 Prompt"""
        path_str = ".".join(section_path) if section_path else ""
        examples_json = json.dumps(reference_templates, ensure_ascii=False, indent=2)

        return f"""你是一个章节标题模板生成专家。请根据以下章节标题，参考已有模板的格式，生成一个完整的模板定义。

章节标题：{title}
章节路径：{path_str or "未知"}

参考模板（同领域已有模板的格式和风格）：
{examples_json}

请生成一个 JSON 格式的模板定义，必须包含以下字段：
{{
  "template_id": "TPL_HEADER_<CATEGORY>_<NN>",
  "name": "模板名称（中文描述）",
  "category": "header",
  "priority": <1-100的整数>,
  "match_rule": {{
    "strategy": "regex_anchor",
    "regex": "正则表达式，使用 (?P<slot_name>...) 命名捕获组",
    "confidence_threshold": 0.8,
    "fallback_keywords": ["关键词1", "关键词2"]
  }},
  "generalized_pattern": "[SECTION] {{chapter_id}} {{topic_text}}",
  "slots": [
    {{"name": "slot_name", "description": "描述", "type": "String", "is_variable": true, "is_anchor": false}}
  ],
  "semantic_routing": {{
    "standard_code": "SEC_...",
    "category": "分类",
    "subcategory": "子分类",
    "required_skills": [],
    "optional_skills": []
  }}
}}

严格只输出 JSON，不要输出任何自然语言解释或代码块标记。"""

    async def _call_llm_for_generation(self, prompt: str) -> str | None:
        """调用 LLM 生成模板"""
        try:
            from yuxi.models.chat import select_model
            from yuxi.config.options import system_options
            model = select_model(model_spec=(await system_options.get())["default_model"])
            response = await asyncio.to_thread(model.call, prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return None

    def _parse_llm_json(self, raw: str) -> dict[str, Any] | None:
        """三阶段 JSON 解析"""
        if not raw or not raw.strip():
            return None

        raw = raw.strip()

        # 尝试1: 直接解析
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试2: 去除 markdown fence
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # 尝试3: 大括号提取
        return self._extract_json_object(raw)

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        """从文本中提取第一个完整的 JSON 对象（大括号深度追踪）"""
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            c = text[i]

            if escape:
                escape = False
                continue

            if c == "\\" and in_string:
                escape = True
                continue

            if c == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        return None

        return None

    def _normalize_generated_template(
        self,
        template_info: dict[str, Any],
        title: str,
        section_path: list[str] | None,
        domain: str,
    ) -> dict[str, Any]:
        """规范化生成的模板，补全缺失字段"""
        # template_id
        if not template_info.get("template_id"):
            title_hash = hashstr(title, 6)
            template_info["template_id"] = f"TPL_HEADER_AUTO_{title_hash}"

        # name
        if not template_info.get("name"):
            template_info["name"] = f"自动生成: {title}"

        # category
        template_info.setdefault("category", "header")
        template_info.setdefault("domain", domain)
        template_info.setdefault("priority", 50)

        # match_rule
        match_rule = template_info.setdefault("match_rule", {})
        match_rule.setdefault("strategy", "regex_anchor")
        match_rule.setdefault("confidence_threshold", 0.8)
        match_rule.setdefault("fallback_keywords", self._extract_keywords_from_title(title))

        # generalized_pattern
        if not template_info.get("generalized_pattern"):
            template_info["generalized_pattern"] = f"[SECTION] {title}"

        # slots
        if not template_info.get("slots"):
            template_info["slots"] = []

        # semantic_routing
        routing = template_info.setdefault("semantic_routing", {})
        if not routing.get("standard_code"):
            keywords = self._extract_keywords_from_title(title)
            kw_part = "_".join(k.upper() for k in keywords[:3]) or "GENERAL"
            routing["standard_code"] = f"SEC_{kw_part}"
        routing.setdefault("category", "General")
        routing.setdefault("required_skills", [])
        routing.setdefault("optional_skills", [])

        # metadata
        template_info.setdefault("metadata", {})
        template_info["metadata"]["auto_generated"] = True
        template_info["metadata"]["domain"] = domain

        return template_info

    def _extract_keywords_from_title(self, title: str) -> list[str]:
        """从标题中提取关键词（去除章节编号后，提取中文二元组）"""
        # 去除开头的章节编号
        cleaned = re.sub(r"^[\d\.]+\s*", "", title).strip()
        if not cleaned:
            return ["GENERAL"]

        # 提取中文二元组
        chinese_chars = re.findall(r"[一-鿿]", cleaned)
        if len(chinese_chars) < 2:
            return [cleaned[:4].upper()] if cleaned else ["GENERAL"]

        bigrams = []
        for i in range(len(chinese_chars) - 1):
            bg = chinese_chars[i] + chinese_chars[i + 1]
            if bg not in bigrams:
                bigrams.append(bg)

        return bigrams[:3] if bigrams else ["GENERAL"]
