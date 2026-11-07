"""eia_stage_service 测试（P2：stages forms 口径字段编辑 + 导出物化）。

字节纪律（bug-417 铁律）：导出走文本级插接（CRLF 字面量 / 8 空格条目 / 保尾态），
禁止 json.load→dumps 全文件重写——测试以「孤立 CR 为零 + 未动族字节原样 + 幂等」三断言钉死。
编辑边界：add 只增字段、amend 只改 label/required/note；name 禁改；文件锚点禁删；
未物化 DB 裁决行可撤回。repo 契约以 fake 忠实模拟（薄层不直测，同 eia_standard 先例）。
"""

import json
from types import SimpleNamespace

import pytest

from pisuan.services import eia_stage_service as svc_mod


def _write_stage_file(root, stage: str, text: str) -> None:
    (root / f"{stage}.json").write_text(text, encoding="utf-8", newline="")


def _stage_doc() -> dict:
    return {
        "version": "test",
        "stage": "planning_eia",
        "forms": {
            "subsidence": {
                "label": "沉陷预测",
                "file": "subsidence.json",
                "required": True,
                "chapters": ["ch5"],
                "note": "测试族",
                "fields": [
                    {"name": "subsidence_coef", "label": "下沉系数", "type": "number", "required": True},
                    {"name": "max_subsidence_mm", "label": "最大下沉值", "type": "number", "required": True},
                ],
            },
            "empty_fam": {
                "label": "空族",
                "file": "empty.json",
                "required": False,
                "chapters": ["ch6"],
                "fields": [],
            },
        },
    }


def _stage_text() -> str:
    # 同实况：CRLF + indent2 + 无尾换行
    return json.dumps(_stage_doc(), ensure_ascii=False, indent=2).replace("\n", "\r\n")


class _FakeRepo:
    """repo 契约模拟：list_edits / upsert_edit / delete_edit，(stage, family, field) 键去重。"""

    def __init__(self):
        self.rows: dict[tuple, SimpleNamespace] = {}
        self.deleted: list[tuple] = []

    async def list_edits(self, stage=None):
        return [r for r in self.rows.values() if stage is None or r.stage == stage]

    async def upsert_edit(self, stage, family_key, field_name, edit_kind, field_json, username):
        row = SimpleNamespace(
            id=len(self.rows) + 1,
            stage=stage,
            family_key=family_key,
            field_name=field_name,
            edit_kind=edit_kind,
            field_json=field_json,
            decided_by=username,
        )
        self.rows[(stage, family_key, field_name)] = row
        return row

    async def delete_edit(self, stage, family_key, field_name):
        self.deleted.append((stage, family_key, field_name))
        return self.rows.pop((stage, family_key, field_name), None) is not None


def _svc(monkeypatch, tmp_path, repo=None):
    monkeypatch.setattr(svc_mod, "STAGES_DIR", tmp_path)
    _write_stage_file(tmp_path, "planning_eia", _stage_text())
    return svc_mod.EiaStageService(repo=repo or _FakeRepo())


_ADD = {
    "edit_kind": "add",
    "name": "surface_move_angle",
    "label": "表土移动角",
    "type": "number",
    "required": False,
    "unit": "°",
}


# ── 列表合并态 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_forms_merges_db_edits_with_source_and_pending(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    await svc.save_stage_field("planning_eia", "subsidence", dict(_ADD), "王工")
    out = await svc.list_stage_forms("planning_eia")

    fam = out["stages"]["planning_eia"]["families"]["subsidence"]
    names = [f["name"] for f in fam["fields"]]
    assert names == ["subsidence_coef", "max_subsidence_mm", "surface_move_angle"]
    file_field = fam["fields"][0]
    db_field = fam["fields"][2]
    assert file_field["source"] == "file"
    assert db_field["source"] == "db" and db_field["pending"] is True
    assert db_field["decided_by"] == "王工" and db_field["edit_kind"] == "add"


@pytest.mark.asyncio
async def test_list_forms_amend_overlay_marks_pending_until_materialized(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    await svc.save_stage_field(
        "planning_eia",
        "subsidence",
        {"edit_kind": "amend", "field_name": "subsidence_coef", "label": "下沉系数（岩移回归）"},
        "王工",
    )
    out = await svc.list_stage_forms("planning_eia")
    field = out["stages"]["planning_eia"]["families"]["subsidence"]["fields"][0]
    assert field["label"] == "下沉系数"  # 文件锚点值不变
    assert field["db_edit"]["edit_kind"] == "amend"
    assert field["db_edit"]["pending"] is True  # 文件还是旧 label → 待导出
    assert field["db_edit"]["field"]["label"] == "下沉系数（岩移回归）"


# ── 保存校验 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_add_rejects_bad_slug_and_duplicate(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    for bad_name in ("SurfaceAngle", "has space", "1abc", "角a"):
        with pytest.raises(ValueError, match="字段标识"):
            await svc.save_stage_field("planning_eia", "subsidence", {**_ADD, "name": bad_name}, "王工")
    # 与文件锚点字段撞名
    with pytest.raises(ValueError, match="已存在"):
        await svc.save_stage_field("planning_eia", "subsidence", {**_ADD, "name": "subsidence_coef"}, "王工")


@pytest.mark.asyncio
async def test_save_add_rejects_unknown_stage_or_family(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    with pytest.raises(KeyError):
        await svc.save_stage_field("nope_eia", "subsidence", dict(_ADD), "王工")
    with pytest.raises(KeyError):
        await svc.save_stage_field("planning_eia", "nope_fam", dict(_ADD), "王工")


@pytest.mark.asyncio
async def test_save_add_rejects_bad_type_and_blank_label(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="类型"):
        await svc.save_stage_field("planning_eia", "subsidence", {**_ADD, "type": "object"}, "王工")
    with pytest.raises(ValueError, match="中文名称"):
        await svc.save_stage_field("planning_eia", "subsidence", {**_ADD, "label": "  "}, "王工")


@pytest.mark.asyncio
async def test_save_add_accepts_enum_prefix_and_upserts_same_name(monkeypatch, tmp_path):
    repo = _FakeRepo()
    svc = _svc(monkeypatch, tmp_path, repo)
    payload = {**_ADD, "type": "enum:规划环评|项目环评"}
    await svc.save_stage_field("planning_eia", "subsidence", payload, "王工")
    await svc.save_stage_field("planning_eia", "subsidence", {**payload, "label": "表土移动角改"}, "李工")
    assert len(repo.rows) == 1  # 同键 upsert 不重复
    assert repo.rows[("planning_eia", "subsidence", "surface_move_angle")].decided_by == "李工"


@pytest.mark.asyncio
async def test_save_amend_patches_only_label_required_and_refuses_name(monkeypatch, tmp_path):
    repo = _FakeRepo()
    svc = _svc(monkeypatch, tmp_path, repo)
    await svc.save_stage_field(
        "planning_eia",
        "subsidence",
        {"edit_kind": "amend", "field_name": "max_subsidence_mm", "required": False},
        "王工",
    )
    row = repo.rows[("planning_eia", "subsidence", "max_subsidence_mm")]
    assert row.edit_kind == "amend"
    assert row.field_json == {"required": False}
    with pytest.raises(ValueError, match="字段标识"):
        await svc.save_stage_field(
            "planning_eia",
            "subsidence",
            {"edit_kind": "amend", "field_name": "max_subsidence_mm", "name": "other", "label": "x"},
            "王工",
        )
    with pytest.raises(KeyError):
        await svc.save_stage_field(
            "planning_eia",
            "subsidence",
            {"edit_kind": "amend", "field_name": "not_there", "label": "x"},
            "王工",
        )


# ── 撤回（仅草稿态 DB 裁决行）────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_pending_edit_roundtrip(monkeypatch, tmp_path):
    repo = _FakeRepo()
    svc = _svc(monkeypatch, tmp_path, repo)
    await svc.save_stage_field("planning_eia", "subsidence", dict(_ADD), "王工")
    out = await svc.delete_stage_field("planning_eia", "subsidence", "surface_move_angle")
    assert out["deleted"] is True
    assert repo.rows == {}
    with pytest.raises(KeyError):
        await svc.delete_stage_field("planning_eia", "subsidence", "surface_move_angle")


# ── 导出物化（字节纪律）──────────────────────────────────────────────────────


def _assert_crlf_discipline(text: str) -> None:
    assert "\r\n" in text, "文件应为 CRLF"
    assert "\r" not in text.replace("\r\n", ""), "存在孤立 CR（行尾形态混用）"


@pytest.mark.asyncio
async def test_export_applies_add_and_amend_with_byte_discipline(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    original = _stage_text()
    await svc.save_stage_field("planning_eia", "subsidence", dict(_ADD), "王工")
    await svc.save_stage_field(
        "planning_eia",
        "subsidence",
        {"edit_kind": "amend", "field_name": "max_subsidence_mm", "label": "最大下沉值（mm）", "required": False},
        "王工",
    )
    out = await svc.export_stage_forms("planning_eia", "王工")
    assert out["results"]["planning_eia"]["added"] == 1
    assert out["results"]["planning_eia"]["amended"] == 1

    text = (tmp_path / "planning_eia.json").read_text(encoding="utf-8", newline="")
    _assert_crlf_discipline(text)
    assert text.endswith("}"), "尾态须保持无尾换行"
    doc = json.loads(text)
    fam = doc["forms"]["subsidence"]["fields"]
    assert [f["name"] for f in fam] == ["subsidence_coef", "max_subsidence_mm", "surface_move_angle"]
    assert fam[1]["label"] == "最大下沉值（mm）" and fam[1]["required"] is False
    assert fam[2]["unit"] == "°"

    # 未动族字节原样（含缩进/行尾）：empty_fam 块在前后文本中逐字节一致
    def _fam_block(t, fam_key):
        i = t.index(f'"{fam_key}": {{')
        return t[i : t.index("\r\n    }", i) + len("\r\n    }")]  # family 闭合于 4 空格（indent2 深度 2）

    assert _fam_block(text, "empty_fam") == _fam_block(original, "empty_fam")


@pytest.mark.asyncio
async def test_export_into_empty_fields_family_expands_array(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    await svc.save_stage_field(
        "planning_eia",
        "empty_fam",
        {"edit_kind": "add", "name": "first_field", "label": "首字段", "type": "string", "required": True},
        "王工",
    )
    await svc.export_stage_forms("planning_eia", "王工")
    doc = json.loads((tmp_path / "planning_eia.json").read_text(encoding="utf-8"))
    assert doc["forms"]["empty_fam"]["fields"] == [
        {"name": "first_field", "label": "首字段", "type": "string", "required": True}
    ]


@pytest.mark.asyncio
async def test_export_is_idempotent_after_materialized(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    await svc.save_stage_field("planning_eia", "subsidence", dict(_ADD), "王工")
    await svc.export_stage_forms("planning_eia", "王工")
    once = (tmp_path / "planning_eia.json").read_bytes()
    out = await svc.export_stage_forms("planning_eia", "王工")
    assert out["results"]["planning_eia"]["added"] == 0
    assert (tmp_path / "planning_eia.json").read_bytes() == once, "二次导出须字节不动"


@pytest.mark.asyncio
async def test_export_without_edits_raises(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="无待导出"):
        await svc.export_stage_forms("planning_eia", "王工")


@pytest.mark.asyncio
async def test_amend_pending_flag_flips_after_export(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    await svc.save_stage_field(
        "planning_eia",
        "subsidence",
        {"edit_kind": "amend", "field_name": "subsidence_coef", "label": "下沉系数q"},
        "王工",
    )
    await svc.export_stage_forms("planning_eia", "王工")
    out = await svc.list_stage_forms("planning_eia")
    field = out["stages"]["planning_eia"]["families"]["subsidence"]["fields"][0]
    assert field["label"] == "下沉系数q"
    assert field["db_edit"]["pending"] is False
