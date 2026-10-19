"""eia_limit_extract_core 单测：区块定位 / 表格+行内解析 / 归一 / 聚合置信。"""

from yuxi.services.eia_limit_extract_core import (
    aggregate_records,
    locate_standard_blocks,
    norm_code,
    parse_block,
    table_key_for,
)

WINDOW = """## 1.4 环境质量标准

项目所在区域环境空气质量执行《环境空气质量标准》(GB3095-2012)二级标准，见下表：

| 污染物 | 取值时间 | 浓度限值 | 单位 |
| ------ | -------- | -------- | ---- |
| SO2 | 1小时 | 0.50 | mg/m3 |
| SO2 | 24小时 | 0.15 | mg/m3 |
| PM10 | 24小时 | 0.15 | mg/m3 |

地表水执行《地表水环境质量标准》(GB3838-2002)III类标准：COD 标准限值 20 mg/L，
氨氮 1.0 mg/L。噪声执行《声环境质量标准》(GB 3096-2008)2类标准。
"""


def test_norm_code_strips_noise():
    assert norm_code("GB/15618-2018") == norm_code("GB 15618—2018") == norm_code("GB15618-2018")


def test_table_key_known_and_unknown():
    assert table_key_for("GB 3095-2012") == "gb3095_concentration_limits"
    assert table_key_for("GB3838-2002") == "gb3838_category_limits"
    assert table_key_for("GB 8978-1996") is None  # 候选


def test_locate_blocks_finds_codes():
    blocks = locate_standard_blocks(WINDOW)
    codes = {norm_code(b.code) for b in blocks}
    assert {"GB3095-2012", "GB3838-2002", "GB3096-2008"} <= codes
    assert all(b.lines for b in blocks)


def test_parse_block_table_rows_schema_mapped():
    b3095 = next(b for b in locate_standard_blocks(WINDOW) if norm_code(b.code) == "GB3095-2012")
    rows = parse_block(b3095)
    assert {"pollutant": "SO₂", "period": "1小时", "grade": "二级标准", "limit_value": 0.5, "unit": "mg/m³"} in rows
    assert {"pollutant": "PM10", "period": "24小时", "grade": "二级标准", "limit_value": 0.15, "unit": "mg/m³"} in rows


def test_parse_block_inline_rows():
    b3838 = next(b for b in locate_standard_blocks(WINDOW) if norm_code(b.code) == "GB3838-2002")
    rows = parse_block(b3838)
    assert {"category": "III类", "pollutant": "COD", "limit_value": 20.0, "unit": "mg/L"} in rows
    assert {"category": "III类", "pollutant": "氨氮", "limit_value": 1.0, "unit": "mg/L"} in rows


def test_aggregate_confidence():
    def rec(v, rid):
        return {
            "code": "GB 3095-2012",
            "table_key": "gb3095_concentration_limits",
            "row": {"pollutant": "SO₂", "period": "24小时", "grade": "二级标准", "limit_value": v, "unit": "mg/m³"},
            "source": {"report_id": rid, "anchor": "ch1"},
        }

    out = aggregate_records([rec(0.15, "001-wps"), rec(0.15, "038-2024-7-9"), rec(0.5, "039-r")])
    assert len(out) == 1 and out[0]["confidence"] == "conflict"
    assert out[0]["row"]["conflict_values"] == [0.15, 0.5]
    assert len(out[0]["sources"]) == 3
