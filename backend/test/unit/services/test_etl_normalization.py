"""Task 9: ETL report_type 归一化测试。

入图谱前需将"通用"等中文别名归一化为 DB code；domain 写入面已恒为通用域
（去领域化），原 domain 归一化方法及用例随之移除。
"""

from yuxi.services.domain_factory_service import DomainFactoryService


def test_normalize_report_type_general_to_code():
    """'通用'和中文别名 → eia_report code。"""
    service = DomainFactoryService()
    assert service._normalize_report_type_for_graph("通用") == "eia_report"
    assert service._normalize_report_type_for_graph("环评报告") == "eia_report"
    assert service._normalize_report_type_for_graph("eia_report") == "eia_report"


def test_normalize_unknown_keeps_original():
    """未知名/空值原样保留。"""
    service = DomainFactoryService()
    assert service._normalize_report_type_for_graph("") == ""
