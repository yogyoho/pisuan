"""eia_meta 服务层全链路集成测试（不经 HTTP，无凭据依赖）。

覆盖：存量导入幂等与越界 rid 拒收 → 总览合并与 counts → 标注校验（404/400）→
导出物化（重写人工层文件、文件独有层按 rid 携带）→ 导入绝不覆盖 DB 裁决（DB≠文件判别场景）→
note 不进物化文件、全清空条目回落文件独有层。
关键隔离：测试前后恢复 corpus_meta_annotations.json 原字节（导出会重写技能内真实文件），
DB 行走行级快照恢复（bug-4198：delete 全表曾抹掉运行库标注），测试后还原原状。
"""

from __future__ import annotations

import json

import pytest

from pisuan.services.eia_meta_service import (
    _ANNOTATION_FIELDS,
    META_ANNOTATIONS_PATH,
    _load_corpus_meta,
    get_eia_meta_service,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _clean_state():
    """DB 行自清理 + 人工层文件字节级快照恢复（pg_manager.initialize 幂等）。"""
    from sqlalchemy import delete

    from pisuan.storage.postgres.manager import pg_manager
    from pisuan.storage.postgres.models_domain_factory import EiaMetaAnnotation

    pg_manager.initialize()
    from test.integration.services._flow_isolation import snapshot_rows, restore_rows

    snapshot = META_ANNOTATIONS_PATH.read_bytes() if META_ANNOTATIONS_PATH.is_file() else None
    saved = await snapshot_rows(EiaMetaAnnotation)

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
    await restore_rows(EiaMetaAnnotation, saved)


async def test_meta_full_flow():
    """导入幂等 → 总览合并/counts → 标注校验 → 导出物化与再导入。"""
    svc = get_eia_meta_service()

    # 1) 导入幂等：首扫把存量人工层全部入库（漂移残留拒收计数上浮），二扫零新增
    r1 = await svc.import_annotations()
    assert r1["added"] == r1["scanned"] - r1["skipped_unknown"] and r1["added"] > 0
    r2 = await svc.import_annotations()
    assert r2["added"] == 0

    # 2) 总览：规模锚 corpus_meta 现读；counts 与明细自洽（annotated 只数非空四字段行）
    corpus_meta = _load_corpus_meta()
    data = await svc.list_reports()
    assert data["total"] == len(corpus_meta.get("reports", {}))
    nonempty = sum(
        1
        for ann in json.loads(META_ANNOTATIONS_PATH.read_text(encoding="utf-8")).values()
        if any(k in (ann or {}) for k in _ANNOTATION_FIELDS)
    )
    assert data["counts"]["annotated"] == nonempty
    needs_review = sum(1 for m in corpus_meta.get("reports", {}).values() if m.get("scale_basis") == "needs_review")
    assert data["counts"]["scale_needs_review"] == needs_review
    with_year = sum(1 for it in data["items"] if not it["year_missing"])
    with_scale = sum(1 for it in data["items"] if not it["scale_missing"])
    assert data["counts"]["year_missing"] + with_year == data["total"]
    assert data["counts"]["scale_missing"] + with_scale == data["total"]
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

    # 4) 导出物化：DB 四字段全量重写 + 文件独有层按 rid 携带；rid 序确定
    before = json.loads(META_ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    result = await svc.export_annotations("tester")
    doc = json.loads(META_ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    assert result["materialized"] == len(doc)
    assert list(doc) == sorted(doc) and "001-wps" in doc
    assert set(doc) == set(before)  # 存活 rid 全保留（含 variant-only 条目）
    assert doc["001-wps"]["year_hint"] == 2024 and doc["001-wps"]["scale_mt_a"] == 1.8
    extras = {k: v for k, v in before["001-wps"].items() if k not in _ANNOTATION_FIELDS}
    assert extras and all(doc["001-wps"].get(k) == v for k, v in extras.items())  # 文件独有层不丢

    # 5) 导入绝不覆盖 DB 裁决（判别场景：DB 值 ≠ 文件值，回归为文件覆盖即在此失败）
    target = next(rid for rid, a in sorted(doc.items()) if "year_hint" in a and rid != "001-wps")
    await svc.set_annotation(target, {"annotations": {"year_hint": 2099}, "note": "页面裁决依据"}, "tester")
    r_imp = await svc.import_annotations()
    assert r_imp["added"] == 0 and r_imp["skipped_unknown"] == 0
    data2 = await svc.list_reports()
    it2 = next(i for i in data2["items"] if i["report_id"] == target)
    assert it2["annotation"]["year_hint"] == 2099
    assert it2["annotation"]["decided_by"] == "tester"
    assert it2["annotation"]["note"] == "页面裁决依据"

    # 6) note 仅 DB 留档不进物化文件；全清空条目回落文件独有层（四字段裁决剔除、variant 保留）
    await svc.set_annotation("001-wps", {"annotations": {}}, "tester")
    result2 = await svc.export_annotations("tester")
    doc2 = json.loads(META_ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    assert result2["materialized"] == len(doc2)
    cleared_extras = {k: v for k, v in before["001-wps"].items() if k not in _ANNOTATION_FIELDS}
    assert doc2.get("001-wps") == cleared_extras
    assert doc2[target]["year_hint"] == 2099
    assert "note" not in doc2[target]

    r3 = await svc.import_annotations()
    assert r3["added"] == 0


async def test_meta_export_empty_rejected():
    """空库导出拒绝（ValueError），不产生半成品文件改写。"""
    svc = get_eia_meta_service()
    with pytest.raises(ValueError, match="无标注可导出"):
        await svc.export_annotations("tester")
