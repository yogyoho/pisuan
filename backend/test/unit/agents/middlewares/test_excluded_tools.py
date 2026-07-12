from __future__ import annotations

from types import SimpleNamespace

import pytest

from yuxi.agents.middlewares.excluded_tools import ExcludedToolsMiddleware


class _Request:
    def __init__(self, tools):
        self.tools = tools

    def override(self, **kwargs):
        return _Request(kwargs.get("tools", self.tools))


def _names(tools):
    result = []
    for t in tools:
        result.append(t["name"] if isinstance(t, dict) else t.name)
    return result


# -- with excluded_tools ----------------------------------------------------------


def test_sync_filters_excluded_tools():
    mw = ExcludedToolsMiddleware(["write_file", "edit_file"])
    seen = {}

    def handler(request):
        seen["tools"] = request.tools
        return "ok"

    tools = [
        SimpleNamespace(name="write_file"),
        SimpleNamespace(name="save_chapter"),
        {"name": "edit_file"},
        SimpleNamespace(name="read_file"),
    ]
    result = mw.wrap_model_call(_Request(tools), handler)

    assert result == "ok"
    assert _names(seen["tools"]) == ["save_chapter", "read_file"]


@pytest.mark.asyncio
async def test_async_filters_excluded_tools():
    mw = ExcludedToolsMiddleware(["write_file"])
    seen = {}

    async def handler(request):
        seen["tools"] = request.tools
        return "ok"

    tools = [
        {"name": "write_file"},
        {"name": "save_chapter"},
    ]
    result = await mw.awrap_model_call(_Request(tools), handler)

    assert result == "ok"
    assert _names(seen["tools"]) == ["save_chapter"]


def test_preserves_order_of_remaining_tools():
    mw = ExcludedToolsMiddleware(["b"])
    seen = {}

    def handler(request):
        seen["tools"] = request.tools
        return "ok"

    tools = [SimpleNamespace(name=n) for n in ["a", "b", "c", "d", "e"]]
    mw.wrap_model_call(_Request(tools), handler)

    assert _names(seen["tools"]) == ["a", "c", "d", "e"]


# -- without excluded_tools -------------------------------------------------------


def test_no_excluded_tools_keeps_all():
    mw = ExcludedToolsMiddleware(None)
    seen = {}

    def handler(request):
        seen["tools"] = request.tools
        return "ok"

    tools = [SimpleNamespace(name="write_file"), SimpleNamespace(name="save_chapter")]
    mw.wrap_model_call(_Request(tools), handler)

    assert _names(seen["tools"]) == ["write_file", "save_chapter"]


@pytest.mark.asyncio
async def test_empty_excluded_tools_keeps_all_async():
    mw = ExcludedToolsMiddleware([])
    seen = {}

    async def handler(request):
        seen["tools"] = request.tools
        return "ok"

    tools = [{"name": "write_file"}, {"name": "edit_file"}]
    await mw.awrap_model_call(_Request(tools), handler)

    assert _names(seen["tools"]) == ["write_file", "edit_file"]


def test_excluded_tool_not_present_keeps_all():
    mw = ExcludedToolsMiddleware(["nonexistent_tool"])
    seen = {}

    def handler(request):
        seen["tools"] = request.tools
        return "ok"

    tools = [SimpleNamespace(name="write_file"), SimpleNamespace(name="save_chapter")]
    mw.wrap_model_call(_Request(tools), handler)

    assert _names(seen["tools"]) == ["write_file", "save_chapter"]


def test_empty_request_tools_returns_empty():
    mw = ExcludedToolsMiddleware(["write_file"])
    seen = {}

    def handler(request):
        seen["tools"] = request.tools
        return "ok"

    mw.wrap_model_call(_Request(None), handler)

    assert seen["tools"] == []
