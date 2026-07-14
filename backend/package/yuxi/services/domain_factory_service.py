"""Domain Factory Service - 领域知识工厂服务层"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


# ---------------------------------------------------------------------------
# 结构化入库数据模型
# ---------------------------------------------------------------------------


@dataclass
class StructuredChunk:
    """结构化分片：领域工厂的一个段落/表格对应一个 chunk"""

    id: str
    content: str
    chunk_order_index: int
    section_id: str = ""
    section_title: str = ""
    parent_section_title: str = ""
    template: dict | None = None
    slots: list[dict] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredSection:
    """结构化章节"""

    section_id: str
    title: str
    level: int
    order: int
    parent_section: str | None = None
    path: list[str] = field(default_factory=list)
    chunk_indexes: list[int] = field(default_factory=list)


@dataclass
class StructuredDocument:
    """结构化文档：保留完整语义元数据的中间结构

    替代纯 Markdown 方案，保留章节层级、模板、插槽等信息，
    供向量化时进行去噪和上下文重组。
    """

    file_id: str
    filename: str
    chunks: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    industry: str = ""
    report_type: str = ""
    standard_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


import aiofiles

from yuxi.config import config
from yuxi.models.chat import select_model
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository
from yuxi.services.entity_meta_service import EntityMetaAdapter, EntityMetaMatcher, SlotEntityMapper
from yuxi.services.task_service import tasker
from yuxi.utils import hashstr
from yuxi.utils.datetime_utils import utc_isoformat
from yuxi.utils.logging_config import logger


# ---------------------------------------------------------------------------
# 入库工具函数：去噪与上下文重组
# ---------------------------------------------------------------------------


def clean_title(title: str) -> str:
    """去除标题开头的章节编号（去噪处理）

    示例：
    - "4. 环境现状调查" -> "环境现状调查"
    - "4.1 大气环境" -> "大气环境"
    - "7.1.2 水资源分析" -> "水资源分析"
    """
    if not title:
        return ""
    return re.sub(r"^[\d\.]+\s*", "", title).strip()


def build_embedding_text(
    industry: str,
    report_type: str,
    parent_section_title: str,
    current_section_title: str,
    content: str,
) -> str:
    """构造用于向量化的文本（去噪与上下文重组）

    构造公式：[行业领域] + [报告类型] + [去噪后的父级章节] + [去噪后的当前章节] + [段落原文]

    示例输出：
    "行业：煤炭；报告：环评报告；背景：环境现状调查 - 大气环境；内容：PM10日均浓度..."
    """
    clean_parent = clean_title(parent_section_title) if parent_section_title else ""
    clean_current = clean_title(current_section_title) if current_section_title else ""

    parts: list[str] = []
    if industry:
        parts.append(f"行业：{industry}")
    if report_type:
        parts.append(f"报告：{report_type}")
    if clean_parent or clean_current:
        if clean_parent and clean_current:
            parts.append(f"背景：{clean_parent} - {clean_current}")
        elif clean_current:
            parts.append(f"背景：{clean_current}")
    if content:
        parts.append(f"内容：{content}")

    return "；".join(parts)


def _safe_filename(name: str) -> str:
    sanitized = re.sub(r"[^\w\-.]+", "_", name)
    return sanitized[:180] or "document"


@dataclass
class DomainTaskDTO:
    """领域任务数据传输对象"""

    id: str
    file_name: str
    domain_label: str
    domain_code: str
    status: str
    uploaded_at: str | None
    ai_confidence: int | None
    reviewer: str | None
    committed_at: str | None
    error_message: str | None = None
    document_type: str | None = None
    report_type_code: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "domain_label": self.domain_label,
            "domain": self.domain_code,
            "status": self.status,
            "uploaded_at": self.uploaded_at,
            "ai_confidence": self.ai_confidence,
            "reviewer": self.reviewer,
            "committed_at": self.committed_at,
            "error_message": self.error_message,
            "document_type": self.document_type,
            "report_type_code": self.report_type_code,
        }


class DomainFactoryService:
    """领域知识工厂服务 - 核心业务逻辑"""

    # 类级别共享状态：章节提取任务缓存 (task_id -> task_state)
    _extract_tasks: dict[str, dict[str, Any]] = {}

    def __init__(self):
        self.repo = DomainFactoryRepository()
        self._storage_dir = Path(config.save_dir) / "domain_factory"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._entity_adapter = EntityMetaAdapter()
        self._entity_matcher = EntityMetaMatcher()
        self._slot_mapper = SlotEntityMapper()
        # 模板系统（延迟加载）
        self._template_library: Any = None
        self._template_matcher: Any = None
        # Prompt 模板缓存
        self._prompt_templates: dict[str, str] | None = None

    async def _get_template_matcher(self, domain: str = "coal_mining") -> Any:
        """获取或创建模板匹配器（延迟加载，含 DB 学习模板）"""
        if self._template_matcher is not None:
            return self._template_matcher

        try:
            from yuxi.services.template_library import TemplateLibrary
            from yuxi.services.template_matcher import TemplateMatcher

            library = TemplateLibrary()
            templates = library.get_templates_by_domain(domain)
            if not templates:
                templates = library.get_all_templates()

            # 从 DB 加载学习模板并注入
            try:
                domain_code = domain.replace("_mining", "").replace("_", "") or "coal"
                db_templates = await self.repo.list_learned_templates(domain_code=domain_code)
                if db_templates:
                    library.add_templates_from_list(db_templates)
            except Exception as db_err:
                logger.warning(f"加载 DB 学习模板失败: {db_err}")

            all_templates = list(library.templates.values())
            if all_templates:
                self._template_library = library
                self._template_matcher = TemplateMatcher(all_templates)
                logger.info(f"模板匹配器已加载: {len(all_templates)} 个模板 (含 DB 学习模板), domain={domain}")
            else:
                logger.info("模板库为空，跳过模板匹配")
        except Exception as e:
            logger.warning(f"加载模板匹配器失败: {e}")

        return self._template_matcher

    # ========== Prompt 模板管理 ==========

    # 默认 Prompt 模板（与前端 PromptConfigView.vue 中的 defaultPrompts 保持同步）
    _PROMPT_DEFAULTS: dict[str, str] = {
        "extract": (
            "你是一个专业的文档信息提取助手。请从以下文档中提取结构化信息。\n\n"
            "## 需要提取的字段：\n{variables}\n\n"
            "## 文档内容：\n{content}\n\n"
            "## 输出要求：\n"
            "请以 JSON 格式返回提取结果，格式如下：\n"
            '{{\n  "字段Key": "提取到的值",\n  "_confidence_字段Key": 0.0-1.0之间的置信度\n}}\n\n'
            "注意：\n"
            "1. 只返回 JSON，不要有其他内容\n"
            "2. 如果某个字段在文档中未找到，设置值为 null\n"
            "3. 置信度 1.0 表示非常有把握，0.5 表示不确定\n"
            "4. 只提取文档中明确提到的信息，不要推断"
        ),
        "template": (
            "你是一个负责生成环评模板的专家，请将下方段落泛化为模板，使用双层大括号 {{插槽名称}} 表示可替换变量。\n\n"
            "重要：插槽命名必须统一使用中文名称，格式为 {{中文名称}}。\n\n"
            "命名示例：\n"
            "- 项目名称：{{项目名称}}\n"
            "- 行政区域：{{行政区域}}\n"
            "- 产能数值：{{产能数值}}\n"
            "- 保护目标名称：{{保护目标名称}}\n\n"
            "泛化粒度规则：\n"
            "1. 每个段落提取的 slot 不超过 5 个\n"
            "2. 固定单位（m、Mt/a、年、度、mm、km、km²、%、mg/L）不作为独立 slot，合并到数值变量中\n"
            "3. 描述性短语保持原文，不拆分为变量\n"
            "4. 方向/位置描述保持原样\n"
            "5. 只提取具有跨项目复用价值的变量\n"
            "6. 相关数值合并：如\"630～1200m\"合并为{{海拔范围}}，不拆为最小值/最大值/单位\n"
            "7. 禁止使用\"方位1\"\"特征2\"\"区域1\"等无语义编号命名，每个 slot 必须有明确业务含义\n"
            "8. 地理描述、环境特征等较长描述文字，如不适合拆为 slot，用 [叙述标记: 描述内容] 标记\n\n"
            "需要：\n"
            "1. 给出泛化后的文本（保持原文逻辑结构不变）；\n"
            "2. 列出每个插槽的含义及推荐数据来源；\n"
            '3. 如果段落包含判断逻辑（如"因此"、"所以"、"如果...则"、"当...时"等），提取触发该模板的前提条件；\n'
            "4. 严格只输出 JSON，不要输出任何自然语言解释或前后缀文本；\n"
            "5. 严格禁止输出代码块标记（例如 ```json 或 ```）；\n"
            "6. 插槽名称必须统一使用中文，格式为 {{中文名称}}。\n\n"
            "文本：\n{content}\n\n"
            "Schema 变量提示：\n{schema_text}\n\n"
            "输出 JSON 结构：\n"
            "{{\n"
            '  "generalized": "...包含 {{产能数值}} ...",\n'
            '  "slots": [\n'
            "     {{\n"
            '       "name": "插槽中文名称",\n'
            '       "type": "类型",\n'
            '       "description": "插槽含义描述",\n'
            '       "suggested_source": "推荐数据来源"\n'
            "     }}\n"
            "  ],\n"
            '  "narrative_placeholders": [\n'
            "     {{\n"
            '       "mark": "叙述标记名称",\n'
            '       "role": "描述该叙述区的用途",\n'
            '       "sample": "原文中的参考文本"\n'
            "     }}\n"
            "  ],\n"
            '  "condition": "IF (条件表达式) == True",\n'
            '  "metadata": {{\n'
            '    "chapter": "{chapter_hint}",\n'
            '    "tags": ["{domain_label}"]\n'
            "  }}\n"
            "}}"
        ),
        "schema_generation": (
            "你是一个专业的领域专家。请根据以下文档内容生成标准化的 Schema 配置。\n\n"
            "## 文档领域：\n{domain}\n\n"
            "## 文档内容摘要：\n{content}\n\n"
            "## 要求：\n"
            "1. 识别文档中的关键信息字段\n"
            "2. 为每个字段指定合适的数据类型和控件类型\n"
            "3. 生成符合领域规范的字段命名\n"
            "4. 输出 JSON 格式：\n"
            "{\n"
            '  "variables": [\n'
            "    {\n"
            '      "key": "字段Key",\n'
            '      "label": "字段显示名",\n'
            '      "data_type": "string|number|boolean|date",\n'
            '      "widget": "Input|InputNumber|Select|DatePicker",\n'
            '      "unit": "单位",\n'
            '      "group": "分组名称",\n'
            '      "required": true/false,\n'
            '      "prompt": "提取提示词"\n'
            "    }\n"
            "  ],\n"
            '  "chapters": [\n'
            '    {"key": "ch1", "title": "章节标题"}\n'
            "  ]\n"
            "}"
        ),
        "section_generalization": (
            "你是一个专业的环评报告分析助手。请对以下章节进行泛化处理。\n\n"
            "## 行业领域：\n{industry}\n\n"
            "## 报告类型：\n{report_type}\n\n"
            "## 章节标题：\n{title}\n\n"
            "## 章节内容：\n{content}\n\n"
            "## 标准章节代码参考：\n{standard_codes}\n\n"
            "## 要求：\n"
            "1. 提取章节的核心内容和结构\n"
            "2. 生成模板化的章节框架\n"
            "3. 识别需要填写的关键参数\n"
            "4. 输出 JSON 格式：\n"
            "{\n"
            '  "generalized_content": "泛化后的内容模板",\n'
            '  "slots": [\n'
            '    {"name": "参数名称", "source": "数据来源", "required": true/false}\n'
            "  ],\n"
            '  "keywords": ["关键词1", "关键词2"],\n'
            '  "related_sections": ["相关章节1", "相关章节2"]\n'
            "}"
        ),
    }

    async def _load_prompt_templates(self) -> dict[str, str]:
        """加载 prompt 模板：先从配置文件读取，再用数据库记录覆盖"""
        if self._prompt_templates is not None:
            return self._prompt_templates

        # 1. 从配置文件读取默认模板
        templates = self._load_prompts_from_file()

        # 2. 数据库中的用户自定义模板覆盖文件默认值
        try:
            configs = await self.repo.list_prompt_configs()
            for cfg in configs:
                prompt_type = cfg.get("prompt_type", "")
                template = cfg.get("template", "")
                if prompt_type and template:
                    templates[prompt_type] = template
        except Exception as e:
            logger.warning(f"加载数据库 prompt 配置失败，仅使用文件默认值: {e}")

        self._prompt_templates = templates
        return templates

    def _load_prompts_from_file(self) -> dict[str, str]:
        """从 prompt_templates.yaml 配置文件读取默认模板"""
        import yaml

        default_templates = dict(self._PROMPT_DEFAULTS)
        config_path = Path(__file__).parent.parent / "config" / "static" / "prompt_templates.yaml"

        try:
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    file_templates = yaml.safe_load(f) or {}
                for key, value in file_templates.items():
                    if isinstance(value, str) and value.strip():
                        default_templates[key] = value.strip()
                logger.info(f"已从 {config_path} 加载 prompt 模板: {list(file_templates.keys())}")
        except Exception as e:
            logger.warning(f"读取 prompt 配置文件失败，使用内置默认值: {e}")

        return default_templates

    def _invalidate_prompt_cache(self) -> None:
        """清除 prompt 模板缓存（保存配置后调用）"""
        self._prompt_templates = None

    def _render_prompt(self, template: str, **kwargs: str) -> str:
        """将 prompt 模板中的占位符替换为实际值"""
        result = template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    # ========== Domain ==========

    async def get_domains(self) -> list[dict[str, Any]]:
        return await self.repo.list_domains()

    async def create_domain(self, code: str, name: str, description: str | None = None) -> dict[str, Any]:
        domain = await self.repo.create_domain(code, name, description)
        return domain.to_dict()

    async def update_domain(self, domain_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        domain = await self.repo.update_domain(domain_id, data)
        return domain.to_dict() if domain else None

    async def delete_domain(self, domain_id: int) -> bool:
        return await self.repo.delete_domain(domain_id)

    # ========== Extraction Variables (Entity-driven) ==========

    async def _get_extraction_variables(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        """从数据库实体库加载提取变量，回退到 JSON 文件。

        实体的属性作为提取字典，指导 LLM 识别文档中的结构化信息。
        """
        try:
            from yuxi.repositories.domain_entity_repository import DomainEntityRepository

            repo = DomainEntityRepository()
            entities = await repo.list_all(domain_code=domain_code)
            if entities:
                return self._convert_db_entities_to_variables(entities)
        except Exception as e:
            logger.warning(f"从数据库加载实体变量失败: {e}")

        # 回退到 JSON 文件
        try:
            entity_defs = self._entity_matcher.loader.load()
            if not entity_defs:
                return []
            return self._entity_adapter.enhance_schema_variables([], entity_defs)
        except Exception as e:
            logger.warning(f"从 JSON 文件加载实体变量失败: {e}")
            return []

    def _convert_db_entities_to_variables(self, entities: list[dict]) -> list[dict]:
        """将数据库实体转换为 LLM 提取变量格式"""
        variables = []
        for entity in entities:
            entity_key = entity.get("entity_key", "")
            name_cn = entity.get("name_cn", "")
            category = entity.get("category", "")
            description = entity.get("description", "")
            value_type = entity.get("value_type", "String")
            unit = entity.get("unit", "")
            synonyms = entity.get("synonyms", [])

            var = {
                "key": entity_key,
                "label": name_cn,
                "data_type": value_type.lower() if value_type else "string",
                "widget": "Input",
                "unit": unit or "",
                "group": category or "基础信息",
                "required": False,
                "prompt": description,
                "source": "entity_db",
                "_entity_id": entity.get("entity_id", ""),
                "_entity_category": category,
                "synonyms": synonyms,
            }
            variables.append(var)

            # 展开子属性为独立变量
            for prop in entity.get("properties", []):
                prop_key = prop.get("key", "")
                if not prop_key:
                    continue
                variables.append(
                    {
                        "key": f"{entity_key}.{prop_key}",
                        "label": f"{name_cn} · {prop.get('name_cn', prop_key)}",
                        "data_type": prop.get("value_type", "String").lower(),
                        "widget": "Input",
                        "unit": prop.get("unit", ""),
                        "group": category or "基础信息",
                        "required": False,
                        "prompt": prop.get("description", ""),
                        "source": "entity_db_prop",
                        "_entity_id": entity.get("entity_id", ""),
                        "_entity_category": category,
                    }
                )

        return variables

    # ========== File Upload ==========

    async def save_uploaded_file(
        self, file_content: bytes, original_filename: str, domain_code: str
    ) -> tuple[str, str]:
        task_id = str(uuid.uuid4())
        safe_name = _safe_filename(original_filename)
        subdir = self._storage_dir / domain_code
        subdir.mkdir(parents=True, exist_ok=True)
        file_path = subdir / f"{task_id}_{safe_name}"
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)
        return task_id, str(file_path)

    # ========== Task ==========

    async def create_task(
        self,
        domain_code: str,
        file_name: str,
        file_path: str,
        uploaded_by: str | None = None,
        document_type: str = "通用",
        report_type_code: str = "通用",
        source_report_id: str | None = None,
        chapter_label: str | None = None,
    ) -> DomainTaskDTO:
        domain = await self.repo.get_domain_by_code(domain_code)
        if not domain:
            raise ValueError(f"Domain not found: {domain_code}")

        if chapter_label and not source_report_id:
            source_report_id = f"sr_{uuid.uuid4().hex[:12]}"

        task_id = str(uuid.uuid4())
        task = await self.repo.create_task(
            task_id=task_id,
            domain_id=domain.id,
            file_name=file_name,
            storage_path=file_path,
            uploaded_by=uploaded_by,
        )
        task.document_type = document_type
        task.report_type_code = report_type_code
        update_data: dict = {"document_type": document_type, "report_type_code": report_type_code}
        if source_report_id:
            update_data["source_report_id"] = source_report_id
        if chapter_label:
            update_data["chapter_label"] = chapter_label
        await self.repo.update_task(task_id, update_data)

        # 注册到任务中心
        try:
            await tasker.enqueue(
                name=f"知识工厂: {file_name}",
                task_type="domain_factory",
                payload={
                    "task_id": task_id,
                    "domain_factory_task_id": task_id,  # 知识工厂原始任务ID
                    "domain_code": domain_code,
                    "domain_name": domain.name,
                    "file_name": file_name,
                    "document_type": document_type,
                    "report_type_code": report_type_code,
                },
                coroutine=self._etl_pipeline_async,
            )
            logger.info(f"已注册 ETL 任务到任务中心: {task_id}")
        except Exception as e:
            logger.warning(f"注册任务中心失败，将继续执行: {e}")

        return DomainTaskDTO(
            id=task.id,
            file_name=task.file_name,
            domain_label=domain.name,
            domain_code=domain.code,
            status=task.status,
            uploaded_at=utc_isoformat(task.created_at),
            ai_confidence=None,
            reviewer=None,
            committed_at=None,
            document_type=document_type,
            report_type_code=report_type_code,
        )

    async def _etl_pipeline_async(self, context) -> dict[str, Any]:
        """ETL 流水线异步执行（由任务中心调度）

        流水线阶段：
        1. 解析 (PARSING): 将文档解析为 Markdown，并按章节/段落切分
        2. 提取 (EXTRACTING): 调用 LLM 提取结构化数据
        3. 泛化 (GENERALIZING): 生成槽位模板
        4. 校验 (WAITING_REVIEW): 等待人工审核
        """
        from yuxi.services.domain_factory_service import get_domain_factory_service
        from yuxi.models.chat import select_model

        # 从 payload 中获取知识工厂任务 ID
        task_id = None
        try:
            if hasattr(context, "_tasker") and hasattr(context, "task_id"):
                tasker_task = context._tasker._tasks.get(context.task_id)
                if tasker_task and tasker_task.payload:
                    task_id = tasker_task.payload.get("task_id")
        except Exception as e:
            logger.warning(f"获取任务ID失败: {e}")

        if not task_id:
            logger.error("ETL 流水线：未找到任务 ID")
            return {"error": "task_id not found"}

        service = get_domain_factory_service()
        task = await service.repo.get_task_with_domain(task_id)

        if not task:
            logger.error(f"ETL 流水线：任务不存在 {task_id}")
            return {"error": "task not found"}

        try:
            # ========== 阶段1: 解析文档 (PARSING) ==========
            await context.set_progress(10.0, "正在解析文档...")
            await context.set_message("正在解析文档...")
            logger.info(f"ETL 流水线开始解析文档: {task_id}")

            # 更新任务状态为解析中
            await service.repo.update_task(task_id, {"status": "PARSING"})

            # 获取文件路径
            file_path = task.storage_path
            if not file_path:
                raise ValueError(f"任务 {task_id} 没有存储路径")

            # 解析文档为 Markdown 和 HTML
            from yuxi.knowledge.parser.unified import parse_source_to_markdown

            parse_result = await parse_source_to_markdown(file_path)
            raw_markdown = parse_result.markdown
            raw_html = parse_result.html  # HTML 格式，表格以 HTML 保存
            logger.info(f"文档解析完成，Markdown: {len(raw_markdown)} 字符, HTML: {len(raw_html or '')} 字符")

            # 按章节和段落切分文档（传入 HTML 内容用于存储完整表格）
            paragraphs = self._parse_markdown_to_paragraphs(raw_markdown, html_content=raw_html)
            logger.info(f"文档切分完成，共 {len(paragraphs)} 个段落")

            # 段落分类 (CLASSIFY)：将段落分为 heading/table/figure/formula/list/legal_reference/parameter/narrative
            self.classify_paragraphs(paragraphs)
            classify_stats = {}
            for p in paragraphs:
                ct = p.get("classify_type", "narrative")
                classify_stats[ct] = classify_stats.get(ct, 0) + 1
            logger.info(f"段落分类完成: {classify_stats}")

            # parent_title 回填：用 section_path → title 映射补全
            title_map = {}
            for p in paragraphs:
                if p.get("is_title") and p.get("section_path"):
                    key = tuple(str(s) for s in p["section_path"])
                    if key not in title_map:
                        title_map[key] = p.get("title", "")
            for p in paragraphs:
                sp = p.get("section_path", [])
                if len(sp) > 1:
                    parent_key = tuple(str(s) for s in sp[:-1])
                    mapped = title_map.get(parent_key)
                    if mapped:
                        p["parent_title"] = mapped

            # 法律引用提取 (LEGAL_EXTRACT)：从 legal_reference 段落提取结构化引用
            legal_refs = self.extract_legal_references(paragraphs)
            if legal_refs:
                logger.info(f"法律引用提取完成（场景A）: {len(legal_refs)} 条")
                # 附加到段落 template 中
                for p in paragraphs:
                    if p.get("classify_type") == "legal_reference":
                        para_refs = [r for r in legal_refs if r.get("source_para_id") == p.get("id")]
                        if para_refs:
                            tmpl = p.get("template") or {}
                            tmpl["legal_references"] = para_refs
                            p["template"] = tmpl

            # 正文标准引用提取（场景B）：从含标准编号的正文段落用 LLM 提取
            try:
                body_refs = await self.extract_legal_references_from_text(paragraphs)
                if body_refs:
                    logger.info(f"正文标准引用提取完成（场景B）: {len(body_refs)} 条")
                    # 附加到对应段落
                    for ref in body_refs:
                        pid = ref.get("source_para_id")
                        if pid:
                            p = next((x for x in paragraphs if x.get("id") == pid), None)
                            if p:
                                tmpl = p.get("template") or {}
                                refs_list = tmpl.get("legal_references", [])
                                refs_list.append(ref)
                                tmpl["legal_references"] = refs_list
                                p["template"] = tmpl
            except Exception as body_legal_err:
                logger.warning(f"正文标准引用提取失败（不阻断）: {body_legal_err}")

            # 模板匹配：对标题段落进行模板匹配，附加 template_id / semantic_routing
            try:
                matcher = await service._get_template_matcher()
                if matcher:
                    matched_count = 0
                    for para in paragraphs:
                        title = para.get("title", "")
                        is_title = para.get("is_title", False)
                        if not is_title or not title:
                            continue

                        match_result = matcher.match(title, context={"domain": "coal_mining"})
                        if match_result.matched:
                            para["template_match"] = {
                                "template_id": match_result.template_id,
                                "slots": match_result.slots,
                                "confidence": match_result.confidence,
                                "routing": match_result.routing,
                                "template_name": match_result.template_name,
                            }
                            matched_count += 1

                    if matched_count > 0:
                        logger.info(f"模板匹配完成: {matched_count}/{len(paragraphs)} 个段落匹配到模板")
                        # 更新学习模板的 match_count
                        await service._increment_learned_template_match_counts(paragraphs)
            except Exception as tpl_err:
                logger.warning(f"模板匹配失败（不阻断 ETL）: {tpl_err}")

            # 公式提取：对 formula 类型段落提取公式结构+变量映射
            formula_count = self._extract_formulas(paragraphs)
            if formula_count > 0:
                logger.info(f"公式提取完成: {formula_count} 个公式")

            # 图片多模态提取：对 figure 类型段落调用 VLM 分析
            try:
                figure_count = await self._extract_figures(paragraphs)
                if figure_count > 0:
                    logger.info(f"图片多模态提取完成: {figure_count} 张图片")
            except Exception as fig_err:
                logger.warning(f"图片多模态提取失败（不阻断）: {fig_err}")

            # 章节提取与泛化共用的领域/表单上下文（须在分章节提取之前初始化）
            domain_for_extract = await service.repo.get_domain_by_id(task.domain_id) if task.domain_id else None
            domain_code = domain_for_extract.code if domain_for_extract else None
            form_data = {}

            # 分章节提取：按章节分组对 parameter/narrative 段落做局部变量提取
            try:
                chapter_extracts = await self.extract_by_chapter(paragraphs, domain_code=domain_code)
                if chapter_extracts:
                    logger.info(f"分章节提取完成: {len(chapter_extracts)} 个章节")
                    # 合并到 base_info
                    for _ch, _vars in chapter_extracts.items():
                        form_data.update(_vars)
            except Exception as ch_err:
                logger.warning(f"分章节提取失败（不阻断）: {ch_err}")

            # 表格 Schema 提取：对 table 类型段落提取列定义模板
            table_schema_count = self._extract_table_schemas(paragraphs)
            if table_schema_count > 0:
                logger.info(f"表格 Schema 提取完成: {table_schema_count} 张表格")

            # 生成结构化块（包含段落和表格）
            # 如果有 HTML 内容，优先使用 HTML 格式保存表格
            structured_blocks = self._extract_structured_blocks(raw_markdown, paragraphs, html_content=raw_html)

            # 保存解析结果
            await service.repo.update_task(
                task_id,
                {
                    "raw_markdown": raw_markdown,
                    "raw_html": raw_html,
                    "source_paragraphs": paragraphs,
                    "structured_blocks": structured_blocks,
                },
            )

            await context.set_progress(25.0, "文档解析完成，正在提取信息...")
            await context.set_message("文档解析完成，正在泛化...")

            # ========== 阶段2: 泛化 (GENERALIZING) ==========
            # 旧的全局 EXTRACT 阶段已废弃：slot 即提取变量，由段落级 GENERALIZE 产出。
            # 保留 variables 用于前端 form_schema 展示，但不再调用 LLM 全局提取。
            prompt_templates = await service._load_prompt_templates()

            await service.repo.update_task(task_id, {"status": "GENERALIZING"})

            # ========== 阶段3: 泛化 (GENERALIZING) ==========
            await service.repo.update_task(task_id, {"status": "GENERALIZING"})

            # 获取领域信息用于泛化
            domain = await service.repo.get_domain_by_id(task.domain_id) if task.domain_id else None
            domain_label = domain.name if domain else "通用"

            # 全局模板不再单独生成 LLM 调用——前端从段落级 template 聚合
            template_payload = {
                "generalized": "",
                "slots": [],
                "metadata": {"chapter": "", "tags": []},
            }

            # ========== 段落级泛化（参考源系统 pipeline.py）==========
            # 只对 parameter 型段落调用 LLM 泛化，其他类型跳过
            try:
                parameter_paragraphs = [p for p in paragraphs if p.get("classify_type") == "parameter"]
                skipped_count = len(paragraphs) - len(parameter_paragraphs)
                logger.info(f"泛化过滤: {len(parameter_paragraphs)} 个参数型段落待泛化, {skipped_count} 个段落跳过")

                paragraph_results = await self.generalize_paragraphs(
                    paragraphs=parameter_paragraphs,
                    schema_variables=[],
                    domain_label=domain_label,
                    max_concurrency=10,
                )

                # 将泛化结果回写到段落中
                # 修复：para["template"] 应该是包含 generalized、slots 等字段的对象，而不是字符串
                generalized_count = 0
                for para in paragraphs:
                    para_id = para.get("id", "")
                    if para_id in paragraph_results:
                        gen_result = paragraph_results[para_id]

                        # 用实体元数据映射插槽的 entity_ref
                        raw_slots = gen_result.get("slots", [])
                        if raw_slots:
                            try:
                                mapped_slots = self._slot_mapper.map_slots(
                                    raw_slots,
                                    paragraph_context=para.get("content", ""),
                                )
                                raw_slots = mapped_slots
                            except Exception as slot_err:
                                logger.debug(f"插槽实体映射失败: {slot_err}")

                        # 为段落匹配关联实体
                        matched_entities = []
                        try:
                            matched_entities = self._entity_matcher.match_paragraph(
                                para.get("parent_title", ""),
                                para.get("content", ""),
                            )
                            matched_entities = [
                                {"id": e.get("id"), "name": e.get("name"), "category": e.get("category")}
                                for e in matched_entities[:3]
                            ]
                        except Exception:
                            pass

                        # 为段落添加泛化字段，前端统一从 para.template 读取
                        generalized_text = gen_result.get("generalized", "")
                        para["template"] = {
                            "generalized": generalized_text,
                            "original": para.get("content", ""),
                            "slots": raw_slots,
                            "metadata": gen_result.get("metadata", {}),
                            "quality_score": self.evaluate_template_quality(generalized_text, raw_slots),
                        }
                        if matched_entities:
                            para["matched_entities"] = matched_entities
                        generalized_count += 1

                logger.info(f"段落级泛化完成: 成功 {generalized_count}/{len(parameter_paragraphs)} 个参数型段落")
            except Exception as para_error:
                logger.warning(f"段落级泛化失败: {para_error}")

            # ========== 叙述型段落摘要提取 ==========
            try:
                narrative_paragraphs = [p for p in paragraphs if p.get("classify_type") == "narrative"]
                if narrative_paragraphs:
                    narrative_results = await self._extract_narrative_summaries(
                        narrative_paragraphs, domain_label, max_concurrency=10,
                    )
                    summarized = 0
                    for para in narrative_paragraphs:
                        pid = para.get("id", "")
                        if pid in narrative_results:
                            para["template"] = narrative_results[pid]
                            summarized += 1
                    logger.info(f"叙述型摘要提取完成: {summarized}/{len(narrative_paragraphs)} 个段落")
            except Exception as narr_err:
                logger.warning(f"叙述型摘要提取失败: {narr_err}")

            # 从段落级 slot 值构建 base_info（slot-variable 统一）
            slot_values = {}
            for p in paragraphs:
                tmpl = p.get("template", {})
                if not isinstance(tmpl, dict):
                    continue
                for slot in tmpl.get("slots", []):
                    if not isinstance(slot, dict):
                        continue
                    name = slot.get("name", "")
                    value = slot.get("value")
                    if name and value is not None:
                        slot_values[name] = value
            if slot_values:
                form_data.update(slot_values)
                logger.info(f"从段落 slot 收集到 {len(slot_values)} 个变量值")

            # 计算 AI 置信度
            total_paras = len([p for p in paragraphs if p.get("classify_type") not in (None, "heading", "narrative")])
            generalized_paras = len([p for p in paragraphs if p.get("template", {}).get("generalized")])
            ai_confidence = int((generalized_paras / max(total_paras, 1)) * 100) if total_paras > 0 else 75

            await service.repo.update_task(
                task_id,
                {
                    "template_payload": template_payload,
                    "base_info": form_data,
                    "ai_confidence": ai_confidence,
                },
            )

            # 重新保存带有泛化结果的段落（段落级泛化已完成）
            await service.repo.update_task(
                task_id,
                {
                    "source_paragraphs": paragraphs,
                },
            )

            # 收集未识别插槽（泛化结果中没有 entity_ref 的插槽）
            unrecognized_slots = self._collect_unrecognized_slots(paragraphs)
            if unrecognized_slots:
                logger.info(f"收集到 {len(unrecognized_slots)} 个未识别插槽")
            await service.repo.update_task(
                task_id,
                {
                    "template_metadata": {
                        "unrecognized_slots": unrecognized_slots,
                        "domain_code": domain_code,
                    },
                },
            )

            # 逻辑关系提取：因果链/条件分支/数据引用链
            logical_relations = {}
            try:
                logical_relations = await self.extract_logical_relationships(paragraphs)
                lr_counts = {k: len(v) for k, v in logical_relations.items() if isinstance(v, list)}
                if any(lr_counts.values()):
                    logger.info(f"逻辑关系提取完成: {lr_counts}")
                    # 附加到 task metadata
                    await service.repo.update_task(
                        task_id,
                        {"logical_relations": logical_relations},
                    )
            except Exception as logic_err:
                logger.warning(f"逻辑关系提取失败（不阻断）: {logic_err}")

            await context.set_progress(80.0, "泛化完成，等待人工审核...")
            await context.set_message("泛化完成，等待人工审核...")

            # ========== 阶段4: 校验 (WAITING_REVIEW) ==========
            await service.repo.update_task(
                task_id,
                {
                    "status": "WAITING_REVIEW",
                },
            )

            await context.set_progress(95.0, "请在知识工厂中审核并提交...")
            await context.set_message("请在知识工厂中审核并提交...")

            return {
                "task_id": task_id,
                "status": "WAITING_REVIEW",
                "message": "ETL 流水线执行完成，请在知识工厂中审核并提交入库",
                "extracted_fields": len(form_data) if form_data else 0,
            }

        except asyncio.CancelledError:
            await context.set_message("任务已取消")
            await service.repo.update_task(task_id, {"status": "FAILED", "error_message": "用户取消"})
            raise
        except Exception as e:
            logger.exception(f"ETL 流水线执行失败: {task_id}")
            await service.repo.update_task(task_id, {"status": "FAILED", "error_message": str(e)})
            await context.set_progress(100.0, f"执行失败: {str(e)}")
            return {"error": str(e)}

    def _clean_chapter_title(self, title: str) -> str:
        """清洗章节标题:去双编号、纯编号返回空。"""
        import re

        text = (title or "").strip()
        if not text:
            return ""

        # 纯编号 → 空(如 "2", "3.1")
        if re.fullmatch(r"\d+(?:\.\d+)*", text):
            return ""

        # 双编号去重: "1.1.1 3.1.1 地形地貌" → "3.1.1 地形地貌"
        dual_match = re.match(r"^(\d+(?:\.\d+)*)\s+(\d+(?:\.\d+)*\s+\S.*)$", text)
        if dual_match:
            text = dual_match.group(2).strip()

        return text

    def _parse_markdown_to_paragraphs(self, markdown: str, html_content: str | None = None) -> list[dict[str, Any]]:
        """将 Markdown 文本解析为段落列表，按章节组织

        参考源系统的逻辑：
        - 表格存储为完整的 HTML 内容，而非分行存储
        - 使用 html_content 中的表格 HTML 替代 Markdown 表格行

        Args:
            markdown: Markdown 格式的文档内容
            html_content: HTML 格式的文档内容（表格以 HTML 保存）

        返回格式：
        [
            {
                "id": "p1",
                "title": "第一章 总论",      # 章节/小节标题
                "content": "",              # 段落内容（标题时为空）
                "is_title": true,           # 是否为标题
                "level": 1,                # 标题层级
                "section_path": ["1"],      # 章节路径，如 ["1", "1.1", "1.1.1"]
                "section_code": "SEC_1",    # 章节代码
                "word_count": 120,          # 字数
                "char_count": 200,          # 字符数
            },
            ...
        ]
        """
        import re

        paragraphs = []
        lines = markdown.split("\n")

        # 预提取 HTML 表格，建立 Markdown 表格位置到 HTML 的映射
        html_tables = self._extract_tables_from_html(html_content) if html_content else []
        html_table_index = 0  # 当前使用的 HTML 表格索引
        md_table_count = 0  # Markdown 中遇到的表格数量

        # 章节路径栈 - 维护当前章节层级路径
        section_path_stack: list[str] = []  # ["1", "1.1", "1.1.1"]
        paragraph_counter = 0

        # 标题层级模式
        heading_patterns = [
            (re.compile(r"^#\s+(.+)$"), 1),  # 一级标题 # 标题
            (re.compile(r"^##\s+(.+)$"), 2),  # 二级标题 ## 标题
            (re.compile(r"^###\s+(.+)$"), 3),  # 三级标题 ### 标题
            (re.compile(r"^####\s+(.+)$"), 4),  # 四级标题 #### 标题
            (re.compile(r"^#####\s+(.+)$"), 5),  # 五级标题 ##### 标题
        ]

        # 数字标题模式（匹配 "1. xxx" 或 "1.1 xxx" 等）
        numbered_pattern = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")

        # 中文章节目录模式
        chapter_pattern = re.compile(r"^第([一二三四五六七八九十百千万\d]+)章\s*(.*)$")

        # 判断是否为表格行的函数
        def is_table_line(text: str) -> bool:
            if not text.startswith("|") or not text.endswith("|"):
                return False
            # 检查是否为分隔符行
            inner = text.strip("|").strip()
            cells = [c.strip() for c in inner.split("|") if c.strip()]
            if cells and all(re.match(r"^[:\-]+\.?[:\-]*$", c) for c in cells):
                return False
            return True

        # 判断是否为标题行
        def is_heading_line(text: str) -> bool:
            # Markdown 标题
            for pattern, _ in heading_patterns:
                if pattern.match(text):
                    return True
            # 数字标题
            if numbered_pattern.match(text):
                return True
            # 中文章节
            if chapter_pattern.match(text):
                return True
            return False

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            paragraph_counter += 1
            para_id = f"p{paragraph_counter}"

            # 检查是否为标题
            is_title = False
            level = 0
            title_text = ""
            num_part = ""

            # 首先尝试 Markdown 标题格式 (# ## ###)
            for pattern, lvl in heading_patterns:
                match = pattern.match(stripped)
                if match:
                    is_title = True
                    level = lvl
                    title_text = match.group(1).strip()
                    # 去掉上游转换器生成的层级编号前缀
                    # 格式如 "1 3 区域..." 或 "1.1 3.1 自然环境..."
                    # 第一个编号是层级序号（冗余），第二个是原文编号（保留）
                    dual_num_match = re.match(r"^(\d+(?:\.\d+)*)\s+(\d+(?:\.\d+)*\s+\S.*)$", title_text)
                    if dual_num_match:
                        title_text = dual_num_match.group(2).strip()
                    # 从标题文本中提取章节编号
                    num_match = numbered_pattern.match(title_text)
                    if num_match:
                        num_part = num_match.group(1)
                    break

            # 如果不是 Markdown 标题，尝试数字标题格式 (1. xxx 或 1.1 xxx)
            if not is_title:
                num_match = numbered_pattern.match(stripped)
                if num_match:
                    num_part = num_match.group(1)
                    potential_title = num_match.group(2).strip()
                    # 判断是否为标题（标题通常较短，内容详细）
                    if len(potential_title) < 50 and not potential_title.endswith("。"):
                        is_title = True
                        title_text = self._clean_chapter_title(potential_title)
                        if not title_text:
                            is_title = False  # 清洗后为空(纯编号),不算标题
                        # 计算层级
                        dots = num_part.count(".")
                        level = dots + 1

            # 如果也不是数字标题，尝试中文章节目录模式
            if not is_title:
                ch_match = chapter_pattern.match(stripped)
                if ch_match:
                    is_title = True
                    level = 1
                    chapter_num = ch_match.group(1)
                    title_text = ch_match.group(2).strip() if ch_match.group(2) else stripped
                    num_part = self._chinese_to_arabic(chapter_num)
                    if num_part == chapter_num:
                        direct_match = re.match(r"^第(\d+)章", stripped)
                        if direct_match:
                            num_part = direct_match.group(1)
                        else:
                            num_part = str(len([p for p in paragraphs if p.get("level", 0) == 1]) + 1)

            if is_title:
                # 计算章节路径
                if num_part:
                    path_parts = num_part.split(".")
                    num_level = len(path_parts)

                    if num_level == 1:
                        level = 1
                    elif num_level == 2:
                        level = 2
                    elif num_level >= 3:
                        level = 3

                    if level == 1:
                        section_path_stack = [num_part]
                    elif level == 2:
                        if len(section_path_stack) >= 1:
                            section_path_stack[0] = path_parts[0]
                        else:
                            section_path_stack.append(path_parts[0])
                        if len(section_path_stack) >= 2:
                            section_path_stack[1] = num_part
                        else:
                            section_path_stack.append(num_part)
                        section_path_stack = section_path_stack[:2]
                    elif level >= 3:
                        while len(section_path_stack) < 2:
                            section_path_stack.append("1")
                        section_path_stack = section_path_stack[:2] + [num_part]
                        section_path_stack = section_path_stack[:3]
                else:
                    if level == 1:
                        section_path_stack = [str(len([p for p in paragraphs if p.get("level", 0) == 1]) + 1)]
                    elif level == 2:
                        if len(section_path_stack) >= 1:
                            pass
                        else:
                            section_path_stack = ["1"]
                        if len(section_path_stack) >= 2:
                            pass
                        else:
                            section_path_stack.append("1")
                        section_path_stack = section_path_stack[:2]
                    else:
                        section_path_stack = section_path_stack[:level] if section_path_stack else ["1"]

                section_code = f"SEC_{'_'.join(section_path_stack)}"

                paragraphs.append(
                    {
                        "id": para_id,
                        "title": title_text,
                        "content": "",
                        "is_title": True,
                        "level": level,
                        "section_path": section_path_stack.copy(),
                        "section_code": section_code,
                        "word_count": len(title_text),
                        "char_count": len(title_text),
                        "parent_title": section_path_stack[0] if section_path_stack else "",
                        "source": "heading",
                    }
                )
                i += 1
            elif is_table_line(stripped):
                # 表格行：收集连续的 Markdown 表格行，然后用 HTML 表格替代
                table_lines = []
                while i < len(lines) and is_table_line(lines[i].strip()):
                    table_lines.append(lines[i].strip())
                    i += 1

                if len(table_lines) >= 2 and html_table_index < len(html_tables):
                    # 使用对应的 HTML 表格
                    html_table = html_tables[html_table_index]
                    html_table_index += 1
                    md_table_count += 1

                    paragraphs.append(
                        {
                            "id": para_id,
                            "title": "",
                            "content": html_table,  # 存储完整 HTML 表格
                            "is_title": False,
                            "level": 0,
                            "section_path": section_path_stack.copy() if section_path_stack else [],
                            "section_code": f"SEC_{'_'.join(section_path_stack)}" if section_path_stack else "",
                            "word_count": len(html_table),
                            "char_count": len(html_table),
                            "parent_title": section_path_stack[0] if section_path_stack else "",
                            "source": "table",
                            "is_table": True,
                            "table_format": "html",
                        }
                    )
                elif len(table_lines) == 1:
                    # 单行表格作为普通段落
                    paragraphs.append(
                        {
                            "id": para_id,
                            "title": "",
                            "content": table_lines[0],
                            "is_title": False,
                            "level": 0,
                            "section_path": section_path_stack.copy() if section_path_stack else [],
                            "section_code": f"SEC_{'_'.join(section_path_stack)}" if section_path_stack else "",
                            "word_count": len(table_lines[0]),
                            "char_count": len(table_lines[0]),
                            "parent_title": section_path_stack[0] if section_path_stack else "",
                            "source": "paragraph",
                            "is_table": False,
                        }
                    )
                    i += 1
                else:
                    # 回退：合并 Markdown 表格行
                    content = "\n".join(table_lines)
                    paragraphs.append(
                        {
                            "id": para_id,
                            "title": "",
                            "content": content,
                            "is_title": False,
                            "level": 0,
                            "section_path": section_path_stack.copy() if section_path_stack else [],
                            "section_code": f"SEC_{'_'.join(section_path_stack)}" if section_path_stack else "",
                            "word_count": len(content),
                            "char_count": len(content),
                            "parent_title": section_path_stack[0] if section_path_stack else "",
                            "source": "table",
                            "is_table": True,
                            "table_format": "markdown",
                        }
                    )
            else:
                # 普通段落
                paragraphs.append(
                    {
                        "id": para_id,
                        "title": "",
                        "content": stripped,
                        "is_title": False,
                        "level": 0,
                        "section_path": section_path_stack.copy() if section_path_stack else [],
                        "section_code": f"SEC_{'_'.join(section_path_stack)}" if section_path_stack else "",
                        "word_count": len(stripped),
                        "char_count": len(stripped),
                        "parent_title": section_path_stack[0] if section_path_stack else "",
                        "source": "paragraph",
                        "is_table": False,
                    }
                )
                i += 1

        title_count = sum(1 for p in paragraphs if p.get("is_title"))
        table_count = sum(1 for p in paragraphs if p.get("is_table"))
        logger.info(f"段落解析完成: {len(paragraphs)} 个段落, {title_count} 个标题, {table_count} 个表格")
        return paragraphs

    def _chinese_to_arabic(self, cn_num: str) -> str:
        """将中文数字转换为阿拉伯数字"""
        cn_map = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
            "百": "100",
            "千": "1000",
            "万": "10000",
        }
        result = cn_num
        for cn, num in cn_map.items():
            result = result.replace(cn, num)
        return result

    def _compute_section_path(self, level: int, title: str, num_part: str | None = None) -> list[str]:
        """计算章节路径（已废弃，保持向后兼容）"""
        if num_part:
            return num_part.split(".")
        return []

    def _generate_section_code(self, title: str, section_path: list[str]) -> str:
        """生成章节代码（已废弃，保持向后兼容）"""
        if section_path:
            path_str = "_".join(section_path)
            return f"SEC_{path_str}".upper()
        return f"SEC_{hash(title) % 100000:05d}"

    # ========== 段落分类 (CLASSIFY) ==========

    LEGAL_PATTERNS: ClassVar[list[str]] = [
        r'《[^》]+》\s*[（(]\s*[A-Z]{1,3}\s*[\d\-]+',
        r'国务院令第\d+号',
        r'[环发改工信环办][发办审能源环评]*〔\d{4}〕\d+号',
        r'《中华人民共和国.+法》',
        r'《.+条例》',
        r'《.+规定》',
        r'(?:GB|HJ|MT|AQ|TB|DL|SL|DZ|CJJ|JGJ|YS|EJ)/?[T/TZ]?[\s\-]*\d+(?:[.\-]\d+)*[-—]\d+',
        r'《.+标准》',
        r'《.+规范》',
        r'《.+导则》',
        r'《.+办法》',
    ]

    # 参数型判定：量纲单位模式
    _UNIT_PATTERNS: ClassVar[list[str]] = [
        r'\d+(?:\.\d+)?\s*(?:mg/[mNL³]|μg/[mNL³]|g/[mNL³]|kg|t|吨|m[²³]|km[²³]|hm²|亩|公顷|万?m[²³]|',
        r'mg/m³|μg/m³|g/m³|mg/L|μg/L|g/L|mg/Nm³|',
        r'dB|dB\(A\)|',
        r'm[³]/[hd]|万m[³]/[da]|t/d|t/a|万t/a|',
        r'MW|kW|kV|kPa|MPa|Pa|',
        r'mm|cm|m|km|',
        r'%|‰|ppm|',
        r'℃|°C|',
        r'万元|亿元|元|',
        r'hm²|km²|亩',
        r')',
    ]
    _UNIT_RE: ClassVar[str] = r'\d+(?:\.\d+)?\s*(?:mg/[mNL³3]|μg/[mNL³3]|g/[mNL³3]|kg|t|吨|m[²23]|km[²23]|hm2|亩|公顷|mg/L|μg/L|g/L|mg/Nm3|dB|dB\([A]\)|m3/[dha]|t/[da]|MW|kW|kV|kPa|MPa|Pa|mm|cm|km|%|‰|ppm|℃|°C|万元|亿元|元|hm2)'

    # 参数型判定：赋值/比较动词
    _PARAM_VERBS: ClassVar[list[str]] = [
        r'(?:为|达|约|超过|不低于|不大于|不超过|等于|约为|高达|低至|介于|范围[为是])\s*[\d.]+',
        r'[\d.]+\s*(?:[～~—\-]\s*[\d.]+)',
    ]

    # 参数型判定：slot 名称模式（可复用参数）
    _SLOT_PATTERNS: ClassVar[list[str]] = [
        r'(?:面积|距离|长度|宽度|深度|高度|厚度|坡度|浓度|排放量|排放浓度|产能|产量|储量|水量|流量'
        r'|人口|户数|投资|总投资|预算|费用|温度|湿度|风速|降水量|水位|标高|标段|占地'
        r'|面积|规模|容量|负荷|效率|利用率|达标率|合格率|回收率|去除率|处理率)',
    ]

    # 叙述型子类型关键词
    _NARRATIVE_SUBTYPE_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "conclusion": ["结论", "综合结论", "总体结论", "评价结论", "综上所述", "总而言之", "结果表明", "分析表明"],
        "methodology": ["方法", "采用.*方法", "评价方法", "预测方法", "计算方法", "分析方法", "技术路线", "工作方法", "调查方法"],
        "summary": ["概况", "综述", "简述", "概述", "基本情况", "总体情况", "项目概况", "区域概况", "现状概况"],
        "background": ["背景", "由来", "历史", "沿革", "缘起", "目的和意义", "任务来源"],
    }

    # 表格子类型关键词
    _TABLE_SUBTYPE_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "monitoring": ["监测", "实测", "检测结果", "采样", "现状监测", "验收监测"],
        "compliance": ["达标", "排放标准", "标准限值", "比较", "对比分析", "达标分析"],
        "standard_limit": ["标准值", "限值", "标准限值", "排放限值", "质量标准", "控制标准"],
    }

    def classify_paragraphs(self, paragraphs: list[dict]) -> list[dict]:
        """段落分类（CLASSIFY 阶段）：将段落分为 heading/table/figure/formula/list/legal_reference/parameter/narrative，并附加子类型标签"""
        import re as _re

        for para in paragraphs:
            content = para.get("content", "").strip()
            title = para.get("title", "")
            tags = []

            # 1. 标题型
            if para.get("is_title"):
                para["classify_type"] = "heading"
                para["classify_tags"] = tags
                continue

            # 2. 表格型
            if para.get("is_table"):
                para["classify_type"] = "table"
                tags.append(self._match_table_subtype(content, title))
                para["classify_tags"] = [t for t in tags if t]
                continue

            # 3. 图片/示意图型
            if self._is_figure(content):
                para["classify_type"] = "figure"
                para["classify_tags"] = tags
                continue

            # 4. 公式/计算模型型
            if self._is_formula(content, title):
                para["classify_type"] = "formula"
                para["classify_tags"] = tags
                continue

            # 5. 列表型
            if self._is_list_block(content):
                para["classify_type"] = "list"
                para["classify_tags"] = tags
                continue

            # 6. 标准引用型
            if self._is_legal_reference(content):
                para["classify_type"] = "legal_reference"
                tags.append(self._match_legal_subtype(content))
                para["classify_tags"] = [t for t in tags if t]
                continue

            # 7. 参数型（细化判定：必须含可量化的参数特征）
            has_numeric = bool(_re.search(r'\d+(?:\.\d+)?', content))
            if has_numeric and len(content) < 500:
                has_unit = bool(_re.search(self._UNIT_RE, content, _re.IGNORECASE))
                has_param_verb = any(_re.search(p, content) for p in self._PARAM_VERBS)
                has_slot_name = any(_re.search(p, content) for p in self._SLOT_PATTERNS)

                if has_unit or has_param_verb or has_slot_name:
                    para["classify_type"] = "parameter"
                    if has_unit:
                        tags.append("measurable")
                    if has_slot_name:
                        tags.append("reusable")
                    if not has_unit and not has_slot_name:
                        tags.append("descriptive")
                    para["classify_tags"] = tags
                    continue

            # 8. 叙述性正文
            para["classify_type"] = "narrative"
            subtype = self._match_narrative_subtype(content, title)
            if subtype:
                tags.append(subtype)
            para["classify_tags"] = tags

        return paragraphs

    def _match_table_subtype(self, content: str, title: str) -> str:
        text = f"{title} {content}".lower()
        for subtype, keywords in self._TABLE_SUBTYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return subtype
        return "key_value"

    def _match_legal_subtype(self, content: str) -> str:
        import re as _re
        if _re.search(r'《中华人民共和国.+法》', content):
            return "law"
        if '条例' in content:
            return "admin_regulation"
        if _re.search(r'(?:GB|HJ|MT|AQ|TB|DL|SL|DZ)/?[T]?[\s\-]*\d+', content):
            return "technical_standard"
        if '规定' in content or '办法' in content:
            return "ministry_rule"
        return "general"

    def _match_narrative_subtype(self, content: str, title: str) -> str:
        import re as _re
        text = f"{title} {content}"
        for subtype, keywords in self._NARRATIVE_SUBTYPE_KEYWORDS.items():
            for kw in keywords:
                if _re.search(kw, text):
                    return subtype
        return ""

    def _is_figure(self, content: str) -> bool:
        import re as _re
        if not content:
            return False
        if _re.match(r'^!\[.*?\]\(.*?\)$', content):
            return True
        if '<!--image-->' in content or '<img ' in content:
            return True
        return False

    def _is_formula(self, content: str, title: str = "") -> bool:
        import re as _re
        if _re.search(r'\$[^$]+\$', content):
            return True
        if _re.search(r'\$\$.+?\$\$', content, _re.DOTALL):
            return True
        if '=' in content and _re.search(r'[×÷·∑∫√π]', content):
            return True
        formula_title_keywords = ["计算公式", "预测模式", "计算方法", "数学模型"]
        if any(kw in title for kw in formula_title_keywords):
            return True
        return False

    def _is_list_block(self, content: str) -> bool:
        import re as _re
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if len(lines) < 2:
            return False
        numbered = sum(1 for l in lines if _re.match(r'^[（(]\d+[)）]', l)
                       or _re.match(r'^\d+[.、）)]', l)
                       or _re.match(r'^[-•]', l))
        return numbered / len(lines) >= 0.6

    def _is_legal_reference(self, text: str) -> bool:
        import re as _re
        return any(_re.search(p, text) for p in self.LEGAL_PATTERNS)

    def _extract_effective_date(self, text: str) -> str | None:
        """从法律引用文本中提取生效日期"""
        import re as _re
        # 匹配日期格式：2015-01-01, 2015年1月1日, 2015.1.1
        m = _re.search(r'(\d{4})[-年.]\s*(\d{1,2})[-月.]\s*(\d{1,2})', text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # 仅年份
        m = _re.search(r'(\d{4})\s*年(?:发布|施行|实施)', text)
        if m:
            return f"{m.group(1)}-01-01"
        return None

    # ========== 公式提取 ==========

    # 常见物理量符号映射
    SYMBOL_MAP: ClassVar[dict[str, dict]] = {
        "C": {"name": "地面浓度", "unit": "mg/m³"},
        "Q": {"name": "源强", "unit": "mg/s"},
        "u": {"name": "风速", "unit": "m/s"},
        "H": {"name": "有效排放高度", "unit": "m"},
        "LA": {"name": "A声级", "unit": "dB"},
        "Leq": {"name": "等效声级", "unit": "dB"},
        "Pi": {"name": "排气速率", "unit": "m³/s"},
        "Ci": {"name": "污染物浓度", "unit": "mg/m³"},
        "V": {"name": "体积", "unit": "m³"},
        "S": {"name": "面积", "unit": "m²"},
        "L": {"name": "距离/长度", "unit": "m"},
        "W": {"name": "产能/产量", "unit": "Mt/a"},
        "T": {"name": "温度", "unit": "℃"},
        "P": {"name": "压力", "unit": "Pa"},
        "q": {"name": "流量", "unit": "m³/d"},
    }

    def _extract_formula_symbols(self, content: str) -> list[str]:
        """从公式文本中提取变量符号"""
        import re as _re
        # LaTeX: 提取 \command{...} 外的单字母/已知多字母变量
        symbols = []
        seen = set()
        # 匹配常见 LaTeX 格式的变量
        for m in _re.finditer(r'([A-Za-z]{1,3})(?![a-z])', content):
            sym = m.group(1)
            if sym in ('frac', 'exp', 'log', 'sin', 'cos', 'tan', 'sqrt', 'sum', 'int', 'min', 'max', 'the', 'not', 'and', 'for'):
                continue
            if sym not in seen:
                symbols.append(sym)
                seen.add(sym)
        return symbols

    def extract_formula(self, para: dict) -> dict | None:
        """提取公式结构 + 变量映射"""
        import re as _re
        content = para.get("content", "")
        if not content:
            return None

        section_path = para.get("section_path", [])
        title = para.get("title", "")

        result = {
            "original": content,
            "format": "latex" if ("$" in content or "59" in content) else "text",
            "variables": [],
            "purpose": self._infer_formula_purpose(title, section_path),
        }

        symbols = self._extract_formula_symbols(content)
        for sym in symbols:
            mapping = self.SYMBOL_MAP.get(sym, {"name": sym, "unit": None})
            entity_ref = self._symbol_to_entity_ref(sym)
            result["variables"].append({
                "symbol": sym,
                "name": mapping["name"],
                "unit": mapping["unit"],
                "entity_ref": entity_ref,
            })

        return result

    def _infer_formula_purpose(self, title: str, section_path: list) -> str:
        """从章节标题推断公式用途"""
        path_str = "/".join(str(p) for p in section_path) if section_path else ""
        purpose_map = [
            ("浓度|扩散|落地", "预测污染物浓度分布"),
            ("噪声|声级", "预测噪声影响范围"),
            ("涌水量|排水", "预测矿井涌水量"),
            ("沉降|沉陷|地表移动", "预测地表沉陷范围"),
            ("预测|估算|计算", "预测计算"),
        ]
        combined = f"{title} {path_str}"
        for pattern, purpose in purpose_map:
            if re.search(pattern, combined):
                return purpose
        return "通用计算"

    def _symbol_to_entity_ref(self, sym: str) -> str:
        """将符号映射到实体引用 key"""
        _sym_entity_map = {
            "C": "ground_concentration",
            "Q": "emission_rate",
            "u": "wind_speed",
            "H": "effective_height",
            "LA": "noise_level_a",
            "Leq": "equivalent_noise_level",
            "q": "water_flow",
            "W": "production_capacity",
        }
        return _sym_entity_map.get(sym, "")

    # ========== 图片多模态提取 ==========

    FIGURE_ANALYSIS_PROMPT: ClassVar[str] = (
        "分析这张来自环境影响评价报告的图片，识别：\n"
        "1. 图片类型：流程图 / 位置示意图 / 数据图表 / 照片 / 其他\n"
        "2. 如果是流程图：提取完整步骤序列（按顺序）\n"
        "3. 如果是数据图表：描述数据趋势和关键数值\n"
        "4. 如果是位置示意图：描述空间关系\n"
        "5. 图片标题/说明文字\n\n"
        "以 JSON 格式输出，包含 figure_type、caption、steps(流程图时)、data_trend(数据图表时)、spatial_description(位置图时) 字段。"
    )

    def _extract_image_url(self, content: str) -> str:
        """从段落内容中提取图片 URL"""
        import re as _re
        # Markdown 图片
        m = _re.search(r'!\[.*?\]\((.*?)\)', content)
        if m:
            return m.group(1)
        # HTML img 标签
        m = _re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
        if m:
            return m.group(1)
        return ""

    async def extract_figure_with_vlm(self, para: dict) -> dict:
        """用多模态 LLM 提取图片内容"""
        content = para.get("content", "")
        image_url = self._extract_image_url(content)

        result = {
            "figure_type": "unknown",
            "caption": para.get("title", ""),
            "url": image_url,
        }

        if not image_url:
            return result

        try:
            from yuxi.models.chat import select_model
            model = select_model()

            # 尝试多模态调用（需要支持 vision 的模型）
            if hasattr(model, "call_vision") or hasattr(model, "analyze_image"):
                fn = getattr(model, "call_vision", None) or getattr(model, "analyze_image")
                response = await fn(image_url, self.FIGURE_ANALYSIS_PROMPT)
            else:
                # 降级：用文本模型描述图片 URL
                prompt = f"根据以下图片 URL 所在的报告上下文，推断图片类型。\nURL: {image_url}\n章节: {para.get('title', '')}\n{self.FIGURE_ANALYSIS_PROMPT}\n\n注意：你无法看到图片，请根据上下文推断。"
                response = await model.call(prompt)

            text = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_figure_result(text)
            result.update(parsed)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"图片多模态提取失败（不阻断）: {e}")

        return result

    def _parse_figure_result(self, text: str) -> dict:
        """解析 LLM 返回的图片分析 JSON"""
        import json
        import re as _re
        try:
            match = _re.search(r'\{[\s\S]*\}', text)
            if match:
                data = json.loads(match.group())
                return {
                    "figure_type": data.get("figure_type", "unknown"),
                    "caption": data.get("caption", ""),
                    "content": data,
                    "steps": data.get("steps", []),
                    "data_trend": data.get("data_trend", ""),
                    "spatial_description": data.get("spatial_description", ""),
                }
        except (json.JSONDecodeError, TypeError):
            pass
        return {}

    # ========== 图片多模态提取 END ==========

    # ========== 法律引用提取 ==========

    # 9 层分类
    LEGAL_TYPE_MAP: ClassVar[dict[str, str]] = {
        "法律": "law",
        "行政法规": "admin_regulation",
        "地方性法规": "local_regulation",
        "部门规章": "ministry_rule",
        "地方规章": "local_rule",
        "技术规范": "technical_standard",
        "相关规划": "national_plan",
        "项目资料": "project_material",
    }

    def extract_legal_references(self, paragraphs: list[dict]) -> list[dict]:
        """从 legal_reference 类型段落中提取结构化法律引用"""
        import re as _re

        results = []
        for para in paragraphs:
            if para.get("classify_type") != "legal_reference":
                continue
            refs = self._parse_legal_list(para.get("content", ""), para)
            results.extend(refs)
        return results

    def _parse_legal_list(self, text: str, para: dict) -> list[dict]:
        """解析法律引用列表（编制依据场景）"""
        import re as _re

        results = []
        # 匹配模式：《名称》（编号/文号）
        patterns = [
            # （N）《名称》（编号）
            _re.compile(
                r'[（(]\s*(\d+)\s*[)）]\s*《([^》]+)》\s*'
                r'(?:[（(]\s*([^）)]+?)\s*[)）])?',
                _re.DOTALL,
            ),
            # 《名称》（编号）
            _re.compile(
                r'《([^》]+)》\s*[（(]\s*([^）)]+?)\s*[)）]',
            ),
        ]

        # 确定引用层级
        section_path = para.get("section_path", [])
        title = para.get("title", "")
        parent_title = para.get("parent_title", "")
        scope = "project"
        ref_type = "technical_standard"

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # 尝试匹配
            matched = False
            for pat in patterns:
                m = pat.search(line)
                if m:
                    groups = m.groups()
                    if len(groups) == 3:
                        _, name, code = groups
                    elif len(groups) == 2:
                        name, code = groups
                    else:
                        continue

                    # 推断分类
                    ref_type, scope = self._infer_legal_type(name, code or "")

                    effective_date = self._extract_effective_date(line)
                    results.append({
                        "name": (name or "").strip(),
                        "code": (code or "").strip() or None,
                        "type": ref_type,
                        "scope": scope,
                        "authority": self._infer_authority(name or "", code or ""),
                        "effective_date": effective_date,
                        "status": "effective",
                        "source_para_id": para.get("id"),
                        "chapter": parent_title or title,
                    })
                    matched = True
                    break

            if not matched:
                # 单行中可能包含标准编号（如 GB13271-2014）但没有书名号包裹
                std_match = _re.search(
                    r'([A-Z]{1,3}[\d.\-]+\s*[-—]\s*\d{4})\s*《?([^》\n,，]+)》?',
                    line,
                )
                if std_match:
                    code, name = std_match.groups()
                    ref_type, scope = self._infer_legal_type(name or "", code)
                    effective_date = self._extract_effective_date(line)
                    results.append({
                        "name": (name or "").strip(),
                        "code": (code or "").strip(),
                        "type": ref_type,
                        "scope": scope,
                        "authority": self._infer_authority(name or "", code),
                        "effective_date": effective_date,
                        "status": "effective",
                        "source_para_id": para.get("id"),
                        "chapter": parent_title or title,
                    })

        return results

    def _infer_legal_type(self, name: str, code: str) -> tuple[str, str]:
        """推断法律引用的类型和范围"""
        import re as _re

        if "中华人民共和国" in name and name.endswith("法"):
            return "law", "national"
        if any(k in name for k in ("条例", "规定")):
            if "省" in name or "市" in name:
                return "admin_regulation", "regional"
            return "admin_regulation", "national"
        if "国务院" in name or "令" in code:
            return "admin_regulation", "national"
        if _re.match(r'^[A-Z]{1,3}[\d.\-]+', code):
            return "technical_standard", "national"
        if "规划" in name:
            if "省" in name or "市" in name:
                return "national_plan", "regional"
            return "national_plan", "national"
        return "technical_standard", "national"

    def _infer_authority(self, name: str, code: str) -> str:
        """推断制定机关"""
        import re as _re

        if "中华人民共和国" in name:
            return "全国人大"
        if "国务院" in name:
            return "国务院"
        authority_map = {
            "HJ": "生态环境部",
            "GB": "国家标准化管理委员会",
            "MT": "煤炭工业出版社",
            "AQ": "应急管理部",
            "TB": "交通运输部",
            "DL": "国家能源局",
            "SL": "水利部",
        }
        for prefix, auth in authority_map.items():
            if code.startswith(prefix):
                return auth
        return ""

    # ========== 法律引用提取 END ==========

    # ========== 正文标准引用 LLM 提取（场景B） ==========

    LEGAL_EXTRACT_PROMPT = """分析以下段落中引用的标准/法规/规范，提取：

1. 标准编号（如 HJ2.2-2018, GB13271-2014）
2. 标准名称
3. 引用类型：applicability（适用性判定）/ compliance（合规性验证）/ classification（分类定级）
4. 引用上下文（摘录原文中的关键句，不超过100字）

严格按 JSON 数组格式输出，不要输出其他内容：
[{"code": "标准编号", "name": "标准名称", "usage": "引用类型", "context": "引用上下文"}]

如果没有引用标准，输出空数组 []"""

    async def extract_legal_references_from_text(self, paragraphs: list[dict]) -> list[dict]:
        """场景B：从正文段落中用 LLM 提取标准引用

        仅对 parameter/narrative 类型、且包含标准编号模式的段落调用。
        """
        import re as _re

        # 筛选含标准编号模式的正文段落（排除已经是 legal_reference 的）
        std_code_pattern = _re.compile(r'[A-Z]{1,3}[\d.\-]+\s*[-—]\s*\d{4}')
        target_paragraphs = []
        for para in paragraphs:
            if para.get("classify_type") in ("legal_reference", "heading", "table", "figure", "formula"):
                continue
            content = para.get("content", "")
            if std_code_pattern.search(content):
                target_paragraphs.append(para)

        if not target_paragraphs:
            return []

        # 按章节分组，减少 LLM 调用次数
        all_results = []
        try:
            from yuxi.models.chat import select_model

            model = select_model()
            # 限制：最多处理 5 个段落，避免过多 LLM 调用
            for para in target_paragraphs[:5]:
                content = para.get("content", "")[:500]
                prompt = f"{self.LEGAL_EXTRACT_PROMPT}\n\n段落内容：\n{content}"
                try:
                    response = await model.call(prompt)
                    text = response.content if hasattr(response, "content") else str(response)
                    refs = self._parse_legal_extract_response(text, para)
                    all_results.extend(refs)
                except Exception as e:
                    logger.warning(f"正文标准引用提取失败: {e}")

            if all_results:
                logger.info(f"正文标准引用提取完成: {len(all_results)} 条")
        except Exception as e:
            logger.warning(f"正文标准引用提取模块初始化失败: {e}")

        return all_results

    def _parse_legal_extract_response(self, text: str, para: dict) -> list[dict]:
        """解析 LLM 返回的标准引用 JSON"""
        import re as _re

        try:
            # 尝试提取 JSON 数组
            match = _re.search(r'\[[\s\S]*\]', text)
            if not match:
                return []
            import json
            items = json.loads(match.group())
            results = []
            for item in items:
                if not isinstance(item, dict) or not item.get("code"):
                    continue
                ref_type, scope = self._infer_legal_type(item.get("name", ""), item["code"])
                results.append({
                    "name": item.get("name", ""),
                    "code": item.get("code", ""),
                    "type": ref_type,
                    "scope": scope,
                    "usage": item.get("usage", ""),
                    "context": item.get("context", ""),
                    "authority": self._infer_authority(item.get("name", ""), item.get("code", "")),
                    "effective_date": item.get("effective_date"),
                    "status": "effective",
                    "source_para_id": para.get("id"),
                    "chapter": para.get("parent_title", ""),
                    "scene": "body_text",
                })
            return results
        except (json.JSONDecodeError, ValueError):
            return []

    # ========== 正文标准引用 LLM 提取 END ==========

    # ========== 表格 Schema 提取 ==========

    def _extract_formulas(self, paragraphs: list[dict]) -> int:
        """对 formula 类型段落调用 extract_formula，结果写入 para.template.formula"""
        count = 0
        for para in paragraphs:
            if para.get("classify_type") != "formula":
                continue
            result = self.extract_formula(para)
            if result:
                tmpl = para.get("template") or {}
                tmpl["formula"] = result
                para["template"] = tmpl
                count += 1
        return count

    async def _extract_figures(self, paragraphs: list[dict]) -> int:
        """对 figure 类型段落调用 extract_figure_with_vlm"""
        count = 0
        for para in paragraphs:
            if para.get("classify_type") != "figure":
                continue
            result = await self.extract_figure_with_vlm(para)
            if result and result.get("figure_type") != "unknown":
                tmpl = para.get("template") or {}
                tmpl["figure"] = result
                para["template"] = tmpl
                count += 1
        return count

    # ========== 分章节提取 ==========

    # 按 (domain, report_type) 预定义的章节级局部 Schema
    # 每个章节最多 10-20 个变量，避免全局 149 变量的提取失败问题
    LOCAL_SCHEMA_MAP: ClassVar[dict[str, dict[str, dict]]] = {
        "coal.eia_construction": {
            "3.1": {  # 自然环境概况
                "地理位置": {"data_type": "text"},
                "地貌类型": {"data_type": "text", "type": "enum",
                             "vocabulary": ["丘陵", "平原", "山地", "高原", "盆地", "沙漠", "戈壁"]},
                "海拔范围": {"data_type": "text", "unit": "m"},
                "气候类型": {"data_type": "text"},
                "年均温": {"data_type": "number", "unit": "℃"},
                "年均降水量": {"data_type": "number", "unit": "mm"},
                "主要河流": {"data_type": "text"},
                "年平均风速": {"data_type": "number", "unit": "m/s"},
                "主导风向": {"data_type": "text"},
            },
            "3.2": {  # 社会经济概况
                "行政区划": {"data_type": "text"},
                "人口数量": {"data_type": "number", "unit": "万人"},
                "GDP": {"data_type": "number", "unit": "亿元"},
                "主要产业": {"data_type": "text"},
            },
            "1.1": {  # 规划背景
                "项目名称": {"data_type": "text", "entity_ref": "project_name"},
                "建设单位": {"data_type": "text", "entity_ref": "construction_unit"},
                "设计产能": {"data_type": "number", "unit": "Mt/a", "entity_ref": "design_capacity"},
                "开采方式": {"data_type": "text", "type": "enum",
                             "vocabulary": ["井工", "露天", "井工+露天"],
                             "entity_ref": "mining_type"},
                "矿区面积": {"data_type": "number", "unit": "km²", "entity_ref": "mine_area"},
            },
        },
        "coal.eia_planning": {
            "3.1": {
                "地理位置": {"data_type": "text"},
                "地貌类型": {"data_type": "text", "type": "enum",
                             "vocabulary": ["丘陵", "平原", "山地", "高原", "盆地"]},
                "海拔范围": {"data_type": "text", "unit": "m"},
                "气候类型": {"data_type": "text"},
                "主要河流": {"data_type": "text"},
            },
            "1.1": {
                "项目名称": {"data_type": "text", "entity_ref": "project_name"},
                "规划面积": {"data_type": "number", "unit": "km²"},
                "规划产能": {"data_type": "number", "unit": "Mt/a"},
            },
        },
    }

    def _get_local_schema(self, chapter_path: str, domain_code: str = "", report_type_code: str = "") -> dict | None:
        """按章节路径匹配局部提取 Schema"""
        # 精确匹配 domain.report_type
        key = f"{domain_code}.{report_type_code}"
        domain_schemas = self.LOCAL_SCHEMA_MAP.get(key, {})
        if not domain_schemas:
            # 回退到同 domain 下任意 report_type
            for k, v in self.LOCAL_SCHEMA_MAP.items():
                if k.startswith(f"{domain_code}."):
                    domain_schemas = v
                    break
        if not domain_schemas:
            return None

        # 匹配章节路径（支持前缀匹配）
        if chapter_path in domain_schemas:
            return domain_schemas[chapter_path]

        # 取最后一级编号匹配
        parts = chapter_path.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in domain_schemas:
                return domain_schemas[prefix]

        return None

    def _group_by_chapter(self, paragraphs: list[dict]) -> dict[str, list[dict]]:
        """将段落按章节分组"""
        chapters: dict[str, list[dict]] = {}
        current_chapter = "0"
        for para in paragraphs:
            if para.get("is_title"):
                sp = para.get("section_path", [])
                if sp:
                    current_chapter = str(sp[0]) if len(sp) == 1 else ".".join(str(p) for p in sp[:2])
                continue
            if current_chapter not in chapters:
                chapters[current_chapter] = []
            chapters[current_chapter].append(para)
        return chapters

    async def extract_by_chapter(self, paragraphs: list[dict], domain_code: str = "", report_type_code: str = "") -> dict[str, dict]:
        """按章节分批提取，每批只提取该章节相关的变量"""
        chapters = self._group_by_chapter(paragraphs)
        results: dict[str, dict] = {}

        for chapter_path, chapter_paras in chapters.items():
            local_schema = self._get_local_schema(chapter_path, domain_code, report_type_code)
            if not local_schema:
                continue

            # 只用该章节的 parameter 段落作为上下文
            context_parts = []
            for p in chapter_paras:
                ct = p.get("classify_type", "")
                if ct in ("parameter", "narrative", "list"):
                    text = p.get("content", "")
                    if text:
                        context_parts.append(text[:300])
            if not context_parts:
                continue

            context = "\n".join(context_parts)[:2000]

            # 构建 prompt
            schema_lines = []
            for name, spec in local_schema.items():
                dt = spec.get("data_type", "text")
                unit = f" ({spec['unit']})" if spec.get("unit") else ""
                schema_lines.append(f'  "{name}": "{dt}{dt}"')
            schema_text = "{\n" + ",\n".join(schema_lines) + "\n}"

            prompt = (
                f"从以下章节内容中提取结构化变量值。\n\n"
                f"章节: {chapter_path}\n"
                f"需要提取的变量:\n{schema_text}\n\n"
                f"章节内容:\n{context}\n\n"
                f"输出 JSON，只包含在文档中明确提到的变量，未找到的不输出。严格只输出 JSON。"
            )

            try:
                from yuxi.models.chat import select_model
                model = select_model()
                response = await model.call(prompt)
                text = response.content if hasattr(response, "content") else str(response)

                import json
                import re
                match = re.search(r'\{[\s\S]*\}', text)
                if match:
                    extracted = json.loads(match.group())
                    # 过滤 None 值
                    extracted = {k: v for k, v in extracted.items() if v is not None}
                    if extracted:
                        results[chapter_path] = extracted
            except Exception as e:
                logger.debug(f"章节 {chapter_path} 提取失败: {e}")

        return results

    # ========== 逻辑关系提取 ==========

    LOGIC_EXTRACT_PROMPT: ClassVar[str] = (
        "分析以下段落组中的逻辑关系，识别：\n\n"
        "1. 因果链：哪些段落之间存在因果关系？提取前提->推理->结论的链路。\n"
        "   格式: {\"causal_chains\": [{\"cause_para_id\": \"p_id\", \"effect_para_id\": \"p_id\", \"relation\": \"描述\"}]}\n\n"
        "2. 条件分支：是否有条件判断（如果/若/当...时）？提取条件表达式。\n"
        "   格式: {\"conditions\": [{\"para_id\": \"p_id\", \"expression\": \"条件表达式\", \"consequence\": \"结果描述\"}]}\n\n"
        "3. 数据引用：段落中引用了哪些数据？数据来源于哪个表格或前文段落？\n"
        "   格式: {\"data_refs\": [{\"para_id\": \"p_id\", \"source\": \"table_id或para_id\", \"data_fields\": [\"字段名\"]}]}\n\n"
        "输出合并为一个 JSON 对象，包含 causal_chains、conditions、data_refs 三个数组。严格只输出 JSON。"
    )

    async def extract_logical_relationships(self, paragraphs: list[dict]) -> dict:
        """按章节粒度提取段落间的逻辑关系（因果链/条件分支/数据引用）"""
        chapters = self._group_by_chapter(paragraphs)
        all_results: dict = {"causal_chains": [], "conditions": [], "data_refs": []}

        for chapter_path, chapter_paras in chapters.items():
            # 只对有 parameter/含逻辑关键词的章节调用
            para_texts = []
            para_ids = []
            for p in chapter_paras:
                content = p.get("content", "")
                if not content:
                    continue
                # 筛选含逻辑标志或 parameter 型的段落
                ct = p.get("classify_type", "")
                has_logic_kw = any(kw in content for kw in ["因此", "所以", "如果", "若", "当", "则", "需", "导致", "引起", "造成"])
                if ct == "parameter" or has_logic_kw:
                    para_texts.append(f"段落ID: {p.get('id', 'p?')}")
                    para_texts.append(content[:300])
                    para_ids.append(p.get("id", ""))

            if len(para_texts) < 2:
                continue

            context = "\n".join(para_texts)[:3000]
            prompt = f"{self.LOGIC_EXTRACT_PROMPT}\n\n章节: {chapter_path}\n\n段落组:\n{context}"

            try:
                from yuxi.models.chat import select_model
                model = select_model()
                response = await model.call(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                parsed = self._parse_logic_response(text, chapter_path)
                for key in ("causal_chains", "conditions", "data_refs"):
                    if key in parsed:
                        all_results[key].extend(parsed[key])
            except Exception as e:
                logger.debug(f"章节 {chapter_path} 逻辑关系提取失败: {e}")

        return all_results

    def _parse_logic_response(self, text: str, chapter_path: str) -> dict:
        """解析 LLM 返回的逻辑关系 JSON"""
        import json
        import re
        result = {"causal_chains": [], "conditions": [], "data_refs": []}
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if not match:
                return result
            data = json.loads(match.group())

            for item in data.get("causal_chains", []):
                if isinstance(item, dict) and item.get("cause_para_id") and item.get("effect_para_id"):
                    item["chapter"] = chapter_path
                    result["causal_chains"].append(item)

            for item in data.get("conditions", []):
                if isinstance(item, dict) and item.get("expression"):
                    item["chapter"] = chapter_path
                    result["conditions"].append(item)

            for item in data.get("data_refs", []):
                if isinstance(item, dict) and item.get("para_id"):
                    item["chapter"] = chapter_path
                    result["data_refs"].append(item)
        except (json.JSONDecodeError, TypeError):
            pass
        return result

    # ========== 逻辑关系提取 END ==========

    def _extract_table_schemas(self, paragraphs: list[dict]) -> int:
        """对 table 类型段落提取列定义模板（含列角色判定）"""
        import re as _re

        count = 0
        for para in paragraphs:
            if para.get("classify_type") != "table":
                continue
            content = para.get("content", "")
            if not content:
                continue

            schema = None
            if content.strip().startswith("<table"):
                schema = self._extract_html_table_schema(content, para)
            elif self._is_markdown_table(content):
                schema = self._extract_markdown_table_schema(content, para)

            if schema:
                tmpl = para.get("template") or {}
                tmpl["table_schema"] = schema
                para["template"] = tmpl
                count += 1

        return count

    def _is_markdown_table(self, text: str) -> bool:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        table_lines = [l for l in lines if l.startswith("|") and l.endswith("|")]
        return len(table_lines) >= 2

    def _extract_markdown_table_schema(self, content: str, para: dict) -> dict | None:
        """从 Markdown 表格提取 schema"""
        import re as _re

        lines = [l.strip() for l in content.split("\n") if l.strip()]
        separator_pat = _re.compile(r'^\|[:\-]+\|[:\-]*\|$')
        data_lines = [l for l in lines if not separator_pat.match(l)]

        if not data_lines:
            return None

        # 表头
        header_cells = [c.strip() for c in data_lines[0].strip("|").split("|") if c.strip()]
        if not header_cells:
            return None

        # 数据行
        rows = []
        for line in data_lines[1:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            row = {}
            for i, h in enumerate(header_cells):
                row[h] = cells[i] if i < len(cells) else ""
            rows.append(row)

        return self._build_table_schema(header_cells, rows, para)

    def _extract_html_table_schema(self, content: str, para: dict) -> dict | None:
        """从 HTML 表格提取 schema"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")
            table = soup.find("table")
            if not table:
                return None

            # 提取表头
            first_row = table.find("tr")
            if not first_row:
                return None

            headers = []
            for th in first_row.find_all(["th", "td"]):
                headers.append(th.get_text(strip=True))

            if not headers:
                return None

            # 提取数据行
            rows = []
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                row = {}
                for i, h in enumerate(headers):
                    row[h] = cells[i] if i < len(cells) else ""
                if row:
                    rows.append(row)

            return self._build_table_schema(headers, rows, para)
        except ImportError:
            return None

    def _build_table_schema(self, headers: list[str], rows: list[dict], para: dict) -> dict:
        """构建表格 Schema，含列角色判定"""
        import re as _re

        section_path = para.get("section_path", [])
        title = para.get("title", "")

        # 判定表格类型
        table_type = self._classify_table_type(headers, rows, section_path, title)

        # 判定每列角色
        columns = []
        for i, h in enumerate(headers):
            col_values = [row.get(h, "") for row in rows]
            role = self._infer_column_role(h, col_values, table_type, section_path)

            col_def = {"name": h, "role": role}

            # 提取单位
            unit_match = _re.search(r'[\((（](.+?)[\)）]', h)
            if unit_match:
                col_def["unit"] = unit_match.group(1)

            # structural/classification 列附加 vocabulary
            if role in ("structural", "classification") and col_values:
                vocab = list(dict.fromkeys(col_values))
                if vocab:
                    col_def["vocabulary"] = vocab

            columns.append(col_def)

        # 提取 structural_rows（保留非 data/derived 列的行数据）
        non_data_indices = [i for i, c in enumerate(columns) if c["role"] not in ("data", "derived")]
        structural_rows = []
        for row in rows:
            sr = {}
            for i in non_data_indices:
                if i < len(headers):
                    sr[headers[i]] = row.get(headers[i], "")
            if sr:
                structural_rows.append(sr)

        return {
            "name": self._infer_table_name(headers, title),
            "table_type": table_type,
            "columns": columns,
            "structural_rows": structural_rows,
            "total_rows": len(rows),
            "section_path": section_path,
        }

    def _classify_table_type(self, headers: list[str], rows: list[dict],
                              section_path: list, title: str) -> str:
        """判定表格类型"""
        title_lower = title.lower() if title else ""

        # 键值对表格：2列，第一列看起来像属性名
        if len(headers) == 2:
            first_col_values = [row.get(headers[0], "") for row in rows]
            if all(len(v) < 30 for v in first_col_values):
                return "key_value"

        # 达标分析表格：含"标准限值"或"达标"
        header_text = " ".join(headers)
        if "标准限值" in header_text or "达标" in header_text:
            return "compliance"

        # 监测数据表格：含"监测点"或"点位"
        if "监测点" in header_text or "点位" in header_text:
            return "monitoring"

        # 标准限值表格：标题含"限值"
        if "限值" in title_lower:
            return "standard_limit"

        return "general"

    def _infer_column_role(self, col_name: str, col_values: list[str],
                           table_type: str, section_path: list) -> str:
        """推断列角色"""
        name_lower = col_name.lower()

        if table_type == "key_value":
            return "key"

        # 关键词匹配
        reference_kw = ["标准", "规范"]
        derived_kw = ["达标", "占标", "符合", "超标", "标准限值", "评价"]
        data_kw = ["浓度", "速率", "流量", "值", "结果", "含量", "指数", "排放"]
        structural_kw = ["监测点", "点位", "污染源", "污染物", "项目", "名称", "类别", "功能", "因子"]

        for kw in reference_kw:
            if kw in name_lower:
                return "reference"
        for kw in derived_kw:
            if kw in name_lower:
                return "derived"
        for kw in data_kw:
            if kw in name_lower:
                return "data"
        for kw in structural_kw:
            if kw in name_lower:
                return "structural"

        # 兜底：数值占比高 → data
        numeric_count = sum(1 for v in col_values if self._is_numeric_value(v))
        if col_values and numeric_count / len(col_values) > 0.5:
            return "data"
        return "structural"

    def _is_numeric_value(self, v: str) -> bool:
        import re as _re
        if not v or v in ("-", "—", "/", "N/A"):
            return False
        return bool(_re.match(r'^[+-]?[\d.]+$', v.strip()))

    def _infer_table_name(self, headers: list[str], title: str) -> str:
        if title:
            return title
        if headers:
            return f"表格（{headers[0]}...）"
        return "未命名表格"

    # ========== 表格 Schema 提取 END ==========

    # ========== 模板质量评估 ==========

    def evaluate_template_quality(self, generalized: str, slots: list[dict]) -> float:
        """评估模板质量，0~1 分

        新算法基于正向信号 + 轻微惩罚，使评分能真正区分"好提取"和"差提取"：
        - 起点 0.5（中性基线）
        - 正向：slot 有值 +0.15、有实体映射 +0.2、模板含 {{}} 占位符 +0.1
        - 负向：通用名 -0.05、slots 过多 -0.05/个（>8）、"单位"后缀 -0.05、名称过长 -0.05
        """
        import re as _re

        if not slots:
            return 0.0

        score = 0.5
        slot_count = len(slots)

        # ---- 正向信号 ----

        # 已填充值的 slot 占比
        filled = [s for s in slots if s.get("value") or s.get("value") == 0]
        if filled:
            score += 0.15 * (len(filled) / slot_count)

        # 已映射实体的 slot 占比
        entity_mapped = [s for s in slots if s.get("entity_ref")]
        if entity_mapped:
            score += 0.2 * (len(entity_mapped) / slot_count)

        # 泛化模板包含 {{slot}} 占位符
        if generalized and "{{" in generalized:
            score += 0.1

        # ---- 负向信号（轻微惩罚） ----

        # slot 过多
        if slot_count > 8:
            score -= 0.05 * (slot_count - 8)

        generic_names = {"方位", "特征", "区域", "描述", "数值", "名称"}
        for slot in slots:
            name = slot.get("name", "")
            # 通用名
            base = _re.sub(r'\d+$', '', name)
            if base in generic_names:
                score -= 0.05
            # "单位" 后缀
            if name.endswith("单位"):
                score -= 0.05
            # 名称过长
            if len(name) > 8:
                score -= 0.05

        return max(0, min(1, score))

    # ========== 模板质量评估 END ==========

    def _extract_structured_blocks(
        self,
        markdown: str,
        paragraphs: list[dict[str, Any]],
        html_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """从 Markdown 文档和段落列表中提取结构化块（段落和表格）

        参考源系统的逻辑：
        - 解析时将表格转换为 HTML
        - 提取时直接使用 HTML 格式的表格

        Args:
            markdown: Markdown 原文
            paragraphs: 解析后的段落列表
            html_content: HTML 格式的文档内容（表格以 HTML 格式保存）

        返回格式：
        [
            {
                "type": "paragraph",    # 或 "table"
                "id": "p1",
                "content": "...",
                "section_path": ["1", "1.1"],
                "section_title": "1.1 项目背景",
            },
            {
                "type": "table",
                "id": "t1",
                "headers": [...],
                "rows": [...],
                "html_content": "<table>...</table>",  # HTML 格式的表格
                "section_path": ["1", "1.2"],
                "section_title": "1.2 主要指标",
                "caption": "表1-1 主要技术指标",
            },
            ...
        ]
        """
        blocks = []
        block_id = 0
        table_count = 0  # 用于生成表格ID
        html_tables = []  # 初始化 html_tables

        # 如果有 HTML 内容，优先从 HTML 中提取表格
        if html_content:
            html_tables = self._extract_tables_from_html(html_content)
            logger.info(f"从 HTML 中提取到 {len(html_tables)} 个表格")

        # 遍历段落，将连续的 is_table=True 的段落合并为完整的表格块
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i]

            # 跳过标题段落
            if para.get("is_title", False):
                i += 1
                continue

            # 检查是否为表格行
            if para.get("is_table") and para.get("content"):
                # 收集连续的表格行
                table_lines = []
                table_section_path = para.get("section_path", [])
                table_section_title = para.get("section_title", "")

                # 合并连续的表格行
                while i < len(paragraphs):
                    current_para = paragraphs[i]
                    if current_para.get("is_table") and current_para.get("content"):
                        table_lines.append(current_para.get("content", ""))
                        # 更新章节路径（使用最后一个表格行的章节路径）
                        if current_para.get("section_path"):
                            table_section_path = current_para.get("section_path", [])
                        i += 1
                    else:
                        break

                # 解析表格行
                if len(table_lines) >= 2:  # 至少需要表头和数据行
                    headers, rows, caption = self._parse_markdown_table(table_lines)
                    if headers or rows:
                        table_count += 1

                        # 构建表格块
                        block = {
                            "type": "table",
                            "id": f"t{table_count}",
                            "headers": headers,
                            "rows": rows,
                            "caption": caption,
                            "section_path": table_section_path,
                            "section_title": table_section_title,
                            "row_count": len(rows),
                        }

                        # 如果有 HTML 内容，尝试匹配对应的 HTML 表格
                        if html_content and html_tables:
                            # 根据位置或内容匹配 HTML 表格
                            matched_html = self._match_html_table(headers, html_tables)
                            if matched_html:
                                block["html_content"] = matched_html

                        blocks.append(block)
                elif len(table_lines) == 1:
                    # 单行表格作为段落处理
                    block_id += 1
                    blocks.append(
                        {
                            "type": "paragraph",
                            "id": para.get("id", f"p{block_id}"),
                            "content": table_lines[0],
                            "section_path": table_section_path,
                            "section_title": table_section_title,
                        }
                    )
            else:
                # 普通段落
                content = para.get("content", "")
                if content.strip():
                    block_id += 1
                    blocks.append(
                        {
                            "type": "paragraph",
                            "id": para.get("id", f"p{block_id}"),
                            "content": content,
                            "section_path": para.get("section_path", []),
                            "section_title": para.get("section_title", ""),
                        }
                    )
                i += 1

        # 如果 blocks 中没有表格（段落解析时没有提取到表格），直接从 Markdown 中提取
        if not any(b.get("type") == "table" for b in blocks):
            tables = self._split_markdown_tables(markdown)
            for table_lines in tables:
                headers, rows, caption = self._parse_markdown_table(table_lines)
                if headers or rows:
                    table_count += 1
                    block_id += 1
                    blocks.append(
                        {
                            "type": "table",
                            "id": f"t{table_count}",
                            "headers": headers,
                            "rows": rows,
                            "caption": caption,
                            "section_path": [],
                            "section_title": "",
                            "row_count": len(rows),
                        }
                    )

        logger.info(f"结构化块提取完成: {len(blocks)} 个块")
        return blocks

    def _split_markdown_tables(self, markdown: str) -> list[list[str]]:
        """从 Markdown 文本中分割出所有表格（参考源系统逻辑）"""
        tables = []
        current = []

        for line in markdown.splitlines():
            stripped = line.strip()
            # 判断是否为表格行（以 | 开头和结尾）
            if stripped.startswith("|") and stripped.endswith("|"):
                current.append(stripped)
            else:
                # 遇到非表格行，如果当前累积的行数 >= 2，则保存为表格
                if len(current) >= 2:
                    tables.append(current)
                current = []

        # 处理文档末尾的表格
        if len(current) >= 2:
            tables.append(current)

        return tables

    def _extract_tables_from_html(self, html_content: str) -> list[str]:
        """从 HTML 内容中提取所有表格

        Args:
            html_content: HTML 格式的文档内容

        Returns:
            list[str]: HTML 表格列表
        """
        import re

        tables = []
        # 使用正则表达式提取所有 table 元素
        table_pattern = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
        matches = table_pattern.findall(html_content)

        for match in matches:
            # 清理表格，移除不必要的空白
            table = match.strip()
            tables.append(table)

        return tables

    def _match_html_table(
        self,
        headers: list[str],
        html_tables: list[str],
    ) -> str | None:
        """根据表头匹配对应的 HTML 表格

        Args:
            headers: Markdown 表格的表头
            html_tables: HTML 表格列表

        Returns:
            str | None: 匹配的 HTML 表格，如果没有匹配则返回 None
        """

        if not headers or not html_tables:
            return None

        # 尝试匹配第一个 HTML 表格（通常按文档顺序）
        for html_table in html_tables:
            # 检查表头是否匹配
            for header in headers[:3]:  # 只检查前3列
                if header.strip() and header.strip() in html_table:
                    return html_table

        # 如果没有精确匹配，返回第一个表格
        return html_tables[0] if html_tables else None

    def _match_html_table_by_content(
        self,
        markdown_lines: list[str],
        html_tables: list[str],
    ) -> str | None:
        """根据 Markdown 表格行内容匹配对应的 HTML 表格

        Args:
            markdown_lines: Markdown 表格行列表
            html_tables: HTML 表格列表

        Returns:
            str | None: 匹配的 HTML 表格，如果没有匹配则返回 None
        """
        if not markdown_lines or not html_tables:
            return None

        # 提取 Markdown 表格的关键内容用于匹配
        for html_table in html_tables:
            # 检查 Markdown 内容是否在 HTML 表格中
            # 提取 HTML 中的文本内容进行比较
            for md_line in markdown_lines[:5]:  # 检查前5行
                # 移除 | 和空格
                cells = [c.strip() for c in md_line.split("|") if c.strip()]
                for cell in cells:
                    if cell and len(cell) > 1:  # 跳过单个字符
                        if cell in html_table:
                            return html_table

        # 如果没有精确匹配，返回第一个表格
        return html_tables[0] if html_tables else None

    def _parse_markdown_table(self, table_lines: list[str]) -> tuple[list[str], list[list[str]], str]:
        """解析 Markdown 表格行，返回表头、数据行和caption

        Args:
            table_lines: 表格行列表，如 ['| 列1 | 列2 |', '| --- | --- |', '| 值1 | 值2 |']

        Returns:
            (headers, rows, caption): 表头列表、数据行列表、表格标题
        """
        headers = []
        rows = []
        caption = ""

        def _is_separator_row(line: str) -> bool:
            """判断是否为分隔符行 | --- | --- |"""
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                return False
            inner = stripped.strip("|").strip()
            cells = [c.strip() for c in inner.split("|") if c.strip()]
            if not cells:
                return False
            return all(re.match(r"^[:\-]+\.?[:\-]*$", c) or c == "" for c in cells)

        def _parse_cells(line: str) -> list[str]:
            """解析表格行，返回单元格列表（保留空单元格用于列对齐）"""
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                return []
            inner = stripped[1:-1]
            cells = [c.strip() for c in inner.split("|")]
            # 保留空单元格用于列对齐，只过滤首尾空单元格
            # 使用 '' 表示空单元格
            return cells

        try:
            non_separator_lines = [line for line in table_lines if not _is_separator_row(line)]

            if not non_separator_lines:
                return [], [], ""

            # 第一行作为表头
            headers = _parse_cells(non_separator_lines[0])

            # 尝试从表头第一列提取 caption
            if headers:
                first_cell = headers[0]
                caption_match = re.search(r"表[\d\-\.]+[^\s]*", first_cell)
                if caption_match:
                    caption = caption_match.group()
                else:
                    # 尝试从第一列内容中提取
                    caption_match = re.search(r"表[\d\-\.]+[^\s]*", first_cell)
                    if caption_match:
                        caption = caption_match.group()

            # 其余行作为数据行
            for line in non_separator_lines[1:]:
                cells = _parse_cells(line)
                if cells:
                    # 确保列数与表头一致
                    if len(cells) == len(headers):
                        rows.append(cells)
                    elif len(cells) > 0:
                        # 列数不匹配时，补齐或截断
                        normalized_row = cells[: len(headers)] + [""] * (len(headers) - len(cells))
                        rows.append(normalized_row)

        except Exception as e:
            logger.warning(f"解析表格失败: {e}")

        return headers, rows, caption

    def _parse_table_row(self, row_content: str) -> dict:
        """解析表格行，返回表头或单元格"""
        if not row_content:
            return {}

        # 移除首尾的 |
        row_content = row_content.strip().strip("|")
        cells = [cell.strip() for cell in row_content.split("|")]

        # 过滤空单元格
        cells = [c for c in cells if c]

        # 判断是否是表头行（通常是第一行，或者包含分隔符）
        is_header = all(c and not c.startswith("-") for c in cells)

        if is_header:
            return {"type": "header", "headers": cells}
        else:
            return {"type": "row", "row": cells}

    def _build_extract_prompt(
        self, markdown_content: str, variables: list, prompt_template: str | None = None
    ) -> list[dict]:
        """构建 LLM 提取 Prompt，优先使用数据库中配置的模板"""
        variables_desc = []
        for var in variables:
            name = var.get("label", var.get("key", ""))
            prompt = var.get("prompt", "")
            required = var.get("required", False)
            unit = var.get("unit", "")
            desc = f"- {name}: {prompt}"
            if unit:
                desc += f" (单位: {unit})"
            if required:
                desc += " [必填]"
            variables_desc.append(desc)

        variables_text = "\n".join(variables_desc)

        if prompt_template:
            prompt = self._render_prompt(
                prompt_template,
                variables=variables_text,
                content=markdown_content[:8000],
            )
        else:
            prompt = self._render_prompt(
                self._PROMPT_DEFAULTS["extract"],
                variables=variables_text,
                content=markdown_content[:8000],
            )
        return [{"role": "user", "content": prompt}]

    def _parse_llm_json_response(self, response_text: str, variables: list) -> dict:
        """解析 LLM 返回的 JSON 响应"""
        import json
        import re

        # 尝试提取 JSON 部分
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            json_str = json_match.group()
            try:
                data = json.loads(json_str)
                # 验证所有变量 key 都存在
                for var in variables:
                    key = var.get("key", "")
                    if key not in data:
                        data[key] = None
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败: {e}")

        # 兜底：返回空字典
        return {}

    async def _generate_template(self, markdown_content: str, form_data: dict) -> dict:
        """生成槽位模板

        参考源系统的逻辑：
        - 优先从"总论"或"工程概况"章节提取文本进行泛化
        - 使用 LLM 将具体数值替换为 {{插槽名称}} 格式
        - 生成包含 slots、metadata 等完整结构
        """
        from yuxi.models.chat import select_model

        # 提取关键章节用于泛化
        chapters = self._segment_chapters_for_template(markdown_content)

        # 优先选择"工程概况"或"总论"章节
        template_text = (
            chapters.get("工程概况")
            or chapters.get("总论")
            or chapters.get("项目概述")
            or next(iter(chapters.values()), markdown_content[:2000])
        )

        # 如果文本太长，截取前面部分
        if len(template_text) > 2000:
            template_text = template_text[:2000]

        # 构建模板生成 Prompt（参考源系统 prompt_templates.py）
        prompt = """你是一个负责生成环评模板的专家，请将下方段落泛化为模板，使用双层大括号 {插槽名称} 表示可替换变量。

重要：插槽命名必须统一使用中文名称，格式为 {中文名称}，例如：{项目名称}、{行政区域}、{产能数值}、{保护目标名称} 等。

命名示例：
- 项目名称：{项目名称}
- 行政区域：{行政区域}
- 产能数值：{产能数值}
- 保护目标名称：{保护目标名称}
- 判定结论：{判定结论}

需要：
1. 给出泛化后的文本（保持原文逻辑结构不变）；
2. 列出每个插槽的含义及推荐数据来源；
3. 如果段落包含判断逻辑（如"因此"、"所以"、"如果...则"、"当...时"等），提取触发该模板的前提条件；
4. 严格只输出 JSON，不要输出任何自然语言解释或前后缀文本；
5. 严格禁止输出代码块标记（例如 ```json 或 ```）；
6. 插槽名称必须统一使用中文，格式为 {中文名称}。

文本：
"""
        prompt += f"""
\"\"\"
{template_text}
\"\"\"

输出 JSON 结构：
{{
  "generalized": "...包含 {{产能数值}} 等插槽...",
  "slots": [
     {{
       "name": "插槽中文名称",
       "type": "类型",
       "description": "插槽含义描述",
       "data_source": "推荐数据来源"
     }}
  ],
  "metadata": {{
    "chapter": "章节名称",
    "tags": ["标签1", "标签2"]
  }},
  "condition": "IF ... THEN ..."
}}
"""

        try:
            model = select_model()
            response = await model.call(prompt)

            response_text = response.content if hasattr(response, "content") else str(response)

            # 解析 JSON
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                result = json.loads(json_match.group())

                # 规范化响应
                result.setdefault("generalized", template_text[:500] + "...")
                result.setdefault("slots", [])
                result.setdefault("metadata", {"chapter": "", "tags": []})

                logger.info(
                    "模板生成成功: generalized 长度=%d, slots数量=%d",
                    len(result.get("generalized", "")),
                    len(result.get("slots", [])),
                )
                return result
            else:
                logger.warning("模板生成失败：无法解析 JSON 响应")
        except Exception as e:
            logger.warning(f"模板生成失败: {e}")

        # 兜底返回
        return {
            "generalized": template_text[:500] + "..." if len(template_text) > 500 else template_text,
            "slots": [],
            "metadata": {"chapter": "", "tags": []},
        }

    def _segment_chapters_for_template(self, markdown: str) -> dict[str, str]:
        """分割文档为关键章节，用于模板泛化

        识别总论、工程概况、环境现状等关键章节。
        """
        import re

        chapters = {}

        # 章节模式列表
        chapter_patterns = [
            ("总论", re.compile(r"(?:^|\n)(?:#|\d+\.?\.?)\s*总论[\s\S]*?(?=\n#|\n\d+\.)", re.IGNORECASE)),
            ("工程概况", re.compile(r"(?:^|\n)(?:#|\d+\.?\.?)\s*工程概况[\s\S]*?(?=\n#|\n\d+\.)", re.IGNORECASE)),
            ("项目概述", re.compile(r"(?:^|\n)(?:#|\d+\.?\.?)\s*项目概述[\s\S]*?(?=\n#|\n\d+\.)", re.IGNORECASE)),
            ("环境现状", re.compile(r"(?:^|\n)(?:#|\d+\.?\.?)\s*环境现状[\s\S]*?(?=\n#|\n\d+\.)", re.IGNORECASE)),
            ("项目组成", re.compile(r"(?:^|\n)(?:#|\d+\.?\.?)\s*项目组成[\s\S]*?(?=\n#|\n\d+\.)", re.IGNORECASE)),
        ]

        for title, pattern in chapter_patterns:
            match = pattern.search(markdown)
            if match:
                chapters[title] = match.group(0)
                break  # 找到第一个匹配的章节就停止

        return chapters

    # ========== 叙述型段落摘要提取 ==========

    NARRATIVE_SUMMARY_PROMPT = """分析以下段落，提取通用性摘要信息。要求：

1. 提取该段落的核心信息点（1-3个要点）
2. 判断该段落属于哪种叙述类型：conclusion（结论）/ methodology（方法）/ summary（概况）/ background（背景）/ description（描述）
3. 提取段落中提到的关键实体名称（如地名、机构名、项目名等）

严格按 JSON 格式输出：
{{"summary": "一句话摘要（不超过50字）", "key_points": ["要点1", "要点2"], "narrative_type": "类型", "entities": ["实体1", "实体2"]}}"""

    async def _extract_narrative_summaries(
        self,
        paragraphs: list[dict],
        domain_label: str = "",
        max_concurrency: int = 10,
    ) -> dict[str, dict]:
        """对叙述型段落批量提取摘要"""
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrency)

        async def _summarize_one(para: dict) -> tuple[str, dict]:
            async with semaphore:
                pid = para.get("id", "")
                content = para.get("content", "").strip()
                title = para.get("title", "")
                if not content or len(content) < 20:
                    return pid, {"summary": content[:50], "key_points": [], "narrative_type": "description", "entities": []}

                text_input = f"标题：{title}\n内容：{content}" if title else content
                try:
                    result = await self._generalize_text(
                        text_input,
                        chapter_hint=domain_label,
                        prompt=self.NARRATIVE_SUMMARY_PROMPT,
                    )
                    # _generalize_text 返回的是泛化结果，我们需要从中提取 JSON
                    generalized = result.get("generalized", "")
                    summary_data = self._parse_narrative_json(generalized)
                    return pid, {
                        "summary": summary_data.get("summary", content[:50]),
                        "key_points": summary_data.get("key_points", []),
                        "narrative_type": summary_data.get("narrative_type", "description"),
                        "entities": summary_data.get("entities", []),
                        "original": content,
                    }
                except Exception as e:
                    logger.debug(f"叙述摘要提取失败 para={pid}: {e}")
                    return pid, {
                        "summary": content[:50],
                        "key_points": [],
                        "narrative_type": "description",
                        "entities": [],
                        "original": content,
                    }

        tasks = [_summarize_one(p) for p in paragraphs]
        results = await asyncio.gather(*tasks)
        return dict(results)

    @staticmethod
    def _parse_narrative_json(text: str) -> dict:
        """从 LLM 输出中解析叙述摘要 JSON"""
        import json
        import re as _re

        # 尝试直接解析
        text = text.strip()
        if text.startswith("```"):
            text = _re.sub(r'^```\w*\n?', '', text)
            text = _re.sub(r'\n?```$', '', text)
            text = text.strip()

        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试提取 JSON 块
        m = _re.search(r'\{[^{}]*"summary"[^{}]*\}', text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                pass

        return {"summary": text[:50], "key_points": [], "narrative_type": "description", "entities": []}

    async def generalize_paragraphs(
        self,
        paragraphs: list[dict[str, Any]],
        schema_variables: list[dict[str, Any]],
        domain_label: str = "通用",
        max_concurrency: int = 10,
    ) -> dict[str, dict[str, Any]]:
        """对分片后的段落逐一进行模板泛化，参考源系统 pipeline.py 的实现

        设计目标：
        - 以「段落分片」为粒度生成模板，便于前端按章节/分片精确展示
        - 与全局模板互补：全局模板给出整体结构，段落模板给出局部细节
        - 每个段落的泛化结果会回写到段落对象中，包含 original 和 generalized 字段
        - 特别处理表格类型的段落，避免表格数据被切碎

        Args:
            paragraphs: 段落列表，每个元素至少包含 id / content / section_path 等字段
            schema_variables: 领域 Schema 变量列表，用于指导插槽命名
            domain_label: 领域标签，用于提示 LLM 当前文档所属领域
            max_concurrency: 并发调用 LLM 的最大协程数，用于控制成本和速率

        Returns:
            dict[str, dict[str, Any]]: 段落 id -> 模板结果 的映射
        """
        import asyncio

        if not paragraphs:
            return {}

        schema_text = self._format_schema_variables(schema_variables)
        semaphore = asyncio.Semaphore(max_concurrency)
        results: dict[str, dict[str, Any]] = {}

        # 预加载 prompt 模板（一次 DB 查询，避免每个段落都查）
        prompt_templates = await self._load_prompt_templates()
        template_prompt = prompt_templates.get("template")

        async def _run_for_paragraph(idx: int, para: dict[str, Any]) -> None:
            # 获取段落内容
            text = (para.get("content") or "").strip()
            is_table = para.get("is_table", False)
            table_format = para.get("table_format", "markdown")

            # 【关键修复】表格类型段落的处理：
            # 1. 如果是 HTML 格式的表格且内容为空，跳过（HTML 表格由 structured_blocks 处理）
            # 2. 如果是 Markdown 表格，需要检查内容长度
            if is_table and table_format == "html":
                # HTML 表格应该从 structured_blocks 中获取，这里只处理纯文本
                # 如果 HTML 内容太短（如只有 <table></table>），跳过
                if len(text) < 50:
                    logger.debug(f"跳过 HTML 表格段落 {para.get('id')}，内容太短")
                    return
                # HTML 表格不进行文本泛化，直接返回占位结果
                results[str(para.get("id") or f"p{idx + 1}")] = {
                    "generalized": "[HTML表格内容，请参考 structured_blocks 中的完整表格数据]",
                    "slots": [],
                    "metadata": {"chapter": "", "tags": [domain_label]},
                    "is_table": True,
                    "table_format": "html",
                }
                return

            # 普通段落：文本长度至少 20 字符才处理
            if not text or len(text) < 20:
                return

            raw_path = para.get("section_path") or para.get("path") or []
            if isinstance(raw_path, list):
                chapter_hint = ".".join(str(p) for p in raw_path)
            else:
                chapter_hint = str(raw_path) if raw_path else ""

            # 根据段落类型构建不同的 Prompt
            if is_table and table_format == "markdown":
                # Markdown 表格类型的段落
                prompt = self._build_table_generalize_prompt(
                    text,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )
            else:
                # 普通文本段落
                prompt = self._build_text_generalize_prompt(
                    text,
                    schema_text,
                    chapter_hint,
                    domain_label,
                    prompt_template=template_prompt,
                )

            async with semaphore:
                try:
                    resp = await self._generalize_text(text[:1200], chapter_hint, prompt=prompt)
                except Exception as exc:
                    logger.warning(f"段落级泛化失败 para_id={para.get('id')}: {exc}")
                    resp = self._generalize_fallback(text, domain_label)

                para_id = str(para.get("id") or f"p{idx + 1}")
                results[para_id] = resp

        await asyncio.gather(*(_run_for_paragraph(idx, p) for idx, p in enumerate(paragraphs)))
        logger.info(f"段落级泛化完成: 共处理 {len(paragraphs)} 个段落，成功 {len(results)} 个")
        return results

    def _build_text_generalize_prompt(
        self,
        text: str,
        schema_text: str,
        chapter_hint: str,
        domain_label: str,
        prompt_template: str | None = None,
    ) -> str:
        """构建文本段落泛化的 Prompt，优先使用配置的模板"""
        if prompt_template:
            return self._render_prompt(
                prompt_template,
                content=text[:1200],
                schema_text=schema_text,
                chapter_hint=chapter_hint,
                domain_label=domain_label,
            )
        return self._render_prompt(
            self._PROMPT_DEFAULTS["template"],
            content=text[:1200],
            schema_text=schema_text,
            chapter_hint=chapter_hint,
            domain_label=domain_label,
        )

    def _build_table_generalize_prompt(
        self,
        table_text: str,
        schema_text: str,
        chapter_hint: str,
        domain_label: str,
    ) -> str:
        """构建 Markdown 表格泛化的 Prompt（参考源系统 prompt_templates.py）

        表格泛化的特殊处理：
        - 表格内容不需要泛化为模板，直接返回结构化信息
        - 提取表格的列名和数据行信息
        - 表格数据应该从 structured_blocks 中获取，这里只生成表格描述
        """
        return (
            "你是一个负责生成环评模板的专家，请分析下方 Markdown 表格，提取表格的结构化信息。\n\n"
            "注意：Markdown 表格内容不需要泛化为文本模板，而是提取以下信息：\n"
            "1. 表格类型（如敏感目标清单、监测数据、技术指标表等）\n"
            "2. 表格列名（表头）\n"
            "3. 数据行数\n"
            "4. 表格内容的语义描述\n\n"
            "文本：\n"
            f'"""\n{table_text[:1500]}\n"""\n\n'
            f"Schema 变量提示：\n{schema_text}\n\n"
            "输出 JSON 结构：\n"
            "{\n"
            '  "generalized": "[表格: {表格类型}，包含 {列数} 列，{行数} 行数据]",\n'
            '  "slots": [],\n'
            '  "table_type": "{表格类型}",\n'
            '  "headers": ["列1", "列2", ...],\n'
            '  "row_count": {行数},\n'
            '  "metadata": {\n'
            f'    "chapter": "{chapter_hint}",\n'
            f'    "tags": ["{domain_label}", "表格"]\n'
            "  }\n"
            "}"
        )

    async def _generalize_text(self, text: str, chapter_hint: str = "", prompt: str | None = None) -> dict[str, Any]:
        """对单个文本进行泛化处理（参考源系统 pipeline.py）

        Args:
            text: 要泛化的文本
            chapter_hint: 章节提示
            prompt: 可选的预构建 prompt，若提供则直接使用

        Returns:
            dict: 包含 generalized、slots、metadata 等字段的字典
        """
        from yuxi.models.chat import select_model

        if not prompt:
            # 参考源系统 prompt_templates.py 的 Prompt 模板
            prompt = """你是一个负责生成环评模板的专家，\
请将下方段落泛化为模板，使用双层大括号 {插槽名称} 表示可替换变量。

重要：插槽命名必须统一使用中文名称，格式为 {中文名称}。

命名规则说明：
1. 插槽名称必须使用中文，清晰描述实体的含义
2. 命名应简洁明了，避免过长
3. 同类实体使用统一的命名方式

命名示例：
- 项目名称：{项目名称}
- 行政区域：{行政区域}
- 产能数值：{产能数值}
- 产能单位：{产能单位}
- 保护目标名称：{保护目标名称}
- 判定结论：{判定结论}

需要：
1. 给出泛化后的文本（保持原文逻辑结构不变）；
2. 列出每个插槽的含义及推荐数据来源；
3. 如果段落包含判断逻辑（如"因此"、"所以"、"如果...则"、"当...时"等），提取触发该模板的前提条件；
4. 严格只输出 JSON，不要输出任何自然语言解释或前后缀文本；
5. 严格禁止输出代码块标记（例如 ```json 或 ```）；
6. 插槽名称必须统一使用中文，格式为 {中文名称}。

文本：
"""
            prompt += f"""
\"\"\"
{text}
\"\"\"

输出 JSON 结构：
{{
  "generalized": "...包含 {{产能数值}}{{产能单位}} ...",
  "slots": [
     {{
       "name": "产能数值",
       "type": "Capacity",
       "attribute": "Value",
       "description": "产能数值",
       "suggested_source": "推荐的取值方式或数据来源"
     }}
  ],
  "condition": "IF (条件表达式) == True",
  "metadata": {{
    "chapter": "{chapter_hint}",
    "tags": []
  }}
}}

逻辑条件提取说明：
如果段落包含判断逻辑，请提取触发该模板的前提条件。

条件格式：
- 简单条件: "IF (条件表达式) == True"
- 复合条件: "IF (条件1 AND 条件2) == True"
- 空间关系: "IF (区域1 INTERSECT 区域2) == True"
- 数值比较: "IF (距离 < 200) == True"

如果没有明确的逻辑条件，condition 字段可以省略或设为 null。"""

        model = None
        try:
            model = select_model()
            logger.debug(f"泛化调用模型={model.model_name}, prompt长度={len(prompt)}字符")
            response = await model.call(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)

            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                result = json.loads(json_match.group())
                result.setdefault("generalized", text[:500] + "...")
                result.setdefault("slots", [])
                result.setdefault("metadata", {"chapter": chapter_hint, "tags": []})
                return self._normalize_template_response(result)
        except Exception as e:
            model_name = getattr(model, "model_name", "unknown") if model else "unknown"
            logger.warning(f"泛化失败 (模型={model_name}, prompt长度={len(prompt)}): {e}")

        return self._generalize_fallback(text, chapter_hint)

    def _normalize_template_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """规范化模板泛化响应，确保插槽名称符合命名规则（参考源系统 pipeline.py）

        该方法会：
        1. 验证和修正所有插槽的名称
        2. 更新 generalized 文本中的插槽占位符
        3. 确保插槽信息完整（包含 type, attribute 字段）
        4. 统一使用中文插槽名称
        """
        if not response:
            return response

        generalized = response.get("generalized", "")
        slots = response.get("slots", [])

        if not slots:
            return response

        # 规范化每个插槽
        slot_mapping: dict[str, str] = {}  # 旧名称 -> 新名称的映射

        normalized_slots = []
        for slot in slots:
            if not isinstance(slot, dict):
                continue

            old_name = slot.get("name", "")
            if not old_name:
                continue

            # 规范化插槽名称
            new_name = self._normalize_slot_name(old_name, slot)

            # 如果名称发生变化，记录映射
            if new_name != old_name:
                slot_mapping[old_name] = new_name
                logger.debug(f"规范化插槽名称: {old_name} -> {new_name}")

            # 更新插槽信息
            normalized_slot = {
                "name": new_name,
                "description": slot.get("description", ""),
                "suggested_source": slot.get("suggested_source", ""),
            }

            # 如果原响应包含 type 和 attribute，保留它们
            if "type" in slot:
                normalized_slot["type"] = slot["type"]
            if "attribute" in slot:
                normalized_slot["attribute"] = slot["attribute"]
            if "value" in slot:
                normalized_slot["value"] = slot["value"]

            # slot type 兜底校验
            _valid_types = {"parameter", "enum", "descriptive", "reference"}
            st = normalized_slot.get("type", "")
            if st not in _valid_types:
                normalized_slot["type"] = "parameter"
            # enum 类型必须有 vocabulary
            if normalized_slot["type"] == "enum" and not normalized_slot.get("vocabulary"):
                normalized_slot["vocabulary"] = slot.get("vocabulary", [])

            normalized_slots.append(normalized_slot)

        # 更新 generalized 文本中的插槽占位符
        if slot_mapping and generalized:
            for old_name, new_name in slot_mapping.items():
                # 替换 {{old_name}} 为 {{new_name}}（双层大括号）
                generalized = generalized.replace(f"{{{{{old_name}}}}}", f"{{{{{new_name}}}}}")
                # 兼容处理：如果 LLM 返回了单花括号格式，也转换为双层大括号
                generalized = generalized.replace(f"{{{old_name}}}", f"{{{{{new_name}}}}}")

        # 确保所有插槽都使用双层大括号格式
        # 将任何单花括号格式的插槽转换为双层大括号
        if generalized:
            # 匹配单花括号格式的插槽：{SlotName} 或 {中文名称}（排除已经是双层大括号的）
            # 使用负向前瞻确保不匹配已经是双层大括号的情况
            # 支持中文字符、英文字母、数字、下划线的组合
            single_brace_pattern = re.compile(r"(?<!\{)\{([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)\}(?!\})")
            generalized = single_brace_pattern.sub(r"{{\1}}", generalized)

            # 将模板中的英文插槽名称转换为中文
            # 遍历所有规范化后的插槽，如果模板中还有英文名称，替换为中文
            for slot in normalized_slots:
                slot_name = slot.get("name", "")
                if slot_name:
                    # 检查插槽名称是否是英文格式（包含下划线且没有中文字符）
                    if "_" in slot_name and not any("\u4e00" <= char <= "\u9fff" for char in slot_name):
                        # 如果插槽名称是英文格式，转换为中文
                        chinese_name = self._convert_english_slot_to_chinese(slot_name, slot)
                        if chinese_name != slot_name:
                            # 更新插槽名称
                            slot["name"] = chinese_name
                            # 替换模板中的插槽名称（处理带下划线后缀的情况）
                            slot_name_clean = slot_name.rstrip("_")
                            chinese_name_clean = chinese_name.rstrip("_")
                            # 替换标准格式
                            generalized = generalized.replace(
                                f"{{{{{slot_name_clean}}}}}", f"{{{{{chinese_name_clean}}}}}"
                            )
                            generalized = generalized.replace(f"{{{slot_name_clean}}}", f"{{{{{chinese_name_clean}}}}}")
                            # 处理带下划线后缀的情况（如 {{Location_Region}}_）
                            if slot_name.endswith("_"):
                                generalized = generalized.replace(
                                    f"{{{{{slot_name}}}}}", f"{{{{{chinese_name_clean}}}}}"
                                )
                                generalized = generalized.replace(f"{{{slot_name}}}", f"{{{{{chinese_name_clean}}}}}")

            # 再次扫描模板，查找所有英文格式的插槽并转换为中文
            # 匹配双层大括号中的英文插槽名称（包括带下划线后缀的情况）
            english_slot_pattern = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}(_)?")
            matches = english_slot_pattern.findall(generalized)
            for match_tuple in matches:
                match = match_tuple[0] if isinstance(match_tuple, tuple) else match_tuple
                if "_" in match and not any("\u4e00" <= char <= "\u9fff" for char in match):
                    # 尝试转换为中文
                    chinese_name = self._convert_english_slot_to_chinese(match, None)
                    if chinese_name != match:
                        # 替换模板中的插槽
                        generalized = generalized.replace(f"{{{{{match}}}}}", f"{{{{{chinese_name}}}}}")
                        # 处理带下划线后缀的情况（如 {{Location_Region}}_）
                        if match.endswith("_"):
                            generalized = generalized.replace(f"{{{{{match}}}}}", f"{{{{{chinese_name}}}}}")

        # 更新响应
        response["generalized"] = generalized
        response["slots"] = normalized_slots

        return response

    def _normalize_slot_name(self, slot_name: str, slot_info: dict | None = None) -> str:
        """规范化插槽名称，统一使用中文（参考源系统 pipeline.py）

        命名规则：
        - 统一使用中文名称，格式为：{{中文名称}}
        - 如果输入是英文或下划线分隔的格式，转换为对应的中文名称
        - 如果已经是中文，直接返回
        """
        if not slot_name:
            return "未知值"

        # 移除可能的空格和特殊字符，去除末尾的下划线
        slot_name = slot_name.strip().rstrip("_")

        # 如果已经是中文名称（包含中文字符），直接返回
        if any("\u4e00" <= char <= "\u9fff" for char in slot_name):
            # 如果包含下划线，检查是否是混合格式（中英文混合）
            if "_" in slot_name:
                # 检查是否包含英文部分
                parts = slot_name.split("_")
                has_english = any(part and not any("\u4e00" <= char <= "\u9fff" for char in part) for part in parts)
                if has_english:
                    # 如果是混合格式，尝试转换
                    return self._convert_english_slot_to_chinese(slot_name, slot_info)
            # 纯中文，直接返回
            return slot_name

        # 如果是英文或下划线分隔的格式，转换为中文
        return self._convert_english_slot_to_chinese(slot_name, slot_info)

    def _convert_english_slot_to_chinese(self, slot_name: str, slot_info: dict | None = None) -> str:
        """将英文插槽名称转换为中文名称（参考源系统 pipeline.py）

        Args:
            slot_name: 英文插槽名称（可能包含下划线）
            slot_info: 插槽信息字典

        Returns:
            str: 中文插槽名称
        """
        # 英文到中文的映射表（扩展版）
        english_to_chinese = {
            # 项目相关
            "ProjectName": "项目名称",
            "ProjectName_Name": "项目名称",
            "Project_Name": "项目名称",
            "ProjectNameName": "项目名称",
            # 位置相关
            "Location": "位置",
            "Location_Region": "行政区域",
            "LocationRegion": "行政区域",
            "Location_Name": "位置名称",
            "LocationName": "位置名称",
            "Location_Area": "位置区域",
            # 产能相关
            "Capacity": "产能",
            "Capacity_Value": "产能数值",
            "CapacityValue": "产能数值",
            "Capacity_Unit": "产能单位",
            "CapacityUnit": "产能单位",
            # 距离相关
            "Distance": "距离",
            "Distance_Value": "距离数值",
            "DistanceValue": "距离数值",
            "Distance_Unit": "距离单位",
            "DistanceUnit": "距离单位",
            "Distance_To_Protected_Area": "距离保护目标",
            "DistanceToProtectedArea": "距离保护目标",
            # 保护目标相关
            "TargetName": "保护目标名称",
            "Protected_Area_Name": "保护目标名称",
            "ProtectedAreaName": "保护目标名称",
            "Target_Name": "保护目标名称",
            "TargetNameName": "保护目标名称",
            # 面积相关
            "Area": "面积",
            "Area_Value": "面积数值",
            "AreaValue": "面积数值",
            "Area_Unit": "面积单位",
            "AreaUnit": "面积单位",
            # 时间相关
            "Time": "时间",
            "Time_Value": "时间数值",
            "TimeValue": "时间数值",
            "Time_Unit": "时间单位",
            "TimeUnit": "时间单位",
            # 判定相关
            "Judgment": "判定",
            "Judgment_Conclusion": "判定结论",
            "JudgmentConclusion": "判定结论",
            "Judgment_Result": "判定结果",
            "JudgmentResult": "判定结果",
            # 沉陷相关
            "Subsidence_Influence_Radius": "沉陷影响半径",
            "SubsidenceInfluenceRadius": "沉陷影响半径",
            # 相对方向
            "Relative_Direction": "相对方向",
            "RelativeDirection": "相对方向",
            # 其他常见插槽
            "Value": "数值",
            "Unit": "单位",
            "Name": "名称",
            "Type": "类型",
            "Region": "区域",
            "Conclusion": "结论",
        }

        # 先尝试直接匹配
        if slot_name in english_to_chinese:
            return english_to_chinese[slot_name]

        # 如果包含下划线，尝试分段匹配
        if "_" in slot_name:
            parts = slot_name.split("_")
            # 尝试组合匹配
            if len(parts) >= 2:
                # 尝试匹配完整名称
                full_name = "_".join(parts)
                if full_name in english_to_chinese:
                    return english_to_chinese[full_name]

                # 尝试匹配各个部分
                chinese_parts = []
                for part in parts:
                    if part in english_to_chinese:
                        chinese_parts.append(english_to_chinese[part])
                    else:
                        # 如果无法匹配，尝试从描述中推断
                        if slot_info and slot_info.get("description"):
                            # 使用描述作为中文名称
                            desc = slot_info.get("description", "")
                            if desc:
                                return desc
                        chinese_parts.append(part)

                if chinese_parts:
                    # 组合中文部分，去除重复
                    result = "".join(chinese_parts)
                    return result if result else slot_name

        # 如果无法转换，尝试从描述中获取
        if slot_info:
            description = slot_info.get("description", "")
            if description:
                return description

        # 如果仍然无法转换，返回原名称（可能是中文或特殊格式）
        return slot_name

    def _format_schema_variables(self, variables: list[dict[str, Any]]) -> str:
        """格式化实体变量为提示词文本"""
        lines = []
        for item in variables:
            key = item.get("key", "").strip()
            dtype = item.get("data_type", "")
            label = item.get("label", "") or key
            prompt = item.get("prompt", "")
            lines.append(f"- {key} ({dtype}): {label}；提取提示：{prompt}")
        return "\n".join(lines) if lines else "无特定 Schema 变量，请根据文本内容自动识别"

    def _generalize_fallback(self, text: str, domain_label: str = "") -> dict[str, Any]:
        """泛化失败时的回退方法"""
        return {
            "original": text,
            "generalized": re.sub(r"\d+(?:\.\d+)?", "{{数值}}", text, count=1),
            "slots": [
                {"name": "数值", "type": "NumericValue", "description": "自动抽取数值", "suggested_source": "文本推断"}
            ],
            "metadata": {"chapter": "", "tags": [domain_label] if domain_label else []},
        }

    async def get_task_detail(self, task_id: str) -> dict[str, Any] | None:
        task = await self.repo.get_task_with_domain(task_id)
        if not task:
            return None

        domain = await self.repo.get_domain_by_id(task.domain_id)
        domain_code = domain.code if domain else None
        variables = await self._get_extraction_variables(domain_code)

        return {
            "id": task.id,
            "file_name": task.file_name,
            "storage_path": task.storage_path,
            "domain": domain.code if domain else None,
            "domain_label": domain.name if domain else None,
            "document_type": task.document_type or "",
            "report_type_code": task.report_type_code or "",
            "status": task.status,
            "ai_confidence": task.ai_confidence,
            "uploaded_at": utc_isoformat(task.created_at),
            "uploaded_by": task.uploaded_by,
            "reviewer": task.reviewer,
            "committed_at": utc_isoformat(task.committed_at),
            "error_message": task.error_message,
            "form_schema": _build_form_schema(variables, task.form_schema_snapshot),
            "base_info": task.base_info or {},
            "structured_blocks": task.structured_blocks or [],
            "template": task.template_payload or {},
            "template_metadata": task.template_metadata,
            "source_paragraphs": task.source_paragraphs or [],
            "raw_markdown": task.raw_markdown,
            "raw_html": getattr(task, "raw_html", None),
            "ingest_task_id": task.ingest_task_id,
            "knowledge_base_id": task.knowledge_base_id,
        }

    async def list_pending_tasks(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        domain_id = None
        if domain_code:
            domain = await self.repo.get_domain_by_code(domain_code)
            if domain:
                domain_id = domain.id
        tasks = await self.repo.list_pending_tasks(domain_id)
        return tasks

    async def list_history_tasks(self, domain_code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        domain_id = None
        if domain_code:
            domain = await self.repo.get_domain_by_code(domain_code)
            if domain:
                domain_id = domain.id
        tasks = await self.repo.list_history_tasks(domain_id, limit)
        return tasks

    async def update_task_form_data(self, task_id: str, form_data: dict[str, Any]) -> dict[str, Any] | None:
        task = await self.repo.get_task_with_domain(task_id)
        if not task:
            return None

        base_info = dict(task.base_info or {})
        base_info.update(form_data)

        update_data = {"base_info": base_info}
        if task.status == "UPLOADED":
            update_data["status"] = "EXTRACTING"

        updated_task = await self.repo.update_task(task_id, update_data)
        return updated_task.to_summary_dict() if updated_task else None

    async def save_task_step(self, task_id: str, step_data: dict[str, Any]) -> dict[str, Any] | None:
        task = await self.repo.get_task_with_domain(task_id)
        if not task:
            return None

        update_fields = {}

        # 处理分步骤数据
        step = step_data.get("step")
        payload = step_data.get("payload", step_data)

        if step == "basic":
            # 基础信息
            if "payload" in step_data:
                update_fields["base_info"] = step_data["payload"]
            else:
                update_fields.update(step_data)
        elif step == "structured":
            # 结构化数据
            structured_blocks = payload.get("structured_blocks") if isinstance(payload, dict) else None
            source_paragraphs = payload.get("source_paragraphs") if isinstance(payload, dict) else None
            if structured_blocks is not None:
                update_fields["structured_blocks"] = structured_blocks
            if source_paragraphs is not None:
                update_fields["source_paragraphs"] = source_paragraphs
        elif step == "template":
            # 模板数据
            template = payload if isinstance(payload, dict) else {"template": payload}
            update_fields["template_payload"] = template.get("template")
            update_fields["template_metadata"] = template.get("metadata", template.get("template_metadata"))
        else:
            # 通用更新
            for field_name in [
                "base_info",
                "structured_blocks",
                "template_payload",
                "form_schema_snapshot",
                "source_paragraphs",
                "raw_markdown",
                "template_metadata",
                "ai_confidence",
                "status",
                "error_message",
            ]:
                if field_name in step_data:
                    update_fields[field_name] = step_data[field_name]

        if "confidence" in step_data:
            update_fields["ai_confidence"] = step_data["confidence"]

        updated_task = await self.repo.update_task(task_id, update_fields)
        return updated_task.to_summary_dict() if updated_task else None

    async def commit_task(
        self, task_id: str, reviewer: str | None = None, knowledge_base_id: str | None = None
    ) -> dict[str, Any] | None:
        task = await self.repo.get_task_with_domain(task_id)
        if not task:
            return None

        # 生成入库任务ID
        ingest_task_id = f"ingest_{task_id}_{uuid.uuid4().hex[:8]}"

        # 注册入库流水线到任务中心，异步执行
        try:
            from yuxi.services.task_service import tasker as global_tasker

            await global_tasker.enqueue(
                name=f"知识工厂入库: {task.file_name}",
                task_type="domain_factory_ingest",
                payload={
                    "task_id": task_id,
                    "domain_factory_task_id": task_id,
                    "knowledge_base_id": knowledge_base_id,
                    "file_name": task.file_name,
                    "reviewer": reviewer,
                    "ingest_task_id": ingest_task_id,
                },
                coroutine=self._commit_pipeline_async,
            )
            logger.info(f"已注册入库任务到任务中心: {task_id}")
        except Exception as e:
            logger.warning(f"注册入库任务失败: {e}")

        result = task.to_summary_dict() if task else None
        if result:
            result["ingest_task_id"] = ingest_task_id
        return result

    async def _upload_original_to_minio(
        self, kb_id: str, file_id: str, storage_path: str, file_name: str
    ) -> tuple[str, int]:
        """上传原文件到 MinIO(documents 桶),供 KB 预览/下载。返回 (url, size_bytes);失败返回 ("", 0)。"""
        try:
            from yuxi.storage.minio import get_minio_client
            from yuxi.storage.minio.client import aupload_file_to_minio

            p = Path(storage_path)
            if not storage_path or not p.exists():
                return "", 0
            data = await asyncio.to_thread(p.read_bytes)
            minio_client = get_minio_client()
            bucket = minio_client.KB_BUCKETS["documents"]
            await asyncio.to_thread(minio_client.ensure_bucket_exists, bucket)
            ext = Path(file_name).suffix.lower() or ".bin"
            object_name = f"{kb_id}/upload/{file_id}{ext}"
            url = await aupload_file_to_minio(bucket, object_name, data)
            return url, len(data)
        except Exception as e:
            logger.warning(f"原文件上传 MinIO 失败(不阻断入库): {e}")
            return "", 0

    def _normalize_domain_for_graph(self, domain: str) -> str:
        """ETL 入图谱前归一化 domain(中文名→code)。"""
        from yuxi.repositories.domain_factory_repository import _normalize_domain

        return _normalize_domain(domain or "") or (domain or "")

    def _normalize_report_type_for_graph(self, report_type: str) -> str:
        """ETL 入图谱前归一化 report_type('通用'→'eia_report')。"""
        from yuxi.repositories.domain_factory_repository import _normalize_report_type

        normalized = _normalize_report_type(report_type or "")
        return normalized if normalized else (report_type or "")

    def _dedup_templates_by_hash(self, templates: list[dict]) -> list[dict]:
        """按 text_pattern 去重, source_count 累加。"""
        seen: dict[str, dict] = {}
        for t in templates:
            pattern = t.get("text_pattern", "")
            if pattern in seen:
                seen[pattern]["source_count"] = seen[pattern].get("source_count", 1) + 1
            else:
                t["source_count"] = 1
                seen[pattern] = t
        return list(seen.values())

    async def _merge_cross_report_knowledge(self, task_detail: dict) -> dict:
        """合并当前报告知识到标准13章(聚合 key_points/regulations + 提取大纲模板 content_contract)。"""
        import json

        from yuxi.services.graph_builder import GraphBuilder

        domain = self._normalize_domain_for_graph(task_detail.get("domain") or "coal")
        report_type = self._normalize_report_type_for_graph(task_detail.get("report_type_code") or "eia_report")
        builder = GraphBuilder()
        merged_count = 0
        try:
            driver = builder._get_driver()
            if driver is None:
                return {"status": "skipped", "reason": "no graph driver"}
            with driver.session() as session:
                for order in range(1, 14):
                    std_id = f"CH_{domain}_{report_type}_std_{order}"

                    # 1. 聚合 key_points
                    result = session.run(
                        """
                        MATCH (std:ChapterTemplate {id: $std_id})
                        OPTIONAL MATCH (std)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
                        WHERE sub.key_points IS NOT NULL
                        WITH std, collect(DISTINCT sub.key_points) AS all_kp,
                             collect(DISTINCT sub.regulations) AS all_reg
                        RETURN all_kp, all_reg
                        """,
                        std_id=std_id,
                    )
                    rec = result.single()
                    if rec is None:
                        continue
                    all_kp = rec["all_kp"] or []
                    all_reg = rec["all_reg"] or []
                    if all_kp:
                        kp_set: list[str] = []
                        seen_kp: set[str] = set()
                        for kp_json in all_kp:
                            try:
                                items = json.loads(kp_json) if isinstance(kp_json, str) else kp_json
                                if isinstance(items, list):
                                    for item in items:
                                        if isinstance(item, str) and item not in seen_kp:
                                            seen_kp.add(item)
                                            kp_set.append(item)
                            except (json.JSONDecodeError, TypeError):
                                continue
                        if kp_set:
                            session.run(
                                "MATCH (std:ChapterTemplate {id: $id}) SET std.key_points = $kp",
                                id=std_id, kp=json.dumps(kp_set, ensure_ascii=False),
                            )
                            merged_count += 1

                    # 2. 提取大纲模板: 按报告分组收集子章节, 计算共通/差异
                    template_result = session.run(
                        """
                        MATCH (std:ChapterTemplate {id: $std_id})
                        OPTIONAL MATCH (std)-[:HAS_CHILD]->(etl:ChapterTemplate)
                        WHERE NOT etl.id STARTS WITH 'CH_coal_eia_report_std_'
                          AND etl.canonical_chapter_key IS NOT NULL
                          AND etl.canonical_chapter_key <> ''
                        OPTIONAL MATCH (doc:Document)-[:CONTRIBUTES_TO]->()
                        WITH std, collect(DISTINCT etl.canonical_chapter_key) AS all_sub_keys
                        RETURN all_sub_keys
                        """,
                        std_id=std_id,
                    )
                    trec = template_result.single()
                    if trec is None:
                        continue
                    sub_keys = [k for k in (trec["all_sub_keys"] or []) if k]
                    if not sub_keys:
                        continue

                    # 统计每个子章节在多少份报告中出现
                    count_result = session.run(
                        """
                        MATCH (std:ChapterTemplate {id: $std_id})-[:HAS_CHILD]->(etl:ChapterTemplate)
                        WHERE etl.canonical_chapter_key IS NOT NULL AND etl.canonical_chapter_key <> ''
                        WITH std, etl.canonical_chapter_key AS key, count(DISTINCT etl) AS cnt
                        RETURN key, cnt ORDER BY key
                        """,
                        std_id=std_id,
                    )
                    key_counts = {r["key"]: r["cnt"] for r in count_result}
                    total_docs = session.run(
                        "MATCH (d:Document) WHERE d.domain_code = $d AND d.report_type_code = $rt RETURN count(DISTINCT d) AS cnt",
                        d=domain, rt=report_type,
                    ).single()
                    doc_count = total_docs["cnt"] if total_docs else 1

                    required = [k for k, c in key_counts.items() if c >= doc_count]
                    optional = [k for k, c in key_counts.items() if c < doc_count]

                    content_contract = {
                        "required_elements": sorted(required),
                        "optional_elements": sorted(optional),
                        "sub_chapter_counts": key_counts,
                        "total_reports": doc_count,
                    }
                    session.run(
                        "MATCH (std:ChapterTemplate {id: $id}) SET std.content_contract = $cc",
                        id=std_id,
                        cc=json.dumps(content_contract, ensure_ascii=False),
                    )
                    merged_count += 1
            return {"status": "ok", "chapters_merged": merged_count}
        finally:
            builder.close()

    async def _commit_pipeline_async(self, context) -> dict[str, Any]:
        """入库流水线异步执行（由任务中心调度）

        流水线阶段：
        1. 准备 (PREPARING): 更新任务状态为 COMMITTED
        2. 同步 (SYNCING): 将结构化数据通过去噪+上下文重组写入知识库
        3. 完成 (COMPLETING): 完成入库

        入库策略：优先使用结构化入库（保留章节元数据、去噪、上下文重组），
        若知识库实例不支持 _ingest_structured_document 则回退到 Markdown 方案。
        """
        from yuxi.services.domain_factory_service import get_domain_factory_service

        task_id = None
        reviewer = None
        knowledge_base_id = None
        ingest_task_id = None

        try:
            if hasattr(context, "_tasker") and hasattr(context, "task_id"):
                tasker_task = context._tasker._tasks.get(context.task_id)
                if tasker_task and tasker_task.payload:
                    task_id = tasker_task.payload.get("task_id")
                    reviewer = tasker_task.payload.get("reviewer")
                    knowledge_base_id = tasker_task.payload.get("knowledge_base_id")
                    ingest_task_id = tasker_task.payload.get("ingest_task_id")
        except Exception as e:
            logger.warning(f"获取入库任务参数失败: {e}")

        if not task_id:
            return {"error": "task_id not found"}

        service = get_domain_factory_service()

        # ========== 提交前校验关卡 ==========
        await context.set_progress(2.0, "正在校验数据...")
        await context.set_message("正在校验数据...")
        from yuxi.services.pre_commit_validator import PreCommitValidator

        task_detail = await service.get_task_detail(task_id)
        validator = PreCommitValidator()
        validation = await validator.validate(task_detail)
        if not validation.passed:
            await service.repo.update_task(
                task_id,
                {"status": "COMMIT_FAILED", "error_message": "; ".join(validation.errors)},
            )
            await context.set_progress(100.0, "校验失败,已中止入库")
            await context.set_message("校验失败: " + "; ".join(validation.errors))
            return {
                "task_id": task_id,
                "status": "COMMIT_FAILED",
                "errors": validation.errors,
                "message": "提交前校验失败",
            }

        try:
            # ========== 阶段1: 准备 (PREPARING) ==========
            await context.set_progress(5.0, "正在准备入库...")
            await context.set_message("正在准备入库...")

            # 更新任务状态为 COMMITTED
            await service.repo.commit_task(task_id, reviewer, ingest_task_id=ingest_task_id)

            # ========== 阶段2: 同步到知识库 (SYNCING) ==========
            await context.set_progress(30.0, "正在同步数据到知识库...")
            await context.set_message("正在同步数据到知识库...")

            # task_detail 已在提交前校验阶段获取（复用）

            kb_ingested = False
            if knowledge_base_id:
                try:
                    from yuxi.knowledge import knowledge_base as kb_manager
                    from yuxi.knowledge.base import FileStatus

                    await context.set_progress(40.0, "正在组装入库内容...")
                    await context.set_message("正在组装入库内容...")

                    kb_instance = await kb_manager.aget_kb(knowledge_base_id)
                    if not kb_instance:
                        raise ValueError(f"知识库 {knowledge_base_id} 不存在")

                    file_name = task_detail.get("file_name", f"domain_factory_{task_id}.md")
                    file_id = f"df_{hashstr(task_id + str(uuid.uuid4()), 8)}"

                    # 同时生成 Markdown（用于 MinIO 存档）和结构化文档（用于向量化）
                    ingest_markdown = self._build_ingest_markdown(task_detail)

                    # 1. 保存 Markdown 到 MinIO（供知识库文件列表展示）
                    markdown_url = ""
                    if hasattr(kb_instance, "_save_markdown_to_minio"):
                        markdown_url = await kb_instance._save_markdown_to_minio(
                            knowledge_base_id, file_id, ingest_markdown
                        )

                    # 上传原文件到 MinIO(供预览/下载,path 指向原文件而非 markdown)
                    original_url, original_size = await service._upload_original_to_minio(
                        knowledge_base_id, file_id, task_detail.get("storage_path", ""), file_name
                    )

                    # 2. 创建文件记录，直接设为 PARSED 状态（写入知识库文件表，供 index_file 消费）
                    file_meta = {
                        "file_id": file_id,
                        "kb_id": knowledge_base_id,
                        "filename": file_name,
                        "original_filename": file_name,
                        "file_type": Path(file_name).suffix.lower().lstrip(".") or "bin",
                        "path": original_url or markdown_url,
                        "markdown_file": markdown_url,
                        "status": FileStatus.PARSED,
                        "content_hash": hashstr(ingest_markdown),
                        "size": original_size or len(ingest_markdown),
                        "content_type": "domain_factory",
                        "processing_params": {},
                        "is_folder": False,
                        "created_by": reviewer,
                    }
                    await kb_instance._persist_file_meta(file_id, file_meta)

                    await context.set_progress(50.0, "正在写入知识库...")
                    await context.set_message("正在写入知识库...")

                    # 3. 优先使用结构化入库（去噪 + 上下文重组）
                    if hasattr(kb_instance, "_ingest_structured_document"):
                        structured_doc = self._build_structured_document(task_detail, file_id, file_name)
                        rag = await kb_instance._get_lightrag_instance(knowledge_base_id)
                        if rag:
                            await kb_instance._ingest_structured_document(
                                rag=rag,
                                db_id=knowledge_base_id,
                                file_id=file_id,
                                file_path=f"domain_factory/{task_id}/{file_name}",
                                structured_doc=structured_doc,
                            )
                            # 更新文件状态为 INDEXED
                            kb_instance.files_meta[file_id]["status"] = FileStatus.INDEXED
                            kb_instance.files_meta[file_id]["updated_at"] = utc_isoformat()
                            if reviewer:
                                kb_instance.files_meta[file_id]["updated_by"] = reviewer
                            await kb_instance._persist_file(file_id)
                            logger.info(
                                f"结构化入库完成: {task_id} -> {knowledge_base_id}, "
                                f"file_id={file_id}, chunks={len(structured_doc.chunks)}"
                            )
                            kb_ingested = True
                        else:
                            raise ValueError(f"获取 LightRAG 实例失败: {knowledge_base_id}")
                    else:
                        # 回退到标准 Markdown 入库
                        logger.info("知识库实例不支持结构化入库，回退到 Markdown 方案")
                        await kb_manager.index_file(knowledge_base_id, file_id, operator_id=reviewer)
                        logger.info(f"Markdown 入库完成: {task_id} -> {knowledge_base_id}, file_id={file_id}")
                        kb_ingested = True

                except Exception as e:
                    logger.error(f"入库知识库失败: {e}")
                    await service.repo.update_task(
                        task_id,
                        {
                            "status": "FAILED",
                            "error_message": f"知识库入库失败: {e}",
                        },
                    )
                    await context.set_progress(100.0, f"入库失败: {e}")
                    await context.set_message(f"入库失败: {e}")
                    return {"error": f"知识库入库失败: {e}"}

            # ========== 阶段2.4b: slot 事后校验 (新增) ==========
            try:
                from yuxi.services.slot_validation_service import SlotValidationService

                svc = SlotValidationService()
                paragraph_slots = [
                    {
                        "paragraph_id": p.get("id", ""),
                        "slots": (p.get("template") or {}).get("slots", []),
                    }
                    for p in task_detail.get("source_paragraphs", [])
                    if p.get("type") == "parameter" and isinstance(p.get("template"), dict)
                ]
                if paragraph_slots:
                    val_report = await svc.validate_slots(paragraph_slots, {})
                    if val_report.get("conflicts"):
                        logger.warning(f"slot 校验发现 {len(val_report['conflicts'])} 个冲突: {val_report['conflicts']}")
                    if val_report.get("warnings"):
                        logger.warning(f"slot 校验 {val_report['warnings']} 个警告")
            except Exception as e:
                logger.warning(f"slot 校验失败(不阻断入库): {e}")

            # ========== 阶段2.5: 构建知识图谱 ==========
            await context.set_progress(80.0, "正在构建知识图谱...")
            await context.set_message("正在构建知识图谱...")

            try:
                from yuxi.services.graph_builder import GraphBuilder

                graph_builder = GraphBuilder()
                doc_id = f"doc_{task_id}"
                source_paragraphs = task_detail.get("source_paragraphs", [])
                domain_label = task_detail.get("domain_label", "")
                base_info = task_detail.get("base_info", {})

                # 将逻辑关系注入段落的 template 中，供图谱构建使用
                logical_relations = task_detail.get("logical_relations", {})
                if isinstance(logical_relations, dict) and any(isinstance(v, list) and v for v in logical_relations.values()):
                    for para in source_paragraphs:
                        tmpl = para.get("template") or {}
                        if isinstance(tmpl, dict):
                            tmpl["logical_refs"] = logical_relations
                            para["template"] = tmpl

                if source_paragraphs:
                    graph_stats = graph_builder.build_knowledge_graph(
                        kb_id=knowledge_base_id or "",
                        doc_id=doc_id,
                        doc_title=task_detail.get("file_name", ""),
                        source_paragraphs=source_paragraphs,
                        domain_label=domain_label,
                        base_info=base_info,
                        domain_code=self._normalize_domain_for_graph(task_detail.get("domain") or ""),
                        report_type_code=self._normalize_report_type_for_graph(task_detail.get("report_type_code") or ""),
                    )
                    logger.info(f"知识图谱构建完成: {graph_stats}")
                    graph_builder.close()
                else:
                    logger.warning(f"任务 {task_id} 无 source_paragraphs，跳过图谱构建")
            except Exception as e:
                logger.exception(f"知识图谱构建失败,任务标记 COMMIT_FAILED: {task_id}")
                await service.repo.update_task(
                    task_id,
                    {"status": "COMMIT_FAILED", "error_message": f"图谱构建失败: {e}"},
                )
                await context.set_progress(100.0, f"图谱构建失败: {e}")
                await context.set_message(f"图谱构建失败: {e}")
                return {
                    "task_id": task_id,
                    "status": "COMMIT_FAILED",
                    "error": f"图谱构建失败: {e}",
                    "message": "图谱构建失败",
                }

            # ========== 阶段2.8: 模板回流 (LEARNED TEMPLATES) ==========
            pipeline_status = "COMMITTED"
            partial_errors: list[str] = []
            try:
                await context.set_progress(90.0, "正在回写学习模板...")
                await context.set_message("正在回写学习模板...")
                learned_count = await service._save_learned_templates_from_task(task_detail)
                logger.info(f"模板回流: {learned_count} 个段落模板已保存")
            except Exception as e:
                logger.warning(f"模板回流失败(标记PARTIAL): {e}")
                pipeline_status = "COMMIT_PARTIAL"
                partial_errors.append(f"模板回流失败: {e}")

            # ========== 阶段2.9: 章节大纲产出 (OUTLINE) ==========
            try:
                await context.set_progress(92.0, "正在产出章节大纲...")
                await context.set_message("正在产出章节大纲...")
                outline_count = await service._produce_outlines_async(
                    task_id,
                    service._normalize_domain_for_graph(task_detail.get("domain") or "coal"),
                    service._normalize_report_type_for_graph(task_detail.get("report_type_code") or "eia_report"),
                )
                logger.info(f"章节大纲产出完成: {outline_count} 章")
            except Exception as e:
                logger.warning(f"章节大纲产出失败(标记PARTIAL): {e}")
                pipeline_status = "COMMIT_PARTIAL"
                partial_errors.append(f"大纲产出失败: {e}")

            if not knowledge_base_id:
                logger.warning(f"任务 {task_id} 未指定目标知识库，跳过入库")

            # ========== 阶段2.10: 跨报告知识合并 (MERGE) ==========
            try:
                await context.set_progress(94.0, "正在合并跨报告知识...")
                await context.set_message("正在合并跨报告知识...")
                merged = await service._merge_cross_report_knowledge(task_detail)
                logger.info(f"跨报告合并完成: {merged}")
            except Exception as e:
                logger.warning(f"跨报告合并失败(不阻断入库): {e}")
                pipeline_status = "COMMIT_PARTIAL"
                partial_errors.append(f"跨报告合并失败: {e}")

            # ========== 阶段3: 完成 (COMPLETING) ==========
            await context.set_progress(95.0, "正在完成入库...")
            await context.set_message("正在完成入库...")

            # 更新最终状态
            await service.repo.update_task(
                task_id,
                {
                    "status": pipeline_status,
                    "knowledge_base_id": knowledge_base_id,
                    **({"error_message": "; ".join(partial_errors)} if partial_errors else {}),
                },
            )

            await context.set_progress(100.0, "入库完成" if pipeline_status == "COMMITTED" else "部分入库完成")
            await context.set_message("入库完成" if pipeline_status == "COMMITTED" else "部分入库完成")

            return {
                "task_id": task_id,
                "status": pipeline_status,
                "knowledge_base_id": knowledge_base_id,
                "kb_ingested": kb_ingested,
                "partial_errors": partial_errors,
                "message": "入库流水线执行完成",
            }

        except Exception as e:
            logger.exception(f"入库流水线执行失败: {task_id}")
            await service.repo.update_task(task_id, {"status": "FAILED", "error_message": str(e)})
            await context.set_progress(100.0, f"入库失败: {str(e)}")
            await context.set_message(f"入库失败: {str(e)}")
            return {"error": str(e)}

    def _build_ingest_markdown(self, task_detail: dict[str, Any]) -> str:
        """将领域工厂的结构化数据组装为知识库可索引的 Markdown

        包含：基础信息表、段落内容（含泛化模板）、结构化表格数据。
        """
        parts: list[str] = []

        file_name = task_detail.get("file_name", "未知文档")
        domain_label = task_detail.get("domain_label", "")
        document_type = task_detail.get("document_type", "")

        # 文档头
        parts.append(f"# {file_name}")
        if domain_label:
            parts.append(f"\n**领域**：{domain_label}")
        if document_type:
            parts.append(f"**文档类型**：{document_type}")

        # 基础信息
        base_info = task_detail.get("base_info", {})
        if base_info:
            parts.append("\n## 基础信息\n")
            parts.append("| 字段 | 值 |")
            parts.append("| --- | --- |")
            for key, value in base_info.items():
                if key.startswith("_") or value is None:
                    continue
                parts.append(f"| {key} | {value} |")

        # 段落内容（含泛化模板）
        paragraphs = task_detail.get("source_paragraphs", [])
        if paragraphs:
            parts.append("\n## 段落内容\n")
            for para in paragraphs:
                title = para.get("title", "")
                content = para.get("content", "")
                section_path = para.get("section_path", [])
                path_hint = ".".join(str(p) for p in section_path) if section_path else ""

                if title:
                    parts.append(f"\n### {path_hint} {title}" if path_hint else f"\n### {title}")

                if content:
                    parts.append(content)

                # 泛化模板
                template = para.get("template", {})
                generalized = template.get("generalized", "") if isinstance(template, dict) else ""
                if generalized:
                    parts.append(f"\n> **泛化模板**：{generalized}")

        # 结构化表格数据
        structured_blocks = task_detail.get("structured_blocks", [])
        if structured_blocks:
            parts.append("\n## 结构化数据\n")
            for block in structured_blocks:
                headers = block.get("headers", [])
                rows = block.get("rows", [])
                html_content = block.get("html_content", "")

                # 优先使用 HTML 表格
                if html_content:
                    parts.append(f"\n{html_content}")
                elif headers and rows:
                    # Markdown 表格
                    parts.append("| " + " | ".join(str(h) for h in headers) + " |")
                    parts.append("| " + " | ".join("---" for _ in headers) + " |")
                    for row in rows:
                        parts.append("| " + " | ".join(str(c) for c in row) + " |")

        # 全局模板
        template_data = task_detail.get("template", {})
        if isinstance(template_data, dict) and template_data:
            generalized = template_data.get("generalized", "")
            slots = template_data.get("slots", [])
            if generalized:
                parts.append("\n## 全局泛化模板\n")
                parts.append(generalized)
            if slots:
                parts.append("\n### 插槽列表\n")
                parts.append("| 插槽名称 | 描述 | 数据来源 |")
                parts.append("| --- | --- | --- |")
                for slot in slots:
                    name = slot.get("name", "")
                    desc = slot.get("description", "")
                    source = slot.get("suggested_source", slot.get("data_source", ""))
                    parts.append(f"| {name} | {desc} | {source} |")

        return "\n".join(parts)

    def _build_structured_document(
        self, task_detail: dict[str, Any], file_id: str, filename: str
    ) -> StructuredDocument:
        """将任务详情构建为 StructuredDocument，保留完整语义元数据

        每个段落（source_paragraphs）对应一个 chunk，保留章节层级和模板信息，
        供 _ingest_structured_document 进行去噪和上下文重组。
        """
        chunks: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        chunk_idx = 0

        # 从任务详情中提取行业和报告类型
        domain_label = task_detail.get("domain_label", "")
        document_type = task_detail.get("document_type", "")

        # 从 base_info 中尝试获取更准确的行业信息
        base_info = task_detail.get("base_info", {})
        industry = base_info.get("行业", base_info.get("Industry", domain_label))
        report_type = base_info.get("报告类型", base_info.get("Report_Type", document_type))

        # 构建基础信息 chunk（将基础信息作为第一个 chunk）
        if base_info:
            info_lines: list[str] = []
            for key, value in base_info.items():
                if key.startswith("_") or value is None:
                    continue
                info_lines.append(f"{key}: {value}")
            if info_lines:
                chunks.append(
                    {
                        "id": f"{file_id}_info",
                        "content": "\n".join(info_lines),
                        "chunk_order_index": chunk_idx,
                        "section_id": "base_info",
                        "section_title": "基础信息",
                        "parent_section_title": "",
                        "template": None,
                        "slots": None,
                    }
                )
                sections.append(
                    {
                        "section_id": "base_info",
                        "title": "基础信息",
                        "level": 1,
                        "order": 0,
                        "parent_section": None,
                        "path": ["基础信息"],
                        "chunk_indexes": [chunk_idx],
                    }
                )
                chunk_idx += 1

        # 构建段落 chunks
        paragraphs = task_detail.get("source_paragraphs", [])
        for para in paragraphs:
            title = para.get("title", "")
            content = para.get("content", "")
            section_path = para.get("section_path", [])

            # 将内容转为纯文本（去除 HTML 标记）
            plain_content = re.sub(r"<[^>]+>", "", content) if content else ""

            # 段落正文 chunk
            if plain_content:
                section_id = para.get("section_id", f"sec_{chunk_idx}")

                # 先临时填入 section_path[-2] 作为父级 ID，后面回填标题
                parent_section_id = (
                    ".".join(str(p) for p in section_path[:-1]) if section_path and len(section_path) > 1 else ""
                )

                chunks.append(
                    {
                        "id": f"{file_id}_chunk_{chunk_idx}",
                        "content": plain_content,
                        "chunk_order_index": chunk_idx,
                        "section_id": section_id,
                        "section_title": title,
                        "parent_section_title": "",
                        "parent_section_id": parent_section_id,
                        "template": para.get("template"),
                        "slots": para.get("template", {}).get("slots")
                        if isinstance(para.get("template"), dict)
                        else None,
                    }
                )

                # 记录章节
                level = min(len(section_path), 4) if section_path else 2
                sections.append(
                    {
                        "section_id": section_id,
                        "title": title,
                        "level": level,
                        "order": chunk_idx,
                        "parent_section": parent_section_id or None,
                        "path": [str(p) for p in section_path] if section_path else [title],
                        "chunk_indexes": [chunk_idx],
                    }
                )
                chunk_idx += 1

        # 构建表格 chunks
        structured_blocks = task_detail.get("structured_blocks", [])
        for block in structured_blocks:
            headers = block.get("headers", [])
            rows = block.get("rows", [])
            if headers and rows:
                # 将表格序列化为文本
                table_lines = [" | ".join(str(h) for h in headers)]
                table_lines.append(" | ".join("---" for _ in headers))
                for row in rows:
                    table_lines.append(" | ".join(str(c) for c in row))

                chunks.append(
                    {
                        "id": f"{file_id}_tbl_{chunk_idx}",
                        "content": "\n".join(table_lines),
                        "chunk_order_index": chunk_idx,
                        "section_id": block.get("section_id", ""),
                        "section_title": block.get("title", "结构化表格"),
                        "parent_section_title": "",
                        "template": None,
                        "slots": None,
                    }
                )
                chunk_idx += 1

        # 构建 section_id -> section 映射，回填 parent_section_title 和 section summary
        section_map = {s["section_id"]: s for s in sections}
        for chunk in chunks:
            pid = chunk.pop("parent_section_id", "")
            if pid and pid in section_map:
                chunk["parent_section_title"] = section_map[pid]["title"]
        for section in sections:
            if not section.get("summary") and section.get("chunk_indexes"):
                first_idx = section["chunk_indexes"][0]
                if first_idx < len(chunks):
                    section["summary"] = chunks[first_idx].get("content", "")[:200]

        return StructuredDocument(
            file_id=file_id,
            filename=filename,
            chunks=chunks,
            sections=sections,
            industry=industry,
            report_type=report_type,
            standard_code="",
            metadata={
                "domain_label": domain_label,
                "document_type": document_type,
                "task_id": task_detail.get("task_id", ""),
            },
        )

    async def _increment_learned_template_match_counts(self, paragraphs: list[dict]) -> None:
        """ETL 匹配阶段后，对被命中的学习模板累加 match_count"""
        learned_ids: set[int] = set()
        for para in paragraphs:
            tpl_id = (para.get("template_match") or {}).get("template_id", "")
            if tpl_id.startswith("learned_"):
                try:
                    learned_ids.add(int(tpl_id.removeprefix("learned_")))
                except ValueError:
                    pass
        if not learned_ids:
            return
        from sqlalchemy import text as sa_text

        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                sa_text(
                    "UPDATE domain_factory_learned_templates "
                    "SET match_count = match_count + 1 "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": list(learned_ids)},
            )
        logger.info(f"学习模板 match_count 更新: {learned_ids}")

    @staticmethod
    def _group_assets_by_chapter(task_detail: dict) -> dict[str, dict]:
        """按原始章节标题分组 ETL 已抽资产。章节标识取段落 title（去空白），无 title 的归 '未分类'。"""
        groups: dict[str, dict] = {}
        for para in task_detail.get("source_paragraphs", []):
            ch = (para.get("title") or para.get("chapter") or "未分类").strip()
            g = groups.setdefault(
                ch,
                {
                    "templates": [],
                    "paragraphs": [],
                    "legal_refs": [],
                    "entities": [],
                    "tables": [],
                    "formulas": [],
                    "charts": [],
                    "figures": [],
                    "template_chapter_keys": set(),
                },
            )
            g["paragraphs"].append(para)
            tmpl = para.get("template") or {}
            if tmpl.get("generalized") or tmpl.get("slots"):
                g["templates"].append(tmpl)
            # 收集与 _save_learned_templates_from_task 相同的 chapter 标识，供回填精确匹配
            pk = (para.get("title") or "").strip() or (
                ".".join(str(s) for s in para.get("section_path", []))
                if para.get("section_path")
                else ""
            )
            if pk:
                g["template_chapter_keys"].add(pk)
        # 结构化资产按章回填（ETL 抽取产物里若带 chapter/title 则归入对应组）
        for _key, items, target in (
            ("legal_references", task_detail.get("legal_references", []), "legal_refs"),
            ("table_schemas", task_detail.get("table_schemas", []), "tables"),
            ("formulas", task_detail.get("formulas", []), "formulas"),
            ("entities", task_detail.get("entities", []), "entities"),
        ):
            for item in items or []:
                ch = (item.get("chapter") or item.get("title") or "未分类").strip()
                groups.setdefault(
                    ch,
                    {
                        "templates": [],
                        "paragraphs": [],
                        "legal_refs": [],
                        "entities": [],
                        "tables": [],
                        "formulas": [],
                        "charts": [],
                        "figures": [],
                        "template_chapter_keys": set(),
                    },
                )[target].append(item)
        return groups

    @staticmethod
    def _assemble_deterministic_outline(assets: dict) -> dict:
        """从分好组的资产确定性组装大纲的 7 个结构化字段。"""
        slots: list[str] = []
        for tmpl in assets.get("templates", []):
            for s in tmpl.get("slots") or []:
                name = s.get("name") if isinstance(s, dict) else s
                if name and name not in slots:
                    slots.append(name)
        roles = sorted(
            {p.get("classify_type") for p in assets.get("paragraphs", []) if p.get("classify_type")}
        )
        content_requirements = slots + [f"段落类型:{r}" for r in roles]

        regulations = [
            {
                "code": r.get("code"),
                "title": r.get("title"),
                "effective_date": r.get("effective_date"),
                "scope": r.get("scope"),
                "standard_code": r.get("standard_code") or r.get("code"),
            }
            for r in assets.get("legal_refs", [])
        ]
        entity_bindings = [
            {
                "entity_id": e.get("entity_id"),
                "entity_key": e.get("entity_key"),
                "role": e.get("role"),
                "value_type": e.get("value_type"),
                "unit": e.get("unit"),
            }
            for e in assets.get("entities", [])
        ]
        expected_tables = [
            {
                "table_type": t.get("table_type"),
                "purpose": t.get("purpose"),
                "columns": t.get("columns") or [],
                "standard_code": t.get("standard_code"),
            }
            for t in assets.get("tables", [])
        ]
        expected_formulas = [
            {
                "formula_template": f.get("formula_template"),
                "variables": f.get("variables") or [],
                "purpose": f.get("purpose"),
            }
            for f in assets.get("formulas", [])
        ]
        expected_charts = [
            {
                "chart_type": c.get("chart_type"),
                "purpose": c.get("purpose"),
                "data_source": c.get("data_source"),
            }
            for c in assets.get("charts", [])
        ]
        expected_figures = [
            {
                "figure_type": fg.get("figure_type"),
                "purpose": fg.get("purpose"),
                "generation_hint": fg.get("generation_hint"),
            }
            for fg in assets.get("figures", [])
        ]
        # writing_example：取最长 sample_original
        samples = [
            t.get("sample_original") for t in assets.get("templates", []) if t.get("sample_original")
        ]
        writing_example = max(samples, key=len) if samples else None

        return {
            "content_requirements": content_requirements,
            "regulations": regulations,
            "entity_bindings": entity_bindings,
            "expected_tables": expected_tables,
            "expected_formulas": expected_formulas,
            "expected_charts": expected_charts,
            "expected_figures": expected_figures,
            "writing_example": writing_example,
        }

    CHAPTER_META_PROMPT = """你是煤炭环评报告章节分析专家。为下列章节产出结构化元数据。

章节标题：{title}
该章已抽出的内容要点：{requirements}

【已存在的规范章节名列表（优先复用，避免新建同义名）】
{seed_keys}

严格输出 JSON（不要 markdown 围栏）：
{{
  "canonical_chapter_key": "规范章节名（优先从上面列表选；都不贴切才新建，用简练通用的中文名，如'地下水环境影响预测'）",
  "purpose": "1-2 句：本章在环评中的作用与编写目的",
  "overview": "2-3 句：本章概述",
  "key_points": ["要点1", "要点2", "要点3-5个"],
  "writing_hints": "本章专属写作提示（如：先列现状值再列标准值；用表格呈现监测点位）"
}}
"""

    async def _llm_chapter_meta(self, chapter_title: str, deterministic: dict, seed_keys: list[str]) -> dict:
        import json as _json
        import re as _re

        prompt = self.CHAPTER_META_PROMPT.format(
            title=chapter_title,
            requirements=", ".join(deterministic.get("content_requirements", [])[:30]) or "（无）",
            seed_keys=", ".join(seed_keys) or "（首次，无已有规范名）",
        )
        fallback_key = chapter_title
        try:
            model = select_model()
            response = await model.call(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            m = _re.search(r"\{[\s\S]*\}", text)
            if not m:
                raise ValueError("LLM 未返回 JSON")
            data = m.group(0)
            parsed = _json.loads(data)
            parsed.setdefault("canonical_chapter_key", fallback_key)
            for k in ("purpose", "overview", "key_points", "writing_hints"):
                parsed.setdefault(k, [] if k == "key_points" else None)
            return parsed
        except Exception as e:
            logger.warning(f"章节元数据 LLM 调用失败（不阻断）: {e}")
            return {
                "canonical_chapter_key": fallback_key,
                "purpose": None,
                "overview": None,
                "key_points": [],
                "writing_hints": None,
            }

    async def _produce_outlines_async(self, task_id: str, domain_code: str, report_type_code: str) -> int:
        """commit 阶段：逐章组装大纲 + LLM 归一/散文 → upsert。非阻断由调用方保证。"""
        task_detail = await self.get_task_detail(task_id)
        groups = self._group_assets_by_chapter(task_detail)
        seed_keys = await self.repo.list_chapter_keys(domain_code, report_type_code)
        count = 0
        for chapter_raw, assets in groups.items():
            deterministic = self._assemble_deterministic_outline(assets)
            meta = await self._llm_chapter_meta(chapter_raw, deterministic, seed_keys)
            canonical_key = meta["canonical_chapter_key"]
            await self.repo.upsert_outline(
                domain_code=domain_code,
                report_type_code=report_type_code,
                canonical_chapter_key=canonical_key,
                chapter_id=chapter_raw.split()[0] if chapter_raw[:1].isdigit() else None,
                chapter_title=chapter_raw,
                purpose=meta.get("purpose"),
                overview=meta.get("overview"),
                key_points=meta.get("key_points") or [],
                **deterministic,
                writing_hints=meta.get("writing_hints"),
                source_task_ids=[task_id],
                source_count=1,
                prose_based_on_source_count=1,
            )
            # 回填 learned_templates.canonical_chapter_key（供 get_templates 检索）
            await self.repo.backfill_template_chapter_key(
                domain_code, report_type_code, list(assets.get("template_chapter_keys", [])), canonical_key
            )
            if canonical_key not in seed_keys:
                seed_keys.append(canonical_key)
            count += 1
        # LLM 算出的 canonical_chapter_key 已通过 ETL 源头(graph_builder Task 1)写入图谱;
        # 此处若需 LLM key 覆盖推导 key,需重建 chapter_id——见 GraphBuilder.backfill_canonical_keys
        logger.info(f"章节大纲产出: {count} 章, domain={domain_code}, report_type={report_type_code}")
        return count

    async def _save_learned_templates_from_task(self, task_detail: dict[str, Any]) -> int:
        """从已提交任务中提取高质量模板，回流到学习模板库"""
        domain_code = task_detail.get("domain", "coal")
        report_type_code = task_detail.get("report_type_code")
        paragraphs = task_detail.get("source_paragraphs", [])
        saved = 0

        for para in paragraphs:
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue
            generalized = template.get("generalized", "")
            if not generalized or len(generalized) < 20:
                continue

            slots = template.get("slots", [])
            slot_names = sorted(s.get("name", "") for s in slots if isinstance(s, dict))
            slot_signature = "|".join(slot_names)
            section_path = para.get("section_path", [])
            chapter = para.get("title", "") or (".".join(str(p) for p in section_path) if section_path else "")
            sample_original = para.get("original", para.get("content", ""))
            metadata = template.get("metadata", {})

            await self.repo.upsert_learned_template(
                domain_code=domain_code,
                chapter=chapter,
                generalized=generalized,
                slots=slots,
                slot_signature=slot_signature,
                sample_original=sample_original,
                extra_meta=metadata,
                report_type_code=report_type_code,
            )
            saved += 1

        if saved > 0:
            logger.info(f"模板回流完成: 领域={domain_code}, 保存/更新={saved} 个模板")
        return saved

    async def reingest_task(self, task_id: str, knowledge_base_id: str | None = None) -> dict[str, Any] | None:
        """再入库：重新处理并入库已提交的任务"""
        task = await self.repo.get_task_with_domain(task_id)
        if not task:
            return None

        # 重置状态为待审核
        task = await self.repo.update_task(
            task_id,
            {
                "status": "WAITING_REVIEW",
                "committed_at": None,
                "reviewer": None,
            },
        )

        # 生成新的入库任务ID
        ingest_task_id = f"reingest_{task_id}_{uuid.uuid4().hex[:8]}"

        # 注册到任务中心进行重新入库
        try:
            from yuxi.services.task_service import tasker as global_tasker

            await global_tasker.enqueue(
                name=f"知识工厂再入库: {task.file_name}",
                task_type="domain_factory_reingest",
                payload={
                    "task_id": task_id,
                    "domain_factory_task_id": task_id,
                    "knowledge_base_id": knowledge_base_id,
                    "file_name": task.file_name,
                    "reingest": True,
                },
                coroutine=self._reingest_pipeline_async,
            )
            logger.info(f"已注册再入库任务到任务中心: {task_id}")
        except Exception as e:
            logger.warning(f"注册再入库任务失败: {e}")

        result = task.to_summary_dict() if task else None
        if result:
            result["ingest_task_id"] = ingest_task_id
        return result

    async def _reingest_pipeline_async(self, context) -> dict[str, Any]:
        """再入库流水线异步执行 - 使用结构化入库逻辑"""
        from yuxi.services.domain_factory_service import get_domain_factory_service

        task_id = None
        knowledge_base_id = None
        try:
            if hasattr(context, "_tasker") and hasattr(context, "task_id"):
                tasker_task = context._tasker._tasks.get(context.task_id)
                if tasker_task and tasker_task.payload:
                    task_id = tasker_task.payload.get("task_id")
                    knowledge_base_id = tasker_task.payload.get("knowledge_base_id")
        except Exception as e:
            logger.warning(f"获取再入库任务ID失败: {e}")

        if not task_id:
            return {"error": "task_id not found"}

        service = get_domain_factory_service()
        task = await service.repo.get_task_with_domain(task_id)

        if not task:
            return {"error": "task not found"}

        try:
            await context.set_progress(10.0, "正在准备再入库...")
            await context.set_message("正在准备再入库...")

            # 获取任务详情
            task_detail = await service.get_task_detail(task_id)

            # 使用任务记录中的 knowledge_base_id 作为回退
            if not knowledge_base_id:
                knowledge_base_id = task.knowledge_base_id

            # 执行入库
            if knowledge_base_id:
                await context.set_progress(30.0, "正在组装入库内容...")
                await context.set_message("正在组装入库内容...")

                from yuxi.knowledge import knowledge_base as kb_manager
                from yuxi.knowledge.base import FileStatus

                ingest_markdown = self._build_ingest_markdown(task_detail)

                await context.set_progress(40.0, "正在写入知识库...")
                await context.set_message("正在写入知识库...")

                kb_instance = await kb_manager.aget_kb(knowledge_base_id)
                if not kb_instance:
                    raise ValueError(f"知识库 {knowledge_base_id} 不存在")

                file_name = task_detail.get("file_name", f"domain_factory_{task_id}.md")
                file_id = f"df_ri_{hashstr(task_id + str(uuid.uuid4()), 8)}"

                # 1. 保存 Markdown 到 MinIO
                markdown_url = ""
                if hasattr(kb_instance, "_save_markdown_to_minio"):
                    markdown_url = await kb_instance._save_markdown_to_minio(
                        knowledge_base_id, file_id, ingest_markdown
                    )

                # 上传原文件到 MinIO(供预览/下载,path 指向原文件而非 markdown)
                original_url, original_size = await self._upload_original_to_minio(
                    knowledge_base_id, file_id, task_detail.get("storage_path", ""), file_name
                )

                # 2. 创建文件记录，直接设为 PARSED 状态（写入知识库文件表，供 index_file 消费）
                file_meta = {
                    "file_id": file_id,
                    "kb_id": knowledge_base_id,
                    "filename": file_name,
                    "original_filename": file_name,
                    "file_type": Path(file_name).suffix.lower().lstrip(".") or "bin",
                    "path": original_url or markdown_url,
                    "markdown_file": markdown_url,
                    "status": FileStatus.PARSED,
                    "content_hash": hashstr(ingest_markdown),
                    "size": original_size or len(ingest_markdown),
                    "content_type": "domain_factory",
                    "processing_params": {},
                    "is_folder": False,
                }
                await kb_instance._persist_file_meta(file_id, file_meta)

                await context.set_progress(50.0, "正在写入知识库...")
                await context.set_message("正在写入知识库...")

                # 3. 优先使用结构化入库
                if hasattr(kb_instance, "_ingest_structured_document"):
                    structured_doc = self._build_structured_document(task_detail, file_id, file_name)
                    rag = await kb_instance._get_lightrag_instance(knowledge_base_id)
                    if rag:
                        await kb_instance._ingest_structured_document(
                            rag=rag,
                            db_id=knowledge_base_id,
                            file_id=file_id,
                            file_path=f"domain_factory/reingest_{task_id}/{file_name}",
                            structured_doc=structured_doc,
                        )
                        kb_instance.files_meta[file_id]["status"] = FileStatus.INDEXED
                        kb_instance.files_meta[file_id]["updated_at"] = utc_isoformat()
                        await kb_instance._persist_file(file_id)
                        logger.info(
                            f"结构化再入库完成: {task_id} -> {knowledge_base_id}, "
                            f"file_id={file_id}, chunks={len(structured_doc.chunks)}"
                        )
                    else:
                        raise ValueError(f"获取 LightRAG 实例失败: {knowledge_base_id}")
                else:
                    # 回退到标准 Markdown 入库
                    logger.info("知识库实例不支持结构化入库，回退到 Markdown 方案")
                    await kb_manager.index_file(knowledge_base_id, file_id)
                    logger.info(f"再入库成功: {task_id} -> 知识库 {knowledge_base_id}, file_id={file_id}")
            else:
                logger.warning(f"再入库任务 {task_id} 未指定目标知识库，跳过入库")

            # 构建知识图谱
            await context.set_progress(80.0, "正在构建知识图谱...")
            await context.set_message("正在构建知识图谱...")

            try:
                from yuxi.services.graph_builder import GraphBuilder

                graph_builder = GraphBuilder()
                doc_id = f"doc_{task_id}"
                source_paragraphs = task_detail.get("source_paragraphs", [])
                domain_label = task_detail.get("domain_label", "")
                base_info = task_detail.get("base_info", {})

                                # 将逻辑关系注入段落的 template 中
                logical_relations = task_detail.get("logical_relations", {})
                if isinstance(logical_relations, dict) and any(isinstance(v, list) and v for v in logical_relations.values()):
                    for para in source_paragraphs:
                        tmpl = para.get("template") or {}
                        if isinstance(tmpl, dict):
                            tmpl["logical_refs"] = logical_relations
                            para["template"] = tmpl

                if source_paragraphs:
                    graph_stats = graph_builder.build_knowledge_graph(
                        kb_id=knowledge_base_id or "",
                        doc_id=doc_id,
                        doc_title=task_detail.get("file_name", ""),
                        source_paragraphs=source_paragraphs,
                        domain_label=domain_label,
                        base_info=base_info,
                        domain_code=self._normalize_domain_for_graph(task_detail.get("domain") or ""),
                        report_type_code=self._normalize_report_type_for_graph(task_detail.get("report_type_code") or ""),
                    )
                    logger.info(f"知识图谱构建完成: {graph_stats}")
                    graph_builder.close()
            except Exception as e:
                logger.warning(f"知识图谱构建失败（不阻断再入库）: {e}")

            await context.set_progress(90.0, "正在完成...")
            await context.set_message("正在完成...")

            # 更新任务状态
            await service.repo.update_task(
                task_id,
                {
                    "status": "COMMITTED",
                    "ingest_task_id": f"reingest_{task_id}_{uuid.uuid4().hex[:8]}",
                },
            )

            await context.set_progress(100.0, "再入库完成")
            await context.set_message("再入库完成")

            return {
                "task_id": task_id,
                "status": "COMMITTED",
                "message": "再入库流水线执行完成",
            }

        except Exception as e:
            logger.exception(f"再入库流水线执行失败: {task_id}")
            await service.repo.update_task(task_id, {"status": "FAILED", "error_message": str(e)})
            await context.set_progress(100.0, f"执行失败: {str(e)}")
            return {"error": str(e)}

    async def delete_task(self, task_id: str) -> bool:
        task = await self.repo.get_task(task_id)
        if task and task.storage_path:
            try:
                path = Path(task.storage_path)
                if path.exists():
                    path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete task file {task.storage_path}: {e}")
        return await self.repo.delete_task(task_id)

    async def retry_task(self, task_id: str) -> dict[str, Any] | None:
        updated_task = await self.repo.update_task(task_id, {"status": "UPLOADED", "error_message": None})
        if not updated_task:
            return None

        # 重新提交到 Tasker 队列
        domain = await self.repo.get_domain_by_id(updated_task.domain_id)
        domain_code = domain.code if domain else "unknown"
        try:
            await tasker.enqueue(
                name=f"知识工厂: {updated_task.file_name}",
                task_type="domain_factory",
                payload={
                    "task_id": task_id,
                    "domain_factory_task_id": task_id,
                    "domain_code": domain_code,
                    "domain_name": domain.name if domain else "",
                    "file_name": updated_task.file_name,
                },
                coroutine=self._etl_pipeline_async,
            )
            logger.info(f"重试任务已注册到 Tasker: {task_id}")
        except Exception as e:
            logger.warning(f"重试任务注册 Tasker 失败: {e}")

        return updated_task.to_summary_dict()

    # ========== Pipeline Config ==========

    def get_pipeline_config_path(self) -> Path:
        return self._storage_dir / "pipeline_config.json"

    async def get_pipeline_config(self) -> dict[str, Any]:
        path = self.get_pipeline_config_path()
        if not path.exists():
            return {
                "pipeline_id": "default",
                "entry_point": "upload",
                "nodes": [
                    {"id": "upload", "type": "input", "label": "文件上传"},
                    {"id": "parse", "type": "process", "label": "文档解析"},
                    {"id": "extract", "type": "llm", "label": "信息提取"},
                    {"id": "review", "type": "manual", "label": "人工审核"},
                    {"id": "commit", "type": "output", "label": "确认入库"},
                ],
                "edges": [
                    {"source": "upload", "target": "parse"},
                    {"source": "parse", "target": "extract"},
                    {"source": "extract", "target": "review"},
                    {"source": "review", "target": "commit"},
                ],
            }
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to load pipeline config: {e}")
            return {"pipeline_id": "default", "nodes": [], "edges": []}

    async def save_pipeline_config(self, config_data: dict[str, Any]) -> bool:
        path = self.get_pipeline_config_path()
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(config_data, ensure_ascii=False, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save pipeline config: {e}")
            return False

    # ========== Prompt Config ==========

    async def get_prompt_config(self) -> dict[str, Any]:
        default_config = {
            "extract_prompt": "你是一个专业的文档信息提取助手。请从以下文档中提取结构化信息。",
            "template_prompt": "请将以下文本泛化为包含槽位的模板格式。",
            "schema_generation_prompt": "请根据领域知识生成标准的Schema配置。",
        }
        configs = await self.repo.list_prompt_configs()
        if not configs:
            return {"config": default_config}
        result = {}
        for cfg in configs:
            result[f"{cfg['prompt_type']}_prompt"] = cfg.get("template", "")
        if not result:
            result = default_config
        return {"config": result}

    async def save_prompt_config(self, config_data: dict[str, Any]) -> bool:
        try:
            for prompt_type, template in config_data.items():
                await self.repo.upsert_prompt_config(None, prompt_type, template)
            self._invalidate_prompt_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to save prompt config: {e}")
            return False

    # ========== Context & Section Routing ==========

    async def query_graph_templates(
        self, domain_code: str = "", report_type_code: str = "", limit: int = 50
    ) -> dict[str, Any]:
        """按 (domain, report_type) 查询图谱中的模板数据"""
        import os

        try:
            from neo4j import GraphDatabase as Neo4jDriver

            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            username = os.getenv("NEO4J_USERNAME", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "0123456789")

            driver = Neo4jDriver.driver(uri, auth=(username, password))
            results = {"sections": [], "templates": [], "table_schemas": []}

            with driver.session() as session:
                # 查询 Section 节点
                where_clauses = []
                if domain_code:
                    where_clauses.append("d.domain_code = $domain_code")
                if report_type_code:
                    where_clauses.append("d.report_type_code = $report_type_code")
                where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                # Sections
                sec_result = session.run(
                    f"""
                    MATCH (d:Document)-[:HAS_SECTION]->(s:Section)
                    {where_str}
                    RETURN s.id as id, s.title as title, s.level as level,
                           s.section_path_str as path, d.domain_code as domain
                    ORDER BY s.section_path_str
                    LIMIT $limit
                    """,
                    domain_code=domain_code,
                    report_type_code=report_type_code,
                    limit=limit,
                )
                results["sections"] = [dict(record) for record in sec_result]

                # ParagraphTemplates
                tpl_result = session.run(
                    f"""
                    MATCH (d:Document)-[:HAS_SECTION]->(s)-[:COMPOSED_OF]->(pt:ParagraphTemplate)
                    {where_str}
                    RETURN pt.id as id, pt.text_pattern as pattern,
                           pt.classify_type as classify_type, pt.hash as hash,
                           s.title as section_title
                    LIMIT $limit
                    """,
                    domain_code=domain_code,
                    report_type_code=report_type_code,
                    limit=limit,
                )
                results["templates"] = [dict(record) for record in tpl_result]

                # TableSchemas
                tbl_result = session.run(
                    f"""
                    MATCH (d:Document)-[:HAS_SECTION]->(s)-[:HAS_TABLE_SCHEMA]->(ts:TableSchema)
                    {where_str}
                    RETURN ts.id as id, ts.name as name, ts.table_type as table_type,
                           ts.columns as columns
                    LIMIT $limit
                    """,
                    domain_code=domain_code,
                    report_type_code=report_type_code,
                    limit=limit,
                )
                results["table_schemas"] = [dict(record) for record in tbl_result]

            driver.close()
            return results
        except Exception as e:
            logger.warning(f"图谱查询失败: {e}")
            return {"sections": [], "templates": [], "table_schemas": [], "error": str(e)}

    async def query_graph_legal_references(
        self, scope: str = "", limit: int = 100
    ) -> dict[str, Any]:
        """查询图谱中的法律引用，支持按 scope 过滤"""
        import os

        try:
            from neo4j import GraphDatabase as Neo4jDriver

            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            username = os.getenv("NEO4J_USERNAME", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "0123456789")

            driver = Neo4jDriver.driver(uri, auth=(username, password))
            where_clause = "WHERE lr.scope = $scope" if scope else ""

            with driver.session() as session:
                result = session.run(
                    f"""
                    MATCH (lr:LegalReference)
                    {where_clause}
                    RETURN lr.id as id, lr.name as name, lr.code as code,
                           lr.type as type, lr.scope as scope,
                           lr.authority as authority, lr.frequency as frequency
                    ORDER BY lr.frequency DESC
                    LIMIT $limit
                    """,
                    scope=scope,
                    limit=limit,
                )
                refs = [dict(record) for record in result]

            driver.close()
            return {"legal_references": refs, "total": len(refs)}
        except Exception as e:
            logger.warning(f"法律引用查询失败: {e}")
            return {"legal_references": [], "total": 0, "error": str(e)}

    async def get_contexts(self) -> dict[str, Any]:
        # 统计学习模板和实体数
        template_count = await self.repo.count_learned_templates()
        try:
            from yuxi.repositories.domain_entity_repository import DomainEntityRepository
            entity_repo = DomainEntityRepository()
            entity_count = len(await entity_repo.list_all())
        except Exception:
            entity_count = 0

        # 从数据库查询领域
        domains = await self.repo.list_domains()

        # 统计每个领域的已入库任务数
        committed_count = 0
        for d in domains:
            committed_count += await self.repo.count_committed_tasks(d.get("code", ""))

        # 从数据库查询报告类型
        report_types = await self.repo.list_report_types()

        # 按 domain_code 分组
        report_types_by_domain: dict[str, list] = {}
        for rt in report_types:
            dc = rt.get("domain_code", "")
            if dc:
                report_types_by_domain.setdefault(dc, []).append(rt)

        return {
            "domains": domains,
            "report_types": report_types_by_domain,
            "stats": {
                "learned_templates": template_count,
                "entity_count": entity_count,
                "committed_tasks": committed_count,
            },
        }

    # ========== Section Routing ==========

    # ========== Standard Code Mapping ==========

    # ========== Entity Evolution（实体进化回路） ==========

    def _collect_unrecognized_slots(self, paragraphs: list[dict]) -> list[dict[str, Any]]:
        """从泛化结果中收集未匹配到实体的插槽"""
        seen_names: set[str] = set()
        slots: list[dict[str, Any]] = []
        for para in paragraphs:
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue
            for slot in template.get("slots", []):
                if slot.get("entity_ref"):
                    continue  # 已匹配，跳过
                name = slot.get("name", "")
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                slots.append(
                    {
                        "name": name,
                        "type": slot.get("type", ""),
                        "description": slot.get("description", ""),
                        "data_source": slot.get("data_source", slot.get("suggested_source", "")),
                        "paragraph_title": para.get("title", ""),
                        "content_preview": para.get("content", "")[:200],
                    }
                )
        return slots

    async def get_proposed_entities(self, task_id: str) -> dict[str, Any]:
        """使用 LLM 将未识别插槽整理为新实体建议，供用户确认后保存到实体库

        分两步处理：
        1. 先匹配已有实体的属性（插槽可能是已有实体缺失的属性）
        2. 剩余的插槽交给 LLM 判断是独立实体还是某个实体的属性
        """
        detail = await self.get_task_detail(task_id)
        if not detail:
            return {"entities": [], "message": "任务不存在"}

        template_metadata = detail.get("template_metadata") or {}
        raw_slots = template_metadata.get("unrecognized_slots", [])
        if not raw_slots:
            return {"entities": [], "message": "没有未识别的插槽"}

        domain_code = template_metadata.get("domain_code") or detail.get("domain") or "coal"

        # 获取领域名称
        domain_obj = await self.repo.get_domain_by_code(domain_code) if domain_code else None
        domain_name_str = domain_obj.name if domain_obj else domain_code or "通用"

        # 获取现有实体完整结构（含属性）
        existing_entities = await self._get_existing_entities_full(domain_code)

        # 第一步：匹配已有实体的属性
        property_proposals, remaining_slots = self._match_slots_to_existing_entities(raw_slots, existing_entities)

        # 第二步：剩余插槽交给 LLM 判断
        entity_proposals = []
        if remaining_slots:
            prompt = self._build_entity_proposal_prompt(remaining_slots, existing_entities, domain_name_str)
            try:
                from yuxi.models.chat import select_model

                model = select_model()
                response = await model.call(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                entity_proposals = self._parse_entity_proposal_response(text)
            except Exception as e:
                logger.warning(f"LLM 实体建议生成失败: {e}")

        return {
            "entities": property_proposals + entity_proposals,
            "raw_slots": raw_slots,
            "matched_count": len(property_proposals),
            "new_count": len(entity_proposals),
            "domain_code": domain_code,
        }

    async def confirm_proposed_entities(self, task_id: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
        """将用户确认的实体/属性保存到数据库实体库

        支持两种类型：
        - new_entity: 创建新实体
        - add_property: 向已有实体追加属性
        """
        detail = await self.get_task_detail(task_id)
        if not detail:
            return {"saved": 0, "error": "任务不存在"}

        template_metadata = detail.get("template_metadata") or {}
        domain_code = template_metadata.get("domain_code") or detail.get("domain") or "coal"

        from yuxi.repositories.domain_entity_repository import DomainEntityRepository

        repo = DomainEntityRepository()
        saved = 0
        skipped = 0

        for entity_data in entities:
            if not entity_data.get("_confirmed"):
                skipped += 1
                continue

            suggestion_type = entity_data.get("suggestion_type", "new_entity")

            if suggestion_type == "add_property":
                # 向已有实体追加属性
                target_key = entity_data.get("target_entity_key") or entity_data.get("entity_key", "")
                if not target_key:
                    skipped += 1
                    continue
                existing = await repo.get_by_key(target_key, domain_code=domain_code)
                if not existing:
                    logger.warning(f"目标实体不存在: {target_key}")
                    skipped += 1
                    continue
                proposed_prop = entity_data.get("proposed_property", {})
                if not proposed_prop:
                    skipped += 1
                    continue
                current_props = list(existing.properties or [])
                # 去重
                existing_keys = {p.get("key", "") for p in current_props}
                if proposed_prop.get("key", "") not in existing_keys:
                    current_props.append(proposed_prop)
                    await repo.update(existing.entity_id, {"properties": current_props})
                    saved += 1
                    logger.info(f"追加属性到 {existing.name_cn}: {proposed_prop.get('name_cn', '')}")
                else:
                    skipped += 1

            else:
                # 创建新实体
                entity_key = entity_data.get("entity_key", "")
                name_cn = entity_data.get("name_cn", "")
                if not entity_key or not name_cn:
                    skipped += 1
                    continue
                existing = await repo.get_by_key(entity_key, domain_code=domain_code)
                if existing:
                    logger.info(f"实体已存在，跳过: {entity_key}")
                    skipped += 1
                    continue
                data = {
                    "entity_id": str(uuid.uuid4()),
                    "entity_key": entity_key,
                    "name_cn": name_cn,
                    "category": entity_data.get("category", "其他"),
                    "domain_code": domain_code,
                    "value_type": entity_data.get("value_type", "String"),
                    "unit": entity_data.get("unit", ""),
                    "is_list_type": entity_data.get("is_list_type", False),
                    "description": entity_data.get("description", ""),
                    "synonyms": entity_data.get("synonyms", []),
                    "properties": entity_data.get("properties", []),
                    "relation_rules": [],
                    "metadata": {
                        "source": "etl_proposal",
                        "task_id": task_id,
                        "confidence": entity_data.get("confidence", 0),
                    },
                }
                await repo.create(data)
                saved += 1
                logger.info(f"保存新实体: {name_cn} ({entity_key})")

        # 触发同领域待审核任务的重映射
        remapped = 0
        try:
            remapped = await self._remap_waiting_review_tasks(domain_code)
            if remapped > 0:
                logger.info(f"实体确认后重映射: {remapped} 个任务已更新")
        except Exception as remap_err:
            logger.warning(f"实体重映射失败（不影响实体保存）: {remap_err}")

        return {"saved": saved, "skipped": skipped, "remapped": remapped}

    async def _remap_waiting_review_tasks(self, domain_code: str) -> int:
        """对同领域 WAITING_REVIEW 任务重新映射插槽的 entity_ref"""
        from yuxi.services.entity_meta_service import SlotEntityMapper

        pending_tasks = await self.repo.list_pending_tasks_by_domain(domain_code)
        if not pending_tasks:
            return 0

        mapper = SlotEntityMapper()
        updated = 0

        for task_summary in pending_tasks:
            task_id = task_summary["id"]
            task = await self.repo.get_task(task_id)
            if not task or not task.source_paragraphs:
                continue

            paragraphs = task.source_paragraphs
            changed = False

            for para in paragraphs:
                template = para.get("template", {})
                if not isinstance(template, dict):
                    continue
                raw_slots = template.get("slots", [])
                if not raw_slots:
                    continue

                try:
                    mapped_slots = mapper.map_slots(raw_slots, paragraph_context=para.get("content", ""))
                except Exception:
                    continue

                for i, mapped in enumerate(mapped_slots):
                    if i >= len(raw_slots):
                        break
                    old_ref = raw_slots[i].get("entity_ref", "")
                    new_ref = mapped.get("entity_ref", "")
                    if new_ref and not old_ref:
                        raw_slots[i]["entity_ref"] = new_ref
                        changed = True

            if changed:
                await self.repo.update_task(task_id, {"source_paragraphs": paragraphs})
                updated += 1

        if updated > 0:
            logger.info(f"实体重映射完成: 领域={domain_code}, 更新={updated} 个任务")
        return updated

    def _match_slots_to_existing_entities(
        self,
        raw_slots: list[dict],
        existing_entities: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """将未识别插槽匹配到已有实体的属性。

        返回 (属性补充建议列表, 剩余未匹配的插槽列表)。
        匹配规则：插槽名称与实体名称/同义词/已有属性名有交集。
        """
        property_proposals: list[dict] = []
        matched_slot_names: set[str] = set()

        for slot in raw_slots:
            slot_name = slot.get("name", "")
            if not slot_name:
                continue

            # 尝试匹配到已有实体（作为其属性）
            for entity in existing_entities:
                entity_name = entity.get("name_cn", "")
                synonyms = entity.get("synonyms", [])
                existing_props = entity.get("properties", [])
                existing_prop_names = {p.get("name_cn", p.get("key", "")) for p in existing_props}

                # 匹配条件：插槽名出现在实体的名称/同义词的上下文中
                is_related = (
                    slot_name in entity_name
                    or entity_name in slot_name
                    or any(syn in slot_name or slot_name in syn for syn in synonyms)
                    or slot_name in existing_prop_names
                )

                if is_related and slot_name not in existing_prop_names:
                    property_proposals.append(
                        {
                            "suggestion_type": "add_property",
                            "target_entity_id": entity.get("entity_id", ""),
                            "target_entity_key": entity.get("entity_key", ""),
                            "target_entity_name": entity.get("name_cn", ""),
                            "entity_key": entity.get("entity_key", ""),
                            "name_cn": entity.get("name_cn", ""),
                            "category": entity.get("category", ""),
                            "proposed_property": {
                                "key": re.sub(r"[^a-zA-Z0-9_一-鿿]", "_", slot_name),
                                "name_cn": slot_name,
                                "value_type": slot.get("type", "String"),
                                "description": slot.get("description", ""),
                            },
                            "confidence": 0.7,
                            "context": slot.get("paragraph_title", ""),
                        }
                    )
                    matched_slot_names.add(slot_name)
                    break

        remaining = [s for s in raw_slots if s.get("name", "") not in matched_slot_names]
        return property_proposals, remaining

    def _build_entity_proposal_prompt(
        self,
        raw_slots: list[dict],
        existing_entities: list[dict],
        domain_name: str = "",
    ) -> list[dict]:
        """构建 LLM Prompt：将剩余未识别插槽整理为新实体建议

        关键：传入完整实体结构（含属性），让 LLM 准确区分实体与属性。
        """
        slot_lines = []
        for s in raw_slots:
            slot_lines.append(
                f"- 插槽名: {s['name']}"
                f"  类型: {s.get('type', '未知')}"
                f"  描述: {s.get('description', '')}"
                f"  出现段落: {s.get('paragraph_title', '')}"
            )
        slots_text = "\n".join(slot_lines)

        # 构建现有实体结构描述（含属性）
        entity_lines = []
        for e in existing_entities[:30]:
            props = e.get("properties", [])
            prop_desc = ""
            if props:
                prop_names = [p.get("name_cn", p.get("key", "")) for p in props[:8]]
                prop_desc = f"，属性: {', '.join(prop_names)}"
            synonyms = e.get("synonyms", [])
            syn_desc = f"，别名: {', '.join(synonyms[:5])}" if synonyms else ""
            entity_lines.append(
                f"- {e.get('name_cn', '')} ({e.get('entity_key', '')}) [{e.get('category', '')}]{prop_desc}{syn_desc}"
            )
        existing_text = "\n".join(entity_lines) if entity_lines else "无"

        domain_name = domain_name or "通用"

        system_prompt = (
            "你是一个领域知识建模专家。"
            "你的任务是将 ETL 泛化阶段产生的未识别插槽变量整理为领域实体对象定义。"
            "\n\n关键概念区分：\n"
            "【实体对象】是独立存在的概念，有自己的属性，能在知识图谱中作为独立节点。"
            "例如：煤矿、敏感目标、河流、环保设施、法规标准。\n"
            "【实体属性】不能独立存在，必须依附于某个实体。"
            "例如：产能、面积、距离、浓度、服务年限——这些必须属于某个实体。\n\n"
            "判断规则：\n"
            "1. 如果插槽描述的是某个已有实体的特征、参数、指标，它应该是该实体的属性，而非新实体\n"
            "2. 如果插槽代表的是一个可以被独立引用和建立关系的事物，它才应该是新实体\n"
            "3. 例如「矿区面积」不是实体，它是「矿区」实体的属性；「敏感目标」是实体，因为它可以被独立引用\n"
            "4. 合并语义相近的插槽（如「占地面积」和「矿区面积」合并为一个属性）\n"
            "5. 严格按 JSON 数组格式输出"
        )

        user_prompt = (
            f"## 行业领域: {domain_name}\n\n"
            f"## 已有实体结构:\n{existing_text}\n\n"
            f"## 未识别插槽列表:\n{slots_text}\n\n"
            "## 输出要求:\n"
            "对每个插槽判断它应该是新实体还是已有实体的属性补充，输出 JSON 数组：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "suggestion_type": "new_entity",\n'
            '    "entity_key": "snake_case_key",\n'
            '    "name_cn": "实体中文名",\n'
            '    "category": "所属分类",\n'
            '    "value_type": "String|Numeric|Boolean|Date",\n'
            '    "unit": "单位（如有）",\n'
            '    "description": "实体含义描述",\n'
            '    "synonyms": ["别名1", "别名2"],\n'
            '    "confidence": 0.8,\n'
            '    "is_list_type": false,\n'
            '    "properties": []\n'
            "  },\n"
            "  {\n"
            '    "suggestion_type": "add_property",\n'
            '    "target_entity_key": "已有实体的 entity_key",\n'
            '    "target_entity_name": "已有实体名称",\n'
            '    "proposed_property": {\n'
            '      "key": "prop_key",\n'
            '      "name_cn": "属性中文名",\n'
            '      "value_type": "String|Numeric",\n'
            '      "description": "属性说明"\n'
            "    },\n"
            '    "confidence": 0.8\n'
            "  }\n"
            "]\n"
            "```\n"
            "只返回 JSON 数组，不要有其他内容。"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_entity_proposal_response(self, response_text: str) -> list[dict[str, Any]]:
        """解析 LLM 实体建议响应"""
        import json

        raw = response_text.strip()
        # 处理 markdown 代码块
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [line for line in lines[1:] if not line.strip().startswith("```")]
            raw = "\n".join(lines)

        # 提取 JSON 数组
        json_match = re.search(r"\[[\s\S]*\]", raw)
        if not json_match:
            logger.warning(f"无法从实体建议响应中提取 JSON: {response_text[:500]}")
            return []

        try:
            result = json.loads(json_match.group())
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"实体建议 JSON 解析失败: {e}")
            return []

    async def _get_existing_entity_names(self, domain_code: str) -> list[str]:
        """获取指定领域下现有实体名称列表"""
        try:
            from yuxi.repositories.domain_entity_repository import DomainEntityRepository

            repo = DomainEntityRepository()
            entities = await repo.list_all(domain_code=domain_code)
            return [e.get("name_cn", "") for e in entities if e.get("name_cn")]
        except Exception:
            return []

    async def _get_existing_entities_full(self, domain_code: str) -> list[dict]:
        """获取指定领域下所有实体的完整结构（含属性、同义词）"""
        try:
            from yuxi.repositories.domain_entity_repository import DomainEntityRepository

            repo = DomainEntityRepository()
            return await repo.list_all(domain_code=domain_code)
        except Exception:
            return []


def get_domain_factory_service() -> DomainFactoryService:
    """获取 DomainFactoryService 单例"""
    return DomainFactoryService()


def _build_form_schema(variables: list[dict[str, Any]], snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """根据实体变量列表构建表单字段列表，带上 AI 建议值和置信度"""
    if not variables:
        return []

    form_schema = []
    for var in variables:
        key = var.get("key", "")
        value = None
        confidence = None
        warning = None

        if snapshot and isinstance(snapshot, dict):
            value = snapshot.get(key)
            confidence = snapshot.get(f"_confidence_{key}")
            warning = snapshot.get(f"_warning_{key}")

        form_schema.append(
            {
                "key": key,
                "label": var.get("label", key),
                "type": var.get("data_type", "string"),
                "widget": var.get("widget", "Input"),
                "unit": var.get("unit", ""),
                "group": var.get("group", ""),
                "required": var.get("required", False),
                "prompt": var.get("prompt", ""),
                "confidence": confidence,
                "warning": warning,
                "suggestion": value,
                "anchor_id": snapshot.get(f"_anchor_{key}") if snapshot else None,
            }
        )
    return form_schema
