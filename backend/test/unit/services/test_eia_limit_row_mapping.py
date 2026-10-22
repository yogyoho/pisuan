"""限值行形 ↔ 扁平指标双向映射单测（P1 合流 Task 2）。

七表异构行形（LIMIT_TABLE_SCHEMAS）在服务边界拍平为 standard_indicators 扁平行；
页面 GET 按 page_row_id 重组回行形。day/night 拆两行是关键用例。
"""

from __future__ import annotations

from yuxi.services.eia_limit_row_mapping import flatten_limit_row, page_row_id_for, regroup_limit_rows


def test_page_row_id_for_deterministic_and_table_scoped():
    """公有化后的派生函数直测：同输入同键（转正幂等契约），不同 table_key 键隔离。"""
    row = {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}
    assert page_row_id_for("gb3096_zone_limits", row) == page_row_id_for("gb3096_zone_limits", dict(row))
    assert page_row_id_for("gb3096_zone_limits", row) != page_row_id_for("gb12348_boundary_limits", row)


def test_flat_rows_direct_map():
    out = flatten_limit_row(
        "gb3838_category_limits",
        {"category": "III类", "pollutant": "COD", "limit_value": 20, "unit": "mg/L"},
    )
    assert out == [
        {
            "pollutant": "COD",
            "metric": "",
            "limit_value": 20,
            "unit": "mg/L",
            "condition": "",
            "category": "III类",
            "period": "",
            "page_row_id": out[0]["page_row_id"],
        }
    ]
    assert len(out[0]["page_row_id"]) == 32  # md5 hexdigest
    assert (
        flatten_limit_row(
            "gb3838_category_limits",
            {"category": "III类", "pollutant": "COD", "limit_value": 20, "unit": "mg/L"},
        )
        == out
    )  # 同输入同键（转正幂等契约）


def test_day_night_splits_two_rows_shared_page_row_id():
    out = flatten_limit_row("gb3096_zone_limits", {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"})
    assert [(r["metric"], r["limit_value"]) for r in out] == [("昼间", 50), ("夜间", 40)]
    assert out[0]["page_row_id"] == out[1]["page_row_id"]
    assert out[0]["category"] == "0类" and out[0]["pollutant"] == ""


def test_a_value_and_phase_maps():
    out = flatten_limit_row("gbt13201_a_value", {"region_type": "工业区", "a_value": 7.5, "unit": "km²/k"})
    assert out[0]["metric"] == "A值" and out[0]["limit_value"] == 7.5 and out[0]["category"] == "工业区"
    out2 = flatten_limit_row(
        "gb20426_emission_limits",
        {"pollutant": "SO2", "phase": "现有", "limit_value": 550, "unit": "mg/m³"},
    )
    assert out2[0]["period"] == "现有" and out2[0]["metric"] == ""


def test_regroup_round_trip_all_shapes():
    cases = [
        ("gb3838_category_limits", {"category": "III类", "pollutant": "COD", "limit_value": 20, "unit": "mg/L"}),
        ("gbt14848_category_limits", {"category": "III类", "pollutant": "总硬度", "limit_value": 450, "unit": "mg/L"}),
        (
            "gb3095_concentration_limits",
            {"pollutant": "SO2", "period": "年平均", "grade": "一级", "limit_value": 20, "unit": "µg/m³"},
        ),
        ("gb3096_zone_limits", {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}),
        ("gb12348_boundary_limits", {"category": "2类", "day": 60, "night": 50, "unit": "dB(A)"}),
        ("gb20426_emission_limits", {"pollutant": "SO2", "phase": "现有", "limit_value": 550, "unit": "mg/m³"}),
        ("gbt13201_a_value", {"region_type": "工业区", "a_value": 7.5, "unit": "km²/k"}),
    ]
    for tk, page_row in cases:
        flat = flatten_limit_row(tk, page_row)
        assert regroup_limit_rows(tk, flat) == [page_row], tk


def test_regroup_merges_day_night_by_page_row_id():
    flat = flatten_limit_row("gb3096_zone_limits", {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"})
    other = flatten_limit_row("gb3096_zone_limits", {"category": "1类", "day": 55, "night": 45, "unit": "dB(A)"})
    mixed = [flat[0], other[0], flat[1], other[1]]  # 打乱顺序
    out = regroup_limit_rows("gb3096_zone_limits", mixed)
    assert out == [
        {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"},
        {"category": "1类", "day": 55, "night": 45, "unit": "dB(A)"},
    ]
