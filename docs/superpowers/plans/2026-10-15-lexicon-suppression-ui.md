# 数值护栏词表 · 抑制名单 UI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 词表页补齐抑制名单卡（列表 + 手工添加 + 撤回），后端 4 端点 + repo 3 方法 + service 4 方法，零 schema 变更。

**Architecture:** 复用既有 `eia_lexicon_suppressions` 表（v13 已播种 7 行）与 `add_suppression` 幂等 upsert；service 层对"手工添加"做扫描差集强校验（不在 `_scan_all` 且非词条的指纹一律 400，杜绝静默无操作）；前端在词条表下方加第二张卡（原型 s9 同位），添加下拉数据源为扫描候选差集端点。

**Tech Stack:** FastAPI + SQLAlchemy(async) / Vue 3 setup + AntD (a-select/a-modal/a-textarea) / pytest（FakeRepo + monkeypatch，零真实 DB）

**Spec:** `docs/superpowers/specs/2026-10-15-lexicon-suppression-ui-design.md`
**对 spec 的一处偏差（有意）:** spec 写"撤回行不存在 → ValueError→400"，实现改为 `KeyError → 404`——与 lexicon 区既有惯例一致（`update_entry`/`split_entry`/mentions 端点不存在均走 KeyError→404）。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/package/yuxi/repositories/eia_lexicon_repository.py` | 修改 | +3 方法：list/get/delete_suppression（改名抑制区） |
| `backend/package/yuxi/services/eia_lexicon_service.py` | 修改 | +4 方法：list_suppressions / scan_candidates / add_suppression / withdraw_suppression（新「抑制名单」区） |
| `backend/server/routers/domain_factory_router.py` | 修改 | +4 端点（import 端点之后、datasets/switches 之前） |
| `backend/test/unit/test_eia_lexicon_suppression_ops.py` | 新建 | FakeRepo 单测，零真实 DB |
| `web/src/apis/eia_lexicon_api.js` | 修改 | +4 函数 |
| `web/src/components/eia-data/LexiconPanel.vue` | 修改 | 抑制名单卡 + 添加弹窗 + 撤回确认 + 刷新接线 |
| `docs/develop-guides/changelog.md` | 修改 | v0.7.3 功能组补一条 |

**容器路径映射**：容器 `/app` ≈ 仓库 `backend/`（如 `/app/package/yuxi/...`、`/app/test/unit/...`）。
**运行栈是绑定挂载**：容器看不到 pisuan 工作树的改动，**每次容器内执行（pytest/ruff/eslint）前必须先 `powershell.exe -NoProfile -File scripts/sync-dev.ps1`**（禁止 `-ExecutionPolicy Bypass`，会被权限分类器拒绝）。容器 eslint 必须在 sync 之后跑，否则测的是旧文件（假绿，已记 DNR）。

---

### Task 1: repository 3 方法

**Files:**
- Modify: `backend/package/yuxi/repositories/eia_lexicon_repository.py`（`add_suppression` 之后、`# ========== 数据集开关 ==========` 之前，约 line 121）

- [ ] **Step 1: 加入 3 个方法**

在 `add_suppression` 方法结束（`await session.execute(stmt)` 之后）与 `# ========== 数据集开关 ==========` 注释之间插入：

```python
    async def list_suppressions(self) -> list[EiaLexiconSuppression]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EiaLexiconSuppression).order_by(
                    EiaLexiconSuppression.created_at.desc(), EiaLexiconSuppression.id.desc()
                )
            )
            return list(result.scalars().all())

    async def get_suppression(self, suppression_id: int) -> EiaLexiconSuppression | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EiaLexiconSuppression).where(EiaLexiconSuppression.id == suppression_id)
            )
            return result.scalar_one_or_none()

    async def delete_suppression(self, suppression_id: int) -> None:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(EiaLexiconSuppression, suppression_id)
            if row is not None:
                await session.delete(row)
```

（repo 层无单测——项目惯例：FakeRepo 代表 repo，DB 流转在集成环境验证；本层由 Task 2 的服务单测与 Task 5 只读冒烟覆盖。）

- [ ] **Step 2: 语法与风格验证**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker exec api-dev sh -c "cd /app && python -c \"from yuxi.repositories.eia_lexicon_repository import EiaLexiconRepository; print('OK')\""
docker exec api-dev sh -c "cd /app && ruff format package/yuxi/repositories/eia_lexicon_repository.py && ruff check package/yuxi/repositories/eia_lexicon_repository.py"
```

Expected: `OK`；ruff 无报错（若 format 改动了文件，检查 diff 只含本次新增行）。

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/repositories/eia_lexicon_repository.py
git commit -m "feat(domain-factory): 词表抑制名单数据访问方法（列表/单查/硬删）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: service 4 方法（TDD）

**Files:**
- Create: `backend/test/unit/test_eia_lexicon_suppression_ops.py`
- Modify: `backend/package/yuxi/services/eia_lexicon_service.py`（`split_entry` 结束之后、`# ── 开关与导出 ──` 之前，约 line 309）

- [ ] **Step 1: 写失败测试（完整文件）**

```python
"""eia_lexicon_service 抑制名单运营单元测试：列表 / 手工添加校验 / 撤回 / 扫描差集。

DB 流转零依赖：FakeRepo 代表抑制表访问面，monkeypatch svc._scan_all 代表语料扫描；
绝不触真实 PG（集成流测试会清 eia_lexicon_entries 表，禁在运行栈跑）。
"""

import asyncio
from types import SimpleNamespace

import pytest

import yuxi.services.eia_lexicon_service as svc

# 语料扫描替身：3 候选，其一已是词条
SCAN_CANDS = [
    {"stage": "planning_eia", "caliber": "水平达标率", "unit": "%", "category": "measure"},
    {"stage": "planning_eia", "caliber": "节水率", "unit": "%", "category": "measure"},
    {"stage": "planning_eia", "caliber": "已入库口径", "unit": "%", "category": "site"},
]


class _SuppressionRow(SimpleNamespace):
    """镜像真实行形状：EiaLexiconSuppression 含 to_dict（models_domain_factory.py:475）。"""

    def to_dict(self):
        return {
            "id": self.id,
            "stage": self.stage,
            "caliber": self.caliber,
            "unit": self.unit,
            "new_caliber": self.new_caliber,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


def _row(sid=1, new_caliber="三率水平达标率", reason="改名抑制：水平达标率 → 三率水平达标率"):
    return _SuppressionRow(
        id=sid,
        stage="planning_eia",
        caliber="水平达标率",
        unit="%",
        new_caliber=new_caliber,
        reason=reason,
        created_by="alice",
        created_at=None,
    )


class FakeRepo:
    """抑制表访问面替身：内存行集 + existing 指纹集 + add 调用记录。"""

    def __init__(self, rows=None, existing=()):
        self.rows = list(rows or [])
        self.existing = set(existing)
        self.added = []

    async def list_suppressions(self):
        return list(self.rows)

    async def get_suppression(self, sid):
        return next((r for r in self.rows if r.id == sid), None)

    async def delete_suppression(self, sid):
        self.rows = [r for r in self.rows if r.id != sid]

    async def add_suppression(self, stage, caliber, unit, new_caliber, reason, created_by):
        self.added.append((stage, caliber, unit, new_caliber, reason, created_by))

    async def existing_keys(self):
        return set(self.existing)

    async def suppressed_keys(self):
        return {(r.stage, r.caliber, r.unit) for r in self.rows}


def _svc(repo):
    s = svc.EiaLexiconService()
    s.repo = repo
    return s


@pytest.fixture(autouse=True)
def fake_scan(monkeypatch):
    monkeypatch.setattr(svc, "_scan_all", lambda: [dict(c) for c in SCAN_CANDS])


def test_list_suppressions_maps_rows():
    out = asyncio.run(_svc(FakeRepo([_row(1), _row(2)])).list_suppressions())
    assert out["total"] == 2
    assert [it["id"] for it in out["items"]] == [1, 2]
    assert out["items"][0]["caliber"] == "水平达标率"


def test_add_suppression_missing_fields_rejected():
    with pytest.raises(ValueError, match="必填"):
        asyncio.run(_svc(FakeRepo()).add_suppression({"stage": "", "caliber": "x"}, "bob"))


def test_add_suppression_validates_against_scan_diff():
    repo = FakeRepo(existing={("planning_eia", "已入库口径", "%")})
    s = _svc(repo)
    # 已是词条 → 拒绝（词条上直接操作即可，无需抑制）
    with pytest.raises(ValueError, match="已是词表条目"):
        asyncio.run(s.add_suppression({"stage": "planning_eia", "caliber": "已入库口径", "unit": "%"}, "bob"))
    # 不在语料扫描结果 → 拒绝（抑制永不生效，静默无操作必须报错）
    with pytest.raises(ValueError, match="不在语料扫描结果"):
        asyncio.run(s.add_suppression({"stage": "planning_eia", "caliber": "语料没有的词", "unit": "%"}, "bob"))
    # 合法候选 → 落库且 new_caliber=''（手工行无语境回落）
    asyncio.run(s.add_suppression({"stage": "planning_eia", "caliber": "节水率", "unit": "%", "reason": "扫描噪声"}, "bob"))
    assert repo.added == [("planning_eia", "节水率", "%", "", "扫描噪声", "bob")]


def test_add_suppression_idempotent_refresh_on_suppressed():
    """已抑制指纹重复登记 → 幂等刷新（repo upsert），不报错。"""
    repo = FakeRepo(rows=[_row(1)])
    asyncio.run(
        _svc(repo).add_suppression({"stage": "planning_eia", "caliber": "水平达标率", "unit": "%", "reason": "复评"}, "carol")
    )
    assert repo.added == [("planning_eia", "水平达标率", "%", "", "复评", "carol")]


def test_withdraw_suppression_deletes_row_or_raises():
    repo = FakeRepo([_row(7)])
    out = asyncio.run(_svc(repo).withdraw_suppression(7, "bob"))
    assert out["id"] == 7
    assert repo.rows == []
    with pytest.raises(KeyError):
        asyncio.run(_svc(repo).withdraw_suppression(7, "bob"))


def test_scan_candidates_diff():
    repo = FakeRepo(rows=[_row(1)], existing={("planning_eia", "已入库口径", "%")})
    out = asyncio.run(_svc(repo).scan_candidates())
    # 水平达标率已抑制、已入库口径已入库 → 只剩 节水率
    assert out["total"] == 1
    assert out["items"][0]["caliber"] == "节水率"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker exec api-dev pytest /app/test/unit/test_eia_lexicon_suppression_ops.py -v
```

Expected: FAIL——`AttributeError: 'EiaLexiconService' object has no attribute 'add_suppression'`（service 方法未实现）。

- [ ] **Step 3: 实现 service 4 方法**

在 `split_entry` 方法结束（`return {"parent_id": entry_id, "children": len(clean_items)}` 之后）与 `# ── 开关与导出 ──` 之间插入：

```python
    # ── 抑制名单 ──

    async def list_suppressions(self) -> dict[str, Any]:
        """抑制行全量列表（改名自动登记 + 手工登记 + 迁移种子）。"""
        items = await self.repo.list_suppressions()
        return {"items": [s.to_dict() for s in items], "total": len(items)}

    async def scan_candidates(self) -> dict[str, Any]:
        """重扫导入将带进来的候选差集（添加抑制下拉数据源）：_scan_all − 已入库 − 已抑制。"""
        cands = await run_in_threadpool(_scan_all)
        existing = await self.repo.existing_keys()
        suppressed = await self.repo.suppressed_keys()
        skip = existing | suppressed
        items = [c for c in cands if (c["stage"], c["caliber"], c["unit"]) not in skip]
        return {"items": items, "total": len(items)}

    async def add_suppression(self, payload: dict[str, Any], username: str) -> dict[str, Any]:
        """手工登记抑制：仅限扫描差集内的候选指纹——屏蔽语料中不存在的指纹永不生效，
        属误操作须报错而非静默吞掉；已抑制指纹幂等刷新（repo upsert）；手工行
        new_caliber=''，无语境回落（无改名目标即无回落，语义自洽）。"""
        stage = str(payload.get("stage") or "").strip()
        caliber = str(payload.get("caliber") or "").strip()
        unit = str(payload.get("unit") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if not stage or not caliber:
            raise ValueError("stage 与 caliber 必填")
        cands = await run_in_threadpool(_scan_all)
        if (stage, caliber, unit) not in {(c["stage"], c["caliber"], c["unit"]) for c in cands}:
            raise ValueError(f"指纹不在语料扫描结果中，抑制无效果: {stage}/{caliber}/{unit}")
        if (stage, caliber, unit) in await self.repo.existing_keys():
            raise ValueError(f"该指纹已是词表条目，请在词条上直接操作: {stage}/{caliber}/{unit}")
        await self.repo.add_suppression(
            stage=stage, caliber=caliber, unit=unit, new_caliber="", reason=reason, created_by=username
        )
        logger.info(f"[eia-lexicon] 手工登记抑制 {stage}/{caliber}/{unit}（{username}）")
        return {"success": True}

    async def withdraw_suppression(self, suppression_id: int, username: str) -> dict[str, Any]:
        """撤回抑制（硬删行，无补种机制）：重扫可能复活旧指纹，UI 撤回前须明示两条后果。"""
        row = await self.repo.get_suppression(suppression_id)
        if row is None:
            raise KeyError(f"抑制行不存在: {suppression_id}")
        await self.repo.delete_suppression(suppression_id)
        logger.info(f"[eia-lexicon] 撤回抑制 {row.stage}/{row.caliber}/{row.unit}（{username}）")
        return row.to_dict()
```

- [ ] **Step 4: 跑测试确认通过 + ruff**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker exec api-dev pytest /app/test/unit/test_eia_lexicon_suppression_ops.py -v
docker exec api-dev sh -c "cd /app && ruff format package/yuxi/services/eia_lexicon_service.py test/unit/test_eia_lexicon_suppression_ops.py && ruff check package/yuxi/services/eia_lexicon_service.py test/unit/test_eia_lexicon_suppression_ops.py"
```

Expected: 6 passed；ruff 无报错。

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/eia_lexicon_service.py backend/test/unit/test_eia_lexicon_suppression_ops.py
git commit -m "feat(domain-factory): 抑制名单服务方法——手工添加扫描差集校验/幂等刷新/撤回

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: router 4 端点

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（`import_eia_lexicon` 端点结束之后、`@domain_factory.get("/eia/datasets/switches")` 之前，约 line 1129）

- [ ] **Step 1: 加入 4 个端点**

```python
@domain_factory.get("/eia/lexicon/suppressions")
async def list_eia_lexicon_suppressions(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """抑制名单（改名自动登记 + 手工登记）：导入按 (stage, caliber, unit) 跳过"""
    try:
        return await get_eia_lexicon_service().list_suppressions()
    except Exception as e:
        logger.error(f"Failed to list eia lexicon suppressions: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取抑制名单失败: {str(e)}")


@domain_factory.post("/eia/lexicon/suppressions")
async def add_eia_lexicon_suppression(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """手工登记抑制（业务人员）：仅限扫描差集内指纹，已抑制幂等刷新"""
    try:
        return await get_eia_lexicon_service().add_suppression(payload, current_user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add eia lexicon suppression: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"登记抑制失败: {str(e)}")


@domain_factory.delete("/eia/lexicon/suppressions/{suppression_id}")
async def withdraw_eia_lexicon_suppression(
    suppression_id: int,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """撤回抑制（硬删行）：重扫可能复活旧指纹，UI 撤回前须明示后果"""
    try:
        row = await get_eia_lexicon_service().withdraw_suppression(suppression_id, current_user.username)
        return {"success": True, "row": row}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to withdraw eia lexicon suppression {suppression_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤回抑制失败: {str(e)}")


@domain_factory.get("/eia/lexicon/scan-candidates")
async def list_eia_lexicon_scan_candidates(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """重扫导入将带进来的候选差集（添加抑制下拉数据源）"""
    try:
        return await get_eia_lexicon_service().scan_candidates()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to list eia lexicon scan candidates: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取扫描候选失败: {str(e)}")
```

（权限说明：全部 `get_required_user`——业务人员即可，与改名对称；导出/开关才挂 `get_admin_user`。）

- [ ] **Step 2: 路由注册冒烟**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker exec api-dev sh -c "cd /app && python -c \"from server.routers.domain_factory_router import domain_factory; ps=[(sorted(r.methods), r.path) for r in domain_factory.routes if 'suppression' in r.path or 'scan-candidates' in r.path]; print(ps); assert len(ps) == 4\""
```

Expected: 打印 4 条路由（GET/POST suppressions、DELETE suppressions/{id}、GET scan-candidates），无 AssertionError。

- [ ] **Step 3: ruff + Commit**

```bash
docker exec api-dev sh -c "cd /app && ruff format server/routers/domain_factory_router.py && ruff check server/routers/domain_factory_router.py"
git add backend/server/routers/domain_factory_router.py
git commit -m "feat(domain-factory): 抑制名单路由——列表/添加/撤回/扫描候选 4 端点

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 前端（API 封装 + 抑制名单卡 + 添加弹窗 + 撤回确认）

**Files:**
- Modify: `web/src/apis/eia_lexicon_api.js`
- Modify: `web/src/components/eia-data/LexiconPanel.vue`

- [ ] **Step 1: eia_lexicon_api.js 加 4 函数**

在 `exportOverrides` 之前插入（对象成员，注意前一行逗号）：

```js
  /** 抑制名单（改名自动登记 + 手工登记的旧指纹防复活清单）→ { items, total } */
  listSuppressions: () => apiGet('/api/domain-factory/eia/lexicon/suppressions'),
  /** 手工登记抑制 {stage, caliber, unit, reason?}（服务端校验扫描差集） */
  addSuppression: (payload) => apiPost('/api/domain-factory/eia/lexicon/suppressions', payload),
  /** 撤回抑制（硬删行；重扫可能复活）→ 被删行 dict */
  withdrawSuppression: (id) =>
    apiRequest(`/api/domain-factory/eia/lexicon/suppressions/${id}`, { method: 'DELETE' }),
  /** 重扫会导入的候选差集（添加抑制下拉数据源）→ { items, total } */
  getScanCandidates: () => apiGet('/api/domain-factory/eia/lexicon/scan-candidates'),
```

- [ ] **Step 2: LexiconPanel.vue——imports**

line 443 改为：`import { message, Modal } from 'ant-design-vue'`
line 444 改为：`import { Ban, BookOpen, Download, Info, Pencil, RefreshCw } from '@lucide/vue'`

- [ ] **Step 3: LexiconPanel.vue——模板（抑制名单卡 + 添加弹窗）**

在空态卡结束的 `</div>`（原 line 249）与 `<div class="note-bar">`（原 line 251）之间插入：

```html
    <!-- 抑制名单：改名/手工登记的旧指纹防复活清单（原型 s9 同位，词条表下方） -->
    <div class="card">
      <div class="card-hd">
        <h3>抑制名单</h3>
        <span class="hd-sub"
          >{{ suppressions.length }} 条 · 命中不计入护栏统计，重扫导入跳过</span
        >
        <div class="hd-right">
          <button
            class="btn btn-sec btn-sm"
            :disabled="supAdd.candidatesLoading"
            @click="openSupAdd"
          >
            <Ban :size="14" />添加抑制
          </button>
        </div>
      </div>
      <table v-if="suppressions.length" class="tbl">
        <thead>
          <tr>
            <th style="width: 26%">被抑制指纹</th>
            <th style="width: 12%">阶段</th>
            <th style="width: 18%">改名目标</th>
            <th style="width: 20%">理由</th>
            <th style="width: 14%">登记人 · 时间</th>
            <th class="r" style="width: 10%; padding-right: 20px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in suppressions" :key="row.id">
            <td>
              <span class="mono sup-fp" :title="`${row.caliber} (${row.unit})`">{{
                row.caliber
              }}</span>
            </td>
            <td>{{ stageLabel(row.stage) }}</td>
            <td class="mono">
              <span v-if="row.new_caliber" class="sup-new" :title="row.new_caliber">{{
                row.new_caliber
              }}</span>
              <span v-else class="missing-unit">—</span>
            </td>
            <td>
              <span class="sup-reason" :title="row.reason || ''">{{ row.reason || '—' }}</span>
            </td>
            <td class="dim-cell">{{ row.created_by || '—' }} · {{ row.created_at || '—' }}</td>
            <td class="r" style="padding-right: 20px; white-space: nowrap">
              <button class="btn btn-txt btn-sm withdraw-btn" @click="onWithdraw(row)">
                撤回抑制
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="sup-empty">
        {{ suppressionLoading ? '加载中…' : '暂无抑制行 — 改名词表口径时自动登记' }}
      </div>
      <div class="tbl-foot">
        <span
          >撤回后该旧指纹若仍在语料中，重扫将重新导入（A 类直接回已入选）；对应改名条目的语境回落也随之失效</span
        >
      </div>
    </div>

    <!-- 手工添加抑制：候选下拉限定扫描差集（服务端强校验兜底） -->
    <a-modal v-model:open="supAdd.open" title="添加抑制" :confirm-loading="supAdd.submitting" @ok="onSupAddSubmit">
      <div class="sup-form">
        <div class="fld">
          <label>被抑制指纹 <em>（仅列重扫会导入的候选）</em></label>
          <a-select
            v-model:value="supAdd.key"
            show-search
            :filter-option="filterCandidate"
            :options="candidateOptions"
            :loading="supAdd.candidatesLoading"
            placeholder="搜索口径名…"
          />
        </div>
        <div class="fld">
          <label>理由 <em>（可选）</em></label>
          <a-textarea v-model:value="supAdd.reason" :auto-size="{ minRows: 2, maxRows: 6 }" />
        </div>
      </div>
    </a-modal>
```

- [ ] **Step 4: LexiconPanel.vue——script（抑制名单状态与动作）**

在 `mentionValueDist` computed 结束（`})` 之后）与 `// ── 导出物化与开关（admin） ──` 之间插入：

```js
// ── 抑制名单 ────────────────────────────────────────────

const suppressions = ref([])
const suppressionLoading = ref(false)

const fetchSuppressions = async () => {
  suppressionLoading.value = true
  try {
    const data = await eiaLexiconApi.listSuppressions()
    suppressions.value = data.items
  } catch {
    /* 抑制名单加载失败不打断主列表 */
  } finally {
    suppressionLoading.value = false
  }
}

const supAdd = reactive({
  open: false,
  submitting: false,
  candidatesLoading: false,
  candidates: [],
  key: null,
  reason: ''
})

const candidateOptions = computed(() =>
  supAdd.candidates.map((c, i) => ({
    value: i,
    label: `${stageLabel(c.stage)} · ${c.caliber}${c.unit ? ` (${c.unit})` : ''}`
  }))
)

// 候选下拉过滤：value 是索引，show-search 须自定义 filter-option 按 label 匹配
const filterCandidate = (input, option) => option.label.toLowerCase().includes(input.toLowerCase())

const openSupAdd = async () => {
  supAdd.key = null
  supAdd.reason = ''
  supAdd.open = true
  supAdd.candidatesLoading = true
  try {
    const data = await eiaLexiconApi.getScanCandidates()
    supAdd.candidates = data.items
  } catch (e) {
    message.error(e?.message || '候选加载失败')
  } finally {
    supAdd.candidatesLoading = false
  }
}

const onSupAddSubmit = async () => {
  if (supAdd.key === null) {
    message.warning('请选择被抑制指纹')
    return
  }
  const c = supAdd.candidates[supAdd.key]
  supAdd.submitting = true
  try {
    await eiaLexiconApi.addSuppression({
      stage: c.stage,
      caliber: c.caliber,
      unit: c.unit,
      reason: supAdd.reason.trim()
    })
    message.success(`已登记抑制：${c.caliber}`)
    supAdd.open = false
    await fetchSuppressions()
  } catch (e) {
    message.error(e?.message || '登记失败')
  } finally {
    supAdd.submitting = false
  }
}

const onWithdraw = (row) => {
  Modal.confirm({
    title: `撤回抑制「${row.caliber}」？`,
    content:
      '撤回后该旧指纹不再屏蔽：若仍在语料中，重扫将重新导入（A 类直接回已入选）；对应改名条目的语境回落也随之失效。',
    okText: '确定撤回',
    cancelText: '取消',
    onOk: async () => {
      try {
        await eiaLexiconApi.withdrawSuppression(row.id)
        message.success(`已撤回抑制：${row.caliber}`)
        await fetchSuppressions()
      } catch (e) {
        message.error(e?.message || '撤回失败')
      }
    }
  })
}
```

- [ ] **Step 5: LexiconPanel.vue——刷新接线（3 处）**

① `onImport` 内 `await fetchList()` 之后加一行：`fetchSuppressions()`
② `onRenameSubmit` 内 `await fetchList()` 之后加一行：`fetchSuppressions()`（改名隐式登记抑制行）
③ `onMounted` 改为：

```js
onMounted(() => {
  fetchList()
  fetchSwitches()
  fetchSuppressions()
})
```

- [ ] **Step 6: LexiconPanel.vue——样式**

在 scoped style 块末尾（`.skip-list` 规则之后、`</style>` 之前）追加：

```less
/* ── 抑制名单卡 ── */
.sup-fp,
.sup-new,
.sup-reason {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sup-fp {
  max-width: 260px;
}

.sup-new {
  max-width: 200px;
}

.sup-empty {
  padding: 24px 20px;
  color: var(--color-text-tertiary);
  font-size: 13px;
  text-align: center;
}

.dim-cell {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.sup-form {
  .fld {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 12px;

    label {
      font-size: 12px;
      color: var(--color-text-secondary);

      em {
        font-style: normal;
        color: var(--color-text-tertiary);
      }
    }
  }
}
```

（`.mono`/`.card-hd`/`.hd-sub`/`.hd-right`/`.tbl`/`.tbl-foot`/`.missing-unit`/`.withdraw-btn` 均为既有类，直接复用。）

- [ ] **Step 7: prettier + sync + 容器 eslint**

```bash
cd web && node node_modules/prettier/bin/prettier.cjs --write src/apis/eia_lexicon_api.js src/components/eia-data/LexiconPanel.vue && cd ..
powershell.exe -NoProfile -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-web-1 sh -c "cd /app && ./node_modules/.bin/eslint src/apis/eia_lexicon_api.js src/components/eia-data/LexiconPanel.vue"
```

Expected: prettier 无 diff 报错；eslint 0 error 0 warning。

- [ ] **Step 8: Commit**

```bash
git add web/src/apis/eia_lexicon_api.js web/src/components/eia-data/LexiconPanel.vue
git commit -m "feat(domain-factory): 词表页抑制名单卡——列表/添加弹窗/撤回确认

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 真实栈 QA（只读）+ changelog

**Files:**
- Modify: `docs/develop-guides/changelog.md`（v0.7.3「功能与修复」组追加一条）

- [ ] **Step 1: 只读 QA（chrome-devtools MCP，isolatedContext，绝不写数据）**

登录（admin 账号，凭据仅会话内使用）→ navigate `http://localhost:5173/domain-factory/eia-data/lexicon`，验证：
1. 词条表下方出现「抑制名单」卡，种子 7 条可见（created_at 倒序）；指纹 mono 截断 + tooltip；手工/种子行「改名目标」若为空显示「—」
2. 「添加抑制」→ 弹窗下拉列出扫描候选差集（不含已入库词条与已抑制指纹，如「水平达标率」不应出现）→ **取消，不提交**
3. 任一行「撤回抑制」→ 确认弹窗文案含两条后果（重扫复活含 A 类直接回已入选 / 语境回落失效）→ **取消，不确认**
4. 暗色：`localStorage.setItem('theme','dark')` + reload，重验 1-3 截图存 `.wolf/`（不跟踪）

导入/改名后的抑制卡刷新接线不点击验证（导入会真写词条表）——该链路由 Task 4 代码审查与 Task 2 单测覆盖，QA 严格 GET-only。

Expected: 亮暗两态无样式破损；两个弹窗文案正确；全程未新增/删除抑制行。

- [ ] **Step 2: changelog 补条**

`docs/develop-guides/changelog.md` v0.7.3「功能与修复」组追加：

```markdown
- 词表页新增抑制名单卡（bug-4028）：列表 / 手工添加（扫描差集候选下拉，服务端强校验拒绝语料外指纹）/ 撤回（确认弹窗明示重扫复活与语境回落失效两条后果）；新增 `/eia/lexicon/suppressions`、`/eia/lexicon/scan-candidates` 4 端点与 repo/service 对应方法
```

（若实施中产生新 bug 修复，按实际编号替换 bug-4028。）

- [ ] **Step 3: Commit**

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(domain-factory): changelog 补充抑制名单 UI

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 红线（执行者必读）

1. **绝不运行** `backend/test/integration/services/test_eia_lexicon_service_flow.py`——它清空 `eia_lexicon_entries` 表；运行栈是真实数据。
2. **真实栈 QA 全程只读**：添加/撤回弹窗只开不提交；生产库严禁 seed。
3. 容器内一切验证前先 `sync-dev.ps1`；eslint 在 sync **之后**跑。
4. `.wolf/` 截图不进 git；提交只 add 计划列出的文件，禁止 `git add .wolf`。
5. 不 push，除非用户明确指示。
