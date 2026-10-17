"""eia_paradigm_service 单元测试：锚点校验 / 两键纪律 / preview 不写盘 / 导出字节纪律 / 漂移 / 回滚 / 撤回 / 空批拒绝。

文件 IO 全部落在 tmp_path（monkeypatch _PARADIGM_DIR），不触真实技能文件；
DB 流转以 FakeRepo 代表，集成环境（容器+PG）再验 API 层。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from pisuan.services import eia_paradigm_service as svc
from pisuan.services.eia_paradigm_scan import GENERIC_TERMS
from pisuan.services.eia_paradigm_service import EiaParadigmService

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
            "examples": [{"form": "x2", "report_id": "r2", "text": "t2"}],
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


_ROLES = {
    "_comment": "节角色映射（bank_compile 产物；顶层元数据键与节映射嵌套并存）",
    "schema_version": 1,
    "paradigm_dir": "references/paradigms",
    "roles": {
        "ch1_S01": "opener",
        "ch1_S02": "baseline",
        "ch2_S01": "analysis",
        "ch2_S02": "measures",
        "ch2_S03": "opener",
    },
}


def _write_roles(tmp_path):
    (tmp_path / "_roles.json").write_text(
        json.dumps(_ROLES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
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
                "numeric_citation",
                {"desc": "数值引用句式（改）", "templates": ["{量}为 {value} {unit}。", "实测 {value} {unit}。"]},
            ),
        ]
    )
    out = asyncio.run(_svc(repo).export_paradigms("admin"))
    assert out["results"]["paradigm_md/analysis"]["materialized"] is True  # 导出回报契约
    assert (tmp_path / "analysis.md").read_text(encoding="utf-8") == new_md  # md 整文件写回
    doc = json.loads((tmp_path / "forms_catalog.json").read_text(encoding="utf-8"))
    assert doc["forms"]["numeric_citation"]["desc"] == "数值引用句式（改）"
    assert doc["forms"]["numeric_citation"]["templates"] == ["{量}为 {value} {unit}。", "实测 {value} {unit}。"]
    assert doc["forms"]["caliber_disambiguation"] == FORMS["forms"]["caliber_disambiguation"]  # 无草稿 family 不动
    assert doc["forms"]["numeric_citation"]["stats"] == {"exact_with_unit": 1.0}  # 只写两键：非空 stats 原样存活
    fam = doc["forms"]["numeric_citation"]
    assert fam["examples"] == FORMS["forms"]["numeric_citation"]["examples"]  # 非空 examples 原样存活
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
    from pisuan.services.eia_data_service import _SKILL_ROOT

    ent = _SKILL_ROOT / "references" / "sample_entities"
    if not ent.exists():
        pytest.skip("宿主无 sample_entities")
    term = json.loads((ent / "hengcheng.json").read_text(encoding="utf-8"))["entities"]["projects"][0]
    if term in GENERIC_TERMS():
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


def test_overview_sync_counts_roles_and_flags_drafts(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    _write_roles(tmp_path)
    repo = FakeRepo(
        [
            _draft("paradigm_md", "analysis", {"md": MD}),
            _draft("forms_catalog", "table_lead", {"desc": "草稿描述（未物化）", "templates": ["草稿模板"]}),
        ]
    )
    out = asyncio.run(_svc(repo).load_overview())
    assert out["role_counts"] == {"opener": 2, "baseline": 1, "analysis": 1, "measures": 1}
    assert set(out["roles_map"]) == {
        "ch1_S01",
        "ch1_S02",
        "ch2_S01",
        "ch2_S02",
        "ch2_S03",
    }  # 只含节映射，元数据三键不入
    assert out["roles_map"]["ch1_S01"] == "opener"
    ana = next(i for i in out["paradigms"] if i["asset_id"] == "analysis")
    ope = next(i for i in out["paradigms"] if i["asset_id"] == "opener")
    assert ana["has_draft"] and ana["drift"] and ana["updated_by"] == "alice"  # base_hash="x"≠文件 → 漂移
    assert not ope["has_draft"] and not ope["drift"] and ope["file_hash"] == svc._sha(MD)
    fam = next(i for i in out["families"] if i["asset_id"] == "table_lead")
    assert fam["has_draft"] and fam["drift"]
    assert fam["desc"] == "d3" and fam["templates"] == ["……{主题}："]  # overview 读文件值非草稿值


def test_get_asset_forms_branch_reads_family(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    _write_roles(tmp_path)
    repo = FakeRepo([_draft("forms_catalog", "numeric_citation", {"desc": "草稿描述", "templates": ["草稿模板"]})])
    out = asyncio.run(_svc(repo).get_asset("forms_catalog", "numeric_citation"))
    assert out["family"] == {
        "desc": "d2",
        "templates": ["{量}为 {value} {unit}。"],
        "examples": FORMS["forms"]["numeric_citation"]["examples"],
        "stats": {"exact_with_unit": 1.0},
    }  # family 恰四键、读文件值
    assert out["drift"] is True  # base_hash="x"≠文件
    assert out["draft"]["content"] == {"desc": "草稿描述", "templates": ["草稿模板"]}
    assert out["draft"]["base_hash"] == "x" and out["draft"]["updated_by"] == "alice"
    out_md = asyncio.run(_svc(repo).get_asset("paradigm_md", "opener"))
    assert out_md["file_text"] == MD and out_md["draft"] is None and out_md["drift"] is False


def test_export_empty_drafts_raises(tmp_path, monkeypatch):
    """无任何草稿时 preview/export 响亮拒绝（路由层映射 400），文件不动。"""
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    s = _svc(FakeRepo())
    with pytest.raises(ValueError, match="无待导出"):
        asyncio.run(s.preview_export())
    with pytest.raises(ValueError, match="无待导出"):
        asyncio.run(s.export_paradigms("admin"))
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_withdraw_draft_removes_row_idempotent_and_validates(tmp_path, monkeypatch):
    """撤回：删行返回 True 且行消失；再撤 False；未知资产 KeyError 响亮。"""
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    s = _svc()
    asyncio.run(s.save_draft("paradigm_md", "opener", {"md": MD}, "bob"))
    assert asyncio.run(s.withdraw_draft("paradigm_md", "opener")) is True
    assert asyncio.run(s.repo.list_drafts()) == []  # 行已删，文件锚点不受影响
    assert asyncio.run(s.withdraw_draft("paradigm_md", "opener")) is False  # 再撤无行
    with pytest.raises(KeyError, match="未知资产"):
        asyncio.run(s.withdraw_draft("paradigm_md", "no_such"))


def test_get_asset_md_with_draft_shape(tmp_path, monkeypatch):
    """md 带草稿：file_text 仍是文件原文，draft 整包（content.md / base_hash / updated_by）。"""
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    drafted = MD.replace("范文段。", "范文段（草稿）。")
    repo = FakeRepo([_draft("paradigm_md", "analysis", {"md": drafted})])
    out = asyncio.run(_svc(repo).get_asset("paradigm_md", "analysis"))
    assert out["file_text"] == MD  # 文件锚点原文不受草稿影响
    assert out["draft"]["content"] == {"md": drafted}
    assert out["draft"]["base_hash"] == "x" and out["draft"]["updated_by"] == "alice"
    assert out["drift"] is True and "family" not in out  # md 分支无 family 四键
