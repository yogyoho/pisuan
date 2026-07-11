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
