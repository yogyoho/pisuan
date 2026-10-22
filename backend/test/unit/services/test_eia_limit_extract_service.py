"""eia_limit_extract_service 单测：试跑幂等 / 行裁决转正 / 候选立表。"""

import asyncio
from types import SimpleNamespace

import pytest

from yuxi.services import eia_limit_extract_service as lex_svc
from yuxi.services.eia_limit_extract_service import EiaLimitExtractService
from yuxi.services.eia_limit_llm_classifier import GateStats, JudgeResult
from yuxi.services.eia_limit_row_mapping import page_row_id_for
from yuxi.services.eia_standard_service import EiaStandardService as _ESS


class PassThroughGate:
    """既有用例的判别门桩：全部放行（Task 13 前 regex 全收语义），行标注仍由服务层写入。"""

    def __init__(self):
        self.stats = GateStats()

    async def judge(self, code, text, table_key=None):
        self.stats.blocks += 1
        self.stats.passed += 1
        return JudgeResult(True, "passed", {"is_limit_statement": True})


class StubExtractRepo:
    """内存桩：rows/registry 列表 + 同签名过滤。"""

    def __init__(self):
        self.rows, self.registry = [], []

    async def list_rows(self, table_key=None, status=None, confidence=None):
        out = self.rows
        for f, v in (("table_key", table_key), ("status", status), ("confidence", confidence)):
            if v:
                out = [r for r in out if getattr(r, f) == v]
        return out

    async def add_rows(self, rows):
        self.rows.extend(rows)
        return len(rows)

    async def get_row(self, row_id):
        return next((r for r in self.rows if r.id == row_id), None)

    async def save_row(self, row):
        return row

    async def list_registry(self):
        return self.registry

    async def get_registry(self, table_key):
        return next((r for r in self.registry if r.table_key == table_key), None)

    async def save_registry(self, row):
        self.registry.append(row)
        return row


@pytest.fixture
def svc(monkeypatch, tmp_path):
    repo = StubExtractRepo()
    s = EiaLimitExtractService(repo=repo, classifier=PassThroughGate())
    monkeypatch.setattr(s, "_bank_dirs", lambda: [tmp_path])
    d = tmp_path / "planning_eia" / "slices" / "ch1"
    d.mkdir(parents=True)
    (d / "038-2024-7-9__1.md").write_text(
        "执行《环境空气质量标准》(GB3095-2012)二级标准：\n"
        "| 污染物 | 取值时间 | 浓度限值 | 单位 |\n| --- | --- | --- | --- |\n"
        "| SO2 | 24小时 | 0.15 | mg/m3 |\n",
        encoding="utf-8",
    )
    return s, repo


class FakeSession:
    """记录 executes 的最小会话桩（同 test_eia_standard_save_rows.py 的 session_env 模式）。"""

    def __init__(self):
        self.executes: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        self.executes.append((str(sql), dict(params or {})))
        return SimpleNamespace(rowcount=0)


@pytest.fixture
def write_env(monkeypatch):
    """转正写路径桩：session / ensure_schema / 锚点加载全走模块级名字，防真库写与真 DDL 漏入。"""
    ses = FakeSession()

    class _CM:
        async def __aenter__(self):
            return ses

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(lex_svc, "pg_manager", SimpleNamespace(get_async_session_context=lambda: _CM()))
    monkeypatch.setattr(lex_svc, "ensure_schema", lambda: asyncio.sleep(0))  # 真 DDL 会经共享单例漏进 FakeSession
    return ses


@pytest.mark.asyncio
async def test_run_extraction_inserts_and_report(svc):
    s, repo = svc
    report = await s.run_extraction("admin")
    assert report["files_scanned"] == 1
    assert len(await repo.list_rows(status="pending")) >= 1


@pytest.mark.asyncio
async def test_run_extraction_idempotent_preserves_decided(svc):
    s, repo = svc
    await s.run_extraction("admin")
    first = await repo.list_rows()
    first[0].status = "confirmed"
    await s.run_extraction("admin")
    again = await repo.list_rows()
    assert len([r for r in again if r.status == "confirmed"]) == 1
    assert len(again) == len(first)  # 不重复插入


@pytest.mark.asyncio
async def test_decide_row_confirm_writes_expert_row(svc, write_env, monkeypatch):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    calls = []

    async def fake_insert(self, session, tk, doc_code, page_row, u):  # 真方法为 async，桩须同形
        calls.append((tk, doc_code, page_row, u))

    monkeypatch.setattr(_ESS, "_insert_expert_row", fake_insert)
    monkeypatch.setattr(
        lex_svc,
        "_load_standards_index",
        lambda: {"limit_tables": {row.table_key: {"code_ref": "GB 3095-2012"}}},
    )
    out = await s.decide_row(row.id, "confirm", None, "admin", note="对照原文无误")
    assert out["status"] == "confirmed"
    assert calls[0][0] == row.table_key
    assert calls[0][1] == "GB 3095-2012"  # doc_code = 测试锚点里配的 code_ref
    assert calls[0][2]["limit_value"] == 0.15 and isinstance(calls[0][2]["limit_value"], float)
    assert calls[0][3] == "admin"
    delete_sql, delete_params = write_env.executes[0]  # 幂等：先按 page_row_id 删旧行
    assert "DELETE FROM standard_indicators" in delete_sql
    assert delete_params["tk"] == row.table_key and delete_params["prid"]
    assert delete_params["prid"] == page_row_id_for(row.table_key, calls[0][2])


@pytest.mark.asyncio
async def test_register_candidate_migrates_rows(svc):
    s, repo = svc
    await s.run_extraction("admin")
    (await repo.list_rows())[0].table_key = "__candidate__:GB8978-1996"  # 与 norm_code("GB 8978-1996") 同号，真跑迁移
    out = await s.register_candidate(
        "GB 8978-1996",
        "gb8978_emission_limits",
        "污水综合排放标准",
        {"pollutant": {"label": "污染物", "type": "str", "required": True}},
        "admin",
    )
    assert out["migrated"] == 1 and (await repo.get_registry("gb8978_emission_limits")) is not None


@pytest.mark.asyncio
async def test_decide_row_discarded_never_finalizes(svc, write_env, monkeypatch):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    calls = []

    async def fake_insert(self, session, tk, doc_code, page_row, u):
        calls.append((tk, doc_code, page_row, u))

    monkeypatch.setattr(_ESS, "_insert_expert_row", fake_insert)
    out = await s.decide_row(row.id, "discarded", None, "admin")
    assert out["status"] == "discarded" and calls == []


@pytest.mark.asyncio
async def test_decide_row_edited_requires_row_json(svc):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    with pytest.raises(ValueError):
        await s.decide_row(row.id, "edited", None, "admin")


@pytest.mark.asyncio
async def test_decide_row_rejects_candidate_key(svc):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    row.table_key = "__candidate__:GB3095-2012"
    with pytest.raises(ValueError):
        await s.decide_row(row.id, "confirm", None, "admin")


@pytest.mark.asyncio
async def test_decide_row_rejects_redecision(svc):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    await s.decide_row(row.id, "discarded", None, "admin")
    with pytest.raises(ValueError):
        await s.decide_row(row.id, "confirm", None, "admin")


@pytest.mark.asyncio
async def test_run_extraction_skips_unreadable_file(svc, tmp_path):
    s, repo = svc
    (tmp_path / "planning_eia" / "slices" / "ch1" / "038-2024-7-9__2.md").write_bytes(
        b"\xff\xfe<\x00?\x00x\x00m\x00l\x00 \x00v\x00e\x00r\x00s\x00i\x00o\x00n\x00"
    )
    report = await s.run_extraction("admin")
    assert report["files_scanned"] == 2 and report["skipped"] >= 1
    assert len(await repo.list_rows(status="pending")) >= 1  # 好文件照常产出


@pytest.mark.asyncio
async def test_registered_table_no_candidate_rebirth_on_rerun(svc, tmp_path):
    s, repo = svc
    d = tmp_path / "planning_eia" / "slices" / "ch1"
    (d / "038-2024-7-9__2.md").write_text(
        "执行《污水综合排放标准》(GB8978-1996)二级标准：\n"
        "| 污染物 | 时段 | 排放限值 | 单位 |\n| --- | --- | --- | --- |\n"
        "| 悬浮物 | 1998年1月1日前建设 | 200 | mg/L |\n",
        encoding="utf-8",
    )
    await s.run_extraction("admin")
    cands = [r for r in await repo.list_rows() if r.table_key.startswith("__candidate__:")]
    assert len(cands) == 1
    await s.register_candidate(
        "GB 8978-1996",
        "gb8978_emission_limits",
        "污水综合排放标准",
        {"pollutant": {"label": "污染物", "type": "str", "required": True}},
        "admin",
    )
    report = await s.run_extraction("admin")
    assert report["inserted"] == 0  # 立表后重跑：重映射命中已迁移行，零新插
    assert [r for r in await repo.list_rows() if r.table_key.startswith("__candidate__:")] == []
