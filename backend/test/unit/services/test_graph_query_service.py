import pytest
from pisuan.services.graph_query_service import GraphQueryService, flatten_leaf_sections


def _chapter(node_id: str, *, parent_id: str | None, key: str, level: int, order: int, chapter_no: str) -> dict:
    return {
        "id": node_id,
        "parent_id": parent_id,
        "canonical_chapter_key": key,
        "title": key,
        "level": level,
        "order": order,
        "chapter_no": chapter_no,
    }


def test_flatten_leaf_sections_keeps_same_title_under_different_parents():
    """同名同层不同父节点必须是不同叶子节，路径与 section_key 都不能合并。"""
    nodes = [
        _chapter("root", parent_id=None, key="总则", level=1, order=1, chapter_no="1"),
        _chapter("left", parent_id="root", key="左侧", level=2, order=1, chapter_no="1.1"),
        _chapter("right", parent_id="root", key="右侧", level=2, order=2, chapter_no="1.2"),
        _chapter("leaf-left", parent_id="left", key="地形地貌", level=3, order=1, chapter_no="1.1.1"),
        _chapter("leaf-right", parent_id="right", key="地形地貌", level=3, order=1, chapter_no="1.2.1"),
    ]

    leaves = flatten_leaf_sections(nodes)

    assert [leaf["section_key"] for leaf in leaves] == ["leaf-left", "leaf-right"]
    assert leaves[0]["path"] == ["总则", "左侧", "地形地貌"]
    assert leaves[1]["path"] == ["总则", "右侧", "地形地貌"]
    assert leaves[0]["canonical_chapter_key"] == leaves[1]["canonical_chapter_key"]


def test_flatten_leaf_sections_excludes_parent_nodes():
    """有子节的章不能进入叶子节清单。"""
    nodes = [
        _chapter("root", parent_id=None, key="区域概况", level=1, order=1, chapter_no="3"),
        _chapter("leaf", parent_id="root", key="气候、气象", level=2, order=1, chapter_no="3.1"),
    ]

    leaves = flatten_leaf_sections(nodes)

    assert [leaf["section_key"] for leaf in leaves] == ["leaf"]
    assert leaves[0]["is_leaf"] is True


def test_flatten_leaf_sections_rejects_cycles():
    """章节层级成环时必须显式失败，不能静默产出错误身份。"""
    nodes = [
        _chapter("a", parent_id="b", key="A", level=1, order=1, chapter_no="1"),
        _chapter("b", parent_id="a", key="B", level=2, order=1, chapter_no="1.1"),
    ]

    with pytest.raises(ValueError, match="环"):
        flatten_leaf_sections(nodes)


def test_flatten_leaf_sections_rejects_broken_parent_link():
    """父节点缺失时不能把子节当根并产出被截断的路径身份。"""
    nodes = [
        _chapter("leaf", parent_id="missing-parent", key="气候、气象", level=3, order=1, chapter_no="3.3.3"),
    ]

    with pytest.raises(ValueError, match="断链"):
        flatten_leaf_sections(nodes)


@pytest.mark.asyncio
async def test_list_chapter_keys_returns_distinct_keys():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("general", "eia_report")
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
async def test_list_leaf_sections_returns_exact_path_identity():
    """叶子节清单携带稳定身份与完整父路径。"""
    service = GraphQueryService()
    try:
        leaves = await service.list_leaf_sections("general", "eia_report")
        climate = [leaf for leaf in leaves if leaf["canonical_chapter_key"] == "气候、气象"]

        assert len(climate) == 1
        assert climate[0]["section_key"] == "CH_general_eia_report_c6a4592541"
        assert climate[0]["path"] == ["区域自然和社会经济概况", "自然环境概况", "气候、气象"]
        assert climate[0]["chapter_no"] == "3.3.3"
        assert climate[0]["is_leaf"] is True
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_section_key_scopes_duplicate_titles():
    """同名同层不同父的叶子节只能返回各自模板，不得按 canonical 合并。"""
    service = GraphQueryService()
    try:
        leaves = await service.list_leaf_sections("general", "eia_report")
        terrain = [leaf for leaf in leaves if leaf["canonical_chapter_key"] == "地形地貌"]
        by_path = {tuple(leaf["path"]): leaf for leaf in terrain}
        left = by_path[("区域自然和社会经济概况", "自然环境概况", "地形地貌")]
        right = by_path[("规划实施环境影响预测与评价", "对宁夏灵武白芨滩自然保护区的影响评价", "地形地貌")]

        left_templates = await service.get_templates("general", "eia_report", section_key=left["section_key"])
        right_templates = await service.get_templates("general", "eia_report", section_key=right["section_key"])

        assert {item["section_key"] for item in left_templates} == {left["section_key"]}
        assert {item["section_key"] for item in right_templates} == {right["section_key"]}
        assert {item["template_id"] for item in left_templates}.isdisjoint(
            {item["template_id"] for item in right_templates}
        )
        assert "TPL_PARA_c69b5435cd26" not in {item["template_id"] for item in left_templates}
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_chapter_outline_returns_structure():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("general", "eia_report")
        if not keys:
            return
        outline = await service.get_chapter_outline("general", "eia_report", keys[0])
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
        outline = await service.get_chapter_outline("general", "eia_report", "不存在的章节XYZ123")
        assert outline is None
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_returns_paragraph_templates():
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("general", "eia_report")
        templates = []
        if keys:
            templates = await service.get_templates("general", "eia_report", keys[0])
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
        keys = await service.list_chapter_keys("general", "eia_report")
        if not keys:
            return
        templates = await service.get_templates("general", "eia_report", keys[0])
        assert isinstance(templates, list)
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_unknown_domain_returns_empty():
    """非主流 domain 下即使 canonical_chapter_key 存在,也不应返回其他 domain 的模板。"""
    service = GraphQueryService()
    try:
        keys = await service.list_chapter_keys("general", "eia_report")
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
        keys = await service.list_chapter_keys("general", "eia_report")
        if not keys:
            return
        order = await service.lookup_chapter_order("general", "eia_report", keys[0])
        assert order is None or isinstance(order, int)
    finally:
        service.close()


@pytest.mark.asyncio
async def test_lookup_chapter_order_unknown_returns_none():
    service = GraphQueryService()
    try:
        order = await service.lookup_chapter_order("general", "eia_report", "不存在XYZ")
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
            outline = await service.get_chapter_outline("general", "eia_report", "地形地貌")
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
        templates = await service.get_templates("general", "eia_report", "区域自然和社会经济概况")
        assert isinstance(templates, list)
        assert len(templates) > 0, "应通过递归子章节返回模板"
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_subchapter_direct():
    """子章节直接查模板(不递归)"""
    service = GraphQueryService()
    try:
        templates = await service.get_templates("general", "eia_report", "自然环境概况")
        assert isinstance(templates, list)
        assert len(templates) > 0
    finally:
        service.close()
