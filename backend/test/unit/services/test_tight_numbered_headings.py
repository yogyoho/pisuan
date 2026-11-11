"""编号紧贴标题文本（无空格）的 markdown heading 编号识别。

实证（任务 7b6364db 第1章 raw_markdown）：上游转换器产出
「### 1.1评价目的与原则」「#### 1.2.2法律、法规」式标题（编号后无空格），
旧 numbered_pattern 要求 ``\\s+`` 导致编号提取失败——节不开、路径栈停滞
（1.2.2 挂到 1.2.1 名下、1.3 挂到 1.2.6）、level3+ 分支补 "1" 产生
幽灵路径元素 ``["1","1","1.1.1"]``（章节导航出现幽灵「1」节点）。

修复后路径改为编号自证（path = 编号逐段，cap 4 级），
无空格编号仅在已确认的 markdown 标题内提取（裸文本路径不放宽，
避免「2024年…」式正文行被误判为标题）。
"""

from pisuan.services.domain_factory_service import DomainFactoryService


def _service():
    return DomainFactoryService.__new__(DomainFactoryService)


def test_no_space_numbered_heading_registers_section():
    """「### 1.1评价目的与原则」应注册 1.1 节，且 1.1.1 不含幽灵重复 "1"。"""
    md = "## 1 总 则\n### 1.1评价目的与原则\n#### 1.1.1 评价目的\n正文内容。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    headings = [p for p in paras if p.get("is_title")]
    assert len(headings) == 3

    assert headings[1]["title"] == "评价目的与原则"
    assert headings[1]["section_path"] == ["1", "1.1"]
    # 关键反断言：修复前此处为 ["1","1","1.1.1"]（幽灵节点）
    assert headings[2]["section_path"] == ["1", "1.1", "1.1.1"]
    assert len(set(headings[2]["section_path"])) == 3


def test_no_space_level3_and_level4_headings():
    """「#### 1.2.2法律、法规」等无空格编号各自开节，不再挂到前节名下。"""
    md = (
        "### 1.2 编制依据\n"
        "#### 1.2.1 任务依据\n"
        "#### 1.2.2法律、法规\n"
        "#### 1.2.3 规章\n"
        "#### 1.2.4相关规划\n"
        "#### 1.2.5 技术规范\n"
        "正文内容。\n"
    )
    paras = _service()._parse_markdown_to_paragraphs(md)
    paths = {tuple(p["section_path"]) for p in paras if p.get("is_title")}
    # 修复前：1.2.2 → ["1","1.2","1.2.1"]、1.2.4 → ["1","1.2","1.2.3"]
    assert ("1", "1.2", "1.2.2") in paths
    assert ("1", "1.2", "1.2.4") in paths
    assert ("1", "1.2", "1.2.3") in paths
    assert ("1", "1.2", "1.2.5") in paths


def test_skip_level_no_ghost_one():
    """跳级（1 总则 后直接 1.1.1，无 1.1 标题）不得补 "1" 占位。"""
    md = "## 1 总 则\n#### 1.1.1 评价目的\n正文内容。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    leaf = [p for p in paras if p.get("is_title")][1]
    # 修复前：["1","1","1.1.1"]（栈浅时盲目补 "1"）
    assert leaf["section_path"] == ["1", "1.1", "1.1.1"]


def test_skip_to_level4_full_prefix():
    """跳级到 level4（栈仅 ["3"]）→ 路径取编号完整四级，不混入栈残段。"""
    md = "## 3 test\n##### 3.3.1.1 leaf\n正文内容。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    leaf = [p for p in paras if p.get("is_title")][1]
    # 修复前：["3","1","3.3.1","3.3.1.1"]（栈补 "1" 后拼接，父子编号断裂）
    assert leaf["section_path"] == ["3", "3.3", "3.3.1", "3.3.1.1"]


def test_body_paragraph_inherits_new_section_path():
    """无空格编号标题后的正文段落继承正确的新路径。"""
    md = "### 1.2 编制依据\n#### 1.2.2法律、法规\n正文内容在这。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    body = [p for p in paras if not p.get("is_title")][0]
    assert body["section_path"] == ["1", "1.2", "1.2.2"]


def test_plain_text_lines_not_loosened():
    """裸文本路径不放宽：数字开头的正文行不被误判为标题。"""
    md = "## 1 总 则\n2024年3月发布的环境保护标准内容，这一行是普通正文段落。\n1.1 有空格的裸文本标题\n正文内容。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    # 「2024年3月…」不是标题
    assert not any(p.get("is_title") and p.get("title", "").startswith("2024年") for p in paras)
    # 有空格的裸文本编号标题照常识别
    assert any(p.get("is_title") and p.get("title") == "有空格的裸文本标题" for p in paras)


def test_numbered_only_tight_heading_falls_back():
    """「#### 1.1.2」纯编号无标题文本：不提取编号，不产生幽灵路径。"""
    md = "## 1 总 则\n#### 1.1.2\n正文内容。\n"
    paras = _service()._parse_markdown_to_paragraphs(md)
    h = [p for p in paras if p.get("is_title")][1]
    assert h["title"] == "1.1.2"
    # 走无编号分支：截断当前栈，不产生编号混血路径
    assert h["section_path"] == ["1"]
