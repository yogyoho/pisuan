"""query_indicators 分层派生与锚点 join 纯函数单测（P1 合流 Task 6）。"""

from yuxi.extensions.regulation_library.enrichment_service import _anchor_maps, _layer_of


def test_layer_of_three_layers():
    assert _layer_of("expert", "2026-10-22T00:00:00") == "authority"
    assert _layer_of("enrich", "2026-10-22T00:00:00") == "reviewed"
    assert _layer_of("enrich", None) == "candidate"


def test_anchor_maps_from_standards_index():
    tier_by_code, nv_by_ref = _anchor_maps(
        {
            "standards": [
                {"code": "GB 3838-2002", "tier": "national"},
                {"code": "GB/T 14848-2017", "tier": "national"},
            ],
            "limit_tables": {
                "gbt14848_category_limits": {"code_ref": "GB/T 14848-2017", "needs_verification": True},
                "_comment": "metadata key, not a limit table",
            },
        }
    )
    assert tier_by_code.get("GB/T 14848-2017") == "national"
    assert nv_by_ref.get("gbt14848_category_limits") is True
    assert "_comment" not in nv_by_ref  # 字符串项被 isinstance 守卫排除
