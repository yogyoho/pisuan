"""Domain Factory Service - 领域知识工厂服务层"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


DEFAULT_SCHEMA: dict[str, Any] = {
    "variables": [
        {
            "key": "Project_Name",
            "label": "项目名称",
            "data_type": "string",
            "widget": "Input",
            "unit": "",
            "group": "基础信息",
            "required": True,
            "prompt": "提取项目全称",
            "source": "",
            "sample": "",
        },
        {
            "key": "Project_Capacity",
            "label": "设计产能",
            "data_type": "float",
            "widget": "InputNumber",
            "unit": "Mt/a",
            "group": "基础信息",
            "required": True,
            "prompt": '搜索"设计生产能力""产能"等关键词',
            "source": "",
            "sample": "5.0",
        },
        {
            "key": "Project_Type",
            "label": "建设性质",
            "data_type": "string",
            "widget": "Select",
            "unit": "",
            "group": "基础信息",
            "required": True,
            "prompt": '提取"新建/扩建/技改"等描述',
            "source": "",
            "sample": "新建",
        },
        {
            "key": "Eng_Method",
            "label": "开采方法",
            "data_type": "string",
            "widget": "Select",
            "unit": "",
            "group": "工程参数",
            "required": False,
            "prompt": '提取"综采/充填/露天"等开采工艺',
            "source": "",
            "sample": "综采",
        },
        {
            "key": "Eng_Life",
            "label": "服务年限",
            "data_type": "integer",
            "widget": "InputNumber",
            "unit": "a",
            "group": "工程参数",
            "required": False,
            "prompt": '提取"服务年限/设计寿命"等数字',
            "source": "",
            "sample": "25",
        },
        {
            "key": "Spatial_Area",
            "label": "井田面积",
            "data_type": "float",
            "widget": "InputNumber",
            "unit": "km²",
            "group": "空间数据",
            "required": False,
            "prompt": '提取"井田面积/占地面积"等描述',
            "source": "",
            "sample": "",
        },
    ],
    "chapters": [
        {"key": "ch1", "title": "1. 总论"},
        {"key": "ch2", "title": "2. 工程概况"},
        {"key": "ch3", "title": "3. 环境现状与敏感目标"},
        {"key": "ch4", "title": "4. 预测与评价"},
    ],
}


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
        }


class DomainFactoryService:
    """领域知识工厂服务 - 核心业务逻辑"""

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

    def _get_template_matcher(self, domain: str = "coal_mining") -> Any:
        """获取或创建模板匹配器（延迟加载）"""
        if self._template_matcher is not None:
            return self._template_matcher

        try:
            from yuxi.services.template_library import TemplateLibrary
            from yuxi.services.template_matcher import TemplateMatcher

            library = TemplateLibrary()
            templates = library.get_templates_by_domain(domain)
            if not templates:
                templates = library.get_all_templates()

            if templates:
                self._template_library = library
                self._template_matcher = TemplateMatcher(templates)
                logger.info(f"模板匹配器已加载: {len(templates)} 个模板, domain={domain}")
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
            "你是一个负责生成环评模板的专家，请将下方段落泛化为模板，使用双层大括号 {插槽名称} 表示可替换变量。\n\n"
            "重要：插槽命名必须统一使用中文名称，格式为 {中文名称}。\n\n"
            "命名示例：\n"
            "- 项目名称：{项目名称}\n"
            "- 行政区域：{行政区域}\n"
            "- 产能数值：{产能数值}\n"
            "- 产能单位：{产能单位}\n"
            "- 保护目标名称：{保护目标名称}\n\n"
            "需要：\n"
            "1. 给出泛化后的文本（保持原文逻辑结构不变）；\n"
            "2. 列出每个插槽的含义及推荐数据来源；\n"
            '3. 如果段落包含判断逻辑（如"因此"、"所以"、"如果...则"、"当...时"等），提取触发该模板的前提条件；\n'
            "4. 严格只输出 JSON，不要输出任何自然语言解释或前后缀文本；\n"
            "5. 严格禁止输出代码块标记（例如 ```json 或 ```）；\n"
            "6. 插槽名称必须统一使用中文，格式为 {中文名称}。\n\n"
            "文本：\n{content}\n\n"
            "Schema 变量提示：\n{schema_text}\n\n"
            "输出 JSON 结构：\n"
            '{\n'
            '  "generalized": "...包含 {产能数值}{产能单位} ...",\n'
            '  "slots": [\n'
            "     {\n"
            '       "name": "插槽中文名称",\n'
            '       "type": "类型",\n'
            '       "description": "插槽含义描述",\n'
            '       "suggested_source": "推荐数据来源"\n'
            "     }\n"
            "  ],\n"
            '  "condition": "IF (条件表达式) == True",\n'
            '  "metadata": {\n'
            '    "chapter": "{chapter_hint}",\n'
            '    "tags": ["{domain_label}"]\n'
            "  }\n"
            "}"
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
            '{\n'
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
            '{\n'
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

    # ========== Schema ==========

    async def get_schema(self, domain_id: int) -> dict[str, Any]:
        schema = await self.repo.get_schema(domain_id)
        if schema:
            return {
                "variables": schema.variables or [],
                "chapters": schema.chapters or [],
            }
        domain = await self.repo.get_domain_by_id(domain_id)
        if domain:
            return DEFAULT_SCHEMA.copy()
        return {"variables": [], "chapters": []}

    async def save_schema(self, domain_id: int, variables: list, chapters: list) -> dict[str, Any]:
        schema = await self.repo.upsert_schema(domain_id, variables, chapters)
        return schema.to_dict()

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
    ) -> DomainTaskDTO:
        domain = await self.repo.get_domain_by_code(domain_code)
        if not domain:
            raise ValueError(f"Domain not found: {domain_code}")

        task_id = str(uuid.uuid4())
        task = await self.repo.create_task(
            task_id=task_id,
            domain_id=domain.id,
            file_name=file_name,
            storage_path=file_path,
            uploaded_by=uploaded_by,
        )
        task.document_type = document_type
        await self.repo.update_task(task_id, {"document_type": document_type})

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
            from yuxi.plugins.parser.unified import parse_source_to_markdown

            parse_result = await parse_source_to_markdown(file_path)
            raw_markdown = parse_result.markdown
            raw_html = parse_result.html  # HTML 格式，表格以 HTML 保存
            logger.info(f"文档解析完成，Markdown: {len(raw_markdown)} 字符, HTML: {len(raw_html or '')} 字符")

            # 按章节和段落切分文档（传入 HTML 内容用于存储完整表格）
            paragraphs = self._parse_markdown_to_paragraphs(raw_markdown, html_content=raw_html)
            logger.info(f"文档切分完成，共 {len(paragraphs)} 个段落")

            # 模板匹配：对标题段落进行模板匹配，附加 template_id / semantic_routing
            try:
                matcher = service._get_template_matcher()
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
            except Exception as tpl_err:
                logger.warning(f"模板匹配失败（不阻断 ETL）: {tpl_err}")

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
            await context.set_message("文档解析完成，正在提取信息...")

            # ========== 阶段2: 提取结构化数据 (EXTRACTING) ==========
            await service.repo.update_task(task_id, {"status": "EXTRACTING"})

            # 预加载 prompt 模板（一次查询，全流程复用）
            prompt_templates = await service._load_prompt_templates()

            # 获取领域 Schema，并用实体定义增强变量
            schema = await service.get_schema(task.domain_id) if task.domain_id else DEFAULT_SCHEMA
            variables = schema.get("variables", [])

            # 用 entity_meta 增强 Schema 变量：补充 extraction_hint、entity_ref 等字段
            try:
                enhanced_vars = self._entity_adapter.enhance_schema_variables(
                    variables, self._entity_matcher.loader.load()
                )
                if len(enhanced_vars) > len(variables):
                    logger.info(f"实体增强：Schema 变量从 {len(variables)} 增加到 {len(enhanced_vars)}")
                variables = enhanced_vars
            except Exception as e:
                logger.warning(f"实体增强失败，使用原始 Schema: {e}")

            form_data = {}
            if variables:
                try:
                    # 构建提取 Prompt
                    extract_prompt = self._build_extract_prompt(raw_markdown, variables, prompt_template=prompt_templates.get("extract"))
                    logger.info(f"开始 LLM 提取，变量数量: {len(variables)}")

                    # 调用 LLM
                    model = select_model()
                    response = await model.call(extract_prompt)

                    extracted_text = response.content if hasattr(response, "content") else str(response)
                    logger.info(f"LLM 提取响应长度: {len(extracted_text)} 字符")

                    # 解析 LLM 返回的 JSON
                    extracted_data = self._parse_llm_json_response(extracted_text, variables)

                    # 分离置信度和数据
                    confidences = {}
                    for key, value in extracted_data.items():
                        if key.startswith("_confidence_"):
                            confidences[key.replace("_confidence_", "")] = value
                        elif key.startswith("_warning_"):
                            pass  # 警告信息暂不处理
                        elif key.startswith("_anchor_"):
                            pass  # 锚点信息暂不处理
                        else:
                            form_data[key] = value

                    # 添加置信度信息
                    for key, confidence in confidences.items():
                        form_data[f"_confidence_{key}"] = confidence

                    # 保存提取结果
                    await service.repo.update_task(
                        task_id,
                        {
                            "form_schema_snapshot": extracted_data,
                            "base_info": form_data,
                            "ai_confidence": int(sum(confidences.values()) / len(confidences) * 100)
                            if confidences
                            else 75,
                        },
                    )

                    logger.info(f"结构化数据提取完成，提取字段数: {len(form_data)}")
                except Exception as llm_error:
                    # LLM 调用失败，记录错误但继续执行（优雅降级）
                    logger.warning(f"LLM 提取失败，使用默认值继续: {llm_error}")
                    await service.repo.update_task(
                        task_id,
                        {
                            "ai_confidence": 50,
                            "error_message": f"LLM 提取失败: {str(llm_error)}，请人工填写",
                        },
                    )
            else:
                logger.warning("Schema 没有定义变量，跳过提取阶段")
                form_data = {}

            await context.set_progress(55.0, "信息提取完成，正在泛化...")
            await context.set_message("信息提取完成，正在泛化...")

            # ========== 阶段3: 泛化 (GENERALIZING) ==========
            await service.repo.update_task(task_id, {"status": "GENERALIZING"})

            # 获取领域信息用于泛化
            domain = await service.repo.get_domain_by_id(task.domain_id) if task.domain_id else None
            domain_label = domain.name if domain else "通用"

            # 生成全局槽位模板
            try:
                template_payload = await self._generate_template(raw_markdown, form_data)
            except Exception as template_error:
                logger.warning(f"模板生成失败，使用默认值: {template_error}")
                template_payload = {
                    "generalized": raw_markdown[:1000] if raw_markdown else "",
                    "slots": list(form_data.keys()) if form_data else [],
                    "metadata": {"chapter": "", "tags": []},
                }

            # ========== 段落级泛化（参考源系统 pipeline.py）==========
            # 对每个段落逐一调用 LLM 进行泛化，并回写到段落对象中
            variables = schema.get("variables", [])

            try:
                # 获取 Schema 变量列表
                schema_vars = variables if variables else []

                # 对所有段落进行泛化
                paragraph_results = await self.generalize_paragraphs(
                    paragraphs=paragraphs,
                    schema_variables=schema_vars,
                    domain_label=domain_label,
                    max_concurrency=5,
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

                        # 为段落添加泛化字段，前端会读取这些字段展示
                        # 源系统格式：para["template"] 是包含 generalized、slots 等字段的对象
                        para["template"] = {
                            "generalized": gen_result.get("generalized", ""),
                            "original": para.get("content", ""),
                            "slots": raw_slots,
                            "metadata": gen_result.get("metadata", {}),
                        }
                        para["original"] = para.get("content", "")
                        para["generalized"] = gen_result.get("generalized", "")
                        para["slots"] = raw_slots
                        para["metadata"] = gen_result.get("metadata", {})
                        if matched_entities:
                            para["matched_entities"] = matched_entities
                        generalized_count += 1

                logger.info(f"段落级泛化完成: 成功 {generalized_count}/{len(paragraphs)} 个段落")
            except Exception as para_error:
                logger.warning(f"段落级泛化失败: {para_error}")
                # 段落级泛化失败不影响整体流程，继续执行

            await service.repo.update_task(
                task_id,
                {
                    "template_payload": template_payload,
                },
            )

            # 重新保存带有泛化结果的段落（段落级泛化已完成）
            await service.repo.update_task(
                task_id,
                {
                    "source_paragraphs": paragraphs,
                },
            )

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
        section_pattern = re.compile(
            r"^(第[一二三四五六七八九十百千万\d]+章\s*)?第([一二三四五六七八九十百千万\d]+)节\s*(.*)$"
        )

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
                        title_text = potential_title
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
        # 合并前几行的内容作为匹配键
        sample_content = " ".join(markdown_lines[:3])

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

    def _build_extract_prompt(self, markdown_content: str, variables: list, prompt_template: str | None = None) -> list[dict]:
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
                    f"模板生成成功: generalized 长度={len(result.get('generalized', ''))}, slots数量={len(result.get('slots', []))}"
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

    async def generalize_paragraphs(
        self,
        paragraphs: list[dict[str, Any]],
        schema_variables: list[dict[str, Any]],
        domain_label: str = "通用",
        max_concurrency: int = 5,
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
                prompt = self._build_table_generalize_prompt(text, schema_text, chapter_hint, domain_label, prompt_template=template_prompt)
            else:
                # 普通文本段落
                prompt = self._build_text_generalize_prompt(text, schema_text, chapter_hint, domain_label, prompt_template=template_prompt)

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
            prompt = """你是一个负责生成环评模板的专家，请将下方段落泛化为模板，使用双层大括号 {插槽名称} 表示可替换变量。

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
            logger.warning(f"泛化失败 (模型={getattr(model, 'model_name', 'unknown')}, prompt长度={len(prompt)}): {e}")

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

    def _format_schema_variables(self, schema: list[dict[str, Any]]) -> str:
        """格式化 Schema 变量为提示词文本"""
        lines = []
        for item in schema:
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
        schema = await self.get_schema(task.domain_id) if domain else DEFAULT_SCHEMA

        return {
            "id": task.id,
            "file_name": task.file_name,
            "domain": domain.code if domain else None,
            "domain_label": domain.name if domain else None,
            "document_type": task.document_type or "通用",
            "status": task.status,
            "ai_confidence": task.ai_confidence,
            "uploaded_at": utc_isoformat(task.created_at),
            "uploaded_by": task.uploaded_by,
            "reviewer": task.reviewer,
            "committed_at": utc_isoformat(task.committed_at),
            "error_message": task.error_message,
            "schema_snapshot": schema,
            "form_schema": _build_form_schema(schema, task.form_schema_snapshot),
            "base_info": task.base_info or {},
            "structured_data": task.structured_data or {},
            "structured_blocks": task.structured_blocks or [],
            "template": task.template_payload or {},
            "template_metadata": task.template_metadata,
            "source_paragraphs": task.source_paragraphs or [],
            "raw_markdown": task.raw_markdown,
            "raw_html": getattr(task, "raw_html", None),  # HTML 格式的文档内容
            "ingest_task_id": task.ingest_task_id,
            "knowledge_base_id": task.knowledge_base_id,
            "metadata_options": {
                "chapters": [ch.get("title", ch) for ch in schema.get("chapters", [])],
                "tags": ["井工开采", "露天开采", "充填开采", "综采", "综放"],
            },
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
                "structured_data",
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

        try:
            # ========== 阶段1: 准备 (PREPARING) ==========
            await context.set_progress(5.0, "正在准备入库...")
            await context.set_message("正在准备入库...")

            # 更新任务状态为 COMMITTED
            await service.repo.commit_task(task_id, reviewer, ingest_task_id=ingest_task_id)

            # ========== 阶段2: 同步到知识库 (SYNCING) ==========
            await context.set_progress(30.0, "正在同步数据到知识库...")
            await context.set_message("正在同步数据到知识库...")

            # 获取任务详情，包含结构化数据和模板
            task_detail = await service.get_task_detail(task_id)

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

                    # 2. 创建文件记录，直接设为 PARSED 状态
                    kb_instance.files_meta[file_id] = {
                        "file_id": file_id,
                        "database_id": knowledge_base_id,
                        "filename": file_name,
                        "original_filename": file_name,
                        "file_type": "md",
                        "path": f"domain_factory/{task_id}/{file_name}",
                        "minio_url": "",
                        "markdown_file": markdown_url,
                        "status": FileStatus.PARSED,
                        "content_hash": hashstr(ingest_markdown),
                        "size": len(ingest_markdown),
                        "content_type": "domain_factory",
                        "processing_params": {},
                        "is_folder": False,
                        "created_by": reviewer,
                        "created_at": utc_isoformat(),
                    }
                    await kb_instance._persist_file(file_id)

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

                if source_paragraphs:
                    graph_stats = graph_builder.build_knowledge_graph(
                        kb_id=knowledge_base_id or "",
                        doc_id=doc_id,
                        doc_title=task_detail.get("file_name", ""),
                        source_paragraphs=source_paragraphs,
                        domain_label=domain_label,
                        base_info=base_info,
                    )
                    logger.info(f"知识图谱构建完成: {graph_stats}")
                    graph_builder.close()
                else:
                    logger.warning(f"任务 {task_id} 无 source_paragraphs，跳过图谱构建")
            except Exception as e:
                # 图谱构建失败不阻断主流程
                logger.warning(f"知识图谱构建失败（不阻断入库）: {e}")

            if not knowledge_base_id:
                logger.warning(f"任务 {task_id} 未指定目标知识库，跳过入库")

            # ========== 阶段3: 完成 (COMPLETING) ==========
            await context.set_progress(95.0, "正在完成入库...")
            await context.set_message("正在完成入库...")

            # 更新最终状态
            await service.repo.update_task(
                task_id,
                {
                    "status": "COMMITTED",
                    "knowledge_base_id": knowledge_base_id,
                },
            )

            await context.set_progress(100.0, "入库完成")
            await context.set_message("入库完成")

            return {
                "task_id": task_id,
                "status": "COMMITTED",
                "knowledge_base_id": knowledge_base_id,
                "kb_ingested": kb_ingested,
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
                block_type = block.get("type", "")
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

            # 提取父级章节标题
            parent_title = ""
            if section_path and len(section_path) > 1:
                parent_title = str(section_path[-2])

            # 将内容转为纯文本（去除 HTML 标记）
            plain_content = re.sub(r"<[^>]+>", "", content) if content else ""

            # 段落正文 chunk
            if plain_content:
                section_id = para.get("section_id", f"sec_{chunk_idx}")
                chunks.append(
                    {
                        "id": f"{file_id}_chunk_{chunk_idx}",
                        "content": plain_content,
                        "chunk_order_index": chunk_idx,
                        "section_id": section_id,
                        "section_title": title,
                        "parent_section_title": parent_title,
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
                        "parent_section": None,
                        "path": [str(p) for p in section_path] if section_path else [title],
                        "chunk_indexes": [chunk_idx],
                    }
                )
                chunk_idx += 1

            # 泛化模板 chunk（模板单独作为一个 chunk 以提升检索命中率）
            template = para.get("template", {})
            if isinstance(template, dict):
                generalized = template.get("generalized", "")
                if generalized:
                    chunks.append(
                        {
                            "id": f"{file_id}_tmpl_{chunk_idx}",
                            "content": f"泛化模板：{generalized}",
                            "chunk_order_index": chunk_idx,
                            "section_id": para.get("section_id", f"sec_{chunk_idx}"),
                            "section_title": f"{title} - 泛化模板",
                            "parent_section_title": title,
                            "template": template,
                            "slots": template.get("slots"),
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

                # 2. 创建文件记录，直接设为 PARSED 状态
                kb_instance.files_meta[file_id] = {
                    "file_id": file_id,
                    "database_id": knowledge_base_id,
                    "filename": file_name,
                    "original_filename": file_name,
                    "file_type": "md",
                    "path": f"domain_factory/reingest_{task_id}/{file_name}",
                    "minio_url": "",
                    "markdown_file": markdown_url,
                    "status": FileStatus.PARSED,
                    "content_hash": hashstr(ingest_markdown),
                    "size": len(ingest_markdown),
                    "content_type": "domain_factory",
                    "processing_params": {},
                    "is_folder": False,
                    "created_at": utc_isoformat(),
                }
                await kb_instance._persist_file(file_id)

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

                if source_paragraphs:
                    graph_stats = graph_builder.build_knowledge_graph(
                        kb_id=knowledge_base_id or "",
                        doc_id=doc_id,
                        doc_title=task_detail.get("file_name", ""),
                        source_paragraphs=source_paragraphs,
                        domain_label=domain_label,
                        base_info=base_info,
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
        return updated_task.to_summary_dict() if updated_task else None

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

    async def get_contexts(self) -> dict[str, Any]:
        return {
            "domains": [
                {"id": "global", "code": "global", "name": "通用（Global）"},
                {"id": "coal", "code": "coal", "name": "煤炭采选业"},
                {"id": "chem", "code": "chem", "name": "石油化工业"},
                {"id": "transport", "code": "transport", "name": "交通运输业"},
            ],
            "report_types": [
                {"id": "feasibility", "code": "feasibility_report", "name": "可行性研究报告"},
                {"id": "eia", "code": "eia_report", "name": "环境影响评价报告"},
                {"id": "stand-alone", "code": "stand_alone_report", "name": "独立篇章"},
            ],
        }

    async def get_context_sections(self, domain_code: str, report_type: str) -> dict[str, Any]:
        ctx = await self.repo.get_context(domain_code, report_type)
        if ctx and ctx.section_tree_json:
            return {"sections": ctx.section_tree_json}
        return {
            "sections": [
                {
                    "code": "SEC_GENERAL_OVERVIEW",
                    "title": "第一章 总论",
                    "section_id": "SEC_GENERAL_OVERVIEW",
                    "children": [],
                },
                {
                    "code": "SEC_PROJECT_ENGINEERING",
                    "title": "第二章 工程分析",
                    "section_id": "SEC_PROJECT_ENGINEERING",
                    "children": [],
                },
                {
                    "code": "SEC_IMPACT_PREDICTION",
                    "title": "第三章 环境影响预测",
                    "section_id": "SEC_IMPACT_PREDICTION",
                    "children": [],
                },
            ]
        }

    async def update_context_sections(self, domain_code: str, report_type: str, sections: list) -> dict[str, Any]:
        ctx = await self.repo.get_or_create_context(domain_code, report_type)
        ctx.section_tree_json = sections
        await self.repo.update_context(domain_code, report_type, section_tree=sections)
        return {"sections": sections}

    async def get_context_section_rule(self, domain_code: str, report_type: str, section_code: str) -> dict[str, Any]:
        ctx = await self.repo.get_context(domain_code, report_type)
        if ctx and ctx.routing_rules_json:
            rule = ctx.routing_rules_json.get(section_code, {})
        else:
            rule = {
                "inherit_mode": "inherit",
                "base_keywords": [],
                "domain_keyword_groups": [],
                "skill_id": None,
                "schema_diff": {},
            }
        return {"rule": rule}

    async def update_context_section_rule(
        self, domain_code: str, report_type: str, section_code: str, rule: dict[str, Any]
    ) -> dict[str, Any]:
        ctx = await self.repo.get_or_create_context(domain_code, report_type)
        routing_rules = dict(ctx.routing_rules_json or {})
        routing_rules[section_code] = rule
        await self.repo.update_context(domain_code, report_type, routing_rules=routing_rules)
        return {"rule": rule}

    # ========== Saved Sections ==========

    async def get_saved_sections(
        self, domain_id: str | None = None, report_type_id: str | None = None
    ) -> dict[str, Any]:
        sections = await self.repo.list_saved_sections(domain_id, report_type_id)
        return {"items": sections}

    async def get_saved_section_detail(self, section_id: str) -> dict[str, Any] | None:
        section = await self.repo.get_saved_section(section_id)
        if not section:
            return None
        return section.to_dict()

    async def import_saved_section(self, section_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        section = await self.repo.get_saved_section(section_id)
        if not section:
            return {"message": "Section not found", "imported_sections": 0, "imported_rules": 0}
        domain_code = (context or {}).get("domain_id", section.domain_id)
        report_type = (context or {}).get("report_type_id", section.report_type_id)
        if domain_code and report_type:
            await self.repo.update_context_sections(domain_code, report_type, section.section_tree_json or [])
        return {
            "message": "Import successful",
            "imported_sections": len(section.section_tree_json or []),
            "imported_rules": 0,
        }

    # ========== Section Routing ==========

    async def get_context_sections_tree(
        self, domain_code: str, report_type: str, is_template: bool = True
    ) -> list[dict[str, Any]]:
        """获取章节树"""
        ctx = await self.repo.get_context(domain_code, report_type)
        if ctx and ctx.section_tree_json:
            return ctx.section_tree_json

        # 返回默认章节结构
        return [
            {
                "code": "SEC_GENERAL_OVERVIEW",
                "title": "第一章 总论",
                "section_path": "1",
                "level": 1,
                "children": [
                    {
                        "code": "SEC_GENERAL_1_1",
                        "title": "1.1 项目背景",
                        "section_path": "1.1",
                        "level": 2,
                        "children": [],
                    },
                    {
                        "code": "SEC_GENERAL_1_2",
                        "title": "1.2 编制依据",
                        "section_path": "1.2",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
            {
                "code": "SEC_PROJECT_ENGINEERING",
                "title": "第二章 工程分析",
                "section_path": "2",
                "level": 1,
                "children": [],
            },
            {"code": "SEC_ENV_STATUS", "title": "第三章 环境现状", "section_path": "3", "level": 1, "children": []},
            {
                "code": "SEC_IMPACT_PREDICTION",
                "title": "第四章 环境影响预测",
                "section_path": "4",
                "level": 1,
                "children": [],
            },
        ]

    async def get_section_detail(self, section_id: int) -> dict[str, Any] | None:
        """获取章节详情"""
        section = await self.repo.get_section_by_id(section_id)
        if not section:
            return None
        return (
            section.to_dict()
            if hasattr(section, "to_dict")
            else {
                "id": section.id,
                "code": section.code,
                "title": section.title,
                "section_path": section.section_path,
                "level": section.level,
                "domain": section.domain,
                "report_type": section.report_type,
                "standard_code": getattr(section, "standard_code", None),
                "match_confidence": getattr(section, "match_confidence", None),
            }
        )

    async def create_section(
        self,
        code: str,
        title: str,
        section_path: str,
        level: int | None,
        domain: str,
        report_type: str,
        parent_id: int | None = None,
        standard_code: str | None = None,
        match_confidence: int | None = None,
        sort_order: int = 0,
        template_data: dict[str, Any] | None = None,
        context_routing: dict[str, Any] | None = None,
        writing_guidance: dict[str, Any] | None = None,
        entity_bindings: list[dict[str, Any]] | None = None,
        user: str | None = None,
    ) -> dict[str, Any]:
        """创建章节"""
        # 计算层级
        if level is None:
            level = section_path.count(".") + 1

        section = await self.repo.create_section(
            code=code,
            title=title,
            section_path=section_path,
            level=level,
            domain=domain,
            report_type=report_type,
            parent_id=parent_id,
            standard_code=standard_code,
            match_confidence=match_confidence,
            sort_order=sort_order,
            template_data=template_data,
            context_routing=context_routing,
            writing_guidance=writing_guidance,
            entity_bindings=entity_bindings,
        )
        return (
            section.to_dict()
            if hasattr(section, "to_dict")
            else {
                "id": section.id,
                "code": code,
                "title": title,
                "section_path": section_path,
                "level": level,
            }
        )

    async def update_section(
        self,
        section_id: int,
        title: str | None = None,
        section_path: str | None = None,
        level: int | None = None,
        parent_id: int | None = None,
        standard_code: str | None = None,
        match_confidence: int | None = None,
        sort_order: int | None = None,
        template_data: dict[str, Any] | None = None,
        context_routing: dict[str, Any] | None = None,
        writing_guidance: dict[str, Any] | None = None,
        entity_bindings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """更新章节"""
        section = await self.repo.update_section(
            section_id=section_id,
            title=title,
            section_path=section_path,
            level=level,
            parent_id=parent_id,
            standard_code=standard_code,
            match_confidence=match_confidence,
            sort_order=sort_order,
            template_data=template_data,
            context_routing=context_routing,
            writing_guidance=writing_guidance,
            entity_bindings=entity_bindings,
        )
        if not section:
            return None
        return section.to_dict() if hasattr(section, "to_dict") else {"id": section_id}

    async def delete_section(self, section_id: int) -> bool:
        """删除章节"""
        return await self.repo.delete_section(section_id)

    async def batch_get_sections(self, section_ids: list[int]) -> dict[int, dict[str, Any]]:
        """批量获取章节"""
        sections = {}
        for section_id in section_ids:
            section = await self.repo.get_section_by_id(section_id)
            if section:
                sections[section_id] = section.to_dict() if hasattr(section, "to_dict") else {"id": section_id}
        return sections

    async def get_section_standard_codes(self, section_id: int) -> list[dict[str, Any]]:
        """获取章节绑定的 StandardCodes"""
        section = await self.repo.get_section_by_id(section_id)
        if not section:
            return []
        codes = []
        if hasattr(section, "standard_code") and section.standard_code:
            codes.append({"standard_code": section.standard_code, "mount_type": "direct"})
        return codes

    async def bind_section_standard_code(self, section_id: int, standard_code: str, mount_type: str = "direct") -> bool:
        """绑定 StandardCode 到章节"""
        section = await self.repo.update_section(section_id, standard_code=standard_code)
        return section is not None

    async def unbind_section_standard_code(self, section_id: int, standard_code: str) -> bool:
        """解绑 StandardCode"""
        section = await self.repo.update_section(section_id, standard_code=None)
        return section is not None

    async def match_standard_codes(
        self,
        title: str,
        section_path: str,
        level: int,
        content_sample: str | None = None,
    ) -> list[dict[str, Any]]:
        """匹配 StandardCodes"""
        # 获取所有 StandardCode 映射
        mappings = await self.repo.list_standard_code_mappings()
        matches = []

        title_lower = title.lower()
        for mapping in mappings:
            standard_code = mapping.get("standard_code", "")
            name = mapping.get("name", "")
            desc = mapping.get("description", "") or ""

            # 简单的关键词匹配
            score = 0
            keywords = []

            # 检查标题关键词
            for keyword in [standard_code.lower(), name.lower(), desc.lower()]:
                if keyword and keyword in title_lower:
                    score += 30
                    keywords.append(keyword[:20])

            # 检查路径层级匹配
            if level <= 2 and "总论" in title:
                if "OVERVIEW" in standard_code.upper() or "GENERAL" in standard_code.upper():
                    score += 20
            elif level == 2 and "工程" in title:
                if "ENGINEERING" in standard_code.upper():
                    score += 20

            if score > 0:
                matches.append(
                    {
                        "standard_code": standard_code,
                        "name": name,
                        "confidence": min(score, 100),
                        "match_reason": f"关键词匹配: {', '.join(keywords[:3])}",
                        "priority": mapping.get("priority", 50),
                    }
                )

        # 按置信度排序
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        return matches[:5]

    async def export_sections(self, domain: str, report_type: str) -> dict[str, Any]:
        """导出章节配置"""
        from datetime import datetime

        sections = await self.get_context_sections_tree(domain, report_type)
        return {
            "metadata": {
                "domain": domain,
                "report_type": report_type,
                "version": "1.0.0",
                "exported_at": datetime.utcnow().isoformat(),
                "section_count": len(sections),
            },
            "sections": sections,
        }

    async def import_sections(self, domain: str, report_type: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
        """导入章节配置"""
        await self.update_context_sections(domain, report_type, sections)
        return {"imported_count": len(sections), "skipped_count": 0, "conflicts": []}

    # ========== Standard Code Mapping ==========

    async def get_standard_code_mapping(self) -> dict[str, Any]:
        items = await self.repo.list_standard_code_mappings()
        return {"items": items}

    async def update_standard_code_mapping(self, items: list[dict[str, Any]]) -> bool:
        return await self.repo.upsert_standard_code_mappings(items)


def get_domain_factory_service() -> DomainFactoryService:
    """获取 DomainFactoryService 单例"""
    return DomainFactoryService()


def _build_form_schema(schema: dict[str, Any], snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """根据 Schema 构建表单字段列表，带上 AI 建议值和置信度"""
    variables = schema.get("variables", [])
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
