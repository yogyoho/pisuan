"""ExcludedToolsMiddleware — 从模型可见工具列表中移除 agent 配置的 excluded_tools。

用于系统级强制断捷径：例如 coal-eia-writer 排除 write_file / edit_file，
迫使其走 save_chapter 工具完成章节存档。
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware.types import AgentMiddleware


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
    else:
        name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


class ExcludedToolsMiddleware(AgentMiddleware[Any, Any, Any]):
    """根据构造时传入的 excluded_tools 集合，从模型可见工具中移除对应工具。"""

    def __init__(self, excluded_tools: list[str] | None = None) -> None:
        self._excluded: frozenset[str] = frozenset(excluded_tools or [])

    def _filter(self, tools: list[Any]) -> list[Any]:
        if not self._excluded:
            return tools
        return [t for t in tools if _tool_name(t) not in self._excluded]

    def wrap_model_call(self, request, handler):
        return handler(request.override(tools=self._filter(request.tools or [])))

    async def awrap_model_call(self, request, handler):
        return await handler(request.override(tools=self._filter(request.tools or [])))
