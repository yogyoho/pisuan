"""标准与限值库面板改版 W1 后端单测（2026-10-20 工单）。

覆盖：verified_at/verified_by/source 三列 DDL 迁移幂等、核验/撤销核验落库、手工标准 CRUD
（doc_code 归一化查重 / 行数上限 / limit_value 数值归一 / 非 expert 行 409 守护）、
enrich 冲突守护（expert 行在场时不发生 DELETE）、缺源候选聚合+差集纯函数。
LLM 全 mock、DB 会话全部桩掉：零真实 LLM、零 DB。
宿主运行：cd backend && uv run --frozen --with pytest --with pytest-asyncio
python -m pytest test/unit/extensions/test_standards_panel_w1.py -q --noconftest
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

import yuxi.extensions.regulation_library.enrichment_service as enrich_mod
import yuxi.extensions.regulation_library.models as models_mod
from yuxi.extensions.regulation_library.enrichment_service import (
    StandardConflictError,
    create_manual_standard,
    delete_manual_standard,
    enrich_regulation_file,
    query_indicators,
    replace_manual_standard,
    set_unit_verification,
)
from yuxi.extensions.regulation_library.models import _DDL
from yuxi.services.eia_limit_extract_core import (
    aggregate_cited_codes,
    diff_source_candidates,
    norm_code,
)

# --------------------------------------------------------------- 会话桩


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeScalar:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class FakeTuples:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return [SimpleNamespace(_mapping=r) for r in self._rows]


class FakeRowcount:
    def __init__(self, n):
        self.rowcount = n


class StubSession:
    """假会话：按 SQL 关键词路由预置结果，全部语句留痕 (sql, params)。"""

    def __init__(self, chunks=(), indicator_rows=(), distinct_codes=(), expert_count=0, delete_rowcount=1):
        self.chunks = list(chunks)
        self.indicator_rows = list(indicator_rows)
        self.distinct_codes = list(distinct_codes)
        self.expert_count = expert_count
        self.delete_rowcount = delete_rowcount
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        low = sql.lower()
        self.statements.append((sql, dict(params or {})))
        if "from knowledge_chunks" in low:
            return FakeScalars(self.chunks)
        if "count(*)" in low:
            return FakeScalar(self.expert_count)
        if "distinct doc_code" in low:
            return FakeTuples([(c,) for c in self.distinct_codes])
        if low.startswith("select doc_code"):
            return FakeMappings(self.indicator_rows)
        if low.startswith("delete"):
            return FakeRowcount(self.delete_rowcount)
        if low.startswith("update"):
            return FakeRowcount(7)
        return FakeRowcount(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _patch_pg(monkeypatch, **session_kwargs):
    """pg_manager 会话上下文桩：每次进入上下文发一个同配置新会话，全部留痕。"""
    holder = []

    def _ctx():
        s = StubSession(**session_kwargs)
        holder.append(s)
        return s

    monkeypatch.setattr(enrich_mod.pg_manager, "get_async_session_context", _ctx)
    return holder


async def _noop():
    pass


# --------------------------------------------------------------- DDL 迁移


def test_ddl_adds_verification_columns_idempotent():
    stmts = [s.strip() for s in _DDL.strip().split(";") if s.strip()]
    assert all("IF NOT EXISTS" in s for s in stmts)  # 全部语句可重复执行
    assert any("ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ" in s for s in stmts)
    assert any("ADD COLUMN IF NOT EXISTS verified_by TEXT" in s for s in stmts)
    assert any("ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'enrich'" in s for s in stmts)
    assert any("ADD COLUMN IF NOT EXISTS doc_name TEXT" in s for s in stmts)


@pytest.mark.asyncio
async def test_ensure_schema_executes_verification_alter(monkeypatch):
    models_mod._schema_ready = False
    s = StubSession()
    monkeypatch.setattr(models_mod.pg_manager, "get_async_session_context", lambda: s)
    await models_mod.ensure_schema()
    executed = [sql for sql, _ in s.statements]
    assert any("ADD COLUMN IF NOT EXISTS verified_at" in sql for sql in executed)
    assert any("ADD COLUMN IF NOT EXISTS verified_by" in sql for sql in executed)
    assert any("ADD COLUMN IF NOT EXISTS source" in sql for sql in executed)


# --------------------------------------------------------------- 指标查询/核验


@pytest.mark.asyncio
async def test_query_indicators_selects_verification_columns(monkeypatch):
    row = {
        "doc_code": "GB X-2019",
        "doc_name": "某环境质量标准",
        "unit_no": "表1",
        "pollutant": "SO2",
        "metric": "年均",
        "limit_value": 60.0,
        "unit": "μg/m³",
        "condition": "",
        "category": "二级",
        "period": "年平均",
        "verified_at": datetime(2026, 10, 20, 1, 2, 3),
        "verified_by": "bob",
        "source": "enrich",
        "table_key": None,  # query_indicators 严格键访问（T6 评审 bug-4127）
    }
    _patch_pg(monkeypatch, indicator_rows=[row])
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    rows = await query_indicators("GB X-2019")

    assert rows[0]["doc_name"] == "某环境质量标准"
    assert rows[0]["verified_by"] == "bob" and rows[0]["source"] == "enrich"
    assert rows[0]["verified_at"] == "2026-10-20T01:02:03Z"  # TIMESTAMPTZ → ISO 串


@pytest.mark.asyncio
async def test_query_indicators_sql_contains_new_columns(monkeypatch):
    holder = _patch_pg(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    await query_indicators("GB X-2019", "SO2")
    sql = holder[0].statements[0][0]
    assert "doc_name" in sql
    assert "verified_at" in sql and "verified_by" in sql and "source" in sql


@pytest.mark.asyncio
async def test_verify_sets_verified_at_and_user(monkeypatch):
    holder = _patch_pg(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    updated = await set_unit_verification("GB X-2019", "表1", True, "alice")

    assert updated == 7
    sql, params = holder[0].statements[0]
    assert "verified_at = now()" in sql and ":verified_by" in sql
    assert params == {"verified_by": "alice", "code": "GB X-2019", "uno": "表1"}


@pytest.mark.asyncio
async def test_unverify_nulls_verification(monkeypatch):
    holder = _patch_pg(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    await set_unit_verification("GB X-2019", "表1", False, "alice")

    sql, params = holder[0].statements[0]
    assert "verified_at = NULL" in sql and "verified_by = NULL" in sql
    assert "verified_by" not in params  # 撤销无需操作人


# --------------------------------------------------------------- 手工标准 CRUD


def _manual_rows():
    return [
        {
            "pollutant": "SO2",
            "metric": "年均",
            "limit_value": 60,
            "unit": "μg/m³",
            "category": "二级",
            "period": "年平均",
        },
        {"pollutant": "总汞", "metric": "日均", "limit_value": "≤0.5"},
    ]


@pytest.mark.asyncio
async def test_create_manual_standard_conflict_on_any_existing_rows(monkeypatch):
    holder = _patch_pg(monkeypatch, distinct_codes=["GB 3838-2002"])
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    with pytest.raises(StandardConflictError, match="拒绝重复创建"):
        await create_manual_standard("gb 3838-2002", None, _manual_rows(), "alice")

    # 归一化查重命中（原文小写带空格 vs 既有 GB 3838-2002），拒绝后不得有 INSERT
    assert len(holder) == 1  # 仅查重会话，未进入插入会话
    assert not any("INSERT" in sql for sql, _ in holder[0].statements)


@pytest.mark.asyncio
async def test_create_manual_standard_row_limit(monkeypatch):
    _patch_pg(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    rows = [{"pollutant": "X", "limit_value": 1}] * 501
    with pytest.raises(ValueError, match="500"):
        await create_manual_standard("GB NEW-2024", None, rows, "alice")


@pytest.mark.asyncio
async def test_create_manual_standard_row_validation(monkeypatch):
    _patch_pg(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    with pytest.raises(ValueError, match="pollutant"):
        await create_manual_standard("GB NEW-2024", None, [{"limit_value": 1}], "alice")
    with pytest.raises(ValueError, match="limit_value"):
        await create_manual_standard("GB NEW-2024", None, [{"pollutant": "坏行", "limit_value": "无法检出"}], "alice")
    with pytest.raises(ValueError, match="对象"):
        await create_manual_standard("GB NEW-2024", None, ["不是对象"], "alice")


@pytest.mark.asyncio
async def test_create_manual_standard_inserts_born_verified(monkeypatch):
    holder = _patch_pg(monkeypatch)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    inserted = await create_manual_standard("GB NEW-2024", "手工环境质量标准", _manual_rows(), "alice")

    assert inserted == 2
    inserts = [(sql, p) for s in holder for sql, p in s.statements if "INSERT INTO standard_indicators" in sql]
    assert len(inserts) == 2
    sql, _ = inserts[0]
    assert "now()" in sql and "'expert'" in sql  # born-verified：verified_at=now() + source='expert'
    by_p = {p["p"]: p for _, p in inserts}
    assert by_p["SO2"]["v"] == 60.0 and by_p["SO2"]["verified_by"] == "alice" and by_p["SO2"]["uno"] == "手录"
    assert all(p["doc_name"] == "手工环境质量标准" for _, p in inserts)  # 标准名随行落库
    assert by_p["总汞"]["v"] == 0.5  # 字符串限值沿用抽取口径归一（方向符号取原值）


@pytest.mark.asyncio
async def test_replace_manual_standard_requires_expert_rows(monkeypatch):
    holder = _patch_pg(monkeypatch, delete_rowcount=0)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    with pytest.raises(StandardConflictError, match="无手工行"):
        await replace_manual_standard("GB X-2019", None, _manual_rows(), "alice")

    stmts = holder[0].statements
    assert any("DELETE FROM standard_indicators" in sql and "source = 'expert'" in sql for sql, _ in stmts)
    assert not any("INSERT" in sql for sql, _ in stmts)  # 守护先于重插


@pytest.mark.asyncio
async def test_replace_manual_standard_deletes_expert_then_reinserts(monkeypatch):
    holder = _patch_pg(monkeypatch, delete_rowcount=3)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    inserted = await replace_manual_standard("GB X-2019", "替换后标准名", _manual_rows(), "alice")

    assert inserted == 2
    stmts = holder[0].statements
    i_del = next(i for i, (sql, _) in enumerate(stmts) if "DELETE" in sql)
    i_ins = min(i for i, (sql, _) in enumerate(stmts) if "INSERT" in sql)
    assert i_del < i_ins
    assert stmts[i_del][1] == {"code": "GB X-2019"}


@pytest.mark.asyncio
async def test_delete_manual_standard_conflict_and_success(monkeypatch):
    _patch_pg(monkeypatch, delete_rowcount=0)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)
    with pytest.raises(StandardConflictError, match="无手工行"):
        await delete_manual_standard("GB X-2019")

    holder2 = _patch_pg(monkeypatch, delete_rowcount=5)
    assert await delete_manual_standard("GB X-2019") == 5
    assert holder2[0].statements[0][1] == {"code": "GB X-2019"}


# --------------------------------------------------------------- enrich 冲突守护

T_LIMIT = "表1 污染物排放限值\n| 因子 | 限值 |\n| SO2 | 0.5 |"
IND_ROW = {
    "pollutant": "SO2",
    "metric": "日平均",
    "limit_value": 0.5,
    "unit": "mg/L",
    "condition": "",
    "category": "III类",
    "period": "24小时",
}


def _mk_chunk(cid, content, tags=None):
    return SimpleNamespace(chunk_id=cid, content=content, tags=dict(tags or {}))


class StubRoleClassifier:
    async def classify(self, doc_code, unit_no, title, content_excerpt):
        return "other"


class StubExtractor:
    def __init__(self, rows):
        self.rows = rows
        self.extract_calls = []

    async def extract_indicators(self, doc_code, unit_no, content):
        self.extract_calls.append(unit_no)
        return [dict(r) for r in self.rows]

    async def extract_method_mappings(self, doc_code, unit_no, content):
        return []


def _patch_enrich_flow(monkeypatch, expert_count):
    holder = _patch_pg(monkeypatch, chunks=[_mk_chunk("c1", T_LIMIT)], expert_count=expert_count)
    monkeypatch.setattr(enrich_mod, "ensure_schema", _noop)

    class FakeGraphWriter:
        def write_document_graph(self, *args):
            return {}

        def close(self):
            pass

    monkeypatch.setattr(enrich_mod, "RegulationGraphWriter", FakeGraphWriter)
    monkeypatch.setattr(enrich_mod, "TableRoleClassifier", StubRoleClassifier)
    ext = StubExtractor(rows=[dict(IND_ROW)])
    monkeypatch.setattr(enrich_mod.indicator_extractor, "extract_indicators", ext.extract_indicators)
    monkeypatch.setattr(enrich_mod.indicator_extractor, "extract_method_mappings", ext.extract_method_mappings)
    return holder, ext


@pytest.mark.asyncio
async def test_enrich_rejects_before_delete_when_expert_rows_present(monkeypatch):
    holder, ext = _patch_enrich_flow(monkeypatch, expert_count=1)

    with pytest.raises(StandardConflictError, match="检测到手工行，拒绝覆盖"):
        await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    # 检测点唯一：守护是首条语句，且全程无 DELETE、无 LLM 抽取（fail-fast）
    assert "count(*)" in holder[0].statements[0][0]
    assert not any("DELETE FROM standard_indicators" in sql for s in holder for sql, _ in s.statements)
    assert ext.extract_calls == []


@pytest.mark.asyncio
async def test_enrich_proceeds_when_no_expert_rows(monkeypatch):
    holder, ext = _patch_enrich_flow(monkeypatch, expert_count=0)

    result = await enrich_regulation_file("kb1", "f1", "GB X-2019", "标准", "technical_standard")

    assert result["indicators"] == 1
    assert ext.extract_calls == ["表1"]
    assert any("DELETE FROM standard_indicators" in sql for s in holder for sql, _ in s.statements)
    ins = [p for s in holder for sql, p in s.statements if "INSERT INTO standard_indicators" in sql]
    assert ins and ins[0]["doc_name"] == "标准"  # enrich 行透传标准名


# --------------------------------------------------------------- 缺源候选纯函数


def test_norm_code_fullwidth_dash():
    assert norm_code("GB 3096－2008") == norm_code("GB3096-2008") == "GB3096-2008"


def test_aggregate_cited_codes_counts_reports_and_caps_samples():
    meta = {
        "reports": {
            "r1": {"standards_cited": ["GB 3838-2002", "GB 3838-2002", "GB/T 13201-91"]},
            "r2": {"standards_cited": ["GB3838-2002"]},
            "r3": {},
        }
    }
    agg = aggregate_cited_codes(meta)
    # 聚合按原文写法分键，同报告重复引用只计一次；归一化合并发生在 diff 侧
    assert agg["GB 3838-2002"] == {"ref_count": 1, "sample_sources": ["r1"]}
    assert agg["GB3838-2002"] == {"ref_count": 1, "sample_sources": ["r2"]}
    assert agg["GB/T 13201-91"] == {"ref_count": 1, "sample_sources": ["r1"]}


def test_aggregate_cited_codes_caps_sample_sources():
    meta = {"reports": {f"r{i}": {"standards_cited": ["HJ 828-2017"]} for i in range(5)}}
    agg = aggregate_cited_codes(meta)
    assert agg["HJ 828-2017"]["ref_count"] == 5
    assert len(agg["HJ 828-2017"]["sample_sources"]) == 3


def test_diff_source_candidates_normalizes_dedups_and_sorts():
    cited = {
        "GB/T 13201-91": {"ref_count": 3, "sample_sources": ["r1", "r2", "r3"]},
        "GBT 13201—91": {"ref_count": 2, "sample_sources": ["r4"]},  # 与上者同归一码，合并
        "HJ 828－2017": {"ref_count": 2, "sample_sources": ["r5"]},  # 已覆盖（全角连字符变体）
        "GB 3096-2008": {"ref_count": 1, "sample_sources": ["r6"]},  # 已覆盖
    }
    covered = ["GB 3838-2002", "HJ828-2017", "GB 3096-2008"]
    out = diff_source_candidates(cited, covered)
    # 变体合并：ref_count 累加、样例来源并集截断到 3，code 取先出现的原文写法
    assert out == [{"code": "GB/T 13201-91", "ref_count": 5, "sample_sources": ["r1", "r2", "r3"]}]


def test_diff_source_candidates_sorts_by_ref_count_desc():
    cited = {
        "A 1-2000": {"ref_count": 1, "sample_sources": ["r1"]},
        "B 2-2001": {"ref_count": 4, "sample_sources": ["r2"]},
        "C 3-2002": {"ref_count": 2, "sample_sources": ["r3"]},
    }
    assert [c["code"] for c in diff_source_candidates(cited, [])] == ["B 2-2001", "C 3-2002", "A 1-2000"]


@pytest.mark.asyncio
async def test_list_source_candidates_composes_aggregation_and_diff(monkeypatch):
    import yuxi.extensions.regulation_library.enrichment_service as enrich_ns
    import yuxi.services.eia_meta_service as meta_mod
    from yuxi.services.eia_limit_extract_service import EiaLimitExtractService

    fake_meta = {
        "reports": {
            "r1": {"standards_cited": ["GB/T 13201-91"]},
            "r2": {"standards_cited": ["GB 3838-2002"]},
        }
    }
    monkeypatch.setattr(meta_mod, "_load_corpus_meta", lambda: fake_meta)

    async def fake_distinct():
        return ["GB 3838-2002"]

    monkeypatch.setattr(enrich_ns, "distinct_doc_codes", fake_distinct)

    svc = EiaLimitExtractService(repo=object(), std_repo=object(), classifier=object())
    out = await svc.list_source_candidates()

    assert out == [{"code": "GB/T 13201-91", "ref_count": 1, "sample_sources": ["r1"]}]
