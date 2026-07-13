import asyncio
import os
import re
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from yuxi.agents.toolkits.registry import ToolExtraMetadata, _all_tool_instances, _extra_registry, tool
from yuxi.repositories.domain_factory_repository import (
    DomainFactoryRepository,
    _normalize_domain,
    _normalize_report_type,
)
from yuxi.utils import logger
from yuxi.utils.paths import (
    CONVERSATION_HISTORY_DIR_NAME,
    LARGE_TOOL_RESULTS_DIR_NAME,
    OUTPUTS_DIR_NAME,
    UPLOADS_DIR_NAME,
    VIRTUAL_PATH_OUTPUTS,
    WORKSPACE_DIR_NAME,
)
from yuxi.utils.question_utils import normalize_questions

# Lazy initialization for TavilySearch (only when API key is available)
_tavily_search_instance = None

_PRESENT_ARTIFACTS_INTERNAL_DIR_NAMES = frozenset(
    {CONVERSATION_HISTORY_DIR_NAME, LARGE_TOOL_RESULTS_DIR_NAME, "large_tool_history"}
)
_OCR_PARSE_ALLOWED_DIRS = frozenset({WORKSPACE_DIR_NAME, UPLOADS_DIR_NAME, OUTPUTS_DIR_NAME})
_OCR_OUTPUT_DIR_NAME = "ocr"
_OCR_PREVIEW_LIMIT = 1200
_SAFE_OUTPUT_STEM_RE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


def _create_tavily_search():
    """Create and register TavilySearch tool with metadata."""
    global _tavily_search_instance
    if _tavily_search_instance is None:
        from langchain_tavily import TavilySearch

        _tavily_search_instance = TavilySearch()

    return _tavily_search_instance


# 注册 TavilySearch 工具（延迟初始化）
def _register_tavily_tool():
    """Register TavilySearch tool with extra metadata."""
    tavily_instance = _create_tavily_search()
    # 手动注册到全局注册表
    _extra_registry["tavily_search"] = ToolExtraMetadata(
        category="buildin",
        tags=["搜索"],
        display_name="Tavily 网页搜索",
    )
    # 添加到工具实例列表
    _all_tool_instances.append(tavily_instance)


# 模块加载时注册
if os.getenv("TAVILY_API_KEY"):
    try:
        _register_tavily_tool()
    except Exception as e:
        logger.warning(f"Failed to register TavilySearch tool: {e}")


class PresentArtifactsInput(BaseModel):
    """Expose artifact files to the frontend after the agent finishes."""

    filepaths: list[str] = Field(
        description=f"需要展示给用户的文件绝对路径列表，只允许位于 {VIRTUAL_PATH_OUTPUTS} 下，且不能是内部运行文件"
    )


def _normalize_presented_artifact_path(filepath: str, runtime: ToolRuntime) -> str:
    from yuxi.agents.backends.sandbox.paths import (
        VIRTUAL_PATH_PREFIX,
        ensure_thread_dirs,
        resolve_virtual_path,
        sandbox_outputs_dir,
    )

    outputs_virtual_prefix = f"{VIRTUAL_PATH_PREFIX}/outputs"
    runtime_context = runtime.context
    thread_id = getattr(runtime_context, "file_thread_id", None) or getattr(runtime_context, "thread_id", None)
    if not thread_id:
        raise ValueError("当前运行时缺少 thread_id")
    uid = getattr(runtime_context, "uid", None)
    if not uid:
        raise ValueError("当前运行时缺少 uid")

    ensure_thread_dirs(thread_id, str(uid))
    outputs_dir = sandbox_outputs_dir(thread_id).resolve()
    normalized_input = str(filepath or "").strip()
    if not normalized_input:
        raise ValueError("文件路径不能为空")

    stripped = normalized_input.lstrip("/")
    virtual_prefix = VIRTUAL_PATH_PREFIX.lstrip("/")
    if stripped == virtual_prefix or stripped.startswith(f"{virtual_prefix}/"):
        actual_path = resolve_virtual_path(thread_id, normalized_input, uid=str(uid))
    else:
        actual_path = Path(normalized_input).expanduser().resolve()

    if not actual_path.exists() or not actual_path.is_file():
        raise ValueError(f"文件不存在或不是普通文件: {normalized_input}")

    try:
        relative_path = actual_path.relative_to(outputs_dir)
    except ValueError as exc:
        raise ValueError(f"只允许展示 {outputs_virtual_prefix}/ 下的文件: {normalized_input}") from exc

    if relative_path.parts and relative_path.parts[0] in _PRESENT_ARTIFACTS_INTERNAL_DIR_NAMES:
        raise ValueError(f"不允许展示工具调用阶段文件: {outputs_virtual_prefix}/{relative_path.as_posix()}")

    return f"{outputs_virtual_prefix}/{relative_path.as_posix()}"


PRESENT_ARTIFACTS_DESCRIPTION = f"""
将已经生成好的结果文件展示给用户。

使用场景：
1. 你已经在 `{VIRTUAL_PATH_OUTPUTS}` 下写好了最终结果文件
2. 你希望前端在对话结束后显示这些结果文件卡片
3. 这些文件需要支持下载或预览

注意事项：
1. 只能传入 `{VIRTUAL_PATH_OUTPUTS}` 下的文件
2. 不要传入中间过程文件，只有真正需要给用户看的结果文件才调用
3. 不要传入工具调用阶段文件，例如：
   - `{VIRTUAL_PATH_OUTPUTS}/{LARGE_TOOL_RESULTS_DIR_NAME}`
   - `{VIRTUAL_PATH_OUTPUTS}/{CONVERSATION_HISTORY_DIR_NAME}`
4. 可以一次传多个文件
"""


@tool(
    category="buildin",
    tags=["文件", "交付物"],
    display_name="展示交付物",
    description=PRESENT_ARTIFACTS_DESCRIPTION,
    args_schema=PresentArtifactsInput,
)
def present_artifacts(
    filepaths: list[str],
    runtime: ToolRuntime,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """登记当前线程 outputs 目录下的交付物文件，使前端在对话结束后展示给用户。"""
    try:
        normalized_paths = [_normalize_presented_artifact_path(filepath, runtime) for filepath in filepaths]
    except ValueError as exc:
        return Command(update={"messages": [ToolMessage(content=f"Error: {exc}", tool_call_id=tool_call_id)]})

    return Command(
        update={
            "artifacts": normalized_paths,
            "messages": [ToolMessage(content="已将交付物展示给用户", tool_call_id=tool_call_id)],
        }
    )


class OcrParseFileInput(BaseModel):
    """Parse a sandbox file with OCR and save the Markdown result."""

    file_path: str = Field(description="需要 OCR 解析的沙盒虚拟路径，必须位于 /home/gem/user-data 下")
    ocr_engine: str | None = Field(default=None, description="可选 OCR 引擎；省略时使用系统默认 OCR 引擎")


OCR_PARSE_FILE_DESCRIPTION = f"""
将沙盒中的 PDF 或图片文件解析为 Markdown 文本，并把结果保存为文件。

使用场景：
1. 用户上传了 PDF/图片附件，需要提取其中的文字内容
2. 工作区、uploads 或 outputs 下已有文件，需要转成可读取的 Markdown
3. 解析结果较长，后续应使用 read_file 读取保存后的 Markdown 文件

注意事项：
1. file_path 必须是 /home/gem/user-data 下的虚拟路径
2. 只允许读取 workspace、uploads、outputs 下的普通文件
3. 解析结果会写入 {VIRTUAL_PATH_OUTPUTS}/{_OCR_OUTPUT_DIR_NAME}/
4. 工具只返回结果文件路径和短预览，不直接返回完整 OCR 文本
5. 如需在前端展示结果文件，请再调用 present_artifacts
"""


@tool(
    category="buildin",
    tags=["文件", "OCR"],
    display_name="OCR 解析文件",
    description=OCR_PARSE_FILE_DESCRIPTION,
    args_schema=OcrParseFileInput,
)
async def ocr_parse_file(file_path: str, runtime: ToolRuntime, ocr_engine: str | None = None) -> dict:
    """Parse a sandbox file with OCR, persist Markdown output, and return only a short result summary."""
    from yuxi.agents.backends.sandbox.paths import virtual_path_for_thread_file
    from yuxi.knowledge.parser import Parser

    file_thread_id, uid, actual_path = _resolve_ocr_source_path(file_path, runtime)
    engine = _resolve_ocr_engine(ocr_engine)
    markdown = await Parser.aparse(str(actual_path), params={"ocr_engine": engine})

    output_path = _next_ocr_output_path(file_thread_id, actual_path)
    output_path.write_text(markdown, encoding="utf-8")
    parsed_path = virtual_path_for_thread_file(file_thread_id, output_path, uid=uid)
    source_virtual_path = virtual_path_for_thread_file(file_thread_id, actual_path, uid=uid)
    preview, truncated = _ocr_preview(markdown)

    return {
        "source_path": source_virtual_path,
        "parsed_path": parsed_path,
        "ocr_engine": engine,
        "char_count": len(markdown),
        "preview": preview,
        "truncated": truncated,
    }


def _resolve_ocr_source_path(file_path: str, runtime: ToolRuntime) -> tuple[str, str, Path]:
    """Resolve a sandbox virtual path to a host file inside the Agent-visible user-data roots."""
    from yuxi.agents.backends.sandbox.paths import get_virtual_path_prefix, resolve_virtual_path

    file_thread_id, uid = _resolve_runtime_file_scope(runtime)

    normalized_input = str(file_path or "").strip()
    if not normalized_input:
        raise ValueError("文件路径不能为空")

    virtual_prefix = get_virtual_path_prefix().rstrip("/")
    clean_virtual_path = "/" + normalized_input.lstrip("/")
    if clean_virtual_path != virtual_prefix and not clean_virtual_path.startswith(f"{virtual_prefix}/"):
        raise ValueError(f"只允许解析 {virtual_prefix} 下的沙盒虚拟路径")

    relative_path = clean_virtual_path[len(virtual_prefix) :].lstrip("/")
    namespace = Path(relative_path).parts[0] if relative_path else ""
    if namespace not in _OCR_PARSE_ALLOWED_DIRS:
        allowed = ", ".join(f"{virtual_prefix}/{item}" for item in sorted(_OCR_PARSE_ALLOWED_DIRS))
        raise ValueError(f"只允许解析 {allowed} 下的文件")

    try:
        actual_path = resolve_virtual_path(file_thread_id, clean_virtual_path, uid=uid)
    except ValueError as exc:
        raise ValueError(f"只允许解析 {virtual_prefix} 下的沙盒虚拟路径") from exc
    if not actual_path.exists():
        raise ValueError(f"文件不存在: {clean_virtual_path}")
    if not actual_path.is_file():
        raise ValueError(f"路径不是普通文件: {clean_virtual_path}")

    return file_thread_id, uid, actual_path


def _resolve_runtime_file_scope(runtime: ToolRuntime) -> tuple[str, str]:
    """Read the thread and user scope needed for sandbox path mapping from ToolRuntime."""
    thread_id = _runtime_scope_value(runtime, "file_thread_id") or _runtime_scope_value(runtime, "thread_id")
    uid = _runtime_scope_value(runtime, "uid")
    if not thread_id:
        raise ValueError("当前运行时缺少 thread_id")
    if not uid:
        raise ValueError("当前运行时缺少 uid")
    return thread_id, uid


def _runtime_scope_value(runtime: ToolRuntime, key: str) -> str | None:
    """Look up a runtime scope value from LangGraph config, context, or state."""
    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    sources = (
        configurable if isinstance(configurable, dict) else {},
        getattr(runtime, "context", None),
        getattr(runtime, "state", None) if isinstance(getattr(runtime, "state", None), dict) else {},
    )
    for source in sources:
        value = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_ocr_engine(ocr_engine: str | None) -> str:
    """Validate the requested OCR engine, falling back to the system default when omitted."""
    from yuxi import config
    from yuxi.knowledge.parser.factory import DocumentProcessorFactory

    engine = str(ocr_engine or config.default_ocr_engine).strip() or config.default_ocr_engine
    allowed = {"disable", *DocumentProcessorFactory.get_available_processors()}
    if engine not in allowed:
        raise ValueError(f"不支持的 OCR 引擎: {engine}")
    return engine


def _next_ocr_output_path(thread_id: str, source_path: Path) -> Path:
    """Choose a non-conflicting Markdown output path under the thread outputs/ocr directory."""
    from yuxi.agents.backends.sandbox.paths import sandbox_outputs_dir

    output_dir = sandbox_outputs_dir(thread_id) / _OCR_OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = _safe_ocr_output_stem(source_path)
    candidate = output_dir / f"{base_name}.md"
    index = 1
    while candidate.exists():
        candidate = output_dir / f"{base_name}-{index}.md"
        index += 1
    return candidate


def _safe_ocr_output_stem(source_path: Path) -> str:
    """Build a filesystem-friendly output filename stem from the source file name."""
    stem = source_path.stem.strip() or "ocr_result"
    safe_stem = _SAFE_OUTPUT_STEM_RE.sub("_", stem).strip("._-")
    return safe_stem or "ocr_result"


def _ocr_preview(markdown: str) -> tuple[str, bool]:
    """Return the short preview included in the tool result and whether it was truncated."""
    if len(markdown) <= _OCR_PREVIEW_LIMIT:
        return markdown, False
    return markdown[:_OCR_PREVIEW_LIMIT].rstrip(), True


ASK_USER_QUESTION_DESCRIPTION = """
在执行过程中，当你需要用户做决定或补充需求时，使用这个工具向用户提问。

适用场景：
1. 收集用户偏好或需求（例如风格、范围、优先级）
2. 澄清模糊指令（存在多种合理解释时）
3. 在实现过程中让用户选择方案方向
4. 在有明显权衡时让用户做取舍

使用规范：
1. questions 提供 1-5 个问题，每项包含：question、options、multi_select、allow_other
2. 每个问题的 options 提供 2-5 个有区分度的选项，每项包含 label 和 value
3. 若有推荐选项：把推荐项放在第一位，并在 label 末尾加 "(Recommended)"
4. 若需要多选：将该问题的 multi_select 设为 true
5. allow_other 通常保持 true，用户可通过 Other 输入自定义答案

注意事项：
1. 不要用这个工具询问“是否继续执行”“计划是否准备好”这类流程控制问题
2. 不要在信息已充分、无需用户决策时滥用该工具
3. 先基于现有上下文自行决策，只有关键不确定性时才提问

返回结果：
answer 为 object，格式为 {question_id: answer}。
其中 answer 可能是 string（单选）、list（多选）或 object（Other 文本）。
"""


@tool(
    category="buildin",
    tags=["交互"],
    display_name="向用户提问",
    description=ASK_USER_QUESTION_DESCRIPTION,
)
def ask_user_question(
    questions: Annotated[
        list[dict] | str | None,
        "问题列表，每项格式 {question, options, multi_select, allow_other, question_id(optional)}",
    ] = None,
) -> dict:
    """向用户发起问题并等待回答。"""
    # 解析 questions 参数：如果是字符串，尝试解析为 JSON
    if isinstance(questions, str):
        try:
            import json

            questions = json.loads(questions)
            logger.debug(f"Parsed string questions to list: {questions}")
        except Exception as e:
            logger.error(f"Failed to parse questions string: {e}, using None")
            questions = None

    normalized_questions = normalize_questions(questions or [])

    if not normalized_questions:
        raise ValueError("questions 至少需要包含一个有效问题")

    interrupt_payload = {
        "questions": normalized_questions,
        "source": "ask_user_question",
    }
    answer = interrupt(interrupt_payload)

    return {
        "questions": normalized_questions,
        "answer": answer,
    }


GET_CHAPTER_OUTLINE_DESCRIPTION = """
取某章节的结构化大纲（入库→写作的桥产出）。
返回 purpose/overview/key_points/content_requirements/regulations/entity_bindings/
expected_tables/expected_charts/expected_formulas/expected_figures/writing_example/writing_hints。
writer 写每章前调用此工具获取本章编写蓝图；compliance-checker 用它取 regulations。
canonical_chapter_key 是归一化章节名（如"地下水环境影响预测"），不是原始章节号。
domain/report_type 必须使用数据字典中的 code（用 list_report_types 查询合法值）。
"""


@tool(
    category="buildin",
    tags=["知识工厂", "大纲"],
    display_name="取章节大纲",
    description=GET_CHAPTER_OUTLINE_DESCRIPTION,
)
async def get_chapter_outline(domain: str, report_type: str, canonical_chapter_key: str) -> dict:
    """获取指定章节的结构化大纲。"""
    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)
    repo = DomainFactoryRepository()
    out = await repo.get_outline(domain, report_type, canonical_chapter_key)
    if out:
        return out
    types = await repo.list_report_types()
    valid_codes = [t["code"] for t in types]
    return {
        "error": f"未找到章节大纲: {domain}/{report_type}/{canonical_chapter_key}",
        "hint": f"该 domain 合法 report_type: {valid_codes}（请用 list_report_types 确认数据字典 code）",
    }


LIST_REPORT_TYPES_DESCRIPTION = """
查询数据字典 report_types，返回指定领域可用的报告类型 code 列表。
domain/report_type code 是数据库精确匹配字段，get_chapter_outline / get_templates / create_report 等工具都依赖正确的 code。
"""


@tool(
    category="buildin",
    tags=["知识工厂", "数据字典"],
    display_name="查报告类型",
    description=LIST_REPORT_TYPES_DESCRIPTION,
)
async def list_report_types(domain: str) -> list[dict]:
    """查询数据字典中指定领域的报告类型 code。"""
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    domain = _normalize_domain(domain)
    repo = DomainEntityRepository()
    return await repo.list_report_types(domain)


LIST_CHAPTER_KEYS_DESCRIPTION = """
列出某领域+报告类型下所有已入库的章节归一化名（canonical_chapter_key）。
调用 get_chapter_outline / get_templates 前先用此工具获取合法的 canonical_chapter_key 列表，避免猜测导致空查询。
"""


@tool(
    category="buildin",
    tags=["知识工厂", "大纲"],
    display_name="列出章节",
    description=LIST_CHAPTER_KEYS_DESCRIPTION,
)
async def list_chapter_keys(domain: str, report_type: str) -> list[str]:
    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)
    """列出指定领域+报告类型下所有已入库的 canonical_chapter_key。"""
    repo = DomainFactoryRepository()
    return await repo.list_chapter_keys(domain, report_type)


GET_TEMPLATES_DESCRIPTION = """
取某章节（或全部）的结构化段落模板（来自 learned_templates）。
返回 [{generalized, slots, chapter, sample_original, standard_code}]。
template-recommender 用它推荐段落模板；slot-filler 用它取插槽定义。
domain/report_type 必须使用数据字典中的 code（用 list_report_types 查询合法值）。
"""


@tool(
    category="buildin",
    tags=["知识工厂", "模板"],
    display_name="取段落模板",
    description=GET_TEMPLATES_DESCRIPTION,
)
async def get_templates(domain: str, report_type: str, canonical_chapter_key: str | None = None) -> list[dict]:
    """获取结构化段落模板。"""
    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)
    repo = DomainFactoryRepository()
    return await repo.list_learned_templates_by_key(domain, report_type, canonical_chapter_key)


CREATE_REPORT_DESCRIPTION = """
为一篇环评报告创建持久化报告对象。后续所有写作(章节/参数/装配)都针对 report_id 操作,
支持跨会话点状写作。一次创建,多会话复用。
domain/report_type 必须使用数据字典中的 code（用 list_report_types 查询合法值）。
"""


@tool(
    category="buildin",
    tags=["报告"],
    display_name="创建报告",
    description=CREATE_REPORT_DESCRIPTION,
)
async def create_report(thread_id: str, title: str, domain: str, report_type: str, kb_id: str) -> dict:
    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)
    """为一篇报告创建持久化记录,返回 report_id。"""
    repo = DomainFactoryRepository()
    return await repo.create_report(
        thread_id=thread_id,
        title=title,
        domain_code=domain,
        report_type_code=report_type,
        kb_id=kb_id,
        created_by=None,
    )


GET_REPORT_DESCRIPTION = """
取报告全景快照:status + PPS 参数列表 + 章节注册表(含已完成章摘要,供交叉引用)。
每章写作前调用一次注入上下文。
"""


@tool(
    category="buildin",
    tags=["报告"],
    display_name="取报告快照",
    description=GET_REPORT_DESCRIPTION,
)
async def get_report(report_id: str) -> dict:
    """返回 report 的状态、PPS 参数与章节注册表快照。"""
    repo = DomainFactoryRepository()
    out = await repo.get_report_snapshot(report_id)
    return out or {"error": f"报告不存在: {report_id}"}


SET_PPS_PARAM_DESCRIPTION = """
设置/更新一个项目参数(PPS)。entity_key 优先用 get_chapter_outline 返回的 entity_bindings 的 key;
value_type 取 number|string|enum。设置后全报告复用。
"""


@tool(
    category="buildin",
    tags=["报告", "PPS"],
    display_name="设置项目参数",
    description=SET_PPS_PARAM_DESCRIPTION,
)
async def set_pps_param(
    report_id: str,
    entity_key: str,
    name: str,
    value: str,
    value_type: str,
    unit: str,
    source: str,
) -> dict:
    """新增或更新某报告的一条 PPS 项目参数。"""
    repo = DomainFactoryRepository()
    return await repo.upsert_pps_param(
        report_id=report_id,
        entity_key=entity_key,
        name=name,
        value=value,
        value_type=value_type,
        unit=unit,
        source=source,
    )


SAVE_CHAPTER_DESCRIPTION = """
懒建/更新一章。canonical_chapter_key 用 get_chapter_outline 的大纲章节名。
content_md 为本章 markdown 正文(含 {{REF:chXX/表X-Y}} 交叉引用占位符、{{MISSING:参数}} 数据占位符)。
status 取:
  - writing: 起草中(默认)
  - done: 终稿锁定
  - skipped: 用户明确跳过
  - pending_data: 等待用户补充数据后再继续
  - review: 提交审批(等待组长/用户确认)
done 时 content_md 不能为空。
"""


@tool(
    category="buildin",
    tags=["报告", "章节"],
    display_name="保存章节",
    description=SAVE_CHAPTER_DESCRIPTION,
)
async def save_chapter(
    report_id: str,
    canonical_chapter_key: str,
    title: str,
    content_md: str,
    summary: str,
    status: str,
) -> dict:
    """懒建或更新一章，自动从大纲推导 chapter_order，并校验。status: writing|done|skipped|pending_data|review"""
    valid_statuses = {"writing", "done", "skipped", "pending_data", "review"}
    if status not in valid_statuses:
        return {"error": f"无效 status: {status}，合法值: {', '.join(sorted(valid_statuses))}"}
    if status == "done" and not (content_md or "").strip():
        return {"error": "status=done 时 content_md 不能为空"}
    if status == "review" and not (content_md or "").strip():
        return {"error": "status=review 时 content_md 不能为空"}
    repo = DomainFactoryRepository()
    if not await repo.report_exists(report_id):
        return {"error": f"报告 {report_id} 不存在。请先调 create_report 创建报告后再 save_chapter。"}
    order = await repo.lookup_chapter_order(report_id, canonical_chapter_key)
    return await repo.upsert_chapter(
        report_id=report_id,
        canonical_chapter_key=canonical_chapter_key,
        chapter_order=order,
        title=title,
        content_md=content_md,
        summary=summary,
        status=status,
    )


ASSEMBLE_REPORT_DESCRIPTION = """
按 outline 序合并所有 done 章节 + 解析 {{REF}} → 成稿 markdown,写入沙箱 outputs。
未解析的 {{REF}} 保留为可见占位符并列出。返回 {markdown, artifact_path, unresolved_refs}。
随后可用 present_artifacts 展示给用户。
"""


async def _write_assembled_to_sandbox(runtime_context, report_id: str, markdown: str) -> str:
    """将成稿 markdown 写入沙箱 outputs 目录,返回虚拟路径。"""
    from yuxi.agents.backends.sandbox.paths import sandbox_outputs_dir

    thread_id = getattr(runtime_context, "thread_id", None) or "shared"
    out_dir = sandbox_outputs_dir(thread_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{report_id}.md"
    await asyncio.to_thread(path.write_text, markdown, "utf-8")
    return f"/home/gem/user-data/outputs/report_{report_id}.md"


@tool(
    category="buildin",
    tags=["报告", "装配"],
    display_name="装配报告",
    description=ASSEMBLE_REPORT_DESCRIPTION,
)
async def assemble_report(report_id: str, runtime: ToolRuntime) -> dict:
    """合并 done 章节 + 解析 {{REF}} + 检测 {{MISSING}} + 写沙箱,返回成稿信息。"""
    from yuxi.services.ref_resolver import _MISSING_RE, resolve_refs

    repo = DomainFactoryRepository()
    chapters = await repo.list_chapters(report_id, status_only="done")
    markdown, unresolved = resolve_refs(chapters)

    # 检测 {{MISSING:...}} 占位符并分组
    missing_params = sorted(set(_MISSING_RE.findall(markdown)))
    missing_by_chapter = {}
    for ch in chapters:
        ch_missing = list(set(_MISSING_RE.findall(ch.get("content_md") or "")))
        if ch_missing:
            missing_by_chapter[ch.get("canonical_chapter_key", "")] = ch_missing

    artifact_path = await _write_assembled_to_sandbox(runtime.context, report_id, markdown)
    await repo.mark_assembled(report_id)
    return {
        "markdown": markdown[:500] + ("..." if len(markdown) > 500 else ""),
        "artifact_path": artifact_path,
        "unresolved_refs": unresolved,
        "missing_params": {
            "total": len(missing_params),
            "params": missing_params,
            "by_chapter": missing_by_chapter,
        },
    }


# ========== v2 计算工具 ==========

CALCULATE_A_VALUE_DESCRIPTION = """
大气环境容量 A 值法计算。

参数:
- A: 地理区域总量控制系数 (如 3.5)
- Ci: 污染物环境质量标准 (mg/m³)
- Si: 区域面积 (km²)

返回:
- capacity: 环境容量 (10⁴ t/a)
- formula: 使用的公式
- steps: 分步计算过程
"""


@tool(
    category="buildin",
    tags=["计算工具", "大气"],
    display_name="A值法大气容量",
    description=CALCULATE_A_VALUE_DESCRIPTION,
)
async def calculate_a_value(A: float, Ci: float, Si: float) -> dict:
    """A 值法计算大气环境容量。"""
    capacity = A * Ci * Si / 10000.0
    return {
        "capacity": round(capacity, 4),
        "unit": "10⁴ t/a",
        "formula": "C = A × Ci × Si / 10000",
        "steps": [
            {"step": "代入数值", "detail": f"C = {A} × {Ci} × {Si} / 10000"},
            {"step": "计算结果", "detail": f"C = {round(capacity, 4)} (10⁴ t/a)"},
        ],
    }


CALCULATE_WATER_CAPACITY_DESCRIPTION = """
一维稳态水质模型水环境容量计算。

参数:
- C0: 初始浓度 (mg/L)
- K: 降解系数 (d⁻¹)
- x: 距离 (m)
- u: 流速 (m/s)

返回:
- Cx: 预测点浓度 (mg/L)
- formula: 使用的公式
- steps: 分步计算过程
"""


@tool(
    category="buildin",
    tags=["计算工具", "水环境"],
    display_name="一维稳态水质模型",
    description=CALCULATE_WATER_CAPACITY_DESCRIPTION,
)
async def calculate_water_capacity(C0: float, K: float, x: float, u: float) -> dict:
    """一维稳态水质模型: C(x) = C₀ exp(-Kx/u)"""
    import math
    exponent = -K * x / (u * 86400)  # u 从 m/s 转为 m/d
    Cx = C0 * math.exp(exponent)
    return {
        "Cx": round(Cx, 4),
        "unit": "mg/L",
        "formula": "C(x) = C₀ × exp(-Kx/u)",
        "steps": [
            {"step": "流速单位换算", "detail": f"u = {u} m/s = {u * 86400} m/d"},
            {"step": "计算指数", "detail": f"-Kx/u = -{K}×{x}/{u*86400} = {exponent:.6f}"},
            {"step": "代入公式", "detail": f"C({x}) = {C0} × exp({exponent:.6f}) = {round(Cx, 4)}"},
        ],
    }


LOOKUP_SUBSIDENCE_DESCRIPTION = """
从知识库查询同类地质条件下的地表沉陷预计算结果（MSPS 软件输出）。

参数:
- depth: 采深范围描述 (如 "300-500m")
- coal_seam: 煤层厚度描述 (如 "2-5m")
- angle: 煤层倾角描述 (如 "0-15°")

返回:
- matched: 匹配到的预计算结果列表 (null 如果没有匹配)
- source: 数据来源报告
- note: 适用性说明
"""


@tool(
    category="buildin",
    tags=["计算工具", "沉陷"],
    display_name="沉陷参数查表",
    description=LOOKUP_SUBSIDENCE_DESCRIPTION,
)
async def lookup_subsidence_params(depth: str, coal_seam: str, angle: str) -> dict:
    """从 KB 查预计算的沉陷参数。"""
    from yuxi.knowledge import knowledge_base as kb_manager
    from yuxi.knowledge.schemas import SearchRequest

    query = f"地表沉陷预测 采深{depth} 煤层{coal_seam} 倾角{angle} MSPS"
    try:
        databases = await kb_manager.get_databases_by_type("milvus")
        if not databases:
            return {"matched": None, "hint": "知识库中没有可用的监测数据库"}

        request = SearchRequest(
            kb_id=databases[0]["kb_id"],
            query=query,
            limit=3,
        )
        results = await kb_manager.search_knowledge(request)
        if not results:
            return {
                "matched": None,
                "hint": f"未找到匹配的地质条件 ({depth}/{coal_seam}/{angle})，建议委托专业建模",
            }

        return {
            "matched": [
                {"content": r.get("content", "")[:500], "source": r.get("source", ""), "score": r.get("score", 0)}
                for r in results[:3]
            ],
            "note": "以上数据来自同类矿区 MSPS 软件预计算结果，引用时标注来源并注明'参考XX煤矿类似地质条件'",
        }
    except Exception as e:
        return {"matched": None, "error": f"KB 查询失败: {e}"}
