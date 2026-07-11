import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from yuxi.services.domain_factory_service import DomainFactoryService


def test_group_assets_by_chapter_buckets_by_chapter():
    task_detail = {
        "source_paragraphs": [
            {
                "id": "p1",
                "title": "5.2 地下水",
                "classify_type": "parameter",
                "template": {
                    "generalized": "水位{{水位值}}",
                    "slots": [{"name": "水位值"}],
                    "sample_original": "水位10m",
                },
            },
            {"id": "p2", "title": "5.2 地下水", "classify_type": "narrative", "template": {}},
            {
                "id": "p3",
                "title": "5.3 声环境",
                "classify_type": "parameter",
                "template": {
                    "generalized": "噪声{{噪声值}}",
                    "slots": [{"name": "噪声值"}],
                    "sample_original": "噪声55dB",
                },
            },
        ],
        "structured_blocks": [],
    }
    svc = DomainFactoryService.__new__(DomainFactoryService)
    groups = svc._group_assets_by_chapter(task_detail)
    assert "5.2 地下水" in groups and "5.3 声环境" in groups
    assert len(groups["5.2 地下水"]["templates"]) == 1


def test_assemble_deterministic_outline_fields():
    assets = {
        "templates": [{"slots": [{"name": "水位值"}, {"name": "影响半径"}], "sample_original": "水位10m"}],
        "paragraphs": [{"classify_type": "parameter"}, {"classify_type": "narrative"}],
        "legal_refs": [{"code": "GB/T 14848", "title": "地下水质量标准"}],
        "entities": [{"entity_key": "groundwater_level", "value_type": "number", "unit": "m"}],
        "tables": [{"table_type": "standard_limit", "columns": [{"name": "污染物", "role": "key"}]}],
        "formulas": [{"formula_template": "S=Q/T", "variables": [{"name": "Q", "symbol": "Q"}]}],
        "charts": [{"chart_type": "line", "data_source": "water_level"}],
        "figures": [{"figure_type": "process_flow"}],
    }
    svc = DomainFactoryService.__new__(DomainFactoryService)
    out = svc._assemble_deterministic_outline(assets)
    assert "水位值" in out["content_requirements"]
    assert out["regulations"][0]["code"] == "GB/T 14848"
    assert out["entity_bindings"][0]["entity_key"] == "groundwater_level"
    assert out["expected_tables"][0]["table_type"] == "standard_limit"
    assert out["writing_example"] == "水位10m"


def test_llm_chapter_meta_parses_json_and_reuses_seed_key():
    svc = DomainFactoryService.__new__(DomainFactoryService)
    fake_resp = type(
        "R",
        (),
        {
            "content": '{"canonical_chapter_key":"地下水环境影响预测",'
            '"purpose":"预测开采对地下水影响",'
            '"overview":"本章预测...",'
            '"key_points":["水位下降"],'
            '"writing_hints":"先水文地质参数"}'
        },
    )()
    with patch(
        "yuxi.services.domain_factory_service.select_model_lazy",
        AsyncMock(return_value=type("M", (), {"call": AsyncMock(return_value=fake_resp)})()),
        create=True,
    ):
        # select_model 是函数导入；按实际导入路径 mock（见 Step 3 实现）
        import yuxi.services.domain_factory_service as mod

        with patch.object(
            mod, "select_model", return_value=type("M", (), {"call": AsyncMock(return_value=fake_resp)})()
        ):
            out = asyncio.run(
                svc._llm_chapter_meta(
                    "5.2 地下水环境影响预测", {"content_requirements": ["水位降深"]}, seed_keys=["地下水环境影响预测"]
                )
            )
    assert out["canonical_chapter_key"] == "地下水环境影响预测"
    assert "水位下降" in out["key_points"]


@pytest.mark.asyncio
async def test_produce_outlines_async_writes_rows_and_backfills(monkeypatch):
    svc = DomainFactoryService.__new__(DomainFactoryService)
    svc.repo = AsyncMock()
    svc.repo.list_chapter_keys = AsyncMock(return_value=[])
    svc.repo.upsert_outline = AsyncMock()
    svc.repo.backfill_template_chapter_key = AsyncMock(return_value=1)
    svc.get_task_detail = AsyncMock(
        return_value={
            "source_paragraphs": [
                {
                    "id": "p1",
                    "title": "5.2 地下水",
                    "classify_type": "parameter",
                    "template": {
                        "generalized": "水位{{水位值}}",
                        "slots": [{"name": "水位值"}],
                        "sample_original": "水位10m",
                    },
                },
            ],
        }
    )
    svc._llm_chapter_meta = AsyncMock(
        return_value={
            "canonical_chapter_key": "地下水环境影响预测",
            "purpose": "p",
            "overview": "o",
            "key_points": ["k"],
            "writing_hints": "h",
        }
    )
    n = await svc._produce_outlines_async("task-1", "coal", "eia_report")
    assert n == 1
    svc.repo.upsert_outline.assert_awaited_once()
    svc.repo.backfill_template_chapter_key.assert_awaited_once_with(
        "coal", "eia_report", ["5.2 地下水"], "地下水环境影响预测"
    )
