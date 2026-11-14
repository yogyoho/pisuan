from yuxi.services.domain_factory_region import attribution_scope_key, normalize_attribution


def test_normalize_attribution_trims_and_collapses_blank_to_none():
    """空白归属按未归属处理，避免同一语义产生多个身份。"""
    assert normalize_attribution(" hengcheng ", " regional ", " project-a ") == (
        "hengcheng",
        "regional",
        "project-a",
    )
    assert normalize_attribution("", "   ", None) == (None, None, None)


def test_attribution_scope_key_is_empty_without_any_attribution():
    """无归属时返回空串，兼容存量共享节点。"""
    assert attribution_scope_key("kb-1", None, "", "   ") == ""


def test_attribution_scope_key_includes_knowledge_base_when_attributed():
    """同一区域写入不同知识库也必须得到不同身份。"""
    attr_a = attribution_scope_key("kb-a", "hengcheng", "regional", "")
    attr_b = attribution_scope_key("kb-b", "hengcheng", "regional", "")

    assert attr_a
    assert attr_a != attr_b


def test_attribution_scope_key_changes_with_region_scope_or_project():
    """区域、范围、项目任一变化都必须产生不同身份。"""
    base = attribution_scope_key("kb-1", "hengcheng", "regional", "project-a")

    assert attribution_scope_key("kb-1", "other-region", "regional", "project-a") != base
    assert attribution_scope_key("kb-1", "hengcheng", "project", "project-a") != base
    assert attribution_scope_key("kb-1", "hengcheng", "regional", "project-b") != base


def test_attribution_scope_key_ignores_knowledge_base_without_attribution():
    """只有知识库没有区域/范围/项目时仍视为未归属。"""
    assert attribution_scope_key("kb-a", None, None, None) == ""
    assert attribution_scope_key("kb-b", None, None, None) == ""
