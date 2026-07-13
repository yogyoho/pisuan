import pytest
from yuxi.services.graph_query_service import GraphQueryService


@pytest.mark.asyncio
async def test_list_chapter_keys_returns_distinct_keys():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("coal", "eia_report")
        assert isinstance(keys, list)
        assert len(keys) >= 30, f"应至少30个章节key,实际{len(keys)}"
        assert all(isinstance(k, str) and k for k in keys)
        assert len(keys) == len(set(keys)), "章节key不应重复"
    finally:
        service.close()


@pytest.mark.asyncio
async def test_list_chapter_keys_unknown_domain_returns_empty():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("nonexistent_domain_xyz", "eia_report")
        assert keys == []
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_chapter_outline_returns_structure():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("coal", "eia_report")
        if not keys:
            return
        outline = await service.get_chapter_outline("coal", "eia_report", keys[0])
        assert outline is not None
        assert "canonical_chapter_key" in outline
        assert "title" in outline
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_chapter_outline_not_found_returns_none():
    service = GraphQueryService()
    try:
        outline = await service.get_chapter_outline("coal", "eia_report", "不存在的章节XYZ123")
        assert outline is None
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_returns_paragraph_templates():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("coal", "eia_report")
        templates = []
        if keys:
            templates = await service.get_templates("coal", "eia_report", keys[0])
        assert isinstance(templates, list)
        for t in templates:
            assert "text_pattern" in t
            assert "slots" in t
    finally:
        service.close()


@pytest.mark.asyncio
async def test_lookup_chapter_order_returns_int_or_none():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("coal", "eia_report")
        if not keys:
            return
        order = await service.lookup_chapter_order("coal", "eia_report", keys[0])
        assert order is None or isinstance(order, int)
    finally:
        service.close()


@pytest.mark.asyncio
async def test_lookup_chapter_order_unknown_returns_none():
    service = GraphQueryService()
    try:
        order = await service.lookup_chapter_order("coal", "eia_report", "不存在XYZ")
        assert order is None
    finally:
        service.close()
