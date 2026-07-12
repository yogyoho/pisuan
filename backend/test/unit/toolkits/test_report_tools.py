import pytest
from unittest.mock import AsyncMock
from langgraph.prebuilt.tool_node import ToolRuntime
import yuxi.agents.toolkits.buildin.tools as tools_mod


def _fake_runtime(context=None):
    """构造测试用 ToolRuntime(最小必填字段)。"""
    return ToolRuntime(
        state={},
        context=context or {},
        config={},
        stream_writer=lambda *a, **k: None,
        tool_call_id="tc_test",
        store=None,
    )


@pytest.mark.asyncio
async def test_create_report_tool(monkeypatch):
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(create_report=AsyncMock(return_value={"id": "rpt_1", "title": "T", "status": "draft"})),
    )
    out = await tools_mod.create_report.ainvoke(
        {"thread_id": "t1", "title": "T", "domain": "coal", "report_type": "eia_report", "kb_id": "kb_x"}
    )
    assert out["id"] == "rpt_1"


@pytest.mark.asyncio
async def test_get_report_and_set_pps_tools(monkeypatch):
    snap = {"id": "rpt_1", "status": "writing", "pps": [], "chapters": [], "registry": []}
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(
            get_report_snapshot=AsyncMock(return_value=snap),
            upsert_pps_param=AsyncMock(return_value={"entity_key": "k", "value": "v"}),
        ),
    )
    rep = await tools_mod.get_report.ainvoke({"report_id": "rpt_1"})
    assert rep["status"] == "writing"
    p = await tools_mod.set_pps_param.ainvoke(
        {
            "report_id": "rpt_1",
            "entity_key": "k",
            "name": "n",
            "value": "v",
            "value_type": "number",
            "unit": "m",
            "source": "s",
        }
    )
    assert p["value"] == "v"


@pytest.mark.asyncio
async def test_save_chapter_tool(monkeypatch):
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(
            report_exists=AsyncMock(return_value=True),
            upsert_chapter=AsyncMock(return_value={"canonical_chapter_key": "k", "status": "done"}),
        ),
    )
    out = await tools_mod.save_chapter.ainvoke(
        {
            "report_id": "rpt_1",
            "canonical_chapter_key": "k",
            "title": "T",
            "content_md": "正文",
            "summary": "摘",
            "status": "done",
        }
    )
    assert out["status"] == "done"


@pytest.mark.asyncio
async def test_save_chapter_rejects_done_with_empty_content(monkeypatch):
    # status=done + 空 content 必须被拒,且不触达 repo
    repo_mock = AsyncMock()
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: repo_mock)
    out = await tools_mod.save_chapter.ainvoke(
        {
            "report_id": "rpt_1",
            "canonical_chapter_key": "k",
            "title": "T",
            "content_md": "",
            "summary": "摘",
            "status": "done",
        }
    )
    assert "error" in out
    repo_mock.upsert_chapter.assert_not_awaited()  # 被拒,不应触达 repo


@pytest.mark.asyncio
async def test_save_chapter_rejects_invalid_report_id(monkeypatch):
    # report_id 不存在 → error,且不触达 upsert_chapter
    repo_mock = AsyncMock(
        report_exists=AsyncMock(return_value=False),
        lookup_chapter_order=AsyncMock(return_value=1),
    )
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: repo_mock)
    out = await tools_mod.save_chapter.ainvoke(
        {
            "report_id": "rpt_nonexistent",
            "canonical_chapter_key": "k",
            "title": "T",
            "content_md": "正文",
            "summary": "摘",
            "status": "writing",
        }
    )
    assert "error" in out
    assert "rpt_nonexistent" in out["error"]
    repo_mock.upsert_chapter.assert_not_awaited()


@pytest.mark.asyncio
async def test_assemble_report_tool(monkeypatch, tmp_path):
    chapters = [{"chapter_order": 1, "content_md": "# ch1\n正文"}]
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(
            list_chapters=AsyncMock(return_value=chapters),
            mark_assembled=AsyncMock(return_value=None),
        ),
    )

    # mock sandbox 写:跳过实际 FS,验证返回结构
    async def fake_write(*a, **k):
        return "/home/gem/user-data/outputs/report.md"

    monkeypatch.setattr(tools_mod, "_write_assembled_to_sandbox", fake_write)
    out = await tools_mod.assemble_report.ainvoke({"report_id": "rpt_1", "runtime": _fake_runtime()})
    assert out["artifact_path"].endswith("report.md")
    assert out["unresolved_refs"] == []
