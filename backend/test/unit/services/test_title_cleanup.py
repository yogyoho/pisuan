"""Task 10: title 双编号清洗测试。

numbered-line 路径也需清洗双编号 + 过滤纯编号。
"""

from yuxi.services.domain_factory_service import DomainFactoryService


def test_clean_dual_numbering_markdown_path():
    """双编号 '1.1.1 3.1.1 地形地貌' → '3.1.1 地形地貌'"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("1.1.1 3.1.1 地形地貌") == "3.1.1 地形地貌"


def test_clean_dual_numbering_numbered_path():
    """单编号 '3.1.1 地形地貌' → 保留"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("3.1.1 地形地貌") == "3.1.1 地形地貌"


def test_clean_pure_number_returns_empty():
    """纯编号 '2' → 空字符串"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("2") == ""


def test_clean_no_numbering_unchanged():
    """无编号标题 → 原样"""
    service = DomainFactoryService()
    assert service._clean_chapter_title("地形地貌") == "地形地貌"
