"""eia_limit_extract_service 单测：试跑幂等 / 行裁决转正 / 候选立表。"""

import pytest

from yuxi.services.eia_limit_extract_service import EiaLimitExtractService


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
    s = EiaLimitExtractService(repo=repo)
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
