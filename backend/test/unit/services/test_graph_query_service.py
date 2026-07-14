import pytest
from yuxi.services.graph_query_service import GraphQueryService


@pytest.mark.asyncio
async def test_list_chapter_keys_returns_distinct_keys():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("coal", "eia_report")
        assert isinstance(keys, list)
        assert len(keys) >= 13, f"应至少13个顶级章节key,实际{len(keys)}"
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
        assert "content_contract" in outline, "返回应含 content_contract 字段(可为 None)"
    finally:
        service.close()


# ---------------------------------------------------------------------------
# _derive_content_contract — 纯单元测试(不需要 Neo4j)
# ---------------------------------------------------------------------------


def test_derive_content_contract_from_key_points():
    """key_points 列表推导出 key_elements"""
    svc = GraphQueryService.__new__(GraphQueryService)
    cc = svc._derive_content_contract(
        key_points=["气候类型", "气温", "降水", "风向风速"],
        expected_tables=["表3-1 气候特征表"],
    )
    assert cc is not None
    assert cc["key_elements"] == ["气候类型", "气温", "降水", "风向风速"]
    assert cc["structure_type"] == "narrative_text"


def test_derive_content_contract_empty_inputs():
    """空 key_points 和 expected_tables 返回 None"""
    svc = GraphQueryService.__new__(GraphQueryService)
    cc = svc._derive_content_contract(key_points=[], expected_tables=[])
    assert cc is None


def test_derive_content_contract_none_inputs():
    """None 输入返回 None"""
    svc = GraphQueryService.__new__(GraphQueryService)
    cc = svc._derive_content_contract(key_points=None, expected_tables=None)
    assert cc is None


def test_derive_content_contract_with_tables_only():
    """只有 expected_tables 也能推导(key_elements 为空列表)"""
    svc = GraphQueryService.__new__(GraphQueryService)
    cc = svc._derive_content_contract(
        key_points=[],
        expected_tables=["表3-1 气候特征表"],
    )
    assert cc is not None
    assert cc["key_elements"] == []


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
async def test_get_templates_accepts_domain_and_report_type_params():
    """验证 get_templates 签名接受 domain/report_type 参数(为多 domain 过滤做准备)。"""
    service = GraphQueryService()
    try:
        # 使用存在的 key 调用,确认 domain/report_type 参数不报错
        keys = await service.list_chapter_keys("coal", "eia_report")
        if not keys:
            return
        templates = await service.get_templates("coal", "eia_report", keys[0])
        assert isinstance(templates, list)
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_unknown_domain_returns_empty():
    """非主流 domain 下即使 canonical_chapter_key 存在,也不应返回其他 domain 的模板。"""
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("coal", "eia_report")
        if not keys:
            return
        # 用不存在的 domain 查同一 key —— 应返回空(ChapterTemplate 先 MATCH 过滤掉)
        templates = await service.get_templates("nonexistent_domain_xyz", "eia_report", keys[0])
        assert templates == []
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


@pytest.mark.asyncio
async def test_get_chapter_outline_handles_duplicate_chapters():
    """图谱里有重复 ChapterTemplate 时取第一条,不报 multiple records warning"""
    import warnings

    service = GraphQueryService()
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            outline = await service.get_chapter_outline("coal", "eia_report", "地形地貌")
            multi_warnings = [x for x in w if "single record" in str(x.message)]
        assert outline is not None
        assert outline.get("canonical_chapter_key") == "地形地貌"
        assert len(multi_warnings) == 0, "不应报 multiple records warning"
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_recurses_to_children():
    """顶级章节无模板时,递归查子章节模板"""
    service = GraphQueryService()
    try:
        templates = await service.get_templates("coal", "eia_report", "区域自然和社会经济概况")
        assert isinstance(templates, list)
        assert len(templates) > 0, "应通过递归子章节返回模板"
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_subchapter_direct():
    """子章节直接查模板(不递归)"""
    service = GraphQueryService()
    try:
        templates = await service.get_templates("coal", "eia_report", "自然环境概况")
        assert isinstance(templates, list)
        assert len(templates) > 0
    finally:
        service.close()
