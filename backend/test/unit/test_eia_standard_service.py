"""eia_standard_service 纯函数单测：核实载荷校验（action 白名单、note 类型、未知字段拒收）+ 引用码归一。

P1 限值行录入：_validate_limit_rows 列配置校验（纯函数）+ save/list/export 服务方法（fake repo +
tmp 最小 standards_index，不触真实文件）。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from yuxi.services import eia_standard_service
from yuxi.services.eia_standard_service import _norm_std, _validate_limit_rows, _validate_review


def test_validate_review_accepts_confirm():
    assert _validate_review({"action": "confirm"}) is None
    assert _validate_review({"action": "confirm", "note": "已对照标准原文"}) is None


def test_validate_review_rejects_bad_action():
    for bad in ("reject", "Confirm", "", None):
        with pytest.raises(ValueError, match="action"):
            _validate_review({"action": bad})
    with pytest.raises(ValueError, match="action"):
        _validate_review({})


def test_validate_review_rejects_unknown_fields():
    with pytest.raises(ValueError, match="未知核实字段"):
        _validate_review({"action": "confirm", "tier": "emission_limit"})


def test_validate_review_rejects_non_string_note():
    with pytest.raises(ValueError, match="note"):
        _validate_review({"action": "confirm", "note": 123})


def test_norm_std_absorbs_citation_noise():
    """语料引用码噪声归一：空格/连字符/破折号/斜杠差异不改变同一性。"""
    base = _norm_std("GB 15618-2018")
    assert base == _norm_std("GB/15618-2018")
    assert base == _norm_std("GB15618—2018")
    assert base == _norm_std("gb 15618 - 2018")
    assert base == _norm_std("GB–15618–2018")


# ── P1 限值行录入（eia_standard_limit_rows）─────────────────────────────


def _noise_row():
    return {"category": "2 类", "day": 50, "night": 40, "unit": "dB(A)"}


class _FakeLimitRepo:
    def __init__(self, db_rows=None, registry=None):
        self.saved = None
        self._db_rows = db_rows or []
        self._registry = registry or []

    async def replace_rows(self, table_key, rows, username):
        self.saved = (table_key, rows, username)
        return len(rows)

    async def list_rows(self):
        return self._db_rows

    async def list_registry(self):
        return self._registry


def _svc_with(repo):
    svc = eia_standard_service.EiaStandardService.__new__(eia_standard_service.EiaStandardService)
    svc.repo = repo
    return svc


def _write_min_index(tmp_path, limit_tables):
    doc = {
        "standards": [{"code": "GB 3096-2008", "title": "声环境质量标准"}],
        "limit_tables": limit_tables,
    }
    p = tmp_path / "standards_index.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def test_validate_limit_rows_normalizes_noise_row():
    out = _validate_limit_rows("gb3096_zone_limits", [_noise_row()])
    assert out == [_noise_row()]


def test_validate_limit_rows_rejects_unknown_table():
    with pytest.raises(KeyError):
        _validate_limit_rows("nonexistent_table", [_noise_row()])


def test_validate_limit_rows_rejects_empty_and_non_list():
    for bad in ([], None, "rows"):
        with pytest.raises(ValueError):
            _validate_limit_rows("gb3096_zone_limits", bad)


def test_validate_limit_rows_rejects_unknown_field():
    row = {**_noise_row(), "origin": "sample_verbatim(x)"}
    with pytest.raises(ValueError, match="未知限值字段"):
        _validate_limit_rows("gb3096_zone_limits", [row])


def test_validate_limit_rows_rejects_missing_required():
    row = {"category": "2 类", "day": 50, "unit": "dB(A)"}
    with pytest.raises(ValueError, match="night"):
        _validate_limit_rows("gb3096_zone_limits", [row])


def test_validate_limit_rows_rejects_non_numeric():
    row = {**_noise_row(), "day": "50"}
    with pytest.raises(ValueError, match="数值"):
        _validate_limit_rows("gb3096_zone_limits", [row])


def test_validate_limit_rows_rejects_blank_string():
    row = {**_noise_row(), "category": "  "}
    with pytest.raises(ValueError, match="category"):
        _validate_limit_rows("gb3096_zone_limits", [row])


def test_save_limit_rows_happy_path():
    repo = _FakeLimitRepo()
    out = asyncio.run(_svc_with(repo).save_limit_rows("gb3096_zone_limits", [_noise_row()], "alice"))
    assert repo.saved[0] == "gb3096_zone_limits"
    assert repo.saved[1] == [_noise_row()]
    assert repo.saved[2] == "alice"
    assert out["saved"] == 1


def test_save_limit_rows_unknown_table_rejected_before_repo():
    repo = _FakeLimitRepo()
    with pytest.raises(KeyError):
        asyncio.run(_svc_with(repo).save_limit_rows("nonexistent_table", [_noise_row()], "alice"))
    assert repo.saved is None


def test_list_limit_tables_merges_db_rows_and_exposes_schemas(monkeypatch, tmp_path):
    monkeypatch.setattr(eia_standard_service, "STANDARDS_INDEX_PATH", _write_min_index(tmp_path, {}))
    db_rows = [
        SimpleNamespace(
            id=1, table_key="gb3096_zone_limits", row_json=_noise_row(), decided_by="alice", updated_at=None
        )
    ]
    out = asyncio.run(_svc_with(_FakeLimitRepo(db_rows)).list_limit_tables())
    t = out["limit_tables"]["gb3096_zone_limits"]
    assert t["rows"] == [_noise_row()]
    assert t["source"] == "db"
    assert out["schemas"]["gb3096_zone_limits"]["day"]["type"] == "number"


def test_list_limit_tables_falls_back_to_file_rows(monkeypatch, tmp_path):
    anchor = {"category": "3 类", "day": 65, "night": 55, "unit": "dB(A)", "origin": "anchor"}
    monkeypatch.setattr(
        eia_standard_service,
        "STANDARDS_INDEX_PATH",
        _write_min_index(
            tmp_path,
            {
                "gb3096_zone_limits": {
                    "desc": "声环境质量标准限值",
                    "code_ref": "GB 3096-2008",
                    "needs_verification": True,
                    "verified": False,
                    "rows": [anchor],
                }
            },
        ),
    )
    out = asyncio.run(_svc_with(_FakeLimitRepo()).list_limit_tables())
    t = out["limit_tables"]["gb3096_zone_limits"]
    assert t["source"] == "file"
    assert t["rows"] == [anchor]


def test_list_limit_tables_exposes_registry_new_table(monkeypatch, tmp_path):
    """新表入册通道：DB 注册表条目露出为新键（source=db_registry）并并入 schemas。"""
    monkeypatch.setattr(eia_standard_service, "STANDARDS_INDEX_PATH", _write_min_index(tmp_path, {}))
    registry = [
        SimpleNamespace(
            table_key="gb8978_emission_limits",
            code="GB 8978-1996",
            desc="污水综合排放标准",
            columns_schema={"pollutant": {"label": "污染物", "type": "str", "required": True}},
        )
    ]
    out = asyncio.run(_svc_with(_FakeLimitRepo(registry=registry)).list_limit_tables())
    t = out["limit_tables"]["gb8978_emission_limits"]
    assert t["source"] == "db_registry" and t["code_ref"] == "GB 8978-1996"
    assert t["needs_verification"] is True and t["rows"] == []
    assert out["schemas"]["gb8978_emission_limits"]["pollutant"]["type"] == "str"


def test_export_limit_rows_writes_and_flips(monkeypatch, tmp_path):
    path = _write_min_index(
        tmp_path,
        {
            "gb3096_zone_limits": {
                "desc": "d",
                "code_ref": "GB 3096-2008",
                "needs_verification": True,
                "verified": False,
                "rows": [{"category": "3 类", "origin": "anchor"}],
            },
            "gb3095_concentration_limits": {
                "desc": "d2",
                "code_ref": "GB 3095-2012",
                "needs_verification": True,
                "verified": False,
                "rows": [],
            },
        },
    )
    monkeypatch.setattr(eia_standard_service, "STANDARDS_INDEX_PATH", path)
    db_rows = [
        SimpleNamespace(
            id=2,
            table_key="gb3096_zone_limits",
            row_json={"category": "1 类", "day": 55, "night": 45, "unit": "dB(A)"},
            decided_by="bob",
            updated_at=None,
        ),
        SimpleNamespace(
            id=1, table_key="gb3096_zone_limits", row_json=_noise_row(), decided_by="alice", updated_at=None
        ),
    ]
    out = asyncio.run(_svc_with(_FakeLimitRepo(db_rows)).export_limit_rows("admin"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    t1 = doc["limit_tables"]["gb3096_zone_limits"]
    # id 序落盘，样例锚点行被人工核对行整体替换
    assert t1["rows"] == [_noise_row(), {"category": "1 类", "day": 55, "night": 45, "unit": "dB(A)"}]
    assert t1["needs_verification"] is False
    assert t1["verified"] is True
    t2 = doc["limit_tables"]["gb3095_concentration_limits"]
    assert t2["needs_verification"] is True  # 无裁决表不动
    assert t2["rows"] == []
    assert doc["standards"][0]["code"] == "GB 3096-2008"  # 其余结构 round-trip
    assert out["materialized"] == 1
    assert out["rows"] == 2


def test_export_limit_rows_without_rows_rejected():
    with pytest.raises(ValueError):
        asyncio.run(_svc_with(_FakeLimitRepo()).export_limit_rows("admin"))
