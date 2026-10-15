"""eia_paradigm_service 单元测试：锚点校验 / 两键纪律 / preview 不写盘 / 导出字节纪律 / 漂移 / 回滚。

文件 IO 全部落在 tmp_path（monkeypatch _PARADIGM_DIR），不触真实技能文件；
DB 流转以 FakeRepo 代表，集成环境（容器+PG）再验 API 层。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from yuxi.services import eia_paradigm_service as svc
from yuxi.services.eia_paradigm_service import EiaParadigmService

MD = """# 节角色范式：测试

## 适用
界定节型与职能。

## 结构骨架
1. 先
2. 后

## 范文（去实体化，仅示范句法与信息组织；实体与数值一律替换为本项目冻结值）
范文段。

## 节尾收束段
收束句。

## 句式模式
- 句式。

## 反模式（与残留门词表同源；违反=残留门 FAIL）
- 禁写。
"""

FORMS = {
    "forms": {
        "caliber_disambiguation": {
            "desc": "d1",
            "examples": [{"form": "x", "report_id": "r", "text": "t"}],
            "stats": {},
            "templates": ["模板一。"],
        },
        "numeric_citation": {
            "desc": "d2",
            "examples": [],
            "stats": {"exact_with_unit": 1.0},
            "templates": ["{量}为 {value} {unit}。"],
        },
        "table_lead": {"desc": "d3", "examples": [], "stats": {}, "templates": ["……{主题}："]},
    },
    "source": "corpus slices statistics (31 report(s))",
    "version": "1.0",
}


class FakeRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def list_drafts(self):
        return list(self.rows)

    async def upsert_draft(self, asset_kind, asset_id, content, base_hash, username):
        row = SimpleNamespace(
            id=len(self.rows) + 1,
            asset_kind=asset_kind,
            asset_id=asset_id,
            content=content,
            base_hash=base_hash,
            created_by=username,
            updated_by=username,
            created_at=None,
            updated_at=None,
        )
        self.rows = [r for r in self.rows if (r.asset_kind, r.asset_id) != (asset_kind, asset_id)] + [row]
        return row

    async def delete_draft(self, asset_kind, asset_id):
        before = len(self.rows)
        self.rows = [r for r in self.rows if (r.asset_kind, r.asset_id) != (asset_kind, asset_id)]
        return len(self.rows) < before


def _svc(repo=None):
    return EiaParadigmService(repo or FakeRepo())


def _write_assets(tmp_path, md_map=None, forms_text=None):
    tmp_path.mkdir(exist_ok=True)
    for aid, text in (md_map or {a: MD for a in svc.PARADIGM_IDS}).items():
        (tmp_path / f"{aid}.md").write_text(text, encoding="utf-8", newline="")
    ft = forms_text if forms_text is not None else json.dumps(FORMS, ensure_ascii=False, indent=2) + "\n"
    (tmp_path / "forms_catalog.json").write_text(ft, encoding="utf-8", newline="")


def _draft(kind, aid, content):
    return SimpleNamespace(
        id=1,
        asset_kind=kind,
        asset_id=aid,
        content=content,
        base_hash="x",
        created_by="alice",
        updated_by="alice",
        created_at=None,
        updated_at=None,
    )


def test_validate_md_anchor_prefix_match(tmp_path, monkeypatch):
    """锚点校验按前缀匹配——真实文件 ## 范文（…）/## 反模式（…）带后缀。"""
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    broken = MD.replace("## 节尾收束段", "## 收束")
    errs = svc._validate_md(broken)
    assert any("节尾收束段" in e for e in errs) and len(errs) == 1
    assert svc._validate_md(MD) == []


def test_save_draft_forms_rejects_extra_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    with pytest.raises(ValueError, match="仅接受"):
        asyncio.run(
            _svc().save_draft("forms_catalog", "table_lead", {"desc": "d", "templates": [], "stats": {}}, "bob")
        )


def test_save_draft_forms_validates_shapes(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    with pytest.raises(ValueError, match="templates"):
        asyncio.run(_svc().save_draft("forms_catalog", "table_lead", {"desc": "d", "templates": "不是数组"}, "bob"))
    with pytest.raises(KeyError, match="未知资产"):
        asyncio.run(_svc().save_draft("forms_catalog", "no_such", {"desc": "d", "templates": []}, "bob"))


def test_preview_reports_diff_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    repo = FakeRepo([_draft("paradigm_md", "analysis", {"md": MD.replace("1. 先", "1. 首先删掉机理性开头")})])
    out = asyncio.run(_svc(repo).preview_export())
    assert out["all_ok"] is True
    item = next(i for i in out["items"] if i["asset_id"] == "analysis")
    assert "-1. 先" in item["diff"] and "+1. 首先删掉机理性开头" in item["diff"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before  # preview 不写盘


def test_export_md_wholesale_and_forms_two_keys_only(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    monkeypatch.setattr(svc, "_SKILL_ROOT", tmp_path)  # 导出回报 paths 按 _SKILL_ROOT 取相对——随夹具一并虚拟化
    _write_assets(tmp_path)
    new_md = MD.replace("范文段。", "范文段改。")
    repo = FakeRepo(
        [
            _draft("paradigm_md", "analysis", {"md": new_md}),
            _draft(
                "forms_catalog",
                "table_lead",
                {"desc": "表题行前一非空行形态（改）", "templates": ["……{主题}：", "……{主题}如下表所列。"]},
            ),
        ]
    )
    out = asyncio.run(_svc(repo).export_paradigms("admin"))
    assert out["results"]["paradigm_md/analysis"]["materialized"] is True  # 导出回报契约
    assert (tmp_path / "analysis.md").read_text(encoding="utf-8") == new_md  # md 整文件写回
    doc = json.loads((tmp_path / "forms_catalog.json").read_text(encoding="utf-8"))
    assert doc["forms"]["table_lead"]["desc"].endswith("（改）")
    assert doc["forms"]["table_lead"]["templates"] == ["……{主题}：", "……{主题}如下表所列。"]
    assert doc["forms"]["caliber_disambiguation"] == FORMS["forms"]["caliber_disambiguation"]  # 无草稿 family 不动
    assert doc["forms"]["table_lead"]["examples"] == [] and doc["forms"]["table_lead"]["stats"] == {}  # 只写两键
    raw = (tmp_path / "forms_catalog.json").read_text(encoding="utf-8")
    assert raw.endswith("\n") and list(doc["forms"].keys()) == list(FORMS["forms"].keys())  # 键序/结尾换行不重排


def test_export_idempotent_byte_identical(tmp_path, monkeypatch):
    """同状态重复导出（草稿值与文件已一致）→ 字节不动。"""
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    same = FORMS["forms"]["table_lead"]["templates"][0]
    desc = FORMS["forms"]["table_lead"]["desc"]
    repo = FakeRepo([_draft("forms_catalog", "table_lead", {"desc": desc, "templates": [same]})])
    f = tmp_path / "forms_catalog.json"
    b0 = f.read_bytes()
    asyncio.run(_svc(repo).export_paradigms("admin"))
    assert f.read_bytes() == b0


def test_export_blocked_when_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    bad_md = MD.replace("## 结构骨架", "## 骨架")
    repo = FakeRepo([_draft("paradigm_md", "opener", {"md": bad_md})])
    with pytest.raises(ValueError, match="结构骨架"):
        asyncio.run(_svc(repo).export_paradigms("admin"))
    assert (tmp_path / "opener.md").read_text(encoding="utf-8") == MD  # 全批不写


def test_export_blocked_by_propernoun_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    from yuxi.services.eia_data_service import _SKILL_ROOT

    ent = _SKILL_ROOT / "references" / "sample_entities"
    if not ent.exists():
        pytest.skip("宿主无 sample_entities")
    term = json.loads((ent / "hengcheng.json").read_text(encoding="utf-8"))["entities"]["projects"][0]
    if term in svc._scan_generic_terms():
        pytest.skip("夹具词已被通用词豁免规则覆盖")
    repo = FakeRepo([_draft("paradigm_md", "opener", {"md": MD + f"\n泄露：{term}\n"})])
    with pytest.raises(ValueError, match="专名"):
        asyncio.run(_svc(repo).export_paradigms("admin"))


def test_drift_flagged_not_blocking(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    s = _svc(FakeRepo())
    asyncio.run(s.save_draft("forms_catalog", "table_lead", {"desc": "d3", "templates": ["……{主题}："]}, "bob"))
    # 草稿落库后文件被 bank_compile 重算（合法 JSON、stats 变化）→ base_hash 漂移
    drifted = json.loads(json.dumps(FORMS))
    drifted["forms"]["numeric_citation"]["stats"]["exact_with_unit"] = 0.9
    (tmp_path / "forms_catalog.json").write_text(
        json.dumps(drifted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
    )
    out = asyncio.run(s.preview_export())
    item = next(i for i in out["items"] if i["asset_id"] == "table_lead")
    assert item["drift"] is True and out["all_ok"] is True  # 漂移示警不阻断


def test_export_rollback_on_partial_failure(tmp_path, monkeypatch):
    """第二个资产写失败 → 已写的第一个文件回滚（全批或全不写）。"""
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    repo = FakeRepo(
        [
            _draft("paradigm_md", "opener", {"md": MD.replace("界定节型与职能。", "界定节型与职能（改）。")}),
            _draft("paradigm_md", "analysis", {"md": MD}),
        ]
    )
    s = _svc(repo)
    orig = svc._atomic_write

    def boom(path, text):
        if path.name == "analysis.md":
            raise OSError("disk full")
        orig(path, text)

    monkeypatch.setattr(svc, "_atomic_write", boom)
    with pytest.raises(OSError):
        asyncio.run(s.export_paradigms("admin"))
    assert "界定节型与职能（改）。" not in (tmp_path / "opener.md").read_text(encoding="utf-8")  # 已回滚
