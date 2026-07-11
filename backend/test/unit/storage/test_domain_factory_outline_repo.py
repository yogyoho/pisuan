import pytest
from yuxi.storage.postgres.manager import pg_manager
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository


@pytest.fixture(autouse=True)
async def _dispose_engine_after():
    """pg_manager 是单例，async_engine 会绑定到首个事件循环；
    每个测试结束后 dispose 并重置初始化标志，确保下一个测试在新循环上重新初始化。"""
    yield
    await pg_manager.close()
    pg_manager.async_engine = None
    pg_manager.AsyncSession = None
    pg_manager._initialized = False


@pytest.mark.asyncio
async def test_upsert_and_get_outline():
    repo = DomainFactoryRepository()
    await repo.upsert_outline(
        domain_code="coal",
        report_type_code="eia_report",
        canonical_chapter_key="地下水环境影响预测",
        chapter_id="5.2",
        chapter_title="地下水环境影响预测",
        purpose="预测开采对地下水的影响",
        overview="本章预测...",
        key_points=["水位下降", "水质影响"],
        content_requirements=["水位降深", "影响半径"],
        regulations=[{"code": "GB/T 14848", "title": "地下水质量标准"}],
        entity_bindings=[{"entity_key": "groundwater_level", "value_type": "number"}],
        writing_example="预测结果表明...",
        writing_hints="先给水文地质参数，再用数值法",
        expected_tables=[], expected_charts=[], expected_formulas=[], expected_figures=[],
        source_task_ids=["t-1"], source_count=1, prose_based_on_source_count=1,
    )
    got = await repo.get_outline("coal", "eia_report", "地下水环境影响预测")
    assert got is not None
    assert got["chapter_title"] == "地下水环境影响预测"
    assert "水位下降" in got["key_points"]


@pytest.mark.asyncio
async def test_list_chapter_keys_and_backfill():
    repo = DomainFactoryRepository()
    keys = await repo.list_chapter_keys("coal", "eia_report")
    assert "地下水环境影响预测" in keys
    n = await repo.backfill_template_chapter_key("coal", "eia_report", "5.2", "地下水环境影响预测")
    assert n >= 0
