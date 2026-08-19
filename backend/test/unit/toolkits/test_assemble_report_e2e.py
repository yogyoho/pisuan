"""P0 修复金标准测试（bug-124）：save_chapter(done/review) → assemble_report → 成稿文件输出。

验证环评写作成稿链路的三处结构性修复：
  A) assemble_report 合并 done + review 章节（review=完稿待审），排除 writing
  B) C3：save_chapter(done/review) 返回 preview_path，writing 不返回
  C) 多章节合并写出真实成稿文件 + mark_assembled 推进报告状态

取证背景（tool_calls 表）：写手 60% 标错 status(writing/review)，编排者 75% 跳过 assemble_report。
本测试锁定结构层修复，使"即使编排者调了 assemble"也能把完稿章节装配出来。
"""
from unittest.mock import AsyncMock

import pytest
from langgraph.prebuilt.tool_node import ToolRuntime

import yuxi.agents.toolkits.buildin.tools as tools_mod


def _fake_runtime() -> ToolRuntime:
    return ToolRuntime(
        state={},
        context={},
        config={},
        stream_writer=lambda *a, **k: None,
        tool_call_id="tc_golden",
        store=None,
    )


@pytest.mark.asyncio
async def test_assemble_includes_done_and_review_excludes_writing(monkeypatch, tmp_path):
    """A) assemble_report 合并 done + review，排除 writing。"""
    monkeypatch.setenv("SAVE_DIR", str(tmp_path))
    chapters = [
        {"chapter_order": 1, "canonical_chapter_key": "ch1", "title": "总则", "status": "done", "content_md": "# 总则\n内容1"},
        {"chapter_order": 2, "canonical_chapter_key": "ch2", "title": "现状", "status": "review", "content_md": "# 现状\n内容2"},
        {"chapter_order": 3, "canonical_chapter_key": "ch3", "title": "预测", "status": "writing", "content_md": "# 预测\n草稿"},
    ]

    async def _list(rid, status_only=None):
        # 模拟真实 list_chapters 的 status 过滤（list/tuple → in_，单值 → ==）
        if status_only is None:
            return chapters
        statuses = set(status_only) if isinstance(status_only, (list, tuple, set)) else {status_only}
        return [c for c in chapters if c["status"] in statuses]

    assembled = {"called": False}
    repo = AsyncMock(
        list_chapters=AsyncMock(side_effect=_list),
        mark_assembled=AsyncMock(side_effect=lambda *a, **k: assembled.__setitem__("called", True)),
    )
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: repo)

    out = await tools_mod.assemble_report.ainvoke({"report_id": "rpt_golden", "runtime": _fake_runtime()})
    # 断言 assemble_report 向 list_chapters 传了 done+review 过滤
    repo.list_chapters.assert_awaited_with("rpt_golden", status_only=["done", "review"])

    # 成稿文件真实写出
    assert out["artifact_path"].endswith("report_rpt_golden.md")
    content = open(out["artifact_path"], encoding="utf-8").read()
    # done + review 章节进入成稿
    assert "内容1" in content
    assert "内容2" in content
    # writing 章节被排除
    assert "草稿" not in content
    # 报告状态推进到 assembled
    assert assembled["called"] is True


@pytest.mark.asyncio
async def test_save_chapter_done_returns_preview_writing_does_not(monkeypatch):
    """B) C3：save_chapter(done/review) 返回 preview_path，writing/skipped 不返回。"""

    def _fake_preview(runtime, report_id, key, content_md, status):
        # 模拟真实 _write_chapter_preview 的 status 门控
        return f"/preview/{key}.md" if status in ("done", "review") else None

    monkeypatch.setattr(tools_mod, "_write_chapter_preview", _fake_preview)
    monkeypatch.setattr(
        tools_mod,
        "DomainFactoryRepository",
        lambda: AsyncMock(
            report_exists=AsyncMock(return_value=True),
            upsert_chapter=AsyncMock(return_value={"canonical_chapter_key": "ch", "status": "done"}),
        ),
    )

    base = {
        "report_id": "rpt_x",
        "canonical_chapter_key": "ch1",
        "title": "T",
        "content_md": "正文",
        "summary": "摘",
        "runtime": _fake_runtime(),
    }
    out_done = await tools_mod.save_chapter.ainvoke({**base, "status": "done"})
    assert out_done.get("preview_path") == "/preview/ch1.md"
    assert "提示" in out_done  # C3 反馈消息

    out_review = await tools_mod.save_chapter.ainvoke({**base, "status": "review"})
    assert out_review.get("preview_path") == "/preview/ch1.md"

    out_writing = await tools_mod.save_chapter.ainvoke({**base, "status": "writing"})
    assert "preview_path" not in out_writing  # writing 不写 preview


@pytest.mark.asyncio
async def test_save_then_assemble_full_chain(monkeypatch, tmp_path):
    """C) save_chapter × N → assemble_report → 成稿含全部 done 章节。"""
    monkeypatch.setenv("SAVE_DIR", str(tmp_path))

    # 用内存 dict 模拟 DB 章节表
    store: dict[str, dict] = {}

    async def _upsert(report_id, canonical_chapter_key, chapter_order, title, content_md, summary, status):
        store[canonical_chapter_key] = {
            "canonical_chapter_key": canonical_chapter_key,
            "chapter_order": chapter_order or len(store) + 1,
            "title": title,
            "content_md": content_md,
            "summary": summary,
            "status": status,
        }
        return store[canonical_chapter_key]

    repo = AsyncMock(
        report_exists=AsyncMock(return_value=True),
        lookup_chapter_order=AsyncMock(side_effect=lambda rid, key: int(key[-1])),
        upsert_chapter=AsyncMock(side_effect=_upsert),
        list_chapters=AsyncMock(side_effect=lambda rid, status_only=None: sorted(store.values(), key=lambda c: c["chapter_order"])),
        mark_assembled=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: repo)
    monkeypatch.setattr(tools_mod, "_write_chapter_preview", lambda *a, **k: "/preview.md")

    rt = _fake_runtime()
    for key, body in [("ch1", "总则正文"), ("ch2", "现状正文"), ("ch3", "预测正文")]:
        await tools_mod.save_chapter.ainvoke({
            "report_id": "rpt_chain", "canonical_chapter_key": key, "title": key,
            "content_md": f"# {key}\n{body}", "summary": "摘", "status": "done", "runtime": rt,
        })

    out = await tools_mod.assemble_report.ainvoke({"report_id": "rpt_chain", "runtime": rt})

    content = open(out["artifact_path"], encoding="utf-8").read()
    for body in ["总则正文", "现状正文", "预测正文"]:
        assert body in content
