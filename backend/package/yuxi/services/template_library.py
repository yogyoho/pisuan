"""模板库：加载、管理和查询段落模板定义

模板库存储预定义的章节标题模板，支持从 JSON 文件或目录加载。
每个模板包含匹配规则、插槽定义和语义路由信息。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yuxi.utils.logging_config import logger

# 默认模板目录
TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"


class TemplateLibrary:
    """模板库：管理模板定义的加载和查询

    支持从单个 JSON 文件或目录加载模板。
    目录模式下递归扫描所有 .json 文件。
    """

    def __init__(self, library_path: str | Path | None = None):
        self.library_path = Path(library_path) if library_path else TEMPLATES_DIR
        self.templates: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load_templates(self) -> dict[str, dict[str, Any]]:
        """加载模板定义"""
        if self._loaded:
            return self.templates

        if not self.library_path.exists():
            logger.warning(f"模板路径不存在: {self.library_path}")
            self._loaded = True
            return self.templates

        try:
            if self.library_path.is_file():
                self._load_from_file(self.library_path)
            elif self.library_path.is_dir():
                self._load_from_directory(self.library_path)

            logger.info(f"模板库加载完成: {len(self.templates)} 个模板")
        except Exception as e:
            logger.error(f"加载模板库失败: {e}")

        self._loaded = True
        return self.templates

    def _load_from_file(self, file_path: Path) -> None:
        """从单个 JSON 文件加载模板"""
        try:
            with open(file_path, encoding="utf-8-sig") as f:
                data = json.load(f)

            if isinstance(data, dict):
                if "templates" in data and isinstance(data["templates"], list):
                    # 格式: {"templates": [...]}
                    for tpl in data["templates"]:
                        self._register_template(tpl)
                elif "template_id" in data:
                    # 格式: 单个模板对象
                    self._register_template(data)
            elif isinstance(data, list):
                for tpl in data:
                    if isinstance(tpl, dict) and "template_id" in tpl:
                        self._register_template(tpl)
        except Exception as e:
            logger.warning(f"加载模板文件失败 {file_path}: {e}")

    def _load_from_directory(self, dir_path: Path) -> None:
        """从目录递归加载所有 JSON 模板文件"""
        for json_file in sorted(dir_path.rglob("*.json")):
            # 跳过 routing_config.json 等非模板文件
            if json_file.name.startswith("routing_"):
                continue
            self._load_from_file(json_file)

    def _register_template(self, template: dict[str, Any]) -> None:
        """注册一个模板到库中"""
        tpl_id = template.get("template_id")
        if not tpl_id:
            return
        self.templates[tpl_id] = template

    # ---- 查询方法 ----

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        """按 ID 获取模板"""
        self.load_templates()
        return self.templates.get(template_id)

    def get_templates_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """按领域获取模板列表"""
        self.load_templates()
        return [t for t in self.templates.values() if t.get("domain") == domain]

    def get_templates_by_category(self, category: str) -> list[dict[str, Any]]:
        """按分类获取模板列表"""
        self.load_templates()
        return [t for t in self.templates.values() if t.get("semantic_routing", {}).get("category") == category]

    def get_all_templates(self) -> list[dict[str, Any]]:
        """获取所有模板"""
        self.load_templates()
        return list(self.templates.values())

    # ---- 变更方法 ----

    def add_templates_from_list(self, templates: list[dict[str, Any]]) -> None:
        """从外部列表注入模板（如 DB 学习模板）"""
        if not self._loaded:
            self.load_templates()

        for tpl in templates:
            template_id = tpl.get("id")
            if not template_id:
                continue

            converted = {
                "template_id": f"learned_{template_id}",
                "title": tpl.get("chapter", ""),
                "generalized_pattern": tpl.get("generalized", ""),
                "slots": tpl.get("slots", []),
                "domain": tpl.get("domain_code", ""),
                "score": tpl.get("source_count", 1),
                "routing": tpl.get("extra_meta", {}).get("routing", ""),
                "source": "learned",
            }
            self.templates[converted["template_id"]] = converted

        logger.info(f"从外部注入 {len(templates)} 个学习模板")

    def add_template(self, template: dict[str, Any]) -> None:
        """添加或更新模板"""
        tpl_id = template.get("template_id")
        if not tpl_id:
            raise ValueError("模板必须包含 template_id")
        self.templates[tpl_id] = template

    def remove_template(self, template_id: str) -> bool:
        """删除模板"""
        if template_id in self.templates:
            del self.templates[template_id]
            return True
        return False

    def save_templates(self, output_path: str | Path) -> None:
        """将模板库保存到 JSON 文件"""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            json.dump({"templates": self.get_all_templates()}, f, ensure_ascii=False, indent=2)

    # ---- 统计 ----

    def get_statistics(self) -> dict[str, Any]:
        """获取模板库统计信息"""
        self.load_templates()
        categories: dict[str, int] = {}
        domains: dict[str, int] = {}
        for t in self.templates.values():
            cat = t.get("semantic_routing", {}).get("category", "未分类")
            categories[cat] = categories.get(cat, 0) + 1
            dom = t.get("domain", "未指定")
            domains[dom] = domains.get(dom, 0) + 1
        return {
            "total_templates": len(self.templates),
            "categories": categories,
            "domains": domains,
        }
