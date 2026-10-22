"""eia_limit_extract_service 单测：试跑幂等 / 行裁决转正 / 候选立表。"""

import pytest

from pisuan.services.eia_limit_extract_service import EiaLimitExtractService
from pisuan.services.eia_limit_llm_classifier import GateStats, JudgeResult


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
async def test_decide_row_confirm_upserts_official(svc, monkeypatch):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    upserted = []

    async def fake_upsert(tk, r, u):  # 真仓储 upsert_row 为 async，桩须同形
        upserted.append((tk, r, u))

    monkeypatch.setattr(s._std_repo, "upsert_row", fake_upsert)
    out = await s.decide_row(row.id, "confirm", None, "admin", note="对照原文无误")
    assert out["status"] == "confirmed" and upserted[0][0] == row.table_key
    assert upserted[0][1]["limit_value"] == 0.15 and isinstance(upserted[0][1]["limit_value"], float)


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
async def test_decide_row_discarded_never_upserts(svc, monkeypatch):
    s, repo = svc
    await s.run_extraction("admin")
    row = (await repo.list_rows(status="pending"))[0]
    calls = []

    async def fake_upsert(tk, r, u):
        calls.append((tk, r, u))

    monkeypatch.setattr(s._std_repo, "upsert_row", fake_upsert)
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
