"""章节写手预置子智能体（pisuan 环评写作链路，v1 单章写手）。"""
from pisuan.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="chapter-writer",
    name="章节写手",
    description=(
        "聚焦单章写作的子智能体，预装报告大纲、模板与章节存档工具，按调用方给定的章节范围产出正文。"
    ),
    backend_id="SubAgentBackend",
    context={
        "tools": [
            "get_chapter_outline",
            "get_report",
            "get_templates",
            "set_pps_param",
            "save_chapter",
        ],
        "excluded_tools": [],
    },
)
