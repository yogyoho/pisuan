"""list_limit_tables 重指向单测：文件锚点 source='file' + 专家行重组 source='expert' + 表级 verified 派生。"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from yuxi.services import eia_standard_service as svc


def _flat(tk, prid, **kw):
    base = {
        "table_key": tk,
        "page_row_id": prid,
        "pollutant": "",
        "metric": "",
        "limit_value": 1,
        "unit": "",
        "condition": "",
        "category": "",
        "period": "",
        "verified_by": "qa",
        "verified_at": datetime(2026, 10, 22, 12, 0, 0),
    }
    base.update(kw)
    return base  # list_expert_rows 返回 dict（r["key"] 取值）


@pytest.fixture
def list_env(monkeypatch):
    async def _no_registry(self):
        return []

    monkeypatch.setattr(
        svc,
        "_load_standards_index",
        lambda: {
            "limit_tables": {
                "gbt14848_category_limits": {
                    "desc": "地下水",
                    "code_ref": "GB/T 14848-2017",
                    "needs_verification": True,
                    "verified": False,
                    "rows": [],
                },
                "gb3096_zone_limits": {
                    "desc": "声环境",
                    "code_ref": "GB 3096-2008",
                    "needs_verification": True,
                    "verified": False,
                    "rows": [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}],
                },
                "_comment": "说明项",
            }
        },
    )
    monkeypatch.setattr(svc.EiaStandardRepository, "list_registry", _no_registry)


def test_expert_rows_regroup_and_override_seed(list_env, monkeypatch):
    rows = [
        _flat("gbt14848_category_limits", "a1", pollutant="总硬度", limit_value=450, unit="mg/L", category="III类"),
        _flat("gb3096_zone_limits", "b1", metric="昼间", limit_value=50, unit="dB(A)", category="0类"),
        _flat("gb3096_zone_limits", "b1", metric="夜间", limit_value=40, unit="dB(A)", category="0类"),
    ]

    async def _fake_rows(self):
        return rows

    monkeypatch.setattr(svc.EiaStandardService, "list_expert_rows", _fake_rows)
    out = asyncio.run(svc.EiaStandardService().list_limit_tables())
    t = out["limit_tables"]["gbt14848_category_limits"]
    assert t["source"] == "expert" and t["verified"] is True and t["needs_verification"] is False
    assert t["rows"] == [{"pollutant": "总硬度", "category": "III类", "limit_value": 450, "unit": "mg/L"}]
    t2 = out["limit_tables"]["gb3096_zone_limits"]
    assert t2["source"] == "expert" and t2["rows"] == [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}]
    assert out["limit_tables"]["_comment"] == "说明项"  # 说明项透传不变
    assert "gbt14848_category_limits" in out["schemas"]


def test_file_seed_kept_when_no_expert_rows(list_env, monkeypatch):
    async def _no_rows(self):
        return []

    monkeypatch.setattr(svc.EiaStandardService, "list_expert_rows", _no_rows)
    out = asyncio.run(svc.EiaStandardService().list_limit_tables())
    t = out["limit_tables"]["gb3096_zone_limits"]
    assert t["source"] == "file" and t["verified"] is False and t["needs_verification"] is True
    assert t["rows"] == [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}]  # 锚点样例行原样
