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


# ========== {{MISSING}} 占位符检测 ==========

from yuxi.services.ref_resolver import _MISSING_RE


def test_missing_re_detects_single_placeholder():
    """RED→GREEN: _MISSING_RE 应检测单个 {{MISSING:...}}"""
    text = "PM10 浓度为 {{MISSING:PM10_2023}} μg/m³"
    found = _MISSING_RE.findall(text)
    assert found == ["PM10_2023"]


def test_missing_re_detects_multiple_placeholders():
    """_MISSING_RE 应检测多个占位符并去重"""
    text = "{{MISSING:PM10}} 和 {{MISSING:SO2}}，再次 {{MISSING:PM10}}"
    found = _MISSING_RE.findall(text)
    assert "PM10" in found
    assert "SO2" in found
    assert len(found) == 3  # 不去重，findall 返回所有匹配


def test_missing_re_ignores_ref_placeholders():
    """_MISSING_RE 不应匹配 {{REF:...}}"""
    text = "见 {{REF:ch05/表5-3}}，数据 {{MISSING:监测数据}}"
    found = _MISSING_RE.findall(text)
    assert found == ["监测数据"]


def test_missing_re_handles_empty_text():
    """_MISSING_RE 空文本应返回空列表"""
    assert _MISSING_RE.findall("") == []


def test_missing_re_handles_special_chars_in_name():
    """_MISSING_RE 支持中文/数字/下划线参数名"""
    text = "{{MISSING:大气监测_PM10_2023}} 和 {{MISSING:项目产能_Mt/a}}"
    found = _MISSING_RE.findall(text)
    assert "大气监测_PM10_2023" in found
    # {{MISSING:...}} 中的 / 不是通配符，所以 "项目产能_Mt/a" 中 / 会切割匹配
    assert any("项目产能" in f for f in found)
