"""Task 9: ETL domain/report_type 归一化测试。

入图谱前需将中文别名归一化为 DB code，防止"通用"等未归一值污染图谱。
"""

from yuxi.services.domain_factory_service import DomainFactoryService


def test_normalize_domain_chinese_to_code():
    """中文别名 → DB code。"""
    service = DomainFactoryService()
    assert service._normalize_domain_for_graph("煤炭采掘") == "coal"
    assert service._normalize_domain_for_graph("煤矿") == "coal"
    assert service._normalize_domain_for_graph("coal") == "coal"


def test_normalize_report_type_general_to_code():
    """'通用'和中文别名 → eia_report code。"""
    service = DomainFactoryService()
    assert service._normalize_report_type_for_graph("通用") == "eia_report"
    assert service._normalize_report_type_for_graph("环评报告") == "eia_report"
    assert service._normalize_report_type_for_graph("eia_report") == "eia_report"


def test_normalize_unknown_keeps_original():
    """未知名/空值原样保留。"""
    service = DomainFactoryService()
    assert service._normalize_domain_for_graph("unknown_domain") == "unknown_domain"
    assert service._normalize_report_type_for_graph("") == ""
