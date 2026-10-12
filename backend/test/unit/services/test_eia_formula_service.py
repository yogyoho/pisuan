"""EiaFormulaService 单测（P3-1：formulas 参数参考值 DB 覆盖 + 文本级导出物化）。

字节纪律：formulas.json 实况 LF + indent2 + inputs 单行紧凑对象 + 尾随换行；
导出仅目标 input 行变化，禁止 json.load→dumps 全文件重写（stages bug-417 同款教训）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from yuxi.services import eia_formula_service as svc_mod
from yuxi.services.eia_formula_service import EiaFormulaService

# 实况同构最小夹具：LF、2 空格缩进、inputs 单行紧凑、尾随换行
_FORMULAS_TEXT = (
    "{\n"
    '  "version": "1.0",\n'
    '  "formulas": [\n'
    "    {\n"
    '      "id": "subsidence_max",\n'
    '      "name": "最大下沉值",\n'
    '      "chapter": "ch4",\n'
    '      "expr": "W = q * m * b",\n'
    '      "inputs": [\n'
    '        {"name": "q", "desc": "下沉系数", "unit": "-", "type": "user_input"},\n'
    '        {"name": "b", "desc": "水平移动系数", "unit": "-", "type": "user_input"}\n'
    "      ],\n"
    '      "outputs": ["W"],\n'
    '      "slots": ["geology.subsidence_max"],\n'
    '      "note": ""\n'
    "    },\n"
    "    {\n"
    '      "id": "gangue_gen",\n'
    '      "name": "矸石产生量",\n'
    '      "chapter": "ch6",\n'
    '      "expr": "G = gangue_rate% * total_scale",\n'
    '      "inputs": [\n'
    '        {"name": "gangue_rate", "desc": "矸石产率", "unit": "%", "type": "user_input"},\n'
    '        {"name": "frozen", "desc": "冻结演示位", "unit": "-", "type": "derived_from_outputs"}\n'
    "      ],\n"
    '      "outputs": ["G"],\n'
    '      "slots": ["solid_waste.gangue_generation"],\n'
    '      "note": ""\n'
    "    }\n"
    "  ],\n"
    '  "derived_slots": [\n'
    '    {"slot": "solid_waste.gangue_generation", "expr": "a%b", "source": "derived:x", "note": "派生值"}\n'
    "  ]\n"
    "}\n"
)


class _FakeRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.upserts = []
        self.deletes = []

    async def list_overrides(self):
        return list(self.rows)

    async def upsert_override(self, formula_id, input_name, value, note, username):
        self.upserts.append((formula_id, input_name, value, note, username))
        return SimpleNamespace(
            id=1,
            formula_id=formula_id,
            input_name=input_name,
            value=value,
            note=note,
            decided_by=username,
            updated_at="2026-10-12T00:00:00",
        )

    async def delete_override(self, formula_id, input_name):
        self.deletes.append((formula_id, input_name))
        return True


def _row(fid="subsidence_max", input_name="q", value="0.65", note="横城实测"):
    return SimpleNamespace(
        id=1,
        formula_id=fid,
        input_name=input_name,
        value=value,
        note=note,
        decided_by="admin",
        updated_at="2026-10-12T00:00:00",
    )


@pytest.fixture
def formulas_file(tmp_path, monkeypatch):
    p = tmp_path / "formulas.json"
    p.write_text(_FORMULAS_TEXT, encoding="utf-8", newline="")
    monkeypatch.setattr(svc_mod, "FORMULAS_PATH", p)
    return p


def _svc(repo=None) -> EiaFormulaService:
    return EiaFormulaService(repo=repo or _FakeRepo())


@pytest.mark.asyncio
async def test_list_formulas_merges_pending_overrides(formulas_file):
    repo = _FakeRepo([_row()])
    out = await _svc(repo).list_formulas()
    f0, f1 = out["formulas"]
    assert f0["inputs"][0]["override"] == {
        "value": "0.65",
        "note": "横城实测",
        "decided_by": "admin",
        "updated_at": "2026-10-12T00:00:00",
        "pending": True,
    }
    assert f0["inputs"][1]["override"] is None
    assert f1["inputs"][0]["override"] is None
    # 结构只读透出：expr / derived_slots 原样
    assert f0["expr"] == "W = q * m * b"
    assert out["derived_slots"][0]["slot"] == "solid_waste.gangue_generation"
    assert out["pending_count"] == 1


@pytest.mark.asyncio
async def test_set_input_value_upserts_and_validates(formulas_file):
    repo = _FakeRepo()
    row = await _svc(repo).set_input_value("subsidence_max", "q", "0.65", "横城实测", "admin")
    assert repo.upserts == [("subsidence_max", "q", "0.65", "横城实测", "admin")]
    assert row["formula_id"] == "subsidence_max"

    with pytest.raises(KeyError, match="未知公式"):
        await _svc(_FakeRepo()).set_input_value("nope", "q", "1", None, "admin")
    with pytest.raises(KeyError, match="未知参数"):
        await _svc(_FakeRepo()).set_input_value("subsidence_max", "nope", "1", None, "admin")
    with pytest.raises(ValueError, match="user_input"):
        await _svc(_FakeRepo()).set_input_value("gangue_gen", "frozen", "1", None, "admin")
    with pytest.raises(ValueError, match="参考值不能为空"):
        await _svc(_FakeRepo()).set_input_value("subsidence_max", "q", "  ", None, "admin")


@pytest.mark.asyncio
async def test_export_splices_value_into_target_line_only(formulas_file):
    repo = _FakeRepo([_row()])
    out = await _svc(repo).export_formulas("admin")
    assert out["results"] == {"subsidence_max": {"materialized": 1, "skipped": 0}}
    assert out["paths"] == ["references/formulas.json"]

    text = formulas_file.read_text(encoding="utf-8", newline="")
    lines = text.split("\n")
    q_line = next(ln for ln in lines if '"name": "q"' in ln)
    b_line = next(ln for ln in lines if '"name": "b"' in ln)
    gangue_line = next(ln for ln in lines if '"name": "gangue_rate"' in ln)
    assert '"value": 0.65' in q_line
    assert q_line.startswith('        {"name": "q", "value": 0.65, "desc"')
    assert '"value"' not in b_line
    assert '"value"' not in gangue_line
    assert text.endswith("\n")


@pytest.mark.asyncio
async def test_export_idempotent_and_materializes_string_value(formulas_file):
    repo = _FakeRepo([_row(), _row(fid="gangue_gen", input_name="gangue_rate", value="横城实测均值", note="样例对账")])
    await _svc(repo).export_formulas("admin")
    first = formulas_file.read_text(encoding="utf-8", newline="")
    out2 = await _svc(repo).export_formulas("admin")
    second = formulas_file.read_text(encoding="utf-8", newline="")
    assert first == second
    assert out2["results"] == {
        "subsidence_max": {"materialized": 0, "skipped": 1},
        "gangue_gen": {"materialized": 0, "skipped": 1},
    }
    gangue_line = next(ln for ln in second.split("\n") if '"name": "gangue_rate"' in ln)
    assert '"value": "横城实测均值"' in gangue_line


@pytest.mark.asyncio
async def test_export_replaces_stale_materialized_value(formulas_file):
    text = _FORMULAS_TEXT.replace(
        '{"name": "q", "desc": "下沉系数"', '{"name": "q", "value": 0.5, "desc": "下沉系数"', 1
    )
    formulas_file.write_text(text, encoding="utf-8", newline="")
    repo = _FakeRepo([_row(value="0.65")])
    out = await _svc(repo).export_formulas("admin")
    assert out["results"] == {"subsidence_max": {"materialized": 1, "skipped": 0}}
    now = formulas_file.read_text(encoding="utf-8", newline="")
    q_line = next(ln for ln in now.split("\n") if '"name": "q"' in ln)
    assert '"value": 0.65' in q_line
    assert '"value": 0.5' not in q_line
    # 仅目标行变
    assert now.replace('"value": 0.65', '"value": 0.5', 1) == text


@pytest.mark.asyncio
async def test_clear_input_value_deletes_override(formulas_file):
    repo = _FakeRepo()
    assert await _svc(repo).clear_input_value("subsidence_max", "q") is True
    assert repo.deletes == [("subsidence_max", "q")]
