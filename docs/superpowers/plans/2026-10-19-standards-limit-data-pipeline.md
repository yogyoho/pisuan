# 标准与限值库限值数据管线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec `docs/superpowers/specs/2026-10-19-standards-limit-data-pipeline-design.md`：语料限值自动提取 → 暂存逐行人工核实 → 正式表/新表入册 → 导出物化，外加 62 条核实辅助与标准原文（乙通道）试跑门。

**Architecture:** 纯函数提取内核（定位/解析/归一/聚合）+ 暂存表（eia_limit_extract_rows）隔离噪声 + 表注册表（eia_limit_table_registry，新表入册）+ 复用现有 P1/P3 通道落库导出。写作侧（standards_index 消费方）不变。

**Tech Stack:** FastAPI + SQLAlchemy（pg_manager 会话上下文）/ Vue3 script setup + ant-design-vue message / pytest。

**对 spec 的三处澄清（实现定稿）：**
1. 新表入册必然扩展现有导出/列表：export_limit_rows 增加「DB 注册表新键物化」分支、list_limit_tables 合并注册表 schemas——7 张已有表的逻辑零改动，仅新增分支；
2. 引用清单接口改为 GET /eia/standards/citations?code=（query param）——注册表 10/62 条编号含 /（GB/T、HJ/T），路径参数段无法跨越内部斜杠（eia/standards/review 已实证）；
3. POST /extract 为同步纯 CPU 任务（33 份 × 数十章节切片，无 LLM 调用），直接返回提取报告；若实测 >30s 再改后台任务。

**运行栈提醒：** 运行容器是 pisuan-localized-* 系列；测试放 backend/test/；严禁对运行栈跑清表类集成测试。

---

### Task 1: 暂存表 + 表注册表模型 + v20 迁移

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`（EiaStandardReview 类之后追加）
- Modify: `backend/package/yuxi/storage/postgres/manager.py`（:56 版本常量；upgrade_business_v18_to_v19 之后追加新方法）
- Modify: `backend/package/yuxi/storage_migration.py`（v19 编排步之后追加）
- Test: `backend/test/unit/storage/test_storage_migration.py`

- [ ] **Step 1: 写模型** —— 在 models_domain_factory.py 的 EiaStandardReview 类后追加（Index/format_utc_datetime 等按文件头既有 import 补齐）：

```python
class EiaLimitExtractRow(Base):
    """Domain Factory - 语料限值提取暂存行（spec 2026-10-19；噪声隔离层，人工核实后转正）。"""

    __tablename__ = "eia_limit_extract_rows"
    __table_args__ = (Index("ix_eler_table_key", "table_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_key = Column(String(80), nullable=False)  # 已知表键，或 __candidate__:<归一码>
    code = Column(String(50), nullable=False)  # 归一标准号（如 GB 3838-2002）
    row_json = Column(JSON, nullable=False)  # 行数据；conflict 时附 conflict_values
    confidence = Column(String(16), nullable=False)  # multi / single / conflict
    sources = Column(JSON, nullable=False)  # [{report_id, anchor}] 溯源到语料切片
    status = Column(String(16), nullable=False, default="pending")  # pending/confirmed/edited/discarded
    decided_by = Column(String(64), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)  # 仅 DB 留档，不物化
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "table_key": self.table_key, "code": self.code, "row": self.row_json,
            "confidence": self.confidence, "sources": self.sources, "status": self.status,
            "decided_by": self.decided_by,
            "decided_at": format_utc_datetime(self.decided_at) if self.decided_at else None,
            "note": self.note, "created_at": format_utc_datetime(self.created_at),
        }


class EiaLimitTableRegistry(Base):
    """Domain Factory - 限值表注册元数据（新表入册通道；导出物化时并入 limit_tables）。"""

    __tablename__ = "eia_limit_table_registry"

    table_key = Column(String(64), primary_key=True)
    code = Column(String(50), nullable=False)  # code_ref，如 GB 8978-1996
    desc = Column(Text, nullable=False)
    columns_schema = Column(JSON, nullable=False)  # {col: {label, type: str|number, required}}
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_key": self.table_key, "code": self.code, "desc": self.desc,
            "columns_schema": self.columns_schema, "created_by": self.created_by,
            "created_at": format_utc_datetime(self.created_at),
        }
```

- [ ] **Step 2: manager.py 迁移** —— `BUSINESS_SCHEMA_VERSION = 20`；在 upgrade_business_v18_to_v19 方法后照 v19 样板追加 upgrade_business_v19_to_v20：幂等（version==20 直接 return）、版本白名单 (...19)、`create_all(tables=[EiaLimitExtractRow.__table__, EiaLimitTableRegistry.__table__])`、INSERT 版本记录 20。两个新模型加入该文件 models import。

- [ ] **Step 3: storage_migration.py 编排链** —— v19 步后追加：

```python
            # [pisuan-custom] v20：限值提取暂存表 + 表注册表（spec 2026-10-19，幂等）
            if business_version in {None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19}:
                await pg_manager.upgrade_business_v19_to_v20()
```

- [ ] **Step 4: 迁移测试** —— test_storage_migration.py 跟随 v19 既有用例模式追加 v20：断言 BUSINESS_SCHEMA_VERSION == 20、upgrade_business_v19_to_v20 存在且幂等、编排链含 v20 步骤。

- [ ] **Step 5: 跑测试** —— `docker exec pisuan-localized-api-1 pytest /app/test/unit/storage/test_storage_migration.py -q` → PASS

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/storage_migration.py backend/test/unit/storage/test_storage_migration.py
git commit -m "feat(domain-factory): 限值提取暂存表+表注册表模型与 v20 迁移"
```

---

### Task 2: 提取内核纯函数模块

**Files:**
- Create: `backend/package/yuxi/services/eia_limit_extract_core.py`
- Test: `backend/test/unit/services/test_eia_limit_extract_core.py`

- [ ] **Step 1: 写失败测试**（夹具模仿真实语料「执行标准」区块形态）

```python
"""eia_limit_extract_core 单测：区块定位 / 表格+行内解析 / 归一 / 聚合置信。"""

from yuxi.services.eia_limit_extract_core import (
    aggregate_records, locate_standard_blocks, norm_code, parse_block, table_key_for,
)

WINDOW = """## 1.4 环境质量标准

项目所在区域环境空气质量执行《环境空气质量标准》(GB3095-2012)二级标准，见下表：

| 污染物 | 取值时间 | 浓度限值 | 单位 |
| ------ | -------- | -------- | ---- |
| SO2 | 1小时 | 0.50 | mg/m3 |
| SO2 | 24小时 | 0.15 | mg/m3 |
| PM10 | 24小时 | 0.15 | mg/m3 |

地表水执行《地表水环境质量标准》(GB3838-2002)III类标准：COD 标准限值 20 mg/L，
氨氮 1.0 mg/L。噪声执行《声环境质量标准》(GB 3096-2008)2类标准。
"""


def test_norm_code_strips_noise():
    assert norm_code("GB/15618-2018") == norm_code("GB 15618—2018") == norm_code("GB15618-2018")


def test_table_key_known_and_unknown():
    assert table_key_for("GB 3095-2012") == "gb3095_concentration_limits"
    assert table_key_for("GB3838-2002") == "gb3838_category_limits"
    assert table_key_for("GB 8978-1996") is None  # 候选


def test_locate_blocks_finds_codes():
    blocks = locate_standard_blocks(WINDOW)
    codes = {norm_code(b.code) for b in blocks}
    assert {"GB3095-2012", "GB3838-2002", "GB3096-2008"} <= codes
    assert all(b.lines for b in blocks)


def test_parse_block_table_rows_schema_mapped():
    b3095 = next(b for b in locate_standard_blocks(WINDOW) if norm_code(b.code) == "GB3095-2012")
    rows = parse_block(b3095)
    assert {"pollutant": "SO₂", "period": "1小时", "grade": "二级标准",
            "limit_value": 0.5, "unit": "mg/m³"} in rows
    assert {"pollutant": "PM10", "period": "24小时", "grade": "二级标准",
            "limit_value": 0.15, "unit": "mg/m³"} in rows


def test_parse_block_inline_rows():
    b3838 = next(b for b in locate_standard_blocks(WINDOW) if norm_code(b.code) == "GB3838-2002")
    rows = parse_block(b3838)
    assert {"category": "III类", "pollutant": "COD", "limit_value": 20.0, "unit": "mg/L"} in rows
    assert {"category": "III类", "pollutant": "氨氮", "limit_value": 1.0, "unit": "mg/L"} in rows


def test_aggregate_confidence():
    def rec(v, rid):
        return {"code": "GB 3095-2012", "table_key": "gb3095_concentration_limits",
                "row": {"pollutant": "SO₂", "period": "24小时", "grade": "二级标准",
                        "limit_value": v, "unit": "mg/m³"},
                "source": {"report_id": rid, "anchor": "ch1"}}
    out = aggregate_records([rec(0.15, "001-wps"), rec(0.15, "038-2024-7-9"), rec(0.5, "039-r")])
    assert len(out) == 1 and out[0]["confidence"] == "conflict"
    assert out[0]["row"]["conflict_values"] == [0.15, 0.5]
    assert len(out[0]["sources"]) == 3
```

- [ ] **Step 2: 跑测试确认失败** —— `docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_limit_extract_core.py -q` → FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现内核** —— `backend/package/yuxi/services/eia_limit_extract_core.py`，要点：

```python
"""语料限值提取内核（纯函数，spec 2026-10-19 W2）。定位→解析→归一→聚合；不碰 IO/DB。"""

_STD_NOISE_RE = re.compile(r"[\s\-—–/]+")   # 与 eia_standard_service._norm_std 同一口径
_CODE_RE = re.compile(r"(?:GB|HJ)(?:/T)?\s?\d+(?:\.\d+)?[-—–]\d{4}")
_TABLE_LINE_RE = re.compile(r"^\s*\|")
_NUM_RE = re.compile(r"[≤<]?\s*([\d.]+)")

def norm_code(code): return _STD_NOISE_RE.sub("", code).upper()

# 已知 7 表 → 归一码前缀（年份不敏感）
_TABLE_BY_PREFIX = {"GB3096": "gb3096_zone_limits", "GB12348": "gb12348_boundary_limits",
                    "GB3095": "gb3095_concentration_limits", "GB3838": "gb3838_category_limits",
                    "GBT14848": "gbt14848_category_limits", "GB20426": "gb20426_emission_limits",
                    "GBT13201": "gbt13201_a_value"}

def table_key_for(code):
    c = norm_code(code)
    return next((k for p, k in _TABLE_BY_PREFIX.items() if c.startswith(p)), None)

# FACTOR_ALIASES：so2/so₂/二氧化硫→SO₂，no2→NO₂，nox/氮氧化物→NOx，pm10/可吸入颗粒物→PM10，
#   pm2.5/细颗粒物→PM2.5，tsp→TSP，o3/臭氧→O₃，co→CO，cod/化学需氧量→COD，bod5→BOD₅，氨氮/总磷/总氮/氟化物/石油类→原名
def norm_factor(name): return FACTOR_ALIASES.get(name.strip().lower().replace(" ", ""), name.strip())

def norm_grade(ctx):
    """上下文提取档位：N级标准→N级标准；Ⅰ-Ⅴ/1-5/一-五 类→罗马+类（III类）。"""
    # 两个正则分支，命中返回规一档位串，否则 None（实现见代码）

_UNIT_FIXES = {"mg/m3": "mg/m³", "μg/m3": "μg/m³", "ug/m3": "μg/m³", "µg/m³": "μg/m³", "mg/l": "mg/L", "db(a)": "dB(A)"}
def norm_unit(u): ...
def convert_limit(value, unit):  # μg/m³ → mg/m³ (÷1000)；其余原样

@dataclass
class Block: code: str; lines: list[str]; start: int

def locate_standard_blocks(text, max_window=30):
    """逐行扫 _CODE_RE；窗口=命中行向后至 md 标题或下一标准号，≤30 行。"""

def parse_block(block):
    """1) GFM 表格（表头|分隔|数据三段式）逐行解析；
    2) 行内正则：因子+时段词?+浓度?+限值?+≤数值+单位。
    已知表 → schema 列（gb3095: pollutant/period/grade/limit_value/unit；
    gb3838/gbt14848: category/pollutant/limit_value/unit；噪声表: category/day/night/unit）；
    候选表 → 原始列名（col_<列名>）+ 数值列。解析不出的行丢弃（服务层报告计数）。"""

def _biz_key(row):  # 业务键=除数值列与 conflict_values 外全部字段
def aggregate_records(records):
    """按 (归一码, table_key, 业务键) 聚合；值列全一致→multi(≥2 份不同报告)/single(单源)；
    不一致→conflict + conflict_values。返回 [{code, table_key, row, confidence, sources}]。"""
```

（完整实现照测试断言语义写；正则与映射为初始版，Task 9 真实语料试跑后允许调参，但测试语义断言不得放松。）

- [ ] **Step 4: 跑到绿** —— 同 Step 2 命令 → PASS

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/eia_limit_extract_core.py backend/test/unit/services/test_eia_limit_extract_core.py
git commit -m "feat(domain-factory): 语料限值提取内核纯函数（定位/解析/归一/聚合）"
```

---

### Task 3: 提取仓储层

**Files:**
- Create: `backend/package/yuxi/repositories/eia_limit_extract_repository.py`
- Modify: `backend/package/yuxi/repositories/eia_standard_repository.py`（追加单行转正方法）

- [ ] **Step 1: 实现仓储**（薄 CRUD，不单独测——语义由 Task 4 服务层覆盖）

```python
"""语料限值提取暂存仓储（eia_limit_extract_rows + eia_limit_table_registry，spec 2026-10-19）。"""

from __future__ import annotations

from sqlalchemy import select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaLimitExtractRow, EiaLimitTableRegistry
from yuxi.utils.datetime_utils import utc_now_naive


class EiaLimitExtractRepository:
    async def list_rows(self, table_key=None, status=None, confidence=None):
        stmt = select(EiaLimitExtractRow).order_by(EiaLimitExtractRow.id)
        if table_key:
            stmt = stmt.where(EiaLimitExtractRow.table_key == table_key)
        if status:
            stmt = stmt.where(EiaLimitExtractRow.status == status)
        if confidence:
            stmt = stmt.where(EiaLimitExtractRow.confidence == confidence)
        async with pg_manager.get_async_session_context() as session:
            return list((await session.scalars(stmt)).all())

    async def add_rows(self, rows):
        async with pg_manager.get_async_session_context() as session:
            session.add_all(rows)
            await session.commit()
            return len(rows)

    async def get_row(self, row_id):
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLimitExtractRow, row_id)

    async def save_row(self, row):
        async with pg_manager.get_async_session_context() as session:
            await session.merge(row)
            await session.commit()
            return row

    async def list_registry(self):
        async with pg_manager.get_async_session_context() as session:
            return list((await session.scalars(select(EiaLimitTableRegistry))).all())

    async def get_registry(self, table_key):
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLimitTableRegistry, table_key)

    async def save_registry(self, row):
        async with pg_manager.get_async_session_context() as session:
            await session.merge(row)
            await session.commit()
            return row
```

`eia_standard_repository.py` 追加（同业务键先删后插，防与编辑器整表替换互相打架）：

```python
    async def upsert_row(self, table_key: str, row: dict, username: str) -> None:
        """逐行转正写入：同 table_key 下业务键完全一致的旧行先删（幂等），再插入。"""
        import json as _json

        biz = _json.dumps(row, ensure_ascii=False, sort_keys=True)
        async with pg_manager.get_async_session_context() as session:
            existing = (
                await session.scalars(select(EiaStandardLimitRow).where(EiaStandardLimitRow.table_key == table_key))
            ).all()
            for e in existing:
                if _json.dumps(e.row_json, ensure_ascii=False, sort_keys=True) == biz:
                    await session.delete(e)
            session.add(EiaStandardLimitRow(table_key=table_key, row_json=row, decided_by=username,
                                            created_at=utc_now_naive(), updated_at=utc_now_naive()))
            await session.commit()
```

- [ ] **Step 2: 语法验证 + Commit**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/repositories/eia_limit_extract_repository.py', encoding='utf-8').read()); print('OK')"
git add backend/package/yuxi/repositories/eia_limit_extract_repository.py backend/package/yuxi/repositories/eia_standard_repository.py
git commit -m "feat(domain-factory): 限值提取暂存仓储与正式表单行转正"
```

---

### Task 4: 提取服务层（试跑/裁决/立表/引用清单）

**Files:**
- Create: `backend/package/yuxi/services/eia_limit_extract_service.py`
- Modify: `backend/package/yuxi/services/eia_standard_service.py`（list_limit_tables 末尾合并注册表）
- Modify: `backend/package/yuxi/repositories/eia_standard_repository.py`（补 list_registry）
- Test: `backend/test/unit/services/test_eia_limit_extract_service.py`

- [ ] **Step 1: 写失败测试**（仓储以内存桩替身，沿 test_eia_library_service 模式）

```python
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
    from yuxi.services import eia_limit_extract_service as mod

    repo = StubExtractRepo()
    s = mod.EiaLimitExtractService(repo=repo)
    monkeypatch.setattr(s, "_bank_dirs", lambda: [tmp_path])
    d = tmp_path / "planning_eia" / "slices" / "ch1"
    d.mkdir(parents=True)
    (d / "038-2024-7-9__1.md").write_text(
        "执行《环境空气质量标准》(GB3095-2012)二级标准：
"
        "| 污染物 | 取值时间 | 浓度限值 | 单位 |
| --- | --- | --- | --- |
"
        "| SO2 | 24小时 | 0.15 | mg/m3 |
", encoding="utf-8")
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
    monkeypatch.setattr(s._std_repo, "upsert_row", lambda tk, r, u: upserted.append((tk, r, u)))
    out = await s.decide_row(row.id, "confirm", None, "admin", note="对照原文无误")
    assert out["status"] == "confirmed" and upserted[0][0] == row.table_key


@pytest.mark.asyncio
async def test_register_candidate_migrates_rows(svc):
    s, repo = svc
    await s.run_extraction("admin")
    (await repo.list_rows())[0].table_key = "__candidate__:GB3095-2012"
    out = await s.register_candidate("GB 8978-1996", "gb8978_emission_limits", "污水综合排放标准",
                                     {"pollutant": {"label": "污染物", "type": "str", "required": True}}, "admin")
    assert out["migrated"] >= 0 and (await repo.get_registry("gb8978_emission_limits")) is not None
```

- [ ] **Step 2: 跑测试确认失败** → ModuleNotFoundError

- [ ] **Step 3: 实现服务** `backend/package/yuxi/services/eia_limit_extract_service.py`（照测试写全，语义骨架如下）

```python
"""语料限值提取服务（spec 2026-10-19 W2/W3 后端）。试跑→暂存；裁决→转正；候选→立表；引用→W1 辅助。"""

_BANK_ROOT = _SKILL_ROOT / "references" / "samples_bank"   # from eia_data_service import _SKILL_ROOT
_SLICE_NAME_RE = re.compile(r"^(?P<rid>.+?)__\d+\.md$")
_CANDIDATE_PREFIX = "__candidate__:"
_VALID_DECISIONS = {"confirm", "edited", "discarded"}


class EiaLimitExtractService:
    def __init__(self, repo=None, std_repo=None):
        # 缺省 EiaLimitExtractRepository() / EiaStandardRepository()

    def _bank_dirs(self):
        # _BANK_ROOT 下含 slices/ 子目录的阶段目录列表（threadpool 调用）

    async def run_extraction(self, username) -> dict:
        # 遍历 _bank_dirs()/**/slices/**/*.md → _SLICE_NAME_RE 取 report_id
        # locate_standard_blocks + parse_block → records（anchor=f"{stage}/{md.stem}"）
        # table_key = table_key_for(code) or f"__candidate__:{norm_code(code)}"
        # aggregate_records → 幂等过滤 → add_rows → 报告
        # 报告 = {files_scanned, aggregated, inserted, tables:{key:{total,multi,single,conflict}}}

    async def list_rows(self, table_key=None, status=None, confidence=None): ...

    async def decide_row(self, row_id, action, row_json, username, note=None) -> dict:
        # action 白名单 {confirm, edited, discarded}；edited 须带非空 row_json
        # confirm/edited → self._std_repo.upsert_row(table_key, row_json, username)
        # 更新 status/decided_by/decided_at/note → save_row → to_dict
        # KeyError→404 / ValueError→400 由路由层映射

    async def list_candidates(self) -> dict:  # __candidate__: 前缀行分组 {candidates:[{candidate_key, rows, count}]}

    async def register_candidate(self, code, table_key, desc, columns_schema, username) -> dict:
        # table_key 全小写 ^[a-z0-9_]+$；与 DB 注册表及 LIMIT_TABLE_SCHEMAS 查重
        # save_registry → 把 __candidate__:<norm_code(code)> 的 pending 行迁移为新键，返回 {table_key, migrated}

    async def list_citations(self, code) -> dict:
        # _load_corpus_meta() 遍历 reports，norm_code 匹配
        # → {code, cited_count, reports:[{report_id, stage, cited_as}]}


def _row_biz(row):
    """业务键 = 除数值列与 conflict_values 外全部字段。"""
    return tuple(sorted((k, str(v)) for k, v in row.items()
                        if k not in ("limit_value", "day", "night", "a_value")))


def _decided_key(r):
    return (r.code, r.table_key) + _row_biz(r.row_json or {})
```

幂等规则：重跑时 `_decided_key` 命中 `status≠pending` 行 → 跳过不覆盖；命中 pending 行 → 跳过不重插；否则插入新行。

- [ ] **Step 4: list_limit_tables 合并注册表**（eia_standard_service.py 返回前，仅新表分支、7 表逻辑不动）

```python
        # 新表入册（spec 2026-10-19）：DB 注册表露出新键 + schemas 合并
        schemas = dict(LIMIT_TABLE_SCHEMAS)
        for reg in await self.repo.list_registry():
            if reg.table_key not in tables:
                tables[reg.table_key] = {"desc": reg.desc, "code_ref": reg.code,
                                         "needs_verification": True, "verified": False,
                                         "rows": [], "source": "db_registry"}
            schemas[reg.table_key] = reg.columns_schema
        return {"limit_tables": tables, "schemas": schemas}
```

EiaStandardRepository 补 `list_registry()`（直查 EiaLimitTableRegistry，同上 select 模式）。

- [ ] **Step 5: 跑到绿** —— `docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_limit_extract_service.py -q` → PASS

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/services/eia_limit_extract_service.py backend/package/yuxi/services/eia_standard_service.py backend/package/yuxi/repositories/eia_standard_repository.py backend/test/unit/services/test_eia_limit_extract_service.py
git commit -m "feat(domain-factory): 限值提取服务（试跑幂等/裁决转正/候选立表/引用清单）"
```

---

### Task 5: API 层（6 端点 + 集成测试）

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（eia/standards 区块末尾追加）
- Create: `backend/test/integration/api/test_eia_standard_extract_flow.py`

- [ ] **Step 1: 实现端点**（鉴权对齐现有：读 get_required_user，extract/register get_admin_user；异常映射 KeyError→404 / ValueError→400 / Exception→500 照现有样板）

```python
# =============================================================================
# EIA Standard Limit Extract（语料限值提取：试跑→暂存→逐行核实，spec 2026-10-19）
# =============================================================================


@domain_factory.post("/eia/standards/extract")
async def run_eia_standard_extract(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """启动语料限值提取（同步纯 CPU，返回提取报告）"""
    try:
        return await get_eia_limit_extract_service().run_extraction(current_user.username)
    except Exception as e:
        logger.error(f"Failed eia standard extract: {e}
{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"限值提取失败: {str(e)}")


@domain_factory.get("/eia/standards/extract/rows")
async def list_eia_extract_rows(
    table_key: str | None = None,
    status: str | None = None,
    confidence: str | None = None,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    return {"rows": await get_eia_limit_extract_service().list_rows(table_key, status, confidence)}


@domain_factory.put("/eia/standards/extract/rows/{row_id}")
async def decide_eia_extract_row(
    row_id: int,
    payload: dict[str, Any],
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """暂存行裁决：{action: confirm|edited|discarded, row_json?, note?}；action 越界 400"""
    try:
        row = await get_eia_limit_extract_service().decide_row(
            row_id, payload.get("action"), payload.get("row_json"),
            current_user.username, payload.get("note"))
        return {"success": True, "row": row}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.get("/eia/standards/extract/candidates")
async def list_eia_extract_candidates(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    return await get_eia_limit_extract_service().list_candidates()


@domain_factory.post("/eia/standards/extract/candidates/register")
async def register_eia_extract_candidate(
    payload: dict[str, Any],
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """候选立表：{code, table_key, desc, columns_schema}（spec §5 表级新增通道）"""
    try:
        out = await get_eia_limit_extract_service().register_candidate(
            payload.get("code"), payload.get("table_key"), payload.get("desc"),
            payload.get("columns_schema"), current_user.username)
        return {"success": True, **out}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.get("/eia/standards/citations")
async def list_eia_standard_citations(
    code: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """W1 辅助：引用该标准的语料报告清单（query param——编号含 / 不能走路径段）"""
    return await get_eia_limit_extract_service().list_citations(code)
```

（文件头补 `get_eia_limit_extract_service` import。）

- [ ] **Step 2: 集成测试** —— 沿 `test_eia_paradigm_flow.py` 模式（认证门槛语义，业务由服务层覆盖）：

```python
"""eia_standard_extract API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.server.app import app  # 按现有集成测试实际 import 路径对齐


@pytest.mark.asyncio
async def test_extract_endpoints_require_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post("/api/domain-factory/eia/standards/extract")).status_code == 401
        assert (await client.get("/api/domain-factory/eia/standards/extract/rows")).status_code == 401
        assert (await client.put("/api/domain-factory/eia/standards/extract/rows/1", json={})).status_code == 401
        assert (await client.get("/api/domain-factory/eia/standards/citations")).status_code == 401
```

（认证 fixture / 依赖覆盖方式以既有集成测试文件为准——先读 `test_eia_paradigm_flow.py` 再写，保持同构。）

- [ ] **Step 3: 跑到绿 + format + Commit**

```bash
docker exec pisuan-localized-api-1 pytest /app/test/integration/api/test_eia_standard_extract_flow.py -q
make format
git add backend/server/routers/domain_factory_router.py backend/test/integration/api/test_eia_standard_extract_flow.py
git commit -m "feat(domain-factory): 限值提取 API 六端点（试跑/裁决/候选立表/引用清单）"
```

---

### Task 6: 前端 API 封装扩展

**Files:**
- Modify: `web/src/apis/eia_standard_api.js`

- [ ] **Step 1: 追加方法**（对齐现有 apiGet/apiPost/apiRequest 用法）

```javascript
  // ── 限值提取（spec 2026-10-19）──
  /** 启动语料限值提取（同步，admin）→ 提取报告 {files_scanned, tables, ...} */
  runExtract: () => apiPost('/api/domain-factory/eia/standards/extract'),
  /** 暂存行清单：?table_key=&status=&confidence= */
  listExtractRows: (params = {}) => apiGet('/api/domain-factory/eia/standards/extract/rows', params),
  /** 暂存行裁决：{action: confirm|edited|discarded, row_json?, note?} */
  decideExtractRow: (rowId, payload) =>
    apiRequest(`/api/domain-factory/eia/standards/extract/rows/${rowId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  /** 新表候选清单 */
  listCandidates: () => apiGet('/api/domain-factory/eia/standards/extract/candidates'),
  /** 候选立表（admin）：{code, table_key, desc, columns_schema} */
  registerCandidate: (payload) => apiPost('/api/domain-factory/eia/standards/extract/candidates/register', payload),
  /** W1 引用清单：?code=（query 传参——编号含 / 不能走路径） */
  listCitations: (code) => apiGet('/api/domain-factory/eia/standards/citations', { code }),
```

（`apiGet/apiPost/apiRequest` 的实参形态以该文件现有 import 与用法为准对齐。）

- [ ] **Step 2: lint + Commit**

```bash
cd web && pnpm run lint
git add web/src/apis/eia_standard_api.js
git commit -m "feat(web): 标准与限值库限值提取 API 封装"
```

---

### Task 7: StandardsPanel 扩展——提取草稿 + 新表候选

**Files:**
- Modify: `web/src/components/eia-data/StandardsPanel.vue`（902 行；在「限值查找表」区块后追加两个 h3 区块，沿用现有卡片/表格/徽标 class）

- [ ] **Step 1: 提取草稿区块**

模板要点（沿用面板既有 class 体系，不引新依赖）：
- 区块头：`<h3>提取草稿 <span class="muted">语料自动提取 · 逐行核实后进入正式表</span></h3>` + 「重新提取」按钮（`eiaStandardApi.runExtract()`，loading 态，完成后 `message.success('提取完成：插入 N 行')` 并刷新行清单与限值表）；
- table_key 分组 pills（复用限值查找表的 `.pill`/`.on` 样式与 `activeExtractTable` ref）；
- 行表格列：因子/档位/限值/单位（按 `schemas[tableKey]` 渲染，候选表按 `col_*` 键平铺）、置信徽标（multi=绿/single=灰/conflict=红，conflict 行额外展示 `row.conflict_values`）、状态、操作列「确认/编辑/丢弃」；
- 行展开：`sources` 列表（report_id + anchor）；
- conflict 行未裁决时「确认」禁用（强制先解决冲突值）；
- 编辑弹层：复用限值查找表现有行编辑弹层模式，字段由 `schemas[tableKey]` 驱动；
- 裁决调用：`decideExtractRow(row.id, {action, row_json, note})`，成功后从草稿清单移除并 `message.success`；「确认」前弹确认框（写入正式表）。

- [ ] **Step 2: 新表候选区块**

- 候选卡片列表：`candidate_key`（`__candidate__:GB8978-1996`）→ 展示标准号、候选行数、因子清单（rows 去重 pollutant）；
- 「立表」对话框三字段：table_key（正则提示 `^[a-z0-9_]+$`）、desc、列结构编辑（列名/label/type 下拉 str|number/required 勾选；默认按候选行 `col_*` 键预填）；
- 提交 `registerCandidate({code, table_key, desc, columns_schema})`；成功后刷新候选与限值表清单，`message.success('已立表并迁移 N 行')`；
- 「忽略」按钮：对该候选全部 pending 行逐行 `decideExtractRow(id, {action:'discarded'})`（确认框说明不可恢复）。

- [ ] **Step 3: 逻辑装配与状态**

```javascript
const extractRows = ref([])
const activeExtractTable = ref('')
const extractReport = ref(null)
const candidates = ref([])

const loadExtract = async () => {
  const [rows, cands] = await Promise.all([
    eiaStandardApi.listExtractRows({ status: 'pending' }),
    eiaStandardApi.listCandidates(),
  ])
  extractRows.value = rows.rows || []
  candidates.value = cands.candidates || []
}
// onMounted 现有加载序列后追加 loadExtract()（失败静默降级：提取功能不可用不阻塞既有区块）
```

- [ ] **Step 4: 验证 + Commit**

```bash
cd web && pnpm run lint
git add web/src/components/eia-data/StandardsPanel.vue
git commit -m "feat(web): 标准与限值库页扩展提取草稿与新表候选工作台"
```

---

### Task 8: 62 条总览增强（W1）——引用清单 + KB 查询弹层

**Files:**
- Modify: `web/src/components/eia-data/StandardsPanel.vue`（「标准核实清单」区块）

- [ ] **Step 1: 行展开引用清单** —— 标准行可展开：懒加载 `eiaStandardApi.listCitations(row.code)` → 引用报告列表（report_id + stage）+ `cited_count`；空态文案「语料 0 引用——SKILL 手工登记标准，须人工 KB/联网核实」。

- [ ] **Step 2: KB 查询弹层** —— 行操作加「KB 查询」：弹层内 KB 下拉（`databaseApi` 列表，默认选名称含「环评」的首个）+ 查询词预填 `<标准名> <编号>` + 调 `queryApi.queryTest(kbId, query, {})` 渲染片段列表（source/chunk 摘要）；弹层顶部固定提示条：「web_search 与 KB 片段仅作核实线索，不可直接引用条款号/限值」（对齐 SKILL.md 纪律）。

- [ ] **Step 3: lint + Commit**

```bash
cd web && pnpm run lint
git add web/src/components/eia-data/StandardsPanel.vue
git commit -m "feat(web): 62条标准核实辅助——引用清单展开与KB查询弹层"
```

---

### Task 9: 真实语料试跑（人工抽检门）

**Files:** 无新代码（调参可能在 Task 2 文件内）

- [ ] **Step 1: 容器内触发提取** —— 管理员 token 调 `POST /api/domain-factory/eia/standards/extract`（curl 或页面按钮），记录耗时；>30s 则按澄清 3 改后台任务（顺延为独立小任务）。

- [ ] **Step 2: 检查提取报告** —— 每表 total/multi/single/conflict 分布；候选清单；与预期对照（7 表应有多源行；GB 8978/GB 18599 等应出现在候选）。零命中或异常低 → 回 Task 2 调正则/窗口参数（测试语义不放松），重跑本步。

- [ ] **Step 3: 人工抽检（验收门）** —— 每张已知表随机抽 ≥10 行：对照 `sources` 指向的语料切片原文逐行核对（因子/档位/限值/单位）。**精度 ≥90% 判过**；不过 → 定位错误模式（档位误配/单位错换/因子错归）回 Task 2 修，重新抽检。

- [ ] **Step 4: 记录** —— 抽检结论（表 × 精度）记入 changelog 草稿；此门通过前不开放 W3 工作台给运营。

---

### Task 10: W4 试跑门——标准原文通道（乙）

**Files:**
- Create: `docs/vibe/2026-10-19-standards-source-pipeline-notes.md`（过程记录，gitignored，勿提交）

- [ ] **Step 1: 联网收集标准原文** —— WebSearch/WebFetch 尝试获取：GB 3095-2012、GB 3838-2002、GB/T 14848-2017、GB 3096-2008、GB 12348-2008、GB 20426-2006（PDF/docx）；每份记录来源 URL 与获取结果；拿不到的出清单交用户补充。文件暂存本地（不入 repo）。

- [ ] **Step 2: 建库与上传** —— 知识库若无「标准规范库」则新建；上传 GB 3838-2002，等待解析索引完成。

- [ ] **Step 3: enrich 试跑** —— `POST /api/regulation-library/enrich {kb_id, file_id, doc_code: "GB 3838-2002", doc_name: "地表水环境质量标准", doc_type: "technical_standard"}`；查 `standard_indicators` 产出行数与内容。

- [ ] **Step 4: 人工精度判定（验收门）** —— 对照 GB 3838-2002 已知表项（I~V 类 × 基本项目 24 项）核对 enrich 抽取：覆盖与数值正确性。**通过 → 批量铺开其余标准（同流程循环）**；**不通过 → 触发 fallback**：标准原文仅作 W3 工作台「原文阅读」辅助材料（人工对照裁决暂存行），enrich 留待后续迭代，本通道结论记入 changelog。

---

### Task 11: ground truth 比对（条件任务——Task 10 通过后执行）

**Files:**
- Modify: `backend/package/yuxi/services/eia_limit_extract_service.py`（追加比对方法）或独立脚本（取简）

- [ ] **Step 1: 比对实现** —— enrich 指标行 vs 暂存/正式行：按 (标准码, 因子, 档位) 归一联接 → 三态（一致/偏差/缺档）报告；偏差行清单供工作台打回（人工复核 `decide_row`）。

- [ ] **Step 2: 试跑一份报告 + Commit**（若为服务化实现则补单测）

```bash
git commit -m "feat(domain-factory): 限值行 ground truth 比对（enrich 指标 vs 暂存/正式行）"
```

---

### Task 12: 收尾——全量测试 / format / changelog

- [ ] **Step 1: 全量相关测试**（容器内）

```bash
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_limit_extract_core.py /app/test/unit/services/test_eia_limit_extract_service.py /app/test/unit/storage/test_storage_migration.py /app/test/unit/services/test_eia_paradigm_service.py -q
docker exec pisuan-localized-api-1 pytest /app/test/integration/api/test_eia_standard_extract_flow.py -q
```

- [ ] **Step 2: format + lint**

```bash
make format
cd web && pnpm run lint
```

- [ ] **Step 3: changelog** —— `docs/develop-guides/changelog.md` 追加条目（提取管线/工作台/立表通道/试跑结论/乙通道结论）。

- [ ] **Step 4: 汇报** —— 向用户汇报全量结果与剩余人工环节（62 条逐条核实、限值行批量裁决、乙通道缺口清单补充）。**后续 commit/push 均等用户明确指令。**

---

## Self-Review 记录

1. **Spec 覆盖**：W1→Task 8；W2→Task 2/3/4/9；W3→Task 7；W4→Task 10/11；数据流/schema→Task 1/4；API→Task 5；验收门→Task 9 Step 3 / Task 10 Step 4；工程纪律→Task 12。✓
2. **占位符**：Task 2/4 实现以「语义骨架 + 测试断言锁定语义」表达（正则调参留到 Task 9 真实语料校准是显式设计决策，非遗漏）；其余任务含完整代码/命令。✓
3. **类型一致性**：`table_key`（str）/`row_json`（dict）/`confidence`（multi|single|conflict）/`status`（pending|confirmed|edited|discarded）在模型/仓储/服务/API/前端各任务一致；`_decided_key` 口径 Task 4 全文统一。✓
4. **已知偏差**：澄清 1-3（见文件头）已声明；`EiaStandardRepository.list_registry` 为 Task 4 新增依赖，Task 3/4 各自覆盖其定义与调用。✓

---

## 修订记录 2026-10-19：A+B 改向（用户裁决）

Task 9 试跑门未过（严格精度 10-15%，结构性错配，详见 `docs/vibe/2026-10-19-extraction-ab-redirect.md`）。裁决：**A** formal 表数据源改标准原文优先（Task 10 乙通道提前为主通道，本计划 Step 1-4 不变，仅语义升级为 formal 表权威源）；**B** 新增 Task 13。原 Task 9 结论已记 changelog；Task 9 关闭，其重跑门移至 Task 13 Step 5。

### Task 13: 语料提取 LLM 语义判别层（B 通道）

**Files:**
- Create: `backend/package/yuxi/services/eia_limit_llm_classifier.py`
- Modify: `backend/package/yuxi/services/eia_limit_extract_service.py`（extract 流程接线）
- Test: `backend/test/unit/services/test_eia_limit_llm_classifier.py`

- [ ] **Step 1: 判别器模块** —— LLM 结构化输出（平台模型网关，选型默认「快速响应模型」，用户可否决）：输入 block 文本 + 表上下文，输出 JSON `{is_limit_statement: bool, pollutant, grade, limit_value, unit, evidence_span, reason}`；限值句才进入抽取，监测陈述直接跳过。解析失败/超时按「未通过」处理（fail-closed，不静默放行）。
- [ ] **Step 2: 服务层接线** —— extract 流程改为：locate 命中 block → LLM 判别 → 通过者走原 parse_block/聚合；行来源标注 `extractor: "llm"`；预估总时长 >30s 走后台任务（既有阈值逻辑）。
- [ ] **Step 3: 单测（mock LLM）+ 容器真实端点冒烟**
- [ ] **Step 4: 清 pending 重跑提取**
- [ ] **Step 5: 重跑 Task 9 抽检门** —— seed=42、每表随机 ≥10 行、对照切片原文四要素核对，≥90% 判过；过门后 W3 工作台解封交用户。
