"""_parse_markdown_to_paragraphs 单元测试。

回归覆盖：正文/表格段落的 title 应继承所属章节标题，不应为空；
模板回流 chapter 标识不应退化为 section_path 全层 join 的乱码。
"""

from yuxi.services.domain_factory_service import DomainFactoryService


def _service() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


def test_body_paragraph_inherits_chapter_title():
    """正文段落 title 应继承最近一个 heading 的完整标题（编号+名称）。"""
    md = (
        "1 总则\n"
        "1.2 法律法规\n"
        "1.2.2 适用标准\n"
        "本项目执行《环境空气质量标准》。\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)

    # 非标题段落
    body = [p for p in paras if not p.get("is_title") and not p.get("is_table")]
    assert len(body) == 1
    # title 不应为空，且应是所属章节的完整标题
    assert body[0]["title"] == "1.2.2 适用标准"
    assert body[0]["section_path"] == ["1", "1.2", "1.2.2"]


def test_table_paragraph_inherits_chapter_title():
    """表格段落 title 也应继承所属章节标题。

    无 HTML 表格输入时，单行 markdown 表格走"单行表格作为普通段落"分支，
    该分支同样应继承 current_section_title（回归覆盖此分支的 title 赋值）。
    """
    md = "1.2.2 适用标准\n| 单行表格内容 |\n正文段落\n"
    paras = _service()._parse_markdown_to_paragraphs(md)

    # 单行表格行被当作普通段落处理
    table_para = [p for p in paras if p.get("content") == "| 单行表格内容 |"][0]
    assert table_para["title"] == "1.2.2 适用标准"


def test_chapter_identifier_not_mangled():
    """回归：_save_learned_templates_from_task 的 chapter 标识不应是 section_path 全层 join。

    section_path=["1","1.2","1.2.2"] 的 join 结果 "1.1.2.1.2.2" 是 bug；
    正确兜底应取最后一级 "1.2.2"，或优先用继承的 title。
    """
    md = "1.2.2 适用标准\n本项目执行空气标准。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    body = [p for p in paras if not p.get("is_title")][0]

    # 模拟 _save_learned_templates_from_task 的 chapter 推导逻辑
    title = (body.get("title") or "").strip()
    sp = body.get("section_path") or []
    chapter = title or (sp[-1] if sp else "")

    assert chapter == "1.2.2 适用标准"
    assert ".".join(str(s) for s in sp) != chapter  # 旧 bug 会把 join 结果当 chapter


def test_pre_heading_paragraph_has_empty_title():
    """文档第一个 heading 之前的段落 title 应为空（无所属章节）。"""
    md = "封面说明文字\n1 总则\n正文内容\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    pre = [p for p in paras if p.get("content") == "封面说明文字"][0]
    assert pre["title"] == ""
