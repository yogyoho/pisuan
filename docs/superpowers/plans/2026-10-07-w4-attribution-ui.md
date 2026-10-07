# W4 归属管理 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识工厂新增「归属管理」tab——任务归属可视可改（逐行改判级联）、区域事实可筛可退（admin 批量退役）、聚合看板可读（统计卡+明细+区域下钻树），并补齐行政区辅助词表 3+6 条（W3 终审挂账②）。

**Architecture:** 后端三薄 GET（router→service→repository，W3 分层，零 DDL）；前端单面板组件 `RegionAttributionPanel`（容器内三子 tab），挂载为 `DomainFactoryView` 第三 tab（纯增量）。行政区词表落在 `domain_factory_region.py` 作 L1 二级查找——主词表（矿区名）优先，段落级 `extract_region_signal` 零改动（classify 行为不变的根基）。

**Tech Stack:** FastAPI + SQLAlchemy(async) + PostgreSQL；Vue 3 `<script setup>` + ant-design-vue + Pinia；测试走容器道（`docker run` ro-mount `--noconftest`）+ 运行栈 `docker exec` live 验证。

**Spec:** [2026-10-07-w4-attribution-ui-design.md](../specs/2026-10-07-w4-attribution-ui-design.md)（Q1-Q6 已裁决，commit 5b3bd8ba）

---

## 全局约束（每个任务的执行者必读）

1. **提交纪律**：中文 Conventional Commits；只 `git add <明确文件>`，**禁止 `git add -A` / `git add .` / `git stash`（任何变体）**；提交信息末尾带 `Co-Authored-By: Claude Code <noreply@anthropic.com>`（heredoc 传参防转义）。
2. **单测容器道**（worktree 即改即测，无需 sync）：

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/<测试文件> --noconftest -q
```

   宿主缺依赖不可宿主 pytest；docker `-v` 用正斜杠盘符路径。单测是纯函数/fake repo，无需 DB，文件头带同款容器命令注释（先例 `backend/test/unit/test_w3_facts_flow.py`）。
3. **docker 命令含宿主路径参数**必须加 `MSYS_NO_PATHCONV=1` 前缀（Git Bash 路径改写）。
4. **运行栈容器**：`pisuan-localized-api-1` / `pisuan-localized-postgres-1` / web 容器（端口 `docker ps` 查）；容器内包名 `pisuan.*`（worktree 为 `yuxi.*`）。worktree 代码进运行栈靠 `./scripts/sync-dev.ps1`（PowerShell）。**本计划 sync-dev 只在 T2 Step 2.6 与 T3/T4/T5 各自收尾步执行，勿提前**。
5. **不变量**（用户硬约束）：**现有知识工厂功能零行为改动**——EtlWorkbench/DataSourceDashboard/confirm-entities 流不动；`DomainFactoryView.vue` 新增触点仅 3 处：1 行 import + 1 个 a-tab-pane + 1 行 `.tab-dot.region` 配色（spec 原文写「仅 2 行增量」，实况 tab 图标是 CSS 圆点非 lucide 图标，需 1 行配色——T6 同步勘误 spec §2/§4.1/DoD7，勿自行扩触点）；classify_tags 与 W3 归属主词表（REGION_VOCAB 17 条）语义零变动（`extract_region_signal` 只许重构为同语义委托，旧用例必须零改动全绿）；**本窗零 DDL**；禁碰 `web/src/views/HomeView.vue`、`LoginView.vue`、`web/src/assets/css/base.css*`、`backend/package/*/config/static/info.template.yaml`。
6. **既有行为基线**：`test_w1_prose_pipeline.py`（26 例）+ `test_w3_region_rules.py` / `test_w3_scope_pipeline.py` / `test_w3_facts_flow.py`（共 50 例）全绿是硬门槛（凡改动 `domain_factory_service.py` / `domain_factory_region.py` 的任务收尾必须复跑）。
7. **中文 printf/echo 有编码风险**：向 `.wolf/` 追加中文一律写 python 脚本文件再运行（不依赖控制台输出）。
8. **凭据红线**：admin 凭据不在 .env——**不发 HTTP 登录请求、不回显任何 API key**；live 验证一律 `docker exec` 进容器直调 service/repository（W3 T5.4 先例）。
9. **retire 不可逆**（status→retired 无恢复通道）：任何冒烟**不得对真实事实行执行退役**；退役实链验证只允许对合成数据（T2 Step 2.7 自清理）。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/package/yuxi/services/domain_factory_region.py` | 改 | T1：+`region_label_for_key`/`derive_template_region` 纯函数；T2：+`ADMIN_REGION_VOCAB`（9 条）、`extract_region_signal` 重构为同语义委托 `_longest_vocab_hit`、+`extract_admin_region_signal`、`l1_task_attribution` 二级查找 |
| `backend/package/yuxi/repositories/domain_factory_repository.py` | 改 | T1：类末 +3 读方法（任务归属分页列表 / 区域事实分页列表 / 看板聚合原始数据） |
| `backend/package/yuxi/services/domain_factory_service.py` | 改 | T1：region import +2、`_reaggregate_templates_for_task` 后 +3 读 service 函数 |
| `backend/server/routers/domain_factory_router.py` | 改 | T1：`retire_regional_facts`（:415）后 +3 薄 GET |
| `backend/test/unit/test_w4_attribution_reads.py` | 新 | T1：派生纯函数 + service 读函数（fake repo）单测 |
| `backend/test/unit/test_w4_admin_vocab.py` | 新 | T2：9 命中/4 排除/主命中优先/回归钉 单测 |
| `web/src/apis/domain_factory_api.js` | 改 | T3：`confirmProposedEntities` 后 +5 方法 |
| `web/src/components/domain-factory/RegionAttributionPanel.vue` | 新 | T3：容器，三子 tab（任务归属/区域事实/模板聚合），看板跳转接线 |
| `web/src/components/domain-factory/AttributionTaskTable.vue` | 新 | T3：子页1 筛选+表格+逐行改判入口 |
| `web/src/components/domain-factory/AttributionEditModal.vue` | 新 | T3：改判弹窗（label 必填/key slug 校验/scope 三选/级联警示） |
| `web/src/components/domain-factory/RegionalFactsTable.vue` | 新 | T4：子页2 三重筛选 + admin 勾选批量退役 |
| `web/src/components/domain-factory/RegionBoard.vue` | 新 | T5：子页3 统计卡+明细表+区域下钻树 |
| `web/src/views/DomainFactoryView.vue` | 改 | T3：+1 import、+1 a-tab-pane(key="region")、+1 行 tab-dot 配色 |
| `docs/develop-guides/changelog.md` | 改 | T6：W4 条目 |
| `docs/superpowers/specs/2026-10-07-w4-attribution-ui-design.md` | 改 | T6：三处勘误（tab 触点数/tab 图标实况/board 响应补 `templates` 数组） |

执行序：T1→T2→T3→T4→T5→T6 串行（spec §5 的 T2∥T3 并行能力不用于本计划，按序执行避免同文件竞争）。

---

### Task 1: 后端读接口三件套（纯函数 + repository + service + router + 单测）

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_region.py`（:66 `region_key_for_label` 后 +`region_label_for_key`；:130 `apply_min_permissive` 后 +`derive_template_region`）
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`（:911 文件末、类末方法 `get_task_scopes` :904 之后）
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（:20-29 import 块；:6508 `_reaggregate_templates_for_task` 之后）
- Modify: `backend/server/routers/domain_factory_router.py`（:415 `retire_regional_facts` 函数结束之后、:418 File Upload 分节注释之前）
- Test: `backend/test/unit/test_w4_attribution_reads.py`（新建）

- [ ] **Step 1.1: 基线快照（改动前）**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_region_rules.py /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w3_facts_flow.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 ruff check /app/package/yuxi/services/domain_factory_region.py /app/package/yuxi/services/domain_factory_service.py /app/package/yuxi/repositories/domain_factory_repository.py /app/server/routers/domain_factory_router.py
```

Expected: pytest 全绿（约 76 passed）；ruff 输出记录四文件告警计数（若镜像无 ruff，改用 `docker exec pisuan-localized-api-1 ruff check ...`，仍无则如实上报控制器，T6 以 ast 解析替代）。**记下这两个数字**，T6 对比。

- [ ] **Step 1.2: 写失败单测**

新建 `backend/test/unit/test_w4_attribution_reads.py`，全文：

```python
# W4 归属管理读接口单测：region 纯函数派生 + service 读函数（fake repo，无 DB）。
# 验证走容器道：
# MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" \
#   pisuan-api:0.7.3 pytest /app/test/unit/test_w4_attribution_reads.py --noconftest -q
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_region import (  # noqa: E402
    derive_template_region,
    region_label_for_key,
)
from yuxi.services.domain_factory_service import DomainFactoryService  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class TestDeriveTemplateRegion:
    def test_single_region(self):
        assert derive_template_region(["t1", "t2"], {"t1": "hengcheng", "t2": "hengcheng"}) == "hengcheng"

    def test_mixed_regions(self):
        assert derive_template_region(["t1", "t2"], {"t1": "hengcheng", "t2": "yining-beiqu"}) == "mixed"

    def test_empty_or_all_null_returns_none(self):
        assert derive_template_region([], {"t1": "hengcheng"}) is None
        assert derive_template_region(["t1"], {"t1": None}) is None
        assert derive_template_region(None, {}) is None

    def test_null_evidence_not_participating(self):
        # 归因集中 region 为 NULL 的任务不参与派生（与 min-permissive 的 NULL 不参与同语义）
        assert derive_template_region(["t1", "t2"], {"t1": "hengcheng", "t2": None}) == "hengcheng"


class TestRegionLabelForKey:
    def test_primary_vocab_reverse(self):
        assert region_label_for_key("hengcheng") == "横城矿区"
        assert region_label_for_key("yining-beiqu") == "伊宁矿区北区"

    def test_unknown_returns_none(self):
        assert region_label_for_key("no-such-region") is None


class FakeReadRepo:
    """list/board 读接口最小 fake（只实现被测三方法，返回形状与真实 repo 契约一致）。"""

    def __init__(self):
        self.calls = []

    async def list_tasks_with_attribution(self, scope=None, region_key=None, keyword=None, page=1, page_size=20):
        self.calls.append(
            {"scope": scope, "region_key": region_key, "keyword": keyword, "page": page, "page_size": page_size}
        )
        return [{"id": "t1", "file_name": "x.docx"}], 1

    async def list_regional_facts(self, region_key=None, fact_type=None, status=None, page=1, page_size=20):
        self.calls.append(
            {"region_key": region_key, "fact_type": fact_type, "status": status, "page": page, "page_size": page_size}
        )
        return [{"id": 1, "source_task_file_name": "x.docx"}], 1

    async def get_region_board_raw(self):
        return {
            "tasks_by_region": [
                {"region_key": "hengcheng", "region_label": "横城矿区", "count": 2},
                {"region_key": None, "region_label": None, "count": 1},
            ],
            "facts_by_region_type_status": [
                {"region_key": "hengcheng", "fact_type": "monitoring", "status": "confirmed", "count": 3},
                {"region_key": "hengcheng", "fact_type": "measure", "status": "draft", "count": 1},
                {"region_key": None, "fact_type": "measure", "status": "draft", "count": 2},
            ],
            "templates_by_scope": {"": 5, "regional": 2},
            "task_regions": {"t1": "hengcheng", "t2": "hengcheng", "t3": "yining-beiqu"},
            "templates": [
                {
                    "id": 1,
                    "chapter": "ch9 措施",
                    "scope": "regional",
                    "contributing_task_ids": ["t1", "t3"],
                    "updated_at": "2026-10-06T00:00:00",
                },
                {
                    "id": 2,
                    "chapter": "ch3 现状",
                    "scope": None,
                    "contributing_task_ids": [],
                    "updated_at": "2026-10-07T00:00:00",
                },
            ],
        }


def make_svc() -> DomainFactoryService:
    svc = DomainFactoryService.__new__(DomainFactoryService)  # 跳过 __init__（W3 fake 先例）
    svc.repo = FakeReadRepo()
    return svc


class TestListTasksWithAttribution:
    def test_passthrough_and_clamp(self):
        svc = make_svc()
        res = run(svc.list_tasks_with_attribution(page=0, page_size=500, keyword="横城"))
        assert res["page"] == 1 and res["page_size"] == 100
        assert res["total"] == 1 and len(res["items"]) == 1
        assert svc.repo.calls[-1]["keyword"] == "横城"

    def test_unassigned_passthrough(self):
        svc = make_svc()
        run(svc.list_tasks_with_attribution(scope="unassigned"))
        assert svc.repo.calls[-1]["scope"] == "unassigned"

    def test_invalid_scope_rejected(self):
        svc = make_svc()
        assert run(svc.list_tasks_with_attribution(scope="bogus")).get("error")


class TestListRegionalFacts:
    def test_valid_filters_passthrough(self):
        svc = make_svc()
        res = run(svc.list_regional_facts(region_key="hengcheng", fact_type="measure", status="draft"))
        assert res["total"] == 1
        assert svc.repo.calls[-1] == {
            "region_key": "hengcheng",
            "fact_type": "measure",
            "status": "draft",
            "page": 1,
            "page_size": 20,
        }

    def test_invalid_fact_type_rejected(self):
        svc = make_svc()
        assert run(svc.list_regional_facts(fact_type="bogus")).get("error")

    def test_invalid_status_rejected(self):
        svc = make_svc()
        assert run(svc.list_regional_facts(status="bogus")).get("error")


class TestBuildRegionBoard:
    def test_stats_tree_and_templates(self):
        svc = make_svc()
        board = run(svc.build_region_board())
        s = board["stats"]
        assert s["templates_by_scope"] == {"universal": 0, "regional": 2, "project": 0, "unassigned": 5}
        assert s["facts_by_status"] == {"draft": 3, "confirmed": 3, "retired": 0}
        assert {r["region_key"]: r["count"] for r in s["tasks_by_region"]} == {"hengcheng": 2, None: 1}
        tree = {n["region_key"]: n for n in board["region_tree"]}
        assert tree["hengcheng"]["task_count"] == 2
        assert tree["hengcheng"]["fact_count"] == 4
        assert tree["hengcheng"]["fact_counts_by_type"]["monitoring"] == 3
        assert tree[None]["task_count"] == 1
        assert tree[None]["template_count"] == 1  # 模板2 无归因 → 未归属伪节点
        # mixed 模板（t1+t3 跨 region）进明细但不计入任何树节点
        tpl = {t["id"]: t for t in board["templates"]}
        assert tpl[1]["region"] == "mixed" and tpl[1]["contributing_count"] == 2
        assert tpl[2]["region"] is None
        assert [t for t in board["templates"] if t["region"] == "hengcheng"] == []
        # 明细按 updated_at 倒序
        assert board["templates"][0]["id"] == 2
```

- [ ] **Step 1.3: 跑单测验证失败**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w4_attribution_reads.py --noconftest -q
```

Expected: FAIL/ERROR — `ImportError: cannot import name 'derive_template_region'`。

- [ ] **Step 1.4: region 模块 +2 纯函数**

`backend/package/yuxi/services/domain_factory_region.py`——在 `region_key_for_label`（:66-68）之后插入：

```python
def region_label_for_key(key: str) -> str | None:
    """slug → 展示名（主词表反查优先，再查行政区辅助词表；查不到返回 None）。"""
    for name, k in REGION_VOCAB.items():
        if k == key:
            return name
    for name, k in ADMIN_REGION_VOCAB.items():
        if k == key:
            return name
    return None
```

（注意：`ADMIN_REGION_VOCAB` 在 Task 2 才落——本函数现阶段的第二段循环引用了未定义名。**T1 阶段先只写主词表反查段**，把 `ADMIN_REGION_VOCAB` 循环段留作 T2 Step 2.3 的一部分与常量同提交；即 T1 版本为：

```python
def region_label_for_key(key: str) -> str | None:
    """slug → 展示名（主词表反查；查不到返回 None）。"""
    for name, k in REGION_VOCAB.items():
        if k == key:
            return name
    return None
```
）

在文件末尾 `apply_min_permissive`（:130-136）之后追加：

```python
def derive_template_region(
    contributing_task_ids: list[str] | None, task_regions: dict[str, str | None]
) -> str | None:
    """[pisuan-custom] W4：模板 region 派生（LearnedTemplate 无 region 列，由归因集推出）。

    归因集任务的 region_key 去重非空——恰一个 → 该值；多个 → "mixed"；空集/全 NULL → None
    （显示「未归属」）。NULL 证据不参与，与 min-permissive 同语义。
    """
    keys = {task_regions.get(str(tid)) for tid in (contributing_task_ids or [])}
    keys.discard(None)
    if not keys:
        return None
    if len(keys) == 1:
        return next(iter(keys))
    return "mixed"
```

- [ ] **Step 1.5: repository +3 读方法**

`backend/package/yuxi/repositories/domain_factory_repository.py`——在类末方法 `get_task_scopes`（:904 起）之后、类体末尾追加：

```python
    # [pisuan-custom] W4 归属管理读接口（只读，零 DDL）

    async def list_tasks_with_attribution(
        self,
        scope: str | None = None,
        region_key: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """任务归属列表。scope='unassigned' 解释为 scope IS NULL，其余等值过滤；
        keyword 对 file_name 大小写不敏感模糊；created_at 倒序分页。"""
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            conditions = []
            if scope == "unassigned":
                conditions.append(DomainFactoryTask.scope.is_(None))
            elif scope:
                conditions.append(DomainFactoryTask.scope == scope)
            if region_key:
                conditions.append(DomainFactoryTask.region_key == region_key)
            if keyword:
                conditions.append(DomainFactoryTask.file_name.ilike(f"%{keyword}%"))

            total = (
                await session.execute(select(func.count(DomainFactoryTask.id)).where(*conditions))
            ).scalar() or 0

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(*conditions)
                .order_by(DomainFactoryTask.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            tasks = result.unique().scalars().all()
            items = [
                {
                    "id": t.id,
                    "file_name": t.file_name,
                    "domain": t.domain.code if t.domain else None,
                    "domain_label": t.domain.name if t.domain else None,
                    "status": t.status,
                    "project_name": t.project_name,
                    "region_label": t.region_label,
                    "region_key": t.region_key,
                    "scope": t.scope,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ]
            return items, total

    async def list_regional_facts(
        self,
        region_key: str | None = None,
        fact_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """区域事实分页列表（created_at 倒序）；来源任务 file_name 就地批量拼接。"""
        async with pg_manager.get_async_session_context() as session:
            conditions = []
            if region_key:
                conditions.append(DomainFactoryRegionalFact.region_key == region_key)
            if fact_type:
                conditions.append(DomainFactoryRegionalFact.fact_type == fact_type)
            if status:
                conditions.append(DomainFactoryRegionalFact.status == status)

            total = (
                await session.execute(select(func.count(DomainFactoryRegionalFact.id)).where(*conditions))
            ).scalar() or 0

            result = await session.execute(
                select(DomainFactoryRegionalFact)
                .where(*conditions)
                .order_by(DomainFactoryRegionalFact.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            facts = result.scalars().all()

            task_ids = {f.source_task_id for f in facts if f.source_task_id}
            file_map: dict[str, str] = {}
            if task_ids:
                rows = await session.execute(
                    select(DomainFactoryTask.id, DomainFactoryTask.file_name).where(
                        DomainFactoryTask.id.in_(task_ids)
                    )
                )
                file_map = dict(rows.all())

            items = [
                {
                    "id": f.id,
                    "fact_type": f.fact_type,
                    "region_key": f.region_key,
                    "content": f.content,
                    "status": f.status,
                    "year": f.year,
                    "source_task_id": f.source_task_id,
                    "source_task_file_name": file_map.get(f.source_task_id),
                    "source_ref": f.source_ref,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                }
                for f in facts
            ]
            return items, total

    async def get_region_board_raw(self) -> dict[str, Any]:
        """看板聚合原始数据（数据量小：任务 8 / 模板 211，单响应一次取全，不做缓存）。"""
        async with pg_manager.get_async_session_context() as session:
            task_rows = (
                await session.execute(
                    select(
                        DomainFactoryTask.region_key,
                        DomainFactoryTask.region_label,
                        func.count(DomainFactoryTask.id),
                    ).group_by(DomainFactoryTask.region_key, DomainFactoryTask.region_label)
                )
            ).all()
            fact_rows = (
                await session.execute(
                    select(
                        DomainFactoryRegionalFact.region_key,
                        DomainFactoryRegionalFact.fact_type,
                        DomainFactoryRegionalFact.status,
                        func.count(DomainFactoryRegionalFact.id),
                    ).group_by(
                        DomainFactoryRegionalFact.region_key,
                        DomainFactoryRegionalFact.fact_type,
                        DomainFactoryRegionalFact.status,
                    )
                )
            ).all()
            scope_rows = (
                await session.execute(
                    select(
                        DomainFactoryLearnedTemplate.scope,
                        func.count(DomainFactoryLearnedTemplate.id),
                    ).group_by(DomainFactoryLearnedTemplate.scope)
                )
            ).all()
            task_region_rows = (
                await session.execute(
                    select(DomainFactoryTask.id, DomainFactoryTask.region_key).where(
                        DomainFactoryTask.region_key.is_not(None)
                    )
                )
            ).all()
            template_rows = (
                await session.execute(
                    select(
                        DomainFactoryLearnedTemplate.id,
                        DomainFactoryLearnedTemplate.chapter,
                        DomainFactoryLearnedTemplate.domain_code,
                        DomainFactoryLearnedTemplate.report_type_code,
                        DomainFactoryLearnedTemplate.scope,
                        DomainFactoryLearnedTemplate.extra_meta,
                        DomainFactoryLearnedTemplate.updated_at,
                    )
                )
            ).all()

        return {
            "tasks_by_region": [
                {"region_key": rk, "region_label": rl, "count": cnt} for rk, rl, cnt in task_rows
            ],
            "facts_by_region_type_status": [
                {"region_key": rk, "fact_type": ft, "status": st, "count": cnt}
                for rk, ft, st, cnt in fact_rows
            ],
            # scope 可能是 NULL → 键用 ""（service 层映射为 unassigned）
            "templates_by_scope": {(scope or ""): cnt for scope, cnt in scope_rows},
            "task_regions": dict(task_region_rows),
            "templates": [
                {
                    "id": tid,
                    "chapter": ch,
                    "domain_code": dc,
                    "report_type_code": rtc,
                    "scope": sc,
                    "contributing_task_ids": (em or {}).get("contributing_task_ids") or [],
                    "updated_at": ua.isoformat() if ua else None,
                }
                for tid, ch, dc, rtc, sc, em, ua in template_rows
            ],
        }
```

- [ ] **Step 1.6: service import +3 读函数**

`backend/package/yuxi/services/domain_factory_service.py`——import 块（:20-29）改为：

```python
from yuxi.services.domain_factory_region import (
    VALID_SCOPES,
    apply_min_permissive,
    derive_template_region,
    extract_fact_signal,
    extract_region_signal,
    extract_year,
    fact_type_for_category,
    l1_task_attribution,
    region_key_for_label,
    region_label_for_key,
)
```

在 `_reaggregate_templates_for_task`（:6503-6508）之后追加：

```python
    # [pisuan-custom] W4 归属管理读接口三件套（只读，读路径不碰写状态）

    async def list_tasks_with_attribution(
        self,
        scope: str | None = None,
        region_key: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """任务归属列表。scope 合法值 universal/regional/project/unassigned。"""
        if scope is not None and scope not in (*VALID_SCOPES, "unassigned"):
            return {"error": f"scope 非法: {scope}"}
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        items, total = await self.repo.list_tasks_with_attribution(
            scope=scope, region_key=region_key, keyword=keyword, page=page, page_size=page_size
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def list_regional_facts(
        self,
        region_key: str | None = None,
        fact_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """区域事实列表。fact_type 四类、status 三态，非法即 400。"""
        valid_types = ("monitoring", "sensitive_target", "measure", "constraint")
        if fact_type is not None and fact_type not in valid_types:
            return {"error": f"fact_type 非法: {fact_type}"}
        if status is not None and status not in ("draft", "confirmed", "retired"):
            return {"error": f"status 非法: {status}"}
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        items, total = await self.repo.list_regional_facts(
            region_key=region_key, fact_type=fact_type, status=status, page=page, page_size=page_size
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def build_region_board(self) -> dict[str, Any]:
        """聚合看板（只读）：统计卡 + 模板明细（region 由归因集派生）+ 区域树。

        树节点 template_count 只计派生 region 恰等于该 region 的模板；mixed 模板只进明细；
        派生 None 进未归属伪节点（region_key=None）。region>6 个时前端 T1 布局换 T2 形态，接口不变。
        """
        raw = await self.repo.get_region_board_raw()

        templates_by_scope = {"universal": 0, "regional": 0, "project": 0, "unassigned": 0}
        for key, cnt in raw["templates_by_scope"].items():
            templates_by_scope[key if key in templates_by_scope else "unassigned"] += cnt

        facts_by_status = {"draft": 0, "confirmed": 0, "retired": 0}
        for row in raw["facts_by_region_type_status"]:
            if row["status"] in facts_by_status:
                facts_by_status[row["status"]] += row["count"]

        tasks_by_region = [
            {"region_key": rk, "region_label": rl, "count": cnt} for rk, rl, cnt in raw["tasks_by_region"]
        ]

        templates = []
        for t in raw["templates"]:
            region = derive_template_region(t["contributing_task_ids"], raw["task_regions"])
            templates.append(
                {
                    "id": t["id"],
                    "chapter": t["chapter"],
                    "scope": t["scope"],
                    "region": region,
                    "contributing_count": len(t["contributing_task_ids"]),
                    "updated_at": t["updated_at"],
                }
            )
        templates.sort(key=lambda x: x["updated_at"] or "", reverse=True)

        def _node(rk: str | None, rl: str | None = None) -> dict[str, Any]:
            return {
                "region_key": rk,
                "region_label": rl,
                "task_count": 0,
                "fact_count": 0,
                "fact_counts_by_type": {"monitoring": 0, "sensitive_target": 0, "measure": 0, "constraint": 0},
                "template_count": 0,
            }

        tree: dict[str | None, dict[str, Any]] = {}
        for row in tasks_by_region:
            node = tree.setdefault(row["region_key"], _node(row["region_key"], row["region_label"]))
            node["task_count"] += row["count"]
            if row["region_label"] and not node["region_label"]:
                node["region_label"] = row["region_label"]
        for row in raw["facts_by_region_type_status"]:
            node = tree.setdefault(row["region_key"], _node(row["region_key"]))
            node["fact_count"] += row["count"]
            if row["fact_type"] in node["fact_counts_by_type"]:
                node["fact_counts_by_type"][row["fact_type"]] += row["count"]
        for t in templates:
            if t["region"] is None or t["region"] == "mixed":
                continue
            node = tree.setdefault(
                t["region"], _node(t["region"], region_label_for_key(t["region"]) or t["region"])
            )
            node["template_count"] += 1

        # 未归属伪节点固定殿后，其余按任务数降序
        nodes = sorted(tree.values(), key=lambda n: (n["region_key"] is None, -n["task_count"], -n["fact_count"]))

        return {
            "stats": {
                "templates_by_scope": templates_by_scope,
                "tasks_by_region": tasks_by_region,
                "facts_by_status": facts_by_status,
            },
            "templates": templates,
            "region_tree": nodes,
        }
```

- [ ] **Step 1.7: router +3 薄 GET**

`backend/server/routers/domain_factory_router.py`——在 `retire_regional_facts` 函数结束（:415）之后、File Upload 分节注释（:418）之前插入（仿 confirm-region 同款 try/except 骨架；路由段数与既有 `GET /tasks/{task_id}` 不同无遮蔽风险）：

```python
@domain_factory.get("/tasks")
async def fetch_attribution_tasks(
    scope: str | None = Query(None),
    region_key: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W4：任务归属列表（scope=unassigned → scope IS NULL）。"""
    try:
        service = get_domain_factory_service()
        result = await service.list_tasks_with_attribution(
            scope=scope, region_key=region_key, keyword=keyword, page=page, page_size=page_size
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list attribution tasks: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取任务归属列表失败: {str(e)}")

@domain_factory.get("/regional-facts")
async def fetch_regional_facts(
    region_key: str | None = Query(None),
    fact_type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W4：区域事实列表（region×fact_type×status 过滤）。"""
    try:
        service = get_domain_factory_service()
        result = await service.list_regional_facts(
            region_key=region_key, fact_type=fact_type, status=status, page=page, page_size=page_size
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list regional facts: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取区域事实列表失败: {str(e)}")

@domain_factory.get("/region-board")
async def fetch_region_board(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W4：聚合看板（统计卡 + 模板明细 + 区域树）。"""
    try:
        service = get_domain_factory_service()
        return await service.build_region_board()
    except Exception as e:
        logger.error(f"Failed to build region board: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取聚合看板失败: {str(e)}")
```

（路由段数与既有 `GET /tasks/{task_id}` 不同，注册顺序无遮蔽风险；插入位置保留前后各一空行与既有端点分隔。）

- [ ] **Step 1.8: 语法与 lint**

```bash
python -c "import ast; ast.parse(open('backend/server/routers/domain_factory_router.py', encoding='utf-8').read()); ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); ast.parse(open('backend/package/yuxi/repositories/domain_factory_repository.py', encoding='utf-8').read()); ast.parse(open('backend/package/yuxi/services/domain_factory_region.py', encoding='utf-8').read()); print('ast OK')"
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 ruff check /app/package/yuxi/services/domain_factory_region.py /app/package/yuxi/services/domain_factory_service.py /app/package/yuxi/repositories/domain_factory_repository.py /app/server/routers/domain_factory_router.py
```

Expected: `ast OK`；ruff 计数 ≤ Step 1.1 基线（新代码零新增告警）。

- [ ] **Step 1.9: 单测全绿（W4 新增 + W3/W1 回归）**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w4_attribution_reads.py /app/test/unit/test_w3_region_rules.py /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w3_facts_flow.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
```

Expected: 全绿（基线 76 + W4 新增 13 = 89 passed 上下；以实际计数为准，关键是零 fail）。

- [ ] **Step 1.10: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_region.py backend/package/yuxi/repositories/domain_factory_repository.py backend/package/yuxi/services/domain_factory_service.py backend/server/routers/domain_factory_router.py backend/test/unit/test_w4_attribution_reads.py
git commit -m "$(cat <<'EOF'
feat(w4): 归属读接口三件套——任务归属/区域事实/聚合看板（零 DDL）

repository 三读方法（分页+GROUP BY 聚合）、service 三读函数（参数校验+钳制+模板 region 派生）、router 三薄 GET；
region 模块 +derive_template_region/region_label_for_key 纯函数。段落级 extract_region_signal 零改动。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 行政区辅助词表 3+6 + L1 二级查找 + live 集成验证

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_region.py`（:35 REGION_VOCAB 后 +ADMIN_REGION_VOCAB；:66 `region_label_for_key` 补二级反查段；:71-77 `extract_region_signal` 重构委托；:105-115 `l1_task_attribution` 二级查找）
- Test: `backend/test/unit/test_w4_admin_vocab.py`（新建）

- [ ] **Step 2.1: 写失败单测**

新建 `backend/test/unit/test_w4_admin_vocab.py`，全文：

```python
# W4 行政区辅助词表单测：9 收录命中 / 4+2 排除不命中 / 主命中优先 / 段落级回归钉。
# 验证走容器道：
# MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" \
#   pisuan-api:0.7.3 pytest /app/test/unit/test_w4_admin_vocab.py --noconftest -q
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_region import (  # noqa: E402
    ADMIN_REGION_VOCAB,
    extract_region_signal,
    l1_task_attribution,
)


def _doc(word: str) -> dict:
    return {"file_name": f"{word}相关规划环评报告书.docx", "document_type": "通用", "report_type_code": "通用"}


class TestAdminVocab:
    def test_slug_format_and_size(self):
        assert len(ADMIN_REGION_VOCAB) == 9
        for name, key in ADMIN_REGION_VOCAB.items():
            assert re.fullmatch(r"[a-z0-9-]+", key), f"{name} -> {key} 不合 slug 格式"

    def test_nine_entries_hit_regional(self):
        for word, expected_key in ADMIN_REGION_VOCAB.items():
            out = l1_task_attribution(_doc(word))
            assert out is not None, word
            assert out["scope"] == "regional", word
            assert out["region_key"] == expected_key, word

    def test_canonical_label_from_primary_vocab(self):
        # 行政区命中 hengcheng 时，region_label 反查主词表展示名「横城矿区」而非「灵武市」
        out = l1_task_attribution(_doc("灵武市"))
        assert out == {"region_label": "横城矿区", "region_key": "hengcheng", "scope": "regional"}

    def test_excluded_words_do_not_hit(self):
        # 排除代表词：邻区参照 / 省市级过宽 / 陷阱词「横城村」（属兴庆区，且不构成「横城矿区」子串命中）
        for word in ("定边县", "博乐市", "萨尔布拉克镇", "横城村", "宁夏", "伊犁州"):
            assert l1_task_attribution(_doc(word)) is None, word

    def test_primary_hit_wins_over_admin(self):
        # 同时含主词表名与行政区词 → 主词表胜（同通道最长名优先）
        doc = {
            "file_name": "伊宁矿区北区总体规划（伊宁县境内）环评.docx",
            "document_type": "通用",
            "report_type_code": "通用",
        }
        out = l1_task_attribution(doc)
        assert out == {"region_label": "伊宁矿区北区", "region_key": "yining-beiqu", "scope": "regional"}

    def test_extract_region_signal_untouched(self):
        # 回归钉：段落级信号函数不查行政区词表（classify region_signals 行为零变动的根基）
        assert extract_region_signal("灵武市临河镇") is None
        assert extract_region_signal("评价范围为横城矿区") == {
            "region_label": "横城矿区",
            "region_key": "hengcheng",
        }
```

- [ ] **Step 2.2: 跑单测验证失败**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w4_admin_vocab.py --noconftest -q
```

Expected: FAIL/ERROR — `ImportError: cannot import name 'ADMIN_REGION_VOCAB'`。

- [ ] **Step 2.3: 实现——词表常量 + 同语义重构 + 二级查找**

`backend/package/yuxi/services/domain_factory_region.py` 三处：

（a）REGION_VOCAB 收尾 `}`（:35）之后、`VALID_SCOPES`（:37）之前插入：

```python
# [pisuan-custom] W4：行政区辅助词表（县/乡镇级，3+6 条，仅任务级 L1 二级查找用）
# 来源：4 份矿区总规环评全文提取（2026-10-07），证据与排除清单见 W4 spec §3/§8-6。
# 与 REGION_VOCAB 的关系：矿区名主命中优先；无主命中才查本表，命中同通道判 regional。
# 陷阱备忘：「横城村」属银川市兴庆区不收；「灵武市」与灵武矿区同域（歧义交 L3 改判纠正）。
ADMIN_REGION_VOCAB: dict[str, str] = {
    "灵武市": "hengcheng",       # 强：归属链核心县级市（歧义：灵武矿区同域，L3 纠）
    "临河镇": "hengcheng",       # 强：「属灵武市临河镇管辖」
    "宁东镇": "hengcheng",       # 强：「矿区位于灵武市宁东镇」多语境
    "伊宁县": "yining-beiqu",        # 强：矿区主体所在县
    "伊宁市": "yining-beiqu",        # 中：紧邻北郊，部分设施在伊宁市界内
    "霍城县": "yining-beiqu",        # 中：保护区/水源地紧邻
    "喀拉亚尕奇乡": "yining-beiqu",  # 强：伊宁县辖
    "英也尔乡": "yining-beiqu",      # 中：伊宁市辖，井田相关
    "曲鲁海乡": "yining-beiqu",      # 中：伊宁县辖，水源地
}
```

（b）`extract_region_signal`（:71-77）整体替换为同语义委托（最长名优先逻辑不变，有 TestRegionSignal 三个旧用例零改动守护）：

```python
def _longest_vocab_hit(text: str, vocab: dict[str, str]) -> dict[str, str] | None:
    """词表扫描：多命中取最长名（防前缀遮蔽，如伊宁矿区北区）。"""
    hit: tuple[str, str] | None = None
    for name, key in vocab.items():
        if name in text and (hit is None or len(name) > len(hit[0])):
            hit = (name, key)
    return {"region_label": hit[0], "region_key": hit[1]} if hit else None


def extract_region_signal(text: str) -> dict[str, str] | None:
    """文本 → region 信号；词表多命中取最长名（防前缀遮蔽，如伊宁矿区北区）。"""
    return _longest_vocab_hit(text, REGION_VOCAB)


def extract_admin_region_signal(text: str) -> dict[str, str] | None:
    """[pisuan-custom] W4：行政区辅助信号（县/乡镇级）。只在任务级 L1 主命中缺席时使用，
    不进段落级 classify（region_signals 行为零变动）。"""
    return _longest_vocab_hit(text, ADMIN_REGION_VOCAB)
```

（c）`region_label_for_key`（T1 版本）补二级反查段：

```python
def region_label_for_key(key: str) -> str | None:
    """slug → 展示名（主词表反查优先，再查行政区辅助词表；查不到返回 None）。"""
    for name, k in REGION_VOCAB.items():
        if k == key:
            return name
    for name, k in ADMIN_REGION_VOCAB.items():
        if k == key:
            return name
    return None
```

（d）`l1_task_attribution`（:105-115）整体替换：

```python
def l1_task_attribution(doc: dict) -> dict | None:
    """任务级 L1 归属：文档身份（文件名/文档类型/报告类型）词表命中 → regional。

    只认文档身份、不扫正文——正文引用矿区名的项目报告（如伊敏项目提「伊敏矿区」）
    不得误判。主词表（REGION_VOCAB 矿区名）优先；无主命中时查行政区辅助词表
    （ADMIN_REGION_VOCAB，W4），命中同通道判 regional，region_label 取 slug 反查的
    主词表展示名（保持同 region 展示一致）。未命中返回 None（scope 留 NULL 交 L2/兜底）。
    """
    identity = " ".join(str(doc.get(k) or "") for k in ("file_name", "document_type", "report_type_code"))
    signal = extract_region_signal(identity)
    if signal is None:
        signal = extract_admin_region_signal(identity)
        if signal is not None:
            canonical = region_label_for_key(signal["region_key"])
            if canonical:
                signal["region_label"] = canonical
    if signal is None:
        return None
    return {**signal, "scope": "regional"}
```

- [ ] **Step 2.4: 单测全绿（W4 两文件 + W3/W1 回归）**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w4_admin_vocab.py /app/test/unit/test_w4_attribution_reads.py /app/test/unit/test_w3_region_rules.py /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w3_facts_flow.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
```

Expected: 全绿。**关键**：`test_w3_region_rules.py` 旧用例零改动全绿 = `extract_region_signal` 重构同语义的证明；`TestTaskAttribution.test_plan_report_regional` 等主命中用例不变 = 主命中优先的证明。

- [ ] **Step 2.5: 语法 + ruff**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_region.py', encoding='utf-8').read()); print('ast OK')"
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 ruff check /app/package/yuxi/services/domain_factory_region.py
```

Expected: `ast OK`；ruff 计数 ≤ 基线。

- [ ] **Step 2.6: sync-dev + live 集成验证（覆盖 T1+T2 后端改动）**

```powershell
./scripts/sync-dev.ps1
```

等 api 容器稳定（`docker logs pisuan-localized-api-1 --tail 20` 无重启报错）后：

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python - <<'PY'
import asyncio

from sqlalchemy import text

from pisuan.repositories.domain_factory_repository import DomainFactoryRepository
from pisuan.services.domain_factory_service import get_domain_factory_service
from pisuan.storage.postgres.manager import pg_manager


async def main():
    repo = DomainFactoryRepository()
    svc = get_domain_factory_service()

    async with pg_manager.get_async_session_context() as s:
        sql_total = (await s.execute(text("SELECT count(*) FROM domain_factory_tasks"))).scalar()
        sql_regional = (await s.execute(text("SELECT count(*) FROM domain_factory_tasks WHERE scope='regional'"))).scalar()
        sql_unassigned = (await s.execute(text("SELECT count(*) FROM domain_factory_tasks WHERE scope IS NULL"))).scalar()
        sql_hc_kw = (await s.execute(text("SELECT count(*) FROM domain_factory_tasks WHERE file_name LIKE '%横城%'"))).scalar()
        fact_status = dict((await s.execute(text(
            "SELECT status, count(*) FROM domain_factory_regional_facts GROUP BY status"))).all())
        tpl_total = (await s.execute(text("SELECT count(*) FROM domain_factory_learned_templates"))).scalar()
        tpl_scoped = (await s.execute(text(
            "SELECT count(*) FROM domain_factory_learned_templates WHERE scope IS NOT NULL"))).scalar()

    # 1) 任务归属列表：分页/筛选/unassigned 语义/关键词
    items, total = await repo.list_tasks_with_attribution()
    assert total == sql_total, (total, sql_total)
    page1, total2 = await repo.list_tasks_with_attribution(page=1, page_size=3)
    assert len(page1) == 3 and total2 == sql_total, (len(page1), total2)
    _, reg_total = await repo.list_tasks_with_attribution(scope="regional")
    assert reg_total == sql_regional, (reg_total, sql_regional)
    _, un_total = await repo.list_tasks_with_attribution(scope="unassigned")
    assert un_total == sql_unassigned, (un_total, sql_unassigned)
    _, kw_total = await repo.list_tasks_with_attribution(keyword="横城")
    assert kw_total == sql_hc_kw, (kw_total, sql_hc_kw)

    # 2) service 层：钳制与非法值
    res = await svc.list_tasks_with_attribution(page=0, page_size=500)
    assert res["page"] == 1 and res["page_size"] == 100, (res["page"], res["page_size"])
    assert (await svc.list_tasks_with_attribution(scope="bogus")).get("error")
    assert (await svc.list_regional_facts(fact_type="bogus")).get("error")

    # 3) 区域事实列表：过滤 + 来源任务名拼接
    f_res = await svc.list_regional_facts(status="confirmed")
    assert f_res["total"] == fact_status.get("confirmed", 0), (f_res["total"], fact_status)
    assert all("source_task_file_name" in it for it in f_res["items"])

    # 4) 看板聚合值 vs SQL 实况
    board = await svc.build_region_board()
    stats = board["stats"]
    assert sum(stats["templates_by_scope"].values()) == tpl_total
    assert stats["templates_by_scope"]["unassigned"] == tpl_total - tpl_scoped
    assert sum(r["count"] for r in stats["tasks_by_region"]) == sql_total
    assert sum(stats["facts_by_status"].values()) == sum(fact_status.values())
    tree = {n["region_key"]: n for n in board["region_tree"]}
    assert tree[None]["task_count"] == sql_unassigned, tree.get(None)
    hc = tree.get("hengcheng")
    assert hc is not None and hc["task_count"] == sql_hc_kw, hc
    if tpl_scoped == 0:  # W3 收口时 211 模板 scope 全 NULL 的预期状态
        assert tree[None]["template_count"] == tpl_total, tree[None]
        assert all(t["region"] is None for t in board["templates"])

    # 5) 合成事实全链（list→retire，自清理；retire 只碰合成行）
    tid = "w4verify_synthetic"
    async with pg_manager.get_async_session_context() as s:
        await s.execute(text(
            "INSERT INTO domain_factory_tasks (id, domain_id, file_name, storage_path, status) "
            "SELECT :id, d.id, :fn, :sp, 'WAITING_REVIEW' FROM domain_factory_domains d "
            "WHERE d.code='coal' ON CONFLICT (id) DO NOTHING"
        ), {"id": tid, "fn": "W4验证-合成任务.docx", "sp": "/tmp/w4v.docx"})
    st = await repo.insert_regional_fact(
        fact_type="measure", content="W4验证-预留煤柱支护", source_task_id=tid,
        entity_key="w4v_m", region_key="hengcheng", year=2026, source_ref="w4v",
    )
    assert st == "created", st
    f2 = await svc.list_regional_facts(fact_type="measure", region_key="hengcheng")
    fid = [i["id"] for i in f2["items"] if i["source_task_id"] == tid]
    assert len(fid) == 1, fid
    assert (await svc.retire_regional_facts(fid)) == 1
    async with pg_manager.get_async_session_context() as s:
        await s.execute(text("DELETE FROM domain_factory_regional_facts WHERE source_task_id=:t"), {"t": tid})
        await s.execute(text("DELETE FROM domain_factory_tasks WHERE id=:t"), {"t": tid})
    print("W4 T2 live verify: ALL PASS")


asyncio.run(main())
PY
```

Expected: 末行 `W4 T2 live verify: ALL PASS`（已知实况锚点：total=8、regional=8、unassigned=0、hengcheng 关键词=5、模板 211 全 NULL——若实况与此不符，以 SQL 实况为准核对断言方向后上报，勿改断言凑数）。

backfill 幂等复跑（W3 已 8/8 落列；新词表只补 NULL，不应有任何写入）：

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python /app/scripts/backfill_task_scope.py
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python /app/scripts/backfill_task_scope.py
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "SELECT count(*) FILTER (WHERE scope IS NOT NULL) AS scoped, count(*) AS total FROM domain_factory_learned_templates"
```

Expected: 两跑均 `回填完成: 0/8 …`（幂等）；模板 `scoped=0`（learned_templates 零改动不变量）。

- [ ] **Step 2.7: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_region.py backend/test/unit/test_w4_admin_vocab.py
git commit -m "$(cat <<'EOF'
feat(w4): 行政区辅助词表 3+6——L1 二级查找与展示名反查

ADMIN_REGION_VOCAB 9 条（横城 3 / 伊宁北区 6，文档驱动提取）；l1_task_attribution 主命中优先、
二级命中 region_label 反查主词表展示名；extract_region_signal 重构为同语义委托（段落级行为零变动，
旧用例零改动全绿）。live 验证：三 GET 聚合值与 SQL 实况一致 + backfill 幂等 0/8 复跑。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: API 封装 5 方法 + Panel 容器 + 任务归属子页 + 改判弹窗 + 第三 tab 挂载

**Files:**
- Modify: `web/src/apis/domain_factory_api.js`（:254 `confirmProposedEntities` 之后）
- Create: `web/src/components/domain-factory/RegionAttributionPanel.vue`
- Create: `web/src/components/domain-factory/AttributionTaskTable.vue`
- Create: `web/src/components/domain-factory/AttributionEditModal.vue`
- Modify: `web/src/views/DomainFactoryView.vue`（:7 import、:272 workbench pane 之后、:564 `&.workbench` 之后）

- [ ] **Step 3.1: API 封装 +5 方法**

`web/src/apis/domain_factory_api.js`——在 `confirmProposedEntities`（:250-254）之后插入（沿用文件内 `withDemoFallback` + `buildUrl` 惯例）：

```js
  // [pisuan-custom] W4 归属管理：任务归属列表（scope/region_key/keyword/page/page_size）
  fetchAttributionTasks: (params = {}) =>
    withDemoFallback(
      () => apiGet(buildUrl('/api/domain-factory/tasks', params)).then((res) => res),
      () => ({ items: [], total: 0, page: 1, page_size: 20 })
    ),
  // 归属确认/改判（级联：facts 确认 + 归因集模板重算）
  confirmRegion: (taskId, payload) =>
    withDemoFallback(
      () => apiPost(`/api/domain-factory/tasks/${taskId}/confirm-region`, payload),
      () => ({ success: true, region_key: '', facts_confirmed: 0, templates_recalculated: 0 })
    ),
  // 区域事实列表（region_key/fact_type/status/page/page_size）
  fetchRegionalFacts: (params = {}) =>
    withDemoFallback(
      () => apiGet(buildUrl('/api/domain-factory/regional-facts', params)).then((res) => res),
      () => ({ items: [], total: 0, page: 1, page_size: 20 })
    ),
  // 批量退役区域事实（admin，不可逆）
  retireRegionalFacts: (factIds) =>
    withDemoFallback(
      () => apiPost('/api/domain-factory/regional-facts/retire', { fact_ids: factIds }),
      () => ({ success: true, retired: 0 })
    ),
  // 聚合看板（stats + templates + region_tree）
  fetchRegionBoard: () =>
    withDemoFallback(
      () => apiGet('/api/domain-factory/region-board').then((res) => res),
      () => ({ stats: {}, templates: [], region_tree: [] })
    ),
```

- [ ] **Step 3.2: 创建 RegionAttributionPanel.vue**

```vue
<script setup>
import { ref } from 'vue'
import AttributionTaskTable from './AttributionTaskTable.vue'
import RegionalFactsTable from './RegionalFactsTable.vue'
import RegionBoard from './RegionBoard.vue'

// [pisuan-custom] W4 归属管理容器：三子页（任务归属/区域事实/模板聚合）。
// v-show 保持子页状态，看板下钻经 ref 调子页 applyRegionFilter 带 region 跳转。
const activeSub = ref('tasks')
const taskTableRef = ref(null)
const factsTableRef = ref(null)

const jumpToTasks = ({ regionKey }) => {
  activeSub.value = 'tasks'
  taskTableRef.value?.applyRegionFilter(regionKey)
}
const jumpToFacts = ({ regionKey }) => {
  activeSub.value = 'facts'
  factsTableRef.value?.applyRegionFilter(regionKey)
}
</script>

<template>
  <div class="attribution-panel">
    <a-tabs v-model:activeKey="activeSub" size="small">
      <a-tab-pane key="tasks" tab="任务归属" />
      <a-tab-pane key="facts" tab="区域事实" />
      <a-tab-pane key="board" tab="模板聚合" />
    </a-tabs>
    <AttributionTaskTable v-show="activeSub === 'tasks'" ref="taskTableRef" />
    <RegionalFactsTable v-show="activeSub === 'facts'" ref="factsTableRef" />
    <RegionBoard
      v-show="activeSub === 'board'"
      @jump-to-tasks="jumpToTasks"
      @jump-to-facts="jumpToFacts"
    />
  </div>
</template>

<style lang="less" scoped>
.attribution-panel {
  padding-top: 4px;
}
</style>
```

- [ ] **Step 3.3: 创建 AttributionTaskTable.vue**

```vue
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import AttributionEditModal from './AttributionEditModal.vue'

// [pisuan-custom] W4 子页1：任务归属列表（scope chips + 关键词 + 逐行改判入口）
const loading = ref(false)
const items = ref([])
const total = ref(0)
const scopeFilter = ref('all')
const keyword = ref('')
const regionKeyFilter = ref('')
const pagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (t) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '50', '100'],
})

const SCOPE_CHIPS = [
  { value: 'all', label: '全部' },
  { value: 'regional', label: 'regional' },
  { value: 'project', label: 'project' },
  { value: 'universal', label: 'universal' },
  { value: 'unassigned', label: '未归属' },
]

const columns = [
  { title: '任务', dataIndex: 'file_name', ellipsis: true },
  { title: '领域', dataIndex: 'domain_label', width: 110 },
  { title: 'scope', key: 'scope', width: 110 },
  { title: 'region_label', dataIndex: 'region_label', width: 140, ellipsis: true },
  { title: 'region_key', dataIndex: 'region_key', width: 130 },
  { title: '任务状态', dataIndex: 'status', width: 140 },
  { title: '操作', key: 'action', width: 100 },
]

const fetchList = async () => {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.pageSize }
    if (scopeFilter.value !== 'all') params.scope = scopeFilter.value
    if (regionKeyFilter.value) params.region_key = regionKeyFilter.value
    if (keyword.value) params.keyword = keyword.value
    const res = await domainFactoryApi.fetchAttributionTasks(params)
    items.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    message.error('加载任务归属列表失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const onFilterChange = () => {
  pagination.current = 1
  fetchList()
}

const handleTableChange = (pag) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchList()
}

// 看板下钻跳转入口：regionKey=null → 未归属（scope=unassigned）；'' → 清过滤；其余按 region 过滤
const applyRegionFilter = (regionKey) => {
  regionKeyFilter.value = regionKey || ''
  scopeFilter.value = regionKey == null ? 'unassigned' : 'all'
  pagination.current = 1
  fetchList()
}
const clearRegionFilter = () => applyRegionFilter('')

const usedRegionKeys = computed(() => [...new Set(items.value.map((t) => t.region_key).filter(Boolean))])

const editingTask = ref(null)
const handleEdited = (result) => {
  message.success(`已归属 ${result.region_key}：级联确认事实 ${result.facts_confirmed} 条，重算模板 ${result.templates_recalculated} 个`)
  editingTask.value = null
  fetchList()
}

onMounted(fetchList)
defineExpose({ applyRegionFilter, refresh: fetchList })
</script>

<template>
  <div class="attribution-task-table">
    <div class="filter-bar">
      <a-radio-group v-model:value="scopeFilter" button-style="solid" size="small" @change="onFilterChange">
        <a-radio-button v-for="c in SCOPE_CHIPS" :key="c.value" :value="c.value">{{ c.label }}</a-radio-button>
      </a-radio-group>
      <a-input-search
        v-model:value="keyword"
        placeholder="搜索任务名"
        style="width: 220px"
        size="small"
        allow-clear
        @search="onFilterChange"
      />
      <a-tag v-if="regionKeyFilter" closable color="blue" @close="clearRegionFilter">
        region: {{ regionKeyFilter }}
      </a-tag>
    </div>
    <a-table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="small"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'scope'">
          <a-tag v-if="record.scope" color="blue">{{ record.scope }}</a-tag>
          <a-tag v-else>未归属</a-tag>
        </template>
        <template v-else-if="column.key === 'action'">
          <a @click="editingTask = record">{{ record.region_key ? '改判' : '归属确认' }}</a>
        </template>
      </template>
    </a-table>
    <AttributionEditModal
      :open="!!editingTask"
      :task="editingTask"
      :used-keys="usedRegionKeys"
      @close="editingTask = null"
      @edited="handleEdited"
    />
  </div>
</template>

<style lang="less" scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
```

- [ ] **Step 3.4: 创建 AttributionEditModal.vue**

```vue
<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

// [pisuan-custom] W4 改判弹窗：region_label 必填 / region_key 可选（候选+可输入新建 slug）/ scope 三选
const props = defineProps({
  open: { type: Boolean, default: false },
  task: { type: Object, default: null },
  usedKeys: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'edited'])

// 与 backend/package/yuxi/services/domain_factory_region.py 的 REGION_VOCAB 同源（17 slug，人工同步）
const REGION_KEY_OPTIONS = [
  'hengcheng', 'yining-beiqu', 'wujianfang', 'naomaohu', 'shajingzi', 'santanghu',
  'lingtai', 'yimin', 'shengli', 'weizhou', 'huating', 'gaotouyao',
  'hegang', 'nalinxili', 'qitaihe', 'yakeshi-wujiu', 'dongsheng',
]
const SCOPE_OPTIONS = [
  { value: 'regional', label: 'regional（区域级：知识归入区域库，多项目共用）' },
  { value: 'project', label: 'project（项目级：知识仅归入单项目）' },
  { value: 'universal', label: 'universal（通用：跨区域跨项目复用）' },
]
const SLUG_RE = /^[a-z0-9-]+$/

const regionLabel = ref('')
const regionKey = ref('')
const scope = ref('regional')
const submitting = ref(false)

watch(
  () => props.open,
  (v) => {
    if (v && props.task) {
      regionLabel.value = props.task.region_label || ''
      regionKey.value = props.task.region_key || ''
      scope.value = props.task.scope || 'regional'
    }
  }
)

const keyOptions = computed(() => {
  const s = new Set([...REGION_KEY_OPTIONS, ...props.usedKeys])
  if (regionKey.value) s.add(regionKey.value)
  return [...s].map((k) => ({ value: k }))
})

const handleOk = async () => {
  if (!props.task) return
  if (!regionLabel.value.trim()) {
    message.warning('region_label 不能为空')
    return
  }
  const key = regionKey.value.trim()
  if (key && !SLUG_RE.test(key)) {
    message.warning('region_key 只允许小写字母/数字/连字符（slug 格式）')
    return
  }
  submitting.value = true
  try {
    const res = await domainFactoryApi.confirmRegion(props.task.id, {
      region_label: regionLabel.value.trim(),
      region_key: key || null,
      scope: scope.value,
    })
    emit('edited', res)
  } catch (e) {
    message.error('归属确认失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="task && task.region_key ? `改判归属 · ${task.file_name}` : `归属确认 · ${task?.file_name || ''}`"
    :confirm-loading="submitting"
    ok-text="确认改判"
    @ok="handleOk"
    @cancel="emit('close')"
  >
    <div class="edit-form">
      <div class="form-row">
        <span class="form-label">region_label *</span>
        <a-input v-model:value="regionLabel" placeholder="区域展示名（如：横城矿区）" />
      </div>
      <div class="form-row">
        <span class="form-label">region_key</span>
        <a-auto-complete
          v-model:value="regionKey"
          :options="keyOptions"
          placeholder="slug，可从候选选择或输入新建；留空则按 label 反查词表"
        />
      </div>
      <div class="form-row">
        <span class="form-label">scope *</span>
        <a-radio-group v-model:value="scope">
          <a-radio v-for="o in SCOPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</a-radio>
        </a-radio-group>
      </div>
      <a-alert
        type="warning"
        show-icon
        message="确认后将级联：该任务全部未退役事实覆盖回填 region 并 draft→confirmed；归因集内模板按 min-permissive 重算。"
      />
    </div>
  </a-modal>
</template>

<style lang="less" scoped>
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-label {
  display: inline-block;
  width: 100px;
  color: var(--gray-500, #64748b);
}
</style>
```

- [ ] **Step 3.5: 挂载第三 tab（DomainFactoryView 仅 3 触点）**

`web/src/views/DomainFactoryView.vue` 三处：

（a）:7 `import EtlWorkbench ...` 之后加一行：

```js
import RegionAttributionPanel from '@/components/domain-factory/RegionAttributionPanel.vue'
```

（b）workbench 的 `</a-tab-pane>`（:272）之后、`</a-tabs>`（:273）之前插入：

```html
          <a-tab-pane key="region" tab="归属管理">
            <template #tab>
              <span class="tab-label">
                <span class="tab-dot region"></span>归属管理
                <span class="tab-hint">改判 · 退役 · 聚合</span>
              </span>
            </template>
            <RegionAttributionPanel />
          </a-tab-pane>
```

（c）样式块 `&.workbench { ... }`（:562-564）之后、嵌套 `.tab-dot` 闭合前加一个变体：

```less
        &.region {
          background: #0891b2; /* [pisuan-custom] W4 归属管理点缀（科技青系），不随主题 */
        }
```

- [ ] **Step 3.6: 前端 lint + format**

```bash
cd web && pnpm run format && pnpm run lint
```

Expected: 零 error（format 自动修复格式属正常；lint 报既有 warning 与本次无关）。

- [ ] **Step 3.7: sync-dev + 运行栈冒烟**

```powershell
./scripts/sync-dev.ps1
docker ps --format "{{.Names}} {{.Ports}}" | Select-String web
```

用 chrome-devtools MCP（或请用户人工）打开 `http://localhost:<web端口>/domain-factory`：

1. 「归属管理」tab 出现在 ETL 工作台右侧，tab-dot 青色圆点渲染；
2. 子页1 表格加载 8 行任务（server 分页 `共 8 条`），scope 徽标 regional；点「regional」「未归属」chips 过滤生效（0 行空态）；关键词「横城」→ 5 行；
3. 点任一横城任务「改判」→ 弹窗预填；region_key 输入 `Hengcheng!` → 提示 slug 校验 warning；**原值不改直接确认**（幂等：同一 region_key/scope 重新确认）→ toast「已归属 hengcheng：级联确认事实 N 条，重算模板 N 个」→ 列表原位刷新；
4. 取消按钮关闭弹窗无副作用；
5. 回归：数据源管理 / ETL 清洗工作台两 tab 打开无异常（零行为变化）。

若遇登录墙：凭据红线（约束 8）——改请用户人工冒烟并回报结果，不要自行取凭据。

- [ ] **Step 3.8: Commit**

```bash
git add web/src/apis/domain_factory_api.js web/src/components/domain-factory/RegionAttributionPanel.vue web/src/components/domain-factory/AttributionTaskTable.vue web/src/components/domain-factory/AttributionEditModal.vue web/src/views/DomainFactoryView.vue
git commit -m "$(cat <<'EOF'
feat(w4): 归属管理面板——API 封装/容器/任务归属子页/改判弹窗/第三 tab 挂载

domain_factory_api +5 方法；RegionAttributionPanel 三子 tab 容器（v-show 保状态）；AttributionTaskTable
scope chips+关键词+region 下钻过滤+逐行改判；AttributionEditModal label 必填/slug 校验/scope 三选/级联警示；
DomainFactoryView 纯增量挂载（1 import + 1 pane + 1 配色行）。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 区域事实子页（三重筛选 + admin 批量退役）

**Files:**
- Create: `web/src/components/domain-factory/RegionalFactsTable.vue`

- [ ] **Step 4.1: 创建 RegionalFactsTable.vue**

```vue
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useUserStore } from '@/stores/user'

// [pisuan-custom] W4 子页2：区域事实浏览 + admin 批量退役。
// API 层 get_admin_user 兜底，前端 isAdmin 仅展示层收敛（不重复鉴权假设）。
const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const regionKey = ref('')
const factType = ref('')
const status = ref('')
const selectedIds = ref([])
const regionOptions = ref([{ value: '', label: '全部 region' }])
const pagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (t) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '50', '100'],
})

const FACT_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'monitoring', label: '监测' },
  { value: 'sensitive_target', label: '敏感目标' },
  { value: 'measure', label: '措施' },
  { value: 'constraint', label: '约束' },
]
const STATUS_CHIPS = [
  { value: '', label: '全部' },
  { value: 'draft', label: 'draft' },
  { value: 'confirmed', label: 'confirmed' },
  { value: 'retired', label: 'retired' },
]
const STATUS_COLORS = { draft: 'orange', confirmed: 'green', retired: 'default' }
const TYPE_LABELS = { monitoring: '监测', sensitive_target: '敏感目标', measure: '措施', constraint: '约束' }

const columns = [
  { title: '类型', key: 'fact_type', width: 90 },
  { title: 'region', dataIndex: 'region_key', width: 120 },
  { title: '内容', dataIndex: 'content', ellipsis: true },
  { title: '状态', key: 'status', width: 100 },
  { title: '年份', dataIndex: 'year', width: 70 },
  { title: '来源任务', dataIndex: 'source_task_file_name', ellipsis: true, width: 220 },
]

const fetchList = async () => {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.pageSize }
    if (regionKey.value) params.region_key = regionKey.value
    if (factType.value) params.fact_type = factType.value
    if (status.value) params.status = status.value
    const res = await domainFactoryApi.fetchRegionalFacts(params)
    items.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    message.error('加载区域事实失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// region 下拉候选来自看板树（真实存在的 region 才可筛）
const fetchRegionOptions = async () => {
  try {
    const board = await domainFactoryApi.fetchRegionBoard()
    const opts = (board.region_tree || []).filter((n) => n.region_key).map((n) => ({
      value: n.region_key,
      label: `${n.region_label || n.region_key}（${n.region_key}）`,
    }))
    regionOptions.value = [{ value: '', label: '全部 region' }, ...opts]
  } catch (e) {
    console.warn('[RegionalFactsTable] region 候选加载失败（不影响浏览）', e)
  }
}

const onFilterChange = () => {
  pagination.current = 1
  fetchList()
}
const handleTableChange = (pag) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchList()
}

const rowSelection = computed(() => {
  if (!userStore.isAdmin) return undefined
  return {
    selectedRowKeys: selectedIds.value,
    onChange: (keys) => {
      selectedIds.value = keys
    },
  }
})

const rowClassName = (record) => (record.status === 'retired' ? 'fact-retired' : '')

const confirmRetire = () => {
  Modal.confirm({
    title: `批量退役 ${selectedIds.value.length} 条区域事实？`,
    content: '退役 = status→retired 留审计行，不删数据；操作不可恢复，请确认。',
    okText: '批量退役',
    okType: 'danger',
    onOk: async () => {
      try {
        const res = await domainFactoryApi.retireRegionalFacts(selectedIds.value)
        message.success(`已退役 ${res.retired} 条`)
        selectedIds.value = []
        fetchList()
      } catch (e) {
        message.error('退役失败: ' + (e.message || '未知错误'))
      }
    },
  })
}

onMounted(() => {
  fetchList()
  fetchRegionOptions()
})
defineExpose({
  applyRegionFilter: (rk) => {
    regionKey.value = rk || ''
    pagination.current = 1
    fetchList()
  },
  refresh: fetchList,
})
</script>

<template>
  <div class="regional-facts-table">
    <div class="filter-bar">
      <a-select v-model:value="regionKey" :options="regionOptions" style="width: 200px" size="small" @change="onFilterChange" />
      <a-select :options="FACT_TYPE_OPTIONS" style="width: 120px" size="small" :value="factType" @change="(v) => { factType = v; onFilterChange() }" />
      <a-radio-group :value="status" button-style="solid" size="small" @change="(e) => { status = e.target.value; onFilterChange() }">
        <a-radio-button v-for="c in STATUS_CHIPS" :key="c.value" :value="c.value">{{ c.label }}</a-radio-button>
      </a-radio-group>
    </div>
    <a-table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :pagination="pagination"
      :row-selection="rowSelection"
      :row-class-name="rowClassName"
      row-key="id"
      size="small"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'fact_type'">
          {{ TYPE_LABELS[record.fact_type] || record.fact_type }}
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="STATUS_COLORS[record.status]">{{ record.status }}</a-tag>
        </template>
      </template>
    </a-table>
    <div v-if="userStore.isAdmin && selectedIds.length" class="batch-bar">
      <span>已选 {{ selectedIds.length }} 条</span>
      <a-button danger size="small" @click="confirmRetire">批量退役</a-button>
    </div>
  </div>
</template>

<style lang="less" scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 6px 12px;
  background: var(--warning-bg, #fff7e6);
  border-radius: 6px;
  width: fit-content;
}
:deep(.fact-retired) {
  opacity: 0.5;
}
</style>
```

- [ ] **Step 4.2: 前端 lint + format**

```bash
cd web && pnpm run format && pnpm run lint
```

Expected: 零 error。

- [ ] **Step 4.3: sync-dev + 冒烟（只看不退，真实行不退役）**

```powershell
./scripts/sync-dev.ps1
```

浏览器进「归属管理 → 区域事实」：

1. 表格加载事实行；region 下拉含 hengcheng（横城矿区）/ yining-beiqu（伊宁矿区北区）；fact_type/状态 chips 过滤生效；
2. admin 登录态：出现勾选列；勾 ≥1 → 底部「已选 N 条 + 批量退役」操作条出现；点「批量退役」→ 确认弹窗出现后**点取消**（不真退）；
3. retired 行置灰（如有）；
4. 非 admin 不可见性：以普通用户登录（种子账号，向用户索取或由用户自验）确认无勾选列、无操作条；
5. 看板下钻联动（T5 后补验）：暂跳过。

- [ ] **Step 4.4: Commit**

```bash
git add web/src/components/domain-factory/RegionalFactsTable.vue
git commit -m "$(cat <<'EOF'
feat(w4): 区域事实子页——三重筛选与 admin 批量退役

region×fact_type×status 三重筛选（region 候选取自看板树）；admin 勾选列+批量退役操作条
（确认弹窗 danger，toast 计数）；retired 行置灰；非 admin 纯浏览。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 聚合看板子页（统计卡 + 明细 + T1 下钻树）

**Files:**
- Create: `web/src/components/domain-factory/RegionBoard.vue`

- [ ] **Step 5.1: 创建 RegionBoard.vue**

```vue
<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { domainFactoryApi } from '@/apis/domain_factory_api'

// [pisuan-custom] W4 子页3：聚合看板（只读）。region>6 个时组件内重排 T2 形态（左树右详情），接口不变。
const emit = defineEmits(['jump-to-tasks', 'jump-to-facts'])
const loading = ref(false)
const board = ref(null)
const expandedKey = ref(null)

const SCOPE_CARDS = [
  { key: 'universal', label: 'universal' },
  { key: 'regional', label: 'regional' },
  { key: 'project', label: 'project' },
  { key: 'unassigned', label: '未判定' },
]

// stats 子对象兜底为空对象（demo fallback 返回 {stats:{}} 时不渲染崩）
const tbs = computed(() => board.value?.stats?.templates_by_scope || {})
const fbs = computed(() => board.value?.stats?.facts_by_status || {})
const tbr = computed(() => board.value?.stats?.tasks_by_region || [])

const templateColumns = [
  { title: '模板（章族）', dataIndex: 'chapter', ellipsis: true },
  { title: 'scope', key: 'scope', width: 110 },
  { title: 'region', key: 'region', width: 140 },
  { title: '归因集', dataIndex: 'contributing_count', width: 80 },
  { title: '更新时间', key: 'updated_at', width: 150 },
]

const fetchBoard = async () => {
  loading.value = true
  try {
    board.value = await domainFactoryApi.fetchRegionBoard()
  } catch (e) {
    message.error('加载聚合看板失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const regionLabel = (node) => node.region_label || node.region_key || '未归属'
const nodeKey = (node) => node.region_key ?? '__unassigned__'
const expandedNode = computed(() =>
  (board.value?.region_tree || []).find((n) => nodeKey(n) === expandedKey.value)
)
const toggleExpand = (node) => {
  expandedKey.value = expandedKey.value === nodeKey(node) ? null : nodeKey(node)
}
const regionText = (r) => (r === 'mixed' ? 'mixed（多区域）' : r || '未归属')
const fmt = (v) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—')

onMounted(fetchBoard)
defineExpose({ refresh: fetchBoard })
</script>

<template>
  <div v-if="board" class="region-board">
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-title">模板 × scope</div>
        <div class="stat-body">
          <span v-for="c in SCOPE_CARDS" :key="c.key" class="stat-item">
            <b>{{ tbs[c.key] ?? 0 }}</b> {{ c.label }}
          </span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-title">任务 × region</div>
        <div class="stat-body">
          <span v-for="r in tbr" :key="r.region_key ?? '__none__'" class="stat-item">
            <b>{{ r.count }}</b> {{ r.region_label || r.region_key || '未归属' }}
          </span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-title">事实 × 状态</div>
        <div class="stat-body">
          <span class="stat-item"><b>{{ fbs.draft ?? 0 }}</b> draft</span>
          <span class="stat-item"><b>{{ fbs.confirmed ?? 0 }}</b> confirmed</span>
          <span class="stat-item"><b>{{ fbs.retired ?? 0 }}</b> retired</span>
        </div>
      </div>
    </div>

    <h4 class="section-title">模板聚合明细</h4>
    <a-table
      :data-source="board.templates"
      :columns="templateColumns"
      :loading="loading"
      :pagination="{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }"
      :locale="{ emptyText: '新任务回写后出现（存量模板 scope=NULL 为 W3 Q3 预期行为）' }"
      row-key="id"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'scope'">
          <a-tag v-if="record.scope" color="blue">{{ record.scope }}</a-tag>
          <a-tag v-else>未判定</a-tag>
        </template>
        <template v-else-if="column.key === 'region'">{{ regionText(record.region) }}</template>
        <template v-else-if="column.key === 'updated_at'">{{ fmt(record.updated_at) }}</template>
      </template>
    </a-table>

    <h4 class="section-title">区域下钻</h4>
    <div class="region-cards">
      <div
        v-for="node in board.region_tree"
        :key="nodeKey(node)"
        class="region-card"
        :class="{ active: expandedKey === nodeKey(node) }"
        @click="toggleExpand(node)"
      >
        <div class="region-name">{{ expandedKey === nodeKey(node) ? '▾' : '▸' }} {{ regionLabel(node) }}</div>
        <div class="region-badges">任务 {{ node.task_count }} · 事实 {{ node.fact_count }} · 模板 {{ node.template_count }}</div>
      </div>
    </div>
    <div v-if="expandedNode" class="region-detail">
      <p>
        事实分布：监测 {{ expandedNode.fact_counts_by_type.monitoring }} · 敏感目标
        {{ expandedNode.fact_counts_by_type.sensitive_target }} · 措施
        {{ expandedNode.fact_counts_by_type.measure }} · 约束
        {{ expandedNode.fact_counts_by_type.constraint }}
      </p>
      <p v-if="expandedNode.region_key">
        <a @click="emit('jump-to-tasks', { regionKey: expandedNode.region_key })">任务 {{ expandedNode.task_count }} →</a>
        <a style="margin-left: 16px" @click="emit('jump-to-facts', { regionKey: expandedNode.region_key })">事实 {{ expandedNode.fact_count }} →</a>
      </p>
      <p v-else class="detail-hint">未归属伪节点：改判任务后自动归位</p>
    </div>
  </div>
  <a-spin v-else :spinning="loading" />
</template>

<style lang="less" scoped>
.region-board {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.stat-cards {
  display: flex;
  gap: 12px;
}
.stat-card {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--gray-200, #e2e8f0);
  border-radius: 8px;
}
.stat-title {
  font-size: 12px;
  color: var(--gray-400, #94a3b8);
}
.stat-body {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.stat-item {
  font-size: 13px;
}
.section-title {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--gray-500, #64748b);
}
.region-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.region-card {
  padding: 8px 14px;
  border: 1px dashed var(--gray-300, #cbd5e1);
  border-radius: 8px;
  cursor: pointer;
  &.active {
    border-color: var(--main-color, #2563eb);
    border-style: solid;
  }
}
.region-name {
  font-size: 13px;
  font-weight: 600;
}
.region-badges {
  margin-top: 4px;
  font-size: 12px;
  color: var(--gray-400, #94a3b8);
}
.region-detail {
  padding: 10px 14px;
  border: 1px solid var(--gray-200, #e2e8f0);
  border-radius: 8px;
  font-size: 13px;
  p {
    margin: 2px 0;
  }
}
.detail-hint {
  color: var(--gray-400, #94a3b8);
}
</style>
```

- [ ] **Step 5.2: 前端 lint + format**

```bash
cd web && pnpm run format && pnpm run lint
```

Expected: 零 error。

- [ ] **Step 5.3: sync-dev + 冒烟（空态/计数/下钻跳转）**

```powershell
./scripts/sync-dev.ps1
```

浏览器进「归属管理 → 模板聚合」：

1. 统计卡×3 数值与 DB 一致（对照：`docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "SELECT scope, count(*) FROM domain_factory_learned_templates GROUP BY scope; SELECT region_key, count(*) FROM domain_factory_tasks GROUP BY region_key; SELECT status, count(*) FROM domain_factory_regional_facts GROUP BY status;"`）——预期 211 模板全落「未判定」、任务 5 hengcheng + 3 yining-beiqu；
2. 明细表 211 行 region=未归属（W3 Q3 预期），倒序，客户端分页；
3. 区域卡两张（hengcheng/yining-beiqu）+ 未归属伪节点殿后；点 hengcheng 展开：任务 5 · 事实 N · 模板 0；再点收起；
4. 点「任务 5 →」→ 自动切「任务归属」子页且出现 `region: hengcheng` 过滤 tag、列表 5 行；点「事实 N →」→ 切「区域事实」子页已过滤；
5. 未归属伪节点无跳转链接，显示提示文案。

- [ ] **Step 5.4: Commit**

```bash
git add web/src/components/domain-factory/RegionBoard.vue
git commit -m "$(cat <<'EOF'
feat(w4): 聚合看板子页——统计卡/模板明细/区域下钻树

统计卡×3（模板×scope/任务×region/事实×状态）；明细表（region 派生展示含 mixed/未归属，倒序+空态文案）；
T1 横排 region 卡+展开明细块，任务/事实计数可点击带 region 过滤跳对应子页。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: lint/format + changelog + spec 勘误 + 全量回归 + 终审

**Files:**
- Modify: `docs/develop-guides/changelog.md`（「pisuan 定制增量（2026-10-06）」节尾后加 W4 条目）
- Modify: `docs/superpowers/specs/2026-10-07-w4-attribution-ui-design.md`（三处勘误）
- Modify: `docs/superpowers/plans/2026-10-07-w4-attribution-ui.md`（勾掉 checkbox，追加执行记录）

- [ ] **Step 6.1: 后端收尾 lint（对比基线）**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 ruff check /app/package/yuxi/services/domain_factory_region.py /app/package/yuxi/services/domain_factory_service.py /app/package/yuxi/repositories/domain_factory_repository.py /app/server/routers/domain_factory_router.py
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 ruff format --check /app/package/yuxi/services/domain_factory_region.py /app/server/routers/domain_factory_router.py /app/package/yuxi/repositories/domain_factory_repository.py
```

Expected: check 计数 ≤ T1 Step 1.1 基线；format --check 若列出文件，按 `ruff format --diff` 输出在 worktree 手工等价修正后复跑至 clean。

- [ ] **Step 6.2: 全量单测回归**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w4_attribution_reads.py /app/test/unit/test_w4_admin_vocab.py /app/test/unit/test_w3_region_rules.py /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w3_facts_flow.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
```

Expected: 全绿（基线 76 + W4 新增，零 fail）。

- [ ] **Step 6.3: changelog 条目**

`docs/develop-guides/changelog.md`——在「pisuan 定制增量（2026-10-06）」节最后一条（W3 收口条）之后、「## v0.7.2」之前插入新节与三条目：

```markdown
### pisuan 定制增量（2026-10-07）

- feat(w4): 归属读接口三件套——`GET /domain-factory/tasks`（scope/region_key/keyword 筛选 + 分页，scope=unassigned → IS NULL）、`GET /domain-factory/regional-facts`（三重筛选，service 拼 source_task_file_name）、`GET /domain-factory/region-board`（stats + 模板明细 + region_tree；模板 region 由归因集派生：恰一→该值/多→mixed/空→未归属）。零 DDL
- feat(w4): 行政区辅助词表 3+6（ADMIN_REGION_VOCAB，横城 3/伊宁北区 6，文档驱动提取）——任务级 L1 二级查找，矿区名主命中优先，二级命中 region_label 反查主词表展示名；段落级 extract_region_signal 零改动（classify region_signals 行为不变）；backfill 幂等复跑 0/8
- feat(w4): 知识工厂第三 tab「归属管理」——任务归属子页（scope chips/关键词/region 下钻过滤/逐行改判弹窗：label 必填+slug 校验+scope 三选+级联警示，toast 计数=级联实况）、区域事实子页（三重筛选+admin 勾选批量退役，retired 置灰，非 admin 纯浏览）、模板聚合看板（统计卡×3/明细表/T1 横排 region 卡下钻，任务/事实计数跨子页带过滤跳转）。DomainFactoryView 纯增量挂载
```

- [ ] **Step 6.4: spec 三处勘误（保持 spec 与实现一致）**

`docs/superpowers/specs/2026-10-07-w4-attribution-ui-design.md`：

（a）§2 不变量句「`DomainFactoryView.vue` 仅新增 1 个 a-tab-pane + 1 行 import」→ 改为「`DomainFactoryView.vue` 仅新增 1 个 a-tab-pane + 1 行 import + 1 行 tab-dot 配色（实况：既有 tab 图标为 CSS 圆点非 lucide 图标）」；
（b）§4.1 末条「图标 lucide-vue-next（tab 图标选 MapPinned 类…）」→ 改为「tab 图标沿用既有 tab-dot CSS 圆点惯例（.tab-dot.region 配色 #0891b2），组件内表格图标按文件现状用 @lucide/vue」；
（c）§4.3 board 响应行补 `templates:[{id,chapter,scope,region,contributing_count,updated_at}]`（明细表数据随看板单响应返回），并在树字段说明处补一句「template_count 只计派生 region 恰等于该 region 的模板（mixed 只进明细）」。

- [ ] **Step 6.5: 勾账 + 执行记录**

本计划文件：勾掉全部 checkbox；文末追加「## 执行记录」小节（日期、各任务 commit SHA、live 验证结果一行、偏离计划事项如「计划勘误 N 条」）。`.wolf/memory.md` 追加一行（python 脚本方式，遵守约束 7）；`.wolf/anatomy.md` 补 5 个新前端组件与 2 个新测试文件的条目。

- [ ] **Step 6.6: 终审 commit**

```bash
git add docs/develop-guides/changelog.md docs/superpowers/specs/2026-10-07-w4-attribution-ui-design.md docs/superpowers/plans/2026-10-07-w4-attribution-ui.md
git commit -m "$(cat <<'EOF'
docs(w4): changelog 与勾账收口——归属管理 tab 交付与 spec 三处勘误

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6.7: fresh-eyes 终审（DoD 对照）**

逐条核对并如实记录（不达标即回修，不许「视为通过」）：

| # | DoD | 证据 |
|---|---|---|
| 1 | 三 GET live 断言与 DB 实况一致 | T2 Step 2.6 `ALL PASS` 输出 |
| 2 | 词表 9 命中+4 排除+主优先单测绿；backfill 幂等 0/8 | T2 Step 2.4 / 2.6 |
| 3 | pnpm lint+format 零 error；现有两 tab 回归零行为变化 | T3-T5 lint 输出 + T3 Step 3.7-5 |
| 4 | 改判级联 toast 计数与 DB 一致；slug 校验拒绝非法输入 | T3 Step 3.7-3 |
| 5 | admin 可见退役操作、非 admin 不可见 | T4 Step 4.3-2/4 |
| 6 | 看板数值=DB 聚合实况；空态文案；下钻跳转带过滤 | T5 Step 5.3 |
| 7 | 零 DDL；禁碰文件零卷入；DomainFactoryView diff=3 触点；中文提交+明确 add | `git log --stat` + `git diff 5b3bd8ba..HEAD --stat` 核对 |

禁碰文件核对命令：

```bash
git diff 5b3bd8ba..HEAD --name-only | grep -E "HomeView|LoginView|base\.css|base\.dark|info\.template" ; echo "exit=$?"
```

Expected: 无输出行、`exit=1`（grep 无命中）。DomainFactoryView 增量核对：

```bash
git diff 5b3bd8ba..HEAD -- web/src/views/DomainFactoryView.vue | grep -cE "^\+[^+]"
```

Expected: `13`（1 行 import + 9 行 pane 块 + 3 行 tab-dot 配色；若 format 微调行数，逐行核对不越界即可，如实记录）。

---

## 风险提示（执行者注意）

- **retire 不可逆**：UI 冒烟与 live 验证中，退役只允许打在合成数据上（T2 Step 2.5 自清理）；UI 冒烟点到确认弹窗即取消。
- **改判原值幂等**：冒烟用「同值重判」——confirm-region 以相同 label/key/scope 重确认是幂等操作；不要在冒烟中把任务改到别的 region（会造成真实数据漂移）。
- **`_longest_vocab_hit` 重构**：语义必须与原循环逐字等价（同样的 dict 迭代序 + 同样的比较条件）；守护 = `test_w3_region_rules.py` 的 TestRegionSignal 三用例零改动全绿，任何旧用例改动都视为违规。
- **region_key 候选硬编码漂移**：前端 `REGION_KEY_OPTIONS`（17 slug）与后端 REGION_VOCAB 人工同步——词表变更（L3 落定新矿区）时两处都要动；如嫌漂移风险大，后续可加 vocab 只读端点（挂账，不属本窗）。
- **sync-dev 动运行栈**：常规开发同步（非官方 sync-upstream 链）；执行前确认无他人在跑其它窗的任务。
- **灵武市歧义**：词表单层设计接受误判（灵武矿区文档与横城文档同词），改判 UI 即兜底通道——冒烟不需要验证误判纠正，那是 L3 人工流程。
