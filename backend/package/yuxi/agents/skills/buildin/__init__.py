from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuiltinSkillSpec:
    slug: str
    source_dir: Path
    description: str = ""
    version: str = "1.0.0"
    tool_dependencies: tuple[str, ...] = ()
    mcp_dependencies: tuple[str, ...] = ()
    skill_dependencies: tuple[str, ...] = ()


_SKILLS_ROOT = Path(__file__).resolve().parent

BUILTIN_SKILLS: list[BuiltinSkillSpec] = [
    BuiltinSkillSpec(
        slug="image-gen",
        source_dir=_SKILLS_ROOT / "image-gen",
        description="在 Agent 沙盒中生成图片并保存到 outputs，默认支持 Qwen-Image，也可接入其它图片生成接口。",
        version="2026.06.02",
        tool_dependencies=("present_artifacts",),
    ),
    BuiltinSkillSpec(
        slug="deep-research",
        source_dir=_SKILLS_ROOT / "deep-research",
        description="深度研究编排方法论：澄清范围、拆解规划、并行调度子智能体调研、对抗式核验、综合成带引用的结构化报告。",
        version="2026.06.05",
        tool_dependencies=("tavily_search",),
    ),
    BuiltinSkillSpec(
        slug="knowledge-base",
        source_dir=_SKILLS_ROOT / "knowledge-base",
        description="使用知识库进行检索、打开文档、文档内定位和查看思维导图。",
        version="2026.06.24",
        tool_dependencies=(
            "list_kbs",
            "query_kb",
            "find_kb_document",
            "open_kb_document",
            "get_mindmap",
            "search_file",
        ),
    ),
    BuiltinSkillSpec(
        slug="mysql-reporter",
        source_dir=_SKILLS_ROOT / "mysql-reporter",
        description="基于 MySQL 数据库生成查询报表和可视化图表，适合分析业务指标、统计趋势，并用 Charts MCP 展示结果。",
        version="2026.06.05",
        mcp_dependencies=("mcp-server-chart",),
    ),
    BuiltinSkillSpec(
        slug="template-recommender",
        source_dir=_SKILLS_ROOT / "template-recommender",
        description="从领域知识库中智能搜索并推荐报告章节和段落模板，支持按章节递归搜索子章节并合并输出模板与原文引用。",
        version="2026.04.29",
        tool_dependencies=["list_kbs", "get_mindmap", "query_kb", "get_templates", "list_report_types", "list_chapter_keys"],
    ),
    BuiltinSkillSpec(
        slug="slot-filler",
        source_dir=_SKILLS_ROOT / "slot-filler",
        description="根据上下文和用户附件智能填充段落模板插槽，给出每个填充数据的置信度，不编造数据，无法填充时提示用户补充。",
        version="2026.04.29",
        tool_dependencies=["query_kb", "ask_user_question", "get_templates", "list_report_types"],
        skill_dependencies=("template-recommender",),
    ),
    BuiltinSkillSpec(
        slug="coal-eia-writer",
        source_dir=_SKILLS_ROOT / "coal-eia-writer",
        description="编写煤矿行业环境影响评价报告。采用分章写作策略处理大型报告，支持公式/表格/图表图文混排，自动合规校验。",
        version="2026.05.11",
        tool_dependencies=(
            "get_chapter_outline",
            "get_templates",
            "create_report",
            "get_report",
            "set_pps_param",
            "save_chapter",
            "assemble_report",
            "subagent_start",
            "subagent_await",
            "present_artifacts",
            "ask_user_question",
            "list_kbs",
            "query_kb",
            "list_report_types",
            "list_chapter_keys",
        ),
        skill_dependencies=("template-recommender", "slot-filler", "compliance-checker"),
    ),
    BuiltinSkillSpec(
        slug="compliance-checker",
        source_dir=_SKILLS_ROOT / "compliance-checker",
        description="对工程类报告进行政策法规合规性校验。从知识库大纲提取法规清单，逐章比对报告内容与法规要求，输出合规校验报告。",
        version="2026.05.11",
        tool_dependencies=[
            "list_kbs",
            "query_kb",
            "read_file",
            "get_chapter_outline",
            "list_report_types",
            "list_chapter_keys",
        ],
    ),
]
