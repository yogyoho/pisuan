"""R1 表格单元拆分（split_table_units）+ enrich 多表接线单测（Task 15）。

覆盖：<table> 边界拆分、标题/续表/孤立单位行/占位 unit_no 推断、未闭合残段丢弃、
enrich 多表 chunk 的 tags["table_units"] 形态与单表标量形态向后兼容。
LLM 调用全部 mock、DB 会话全部桩掉：零真实 LLM、零 DB。
宿主运行：cd backend && uv run --frozen --with pytest --with pytest-asyncio
python -m pytest test/unit/extensions/test_table_splitter.py -q --noconftest
"""

from types import SimpleNamespace

import pytest

import pisuan.extensions.regulation_library.enrichment_service as enrich_mod
import pisuan.extensions.regulation_library.table_splitter as splitter_mod
from pisuan.extensions.regulation_library.enrichment_service import enrich_regulation_file
from pisuan.extensions.regulation_library.table_splitter import split_table_units


def _tbl(body="a"):
    return f"<table><tr><td>{body}</td></tr></table>"


# --------------------------------------------------------------- split_table_units：unit_no 推断
def test_title_adjacent_table():
    units = split_table_units(f"表1地表水环境质量标准基本项目标准限值\n{_tbl()}")
    assert len(units) == 1
    assert units[0]["unit_no"] == "表1"
    assert units[0]["title"] == "地表水环境质量标准基本项目标准限值"
    assert units[0]["unit_type"] == "table"
    assert units[0]["table_content"] == _tbl()


@pytest.mark.parametrize("marker,expected", [("表 2-1 补充项目", "表2-1"), ("表12 特定项目", "表12")])
def test_title_number_formats(marker, expected):
    units = split_table_units(f"{marker}\n{_tbl()}")
    assert units[0]["unit_no"] == expected


def test_title_with_unit_suffix_kept():
    units = split_table_units(f"表2集中式生活饮用水地表水源地补充项目标准限值 单位：mg/L\n{_tbl()}")
    assert units[0]["unit_no"] == "表2"
    assert units[0]["title"] == "集中式生活饮用水地表水源地补充项目标准限值 单位：mg/L"


@pytest.mark.parametrize(
    "marker,expected",
    [("表2（完）", "表2（续）"), ("表5（完）", "表5（续）"), ("表6（续）", "表6（续）")],
)
def test_continuation_with_explicit_number(marker, expected):
    units = split_table_units(f"{marker}\n{_tbl()}")
    assert units[0]["unit_no"] == expected
    assert units[0]["title"] == ""


def test_bare_continuation_after_previous_table():
    content = f"表3 特定项目标准限值\n{_tbl('3')}\n续表\n{_tbl('3b')}"
    units = split_table_units(content)
    assert [u["unit_no"] for u in units] == ["表3", "表3（续）"]


def test_bare_continuation_without_previous():
    units = split_table_units(f"续表\n{_tbl()}")
    assert units[0]["unit_no"] == "表?（续）"


def test_isolated_unit_line_skipped_to_find_title():
    # GB 8978 实况形态：标题与表格之间夹孤立单位行，跳过纯单位行向前找
    units = split_table_units(f"表4 检测方法\nmg/L\n{_tbl()}")
    assert units[0]["unit_no"] == "表4"
    assert units[0]["title"] == "检测方法"


def test_isolated_unit_line_without_title_is_placeholder():
    units = split_table_units(f"mg/L\n{_tbl()}")
    assert units[0]["unit_no"] == "表?"
    assert units[0]["title"] == ""


def test_title_found_beyond_200_chars():
    # parse_chunk_unit 只看开头 200 字符；拆分器不受限（4096 大 chunk 场景）
    units = split_table_units("前言" * 200 + f"\n表1 基本项目\n{_tbl()}")
    assert units[0]["unit_no"] == "表1"


# --------------------------------------------------------------- split_table_units：多表与残段
def test_multi_table_chunk_in_document_order():
    content = (
        "地表水环境质量标准\n"
        f"表1 基本项目标准限值\n{_tbl('1')}\n"
        f"表2 补充项目标准限值\n{_tbl('2')}\n"
        f"表3 特定项目标准限值\n{_tbl('3')}"
    )
    units = split_table_units(content)
    assert [u["unit_no"] for u in units] == ["表1", "表2", "表3"]
    assert [u["title"] for u in units] == ["基本项目标准限值", "补充项目标准限值", "特定项目标准限值"]
    assert "1" in units[0]["table_content"] and "3" in units[2]["table_content"]


def test_title_region_never_crosses_previous_table():
    # 标题只在「本表开始标签与上一表结束标签」之间找，不跨表认领更早的标题
    content = f"表1 甲\n{_tbl('1')}\n正文段落。\n{_tbl('2')}"
    units = split_table_units(content)
    assert [u["unit_no"] for u in units] == ["表1", "表?"]


def test_unclosed_table_only_dropped():
    assert split_table_units("表1 基本项目\n<table><tr><td>被拦腰切") == []


def test_closed_table_kept_unclosed_tail_dropped():
    units = split_table_units(f"{_tbl('ok')}\n表2 后表\n<table><tr><td>残")
    assert len(units) == 1
    assert "ok" in units[0]["table_content"]


def test_unclosed_residual_logged_debug(monkeypatch):
    logs = []
    monkeypatch.setattr(splitter_mod.logger, "debug", lambda msg, *a, **k: logs.append(str(msg)))
    split_table_units("表1 x\n<table><tr>")
    assert any("未闭合" in m for m in logs)


def test_plain_and_markdown_table_return_empty():
    assert split_table_units("正文段落，无表格。") == []
    assert split_table_units("") == []
    # 竖线 markdown 表无 <table> 边界，不归本函数管（仍走 parse_chunk_unit 老路）
    assert split_table_units("表1 限值\n| 因子 | 限值 |\n| SO2 | 0.5 |") == []


# --------------------------------------------------------------- enrich 接线：桩与素材
T_MULTI = (
    "地表水环境质量标准\n"
    f"表1 地表水环境质量标准基本项目标准限值\n{_tbl('1')}\n"
    f"表2 集中式生活饮用水地表水源地补充项目标准限值\n{_tbl('2')}\n"
    f"表3 地表水环境质量标准特定项目标准限值\n{_tbl('3')}"
)
T_HEAD_CLAUSE_MULTI = (
    "1 适用范围\n"
    + "本标准适用于中华人民共和国领域内江河湖泊水库。" * 15
    + "\n"
    + f"表1 基本项目标准限值\n{_tbl('1')}\n"
    + f"表2 补充项目标准限值\n{_tbl('2')}"
)
T_SINGLE_HTML = "表1 监测布点位置\n" + _tbl("s")
T_UNCLOSED = "表1 基本项目标准限值\n<table><tr><td>切"
T_MARKDOWN = "表1 污染物排放限值\n| 因子 | 限值 |\n| SO2 | 0.5 |"
T_MULTI_METHOD = f"表1 污染物排放限值\n{_tbl('1')}\n表2 水质分析方法\n{_tbl('2')}"

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
    def _ctx():
        return FakeSession(chunks)

    monkeypatch.setattr(enrich_mod.pg_manager, "get_async_session_context", _ctx)


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


def _wire(monkeypatch, chunks, clf, ext):
    _patch_pg(monkeypatch, chunks)
    writes = _patch_graph(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    monkeypatch.setattr(enrich_mod, "TableRoleClassifier", lambda: clf)
    monkeypatch.setattr(enrich_mod.indicator_extractor, "extract_indicators", ext.extract_indicators)
    monkeypatch.setattr(enrich_mod.indicator_extractor, "extract_method_mappings", ext.extract_method_mappings)
    return writes


# --------------------------------------------------------------- enrich 接线：多表 chunk
@pytest.mark.asyncio
async def test_multi_table_chunk_writes_table_units_not_scalars(monkeypatch):
    chunks = [_mk_chunk("c0", T_MULTI)]
    _wire(monkeypatch, chunks, StubRoleClassifier(), StubExtractor())

    result = await enrich_regulation_file("kb1", "f1", "GB 3838-2002", "地表水", "technical_standard")

    assert result["tables"] == 3 and result["units"] == 3
    tags = chunks[0].tags
    # 多表 chunk 不写标量 unit_no/table_role（宁可缺失不可说谎），写 table_units 清单
    assert "unit_no" not in tags and "table_role" not in tags
    assert [u["unit_no"] for u in tags["table_units"]] == ["表1", "表2", "表3"]
    assert tags["table_units"][0]["title"] == "地表水环境质量标准基本项目标准限值"
    # 标题关键词快路径逐单元命中（三个标题都带「限值」）
    assert [u["table_role"] for u in tags["table_units"]] == ["limit", "limit", "limit"]


@pytest.mark.asyncio
async def test_multi_table_limit_extracted_per_unit(monkeypatch):
    chunks = [_mk_chunk("c0", T_MULTI)]
    writes = _wire(monkeypatch, chunks, StubRoleClassifier(), StubExtractor(rows=[dict(IND_ROW)]))

    result = await enrich_regulation_file("kb1", "f1", "GB 3838-2002", "地表水", "technical_standard")

    assert result["indicators"] == 3  # 分流循环按表格单元逐个进
    assert [i["unit_no"] for i in writes[0]["indicators"]] == ["表1", "表2", "表3"]  # 行归属逐表单元


@pytest.mark.asyncio
async def test_multi_table_method_map_lands_in_unit_entry(monkeypatch):
    # 表1 限值（快路径 limit）、表2 方法（快路径 method）：映射逐单元入 table_units
    chunks = [_mk_chunk("c0", T_MULTI_METHOD)]
    ext = StubExtractor(rows=[dict(IND_ROW)], mappings=[dict(METHOD_MAP[0])])
    _wire(monkeypatch, chunks, StubRoleClassifier(), ext)

    await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert ext.extract_calls == ["表1"] and ext.method_calls == ["表2"]
    units = chunks[0].tags["table_units"]
    assert units[0]["table_role"] == "limit" and "method_map" not in units[0]
    assert units[1]["table_role"] == "method"
    assert units[1]["method_map"] == METHOD_MAP


@pytest.mark.asyncio
async def test_continuation_unit_inherits_base_role(monkeypatch):
    # 续表（表3（续））标题无关键词：按主表序号继承角色，不再走 LLM 判别（容器实测 6 连 validation error 教训）
    content = f"表3 地表水环境质量标准特定项目标准限值\n{_tbl('3')}\n表3（续）\n{_tbl('3b')}"
    chunks = [_mk_chunk("c0", content)]
    clf = StubRoleClassifier(role="other")  # 若误走 LLM 会判成 other，断言即失败
    ext = StubExtractor(rows=[dict(IND_ROW)])
    writes = _wire(monkeypatch, chunks, clf, ext)

    result = await enrich_regulation_file("kb1", "f1", "GB 3838-2002", "地表水", "technical_standard")

    assert clf.calls == []  # 快路径（表3）+ 继承（表3（续）），LLM 零调用
    assert ext.extract_calls == ["表3", "表3（续）"]  # 续表片段照常独立抽取
    assert result["indicators"] == 2
    assert [i["unit_no"] for i in writes[0]["indicators"]] == ["表3", "表3（续）"]
    assert [u["table_role"] for u in chunks[0].tags["table_units"]] == ["limit", "limit"]


@pytest.mark.asyncio
async def test_orphan_continuation_without_base_falls_to_llm(monkeypatch):
    # 孤立「续表」（无主表可继承）：仍走 LLM 慢路径，fail-closed 不抽取
    chunks = [_mk_chunk("c0", f"续表\n{_tbl()}")]
    clf = StubRoleClassifier(role="other")
    ext = StubExtractor(rows=[dict(IND_ROW)])
    _wire(monkeypatch, chunks, clf, ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert clf.calls == ["表?（续）"]  # memo 未命中（表? 无主表），落 LLM
    assert ext.extract_calls == [] and result["indicators"] == 0


@pytest.mark.asyncio
async def test_head_clause_kept_alongside_multi_tables(monkeypatch):
    # chunk 头部非表格结构单元照旧保留（parse 的表识别被拆分结果取代）
    chunks = [_mk_chunk("c0", T_HEAD_CLAUSE_MULTI)]
    _wire(monkeypatch, chunks, StubRoleClassifier(), StubExtractor())

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert result["tables"] == 2
    tags = chunks[0].tags
    assert tags["unit_no"] == "1" and tags["unit_type"] == "clause"  # 头部条款标量保留
    assert [u["unit_no"] for u in tags["table_units"]] == ["表1", "表2"]


@pytest.mark.asyncio
async def test_multi_table_reenrich_idempotent_tags(monkeypatch):
    chunks = [_mk_chunk("c0", T_MULTI)]
    _wire(monkeypatch, chunks, StubRoleClassifier(), StubExtractor())

    await enrich_regulation_file("kb1", "f1", "GB 3838-2002", "地表水", "technical_standard")
    snapshot = dict(chunks[0].tags)
    await enrich_regulation_file("kb1", "f1", "GB 3838-2002", "地表水", "technical_standard")

    assert chunks[0].tags == snapshot  # 幂等重跑 tags 形态稳定


# --------------------------------------------------------------- enrich 接线：单表/残段/老路
@pytest.mark.asyncio
async def test_single_html_table_chunk_keeps_scalar_tags(monkeypatch):
    chunks = [_mk_chunk("c1", T_SINGLE_HTML)]
    _wire(monkeypatch, chunks, StubRoleClassifier(), StubExtractor())

    await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    tags = chunks[0].tags
    assert tags["unit_no"] == "表1"  # 单表 chunk 标量形态与现状一致（向后兼容）
    assert tags["unit_type"] == "table" and tags["table_role"] == "other"
    assert "table_units" not in tags


@pytest.mark.asyncio
async def test_unclosed_table_chunk_dropped_not_extracted(monkeypatch):
    chunks = [_mk_chunk("c1", T_UNCLOSED)]
    ext = StubExtractor(rows=[dict(IND_ROW)])
    _wire(monkeypatch, chunks, StubRoleClassifier(), ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert result["tables"] == 0 and result["units"] == 0
    assert ext.extract_calls == []  # 残段丢弃不识别（宁可漏不可错）
    assert "unit_no" not in chunks[0].tags


@pytest.mark.asyncio
async def test_markdown_table_chunk_legacy_path_unchanged(monkeypatch):
    chunks = [_mk_chunk("c1", T_MARKDOWN)]
    ext = StubExtractor(rows=[dict(IND_ROW)])
    _wire(monkeypatch, chunks, StubRoleClassifier(), ext)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert ext.extract_calls == ["表1"]
    tags = chunks[0].tags
    assert tags["unit_no"] == "表1" and tags["table_role"] == "limit"  # 快路径标题规则照旧
    assert "table_units" not in tags
    assert result["tables"] == 1
