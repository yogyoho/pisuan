import pytest
from yuxi.storage.postgres.manager import pg_manager
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    await pg_manager.close()
    pg_manager._initialized = False


@pytest.mark.asyncio
async def test_create_report_and_chapter_and_pps():
    repo = DomainFactoryRepository()
    rep = await repo.create_report(
        thread_id="t1", title="伊宁矿区环评", domain_code="coal",
        report_type_code="eia_report", kb_id="kb_x", created_by="admin",
    )
    assert rep["id"]
    rid = rep["id"]

    ch = await repo.upsert_chapter(
        report_id=rid, canonical_chapter_key="地下水环境影响预测",
        chapter_order=5, title="5 地下水", content_md="正文…", summary="地下水预测",
        status="done",
    )
    assert ch["status"] == "done"

    pps = await repo.upsert_pps_param(
        report_id=rid, entity_key="groundwater_level", name="地下水位",
        value="10", value_type="number", unit="m", source="监测",
    )
    assert pps["value"] == "10"

    snap = await repo.get_report_snapshot(rid)
    assert snap["status"] == "writing"  # upsert_chapter advances draft → writing
    assert any(c["canonical_chapter_key"] == "地下水环境影响预测" for c in snap["chapters"])
    assert any(p["entity_key"] == "groundwater_level" for p in snap["pps"])
