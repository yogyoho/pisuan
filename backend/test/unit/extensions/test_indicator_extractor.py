"""指标提取器测试：LLM 响应解析（LLM 调用 mock）"""

from yuxi.extensions.regulation_library.indicator_extractor import parse_indicator_response


def test_parse_valid_response():
    text = """[
      {"pollutant": "SO2", "metric": "年平均浓度限值", "limit_value": 60,
       "unit": "μg/m³", "condition": "二类区"},
      {"pollutant": "NO2", "metric": "年平均浓度限值", "limit_value": 40,
       "unit": "μg/m³", "condition": "二类区"}
    ]"""
    rows = parse_indicator_response(text)
    assert len(rows) == 2
    assert rows[0]["pollutant"] == "SO2"
    assert rows[0]["limit_value"] == 60


def test_parse_with_code_fence():
    text = (
        '```json\n[{"pollutant": "TSP", "metric": "日均", "limit_value": 300, "unit": "μg/m³", "condition": ""}]\n```'
    )
    rows = parse_indicator_response(text)
    assert len(rows) == 1


def test_parse_invalid_returns_empty():
    assert parse_indicator_response("没有 JSON") == []
    assert parse_indicator_response("") == []


def test_rows_missing_required_fields_skipped():
    text = '[{"pollutant": "SO2"}, {"pollutant": "NO2", "metric": "年均", "limit_value": 40, "unit": "μg/m³"}]'
    rows = parse_indicator_response(text)
    assert len(rows) == 1
    assert rows[0]["pollutant"] == "NO2"
