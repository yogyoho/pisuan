import pytest

from yuxi.services.task_registry import get_failure_task_definition, get_task_definition


def test_failure_hook_fallback_is_limited_to_migrated_legacy_version() -> None:
    assert get_failure_task_definition("knowledge_parse", 0).version == 1

    with pytest.raises(ValueError, match="Unsupported handler version"):
        get_failure_task_definition("knowledge_parse", 2)


def test_domain_factory_handlers_resolve_to_module_functions() -> None:
    # [pisuan-custom] 知识工厂 ETL/入库/再入库走持久任务协议：注册表必须能惰性加载模块级 Handler
    for task_type, function in (
        ("domain_factory", "run_domain_factory_etl"),
        ("domain_factory_ingest", "run_domain_factory_ingest"),
        ("domain_factory_reingest", "run_domain_factory_reingest"),
    ):
        definition = get_task_definition(task_type)
        assert definition.module == "yuxi.services.domain_factory_service"
        assert definition.function == function
        assert callable(definition.load_handler())
