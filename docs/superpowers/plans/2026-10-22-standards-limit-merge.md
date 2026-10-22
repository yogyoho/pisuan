# P1 标准限值合流（Q2=A 物理合并）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** eia_standard_limit_rows 退役，standard_indicators 成为标准限值单表单真相（专家行 born-verified 权威层 / enrich 候选层），统一分层查询供写手与页面对齐消费。

**Architecture:** spec `docs/superpowers/specs/2026-10-22-standards-limit-merge-design.md`（已批准）。standard_indicators（raw SQL 表，`extensions/regulation_library/models.py` ensure_schema）加 `table_key`/`page_row_id` 两列；七表异构行形在服务边界拍平/重组（纯函数模块）；三生产者（StandardsPanel 录入、语料限值提取转正、候选立表后录入）全量重指向；enrich DELETE 收窄 `AND source='enrich'`；query_indicators 升级带 layer/tier；export_limit_rows 端点废除。

**Tech Stack:** FastAPI + SQLAlchemy raw SQL（pg_manager）+ pytest + Vue3（StandardsPanel.vue）

---

## 执行环境约定（全任务通用）

- 分支 `pisuan-custom`；提交中文 Conventional Commits，结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`
- 运行栈容器：`pisuan-localized-api-1`（导入名 `pisuan.*`，仓库 `yuxi.*`）。改 service/extensions 代码后部署到容器：
  ```bash
  python -c "
  from pathlib import Path
  for src, dst in [('backend/package/yuxi/services/XXX.py', '/tmp/XXX.py')]:
      b = Path(src).read_bytes().replace(b'package/yuxi', b'package/pisuan').replace(b'yuxi.', b'pisuan.')
      Path(dst).write_bytes(b)
  " && docker cp MSYS_NO_PATHCONV=1 /tmp/XXX.py pisuan-localized-api-1:/app/package/pisuan/services/XXX.py
  ```
  （注意 `MSYS_NO_PATHCONV=1` 前缀防 Git Bash 路径改写；多文件逐个 cp）
- 容器内跑测试：`docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_XXX.py -v`（**MSYS 下路径必须加 MSYS_NO_PATHCONV=1**，否则静默 0 collected）
- **禁跑** `test/integration/services/test_eia_lexicon_service_flow.py`（会清空词表）
- 生产 DB（`pisuan-localized-postgres-1`，库 `yuxi_know`）只读为主；Task 5/9 的写入演练只插临时行并在同任务内清理
- 并行工作流脏文件**禁暂存**：knowledge_router.py、knowledge/*.py、web 侧 knowledge/FileTable/MarkdownPreview 等（本计划不碰这些文件，提交时逐一指名 `git add`）
- 每个 Task 结束：`make format`（host 侧，仅本任务触碰文件）+ 更新 `.wolf/memory.md`

---

### Task 1: ensure_schema 加 table_key / page_row_id 两列 + 索引

**Files:**
- Modify: `backend/package/yuxi/extensions/regulation_library/models.py`（DDL 常量）
- Test: 容器 DDL 冒烟（无单测文件——纯幂等 DDL，行为验证在 Task 2+ 的测试间接覆盖）

- [ ] **Step 1: 修改 DDL**

在 `models.py` 的 DDL 字符串末尾（`ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS doc_name TEXT;` 之后、`"""` 之前）追加：

```sql
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS table_key VARCHAR(64);
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS page_row_id VARCHAR(32);
CREATE INDEX IF NOT EXISTS ix_si_table_key ON standard_indicators (table_key);
```

- [ ] **Step 2: 部署 + 容器冒烟**

按执行环境约定 cp 到 api 容器，然后：

```bash
docker exec pisuan-localized-api-1 python -c "
import asyncio
from pisuan.extensions.regulation_library.models import ensure_schema
asyncio.run(ensure_schema())
asyncio.run(ensure_schema())  # 幂等：二次调用不炸
from pisuan.storage.postgres.manager import pg_manager
from sqlalchemy import text as t
async def main():
    async with pg_manager.get_async_session_context() as s:
        rows = (await s.execute(t(\"SELECT column_name FROM information_schema.columns WHERE table_name='standard_indicators' AND column_name IN ('table_key','page_row_id')\"))).all()
        print('cols:', sorted(r[0] for r in rows))
asyncio.run(main())
"
```

Expected: `cols: ['page_row_id', 'table_key']`

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/models.py
git commit -m "feat(domain-factory): standard_indicators 加 table_key/page_row_id（限值合流 schema 前置）"
```

---

### Task 2: 行形拍平/重组纯函数模块 + round-trip 单测

**Files:**
- Create: `backend/package/yuxi/services/eia_limit_row_mapping.py`
- Test: `backend/test/unit/services/test_eia_limit_row_mapping.py`

- [ ] **Step 1: 写失败测试**

```python
"""限值行形 ↔ 扁平指标双向映射单测（P1 合流 Task 2）。

七表异构行形（LIMIT_TABLE_SCHEMAS）在服务边界拍平为 standard_indicators 扁平行；
页面 GET 按 page_row_id 重组回行形。day/night 拆两行是关键用例。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package" / "yuxi" / "agents" / "skills" / "buildin" / "coal-eia-writer" / "scripts"))

from yuxi.services.eia_limit_row_mapping import flatten_limit_row, regroup_limit_rows


def test_flat_rows_direct_map():
    out = flatten_limit_row("gb3838_category_limits", {"category": "III类", "pollutant": "COD", "limit_value": 20, "unit": "mg/L"})
    assert out == [
        {"pollutant": "COD", "metric": "", "limit_value": 20, "unit": "mg/L",
         "condition": "", "category": "III类", "period": ""}
    ]
    assert all(r["page_row_id"] == out[0]["page_row_id"] for r in out)
    assert len(out[0]["page_row_id"]) == 32  # uuid hex[:32]


def test_day_night_splits_two_rows_shared_page_row_id():
    out = flatten_limit_row("gb3096_zone_limits", {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"})
    assert [(r["metric"], r["limit_value"]) for r in out] == [("昼间", 50), ("夜间", 40)]
    assert out[0]["page_row_id"] == out[1]["page_row_id"]
    assert out[0]["category"] == "0类" and out[0]["pollutant"] == ""


def test_a_value_and_phase_maps():
    out = flatten_limit_row("gbt13201_a_value", {"region_type": "工业区", "a_value": 7.5, "unit": "km²/k"})
    assert out[0]["metric"] == "A值" and out[0]["limit_value"] == 7.5 and out[0]["category"] == "工业区"
    out2 = flatten_limit_row("gb20426_emission_limits", {"pollutant": "SO2", "phase": "现有", "limit_value": 550, "unit": "mg/m³"})
    assert out2[0]["period"] == "现有" and out2[0]["metric"] == ""


def test_regroup_round_trip_all_shapes():
    cases = [
        ("gb3838_category_limits", {"category": "III类", "pollutant": "COD", "limit_value": 20, "unit": "mg/L"}),
        ("gbt14848_category_limits", {"category": "III类", "pollutant": "总硬度", "limit_value": 450, "unit": "mg/L"}),
        ("gb3095_concentration_limits", {"pollutant": "SO2", "period": "年平均", "grade": "一级", "limit_value": 20, "unit": "µg/m³"}),
        ("gb3096_zone_limits", {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}),
        ("gb12348_boundary_limits", {"category": "2类", "day": 60, "night": 50, "unit": "dB(A)"}),
        ("gb20426_emission_limits", {"pollutant": "SO2", "phase": "现有", "limit_value": 550, "unit": "mg/m³"}),
        ("gbt13201_a_value", {"region_type": "工业区", "a_value": 7.5, "unit": "km²/k"}),
    ]
    for tk, page_row in cases:
        flat = flatten_limit_row(tk, page_row)
        assert regroup_limit_rows(tk, flat) == [page_row], tk


def test_regroup_merges_day_night_by_page_row_id():
    flat = flatten_limit_row("gb3096_zone_limits", {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"})
    other = flatten_limit_row("gb3096_zone_limits", {"category": "1类", "day": 55, "night": 45, "unit": "dB(A)"})
    mixed = [flat[0], other[0], flat[1], other[1]]  # 打乱顺序
    out = regroup_limit_rows("gb3096_zone_limits", mixed)
    assert out == [
        {"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"},
        {"category": "1类", "day": 55, "night": 45, "unit": "dB(A)"},
    ]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest test/unit/services/test_eia_limit_row_mapping.py -v
```
Expected: FAIL（ModuleNotFoundError: eia_limit_row_mapping）

- [ ] **Step 3: 实现模块**

```python
"""限值行形 ↔ standard_indicators 扁平指标双向映射（P1 合流；spec 2026-10-22 §4）。

LIMIT_TABLE_SCHEMAS 七表异构行形是页面编辑/校验契约；落库统一拍平为扁平指标行。
day/night 拆两行共享 page_row_id（页面重组键）；page_row_id 由行形业务键确定性派生，
转正幂等删除以它为键。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def _page_row_id(table_key: str, page_row: dict[str, Any]) -> str:
    biz = json.dumps(page_row, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(f"{table_key}|{biz}".encode()).hexdigest()


def flatten_limit_row(table_key: str, page_row: dict[str, Any]) -> list[dict[str, Any]]:
    """页面行形 → 扁平指标行列表（共享同一 page_row_id；id 由调用方补）。"""
    prid = _page_row_id(table_key, page_row)

    def _row(**kw: Any) -> dict[str, Any]:
        return {
            "page_row_id": prid,
            "pollutant": kw.get("pollutant", ""),
            "metric": kw.get("metric", ""),
            "limit_value": kw["limit_value"],
            "unit": kw.get("unit", ""),
            "condition": "",
            "category": kw.get("category", ""),
            "period": kw.get("period", ""),
        }

    if "day" in page_row or "night" in page_row:  # 噪声行形：拆昼/夜两行
        return [_row(category=page_row.get("category", ""), metric="昼间", limit_value=page_row["day"], unit=page_row["unit"]),
                _row(category=page_row.get("category", ""), metric="夜间", limit_value=page_row["night"], unit=page_row["unit"])]
    if "a_value" in page_row:  # GB/T 13201 A 值
        return [_row(category=page_row.get("region_type", ""), metric="A值", limit_value=page_row["a_value"], unit=page_row["unit"])]
    return [
        _row(
            pollutant=page_row.get("pollutant", ""),
            limit_value=page_row["limit_value"],
            unit=page_row.get("unit", ""),
            category=page_row.get("category", page_row.get("grade", "")),
            period=page_row.get("period", page_row.get("phase", "")),
        )
    ]


def regroup_limit_rows(table_key: str, flat_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """扁平指标行 → 页面行形（按 page_row_id 分组；组内按昼间<夜间排序还原 day/night）。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in flat_rows:
        groups.setdefault(r["page_row_id"], []).append(r)
    out: list[dict[str, Any]] = []
    for prid in sorted(groups):
        rows = sorted(groups[prid], key=lambda r: 0 if r["metric"] == "昼间" else 1)
        head = rows[0]
        if head["metric"] == "昼间":  # 噪声行形重组
            out.append({"category": head["category"], "day": head["limit_value"],
                        "night": rows[1]["limit_value"], "unit": head["unit"]})
        elif head["metric"] == "A值":
            out.append({"region_type": head["category"], "a_value": head["limit_value"], "unit": head["unit"]})
        else:
            page: dict[str, Any] = {"pollutant": head["pollutant"]}
            if head["period"]:
                page["period" if table_key != "gb20426_emission_limits" else "phase"] = head["period"]
            if head["category"]:
                page["category" if table_key != "gb3095_concentration_limits" else "grade"] = head["category"]
            page["limit_value"] = head["limit_value"]
            page["unit"] = head["unit"]
            out.append(page)
    return out
```

注意：模块内 uuid import 若未用到则不写（round-trip 测试不依赖 id）；`test_flat_rows_direct_map` 断言 `len(...)==32` 用 md5 hexdigest（32 位）。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && python -m pytest test/unit/services/test_eia_limit_row_mapping.py -v
```
Expected: 5 passed

- [ ] **Step 5: 部署容器复跑 + Commit**

```bash
docker cp backend/test/unit/services/test_eia_limit_row_mapping.py pisuan-localized-api-1:/app/test/unit/services/
# 模块本体按执行环境约定 transform 后 cp
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 pytest /app/test/unit/services/test_eia_limit_row_mapping.py -v
```
Expected: 5 passed

```bash
git add backend/package/yuxi/services/eia_limit_row_mapping.py backend/test/unit/services/test_eia_limit_row_mapping.py
git commit -m "feat(domain-factory): 限值行形拍平/重组纯函数（day/night 拆行共享 page_row_id）"
```

---

### Task 3: born-verified 权威写入 + save_limit_rows 重指向

**Files:**
- Modify: `backend/package/yuxi/services/eia_standard_service.py`
- Test: `backend/test/unit/services/test_eia_standard_save_rows.py`

- [ ] **Step 1: 写失败测试**

```python
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
    return ses


def test_save_rows_writes_born_verified_expert_rows(session_env, monkeypatch):
    monkeypatch.setattr(svc, "_load_standards_index",
                        lambda: {"limit_tables": {"gbt14848_category_limits": {"code_ref": "GB/T 14848-2017"}}})
    service = svc.EiaStandardService()
    out = asyncio.run(service.save_limit_rows(
        "gbt14848_category_limits",
        [{"category": "III类", "pollutant": "总硬度", "limit_value": 450, "unit": "mg/L"}],
        "qa"))
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
    monkeypatch.setattr(svc, "_load_standards_index",
                        lambda: {"limit_tables": {"gb3096_zone_limits": {"code_ref": "GB 3096-2008"}}})
    service = svc.EiaStandardService()
    out = asyncio.run(service.save_limit_rows(
        "gb3096_zone_limits", [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}], "qa"))
    assert out["saved"] == 2
    p1, p2 = session_env.executes[1][1], session_env.executes[2][1]
    assert {p1["metric"], p2["metric"]} == {"昼间", "夜间"}
    assert p1["page_row_id"] == p2["page_row_id"]
```

- [ ] **Step 2: 跑测试确认失败**（AttributeError: pg_manager / save_limit_rows 仍走 repo）

- [ ] **Step 3: 实现**

`eia_standard_service.py` 顶部 import 补：

```python
import uuid

from sqlalchemy import text as sql_text

from yuxi.services.eia_limit_row_mapping import flatten_limit_row
from yuxi.storage.postgres.manager import pg_manager
```

（`format_utc_datetime, utc_now_naive` 已有；`EiaStandardLimitRow` 的 model import 与 repo 行方法在本任务后成为死代码——repo 清理放 Task 7 末尾统一做，本任务不删，保持每任务可独立回退。）

`EiaStandardService` 内新增公开写入函数（供 Task 7 转正复用）+ 改写 `save_limit_rows`：

```python
    async def _insert_expert_row(
        self, session: Any, table_key: str, doc_code: str, page_row: dict[str, Any], username: str
    ) -> None:
        """页面行形 → born-verified 权威行（source='expert'，verified_at=now）。"""
        for f in flatten_limit_row(table_key, page_row):
            await session.execute(
                sql_text(
                    "INSERT INTO standard_indicators "
                    "(id, doc_code, doc_name, unit_no, chunk_id, pollutant, metric, limit_value,"
                    " unit, condition, category, period, verified_at, verified_by, source,"
                    " table_key, page_row_id) "
                    "VALUES (:id, :code, :doc_name, '手录', NULL, :p, :m, :v, :u, :c, :cat, :prd,"
                    " now(), :verified_by, 'expert', :tk, :prid)"
                ),
                {
                    "id": uuid.uuid4().hex[:32],
                    "code": doc_code,
                    "doc_name": doc_code,  # 手录行 doc_name 暂以编号代（页面详情不依赖）
                    "p": f["pollutant"],
                    "m": f["metric"],
                    "v": f["limit_value"],
                    "u": f["unit"],
                    "c": f["condition"],
                    "cat": f["category"],
                    "prd": f["period"],
                    "verified_by": username,
                    "tk": table_key,
                    "prid": f["page_row_id"],
                },
            )

    async def save_limit_rows(self, table_key: str, rows: Any, username: str) -> dict[str, Any]:
        """限值行整表替换落 standard_indicators（born-verified 权威行；事务内删旧插新）。"""
        validated = _validate_limit_rows(table_key, rows)
        doc = await run_in_threadpool(_load_standards_index)
        code_ref = (doc.get("limit_tables", {}).get(table_key) or {}).get("code_ref") or table_key
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                sql_text("DELETE FROM standard_indicators WHERE table_key = :tk AND source = 'expert'"),
                {"tk": table_key},
            )
            for page_row in validated:
                await self._insert_expert_row(session, table_key, code_ref, page_row, username)
        logger.info(f"[eia-standard] 限值表 {table_key} 权威行落库 {len(validated)} 行（by {username}）")
        return {"table_key": table_key, "saved": len(validated)}
```

旧实现体（`saved = await self.repo.replace_rows(...)` 段）整段删除。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && python -m pytest test/unit/services/test_eia_standard_save_rows.py test/unit/services/test_eia_standard_gate1.py -v
```
Expected: 全 passed（gate1 回归不受影响）

- [ ] **Step 5: 部署容器复跑 + Commit**

```bash
git add backend/package/yuxi/services/eia_standard_service.py backend/test/unit/services/test_eia_standard_save_rows.py
git commit -m "feat(domain-factory): 限值录入重指向 standard_indicators（born-verified 权威行）"
```

---

### Task 4: list_limit_tables 重指向（file 锚点 + expert 重组 + verified 派生）

**Files:**
- Modify: `backend/package/yuxi/services/eia_standard_service.py`
- Test: `backend/test/unit/services/test_eia_standard_list_limits.py`

- [ ] **Step 1: 写失败测试**

```python
"""list_limit_tables 重指向单测：文件锚点 source='file' + 专家行重组 source='expert' + 表级 verified 派生。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from yuxi.services import eia_standard_service as svc


def _flat(tk, prid, **kw):
    base = {"table_key": tk, "page_row_id": prid, "pollutant": "", "metric": "", "limit_value": 1,
            "unit": "", "condition": "", "category": "", "period": "",
            "verified_by": "qa", "verified_at": datetime(2026, 10, 22, 12, 0, 0)}
    base.update(kw)
    return base  # list_expert_rows 返回 dict（r["key"] 取值）


@pytest.fixture
def list_env(monkeypatch):
    monkeypatch.setattr(svc, "_load_standards_index", lambda: {
        "limit_tables": {
            "gbt14848_category_limits": {"desc": "地下水", "code_ref": "GB/T 14848-2017",
                                         "needs_verification": True, "verified": False, "rows": []},
            "gb3096_zone_limits": {"desc": "声环境", "code_ref": "GB 3096-2008", "needs_verification": True,
                                   "verified": False, "rows": [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}]},
            "_comment": "说明项",
        }})
    monkeypatch.setattr(svc.EiaStandardService, "list_registry", lambda self: [])


def test_expert_rows_regroup_and_override_seed(list_env, monkeypatch):
    rows = [
        _flat("gbt14848_category_limits", "a1", pollutant="总硬度", limit_value=450, unit="mg/L", category="III类"),
        _flat("gb3096_zone_limits", "b1", metric="昼间", limit_value=50, unit="dB(A)", category="0类"),
        _flat("gb3096_zone_limits", "b1", metric="夜间", limit_value=40, unit="dB(A)", category="0类"),
    ]
    monkeypatch.setattr(svc.EiaStandardService, "list_expert_rows",
                        lambda self: rows)  # Task 4 实现的读取方法
    out = asyncio.run(svc.EiaStandardService().list_limit_tables())
    t = out["limit_tables"]["gbt14848_category_limits"]
    assert t["source"] == "expert" and t["verified"] is True and t["needs_verification"] is False
    assert t["rows"] == [{"pollutant": "总硬度", "category": "III类", "limit_value": 450, "unit": "mg/L"}]
    t2 = out["limit_tables"]["gb3096_zone_limits"]
    assert t2["source"] == "expert" and t2["rows"] == [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}]
    assert out["limit_tables"]["_comment"] == "说明项"  # 说明项透传不变
    assert "gbt14848_category_limits" in out["schemas"]


def test_file_seed_kept_when_no_expert_rows(list_env, monkeypatch):
    monkeypatch.setattr(svc.EiaStandardService, "list_expert_rows", lambda self: [])
    out = asyncio.run(svc.EiaStandardService().list_limit_tables())
    t = out["limit_tables"]["gb3096_zone_limits"]
    assert t["source"] == "file" and t["verified"] is False and t["needs_verification"] is True
    assert t["rows"] == [{"category": "0类", "day": 50, "night": 40, "unit": "dB(A)"}]  # 锚点样例行原样
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

`eia_standard_service.py`：

import 补 `from yuxi.services.eia_limit_row_mapping import flatten_limit_row, regroup_limit_rows`。

`EiaStandardService` 新增读取方法（紧跟 `_insert_expert_row` 后）：

```python
    async def list_expert_rows(self) -> list[Any]:
        """standard_indicators 全量专家行（page_row_id 重组的原材料）。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                sql_text(
                    "SELECT table_key, page_row_id, doc_code, pollutant, metric, limit_value,"
                    " unit, condition, category, period, verified_by, verified_at"
                    " FROM standard_indicators WHERE source = 'expert' AND table_key IS NOT NULL"
                    " ORDER BY table_key, page_row_id, id"
                )
            )
            return [dict(r._mapping) for r in result.all()]
```

`list_limit_tables` 整方法替换为：

```python
    async def list_limit_tables(self) -> dict[str, Any]:
        """limit_tables：文件锚点（source='file'，seed 展示）+ 专家行重组（source='expert'，覆盖锚点）。

        表级 verified 派生：该 table_key 存在专家行即 true（DB 唯一真相，不再依赖文件 flag 翻转）。
        """
        doc = await run_in_threadpool(_load_standards_index)
        by_table: dict[str, list] = {}
        for r in await self.list_expert_rows():
            by_table.setdefault(r["table_key"], []).append(r)

        tables: dict[str, Any] = {}
        for name, t in doc.get("limit_tables", {}).items():
            if not isinstance(t, dict):  # _comment 等说明项原样透传
                tables[name] = t
                continue
            merged = dict(t)
            flat = by_table.get(name)
            if flat:
                page_rows = regroup_limit_rows(
                    name, [{k: r[k] for k in ("page_row_id", "pollutant", "metric", "limit_value",
                                              "unit", "condition", "category", "period")} for r in flat]
                )
                first = flat[0]
                merged.update({
                    "rows": page_rows,
                    "source": "expert",
                    "decided_by": first.get("verified_by"),
                    "updated_at": format_utc_datetime(first["verified_at"]) if first.get("verified_at") else None,
                    "verified": True,
                    "needs_verification": False,
                })
            else:
                merged.update({"source": "file"})
            tables[name] = merged
        for key, flat in by_table.items():  # 注册表漂移防护：有专家行但文件锚点消失的表仍须露出
            if key not in tables:
                merged = {"code_ref": flat[0]["doc_code"]}
                merged.update({
                    "rows": regroup_limit_rows(
                        key, [{k: r[k] for k in ("page_row_id", "pollutant", "metric", "limit_value",
                                                 "unit", "condition", "category", "period")} for r in flat]
                    ),
                    "source": "expert",
                    "verified": True,
                    "needs_verification": False,
                })
                tables[key] = merged
        # 新表入册（spec 2026-10-19）：DB 注册表露出新键 + schemas 合并（不变）
        schemas = dict(LIMIT_TABLE_SCHEMAS)
        for reg in await self.repo.list_registry():
            if reg.table_key not in tables:
                tables[reg.table_key] = {
                    "desc": reg.desc,
                    "code_ref": reg.code,
                    "needs_verification": True,
                    "verified": False,
                    "rows": [],
                    "source": "db_registry",
                }
            schemas[reg.table_key] = reg.columns_schema
        return {"limit_tables": tables, "schemas": schemas}
```

（`list_standards` 里 counts 的 `limit_tables_pending` 统计逻辑保持——它读文件 flag，Task 8 一并复核。本任务不动。）

- [ ] **Step 4: 跑测试确认通过**（含 gate1 回归）

- [ ] **Step 5: 部署容器复跑 + Commit**

```bash
git add backend/package/yuxi/services/eia_standard_service.py backend/test/unit/services/test_eia_standard_list_limits.py
git commit -m "feat(domain-factory): StandardsPanel 限值读取重指向（专家行重组 + 表级 verified 派生）"
```

---

### Task 5: enrich DELETE 收窄 source='enrich'

**Files:**
- Modify: `backend/package/yuxi/extensions/regulation_library/enrichment_service.py:182`
- Test: `backend/test/integration/regulation_library/test_enrich_delete_scope.py`（新目录新文件）

- [ ] **Step 1: 写失败测试**

```python
"""enrich 删旧插新不得波及专家行（P1 合流 Task 5；集成测试直连运行栈 PG）。

enrich_regulation_file 全函数依赖文档与 LLM，不可直跑；DELETE 语句提为模块常量后
以常量真源验证语义：enrich 行被清、expert 行幸存。
"""

import asyncio
import uuid

import pytest
from sqlalchemy import text as sql_text

from pisuan.extensions.regulation_library.enrichment_service import ENRICH_DELETE_SQL
from pisuan.storage.postgres.manager import pg_manager


@pytest.fixture
def seed_rows():
    async def _seed():
        async with pg_manager.get_async_session_context() as s:
            await s.execute(sql_text(
                "INSERT INTO standard_indicators (id, doc_code, pollutant, metric, limit_value, unit,"
                " condition, category, period, source, table_key, page_row_id)"
                " VALUES ('t5-expert', 'T5-DOC', 'p', '', 1, '', '', '', '', 'expert', 'gb3838_category_limits', 'pr1'),"
                " ('t5-enrich', 'T5-DOC', 'p', '', 2, '', '', '', '', 'enrich', NULL, NULL)"))
        return True
    return asyncio.run(_seed())

    # 清理在测试体内 finally 完成


async def _cleanup():
    async with pg_manager.get_async_session_context() as s:
        await s.execute(sql_text("DELETE FROM standard_indicators WHERE id IN ('t5-expert','t5-enrich')"))


def test_enrich_delete_spares_expert_rows(seed_rows):
    try:
        async def main():
            async with pg_manager.get_async_session_context() as s:
                await s.execute(sql_text(ENRICH_DELETE_SQL), {"code": "T5-DOC"})
                rows = (await s.execute(sql_text(
                    "SELECT id, source FROM standard_indicators WHERE doc_code='T5-DOC'"))).all()
                assert rows == [("t5-expert", "expert")]

        asyncio.run(main())
    finally:
        asyncio.run(_cleanup())
```

（conftest：`backend/test/integration/` 已有 conftest.py 提供 pisuan.* 导入路径——沿用；若无，文件头加 `import sys; sys.path.insert(0, "backend/package")` 等价适配，以现有 integration 用例的导入方式为准。）

- [ ] **Step 2: 实现常量并替换调用点**

`enrichment_service.py` 模块级（`_MANUAL_UNIT_NO` 附近）加：

```python
# enrich 幂等删旧：仅清自身候选行——expert 权威行对重跑免疫（P1 合流，spec §5）
ENRICH_DELETE_SQL = "DELETE FROM standard_indicators WHERE doc_code = :code AND source = 'enrich'"
```

enrich_regulation_file 内原 `sql_text("DELETE FROM standard_indicators WHERE doc_code = :code")` 改为 `sql_text(ENRICH_DELETE_SQL)`。

- [ ] **Step 3: 测试转绿 + 容器复跑**

```bash
docker cp backend/test/integration/regulation_library/ pisuan-localized-api-1:/app/test/integration/
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 pytest /app/test/integration/regulation_library/test_enrich_delete_scope.py -v
```
Expected: 1 passed

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/enrichment_service.py backend/test/integration/regulation_library/
git commit -m "fix(domain-factory): enrich 删旧收窄 source='enrich'，专家权威行对重跑免疫"
```

---

### Task 6: query_indicators 升级（layer/tier/table_nv/table_key）

**Files:**
- Modify: `backend/package/yuxi/extensions/regulation_library/enrichment_service.py`（query_indicators + 锚点 helper）
- Test: `backend/test/unit/extensions/test_query_indicators_layer.py`（目录不存在则建）

> **T5 质量评审 rider（bug-4125 语境）**：本任务单测是纯函数（无 pg_manager）；冒烟脚本若用
> `asyncio.run` 跑 `query_indicators`，必须把 `await pg_manager.close()` 放进 loop 存续期内
> （try/finally），否则 psycopg 池后台任务令退出永久挂死。若后续出现第二个消费 pg_manager 的
> async 测试，把 `test_enrich_delete_scope.py` 的 `_run` **提升**（非复制）入 conftest——复制
> 即稀碎。

- [ ] **Step 1: 写失败测试**

```python
"""query_indicators 分层派生与锚点 join 纯函数单测（P1 合流 Task 6）。"""

from yuxi.extensions.regulation_library.enrichment_service import _anchor_maps, _layer_of


def test_layer_of_three_layers():
    assert _layer_of("expert", "2026-10-22T00:00:00") == "authority"
    assert _layer_of("enrich", "2026-10-22T00:00:00") == "reviewed"
    assert _layer_of("enrich", None) == "candidate"


def test_anchor_maps_from_standards_index():
    tier_by_code, nv_by_ref = _anchor_maps({
        "standards": [{"code": "GB 3838-2002", "tier": "national"}, {"code": "GB/T 14848-2017", "tier": "national"}],
        "limit_tables": {"gbt14848_category_limits": {"code_ref": "GB/T 14848-2017", "needs_verification": True}},
    })
    assert tier_by_code.get("GB/T 14848-2017") == "national"
    assert nv_by_ref.get("gbt14848_category_limits") is True
```

- [ ] **Step 2: 实现**

`enrichment_service.py`：

模块级 helper（`query_indicators` 上方）：

```python
def _layer_of(source: str, verified_at: Any) -> str:
    """行级分层：expert 权威 / enrich+verified 已核验候选 / enrich 裸候选（spec §2）。"""
    if source == "expert":
        return "authority"
    return "reviewed" if verified_at else "candidate"


def _anchor_maps(doc: dict[str, Any]) -> tuple[dict[str, str], dict[str, bool]]:
    """standards_index.json 锚点：{code: tier} + {table_key: needs_verification}。"""
    tier_by_code = {s["code"]: s.get("tier") for s in doc.get("standards", []) if s.get("code")}
    nv_by_ref = {
        k: bool(t.get("needs_verification"))
        for k, t in doc.get("limit_tables", {}).items()
        if isinstance(t, dict)
    }
    return tier_by_code, nv_by_ref
```

import 补：`import json`（若无）、`from yuxi.services.eia_data_service import _SKILL_ROOT`（extensions→services 已有 norm_code 先例）。

`query_indicators` 整函数替换：

```python
async def query_indicators(doc_code: str | None = None, pollutant: str | None = None) -> list[dict]:
    """精确查询指标（分层：authority > reviewed > candidate；供 API 与 writer 工具使用）"""
    await ensure_schema()
    conditions, params = [], {}
    if doc_code:
        conditions.append("doc_code = :code")
        params["code"] = doc_code
    if pollutant:
        conditions.append("pollutant = :p")
        params["pollutant"] = pollutant
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            sql_text(
                f"SELECT doc_code, doc_name, unit_no, pollutant, metric, limit_value, "
                f"unit, condition, category, period, verified_at, verified_by, source, "
                f"table_key FROM standard_indicators {where} "
                f"ORDER BY CASE WHEN source = 'expert' THEN 0 ELSE 1 END, doc_code, unit_no"
            ),
            params,
        )
        rows = [dict(r._mapping) for r in result.all()]
    doc = json.loads((_SKILL_ROOT / "references" / "standards_index.json").read_text(encoding="utf-8"))
    tier_by_code, nv_by_ref = _anchor_maps(doc)
    for r in rows:  # TIMESTAMPTZ → ISO 串 + 派生分层/锚点标注
        r["verified_at"] = format_utc_datetime(r["verified_at"])
        r["layer"] = _layer_of(r["source"], r["verified_at"])
        r["tier"] = tier_by_code.get(r["doc_code"])
        r["table_nv"] = nv_by_ref.get(r["table_key"]) if r["table_key"] else None
    return rows
```

- [ ] **Step 3: 测试转绿 + 容器复跑 + 实数据冒烟**

```bash
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 python -c "
import asyncio
from pisuan.extensions.regulation_library.enrichment_service import query_indicators
rows = asyncio.run(query_indicators(pollutant='化学需氧量'))
print(len(rows), sorted({r['layer'] for r in rows}), rows[0]['tier'] if rows else None)
"
```
Expected: 非 0 行、layer 全 'candidate'、tier='national'（GB 3838 锚点命中）

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/enrichment_service.py backend/test/unit/extensions/
git commit -m "feat(domain-factory): 统一分层限值查询（layer/tier/table_nv，权威行优先）"
```

---

### Task 7: 语料限值提取转正重指向 + repo 死代码清理

**Files:**
- Modify: `backend/package/yuxi/services/eia_limit_extract_service.py:214`
- Modify: `backend/package/yuxi/repositories/eia_standard_repository.py`（删死方法）
- Test: 修改 `backend/test/unit/services/test_eia_limit_extract_service.py`（两处桩）

- [ ] **Step 1: 改测试桩**

`test_eia_limit_extract_service.py:98` 与 `:132` 两处 `monkeypatch.setattr(s._std_repo, "upsert_row", fake_upsert)` 改为 patch 服务层函数：

```python
    monkeypatch.setattr(svc_eia_standard.EiaStandardService, "_insert_expert_row", fake_insert)  # fake 同 async 形
```

具体：文件头加 `from yuxi.services.eia_standard_service import EiaStandardService as _ESS`；
`fake_upsert(tk, r, u)` 桩改为 `async def fake_insert(self, session, tk, page_row, u): calls.append((tk, page_row, u))`，
断言从 `(tk, r, u)` 改 `(tk, page_row, u)`（page_row 即行形 dict，断言键等价）。
`_std_repo` 若再无他处引用则连同其构造桩一并移除。
同用例一并 monkeypatch（新代码路径需要）：`s.pg_manager.get_async_session_context`（FakeSession
同 Task 3 模式）与 `s._load_standards_index`（返回含该 table_key 的 code_ref 最小锚点）。

- [ ] **Step 2: 实现转正重指向（按 page_row_id 幂等追加，非整表替换）**

> 裁决 API 是逐行调用（页面逐条确认/编辑），整表替换会冲掉先确认的行——必须按
> `page_row_id`（行形内容确定性派生）幂等：同行重确认 = 删旧插新，异行互不波及。

`eia_limit_extract_service.py:214`：

```python
            # 旧：await self._std_repo.upsert_row(row.table_key, normalized, username)
            # 转正 = born-verified 权威行按 page_row_id 幂等追加（裁决逐行触发，不能整表替换）
            svc_std = EiaStandardService()
            async with pg_manager.get_async_session_context() as session:
                doc = await run_in_threadpool(_load_standards_index)
                code_ref = (doc.get("limit_tables", {}).get(row.table_key) or {}).get("code_ref") or row.table_key
                await session.execute(
                    sql_text("DELETE FROM standard_indicators WHERE table_key = :tk AND source = 'expert' AND page_row_id = :prid"),
                    {"tk": row.table_key, "prid": _page_row_id(row.table_key, normalized)},
                )
                await svc_std._insert_expert_row(session, row.table_key, code_ref, normalized, username)
```

import 补：`from sqlalchemy import text as sql_text`、
`from yuxi.services.eia_limit_row_mapping import _page_row_id`、
`from yuxi.services.eia_data_service import _SKILL_ROOT`（若 `_load_standards_index` 未引入则
`from yuxi.services.eia_standard_service import EiaStandardService, _load_standards_index`）、
`from yuxi.storage.postgres.manager import pg_manager`。
同时删 `self._std_repo = EiaStandardRepository()` 相关行（若无他处引用）。
模块 docstring 第 5 行「经 upsert_row 幂等转正到 eia_standard_limit_rows」改为
「经 _insert_expert_row born-verified 幂等转正到 standard_indicators 权威层」。

- [ ] **Step 3: repo 死方法清理**

`eia_standard_repository.py` 删 `replace_rows`/`upsert_row`（Task 3/7 使其无消费者；
`list_rows` 若 Task 4 后亦无调用一并删；`list_reviews`/`get_review`/`save_review`/`list_registry` 保留）。
`grep -rn "replace_rows\|upsert_row\|list_rows" backend/package/yuxi --include="*.py"` 确认零残留后，跑该 repo 相关全部单测。

- [ ] **Step 4: 全量验证 + Commit**

```bash
cd backend && python -m pytest test/unit/services/ -v
docker cp ... (deploy both files) && docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 pytest /app/test/unit/services/ -v
```

```bash
git add backend/package/yuxi/services/eia_limit_extract_service.py backend/package/yuxi/repositories/eia_standard_repository.py backend/test/unit/services/test_eia_limit_extract_service.py
git commit -m "refactor(domain-factory): 语料限值转正改 born-verified 直写权威层，退役 eia_standard_limit_rows 通道"
```

---

### Task 8: export_limit_rows 端点废除（后端 + 前端）

**Files:**
- Modify: `backend/package/yuxi/services/eia_standard_service.py`（删 `export_limit_rows`）
- Modify: `backend/server/routers/domain_factory_router.py:1579`（删端点）
- Modify: `web/src/apis/eia_standard_api.js:13-14`（删 exportLimits）
- Modify: `web/src/components/eia-data/StandardsPanel.vue`（删按钮/pill/函数）

- [ ] **Step 1: 后端删除**

- 删 `export_limit_rows` 方法整段（`eia_standard_service.py`）
- 删 `domain_factory_router.py` 的 `@domain_factory.post("/eia/standards/limits/export")` 端点整段
- `grep -rn "export_limit_rows\|limits/export" backend/ --include="*.py"` 确认零残留（`export_reviews` 不受影响）

- [ ] **Step 2: 前端删除与徽章词表跟进（T4 评审折入）**

- `eia_standard_api.js`：删 `/** 限值行整表导出物化... */` 注释 + `exportLimits: () => apiPost(...)` 行
- `StandardsPanel.vue`：
  - 删模板中「导出限值行」`<button>` 块（`@click="exportLimits"` 的整个 button 元素）
  - 删页头 pill `<span v-if="dbTableCount" class="pill pill-orange">...表待导出</span>` 块
  - 删 `const exportLimits = async () => {...}` 整函数
  - grep `dbTableCount` 定位其 computed 定义并整块删除（该 computed 仅剩此 pill 与按钮两处消费，均已删）
  - **行内徽章词表跟进（T4 评审折入，source 语义已从 'db' 改 'expert'）**：限值表行内徽章的
    `t.source === 'db'` 分支改为 `'expert'`（文案「DB · 已核实」、pill-ok 类样式），'file' 分支
    保留「文件态」；徽章 title 的导出时代文案（「导出前须先录入核实」等）同步改写为无导出语义
  - **`limit_tables_pending` 口径收口（T4 评审折入）**：`list_standards` 的 counts 里
    `limit_tables_pending` 仍读文件 flag，与派生 verified 分叉——改为按重写后 `list_limit_tables`
    结果重算（`source != 'expert'` 的注册表计数），前端虽暂不消费，口径必须单一
- 确认 `exporting` ref 仍被「导出核实结果」（onExport）使用——保留

- [ ] **Step 3: 验证**

```bash
cd web && pnpm run lint
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 python -c "from pisuan.services.eia_standard_service import EiaStandardService; print(hasattr(EiaStandardService, 'export_limit_rows'))"
```
Expected: lint 0 error；`False`

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/services/eia_standard_service.py backend/server/routers/domain_factory_router.py web/src/apis/eia_standard_api.js web/src/components/eia-data/StandardsPanel.vue
git commit -m "refactor(domain-factory): 废除限值行 DB→文件物化导出（DB 已是唯一真相）"
```

---

### Task 9: SKILL 接线 + changelog + 集成冒烟 + 回归

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md:32`
- Modify: `docs/develop-guides/changelog.md`（**只编辑不暂存**——并行工作流脏文件）
- Test: 端到端冒烟

- [ ] **Step 1: SKILL.md 门 1 纪律接线**

Line 32 现文（「**标准编号/年份/限值只从 `references/standards_index.json` 枚举**…」）其后追加一句：

```
   限值断言优先经 `lookup_standard_indicator` 查权威行：`layer=authority` 可直接写成
   断言；`layer=reviewed` 引用时标注「已核验候选」；`layer=candidate` 或查询为空 →
   写「[需人工对照]」不下结论（与 needs_verification=true 同纪律）。
```

- [ ] **Step 2: changelog 追加**（编辑允许，**严禁 git add**）

```markdown
- feat(domain-factory): 标准限值合流 P1（Q2=A 物理合并）。standard_indicators 成为单表单真相：
  专家行 born-verified 权威层（table_key/page_row_id 行形拍平映射）+ enrich 候选层（删旧收窄
  source='enrich'，重跑免疫）；统一分层查询（authority/reviewed/candidate + tier 锚点 join）；
  StandardsPanel 录入/读取重指向，语料限值转正直写权威层，DB→standards_index.json 限值物化
  导出废除（spec 2026-10-22-standards-limit-merge-design.md）。
```

- [ ] **Step 3: 端到端冒烟（容器，临时行用后即清）**

```bash
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 python -c "
import asyncio
from pisuan.services.eia_standard_service import EiaStandardService, get_eia_standard_service
from pisuan.extensions.regulation_library.enrichment_service import query_indicators

async def main():
    svc = get_eia_standard_service()
    # 1. 录入 GB/T 14848 一行（born-verified）
    r = await svc.save_limit_rows('gbt14848_category_limits',
        [{'category': 'III类', 'pollutant': '总硬度', 'limit_value': 450, 'unit': 'mg/L'}], 'qa')
    assert r['saved'] == 1, r
    # 2. 统一查询查到 authority 行
    rows = await query_indicators(doc_code='GB/T 14848-2017')
    assert rows and rows[0]['layer'] == 'authority' and rows[0]['table_key'] == 'gbt14848_category_limits', rows[:2]
    # 3. 页面读取表态：source=expert、verified 派生 True
    lt = (await svc.list_limit_tables())['limit_tables']['gbt14848_category_limits']
    assert lt['source'] == 'expert' and lt['verified'] is True and lt['needs_verification'] is False, lt
    # 4. 清理临时行
    from pisuan.storage.postgres.manager import pg_manager
    from sqlalchemy import text as t
    async with pg_manager.get_async_session_context() as s:
        await s.execute(t(\"DELETE FROM standard_indicators WHERE table_key='gbt14848_category_limits' AND source='expert'\"))
    print('SMOKE OK')

asyncio.run(main())
"
```
Expected: `SMOKE OK`

- [ ] **Step 4: 全量回归**

```bash
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 pytest /app/test/unit/services/ /app/test/unit/extensions/ -v
docker exec MSYS_NO_PATHCONV=1 pisuan-localized-api-1 pytest /app/test/integration/regulation_library/ -v
# 禁跑 test/integration/services/test_eia_lexicon_service_flow.py
```

- [ ] **Step 5: 收尾**

- `make format`（host）
- `.wolf/buglog.json` 视冒烟结果记录；`.wolf/memory.md` 会话行
- 提交 SKILL.md：

```bash
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md
git commit -m "docs(domain-factory): SKILL 门1 纪律接统一分层限值查询（authority 可断言/candidate 需人工对照）"
```

- 汇报用户：改动面、冒烟证据、未推送提交清单（推送等用户指令）

---

## Self-Review 记录

- **Spec 覆盖**：§3 schema→Task 1；§4 映射→Task 2；§5 三入口→Task 3/7（候选立表本身不改，录入走 Task 3 通道）；enrich 收窄→Task 5；§6 查询→Task 6；§7 消费者→Task 4/8；§8 SKILL→Task 9；§9 迁移（0 行，无数据迁移）→Task 1 冒烟即含列就位验证
- **类型一致性**：`flatten_limit_row`/`regroup_limit_rows` 签名在 Task 2/3/4 一致；`page_row_id` 32 位 md5 hex 与 DDL VARCHAR(32) 一致
- **已知边界（写入提交信息）**：regulation_library 既有 `create_manual_standard`（无 table_key 的手工行入口）与本通道并存——其查重语义（doc_code 有任何行即拒）天然防双入口同标准混写；`replace_manual_standard` 的整标准替换只动其自建行范围外不变（doc_code 不同则互不相扰）
