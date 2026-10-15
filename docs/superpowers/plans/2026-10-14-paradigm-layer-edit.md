# 写作范式层查询与编辑页 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给写作范式层三类资产（paradigms/*.md、forms_catalog.json、_roles.json 只读）补上查询+编辑页：DB 草稿为编辑唯一真相，admin「导出物化」回写技能 references 文件，UI 不直接改数据文件。

**Architecture:** 单通用草稿表 `eia_paradigm_drafts`（UNIQUE(asset_kind, asset_id)，base_hash 漂移检测）+ 6 个端点（挂既有 `domain_factory` 路由）+ `eia_paradigm_service`（读/校验/diff/validate-all-then-write 写入）+ 纯模块 `eia_paradigm_scan`（专名扫描，承方向 A A1 红线）+ 前端数据工厂新分组两页（像素基准 = 原型 s12/s13+exportModal）。导出先例 = `eia_formula_service`（方案乙同构）。

**Tech Stack:** FastAPI + SQLAlchemy async（pg_insert on_conflict）/ pytest（unit 纯逻辑 + integration 认证门槛）/ Vue3 + antd + less（factory-ui.less 配方，`.ewp` 命名空间）。

**设计文档:** `docs/vibe/2026-10-14-paradigm-layer-edit-design.md`（已评审）。**原型:** `docs/vibe/prototypes/2026-10-12-eia-p2-ui.html` 的 s12/s13/exportModal。

**环境约定（全程适用）:**
- 后端测试在容器内跑：`docker exec api-dev pytest /app/test/unit/test_xxx.py -v`（integration 在 `/app/test/integration/api/`）。容器名以 `docker ps` 实际为准（若栈是 pisuan-localized，则容器名为 `pisuan-localized-api-1` 等，下同以 `<api容器>` 代指）。
- 前端 lint 走容器：`docker exec pisuan-localized-web-1 sh -c "cd /app && npx prettier --write src/... && npx eslint src/... --fix && echo LINT_OK"`（容器 /app 即 web 根，路径不带 `web/` 前缀）。
- 提交信息：中文 Conventional Commits，结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- **禁止**把技能 references 文件的改动直接提交进这些任务的代码提交之外——导出物化只落运行栈，回流 pisuan-custom 是人工动作；集成测试不得写真实技能文件（见 Task 6 说明）。

---

### Task 1: 数据模型 + 迁移 v17（eia_paradigm_drafts）

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`（eia 模型区，`EiaFormulaOverride` 类之后）
- Modify: `backend/package/yuxi/storage/postgres/manager.py`（新增 `upgrade_business_v16_to_v17`，跟在 `upgrade_business_v15_to_v16` 之后）
- Modify: `backend/package/yuxi/storage_migration.py`（v16 派发行之后加 v17）
- Modify: `backend/package/yuxi/storage/postgres/manager.py` 头部 import（`EiaParadigmDraft` 加入既有 `EiaFormulaOverride` 同一 import 块）

- [ ] **Step 1: 在 models_domain_factory.py 中追加模型**

在 `class EiaFormulaOverride` 的 `to_dict` 方法结束后（该类整体结束后空两行）插入：

```python
class EiaParadigmDraft(Base):
    """Domain Factory - 写作范式层草稿（DB 草稿=编辑唯一真相，admin 显式导出物化回写 references/paradigms/*）

    asset_kind='paradigm_md' 时 content={"md": 整文件文本}；'forms_catalog' 时 content 仅含
    {"desc": str, "templates": [str]} 两键（stats/examples 为 bank_compile 语料统计，恒只读，
    多余键服务层拒收）。base_hash 为保存草稿时的数据文件 sha256——导出前重算比对检测文件
    漂移（bank_compile 整文件重算场景），漂移不阻断，导出即以草稿为准恢复。
    """

    __tablename__ = "eia_paradigm_drafts"
    __table_args__ = (UniqueConstraint("asset_kind", "asset_id", name="uq_epd_kind_asset"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_kind = Column(String(32), nullable=False)  # 'paradigm_md' | 'forms_catalog'
    asset_id = Column(String(64), nullable=False)  # 角色名（opener/baseline/analysis/measures）| 句式族名（3）
    content = Column(JSONB, nullable=False)  # 见类注（两键纪律由服务层执法）
    base_hash = Column(String(64), nullable=False)
    created_by = Column(String(64), nullable=True)
    updated_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asset_kind": self.asset_kind,
            "asset_id": self.asset_id,
            "content": self.content,
            "base_hash": self.base_hash,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
```

（`JSONB` 已在该模块头导入——`EiaStandardReview.row_json` 在用；`format_utc_datetime` 同理。）

- [ ] **Step 2: manager.py 头部 import 加入 EiaParadigmDraft**

在 manager.py 顶部既有 `from ...models_domain_factory import (EiaFormulaOverride, ...)` 块中按字母序加入 `EiaParadigmDraft`。

- [ ] **Step 3: manager.py 新增迁移方法**

在 `upgrade_business_v15_to_v16` 方法之后新增（照抄 v16 的骨架，只换版本号与表）：

```python
    async def upgrade_business_v16_to_v17(self) -> None:
        """[pisuan-custom] v17：写作范式层草稿表（存量库 create_all 不补表，显式建 + 记版本）。

        幂等：version=17 直接返回；表用 create_all(tables=[...]) 仅补新表，不动其他。
        """
        self._check_initialized()
        async with self.async_engine.begin() as conn:
            version = await conn.scalar(
                text(f"SELECT version FROM {SCHEMA_VERSION_TABLE} WHERE domain = 'business' FOR UPDATE")
            )
            if version == 17:
                return
            if version not in (None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16):
                raise RuntimeError(f"Unsupported business schema version: {version}")
            await conn.run_sync(
                lambda sync_conn: DomainFactoryBase.metadata.create_all(sync_conn, tables=[EiaParadigmDraft.__table__])
            )
            await conn.execute(
                text(f"""
                    INSERT INTO {SCHEMA_VERSION_TABLE} (domain, version, applied_at)
                    VALUES ('business', 17, CURRENT_TIMESTAMP)
                    ON CONFLICT (domain) DO UPDATE SET version = 17, applied_at = EXCLUDED.applied_at
                """)
            )
```

- [ ] **Step 4: storage_migration.py 派发行**

在 `await pg_manager.upgrade_business_v15_to_v16()` 块之后（`if knowledge_version is None:` 之前）追加：

```python
            # [pisuan-custom] v17：写作范式层草稿表（存量库显式补表，幂等）
            if business_version in {None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}:
                await pg_manager.upgrade_business_v16_to_v17()
```

- [ ] **Step 5: 容器内验证导入 + 迁移幂等**

Run: `docker exec <api容器> python -c "from yuxi.storage.postgres.models_domain_factory import EiaParadigmDraft; print(EiaParadigmDraft.__tablename__)"`
Expected: `eia_paradigm_drafts`

Run: `docker exec <api容器> python -m yuxi.storage_migration`（成功无栈）后紧跟第二次执行（幂等，应同样无错直接过）。
Expected: 两次均退出码 0；`docker exec <api容器> python -c` 用 async session 查 `SELECT version FROM business_schema_version WHERE domain='business'`（表名以 SCHEMA_VERSION_TABLE 实际值为准，可从 manager.py 顶部读到）应得 17。

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/storage_migration.py
git commit -m "feat(domain-factory): 写作范式层草稿表 eia_paradigm_drafts（迁移 v17）"
```

---

### Task 2: 专名扫描器（纯模块，TDD）

**Files:**
- Create: `backend/package/yuxi/services/eia_paradigm_scan.py`
- Test: `backend/test/unit/test_eia_paradigm_scan.py`

- [ ] **Step 1: 先写失败测试**

```python
"""eia_paradigm_scan 单元测试：专名扫描集构建与命中（承方向 A A1 红线）。

扫描集依赖仓库内置 coal-eia-writer 技能 sample_entities（宿主无技能目录时自动跳过）。
夹具动态取自真实黑名单（不硬编码实体串，防黑名单迭代漂移）。
"""

import json
from pathlib import Path

import pytest

from yuxi.services import eia_paradigm_scan
from yuxi.services.eia_data_service import _SKILL_ROOT

_ENTITIES_DIR = _SKILL_ROOT / "references" / "sample_entities"

pytestmark = pytest.mark.skipif(not _ENTITIES_DIR.exists(), reason="宿主无技能 sample_entities 目录")


def _blacklists() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_ENTITIES_DIR.glob("*.json")) if p.name != "_index.json"]


def test_propernoun_hit_in_text():
    """黑名单专名（单文件独有）进扫描集，出现在文本中即命中。"""
    doc = next(d for d in _blacklists() if d["sample_slug"] == "hengcheng")
    term = doc["entities"]["projects"][0]
    assert term not in eia_paradigm_scan.GENERIC_TERMS
    assert term in eia_paradigm_scan.scan_text(f"本报告以{term}规划区为对象。")


def test_high_frequency_and_generic_terms_exempt():
    """≥3 份黑名单共现的词与各文件 generic_terms 声明的通用词不入扫描集。"""
    counts: dict[str, int] = {}
    for d in _blacklists():
        for terms in d["entities"].values():
            for t in terms:
                counts[t] = counts.get(t, 0) + 1
    freq = [t for t, n in counts.items() if n >= 3]
    generic = {g for d in _blacklists() for g in d.get("generic_terms", [])}
    assert eia_paradigm_scan.GENERIC_TERMS >= set(freq) | generic
    for t in list(set(freq) | generic)[:5]:
        assert t not in eia_paradigm_scan.scan_text(f"文本提及{t}不判命中。")


def test_substring_of_generic_exempt():
    """专名若为某通用词的子串（或反之）→ 豁免（方向 A §8 规则）。"""
    generic = sorted(eia_paradigm_scan.GENERIC_TERMS)
    assert generic, "通用词集不应为空"
    g = generic[0]
    assert g not in eia_paradigm_scan.scan_text(f"xx{g}yy")


def test_scan_deterministic_sorted():
    hits = eia_paradigm_scan.scan_text("".join(sorted(eia_paradigm_scan.PROPER_NOUNS)[:3]))
    assert hits == sorted(hits)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec <api容器> pytest /app/test/unit/test_eia_paradigm_scan.py -v`
Expected: FAIL/ERROR —— `ModuleNotFoundError: No module named 'yuxi.services.eia_paradigm_scan'`（或 ImportError 属性缺失）

- [ ] **Step 3: 实现扫描模块**

```python
"""范式 md 专名扫描（承方向 A A1 红线：导出写入前 0 命中）。

扫描集 = 24 份 sample_entities 黑名单 entities 五类（projects/mines/orgs/places/sensitive）
的并集，剔除通用词。通用词（豁免集）= ①各文件 generic_terms 显式声明（含「/」复合作逐段
拆分）②出现在 ≥3 份不同文件黑名单中的词 ③专名与任一通用词互为子串者。仅对剩余专名集
断言 0 命中（子串匹配）。
"""

from functools import lru_cache
import json
from pathlib import Path

from yuxi.services.eia_data_service import _SKILL_ROOT

ENTITIES_DIR = _SKILL_ROOT / "references" / "sample_entities"
GENERIC_MIN_FILES = 3


def _build_index(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    counts: dict[str, int] = {}
    generic: set[str] = set()
    for p in sorted(root.glob("*.json")):
        if p.name == "_index.json":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        for terms in doc.get("entities", {}).values():
            for t in terms:
                counts[t] = counts.get(t, 0) + 1
        for g in doc.get("generic_terms", []):
            generic.update(g.split("/"))
    freq = {t for t, n in counts.items() if n >= GENERIC_MIN_FILES}
    generic |= freq
    proper = {t for t in counts if t not in generic and not any(t in g or g in t for g in generic)}
    return frozenset(proper), frozenset(generic)


@lru_cache(maxsize=8)
def _cached(root: str) -> tuple[frozenset[str], frozenset[str]]:
    return _build_index(Path(root))


def _index():
    return _cached(str(ENTITIES_DIR))


def scan_text(text: str, root: Path | None = None) -> list[str]:
    """返回 text 中命中的专名（排序确定性）；root 仅测试注入用。"""
    proper, _ = _cached(str(root or ENTITIES_DIR))
    return sorted(t for t in proper if t in text)


def PROPER_NOUNS() -> frozenset[str]:
    return _index()[0]


def GENERIC_TERMS() -> frozenset[str]:
    return _index()[1]
```

注意：测试里用的是 `eia_paradigm_scan.GENERIC_TERMS`（集合语义）与 `PROPER_NOUNS`——上面以**函数**形式暴露（惰性缓存，导入零开销）。把测试中三处 `eia_paradigm_scan.GENERIC_TERMS` 改为 `eia_paradigm_scan.GENERIC_TERMS()`、`eia_paradigm_scan.PROPER_NOUNS` 改为 `eia_paradigm_scan.PROPER_NOUNS()` 后再进 Step 4（函数名首字母大写在此仅表「集」语义，不引入常量导入期 IO）。

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec <api容器> pytest /app/test/unit/test_eia_paradigm_scan.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/eia_paradigm_scan.py backend/test/unit/test_eia_paradigm_scan.py
git commit -m "feat(domain-factory): 范式导出前置专名扫描器（sample_entities 黑名单聚合+通用词豁免）"
```

---

### Task 3: 范式仓库 + 服务层（读/存/撤/校验/diff/导出，TDD）

**Files:**
- Create: `backend/package/yuxi/repositories/eia_paradigm_repository.py`
- Create: `backend/package/yuxi/services/eia_paradigm_service.py`
- Test: `backend/test/unit/test_eia_paradigm_service.py`

- [ ] **Step 1: 写仓库（薄层，集成环境覆盖，无单测）**

```python
"""写作范式层草稿的数据访问边界（每资产 (asset_kind, asset_id) 至多一份活跃草稿）。

thin repository：同键保存走 upsert 覆盖；撤回即删行（文件锚点不受影响）。
"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaParadigmDraft
from yuxi.utils.datetime_utils import utc_now_naive


class EiaParadigmRepository:
    """eia_paradigm_drafts 表访问（薄层）。"""

    async def list_drafts(self) -> list[EiaParadigmDraft]:
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.scalars(select(EiaParadigmDraft).order_by(EiaParadigmDraft.id))).all()
            return list(rows)

    async def upsert_draft(
        self, asset_kind: str, asset_id: str, content: dict[str, Any], base_hash: str, username: str
    ) -> EiaParadigmDraft:
        now = utc_now_naive()
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                pg_insert(EiaParadigmDraft)
                .values(
                    asset_kind=asset_kind,
                    asset_id=asset_id,
                    content=content,
                    base_hash=base_hash,
                    created_by=username,
                    updated_by=username,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_epd_kind_asset",
                    set_={
                        "content": content,
                        "base_hash": base_hash,
                        "updated_by": username,
                        "updated_at": now,
                    },
                )
                .returning(EiaParadigmDraft)
            )
            row = (await session.scalars(stmt)).one()
            await session.commit()
            return row

    async def delete_draft(self, asset_kind: str, asset_id: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            res = await session.execute(
                delete(EiaParadigmDraft).where(
                    EiaParadigmDraft.asset_kind == asset_kind, EiaParadigmDraft.asset_id == asset_id
                )
            )
            await session.commit()
            return (res.rowcount or 0) > 0
```

- [ ] **Step 2: 先写服务层失败测试（monkeypatch `_PARADIGM_DIR` 到 tmp_path，FakeRepo 隔离 DB）**

```python
"""eia_paradigm_service 单元测试：锚点校验 / 两键纪律 / preview 不写盘 / 导出字节纪律 / 漂移 / 回滚。

文件 IO 全部落在 tmp_path（monkeypatch _PARADIGM_DIR），不触真实技能文件；
DB 流转以 FakeRepo 代表，集成环境（容器+PG）再验 API 层。
"""

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
        id=1, asset_kind=kind, asset_id=aid, content=content, base_hash="x",
        created_by="alice", updated_by="alice", created_at=None, updated_at=None,
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
        asyncio_run = __import__("asyncio").run
        asyncio_run(_svc().save_draft("forms_catalog", "table_lead", {"desc": "d", "templates": [], "stats": {}}, "bob"))


def test_save_draft_forms_validates_shapes(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    import asyncio

    with pytest.raises(ValueError, match="templates"):
        asyncio.run(_svc().save_draft("forms_catalog", "table_lead", {"desc": "d", "templates": "不是数组"}, "bob"))
    with pytest.raises(KeyError, match="未知资产"):
        asyncio.run(_svc().save_draft("forms_catalog", "no_such", {"desc": "d", "templates": []}, "bob"))


def test_preview_reports_diff_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    import asyncio

    out = asyncio.run(
        _svc(FakeRepo([_draft("paradigm_md", "analysis", {"md": MD.replace("1. 先", "1. 首先删掉机理性开头")})])).preview_export()
    )
    assert out["all_ok"] is True
    item = next(i for i in out["items"] if i["asset_id"] == "analysis")
    assert "-1. 先" in item["diff"] and "+1. 首先删掉机理性开头" in item["diff"]  # 勘误：difflib 前缀无空格
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before  # preview 不写盘


def test_export_md_wholesale_and_forms_two_keys_only(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
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
    import asyncio

    out = asyncio.run(_svc(repo).export_paradigms("admin"))
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
    repo = FakeRepo([_draft("forms_catalog", "table_lead", {"desc": FORMS["forms"]["table_lead"]["desc"], "templates": [same]})])
    import asyncio

    f = tmp_path / "forms_catalog.json"
    b0 = f.read_bytes()
    asyncio.run(_svc(repo).export_paradigms("admin"))
    assert f.read_bytes() == b0


def test_export_blocked_when_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    bad_md = MD.replace("## 结构骨架", "## 骨架")
    repo = FakeRepo([_draft("paradigm_md", "opener", {"md": bad_md})])
    import asyncio

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
    pytest.importorskip("yuxi.services.eia_paradigm_scan")
    term = json.loads((ent / "hengcheng.json").read_text(encoding="utf-8"))["entities"]["projects"][0]
    if term in svc._scan_generic_terms():
        pytest.skip("夹具词已被通用词豁免规则覆盖")
    repo = FakeRepo([_draft("paradigm_md", "opener", {"md": MD + f"\n泄露：{term}\n"})])
    import asyncio

    with pytest.raises(ValueError, match="专名"):
        asyncio.run(_svc(repo).export_paradigms("admin"))


def test_drift_flagged_not_blocking(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARADIGM_DIR", tmp_path)
    _write_assets(tmp_path)
    import asyncio

    s = _svc(FakeRepo())
    asyncio.run(s.save_draft("forms_catalog", "table_lead", {"desc": "d3", "templates": ["……{主题}："]}, "bob"))
    # 草稿落库后文件被外部改写（bank_compile 重算场景）——必须是合法 JSON（追加文本会破坏
    # json.loads，splice 报错则 all_ok=False 自相矛盾），故改为 stats 值漂移
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
    import asyncio

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
```

- [ ] **Step 3: 跑测试确认失败**

Run: `docker exec <api容器> pytest /app/test/unit/test_eia_paradigm_service.py -v`
Expected: ERROR —— `cannot import name 'EiaParadigmService'`

- [ ] **Step 4: 实现服务层**

```python
"""写作范式层编辑服务（s12/s13：DB 草稿=编辑唯一真相 + admin 导出物化回写 references/paradigms/*）。

编辑边界（2026-10-14 设计）：paradigm md 整文件草稿；forms_catalog 仅 desc/templates 两键
（stats/examples 为 bank_compile 语料统计只读）；_roles.json 只读。导出 validate-all-then-write：
锚点小节 / forms 两键形状 / 专名扫描任一不过 → 全批不写。写入字节纪律：forms 走整文件
json round-trip（indent=2 + 结尾换行，实测与现文件逐字节恒等）仅改两键，键序不重排；
md 整文件写回。base_hash 为存草稿时文件 sha256，导出前重算比对 → drift 标记（不阻断，
admin 确认 diff 即以草稿为准恢复）。
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_paradigm_repository import EiaParadigmRepository
from yuxi.services import eia_paradigm_scan
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.utils import logger

_PARADIGM_DIR = _SKILL_ROOT / "references" / "paradigms"
KIND_MD = "paradigm_md"
KIND_FORMS = "forms_catalog"
KINDS = (KIND_MD, KIND_FORMS)
PARADIGM_IDS = ("opener", "baseline", "analysis", "measures")
FAMILY_IDS = ("caliber_disambiguation", "numeric_citation", "table_lead")
ANCHORS = ("## 适用", "## 结构骨架", "## 范文", "## 节尾收束段", "## 句式模式", "## 反模式")


def _asset_path(kind: str, asset_id: str):
    if kind == KIND_MD:
        return _PARADIGM_DIR / f"{asset_id}.md"
    return _PARADIGM_DIR / "forms_catalog.json"


def _known_asset(kind: str, asset_id: str) -> None:
    if kind not in KINDS:
        raise KeyError(f"未知资产类型: {kind}")
    if kind == KIND_MD and asset_id not in PARADIGM_IDS:
        raise KeyError(f"未知资产: {asset_id}")
    if kind == KIND_FORMS and asset_id not in FAMILY_IDS:
        raise KeyError(f"未知资产: {asset_id}")


def _read_text(path) -> str:
    if not path.exists():
        raise KeyError(f"数据文件未找到: {path}")
    return path.read_text(encoding="utf-8", newline="")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scan_generic_terms() -> frozenset[str]:
    return eia_paradigm_scan.GENERIC_TERMS()


def _validate_md(text: str) -> list[str]:
    """锚点小节在位（前缀匹配——范文/反模式标题带括号后缀）。"""
    return [f"锚点小节缺失: {a}" for a in ANCHORS if not any(line.startswith(a) for line in text.splitlines())]


def _load_forms_doc(text: str) -> dict:
    doc = json.loads(text)
    if not isinstance(doc.get("forms"), dict):
        raise ValueError("forms_catalog.json 结构异常：缺 forms 对象")
    return doc


def _validate_forms_content(asset_id: str, content: dict) -> None:
    if set(content) - {"desc", "templates"}:
        raise ValueError(f"{asset_id}: 草稿仅接受 desc/templates 两键（stats/examples 只读），多余键: {sorted(set(content) - {'desc', 'templates'})}")
    if not isinstance(content.get("desc"), str) or not content["desc"].strip():
        raise ValueError(f"{asset_id}: desc 必须为非空字符串")
    tpls = content.get("templates")
    if not isinstance(tpls, list) or not tpls or not all(isinstance(t, str) and t.strip() for t in tpls):
        raise ValueError(f"{asset_id}: templates 必须为非空字符串数组")


def _splice_forms(text: str, drafts: dict[str, dict]) -> tuple[str, bool]:
    """仅替换有草稿 family 的 desc/templates 两键；json round-trip 保证其余字节不动。"""
    doc = _load_forms_doc(text)
    for fid, content in drafts.items():
        fam = doc["forms"][fid]
        fam["desc"] = content["desc"]
        fam["templates"] = content["templates"]
    new_text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return new_text, new_text != text


def _unified_diff(name: str, old: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), fromfile=f"{name}: 文件", tofile=f"{name}: 草稿", lineterm=""
        )
    )


def _atomic_write(path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


class EiaParadigmService:
    """范式层：overview / get / save_draft / withdraw_draft / preview_export / export_paradigms。"""

    def __init__(self, repo: EiaParadigmRepository | None = None):
        self.repo = repo or EiaParadigmRepository()

    # ── 查询 ──

    async def load_overview(self) -> dict[str, Any]:
        drafts = {(d.asset_kind, d.asset_id): d for d in await self.repo.list_drafts()}
        return await run_in_threadpool(self._overview_sync, drafts)

    def _overview_sync(self, drafts: dict) -> dict[str, Any]:
        roles = json.loads(_read_text(_PARADIGM_DIR / "_roles.json"))
        role_map = {k: v for k, v in roles.items() if not k.startswith("_")}
        counts = {r: sum(1 for v in role_map.values() if v == r) for r in PARADIGM_IDS}
        paradigms = []
        for aid in PARADIGM_IDS:
            d = drafts.get((KIND_MD, aid))
            fh = _sha(_read_text(_md_file(aid)))
            paradigms.append(
                {
                    "kind": KIND_MD,
                    "asset_id": aid,
                    "has_draft": d is not None,
                    "drift": bool(d) and d.base_hash != fh,
                    "updated_by": d.updated_by if d else None,
                    "file_hash": fh,
                }
            )
        forms_text = _read_text(_PARADIGM_DIR / "forms_catalog.json")
        forms_doc = _load_forms_doc(forms_text)
        families = []
        for fid in FAMILY_IDS:
            d = drafts.get((KIND_FORMS, fid))
            families.append(
                {
                    "kind": KIND_FORMS,
                    "asset_id": fid,
                    "desc": forms_doc["forms"][fid].get("desc", ""),
                    "templates": forms_doc["forms"][fid].get("templates", []),
                    "has_draft": d is not None,
                    "drift": bool(d) and d.base_hash != _sha(forms_text),
                    "updated_by": d.updated_by if d else None,
                }
            )
        return {"paradigms": paradigms, "families": families, "role_counts": counts, "roles_map": role_map}

    def _md_file(self, aid: str):
        return _PARADIGM_DIR / f"{aid}.md"

    async def get_asset(self, kind: str, asset_id: str) -> dict[str, Any]:
        _known_asset(kind, asset_id)
        drafts = {(d.asset_kind, d.asset_id): d for d in await self.repo.list_drafts()}
        return await run_in_threadpool(self._get_sync, kind, asset_id, drafts)

    def _get_sync(self, kind: str, asset_id: str, drafts: dict) -> dict[str, Any]:
        path = _asset_path(kind, asset_id)
        text = _read_text(path)
        fh = _sha(text)
        d = drafts.get((kind, asset_id))
        out: dict[str, Any] = {
            "kind": kind,
            "asset_id": asset_id,
            "file_hash": fh,
            "drift": bool(d) and d.base_hash != fh,
            "draft": (
                {
                    "content": d.content,
                    "base_hash": d.base_hash,
                    "updated_by": d.updated_by,
                    "updated_at": d.updated_at.isoformat() if hasattr(d.updated_at, "isoformat") else d.updated_at,
                }
                if d
                else None
            ),
        }
        if kind == KIND_MD:
            out["file_text"] = text
        else:
            fam = _load_forms_doc(text)["forms"][asset_id]
            out["family"] = {k: fam.get(k) for k in ("desc", "templates", "examples", "stats")}
        return out

    # ── 草稿 ──

    async def save_draft(self, kind: str, asset_id: str, content: dict, username: str) -> dict[str, Any]:
        _known_asset(kind, asset_id)
        if kind == KIND_MD:
            md = content.get("md") if isinstance(content, dict) else None
            if not isinstance(md, str) or not md.strip():
                raise ValueError("md 草稿不能为空")
            clean = {"md": md}
        else:
            _validate_forms_content(asset_id, content)
            clean = {"desc": content["desc"], "templates": content["templates"]}
        base_hash = await run_in_threadpool(lambda: _sha(_read_text(_asset_path(kind, asset_id))))
        row = await self.repo.upsert_draft(kind, asset_id, clean, base_hash, username)
        logger.info(f"[eia-paradigm] 草稿落库 {kind}/{asset_id}（by {username}）")
        return {"asset_kind": kind, "asset_id": asset_id, "base_hash": row.base_hash, "updated_by": username}

    async def withdraw_draft(self, kind: str, asset_id: str) -> bool:
        _known_asset(kind, asset_id)
        return await self.repo.delete_draft(kind, asset_id)

    # ── 导出（validate-all-then-write） ──

    async def preview_export(self) -> dict[str, Any]:
        drafts = {(d.asset_kind, d.asset_id): d for d in await self.repo.list_drafts()}
        return await run_in_threadpool(self._preview_sync, drafts)

    def _preview_sync(self, drafts: dict) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        forms_drafts = {aid: d.content for (k, aid), d in drafts.items() if k == KIND_FORMS}
        for aid in PARADIGM_IDS:
            d = drafts.get((KIND_MD, aid))
            if not d:
                continue
            old = _read_text(self._md_file(aid))
            new = d.content["md"]
            errors = _validate_md(new)
            hits = eia_paradigm_scan.scan_text(new)
            if hits:
                errors.append(f"专名扫描命中（须去实体化）: {hits}")
            items.append(
                {
                    "kind": KIND_MD,
                    "asset_id": aid,
                    "drift": d.base_hash != _sha(old),
                    "ok": not errors,
                    "errors": errors,
                    "diff": _unified_diff(f"{aid}.md", old, new),
                }
            )
        if forms_drafts:
            old = _read_text(_PARADIGM_DIR / "forms_catalog.json")
            try:
                new, changed = _splice_forms(old, forms_drafts)
                diff = _unified_diff("forms_catalog.json", old, new) if changed else ""
                errors: list[str] = []
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                new, changed, diff, errors = None, False, "", [f"forms_catalog 拼装失败: {e}"]
            d0 = next(d for (k, aid), d in drafts.items() if k == KIND_FORMS)
            items.append(
                {
                    "kind": KIND_FORMS,
                    "asset_id": "、".join(sorted(forms_drafts)),
                    "drift": any(d.base_hash != _sha(old) for (_, _), d in drafts.items() if k_check(d)),
                    "ok": not errors,
                    "errors": errors,
                    "diff": diff,
                }
            )
        if not items:
            raise ValueError("无待导出的范式草稿")
        return {"items": items, "all_ok": all(i["ok"] for i in items)}

    async def export_paradigms(self, username: str) -> dict[str, Any]:
        preview = await self.preview_export()
        if not preview["all_ok"]:
            failed = [f"{i['kind']}/{i['asset_id']}: {'；'.join(i['errors'])}" for i in preview["items"] if not i["ok"]]
            raise ValueError("写前校验未通过（全批不写）—" + " | ".join(failed))
        return await run_in_threadpool(self._export_sync, preview, username)

    def _export_sync(self, preview: dict, username: str) -> dict[str, Any]:
        drafts = {(d.asset_kind, d.asset_id): d for d in _list_drafts_sync_safe(self)}
        written: list[tuple[Any, str]] = []
        results: dict[str, dict[str, Any]] = {}
        try:
            for item in preview["items"]:
                path = _asset_path(item["kind"], item["asset_id"].split("、")[0]) if item["kind"] == KIND_FORMS else self._md_file(item["asset_id"])
                original = _read_text(path)
                if item["kind"] == KIND_MD:
                    new = next(d.content["md"] for (k, a), d in drafts.items() if k == KIND_MD and a == item["asset_id"])
                else:
                    forms_drafts = {a: d.content for (k, a), d in drafts.items() if k == KIND_FORMS}
                    new, changed = _splice_forms(original, forms_drafts)
                    if not changed:
                        results[f"{KIND_FORMS}/{item['asset_id']}"] = {"materialized": False, "drift": item["drift"]}
                        continue
                _atomic_write(path, new)
                written.append((path, original))
                results[f"{item['kind']}/{item['asset_id']}"] = {"materialized": True, "drift": item["drift"]}
        except Exception:
            for path, original in reversed(written):
                _atomic_write(path, original)
            raise
        logger.info(f"[eia-paradigm] 导出物化 {len(written)} 文件 → references/paradigms/（by {username}）")
        return {
            "results": results,
            "paths": sorted({str(p.relative_to(_SKILL_ROOT)) for p, _ in written}) or ["(无变更)"],
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


def k_check(d):
    return True


def _list_drafts_sync_safe(self):
    """_export_sync 在线程池内需要草稿行——由调用方传入，这里占位防误用。

    实现为：export_paradigms 先取行再进线程池。见 export_paradigms 的改写。
    """
    raise RuntimeError("internal")
```

**注意——上面 `_preview_sync`/`_export_sync` 草稿行访问有竞态隐患，落地时按此修正版为准：**

`export_paradigms` 改为在进线程池**前**取行，并把「行 → 所需内容」先解析成纯数据：

```python
    async def export_paradigms(self, username: str) -> dict[str, Any]:
        drafts = {(d.asset_kind, d.asset_id): d for d in await self.repo.list_drafts()}
        md_contents = {aid: d.content["md"] for (k, aid), d in drafts.items() if k == KIND_MD}
        forms_contents = {aid: d.content for (k, aid), d in drafts.items() if k == KIND_FORMS}
        preview = await self.preview_export()
        if not preview["all_ok"]:
            failed = [f"{i['kind']}/{i['asset_id']}: {'；'.join(i['errors'])}" for i in preview["items"] if not i["ok"]]
            raise ValueError("写前校验未通过（全批不写）—" + " | ".join(failed))
        return await run_in_threadpool(self._export_sync, preview, md_contents, forms_contents, username)

    def _export_sync(self, preview: dict, md_contents: dict, forms_contents: dict, username: str) -> dict[str, Any]:
        written: list[tuple[Any, str]] = []
        results: dict[str, dict[str, Any]] = {}
        try:
            for item in preview["items"]:
                if item["kind"] == KIND_MD:
                    path = self._md_file(item["asset_id"])
                    new = md_contents[item["asset_id"]]
                else:
                    path = _PARADIGM_DIR / "forms_catalog.json"
                    original_now = _read_text(path)
                    new, changed = _splice_forms(original_now, forms_contents)
                    if not changed:
                        results[f"{KIND_FORMS}/{item['asset_id']}"] = {"materialized": False, "drift": item["drift"]}
                        continue
                original = _read_text(path)
                _atomic_write(path, new)
                written.append((path, original))
                results[f"{item['kind']}/{item['asset_id']}"] = {"materialized": True, "drift": item["drift"]}
        except Exception:
            for path, original in reversed(written):
                _atomic_write(path, original)
            raise
        logger.info(f"[eia-paradigm] 导出物化 {len(written)} 文件 → references/paradigms/（by {username}）")
        return {
            "results": results,
            "paths": sorted({str(p.relative_to(_SKILL_ROOT)) for p, _ in written}),
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
```

同时 `_preview_sync` 里 forms 的 drift 计算改为对每份草稿独立比对（删除 `k_check` 占位与 `_list_drafts_sync_safe`，preview 在进线程池前把 `[(kind, aid, content, base_hash)]` 纯数据传入）：

```python
    async def preview_export(self) -> dict[str, Any]:
        rows = await self.repo.list_drafts()
        plain = [(d.asset_kind, d.asset_id, d.content, d.base_hash) for d in rows]
        return await run_in_threadpool(self._preview_sync, plain)

    def _preview_sync(self, rows: list[tuple]) -> dict[str, Any]:
        drafts = {(k, a): (c, h) for k, a, c, h in rows}
        items: list[dict[str, Any]] = []
        forms_drafts = {aid: c for (k, aid), (c, _h) in drafts.items() if k == KIND_FORMS}
        for aid in PARADIGM_IDS:
            if (KIND_MD, aid) not in drafts:
                continue
            content, base_hash = drafts[(KIND_MD, aid)]
            old = _read_text(self._md_file(aid))
            new = content["md"]
            errors = _validate_md(new)
            hits = eia_paradigm_scan.scan_text(new)
            if hits:
                errors.append(f"专名扫描命中（须去实体化）: {hits}")
            items.append(
                {
                    "kind": KIND_MD,
                    "asset_id": aid,
                    "drift": base_hash != _sha(old),
                    "ok": not errors,
                    "errors": errors,
                    "diff": _unified_diff(f"{aid}.md", old, new),
                }
            )
        if forms_drafts:
            old = _read_text(_PARADIGM_DIR / "forms_catalog.json")
            forms_hash = _sha(old)
            drift = any(h != forms_hash for (k, _a), (_c, h) in drafts.items() if k == KIND_FORMS)
            try:
                new, changed = _splice_forms(old, forms_drafts)
                diff = _unified_diff("forms_catalog.json", old, new) if changed else ""
                errors = []
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                new, changed, diff, errors = None, False, "", [f"forms_catalog 拼装失败: {e}"]
            items.append(
                {
                    "kind": KIND_FORMS,
                    "asset_id": "、".join(sorted(forms_drafts)),
                    "drift": drift,
                    "ok": not errors,
                    "errors": errors,
                    "diff": diff,
                }
            )
        if not items:
            raise ValueError("无待导出的范式草稿")
        return {"items": items, "all_ok": all(i["ok"] for i in items)}
```

（`_overview_sync`/`_get_sync` 同样只收纯数据——`load_overview`/`get_asset` 先 `await self.repo.list_drafts()` 再把行映射为 `(kind, aid, content, base_hash, updated_by, updated_at)` 元组传入线程池；实现时把上面初版的 drafts dict 传参替换为该元组列表即可，字段读取改为解包。）

- [ ] **Step 5: 跑测试确认通过**

Run: `docker exec <api容器> pytest /app/test/unit/test_eia_paradigm_service.py -v`
Expected: 9 passed

- [ ] **Step 6: ruff 检查**

Run: `docker exec <api容器> ruff format backend/package/yuxi/services/eia_paradigm_service.py backend/package/yuxi/services/eia_paradigm_scan.py backend/package/yuxi/repositories/eia_paradigm_repository.py && docker exec <api容器> ruff check backend/package/yuxi/services/ backend/package/yuxi/repositories/eia_paradigm_repository.py`
Expected: 无新增告警（项目 ruff 基线 30 错，不得新增）

- [ ] **Step 7: Commit**

```bash
git add backend/package/yuxi/repositories/eia_paradigm_repository.py backend/package/yuxi/services/eia_paradigm_service.py backend/test/unit/test_eia_paradigm_service.py
git commit -m "feat(domain-factory): 范式层草稿服务（validate-all-then-write 导出 + 字节纪律 + 漂移检测）"
```

---

### Task 4: 路由 6 端点

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（formulas 区块之后插入新区块；顶部 import 区加服务 getter）

- [ ] **Step 1: 顶部 import**

在 `from yuxi.services.eia_formula_service import get_eia_formula_service` 之后加：

```python
from yuxi.services.eia_paradigm_service import get_eia_paradigm_service
```

并在 `eia_paradigm_service.py` 末尾补 getter（与 formulas 同款单例）：

```python
_service: EiaParadigmService | None = None


def get_eia_paradigm_service() -> EiaParadigmService:
    global _service
    if _service is None:
        _service = EiaParadigmService()
    return _service
```

- [ ] **Step 2: 追加路由区块**

在 `export_eia_formulas` 端点函数之后、`# ==== EIA Entities` 注释之前插入：

```python
# =============================================================================
# EIA Paradigms (写作范式层：DB 草稿唯一真相 + admin 导出物化回写 references/paradigms/*)
# =============================================================================


@domain_factory.get("/eia/paradigms")
async def list_eia_paradigms(current_user: User = Depends(get_required_user)) -> dict[str, Any]:
    """范式层概览：4 md + 3 family 草稿态/漂移 + 角色挂载计数 + _roles 全映射（只读）"""
    try:
        return {"success": True, **await get_eia_paradigm_service().load_overview()}
    except Exception as e:
        logger.error(f"Failed to list eia paradigms: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取范式层概览失败: {str(e)}")


@domain_factory.get("/eia/paradigms/{kind}/{asset_id}")
async def get_eia_paradigm_asset(
    kind: str, asset_id: str, current_user: User = Depends(get_required_user)
) -> dict[str, Any]:
    """单资产：md 全文（草稿在则附草稿）/ family 四键（草稿值在 draft.content）"""
    try:
        return {"success": True, **await get_eia_paradigm_service().get_asset(kind, asset_id)}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get eia paradigm {kind}/{asset_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取范式资产失败: {str(e)}")


@domain_factory.put("/eia/paradigms/{kind}/{asset_id}/draft")
async def save_eia_paradigm_draft(
    kind: str,
    asset_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """保存草稿（登录用户）：md 整文件 / 仅 desc+templates 两键，其余键拒收；upsert"""
    try:
        return {
            "success": True,
            **await get_eia_paradigm_service().save_draft(kind, asset_id, payload, current_user.username),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to save eia paradigm draft {kind}/{asset_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存草稿失败: {str(e)}")


@domain_factory.delete("/eia/paradigms/{kind}/{asset_id}/draft")
async def withdraw_eia_paradigm_draft(
    kind: str, asset_id: str, current_user: User = Depends(get_required_user)
) -> dict[str, Any]:
    """撤回草稿（删行，文件锚点不受影响）"""
    try:
        ok = await get_eia_paradigm_service().withdraw_draft(kind, asset_id)
        return {"success": True, "withdrawn": ok}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to withdraw eia paradigm draft {kind}/{asset_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤回草稿失败: {str(e)}")


@domain_factory.post("/eia/paradigms/export/preview")
async def preview_eia_paradigm_export(current_user: User = Depends(get_required_user)) -> dict[str, Any]:
    """写前校验 + difflib diff（不写盘）"""
    try:
        return {"success": True, **await get_eia_paradigm_service().preview_export()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to preview eia paradigm export: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出预览失败: {str(e)}")


@domain_factory.post("/eia/paradigms/export")
async def export_eia_paradigms(current_user: User = Depends(get_admin_user)) -> dict[str, Any]:
    """DB 草稿 → references/paradigms/* 物化（validate-all-then-write；字节纪律；admin）"""
    try:
        result = await get_eia_paradigm_service().export_paradigms(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia paradigms: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出范式失败: {str(e)}")
```

- [ ] **Step 3: 容器内验证应用可导入、路由注册**

Run: `docker exec <api容器> python -c "from server.routers.domain_factory_router import domain_factory; print(sum(1 for r in domain_factory.routes if 'paradigms' in r.path))"`
Expected: `6`

- [ ] **Step 4: Commit**

```bash
git add backend/server/routers/domain_factory_router.py backend/package/yuxi/services/eia_paradigm_service.py
git commit -m "feat(domain-factory): 范式层 6 端点（概览/详情/存撤草稿/预览/admin 导出）"
```

---

### Task 5: 集成流测试（认证门槛 + 错误路径，不触真实文件）

**Files:**
- Test: `backend/test/integration/api/test_eia_paradigm_flow.py`

全链 DB/文件语义由 Task 3 单测覆盖（FakeRepo + tmp_path）；本任务按 house 模式（`test_eia_standard_flow.py`）只测认证门槛与错误路径——**不产生真实 DB 草稿行、不写真实技能文件**。

- [ ] **Step 1: 写测试**

```python
"""eia_paradigm API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。

同 standard flow：全链用例需 TEST_USERNAME/TEST_PASSWORD，缺失即 skip；401 用例无凭据依赖恒跑。
不触真实技能文件：写路径全部用「未知资产 404 / 键形状 400」等在落盘前即失败的用例。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_paradigms_requires_auth(test_client):
    """未认证访问范式端点一律 401（读写与物化同门槛）。"""
    for method, url in (
        ("GET", "/api/domain-factory/eia/paradigms"),
        ("GET", "/api/domain-factory/eia/paradigms/paradigm_md/analysis"),
        ("PUT", "/api/domain-factory/eia/paradigms/paradigm_md/analysis/draft"),
        ("DELETE", "/api/domain-factory/eia/paradigms/forms_catalog/table_lead/draft"),
        ("POST", "/api/domain-factory/eia/paradigms/export/preview"),
        ("POST", "/api/domain-factory/eia/paradigms/export"),
    ):
        resp = await test_client.request(method, url, json={} if method in ("PUT", "POST") else None)
        assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


async def test_paradigms_export_requires_admin(test_client, standard_user):
    """非 admin 导出物化 403（凭据缺失自动 skip）。"""
    resp = await test_client.post("/api/domain-factory/eia/paradigms/export", headers=standard_user["headers"])
    assert resp.status_code == 403, resp.text


async def test_paradigm_draft_unknown_asset_404(test_client, admin_headers):
    """未知 kind / 未知 asset_id → 404（KeyError 映射；不落任何行）。"""
    for kind, aid in (("no_such_kind", "analysis"), ("paradigm_md", "no_such"), ("forms_catalog", "no_such")):
        resp = await test_client.put(
            f"/api/domain-factory/eia/paradigms/{kind}/{aid}/draft",
            headers=admin_headers,
            json={"md": "x"},
        )
        assert resp.status_code == 404, f"{kind}/{aid} -> {resp.status_code}: {resp.text}"


async def test_paradigm_draft_extra_keys_rejected_400(test_client, admin_headers):
    """forms 草稿夹带只读键（stats）→ 400（服务层两键纪律；不落数据库行）。"""
    resp = await test_client.put(
        "/api/domain-factory/eia/paradigms/forms_catalog/table_lead/draft",
        headers=admin_headers,
        json={"desc": "d", "templates": ["t。"], "stats": {"colon_lead": 0.0}},
    )
    assert resp.status_code == 400, resp.text
    assert "stats" in resp.text


async def test_paradigm_export_empty_400(test_client, admin_headers):
    """无任何草稿时导出预览/物化 → 400（无待导出）。"""
    for url in ("/api/domain-factory/eia/paradigms/export/preview", "/api/domain-factory/eia/paradigms/export"):
        resp = await test_client.post(url, headers=admin_headers)
        assert resp.status_code in (400, 200), f"{url} -> {resp.status_code}: {resp.text}"
        # 环境已有他人草稿时允许 200；本用例锚定的是「不 5xx、不写盘」
```

- [ ] **Step 2: 跑测试**

Run: `docker exec <api容器> pytest /app/test/integration/api/test_eia_paradigm_flow.py -v`
Expected: passed 或（无 E2E 凭据时）相应 skip——**不得出现 failed**（对照记忆：12 skipped ≠ 通过，须区分 skip 原因）

- [ ] **Step 3: Commit**

```bash
git add backend/test/integration/api/test_eia_paradigm_flow.py
git commit -m "test(domain-factory): 范式层 API 认证门槛与错误路径集成测试"
```

---

### Task 6: 前端 API 封装 + 路由 + 菜单分组 + View 包装

**Files:**
- Create: `web/src/apis/eia_paradigm_api.js`
- Modify: `web/src/router/index.js`（eia-data children 末尾 `entities` 之后加两条）
- Modify: `web/src/components/eia-data/EiaDataLayout.vue`（icon import + 新分组）
- Create: `web/src/views/EiaParadigmsView.vue`、`web/src/views/EiaFormsView.vue`

- [ ] **Step 1: API 封装**

```javascript
/**
 * EIA Paradigm API
 * 写作范式层（DB 草稿唯一真相 + admin 导出物化回写 references/paradigms/*）
 */

import { apiDelete, apiGet, apiPost, apiRequest } from './base'

const enc = encodeURIComponent

export const eiaParadigmApi = {
  /** 概览：4 md + 3 family 草稿态/漂移 + 角色挂载计数 + _roles 全映射（只读） */
  loadOverview: () => apiGet('/api/domain-factory/eia/paradigms'),

  /** 单资产：md 全文（file_text + draft）/ family 四键（desc/templates/examples/stats + draft） */
  getAsset: (kind, assetId) => apiGet(`/api/domain-factory/eia/paradigms/${enc(kind)}/${enc(assetId)}`),

  /** 保存草稿：md 传 {md: 整文}；forms 传 {desc, templates}（多余键后端 400 拒收） */
  saveDraft: (kind, assetId, payload) =>
    apiRequest(`/api/domain-factory/eia/paradigms/${enc(kind)}/${enc(assetId)}/draft`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  /** 撤回草稿（删行，文件锚点不受影响） */
  withdrawDraft: (kind, assetId) =>
    apiDelete(`/api/domain-factory/eia/paradigms/${enc(kind)}/${enc(assetId)}/draft`),

  /** 写前校验 + diff（不写盘）→ { items, all_ok } */
  previewExport: () => apiPost('/api/domain-factory/eia/paradigms/export/preview'),

  /** admin 物化 → { results, paths, exported_at } */
  exportParadigms: () => apiPost('/api/domain-factory/eia/paradigms/export')
}
```

- [ ] **Step 2: 路由两条 child**

在 `web/src/router/index.js` 的 eia-data children 数组中 `entities` 条目之后插入：

```javascript
            {
              path: 'paradigms',
              name: 'EiaDataParadigms',
              component: () => import('../views/EiaParadigmsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'forms',
              name: 'EiaDataForms',
              component: () => import('../views/EiaFormsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            }
```

- [ ] **Step 3: 菜单分组**

`EiaDataLayout.vue`：icon import 列表加入 `MessageSquareQuote,` 与 `NotebookPen,`（按字母序插入既有 `@lucide/vue` import 块）；`groups` 数组末尾（「参数与实体」组之后）追加：

```javascript
  {
    label: '写作范式',
    items: [
      { to: '/domain-factory/eia-data/paradigms', label: '写作范式（md）', icon: NotebookPen },
      { to: '/domain-factory/eia-data/forms', label: '句式范式（catalog）', icon: MessageSquareQuote }
    ]
  }
```

- [ ] **Step 4: View 包装（两个文件）**

`web/src/views/EiaParadigmsView.vue`：

```vue
<template>
  <ParadigmsPanel />
</template>

<script setup>
import ParadigmsPanel from '@/components/eia-data/ParadigmsPanel.vue'
</script>
```

`web/src/views/EiaFormsView.vue`：

```vue
<template>
  <FormsPanel />
</template>

<script setup>
import FormsPanel from '@/components/eia-data/FormsPanel.vue'
</script>
```

（Panel 组件 Task 7/8 才创建——本任务先建 View 会临时红，故 Step 4 放到 Task 7/8 各自文件就绪后再执行 lint。任务内顺序：Step 1-3 完成即可 lint apis/router/layout；View 文件与 Panel 同任务提交。）

- [ ] **Step 5: 前端 lint**

Run: `docker exec pisuan-localized-web-1 sh -c "cd /app && npx prettier --write src/apis/eia_paradigm_api.js src/router/index.js src/components/eia-data/EiaDataLayout.vue && npx eslint src/apis/eia_paradigm_api.js src/router/index.js src/components/eia-data/EiaDataLayout.vue && echo LINT_OK"`
Expected: `LINT_OK`（View 文件待 Task 7 一并 lint）

- [ ] **Step 6: Commit（与 Task 7 合并提交亦可——若合并，本步跳过）**

```bash
git add web/src/apis/eia_paradigm_api.js web/src/router/index.js web/src/components/eia-data/EiaDataLayout.vue
git commit -m "feat(domain-factory): 范式层前端骨架（api/路由/菜单分组）"
```

---

### Task 7: ParadigmsPanel.vue（原型 s12 像素复刻）

**Files:**
- Create: `web/src/components/eia-data/ParadigmsPanel.vue`
- Create: `web/src/components/eia-data/ParadigmExportModal.vue`
- Create: `web/src/views/EiaParadigmsView.vue`（Task 6 Step 4 已列，此处落地）

**原型基准:** `docs/vibe/prototypes/2026-10-12-eia-p2-ui.html` 搜 `id="s12"` 区块 + `id="exportModal"`。样式词汇：`page-head/ph-icon/ph-sub/ph-actions`、`card/card-hd/hd-sub/hd-right`、`split/fam-list/fam-search/fam-item/fam-name/fam-cnt/mini-dot`、`seg`、`tbl/tbl-foot`、`field-src file/db`、`pill pill-ok/warn/gray/orange`、`note-bar` 全部已在 `factory-ui.less`（`.ewp` 命名空间）；本页新增形状（textarea/预览块/diff）写本组件 scoped。

- [ ] **Step 1: ParadigmExportModal.vue（两页共用导出弹窗）**

```vue
<template>
  <a-modal
    :open="open"
    title="导出物化 · 写前校验"
    :confirm-loading="exporting"
    :ok-text="'校验并写入（admin）'"
    :ok-button-props="{ disabled: !data?.all_ok || exporting }"
    @ok="onExport"
    @cancel="$emit('update:open', false)"
  >
    <a-spin v-if="loading" style="display: block; margin: 32px auto" />
    <template v-else-if="data">
      <div v-for="it in data.items" :key="it.kind + it.asset_id" style="margin-bottom: 14px">
        <div class="dif-hd">
          {{ label(it) }}
          <span v-if="it.drift" class="pill pill-warn">文件已漂移 · 以草稿为准恢复</span>
          <span v-else-if="it.ok" class="pill pill-ok">校验通过</span>
          <span v-else class="pill pill-err">校验未过</span>
        </div>
        <ul v-if="it.errors?.length" class="err-list">
          <li v-for="e in it.errors" :key="e">{{ e }}</li>
        </ul>
        <pre v-else class="dif-box">{{ it.diff || '（无字节变化）' }}</pre>
      </div>
      <div class="frm-help">
        写前校验：范式 md 锚点小节在位、专名扫描 0 命中、forms JSON 可解析；任一不过 →
        全批不写。round-trip：未改动的文件与键保持字节一致（不重排键序）。
      </div>
      <div class="residue-warn">
        <Alert :size="14" />
        <span>反模式表如有改动，需同步人工修订交付门残留词表（RESIDUE_RE）——先改门表，再同步范式，导出不联动。</span>
      </div>
    </template>
  </a-modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Alert } from '@lucide/vue'
import { eiaParadigmApi } from '@/apis/eia_paradigm_api'
import { useUserStore } from '@/stores/user'

const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['update:open', 'exported'])

const userStore = useUserStore()
const loading = ref(false)
const exporting = ref(false)
const data = ref(null)

const label = (it) =>
  it.kind === 'paradigm_md' ? `references/paradigms/${it.asset_id}.md · 草稿 → 文件` : `forms_catalog.json · ${it.asset_id} desc/templates 两键`

const load = async () => {
  loading.value = true
  try {
    data.value = await eiaParadigmApi.previewExport()
  } catch (e) {
    message.error(e.message)
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => v && load()
)

const onExport = async () => {
  exporting.value = true
  try {
    const out = await eiaParadigmApi.exportParadigms()
    message.success(`已写回 ${out.paths.join('、')}（落运行栈技能目录，需人工回流 pisuan-custom 走 git 评审）`, 6)
    emit('update:open', false)
    emit('exported')
  } catch (e) {
    message.error(e.message)
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.dif-hd {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}

.dif-box {
  max-height: 200px;
  overflow: auto;
  margin: 0 0 4px;
  padding: 10px 12px;
  background: var(--color-bg-layout);
  border-radius: 6px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.err-list {
  margin: 0 0 4px;
  padding-left: 18px;
  font-size: 12px;
  color: var(--color-error);
}

.frm-help {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.7;
}

.residue-warn {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 10px;
  padding: 9px 12px;
  border-radius: 6px;
  background: var(--color-warning-bg);
  font-size: 12px;
  line-height: 1.6;
}
</style>
```

（若 `--color-warning-bg`/`--color-error` 变量名与 `web/src/assets/css/base.css` 实际 token 不符，以 base.css 实有 token 替换——写此文件前先 `grep -n "warning-bg\|--color-error" web/src/assets/css/base.css` 核对。）

- [ ] **Step 2: ParadigmsPanel.vue**

```vue
<template>
  <div class="ewp paradigms-panel">
    <!-- 页头（原型 s12：NotebookPen + 待导出 pill + 导出物化） -->
    <div class="page-head">
      <div class="ph-icon"><NotebookPen :size="18" /></div>
      <div>
        <h2>写作范式</h2>
        <div class="ph-sub">
          paradigms/*.md · 四角色行文范式（适用 / 结构骨架 / 范文 / 节尾收束段 / 句式模式 / 反模式）· 写手按节角色整文件注入
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="pendingCount" class="pill pill-orange">
          <span class="dot dot-warn"></span>{{ pendingCount }} 文件待导出
        </span>
        <button
          v-if="userStore.isAdmin"
          class="btn btn-pri btn-sm"
          :disabled="!pendingCount"
          @click="exportOpen = true"
        >
          导出物化
        </button>
      </div>
    </div>

    <a-spin v-if="loading" style="display: block; margin: 48px auto" />
    <template v-else>
      <div class="split">
        <!-- 左：角色列表 -->
        <div class="card fam-list">
          <div class="fam-search"><input v-model="query" class="inp" placeholder="搜索角色…" /></div>
          <div
            v-for="p in filteredParadigms"
            :key="p.asset_id"
            class="fam-item"
            :class="{ on: p.asset_id === activeId }"
            @click="selectRole(p.asset_id)"
          >
            <span v-if="p.has_draft && !p.drift" class="mini-dot"></span>
            <span class="fam-name">{{ roleLabel(p.asset_id) }}</span>
            <span class="fam-cnt" style="margin-left: auto">{{ p.has_draft ? '改·未导出' : '一致' }}</span>
            <span class="fam-cnt">{{ roleCounts[p.asset_id] ?? 0 }} 节</span>
          </div>
          <div class="tbl-foot">挂载节数取自 _roles.json（77 节全映射，查不到=拒派报错）</div>
        </div>

        <!-- 右：编辑器 + 角色对照 -->
        <div>
          <div class="card" style="margin-bottom: 12px">
            <div class="card-hd">
              <h3>{{ activeId }}.md</h3>
              <span class="hd-sub">挂载 {{ roleCounts[activeId] ?? 0 }} 节</span>
              <div class="hd-right">
                <div class="seg">
                  <button :class="{ on: mode === 'edit' }" @click="mode = 'edit'">编辑</button>
                  <button :class="{ on: mode === 'view' }" @click="mode = 'view'">预览</button>
                </div>
                <button v-if="draftContent !== null" class="btn btn-txt btn-sm" @click="onWithdraw">丢弃草稿</button>
                <button class="btn btn-pri btn-sm" :disabled="!dirty" @click="onSave">
                  {{ saving ? '保存中…' : '保存草稿' }}
                </button>
              </div>
            </div>
            <textarea
              v-show="mode === 'edit'"
              v-model="mdText"
              class="edt-area"
              spellcheck="false"
            ></textarea>
            <div v-show="mode === 'view'" class="md-preview">{{ mdText }}</div>
            <div class="edt-meta">
              <span v-if="draftContent !== null" class="field-src db">
                草稿 · {{ active?.draft?.updated_by }} · {{ shortTime(active?.draft?.updated_at) }}
              </span>
              <span v-else class="field-src file">无草稿 · 编辑后保存落库</span>
              <span style="margin-left: auto" class="field-src file">base_hash {{ shortHash(active?.file_hash) }}</span>
            </div>
          </div>

          <div class="card">
            <div class="card-hd">
              <h3>节角色对照</h3>
              <span class="hd-sub">_roles.json · {{ rolesTotal }} 节 · 只读</span>
              <div class="hd-right">
                <div class="seg">
                  <button
                    v-for="f in roleFilters"
                    :key="f"
                    :class="{ on: roleFilter === f }"
                    @click="roleFilter = f"
                  >
                    {{ f }}
                  </button>
                </div>
                <input v-model="roleQuery" class="inp" style="width: 150px" placeholder="搜索节 id…" />
              </div>
            </div>
            <table class="tbl">
              <thead>
                <tr>
                  <th style="width: 130px">节 id</th>
                  <th style="width: 110px">角色</th>
                  <th style="width: 110px">挂载范式</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="[sid, role] in filteredRoles" :key="sid">
                  <td class="mono">{{ sid }}</td>
                  <td><span class="pill pill-gray">{{ role }}</span></td>
                  <td>{{ roleLabel(role) }}</td>
                </tr>
              </tbody>
            </table>
            <div class="tbl-foot">
              共 {{ rolesTotal }} 节 · <span>角色错配 = 整节范式错注入；调整映射改 _roles.json 走 git 评审，不设 UI 编辑</span>
            </div>
          </div>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          范式 md 的「反模式」表与交付门残留词表（RESIDUE_RE）人工同源：此处修改反模式表述不会自动更新门禁词表，
          导出确认时会提示同步修订。
        </span>
      </div>
    </template>

    <ParadigmExportModal v-model:open="exportOpen" @exported="fetchAll" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Info, NotebookPen } from '@lucide/vue'
import { eiaParadigmApi } from '@/apis/eia_paradigm_api'
import { useUserStore } from '@/stores/user'
import ParadigmExportModal from './ParadigmExportModal.vue'

const KIND = 'paradigm_md'
const ROLE_LABELS = {
  opener: 'opener · 章首定位',
  baseline: 'baseline · 现状盘点',
  analysis: 'analysis · 影响预测',
  measures: 'measures · 措施要求'
}

const userStore = useUserStore()
const loading = ref(true)
const overview = ref(null)
const activeId = ref('analysis')
const query = ref('')
const mode = ref('edit')
const mdText = ref('')
const draftContent = ref(null)
const saving = ref(false)
const exportOpen = ref(false)
const roleFilter = ref('全部')
const roleQuery = ref('')

const roleFilters = ['全部', 'opener', 'baseline', 'analysis', 'measures']
const roleCounts = computed(() => overview.value?.role_counts ?? {})
const rolesMap = computed(() => overview.value?.roles_map ?? {})
const rolesTotal = computed(() => Object.keys(rolesMap.value).length)
const pendingCount = computed(
  () => (overview.value?.paradigms ?? []).filter((p) => p.has_draft).length + (overview.value?.families ?? []).filter((f) => f.has_draft).length
)
const filteredParadigms = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (overview.value?.paradigms ?? []).filter((p) => !q || p.asset_id.includes(q))
})
const filteredRoles = computed(() =>
  Object.entries(rolesMap.value)
    .filter(([sid, role]) => (roleFilter.value === '全部' || role === roleFilter.value) && sid.includes(roleQuery.value.trim()))
    .slice(0, 20)
)

const roleLabel = (r) => ROLE_LABELS[r] ?? r
const shortHash = (h) => (h ? `${h.slice(0, 4)}…${h.slice(-2)}` : '—')
const shortTime = (t) => (t ? String(t).slice(5, 16).replace('T', ' ') : '')

const active = computed(() => (overview.value?.paradigms ?? []).find((p) => p.asset_id === activeId.value))
const dirty = computed(() => mdText.value !== (draftContent.value ?? fileText.value))
const fileText = ref('')

const selectRole = async (id) => {
  if (id === activeId.value) return
  activeId.value = id
}

const loadAsset = async () => {
  const out = await eiaParadigmApi.getAsset(KIND, activeId.value)
  fileText.value = out.file_text
  draftContent.value = out.draft ? out.draft.content.md : null
  mdText.value = out.draft ? out.draft.content.md : out.file_text
}

const fetchAll = async () => {
  loading.value = true
  try {
    overview.value = await eiaParadigmApi.loadOverview()
    await loadAsset()
  } catch (e) {
    message.error(`获取范式层失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

watch(activeId, () => loadAsset().catch((e) => message.error(e.message)))

const onSave = async () => {
  saving.value = true
  try {
    await eiaParadigmApi.saveDraft(KIND, activeId.value, { md: mdText.value })
    message.success('草稿已落库，待 admin 导出物化')
    await fetchAll()
  } catch (e) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

const onWithdraw = async () => {
  try {
    await eiaParadigmApi.withdrawDraft(KIND, activeId.value)
    message.success('已撤回草稿（文件锚点不受影响）')
    await fetchAll()
  } catch (e) {
    message.error(e.message)
  }
}

onMounted(fetchAll)
</script>

<style lang="less" scoped>
/* 本页形状（原型 s12）：md 编辑区 / 预览 / 元信息行 —— 公共配方在 factory-ui.less */
.edt-area {
  display: block;
  width: 100%;
  border: 0;
  border-top: 1px solid var(--color-border-secondary);
  background: transparent;
  color: var(--color-text);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.8;
  padding: 14px 16px;
  min-height: 320px;
  resize: vertical;
  outline: none;
}

.md-preview {
  border-top: 1px solid var(--color-border-secondary);
  padding: 16px 20px;
  min-height: 320px;
  font-size: 13px;
  line-height: 1.9;
  white-space: pre-wrap;
  color: var(--color-text);
}

.edt-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 16px;
  border-top: 1px solid var(--color-border-secondary);
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>

<style lang="less" src="./factory-ui.less"></style>
```

- [ ] **Step 3: 浏览器双主题对照原型**

启动栈就绪（`docker ps`）后，用隔离浏览器上下文打开 `http://localhost:5173/domain-factory/eia-data/paradigms`（admin 登录），亮/暗两态截图与原型 s12 亮/暗对照。检查点：左列 4 角色 + 计数、编辑器 mono 字体与 min 高度、seg 切换、角色对照表、note-bar 文案。

- [ ] **Step 4: lint + Commit**

Run: `docker exec pisuan-localized-web-1 sh -c "cd /app && npx prettier --write src/components/eia-data/ParadigmsPanel.vue src/components/eia-data/ParadigmExportModal.vue src/views/EiaParadigmsView.vue && npx eslint src/components/eia-data/ParadigmsPanel.vue src/components/eia-data/ParadigmExportModal.vue src/views/EiaParadigmsView.vue && echo LINT_OK"`
Expected: `LINT_OK`

```bash
git add web/src/components/eia-data/ParadigmsPanel.vue web/src/components/eia-data/ParadigmExportModal.vue web/src/views/EiaParadigmsView.vue
git commit -m "feat(domain-factory): 写作范式页（md 整文件草稿编辑 + 节角色对照只读）"
```

---

### Task 8: FormsPanel.vue（原型 s13 像素复刻）

**Files:**
- Create: `web/src/components/eia-data/FormsPanel.vue`
- Create: `web/src/views/EiaFormsView.vue`（Task 6 Step 4 已列，此处落地）

**原型基准:** `id="s13"` 区块。三族卡片 grid 布局（原型 `.grid3` → 本组件 scoped `.family-grid`）；stats 只读条；DB 草稿行 pill；导出安全阀 meta 行。**原型的「改/新增」未画弹窗**——按 fieldModal frm 词汇补最小编辑弹窗（desc 一块、templates 每行可改/删、可新增），保存即 PUT 整族 `{desc, templates}` 草稿。

- [ ] **Step 1: FormsPanel.vue**

```vue
<template>
  <div class="ewp forms-panel">
    <!-- 页头（原型 s13：MessageSquareQuote + 待导出 pill + 导出物化） -->
    <div class="page-head">
      <div class="ph-icon"><MessageSquareQuote :size="18" /></div>
      <div>
        <h2>句式范式</h2>
        <div class="ph-sub">
          forms_catalog.json · 三族句式（口径消歧 / 数值引用 / 表题引导）· 写手按场景取 templates 渲染
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="pendingCount" class="pill pill-orange">
          <span class="dot dot-warn"></span>{{ pendingCount }} 行待导出
        </span>
        <button
          v-if="userStore.isAdmin"
          class="btn btn-pri btn-sm"
          :disabled="!pendingCount"
          @click="exportOpen = true"
        >
          导出物化
        </button>
      </div>
    </div>

    <a-spin v-if="loading" style="display: block; margin: 48px auto" />
    <template v-else>
      <div class="family-grid">
        <div v-for="fam in families" :key="fam.asset_id" class="card">
          <div class="card-hd">
            <h3 class="mono" style="font-size: 13px">{{ fam.asset_id }}</h3>
            <span class="pill pill-gray" style="margin-left: auto">{{ fam.templates.length }} 模板</span>
            <span v-if="fam.has_draft" class="pill pill-orange" style="margin-left: 6px">
              <span class="dot dot-warn"></span>待导出
            </span>
          </div>
          <div class="fam-desc-row">
            <span>{{ fam.desc }}</span>
            <button class="btn btn-txt btn-sm" @click="openDescEdit(fam)">改简介</button>
          </div>
          <div class="sub-h">templates · 写手消费（可编辑）</div>
          <div v-for="(t, i) in fam.templates" :key="i" class="tpl-row">
            <span class="no">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="tx">{{ t }}</span>
            <button class="btn btn-txt btn-sm" @click="openTplEdit(fam, i)">改</button>
          </div>
          <div class="tpl-row">
            <span class="no">+</span>
            <span class="tx" style="color: var(--color-text-quaternary)">
              <button class="btn btn-txt btn-sm" @click="openTplEdit(fam, -1)">新增模板句式…</button>
            </span>
          </div>
          <div class="sub-h">stats · 语料统计（只读）</div>
          <div class="stat-strip">
            <span v-for="(v, k) in fam.stats" :key="k" class="st" :class="{ hot: v >= 0.5 }">
              {{ k }} {{ (v * 100).toFixed(1) }}%
            </span>
            <span v-if="!Object.keys(fam.stats).length" class="st">31 份语料 · 该族无统计产出</span>
          </div>
          <div class="sub-h" style="border-bottom: 1px solid var(--color-border-secondary); margin-top: 0">
            导出安全阀
          </div>
          <div class="edt-meta">
            <span>仅写 desc / templates</span>
            <span class="field-src file" style="margin-left: auto">stats / examples 字节不动</span>
          </div>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          bank_compile 重算会整文件重写 forms_catalog.json：草稿落库后若检测到 base_hash 漂移（文件被语料脚本重算），
          导出预览会示警「文件已漂移」，确认导出即以草稿为准恢复。
        </span>
      </div>
    </template>

    <!-- 最小编辑弹窗（原型的 fieldModal frm 词汇；desc 或单条 template） -->
    <a-modal
      v-model:open="editModal.open"
      :title="editModal.title"
      :confirm-loading="editModal.saving"
      @ok="submitEdit"
    >
      <div class="frm">
        <div class="frm-row">
          <label>{{ editModal.isDesc ? '族简介（desc）' : '模板句式' }}</label>
          <a-textarea v-model:value="editModal.value" :rows="3" />
        </div>
        <div class="frm-help">保存即写入该族草稿（desc / templates 两键），admin「导出物化」后回写 forms_catalog.json</div>
      </div>
    </a-modal>

    <ParadigmExportModal v-model:open="exportOpen" @exported="fetchAll" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Info, MessageSquareQuote } from '@lucide/vue'
import { eiaParadigmApi } from '@/apis/eia_paradigm_api'
import { useUserStore } from '@/stores/user'
import ParadigmExportModal from './ParadigmExportModal.vue'

const KIND = 'forms_catalog'
const FAMILY_LABELS = { caliber_disambiguation: '口径消歧', numeric_citation: '数值引用', table_lead: '表题引导' }

const userStore = useUserStore()
const loading = ref(true)
const overview = ref(null)
const assets = ref({}) // asset_id -> getAsset 详情（含 family 只读键 + 草稿）
const exportOpen = ref(false)
const editModal = reactive({ open: false, saving: false, title: '', isDesc: false, family: '', index: -1, value: '' })

const families = computed(() => overview.value?.families ?? [])
const pendingCount = computed(() => families.value.filter((f) => f.has_draft).length)

const fetchAll = async () => {
  loading.value = true
  try {
    overview.value = await eiaParadigmApi.loadOverview()
    const out = await Promise.all(families.value.map((f) => eiaParadigmApi.getAsset(KIND, f.asset_id)))
    assets.value = Object.fromEntries(out.map((o) => [o.asset_id, o]))
  } catch (e) {
    message.error(`获取句式范式失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

// 草稿值优先展示（与 DB 草稿=编辑真相一致）；无草稿用文件值
const displayValue = (fam) => {
  const a = assets.value[fam.asset_id]
  if (a?.draft) return a.draft.content
  return { desc: fam.desc, templates: fam.templates }
}

const openDescEdit = (fam) => {
  editModal.title = `族简介 · ${FAMILY_LABELS[fam.asset_id] ?? fam.asset_id}`
  editModal.isDesc = true
  editModal.family = fam.asset_id
  editModal.index = -1
  editModal.value = displayValue(fam).desc
  editModal.open = true
}

const openTplEdit = (fam, index) => {
  editModal.title = index < 0 ? `新增模板 · ${FAMILY_LABELS[fam.asset_id] ?? fam.asset_id}` : `模板 ${String(index + 1).padStart(2, '0')} · ${fam.asset_id}`
  editModal.isDesc = false
  editModal.family = fam.asset_id
  editModal.index = index
  editModal.value = index < 0 ? '' : displayValue(fam).templates[index]
  editModal.open = true
}

const submitEdit = async () => {
  const fam = families.value.find((f) => f.asset_id === editModal.family)
  const cur = displayValue(fam)
  const desc = editModal.isDesc ? editModal.value.trim() : cur.desc
  let templates = [...cur.templates]
  if (editModal.isDesc) {
    if (!desc) {
      message.warning('desc 不能为空')
      return
    }
  } else {
    const v = editModal.value.trim()
    if (!v) {
      message.warning('模板句式不能为空')
      return
    }
    if (editModal.index < 0) templates.push(v)
    else templates[editModal.index] = v
  }
  editModal.saving = true
  try {
    await eiaParadigmApi.saveDraft(KIND, editModal.family, { desc, templates })
    message.success('草稿已落库，待 admin 导出物化')
    editModal.open = false
    await fetchAll()
  } catch (e) {
    message.error(e.message)
  } finally {
    editModal.saving = false
  }
}

onMounted(fetchAll)
</script>

<style lang="less" scoped>
/* 本页形状（原型 s13）：三族 grid / 模板行 / 统计条 —— 公共配方在 factory-ui.less */
.family-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  align-items: start;

  @media (max-width: 1280px) {
    grid-template-columns: 1fr;
  }
}

.fam-desc-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 2px 16px 10px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--color-text-secondary);

  span {
    flex: 1;
  }
}

.sub-h {
  padding: 10px 16px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--color-text-tertiary);
  border-top: 1px solid var(--color-border-secondary);
  margin-top: 6px;
}

.tpl-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 16px;

  & + .tpl-row {
    border-top: 1px dashed var(--color-border-secondary);
  }

  .no {
    width: 22px;
    flex: none;
    font-size: 11px;
    color: var(--color-text-quaternary);
    font-family: 'JetBrains Mono', Consolas, monospace;
    padding-top: 2px;
  }

  .tx {
    flex: 1;
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 13px;
    line-height: 1.6;
  }
}

.stat-strip {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 2px 16px 12px;

  .st {
    font-size: 11px;
    font-family: 'JetBrains Mono', Consolas, monospace;
    color: var(--color-text-secondary);
    background: var(--color-bg-layout);
    border-radius: 4px;
    padding: 2px 8px;

    &.hot {
      background: var(--color-primary-bg);
      color: var(--color-primary);
    }
  }
}

.edt-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 16px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.frm {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;

  .frm-row label {
    font-size: 12px;
    color: var(--color-text-secondary);
  }

  .frm-help {
    font-size: 12px;
    color: var(--color-text-tertiary);
    line-height: 1.6;
  }
}
</style>

<style lang="less" src="./factory-ui.less"></style>
```

（同 Task 7：写文件前先 `grep -n "color-primary-bg\|color-text-quaternary\|color-warning-bg" web/src/assets/css/base.css`，不在册的 token 换成 base.css 实有近义 token。）

- [ ] **Step 2: 浏览器双主题对照原型 s13**

同 Task 7 Step 3，URL `/domain-factory/eia-data/forms`。检查点：三卡 grid、模板行序号 mono、stats hot 高亮、导出安全阀行、编辑弹窗落草稿后卡片出现「待导出」pill。

- [ ] **Step 3: lint + Commit**

Run: `docker exec pisuan-localized-web-1 sh -c "cd /app && npx prettier --write src/components/eia-data/FormsPanel.vue src/views/EiaFormsView.vue && npx eslint src/components/eia-data/FormsPanel.vue src/views/EiaFormsView.vue && echo LINT_OK"`
Expected: `LINT_OK`

```bash
git add web/src/components/eia-data/FormsPanel.vue web/src/views/EiaFormsView.vue
git commit -m "feat(domain-factory): 句式范式页（desc/templates 两键编辑 + stats 只读）"
```

---

### Task 9: 端到端演练 + 收尾

**Files:**
- Modify: `docs/develop-guides/changelog.md`
- Modify: `docs/vibe/2026-10-14-paradigm-layer-edit-design.md`（状态行：草案 → 已实施）

- [ ] **Step 1: 全量回归**

Run: `docker exec <api容器> pytest /app/test/unit/test_eia_paradigm_scan.py /app/test/unit/test_eia_paradigm_service.py /app/test/integration/api/test_eia_paradigm_flow.py -v`
Expected: 单测全 passed；集成 passed/skip（无 failed）

Run: `docker exec <api容器> pytest /app/test/unit/ -k "eia" -q`
Expected: 既有 eia 单测无回归

- [ ] **Step 2: docker 端到端演练（真实验证 A1-A6）**

在运行栈浏览器（隔离上下文，admin 登录）：
1. 范式页改 analysis.md 一个字 → 保存 → 概览 pending=1 → verify: A2 草稿链路
2. 打开导出物化 → diff 含该行 → verify: A3 校验+diff
3. 句式页 table_lead 改一条模板 → 保存
4. 确认导出 → `docker exec <api容器> sh -c "cd /app && git status --short backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/"` → verify: 仅两文件变更（A4 部分证据；容器内若非 git 工作树则直接 `git -C 宿主 diff` 看回流前运行栈差异）
5. **还原**：`git checkout -- <两文件路径>`（宿主 pisuan-custom 工作树）+ `docker exec <api容器> python -c` 删 `eia_paradigm_drafts` 全行（演练数据不留在运行栈）
6. verify: A5 漂移——重复 1 后手工改文件再 preview，弹窗出现「文件已漂移」

- [ ] **Step 3: changelog + 文档状态**

`docs/develop-guides/changelog.md` 顶部既有批次块后追加一条（对齐既有条目风格）：

```markdown
- 写作范式层查询+编辑页（/domain-factory/eia-data/paradigms · forms）：eia_paradigm_drafts 单表草稿（迁移 v17）+ 6 端点 + validate-all-then-write 导出（锚点/两键/专名扫描校验，round-trip 字节纪律，base_hash 漂移检测）+ 前端两页（原型 s12/s13 像素复刻）；_roles.json 只读，RESIDUE_RE 人工同步纪律入导出确认
```

设计文档头部 `状态：草案（待评审）` → `状态：已实施（2026-10-14）`。

Run: `docker exec <api容器> ruff check backend/ --statistics | head -3`
Expected: 基线 30 错不新增

- [ ] **Step 4: Commit**

```bash
git add docs/develop-guides/changelog.md docs/vibe/2026-10-14-paradigm-layer-edit-design.md
git commit -m "docs: 写作范式层编辑页 changelog + 设计文档状态更新"
```

---

## Self-Review 记录

1. **Spec coverage**：§2 编辑边界→Task 3/7/8（两键拒收、_roles 只读仅展示）；§4 表+漂移→Task 1/3；§5 六端点→Task 4；§6 校验+字节纪律+回滚→Task 3（test_export_blocked/rollback/idempotent）；§7 前端→Task 6/7/8；§8 RESIDUE_RE 提示→Task 7 弹窗 residue-warn；§9 A1-A6→Task 9 Step 2；§10 checklist→Task 1-9 对应。无缺口。
2. **Placeholder scan**：无 TBD/TODO；所有代码步骤给出完整代码；「以 base.css 实有 token 替换」是显式核对指令而非占位。
3. **Type consistency**：`save_draft(kind, asset_id, content, username)` 在 Task 3 定义、Task 4 路由与 Task 6 api 调用一致；`preview_export` 返回 `{items, all_ok}` 与弹窗消费一致；`asset_kind` 取值 `paradigm_md`/`forms_catalog` 全文一致；路由 `/eia/paradigms/...` 与 api 封装一致；Task 3 中初版 `_preview_sync`/`_export_sync` 的竞态问题已用「修正版为准」内联解决（实现者以修正版代码落地，勿抄初版）。
