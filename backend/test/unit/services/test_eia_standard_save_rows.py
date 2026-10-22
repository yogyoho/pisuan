"""save_limit_rows 重指向 standard_indicators（born-verified 权威行）单测（P1 合流 Task 3）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from yuxi.services import eia_standard_service as svc


class FakeSession:
    def __init__(self):
        self.executes: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        self.executes.append((str(sql), dict(params or {})))
        return SimpleNamespace(rowcount=0)

    async def commit(self):
        pass


@pytest.fixture
def session_env(monkeypatch):
    ses = FakeSession()

    class _CM:
        async def __aenter__(self):
            return ses

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(svc.pg_manager, "get_async_session_context", lambda: _CM())
    monkeypatch.setattr(svc, "ensure_schema", lambda: asyncio.sleep(0))  # 写路径默认桩 DDL（Task 4 守卫）
    return ses


def test_save_rows_writes_born_verified_expert_rows(session_env, monkeypatch):
    monkeypatch.setattr(
        svc,
        "_load_standards_index",
        lambda: {"limit_tables": {"gbt14848_category_limits": {"code_ref": "GB/T 14848-2017"}}},
    )
    service = svc.EiaStandardService()
    out = asyncio.run(
        service.save_limit_rows(
            "gbt14848_category_limits",
            [{"category": "III类", "pollutant": "总硬度", "limit_value": 450, "unit": "mg/L"}],
            "qa",
        )
    )
    assert out == {"table_key": "gbt14848_category_limits", "saved": 1}
    delete_sql, delete_params = session_env.executes[0]
    assert "DELETE FROM standard_indicators" in delete_sql and "source = 'expert'" in delete_sql
    assert delete_params == {"tk": "gbt14848_category_limits"}
    insert_sql, insert_params = session_env.executes[1]
    assert "INSERT INTO standard_indicators" in insert_sql
    assert insert_params["source"] == "expert"
    assert insert_params["verified_by"] == "qa"
    assert insert_params["doc_code"] == "GB/T 14848-2017"
    assert insert_params["table_key"] == "gbt14848_category_limits"
    assert insert_params["page_row_id"]
    assert "now()" in insert_sql  # born-verified：verified_at 由 SQL now() 生成


def test_save_rows_day_night_saves_two_rows(session_env, monkeypatch):
    monkeypatch.setattr(
        svc, "_load_standards_index", lambda: {"limit_tables": {"gb3096_zone_limits": {"code_ref": "GB 3096-2008"}}}
    )
    service = svc.EiaStandardService()
    out = asyncio.run(
        service.save_limit_rows(
            "gb3096_zone_limits", [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}], "qa"
        )
    )
    assert out["saved"] == 2
    p1, p2 = session_env.executes[1][1], session_env.executes[2][1]
    assert {p1["metric"], p2["metric"]} == {"昼间", "夜间"}
    assert p1["page_row_id"] == p2["page_row_id"]


def test_save_rows_calls_ensure_schema_first(session_env, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(svc, "ensure_schema", lambda: calls.append("schema") or asyncio.sleep(0))
    monkeypatch.setattr(svc, "_load_standards_index", lambda: {"limit_tables": {}})
    asyncio.run(
        svc.EiaStandardService().save_limit_rows(
            "gbt14848_category_limits",
            [{"category": "III类", "pollutant": "总硬度", "limit_value": 450, "unit": "mg/L"}],
            "qa",
        )
    )
    assert calls == ["schema"]  # fresh DB 首写守卫在 IO 前执行


def test_save_rows_invalid_payload_aborts_before_session(session_env, monkeypatch):
    monkeypatch.setattr(svc, "ensure_schema", lambda: asyncio.sleep(0))
    monkeypatch.setattr(svc, "_load_standards_index", lambda: {"limit_tables": {}})
    with pytest.raises(KeyError):
        asyncio.run(svc.EiaStandardService().save_limit_rows("no_such_table", [{"x": 1}], "qa"))
    assert session_env.executes == []  # 校验失败不得开库
