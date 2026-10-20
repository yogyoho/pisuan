"""enrich 表类型打标分流 + 指标结构化单测（Task 14）。

覆盖：标题关键词快路径逐类正反例、LLM 慢路径 fail-closed（判别失败→other→不抽取）、
method 表零 limit_value 产出（映射入 tags）、category/period 结构化字段 + DDL 迁移幂等、
重跑 enrich 幂等。LLM 调用全部 mock、DB 会话全部桩掉：零真实 LLM、零 DB。
宿主运行：cd backend && uv run --frozen --with pytest --with pytest-asyncio
python -m pytest test/unit/extensions/test_regulation_enrich_routing.py -q --noconftest
"""

from types import SimpleNamespace

import pytest

import yuxi.extensions.regulation_library.enrichment_service as enrich_mod
import yuxi.extensions.regulation_library.indicator_extractor as ext_mod
import yuxi.extensions.regulation_library.models as models_mod
import yuxi.extensions.regulation_library.structured_channel as chan_mod
from yuxi.extensions.regulation_library.enrichment_service import enrich_regulation_file, query_indicators
from yuxi.extensions.regulation_library.indicator_extractor import (
    IndicatorExtraction,
    IndicatorRow,
    MethodMapping,
    MethodMappingExtraction,
    parse_indicator_response,
)
from yuxi.extensions.regulation_library.models import _DDL
from yuxi.extensions.regulation_library.table_role_classifier import (
    TableRoleClassifier,
    TableRoleVerdict,
    classify_table_role_by_title,
)


# --------------------------------------------------------------- 通道桩
class FakeOptions:
    def __init__(self, conf):
        self._conf = conf

    async def get(self):
        return self._conf


class FakeAdapter:
    """LangChainChatAdapter 桩：.model.with_structured_output(schema).ainvoke(prompt) + .call(prompt)。"""

    def __init__(self, structured_result=None, structured_exc=None, prompt_content="", prompt_exc=None):
        self.model_name = "fake-fast"
        self.structured_calls = 0
        self.prompt_calls = 0
        self.last_prompt = None
        self.last_schema = None
        self._structured_result = structured_result
        self._structured_exc = structured_exc
        self._prompt_content = prompt_content
        self._prompt_exc = prompt_exc

    @property
    def model(self):
        outer = self

        class _M:
            def with_structured_output(self, schema):
                outer.last_schema = schema
                return self

            async def ainvoke(self, prompt):
                outer.structured_calls += 1
                outer.last_prompt = prompt
                if outer._structured_exc is not None:
                    raise outer._structured_exc
                return outer._structured_result

        return _M()

    async def call(self, prompt):
        self.prompt_calls += 1
        self.last_prompt = prompt
        if self._prompt_exc is not None:
            raise self._prompt_exc
        return SimpleNamespace(content=self._prompt_content)


@pytest.fixture(autouse=True)
def _reset_caches():
    chan_mod.reset_channel_caches()
    models_mod._schema_ready = False
    yield
    chan_mod.reset_channel_caches()
    models_mod._schema_ready = False


def _patch_channel_model(monkeypatch, adapter):
    """通道默认模型解析桩：system_options.fast_model → 注入 adapter。"""
    monkeypatch.setattr(chan_mod, "select_model", lambda spec: adapter)
    monkeypatch.setattr(chan_mod, "system_options", FakeOptions({"fast_model": "fake-spec"}))


def _ext_result(rows):
    return IndicatorExtraction(rows=[IndicatorRow(**r) for r in rows])


# --------------------------------------------------------------- R1 快路径：标题规则
@pytest.mark.parametrize(
    "title,role",
    [
        ("最高允许排放浓度", "limit"),
        ("水质 基本项目标准限值", "limit"),
        ("污染物排放限值", "limit"),
        ("水质 分析方法", "method"),
        ("测定方法", "method"),
        ("检出限", "method"),
        ("评价标准与判据", "criteria"),
        ("水质评价等级划分", "criteria"),
        ("垃圾填埋工艺参数", "param"),
        ("排污系数", "param"),
    ],
)
def test_title_rules_positive(title, role):
    assert classify_table_role_by_title(title) == role


@pytest.mark.parametrize(
    "title",
    ["", "地表水环境质量监测布点", "建设项目竣工环境保护验收监测结果", "土壤分层情况"],
)
def test_title_rules_no_hit_returns_none(title):
    assert classify_table_role_by_title(title) is None


def test_title_rules_first_match_order():
    # 规则按工单顺序先到先得；「限值」与「方法」同时命中归 limit（真实限值表常附测定方法列）
    assert classify_table_role_by_title("限值测定方法") == "limit"


# --------------------------------------------------------------- R1 慢路径：LLM 判别器
@pytest.mark.asyncio
async def test_role_classifier_structured_success():
    adapter = FakeAdapter(structured_result=TableRoleVerdict(table_role="method"))
    clf = TableRoleClassifier(model=adapter)
    assert await clf.classify("GB 3838-2002", "表4", "", "| a | b |") == "method"
    assert adapter.structured_calls == 1 and adapter.prompt_calls == 0
    assert chan_mod._structured_support == {}  # 成功不写探测缓存


@pytest.mark.asyncio
async def test_role_classifier_invalid_verdict_fail_closed_no_blacklist():
    adapter = FakeAdapter(structured_result={"table_role": "限值表"})  # 枚举外取值
    clf = TableRoleClassifier(model=adapter)
    assert await clf.classify("X", "表1", "", "c") == "other"
    assert chan_mod._structured_support == {}  # 输出校验失败不拉黑模型
    assert adapter.prompt_calls == 0  # 判别无效不降级重试（fail-closed）


@pytest.mark.asyncio
async def test_role_classifier_channel_failure_falls_back_to_prompt():
    adapter = FakeAdapter(structured_exc=RuntimeError("timeout"), prompt_content='{"table_role": "criteria"}')
    clf = TableRoleClassifier(model=adapter)
    assert await clf.classify("X", "表2", "", "c") == "criteria"
    assert chan_mod._structured_support == {"fake-fast": False}  # 通道级失败拉黑
    assert adapter.prompt_calls == 1


@pytest.mark.asyncio
async def test_role_classifier_both_channels_fail_is_other():
    adapter = FakeAdapter(structured_exc=RuntimeError("down"), prompt_content="not json")
    clf = TableRoleClassifier(model=adapter)
    assert await clf.classify("X", "表3", "", "c") == "other"


@pytest.mark.asyncio
async def test_role_classifier_blacklisted_model_skips_structured():
    chan_mod._structured_support["fake-fast"] = False
    adapter = FakeAdapter(
        structured_result=TableRoleVerdict(table_role="limit"), prompt_content='{"table_role": "param"}'
    )
    clf = TableRoleClassifier(model=adapter)
    assert await clf.classify("X", "表4", "", "c") == "param"
    assert adapter.structured_calls == 0


@pytest.mark.asyncio
async def test_role_classifier_default_resolves_fast_model(monkeypatch):
    seen = {}
    adapter = FakeAdapter(structured_result=TableRoleVerdict(table_role="other"))

    def fake_select_model(spec):
        seen["spec"] = spec
        return adapter

    monkeypatch.setattr(chan_mod, "select_model", fake_select_model)
    monkeypatch.setattr(chan_mod, "system_options", FakeOptions({"fast_model": "fm-spec"}))
    clf = TableRoleClassifier()
    assert await clf.classify("X", "表1", "", "c") == "other"
    assert seen["spec"] == "fm-spec"


@pytest.mark.asyncio
async def test_role_classifier_no_fast_model_is_other(monkeypatch):
    monkeypatch.setattr(chan_mod, "system_options", FakeOptions({}))
    clf = TableRoleClassifier()
    assert await clf.classify("X", "表1", "", "c") == "other"


@pytest.mark.asyncio
async def test_role_classifier_prompt_carries_title_and_capped_excerpt():
    adapter = FakeAdapter(structured_result=TableRoleVerdict(table_role="other"))
    clf = TableRoleClassifier(model=adapter)
    await clf.classify("GB 3838-2002", "表4", "地表水监测结果", "| 检出浓度 |" * 500)
    assert "地表水监测结果" in adapter.last_prompt
    assert len(adapter.last_prompt) < 4000  # 内容截选有上限


# --------------------------------------------------------------- R2/R3：指标抽取通道
@pytest.mark.asyncio
async def test_extract_indicators_structured_category_period(monkeypatch):
    adapter = FakeAdapter(
        structured_result=_ext_result(
            [
                {
                    "pollutant": "SO2",
                    "metric": "年平均浓度限值",
                    "limit_value": 60,
                    "unit": "μg/m³",
                    "condition": "二类区",
                    "category": "二类区",
                    "period": "年平均",
                }
            ]
        )
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_indicators("GB 3095-2012", "表1", "| 因子 | 限值 |")
    assert rows == [
        {
            "pollutant": "SO2",
            "metric": "年平均浓度限值",
            "limit_value": 60,
            "unit": "μg/m³",
            "condition": "二类区",
            "category": "二类区",
            "period": "年平均",
        }
    ]
    assert adapter.structured_calls == 1 and adapter.prompt_calls == 0


@pytest.mark.asyncio
async def test_extract_indicators_filters_incomplete_rows(monkeypatch):
    adapter = FakeAdapter(
        structured_result=_ext_result(
            [
                {"pollutant": "", "metric": "x", "limit_value": 1},
                {"pollutant": "PM10", "metric": "年均", "limit_value": None},
                {"pollutant": "NO2", "metric": "年均", "limit_value": 40},
            ]
        )
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_indicators("X", "表1", "c")
    assert [r["pollutant"] for r in rows] == ["NO2"]


@pytest.mark.asyncio
async def test_extract_indicators_string_limit_value_normalized(monkeypatch):
    adapter = FakeAdapter(
        structured_result=_ext_result(
            [
                {"pollutant": "总汞", "metric": "日均", "limit_value": "≤0.5"},
                {"pollutant": "硫酸盐", "metric": "日均", "limit_value": "0.07~0.09"},
            ]
        )
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_indicators("X", "表2", "c")
    # 字符串归一为数值：方向符号取原值、区间取上限（NUMERIC 列类型安全）
    assert [r["limit_value"] for r in rows] == [0.5, 0.09]


@pytest.mark.asyncio
async def test_extract_indicators_unparseable_limit_value_drops_row(monkeypatch):
    adapter = FakeAdapter(
        structured_result=_ext_result(
            [
                {"pollutant": "坏行", "metric": "日均", "limit_value": "无法检出"},
                {"pollutant": "NO2", "metric": "年均", "limit_value": 40},
            ]
        )
    )
    _patch_channel_model(monkeypatch, adapter)
    logs = []
    monkeypatch.setattr(ext_mod.logger, "warning", lambda msg, *a, **k: logs.append(str(msg)))
    rows = await ext_mod.extract_indicators("GB X-2019", "表2", "c")
    assert [r["pollutant"] for r in rows] == ["NO2"]  # 垃圾串行丢弃，其余行保留
    assert any("GB X-2019" in m and "表2" in m and "无法检出" in m for m in logs)  # warning 带 doc_code/unit_no/原文


@pytest.mark.asyncio
async def test_extract_indicators_prompt_fallback(monkeypatch):
    adapter = FakeAdapter(
        structured_exc=RuntimeError("structured unsupported"),
        prompt_content=(
            '{"rows": [{"pollutant": "NO2", "metric": "年均", "limit_value": 40,'
            ' "category": "二级", "period": "年平均"}]}'
        ),
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_indicators("X", "表1", "c")
    assert rows[0]["limit_value"] == 40 and rows[0]["category"] == "二级"
    assert chan_mod._structured_support == {"fake-fast": False}
    assert adapter.structured_calls == 1 and adapter.prompt_calls == 1


@pytest.mark.asyncio
async def test_extract_indicators_prompt_fallback_bare_array(monkeypatch):
    adapter = FakeAdapter(
        structured_exc=RuntimeError("x"),
        prompt_content='[{"pollutant": "TSP", "metric": "年均", "limit_value": 200}]',
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_indicators("X", "表1", "c")
    assert rows[0]["pollutant"] == "TSP" and rows[0]["period"] == ""


@pytest.mark.asyncio
async def test_extract_indicators_all_channels_fail_returns_empty(monkeypatch):
    adapter = FakeAdapter(structured_exc=RuntimeError("down"), prompt_content="没有 JSON")
    _patch_channel_model(monkeypatch, adapter)
    assert await ext_mod.extract_indicators("X", "表1", "c") == []


@pytest.mark.asyncio
async def test_channel_invalid_output_no_probe_blacklist(monkeypatch):
    adapter = FakeAdapter(structured_result={"rows": "不是列表"})
    _patch_channel_model(monkeypatch, adapter)
    assert await ext_mod.extract_indicators("X", "表1", "c") == []
    assert chan_mod._structured_support == {}  # 校验失败不拉黑，下次仍尝试结构化


@pytest.mark.asyncio
async def test_extract_indicators_truncation_logged(monkeypatch):
    adapter = FakeAdapter(structured_result=_ext_result([]))
    _patch_channel_model(monkeypatch, adapter)
    logs = []
    monkeypatch.setattr(ext_mod.logger, "info", lambda msg, *a, **k: logs.append(str(msg)))
    cap = ext_mod._PROMPT_TEXT_CAP
    await ext_mod.extract_indicators("GB 3838-2002", "表4", "x" * (cap + 1000))
    assert any("GB 3838-2002" in m and "表4" in m and str(cap + 1000) in m and str(cap) in m for m in logs)
    assert "x" * (cap + 1) not in adapter.last_prompt  # 实际送入模型的内容已截断


@pytest.mark.asyncio
async def test_extract_indicators_timeout_passed_to_channel(monkeypatch):
    # 大表 JSON 生成超 60s 默认上限会 fail-closed（容器实测 GB 3838 表1 双通道超时）：必须带提额 timeout
    captured = {}

    async def _spy(schema_type, prompt, *, timeout=None):
        captured["timeout"] = timeout
        return IndicatorExtraction(rows=[])

    monkeypatch.setattr(ext_mod, "call_structured", _spy)
    await ext_mod.extract_indicators("X", "表1", "c")
    assert captured["timeout"] == ext_mod._EXTRACT_TIMEOUT_SECONDS
    assert ext_mod._EXTRACT_TIMEOUT_SECONDS > 60


# --------------------------------------------------------------- method 表映射抽取
@pytest.mark.asyncio
async def test_extract_method_mappings_structured(monkeypatch):
    adapter = FakeAdapter(
        structured_result=MethodMappingExtraction(
            mappings=[MethodMapping(pollutant="COD", method_name="重铬酸盐法", method_code="HJ 828-2017")]
        )
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_method_mappings("GB 3838-2002", "表4", "| 因子 | 方法 |")
    assert rows == [{"pollutant": "COD", "method_name": "重铬酸盐法", "method_code": "HJ 828-2017"}]


@pytest.mark.asyncio
async def test_extract_method_mappings_fail_closed(monkeypatch):
    adapter = FakeAdapter(structured_exc=RuntimeError("down"), prompt_content="无")
    _patch_channel_model(monkeypatch, adapter)
    assert await ext_mod.extract_method_mappings("X", "表4", "c") == []


# --------------------------------------------------------------- R1 接线：enrich 分流
T_LIMIT = "表1 污染物排放限值\n| 因子 | 限值 |\n| SO2 | 0.5 |"
T_METHOD = "表2 水质分析方法\n| 因子 | 方法 |\n| COD | 重铬酸盐法 |"
T_AMBIG = "表3 监测布点位置\n| 点位 | 位置 |\n| 1 | 厂址 |"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeCount:
    """scalar_one 结果桩（enrich 冲突守护探测：0 = 无 expert 手工行）。"""

    def scalar_one(self):
        return 0


class FakeSession:
    """假会话：knowledge_chunks 查询返回预置 chunks，其余语句仅记录。"""

    def __init__(self, chunks):
        self.chunks = chunks
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append((sql, dict(params or {})))
        if "from knowledge_chunks" in sql.lower():
            return FakeResult(self.chunks)
        if "count(*)" in sql.lower():
            return FakeCount()
        return FakeResult([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _mk_chunk(cid, content, tags=None):
    return SimpleNamespace(chunk_id=cid, content=content, tags=dict(tags or {}))


def _patch_pg(monkeypatch, chunks):
    holder = []

    def _ctx():
        s = FakeSession(chunks)
        holder.append(s)
        return s

    monkeypatch.setattr(enrich_mod.pg_manager, "get_async_session_context", _ctx)
    return holder


def _patch_graph(monkeypatch):
    writes = []

    class FakeGraphWriter:
        def write_document_graph(self, doc_code, doc_name, doc_type, units, indicators):
            writes.append({"units": units, "indicators": indicators})
            return {"nodes": len(units) + 1, "relationships": len(units)}

        def close(self):
            pass

    monkeypatch.setattr(enrich_mod, "RegulationGraphWriter", FakeGraphWriter)
    return writes


async def _noop():
    pass


class StubRoleClassifier:
    def __init__(self, role="other"):
        self.role = role
        self.calls = []

    async def classify(self, doc_code, unit_no, title, content_excerpt):
        self.calls.append(unit_no)
        return self.role


class StubExtractor:
    def __init__(self, rows=None, mappings=None):
        self.rows = rows or []
        self.mappings = mappings or []
        self.extract_calls = []
        self.method_calls = []

    async def extract_indicators(self, doc_code, unit_no, content):
        self.extract_calls.append(unit_no)
        return [dict(r) for r in self.rows]

    async def extract_method_mappings(self, doc_code, unit_no, content):
        self.method_calls.append(unit_no)
        return [dict(m) for m in self.mappings]


def _patch_role_classifier(monkeypatch, stub):
    monkeypatch.setattr(enrich_mod, "TableRoleClassifier", lambda: stub)


def _patch_extractor(monkeypatch, stub):
    monkeypatch.setattr(enrich_mod.indicator_extractor, "extract_indicators", stub.extract_indicators)
    monkeypatch.setattr(enrich_mod.indicator_extractor, "extract_method_mappings", stub.extract_method_mappings)


IND_ROW = {
    "pollutant": "SO2",
    "metric": "日平均",
    "limit_value": 0.5,
    "unit": "mg/L",
    "condition": "",
    "category": "III类",
    "period": "24小时",
}
METHOD_MAP = [{"pollutant": "COD", "method_name": "重铬酸盐法", "method_code": "HJ 828-2017"}]


@pytest.mark.asyncio
async def test_routing_limit_extracts_and_method_maps_to_tags(monkeypatch):
    chunks = [_mk_chunk("c1", T_LIMIT), _mk_chunk("c2", T_METHOD)]
    holder = _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    clf = StubRoleClassifier()
    _patch_role_classifier(monkeypatch, clf)
    ext = StubExtractor(rows=[dict(IND_ROW)], mappings=[dict(METHOD_MAP[0])])
    _patch_extractor(monkeypatch, ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert result["indicators"] == 1
    assert result["table_roles"] == {"limit": 1, "method": 1, "criteria": 0, "param": 0, "other": 0}
    assert ext.extract_calls == ["表1"]  # 仅 limit 表进指标抽取
    assert ext.method_calls == ["表2"]
    assert clf.calls == []  # 快路径全命中，未走 LLM
    by_id = {c.chunk_id: c for c in chunks}
    assert by_id["c1"].tags["table_role"] == "limit"
    assert by_id["c2"].tags["table_role"] == "method"
    assert by_id["c2"].tags["method_map"] == METHOD_MAP
    # 指标 INSERT 携带 category/period
    inserts = [(sql, p) for s in holder for sql, p in s.statements if "INSERT INTO standard_indicators" in sql]
    assert inserts and inserts[0][1]["cat"] == "III类" and inserts[0][1]["prd"] == "24小时"
    assert "category" in inserts[0][0] and "period" in inserts[0][0]


@pytest.mark.asyncio
async def test_routing_method_table_zero_indicators(monkeypatch):
    chunks = [_mk_chunk("c1", T_METHOD)]
    _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    _patch_role_classifier(monkeypatch, StubRoleClassifier())
    ext = StubExtractor(rows=[dict(IND_ROW)])  # 若被误调用会产出行
    _patch_extractor(monkeypatch, ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2002", "标准", "technical_standard")

    assert result["indicators"] == 0  # method 表零 limit_value 产出
    assert ext.extract_calls == []
    assert ext.method_calls == ["表2"]


@pytest.mark.asyncio
async def test_routing_ambiguous_title_slow_path_other_no_extract(monkeypatch):
    chunks = [_mk_chunk("c1", T_AMBIG)]
    _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    clf = StubRoleClassifier(role="other")
    _patch_role_classifier(monkeypatch, clf)
    ext = StubExtractor(rows=[dict(IND_ROW)])
    _patch_extractor(monkeypatch, ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert clf.calls == ["表3"]  # 标题歧义 → 慢路径
    assert result["indicators"] == 0  # other → 不抽取
    assert chunks[0].tags["table_role"] == "other"


@pytest.mark.asyncio
async def test_routing_slow_path_param_tagged_not_extracted(monkeypatch):
    chunks = [_mk_chunk("c1", T_AMBIG)]
    _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    _patch_role_classifier(monkeypatch, StubRoleClassifier(role="param"))
    ext = StubExtractor(rows=[dict(IND_ROW)])
    _patch_extractor(monkeypatch, ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert result["table_roles"]["param"] == 1
    assert result["indicators"] == 0
    assert chunks[0].tags["table_role"] == "param"


@pytest.mark.asyncio
async def test_reenrich_idempotent_delete_before_insert(monkeypatch):
    chunks = [_mk_chunk("c1", T_LIMIT)]
    holder = _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    _patch_role_classifier(monkeypatch, StubRoleClassifier())
    ext = StubExtractor(rows=[dict(IND_ROW)])
    _patch_extractor(monkeypatch, ext)

    r1 = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")
    r2 = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert r1["indicators"] == r2["indicators"] == 1
    del_sessions = [s for s in holder if any("DELETE FROM standard_indicators" in sql for sql, _ in s.statements)]
    assert len(del_sessions) == 2  # 每次运行先删旧再插新
    for s in del_sessions:
        i_del = next(i for i, (sql, _) in enumerate(s.statements) if "DELETE" in sql)
        i_ins = min(i for i, (sql, _) in enumerate(s.statements) if "INSERT INTO standard_indicators" in sql)
        assert i_del < i_ins


@pytest.mark.asyncio
async def test_insert_path_limit_value_all_numeric(monkeypatch):
    # INSERT 路径类型守护：抽取出口归一后，DB 桩收到的 limit_value 全部为 float/None
    adapter = FakeAdapter(
        structured_result=_ext_result(
            [
                {"pollutant": "总汞", "metric": "日均", "limit_value": "≤0.5"},
                {"pollutant": "硫酸盐", "metric": "日均", "limit_value": "0.07~0.09"},
                {"pollutant": "坏行", "metric": "日均", "limit_value": "垃圾串"},
            ]
        )
    )
    _patch_channel_model(monkeypatch, adapter)
    rows = await ext_mod.extract_indicators("GB X", "表1", "c")
    assert len(rows) == 2  # 垃圾串行已在抽取出口丢弃

    chunks = [_mk_chunk("c1", T_LIMIT)]
    holder = _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    _patch_role_classifier(monkeypatch, StubRoleClassifier())
    _patch_extractor(monkeypatch, StubExtractor(rows=rows))

    await enrich_regulation_file("kb1", "f1", "GB X", "标准", "technical_standard")

    inserts = [p for s in holder for sql, p in s.statements if "INSERT INTO standard_indicators" in sql]
    assert len(inserts) == 2
    assert all(p["v"] is None or isinstance(p["v"], float) for p in inserts)
    assert sorted(p["v"] for p in inserts) == [0.09, 0.5]


# --------------------------------------------------------------- R2：DDL 迁移幂等 + 查询
def test_ddl_statements_all_idempotent():
    stmts = [s.strip() for s in _DDL.strip().split(";") if s.strip()]
    assert len(stmts) >= 5
    assert all("IF NOT EXISTS" in s for s in stmts)  # 全部语句可重复执行
    assert any("ADD COLUMN IF NOT EXISTS category" in s for s in stmts)
    assert any("ADD COLUMN IF NOT EXISTS period" in s for s in stmts)


@pytest.mark.asyncio
async def test_ensure_schema_executes_new_alter(monkeypatch):
    s = FakeSession([])

    monkeypatch.setattr(models_mod.pg_manager, "get_async_session_context", lambda: s)
    await models_mod.ensure_schema()
    executed = [sql for sql, _ in s.statements]
    assert any("ADD COLUMN IF NOT EXISTS category" in sql for sql in executed)
    assert any("ADD COLUMN IF NOT EXISTS period" in sql for sql in executed)


@pytest.mark.asyncio
async def test_query_indicators_selects_category_period(monkeypatch):
    holder = _patch_pg(monkeypatch, [])
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    assert await query_indicators("GB X-2019", "SO2") == []
    sql = holder[0].statements[0][0]
    assert "category" in sql and "period" in sql


# --------------------------------------------------------------- R2：parse 通道默认值
def test_parse_indicator_response_defaults_category_period():
    text = '[{"pollutant": "SO2", "metric": "年均", "limit_value": 60}]'
    rows = parse_indicator_response(text)
    assert rows[0]["category"] == "" and rows[0]["period"] == ""


def test_parse_indicator_response_keeps_category_period():
    text = '[{"pollutant": "SO2", "metric": "24小时", "limit_value": 150, "category": "二级", "period": "24小时"}]'
    rows = parse_indicator_response(text)
    assert rows[0]["category"] == "二级" and rows[0]["period"] == "24小时"


@pytest.mark.asyncio
async def test_enrich_preserves_existing_chunk_tags(monkeypatch):
    # 入库期预置的既有 tags 在 enrich 后保留，富化新键（table_role/method_map/unit）并存
    chunks = [
        _mk_chunk("c1", T_LIMIT, tags={"doc_code": "GB X-2019", "source": "ingest"}),
        _mk_chunk("c2", T_METHOD, tags={"source": "ingest"}),
    ]
    _patch_pg(monkeypatch, chunks)
    _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    _patch_role_classifier(monkeypatch, StubRoleClassifier())
    _patch_extractor(monkeypatch, StubExtractor(mappings=[dict(METHOD_MAP[0])]))

    await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    by_id = {c.chunk_id: c for c in chunks}
    assert by_id["c1"].tags["source"] == "ingest"  # 既有键保留
    assert by_id["c1"].tags["doc_code"] == "GB X-2019"
    assert by_id["c1"].tags["table_role"] == "limit"  # 新键并存
    assert by_id["c1"].tags["unit_no"] == "表1"
    assert by_id["c2"].tags["source"] == "ingest"
    assert by_id["c2"].tags["method_map"] == METHOD_MAP
