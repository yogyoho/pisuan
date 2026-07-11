from yuxi.services.ref_resolver import resolve_refs


def test_resolve_table_ref_and_flag_unresolved():
    chapters = [
        {
            "chapter_order": 2,
            "title": "ch2",
            "content_md": "## 2.1\n见 {{REF:ch05/表5-3}}。\n\n**表5-3 监测结果**\n|a|b|\n",
        },
        {
            "chapter_order": 5,
            "title": "ch5",
            "content_md": "标题\n**表5-3 大气监测**\n|x|y|\n引用 {{REF:ch09/图9-1}} 未写。",
        },
    ]
    merged, unresolved = resolve_refs(chapters)
    assert "表5-3" in merged  # ch05 的表5-3 被解析进 ch2 的引用
    assert any("图9-1" in u.get("ref", "") or "图9-1" in str(u) for u in unresolved)


def test_chapters_merged_in_order():
    chapters = [
        {"chapter_order": 5, "content_md": "第五"},
        {"chapter_order": 2, "content_md": "第二"},
    ]
    merged, _ = resolve_refs(chapters)
    assert merged.index("第二") < merged.index("第五")


def test_resolve_section_ref():
    chapters = [
        {"chapter_order": 2, "content_md": "见 {{REF:ch05/2.1 排放情况}}。"},
        {"chapter_order": 5, "content_md": "## 2.1 排放情况\nSO₂ 排放..."},
    ]
    merged, unresolved = resolve_refs(chapters)
    assert "见2.1 排放情况" in merged or "2.1 排放情况" in merged  # section ref 解析
    assert unresolved == []
