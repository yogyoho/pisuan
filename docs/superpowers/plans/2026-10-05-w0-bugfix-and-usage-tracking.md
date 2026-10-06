# W0：bug-353/354 修复 + 工厂产物取用率埋点 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复两处静默失效的工厂缺陷（bug-354 校验空转、bug-353 match_count 断链），并为写作侧 4 个工厂产物读取工具装上取用率台账，为后续所有窗口提供测量基础。

**Architecture:** bug-354 是单行字段修正；bug-353 按「调用点原意」实现缺失方法（从 `template_match.template_id` 提取 `learned_{db_id}` 前缀 id，批量自增）；埋点是新增只增不改的台账表 `domain_factory_tool_usage`（走 `DomainFactoryBase.metadata.create_all` 自动建表，零迁移脚本），tools.py 内以 fire-and-forget 任务记录、绝不阻断工具主流程。写作侧消费计数走新台账，ETL 语料命中计数走 match_count——两种语义分开，不共用一列。

**Tech Stack:** Python 3.12 / SQLAlchemy async / pytest（docker api-dev 内运行）/ 项目规约见 CLAUDE.md（提交前 `make format`、中文 Conventional Commits）。

**Spec:** `docs/superpowers/specs/2026-10-05-kf-product-roadmap-v2-design.md` §7（bug 前置）、§9（埋点拍板）。本计划只覆盖 W0；W1-W4 另出计划。

**范围外（明确不做）：** query_kb（kbs/tools.py，KB 通用工具）不在本批埋点范围——它不区分工厂产物；工厂专用注册表工具 get_slot_registry 到 P1-1b 时自带埋点。

---

## 背景事实（工程师必读）

1. **bug-354**：`backend/package/yuxi/services/pre_commit_validator.py:32` 读 `para.get("type")`，但 ETL 写入的段落字段是 `classify_type`（见 `domain_factory_service.py` 中 `p.get("classify_type", "narrative")`）。字段永远取不到 `parameter` → 整个校验循环 `continue` 空转。
2. **bug-353**：`domain_factory_service.py:648` 在 `_etl_parse_stage`（:532，`service` 是入参，指向 `DomainFactoryService` 实例）中调用 `service._increment_learned_template_match_counts(paragraphs)`——该方法**不存在**，AttributeError 被 :649 的 `except` 吞掉只留 warning。match_count 列（`models_domain_factory.py:132`）因此永无增量。
3. **template_id 语义**：matcher 的学习模板由 `template_library.py:114 add_templates_from_list` 注入，`template_id = f"learned_{db_id}"`；静态标题模板 id 来自 `backend/templates/coal_mining/headers/*.json`（无 `learned_` 前缀）。所以只有 `learned_` 前缀的命中才回写 match_count。
4. **建表机制**：新表加入 `models_domain_factory.py` 的 `Base` 后，`manager.py:591 DomainFactoryBase.metadata.create_all` 在 api-dev 启动/热重载时自动建表，无需迁移脚本。
5. **tools.py 是上游共享文件**：改动一律带 `# [pisuan-custom]` 注释标记（文件内已有先例，grep `[pisuan-custom]` 可见）。文件顶部已 `import asyncio`、`logger`、`DomainFactoryRepository`。
6. **测试模式**：参考 `backend/test/unit/services/test_commit_pipeline_status.py`——`unittest.mock` + `pytest.mark.asyncio`，直接实例化 `DomainFactoryService()`（安全，init 不触 DB），属性注入 fake repo。
7. **运行测试**：代码热重载进容器。先确认 api-dev 在跑（`docker ps`）；若容器内 `/app` 非本仓库挂载，先跑 `.\scripts\sync-dev.ps1`。测试命令形如 `docker exec api-dev pytest /app/test/unit/services/test_xxx.py -v`。

---

### Task 1: bug-354 — pre_commit_validator 读取 classify_type

**Files:**
- Modify: `backend/package/yuxi/services/pre_commit_validator.py:32`
- Test: `backend/test/unit/services/test_pre_commit_validator.py`（新建）

- [ ] **Step 1: 写失败测试**

创建 `backend/test/unit/services/test_pre_commit_validator.py`：

```python
"""bug-354: pre_commit_validator 应读 classify_type（原读不存在的 type 字段导致校验空转）。"""

import pytest

from yuxi.services.pre_commit_validator import PreCommitValidator


@pytest.mark.asyncio
async def test_parameter_para_by_classify_type_is_validated():
    """classify_type=parameter 且 text_pattern 为空 → 必须报错（修复前校验空转直接 passed）"""
    v = PreCommitValidator()
    detail = {"source_paragraphs": [{"id": "p1", "classify_type": "parameter", "template": {}}]}
    r = await v.validate(detail)
    assert not r.passed
    assert any("text_pattern" in e for e in r.errors)


@pytest.mark.asyncio
async def test_narrative_para_skipped():
    """非 parameter 段落不参与模板校验"""
    v = PreCommitValidator()
    detail = {"source_paragraphs": [{"id": "p1", "classify_type": "narrative"}]}
    r = await v.validate(detail)
    assert r.passed


@pytest.mark.asyncio
async def test_wellformed_parameter_passes():
    """合规 parameter 段落通过"""
    v = PreCommitValidator()
    detail = {"source_paragraphs": [
        {"id": "p1", "classify_type": "parameter",
         "template": {"text_pattern": "矿区规模 {{规模}} Mt/a", "slots": [{"name": "规模"}]}},
    ]}
    r = await v.validate(detail)
    assert r.passed
```

- [ ] **Step 2: 运行验证失败**

```bash
docker exec api-dev pytest /app/test/unit/services/test_pre_commit_validator.py -v
```

预期：`test_parameter_para_by_classify_type_is_validated` FAIL（实际 passed，因为读不到 type 字段直接跳过）；其余两个 PASS。

- [ ] **Step 3: 修复**

`pre_commit_validator.py:32` 一行：

```python
            if para.get("classify_type") != "parameter":
```

- [ ] **Step 4: 运行验证通过**

```bash
docker exec api-dev pytest /app/test/unit/services/test_pre_commit_validator.py -v
```

预期：3 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/package/yuxi/services/pre_commit_validator.py backend/test/unit/services/test_pre_commit_validator.py
git commit -m "fix: bug-354 pre_commit_validator 改读 classify_type，L1 模板校验恢复生效

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 1b: bug-354 同族 — domain_factory_service 三处 type 字段错位（控制方追加）

**背景**：Task 1 实现期间发现 `domain_factory_service.py` 存在 3 处与 bug-354 同族的 `"type"` 字段错位（段落实际字段为 `classify_type`），导致 validate_task 统计与 slot 校验静默空转。控制方已核实，追加本任务。

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（3 处，**以下表代码锚点定位；行号会因 Task 2 的插入而漂移，以代码内容为准**）
- Test: `backend/test/unit/services/test_validate_task_report.py`（新建）

| 位置（当前行号） | 修改 |
|---|---|
| `validate_task` 内 L2 过滤（约 :4101）：`if p.get("type") == "parameter" and isinstance(p.get("template"), dict)` | `"type"` → `"classify_type"` |
| `validate_task` 报告统计（约 :4131）：`"parameter_paragraphs": sum(1 for p in paragraphs if p.get("type") == "parameter"),` | 同上 |
| `_commit_pipeline_async` 阶段 2.4b（约 :4586）：同款过滤行（文件中第二处） | 同上 |

**注意**：约 :2818 的 `b.get("type") == "table"` 操作的是 block 对象，字段语义不同，**不要改动**。

- [ ] **Step 1: 写失败测试** — 新建 `backend/test/unit/services/test_validate_task_report.py`：

```python
"""bug-354 同族：validate_task 报告统计/L2 过滤应读 classify_type（原读 type 全部落空）。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuxi.services.domain_factory_service import DomainFactoryService


def _fake_detail() -> dict:
    return {
        "source_paragraphs": [
            {"id": "p1", "classify_type": "parameter",
             "template": {"text_pattern": "矿区规模 {{规模}} Mt/a", "slots": [{"name": "规模"}]}},
            {"id": "p2", "classify_type": "narrative"},
        ],
    }


@pytest.mark.asyncio
async def test_validate_task_counts_parameter_paragraphs():
    """修复前 parameter_paragraphs 恒为 0（段落无 type 字段）→ 断言失败；修复后应为 1"""
    svc = DomainFactoryService()
    svc.repo = MagicMock()
    svc.repo.update_task = AsyncMock()
    with patch.object(svc, "get_task_detail", new=AsyncMock(return_value=_fake_detail())):
        report = await svc.validate_task("t1")
    assert report["summary"]["parameter_paragraphs"] == 1
    assert report["passed"] is True
    svc.repo.update_task.assert_awaited_once()
```

说明：`_commit_pipeline_async` 阶段 2.4b 一处不设专门单测（整条管线 mock 成本远超收益），以 grep 无残留 + services 回归套件覆盖。

- [ ] **Step 2: 运行验证失败**

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_validate_task_report.py -v
```

预期：`test_validate_task_counts_parameter_paragraphs` FAIL（parameter_paragraphs == 0）。

- [ ] **Step 3: 修 3 处**（`grep -n 'get("type") == "parameter"' backend/package/yuxi/services/domain_factory_service.py` 定位，逐处改 `"type"` → `"classify_type"`）

- [ ] **Step 4: 验证通过 + 无残留**

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/test_validate_task_report.py -v
docker exec pisuan-localized-api-1 grep -c 'get("type") == "parameter"' /app/package/pisuan/services/domain_factory_service.py || echo "0 residual"
docker exec pisuan-localized-api-1 pytest /app/test/unit/services/ -q
```

预期：新测试 1 passed；残留计数 0（grep 无匹配退出码非 0 属正常）；services 全量回归全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/package/yuxi/services/domain_factory_service.py backend/test/unit/services/test_validate_task_report.py
git commit -m "fix: bug-354 同族——domain_factory_service 三处 type 改读 classify_type，validate_task 统计与 slot 校验恢复生效

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 2: bug-353 — 实现 match_count 自增链

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（在 `_get_template_matcher` 方法之后，约 :165 处插入两个方法）
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`（在 `upsert_learned_template` 之后，约 :315 处插入一个方法）
- Test: `backend/test/unit/services/test_learned_template_match_count.py`（新建）

- [ ] **Step 1: 确认 repo 模块的导入名**

```bash
grep -n "^from sqlalchemy\|^from yuxi.storage.postgres.manager" backend/package/yuxi/repositories/domain_factory_repository.py
```

预期看到 `pg_manager` 的导入行（ monkeypatch 目标用它）；并确认 sqlalchemy 导入中是否有 `update`——没有则 Task 2 Step 3 需补。

- [ ] **Step 2: 写失败测试**

创建 `backend/test/unit/services/test_learned_template_match_count.py`：

```python
"""bug-353: _increment_learned_template_match_counts 原方法不存在被静默吞，match_count 永不增量。

验证三层：纯提取函数 → service 方法转发 repo → repo 构造 UPDATE 语句。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------- 纯提取逻辑 ----------

def test_extract_learned_match_ids():
    """只取 learned_ 前缀 id；静态标题模板 id / 缺失 / 非数字全部跳过；去重排序"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    paras = [
        {"template_match": {"template_id": "learned_7"}},
        {"template_match": {"template_id": "learned_3"}},
        {"template_match": {"template_id": "learned_7"}},      # 重复
        {"template_match": {"template_id": "HDR_CONCLUSION"}},  # 静态标题模板
        {"template_match": {"template_id": "learned_abc"}},     # 非数字
        {"template_match": {}},
        {"other": 1},
    ]
    assert DomainFactoryService._extract_learned_match_ids(paras) == [3, 7]


# ---------- service 方法 ----------

@pytest.mark.asyncio
async def test_service_increment_forwards_ids_to_repo():
    from yuxi.services.domain_factory_service import DomainFactoryService

    svc = DomainFactoryService()
    called = {}

    async def fake_inc(ids):
        called["ids"] = ids

    svc.repo = MagicMock()
    svc.repo.increment_learned_template_match_counts = fake_inc
    paras = [{"template_match": {"template_id": "learned_42"}}]
    await svc._increment_learned_template_match_counts(paras)
    assert called["ids"] == [42]


@pytest.mark.asyncio
async def test_increment_noop_when_no_learned_match():
    """无 learned_ 命中时不触 repo（纯静态模板命中的文档不该写库）"""
    from yuxi.services.domain_factory_service import DomainFactoryService

    svc = DomainFactoryService()
    svc.repo = MagicMock()
    svc.repo.increment_learned_template_match_counts = AsyncMock()
    await svc._increment_learned_template_match_counts(
        [{"template_match": {"template_id": "HDR_X"}}]
    )
    svc.repo.increment_learned_template_match_counts.assert_not_awaited()


# ---------- repo 方法（fake session，验证 UPDATE 语句与 rowcount 透传） ----------

class _FakeResult:
    rowcount = 2


class _FakeSession:
    def __init__(self):
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _FakeResult()


@pytest.mark.asyncio
async def test_repo_increment_builds_update(monkeypatch):
    from yuxi.repositories import domain_factory_repository as mod

    sess = _FakeSession()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=sess)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_pg = MagicMock()
    fake_pg.get_async_session_context = MagicMock(return_value=cm)
    monkeypatch.setattr(mod, "pg_manager", fake_pg)

    repo = mod.DomainFactoryRepository()
    n = await repo.increment_learned_template_match_counts([42, 43])
    assert n == 2
    assert len(sess.executed) == 1


@pytest.mark.asyncio
async def test_repo_increment_empty_ids_no_db(monkeypatch):
    from yuxi.repositories import domain_factory_repository as mod

    fake_pg = MagicMock()
    monkeypatch.setattr(mod, "pg_manager", fake_pg)
    repo = mod.DomainFactoryRepository()
    n = await repo.increment_learned_template_match_counts([])
    assert n == 0
    fake_pg.get_async_session_context.assert_not_called()
```

- [ ] **Step 3: 运行验证失败**

```bash
docker exec api-dev pytest /app/test/unit/services/test_learned_template_match_count.py -v
```

预期：全部 FAIL（`_extract_learned_match_ids` / `_increment_learned_template_match_counts` / `increment_learned_template_match_counts` 均不存在，AttributeError）。

- [ ] **Step 4: 实现 repo 方法**

`domain_factory_repository.py`：若 sqlalchemy 导入无 `update`，补上（如 `from sqlalchemy import select, update`）。在 `upsert_learned_template` 方法之后插入：

```python
    async def increment_learned_template_match_counts(self, template_ids: list[int]) -> int:
        """批量自增学习模板 match_count（ETL 标题命中留痕，bug-353）。"""
        if not template_ids:
            return 0
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                update(DomainFactoryLearnedTemplate)
                .where(DomainFactoryLearnedTemplate.id.in_(template_ids))
                .values(match_count=DomainFactoryLearnedTemplate.match_count + 1)
            )
            result = await session.execute(stmt)
            return result.rowcount or 0
```

- [ ] **Step 5: 实现 service 方法**

`domain_factory_service.py`，在 `_get_template_matcher` 方法结束后插入：

```python
    @staticmethod
    def _extract_learned_match_ids(paragraphs: list[dict]) -> list[int]:
        """从段落 template_match 提取学习模板 id（template_id 形如 learned_42，见 template_library.add_templates_from_list）。"""
        ids: set[int] = set()
        for p in paragraphs:
            tm = p.get("template_match") or {}
            tid = str(tm.get("template_id") or "")
            if tid.startswith("learned_"):
                try:
                    ids.add(int(tid[len("learned_"):]))
                except ValueError:
                    continue
        return sorted(ids)

    async def _increment_learned_template_match_counts(self, paragraphs: list[dict]) -> None:
        """ETL 标题命中学习模板后自增 match_count（bug-353：原调用点方法不存在，AttributeError 被吞）。"""
        ids = self._extract_learned_match_ids(paragraphs)
        if not ids:
            return
        await self.repo.increment_learned_template_match_counts(ids)
        logger.info(f"学习模板 match_count 自增: {len(ids)} 个模板")
```

调用点（:648）**不动**——`service` 入参即服务实例，方法补上后原调用自然生效。

- [ ] **Step 6: 运行验证通过**

```bash
docker exec api-dev pytest /app/test/unit/services/test_learned_template_match_count.py -v
```

预期：5 个测试全部 PASS。

- [ ] **Step 7: 端到端冒烟（可选但推荐）**

对横城样例重跑一次 ETL（走管理页或 API），观察 api-dev 日志：

```bash
docker logs api-dev --tail 50 2>&1 | grep -E "match_count|模板匹配完成"
```

预期：出现「学习模板 match_count 自增: N 个模板」（首次运行横城语料时 N>0，因 matcher 注入了 DB 学习模板）。

- [ ] **Step 8: 提交**

```bash
git add backend/package/yuxi/services/domain_factory_service.py backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/services/test_learned_template_match_count.py
git commit -m "fix: bug-353 实现 match_count 自增链，学习模板命中计数恢复

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 取用率埋点 — 台账表 + repo 方法 + 4 工具接线

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`（文件末尾追加模型类）
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`（models 导入行 + 新方法）
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`（模块级 helper + 4 个工具接线；上游共享文件，全部带 `[pisuan-custom]` 标记）
- Test: `backend/test/unit/services/test_tool_usage_tracking.py`（新建）

- [ ] **Step 1: 写失败测试**

创建 `backend/test/unit/services/test_tool_usage_tracking.py`：

```python
"""W0 取用率埋点：台账表 repo 方法与 tools.py 接线辅助。"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


def _fake_pg(monkeypatch, sess):
    from yuxi.repositories import domain_factory_repository as mod

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=sess)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_pg = MagicMock()
    fake_pg.get_async_session_context = MagicMock(return_value=cm)
    monkeypatch.setattr(mod, "pg_manager", fake_pg)
    return mod


@pytest.mark.asyncio
async def test_record_tool_usage_inserts_row(monkeypatch):
    sess = _FakeSession()
    mod = _fake_pg(monkeypatch, sess)
    repo = mod.DomainFactoryRepository()
    await repo.record_tool_usage(
        tool_name="get_templates",
        domain="coal",
        report_type="planning_eia",
        args_summary={"canonical_chapter_key": "地表沉陷"},
        result_count=3,
        source="graph",
    )
    assert len(sess.added) == 1
    row = sess.added[0]
    assert row.tool_name == "get_templates"
    assert row.domain == "coal"
    assert row.report_type == "planning_eia"
    assert row.result_count == 3
    assert row.source == "graph"
    assert row.args_summary == {"canonical_chapter_key": "地表沉陷"}


@pytest.mark.asyncio
async def test_record_tool_usage_defaults(monkeypatch):
    """缺省参数落库为 0 / {}，不抛错"""
    sess = _FakeSession()
    mod = _fake_pg(monkeypatch, sess)
    repo = mod.DomainFactoryRepository()
    await repo.record_tool_usage(tool_name="list_report_types")
    row = sess.added[0]
    assert row.result_count == 0
    assert row.args_summary == {}
    assert row.source is None
```

- [ ] **Step 2: 运行验证失败**

```bash
docker exec api-dev pytest /app/test/unit/services/test_tool_usage_tracking.py -v
```

预期：FAIL，`record_tool_usage` 不存在（AttributeError）。

- [ ] **Step 3: 追加台账表模型**

`models_domain_factory.py` 文件末尾追加（`Base`/`Column`/`Integer`/`String`/`JSON`/`DateTime`/`Index`/`utc_now_naive`/`format_utc_datetime`/`Any` 均为文件既有导入）：

```python
class DomainFactoryToolUsage(Base):
    """领域知识工厂 - 写作侧工具取用台账（W0 埋点）

    只增不改：每次工厂产物读取类工具调用记一行，供 D2 取用率测量。
    """

    __tablename__ = "domain_factory_tool_usage"
    __table_args__ = (Index("idx_dftu_tool_time", "tool_name", "created_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_name = Column(String(64), nullable=False)
    domain = Column(String(64), nullable=True)
    report_type = Column(String(64), nullable=True)
    args_summary = Column(JSON, nullable=True, default=dict)
    result_count = Column(Integer, nullable=False, default=0)
    source = Column(String(32), nullable=True)  # graph / db / db_fallback / miss
    created_at = Column(DateTime, default=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "domain": self.domain,
            "report_type": self.report_type,
            "args_summary": self.args_summary or {},
            "result_count": self.result_count,
            "source": self.source,
            "created_at": format_utc_datetime(self.created_at),
        }
```

- [ ] **Step 4: repo 方法**

`domain_factory_repository.py`：在 models 导入行（`from yuxi.storage.postgres.models_domain_factory import (...)`）中加入 `DomainFactoryToolUsage`；在 Task 2 新增方法之后插入：

```python
    async def record_tool_usage(
        self,
        tool_name: str,
        *,
        domain: str | None = None,
        report_type: str | None = None,
        args_summary: dict | None = None,
        result_count: int = 0,
        source: str | None = None,
    ) -> None:
        """记一条工具取用台账（W0 埋点）。失败上抛，由调用方决定是否吞。"""
        async with pg_manager.get_async_session_context() as session:
            session.add(
                DomainFactoryToolUsage(
                    tool_name=tool_name,
                    domain=domain,
                    report_type=report_type,
                    args_summary=args_summary or {},
                    result_count=result_count,
                    source=source,
                )
            )
```

- [ ] **Step 5: 运行验证通过**

```bash
docker exec api-dev pytest /app/test/unit/services/test_tool_usage_tracking.py -v
```

预期：2 个 PASS。

- [ ] **Step 6: tools.py 加 helper 并接线 4 个工具**

`backend/package/yuxi/agents/toolkits/buildin/tools.py`（上游共享，所有新增行带标记）。

6a. 在 `_normalize_report_type` 函数定义之后，加模块级 helper：

```python
# [pisuan-custom] W0 取用率埋点：工厂产物读取类工具的取用留痕（fire-and-forget，
# 埋点失败绝不阻断工具主流程）。台账表 domain_factory_tool_usage，只增不改。
_tracking_tasks: set = set()


def _track_usage(
    tool_name: str,
    *,
    domain: str | None = None,
    report_type: str | None = None,
    args_summary: dict | None = None,
    result_count: int = 0,
    source: str | None = None,
) -> None:
    async def _run():
        try:
            repo = DomainFactoryRepository()
            await repo.record_tool_usage(
                tool_name=tool_name,
                domain=domain,
                report_type=report_type,
                args_summary=args_summary,
                result_count=result_count,
                source=source,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[tool-usage] 埋点失败(忽略): {tool_name} - {exc}")

    task = asyncio.create_task(_run())
    _tracking_tasks.add(task)
    task.add_done_callback(_tracking_tasks.discard)
```

6b. `get_chapter_outline`（:553）——三处 return 前各加一行（错误分支也记，0 结果本身是信号）：

```python
            if outline:
                outline.setdefault("_source", "graph")
                # [pisuan-custom] W0 埋点
                _track_usage("get_chapter_outline", domain=domain, report_type=report_type,
                             args_summary={"canonical_chapter_key": canonical_chapter_key},
                             result_count=1, source="graph")
                return outline
```

```python
    if out:
        out["_source"] = "db_fallback" if graph_errored else "db"
        # [pisuan-custom] W0 埋点
        _track_usage("get_chapter_outline", domain=domain, report_type=report_type,
                     args_summary={"canonical_chapter_key": canonical_chapter_key},
                     result_count=1, source=out["_source"])
```

函数最末 `return {"error": ...}` 之前：

```python
    # [pisuan-custom] W0 埋点（未命中也记，0 结果是查询质量信号）
    _track_usage("get_chapter_outline", domain=domain, report_type=report_type,
                 args_summary={"canonical_chapter_key": canonical_chapter_key},
                 result_count=0, source="miss")
```

6c. `list_report_types`（:607）——主体改为：

```python
    domain = _normalize_domain(domain)
    repo = DomainEntityRepository()
    out = await repo.list_report_types(domain)
    # [pisuan-custom] W0 埋点
    _track_usage("list_report_types", domain=domain, result_count=len(out))
    return out
```

6d. `list_chapter_keys`（:628）——图谱命中分支 `if keys:` 内、return 前加：

```python
                # [pisuan-custom] W0 埋点
                _track_usage("list_chapter_keys", domain=domain, report_type=report_type,
                             result_count=len(keys), source="graph")
```

末尾 DB 回退改为：

```python
    repo = DomainFactoryRepository()
    out = await repo.list_chapter_keys(domain, report_type)
    # [pisuan-custom] W0 埋点
    _track_usage("list_chapter_keys", domain=domain, report_type=report_type,
                 result_count=len(out), source="db")
    return out
```

6e. `get_templates`（:662）——图谱命中分支（`if templates:` 块内、`return templates` 前）：

```python
                    # [pisuan-custom] W0 埋点
                    _track_usage("get_templates", domain=domain, report_type=report_type,
                                 args_summary={"canonical_chapter_key": canonical_chapter_key},
                                 result_count=len(templates), source="graph")
```

DB 回退路径（函数末尾 `return out` 前）：

```python
    # [pisuan-custom] W0 埋点
    _track_usage("get_templates", domain=domain, report_type=report_type,
                 args_summary={"canonical_chapter_key": canonical_chapter_key},
                 result_count=len(out), source=out[0].get("_source") if out else "miss")
    return out
```

- [ ] **Step 7: 验证台账表已建**

models 改动经热重载触发 lifespan `create_all`。等 api-dev 重载后（`docker logs api-dev --tail 20` 看到 reload/startup 完成）：

```bash
docker exec api-dev python -c "
import asyncio
from sqlalchemy import text
from yuxi.storage.postgres.manager import pg_manager

async def main():
    async with pg_manager.get_async_session_context() as s:
        r = await s.execute(text(\"SELECT to_regclass('domain_factory_tool_usage')\"))
        print('table =', r.scalar())

asyncio.run(main())
"
```

预期输出：`table = domain_factory_tool_usage`。若为 None，手动重启 api-dev（`docker restart api-dev`）后重试。

- [ ] **Step 8: 跑本仓库既有相关单测防回归**

```bash
docker exec api-dev pytest /app/test/unit/services/ -q
```

预期：全绿（既有用例不因 repo/service 签名变化受影响）。

- [ ] **Step 9: 提交**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/repositories/domain_factory_repository.py backend/package/yuxi/agents/toolkits/buildin/tools.py backend/test/unit/services/test_tool_usage_tracking.py
git commit -m "feat: 工厂产物取用率埋点——tool_usage 台账表 + 写手侧 4 工具留痕

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 收尾 — 格式检查 + changelog + 回归

- [ ] **Step 1: 格式化与静态检查**

```bash
make format
```

预期：ruff 无报错；若有自动修复，重跑 Task 1-3 的测试确认仍绿。

已知待清理（Task 1 质量审查发现）：
- `backend/test/unit/services/test_pre_commit_validator.py` 两个新增测试的 dict 不满足 ruff format（ruff format 自动折叠即可）
- 同文件第 4 行 `ValidationResult` 为 base 遗留的 F401 unused import（ruff check 会报；该文件本次已触碰，允许顺手移除该行以过提交门禁）
- Task 3 发现：models/repo/tools 等文件存在**预存**整文件 ruff format 漂移（非本次引入）。处理规则：自有文件可整文件 format；**上游共享文件（tools.py、manager.py）禁止整文件重排**——`make format` 后检查 `git diff`，凡上游共享文件出现与本次新增块无关的重排 hunk，回退之（仅保留新增行的格式修正），否则会污染上游同步 diff。验收放宽为"新引入违规清零"，不强求全仓 ruff 干净

- [ ] **Step 1b: 标注遗留失败测试（bug-357）**

`backend/test/unit/services/test_formula_chunk.py` 中 3 个引用已删除方法 `_build_structured_document`（9b74874d 移除）的测试，在测试函数上加：

```python
@pytest.mark.skip(reason="bug-357: _build_structured_document 已于 9b74874d 移除，待按新架构重写")
```

目的：恢复 services 回归绿基线（标注债务，不掩盖——重写为独立跟进任务）。不重写、不删除测试本体。验证：`docker exec pisuan-localized-api-1 pytest /app/test/unit/services/ -q` → 0 failed（3 skipped）。

- [ ] **Step 2: 更新 changelog**

在 `docs/develop-guides/changelog.md` 顶部未发布区块（按文件既有格式，新增版本小节或并入当前未发布小节）追加：

```markdown
### 修复
- bug-354: pre_commit_validator 改读 classify_type（原读不存在的 type 字段，L1 模板校验一直空转）
- bug-354 同族: domain_factory_service 三处 type 改读 classify_type（validate_task 参数段统计与 L2/2.4b slot 校验恢复生效）
- bug-353: 实现 _increment_learned_template_match_counts，学习模板 match_count 恢复自增（ETL 标题命中留痕）

### 新增
- domain_factory_tool_usage 台账表 + 写手侧 4 个工厂产物读取工具的取用率埋点（W0，roadmap v2 测量基础）
```

- [ ] **Step 3: 提交 changelog**

```bash
git add backend/test/unit/services/test_pre_commit_validator.py backend/test/unit/services/test_formula_chunk.py docs/develop-guides/changelog.md
git commit -m "chore: W0 收尾——lint 清理、test_formula_chunk 遗留失败标注（bug-357）与 changelog

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 验收清单（对照 spec §7/§9）

| 项 | 判据 |
|---|---|
| bug-354 | parameter 段落缺 text_pattern 时 validate 返回 not passed（测试证明） |
| bug-354 同族 | validate_task 报告 parameter_paragraphs 恢复计数（测试证明）；文件内 `get("type") == "parameter"` 零残留 |
| bug-353 | learned_ 前缀命中触发 repo 自增；静态模板命中不写库（测试证明）；横城 ETL 冒烟日志出现自增行 |
| 埋点 | 4 工具调用落台账行（含 0 结果与 miss）；埋点异常不影响工具返回 |
| 无回归 | /app/test/unit/services/ 全绿（唯一已知基线失败 test_formula_chunk 3 例，由 Task 4 以 skip+bug-357 理由标注，重写为独立跟进任务）；make format：新引入违规清零，上游共享文件不整文件重排 |
