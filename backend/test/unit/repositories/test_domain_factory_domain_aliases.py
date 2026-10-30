"""去领域化常量与别名归一单元测试（设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md）。"""

from yuxi.repositories.domain_factory_repository import (
    GENERAL_DOMAIN_CODE,
    GENERAL_DOMAIN_NAME,
    _normalize_domain,
    _normalize_report_type,
)


def test_general_domain_constants():
    assert GENERAL_DOMAIN_CODE == "general"
    assert GENERAL_DOMAIN_NAME == "通用域"


def test_normalize_domain_still_works_as_alias_lookup():
    # 别名表保留（工具入参兼容），但去域后语义由调用方强制覆盖为 general
    assert _normalize_domain("煤矿") == "coal"
    assert _normalize_domain("  chem ") == "chem"


def test_report_type_alias_general_to_eia_report_is_load_bearing():
    # 与 spec 的偏差项：该映射保留（默认上传 report_type="通用" 依赖它换算大纲键）
    assert _normalize_report_type("通用") == "eia_report"
