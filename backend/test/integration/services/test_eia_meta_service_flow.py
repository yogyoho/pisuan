"""eia_meta 服务层全链路集成测试（不经 HTTP，无凭据依赖）。

覆盖：存量导入幂等 → 总览合并与 counts → 标注校验（404/400）→ 导出物化（重写人工层文件）。
关键隔离：测试前后恢复 corpus_meta_annotations.json 原字节（导出会重写技能内真实文件），
DB 行前后自清理；绝不污染运行库与技能目录。
"""

from __future__ import annotations

import json

import pytest

from yuxi.services.eia_meta_service import (
    META_ANNOTATIONS_PATH,
    get_eia_meta_service,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _clean_state():
    """DB 行自清理 + 人工层文件字节级快照恢复（pg_manager.initialize 幂等）。"""
    from sqlalchemy import delete

    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.storage.postgres.models_domain_factory import EiaMetaAnnotation

    pg_manager.initialize()
    snapshot = META_ANNOTATIONS_PATH.read_bytes() if META_ANNOTATIONS_PATH.is_file() else None

    async def _wipe():
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EiaMetaAnnotation))

    await _wipe()
    yield
    await _wipe()
    if snapshot is None:
        META_ANNOTATIONS_PATH.unlink(missing_ok=True)
    else:
        META_ANNOTATIONS_PATH.write_bytes(snapshot)


async def test_meta_full_flow():
    """导入幂等 → 总览合并/counts → 标注校验 → 导出物化与再导入。"""
    svc = get_eia_meta_service()

    # 1) 导入幂等：首扫把存量人工层全部入库，二扫零新增
    r1 = await svc.import_annotations()
    assert r1["added"] == r1["scanned"] and r1["added"] > 0
    r2 = await svc.import_annotations()
    assert r2["added"] == 0

    # 2) 总览：31 份全量；已标注 == 导入数；counts 与明细自洽
    data = await svc.list_reports()
    assert data["total"] == 31
    assert data["counts"]["annotated"] == r1["added"]
    assert data["counts"]["scale_needs_review"] == 27
    with_year = sum(1 for it in data["items"] if not it["year_missing"])
    with_scale = sum(1 for it in data["items"] if not it["scale_missing"])
    assert data["counts"]["year_missing"] + with_year == 31
    assert data["counts"]["scale_missing"] + with_scale == 31
    by_rid = {it["report_id"]: it for it in data["items"]}
    assert "001-wps" in by_rid

    # 3) 标注校验：未知 rid 404（KeyError）；越界/未知字段 400（ValueError）；合法值落库
    with pytest.raises(KeyError):
        await svc.set_annotation("no-such-report", {"annotations": {"year_hint": 2024}}, "tester")
    with pytest.raises(ValueError, match="year_hint"):
        await svc.set_annotation("001-wps", {"annotations": {"year_hint": 1999}}, "tester")
    with pytest.raises(ValueError, match="未知标注字段"):
        await svc.set_annotation("001-wps", {"annotations": {"coal_type": "x"}}, "tester")
    row = await svc.set_annotation("001-wps", {"annotations": {"year_hint": 2024, "scale_mt_a": 1.8}}, "tester")
    assert row["annotations"] == {"year_hint": 2024, "scale_mt_a": 1.8}
    assert row["decided_by"] == "tester"

    # 4) 导出物化：DB 全量（导入 18 + 新标 1）重写人工层文件；rid 序确定；再导入零新增
    result = await svc.export_annotations("tester")
    assert result["materialized"] == r1["added"] + 1
    doc = json.loads(META_ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    assert list(doc) == sorted(doc) and "001-wps" in doc
    assert doc["001-wps"] == {"year_hint": 2024, "scale_mt_a": 1.8}
    r3 = await svc.import_annotations()
    assert r3["added"] == 0


async def test_meta_export_empty_rejected():
    """空库导出拒绝（ValueError），不产生半成品文件改写。"""
    svc = get_eia_meta_service()
    with pytest.raises(ValueError, match="无标注可导出"):
        await svc.export_annotations("tester")
