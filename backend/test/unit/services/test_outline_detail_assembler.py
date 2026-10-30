"""get_outline_template_detail 薄装配测试：图谱 meta + PG 大纲行富字段合并（bug-4167）。"""

import asyncio
from typing import Any
from unittest.mock import patch

from yuxi.services.domain_factory_service import DomainFactoryService


class _FakeGraphService:
    """GraphQueryService.get_chapter_outline 的最小替身"""

    def __init__(self, outline: dict[str, Any] | None):
        self._outline = outline

    async def get_chapter_outline(self, domain: str, report_type: str, chapter_key: str):
        return self._outline

    def close(self) -> None:
        pass


class _FakeRepo:
    """repo.get_outline 的最小替身，记录被请求的 canonical key"""

    def __init__(self, row: dict[str, Any] | None):
        self._row = row
        self.requested_key: str | None = None

    async def get_outline(self, domain: str, report_type: str, canonical_key: str):
        self.requested_key = canonical_key
        return self._row


GRAPH_OUTLINE = {
    "canonical_chapter_key": "总则",
    "title": "总则",
    "level": 1,
    "order": 1,
    "expected_tables": None,
    "expected_charts": None,
    "expected_formulas": None,
    "child_chapters": [],
    "paragraph_roles": [],
}

PG_ROW = {
    "canonical_chapter_key": "总则",
    "chapter_title": "1  总　则",
    "overview": "本章概述编制依据与评价时段",
    "content_requirements": ["编制依据", "评价时段"],
    "entity_bindings": [{"entity_key": "groundwater_level"}],
    "writing_example": "本次评价执行 GB/T 14848...",
    "source_count": 3,
    "expected_tables": [{"table_type": "standard_limit"}],
    "expected_charts": [],
    "expected_formulas": [],
}


def _make_svc(pg_row: dict[str, Any] | None) -> tuple[DomainFactoryService, _FakeRepo]:
    repo = _FakeRepo(pg_row)
    svc = DomainFactoryService.__new__(DomainFactoryService)
    svc.repo = repo
    return svc, repo


def _patch_graph(outline: dict[str, Any] | None):
    return patch("yuxi.services.graph_query_service.GraphQueryService", lambda: _FakeGraphService(outline))


def test_detail_merges_pg_rich_fields_and_falls_back_expected():
    """图谱命中 + PG 富字段收进 source_data；图谱缺失的 expected_* 由 PG 兜底"""
    svc, repo = _make_svc(PG_ROW)
    with _patch_graph(GRAPH_OUTLINE):
        detail = asyncio.run(svc.get_outline_template_detail("coal", "eia_report", "总则||1"))
    assert detail["title"] == "总则"
    assert detail["level"] == 1
    # 图谱侧缺失 → PG 兜底
    assert detail["expected_tables"] == PG_ROW["expected_tables"]
    assert detail["expected_charts"] == []
    # PG 富字段透出在 source_data 子对象
    assert detail["source_data"]["overview"] == "本章概述编制依据与评价时段"
    assert detail["source_data"]["content_requirements"] == ["编制依据", "评价时段"]
    assert detail["source_data"]["entity_bindings"] == [{"entity_key": "groundwater_level"}]
    assert detail["source_data"]["writing_example"] == "本次评价执行 GB/T 14848..."
    assert detail["source_data"]["source_count"] == 3
    # repo 查询用归一 canonical（复合 key 先剥 ||level 再归一）
    assert repo.requested_key == "总则"


def test_detail_keeps_graph_expected_when_present():
    """图谱侧 expected_* 非空时保留图谱值，不被 PG 覆盖"""
    graph = dict(GRAPH_OUTLINE, expected_tables=[{"table_type": "graph_only"}])
    svc, _ = _make_svc(PG_ROW)
    with _patch_graph(graph):
        detail = asyncio.run(svc.get_outline_template_detail("coal", "eia_report", "总则"))
    assert detail["expected_tables"] == [{"table_type": "graph_only"}]


def test_detail_returns_none_when_both_sides_missing():
    svc, _ = _make_svc(None)
    with _patch_graph(None):
        assert asyncio.run(svc.get_outline_template_detail("coal", "eia_report", "不存在的章节XYZ")) is None


def test_detail_serves_pg_only_when_graph_missing():
    """图谱无节点但 PG 有行时仍返回 PG 数据（带编号 key 归一后命中，标题同存去编号干净值）"""
    svc, repo = _make_svc(PG_ROW)
    with _patch_graph(None):
        detail = asyncio.run(svc.get_outline_template_detail("coal", "eia_report", "1  总　则"))
    assert detail is not None
    assert detail["title"] == "总则"  # pg-only 分支 title 同样归一（去编号/空白），与图谱分支一致
    assert detail["canonical_chapter_key"] == "总则"
    assert repo.requested_key == "总则"
    assert detail["source_data"]["source_count"] == 3
