# 方案 B：通用域去领域化（行为级）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md §4 落地行为级去领域化——领域维度从前端与 API 契约消失，后端收敛为固定 `general` 常量，存量数据 B2 迁移，/eia 段与写手 prompts 零改动。

**Architecture:** 三阶段推进（① 后端常量收敛+数据脚本 → ② 前端摘除 → ③ 路由删参+测试清理），任一时刻栈内兼容。单一事实源 `GENERAL_DOMAIN_CODE` 放在仓储层模块（service 与 tools 均已依赖该模块）；服务层函数签名一律不动，只改值来源；图谱键结构不变（domain 槽恒 general）。

**Tech Stack:** FastAPI + SQLAlchemy(async) + Vue3/AntDV + pytest；后端测试统一在 docker 内跑。

---

## 执行环境约定（每个任务都适用）

- 工作目录 `C:\workspace\pisuan`，分支 `pisuan-custom`（无 worktree——本项目依赖主树的 sync-dev 热重载栈）。
- **docker 内测试必须加 `MSYS_NO_PATHCONV=1`**（Git Bash 会改写 `/app/...` 导致 0 collected，见 .wolf/cerebrum）：
  ```bash
  MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/... -v
  ```
- 容器布局：`/app` = backend/ 内容（`/app/test`、`/app/package/yuxi`）。仓库根的 `scripts/` 不确定是否挂载——数据脚本用 `docker exec -i api-dev python - < <宿主路径>` 执行。
- 提交前：`make format`（或容器内 `ruff format` + `ruff check`）；提交信息中文 + Conventional Commits + `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 前端命令在 `web/` 下：`pnpm run lint`。
- 基线：动手前先跑一次现有集成测试确认绿（见 Task 1 Step 0）。

## 与 spec 的偏差（已识别，需知悉）

1. **`_REPORT_TYPE_ALIASES` 的 `"通用": "eia_report"` 键保留不删**（spec §3.2 原计划删除）。原因：它是 report_type 归一而非领域维度，且默认上传 `report_type_code="通用"`（router:510）依赖此映射换算成图谱/大纲键 `eia_report`（service:4335/:4719-4720），删除会打断存量 outlines 的键链。登记为后续独立小项。
2. **数据脚本 UPDATE 范围 = 7 表 + `report_types`**（spec §4.1 列 7 表，`report_types` 在 §3.7 只写了"查询恒 general"）。不迁移则写手工具 `list_report_types('general')` 查不到存量报告类型，必须一并迁移，共 8 张表。

---

### Task 1: 仓储层——常量锚点 + get_or_create_general_domain + 单元测试

**Files:**
- Test (create): `backend/test/unit/repositories/test_domain_factory_domain_aliases.py`
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`（常量区 :23-45 附近；Domain CRUD 区 :96-116 附近）

- [ ] **Step 0: 基线确认**

```bash
docker ps --format "{{.Names}}" | grep api-dev
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/integration/api/test_domain_factory_api.py -v
```
Expected: 全部 PASS（或既有 skip）。失败先停：修基线，不带病开工。

- [ ] **Step 1: 写失败测试**

新建 `backend/test/unit/repositories/test_domain_factory_domain_aliases.py`：

```python
"""去领域化常量与别名归一单元测试（设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md）。"""

from yuxi.repositories.domain_factory_repository import (
    GENERAL_DOMAIN_CODE,
    GENERAL_DOMAIN_NAME,
    _normalize_domain,
    _normalize_report_type,
)


def test_general_domain_constants():
    assert GENERAL_DOMAIN_CODE == "general"
    assert GENERAL_DOMAIN_NAME == "通用域"


def test_normalize_domain_still_works_as_alias_lookup():
    # 别名表保留（工具入参兼容），但去域后语义由调用方强制覆盖为 general
    assert _normalize_domain("煤矿") == "coal"
    assert _normalize_domain("  chem ") == "chem"


def test_report_type_alias_general_to_eia_report_is_load_bearing():
    # 与 spec 的偏差项：该映射保留（默认上传 report_type="通用" 依赖它换算大纲键）
    assert _normalize_report_type("通用") == "eia_report"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/unit/repositories/test_domain_factory_domain_aliases.py -v
```
Expected: FAIL，`ImportError: cannot import name 'GENERAL_DOMAIN_CODE'`。

- [ ] **Step 3: 实现——repo 模块头部加常量**

在 `domain_factory_repository.py` 的 `_DOMAIN_ALIASES` 定义之前（:23 注释上方）加：

```python
# 去领域化（2026-10-29）：通用域唯一常量。领域维度废弃后，所有写入与查询固定使用此值；
# domains 表冻结保留（历史外键兼容），不再暴露增删改接口。
GENERAL_DOMAIN_CODE = "general"
GENERAL_DOMAIN_NAME = "通用域"
```

- [ ] **Step 4: 实现——get_or_create_general_domain**

在 `create_domain` 方法（:112-116）之后加（session 模式与 `create_domain` 完全一致）：

```python
    async def get_or_create_general_domain(self) -> DomainFactoryDomain:
        """通用域行不存在则建（幂等）。去域后任务外键统一指向它。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).where(DomainFactoryDomain.code == GENERAL_DOMAIN_CODE)
            )
            domain = result.scalar_one_or_none()
            if domain is None:
                domain = DomainFactoryDomain(
                    code=GENERAL_DOMAIN_CODE,
                    name=GENERAL_DOMAIN_NAME,
                    description="去领域化后的唯一通用域",
                )
                session.add(domain)
        return domain
```

- [ ] **Step 5: 跑测试确认通过**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/unit/repositories/test_domain_factory_domain_aliases.py -v
```
Expected: 3 PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/repositories/test_domain_factory_domain_aliases.py
git commit -m "feat(domain-factory): 去领域化常量锚点 GENERAL_DOMAIN_CODE 与通用域行 get_or_create

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 服务层——`or "coal"` 兜底全部收敛 + create_task 换通用域外键

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（8 处字面量 + create_task :582-584）

- [ ] **Step 1: 导入常量**

在 service 文件已有的 `from yuxi.repositories.domain_factory_repository import ...` 行补充导入（该文件 :4331 处已有函数级导入 `from yuxi.repositories.domain_factory_repository import _normalize_domain`，模块级若没有则新增一行）：

```python
from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
```

- [ ] **Step 2: 逐处替换（8 处，全部是把 `"coal"` 换成 `GENERAL_DOMAIN_CODE`）**

| 行号（2026-10-29 工作树） | 现状 | 改为 |
|---|---|---|
| :742 | `matcher = await service._get_template_matcher(domain_code or "coal")` | `matcher = await service._get_template_matcher(domain_code or GENERAL_DOMAIN_CODE)` |
| :751 | `match_result = matcher.match(title, context={"domain": domain_code or "coal"})` | `context={"domain": domain_code or GENERAL_DOMAIN_CODE}` |
| :4360 | `domain = self._normalize_domain_for_graph(task_detail.get("domain") or "coal")` | `or GENERAL_DOMAIN_CODE)` |
| :4719 | `service._normalize_domain_for_graph(task_detail.get("domain") or "coal"),` | `or GENERAL_DOMAIN_CODE),` |
| :5444 | `domain_code = task_detail.get("domain", "coal")` | `task_detail.get("domain", GENERAL_DOMAIN_CODE)` |
| :5898 | `domain_code = detail.get("domain") or "coal"` | `or GENERAL_DOMAIN_CODE` |
| :6111 | `domain_code = template_metadata.get("domain_code") or detail.get("domain") or "coal"` | 末尾 `or GENERAL_DOMAIN_CODE` |
| :6157 | 同 :6111 模式 | 同上 |

- [ ] **Step 3: create_task 去掉域校验（:582-584）**

```python
        domain = await self.repo.get_domain_by_code(domain_code)
        if not domain:
            raise ValueError(f"Domain not found: {domain_code}")
```
改为（router 阶段 1 起恒传 "general"，见 Task 5；上传目录仍用 domain_code 参数）：

```python
        # 去领域化：不再按传入 domain 查表校验，外键统一指向通用域行
        domain = await self.repo.get_or_create_general_domain()
```

- [ ] **Step 4: 全文件残留检查**

```bash
grep -n '"coal"' backend/package/yuxi/services/domain_factory_service.py
```
Expected: 仅剩 `LOCAL_SCHEMA_MAP` 的两个键（`"coal.eia_construction"`、`"coal.eia_planning"`，Task 3 处理）。若有其他残留，逐处按同规则替换。

- [ ] **Step 5: 回归**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/integration/api/test_domain_factory_api.py /app/test/unit/repositories/test_domain_factory_domain_aliases.py -v
```
Expected: PASS（既有用例不触达这些路径，单测不变绿）。

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "refactor(domain-factory): 服务层 coal 兜底字面量收敛为 GENERAL_DOMAIN_CODE，create_task 外键指向通用域行

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: LOCAL_SCHEMA_MAP 键改 general 前缀

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（:2340-2376 与 `_get_local_schema` :2396-2404）

- [ ] **Step 1: 改键**

只做两处键字符串替换，**字典值一律不动**：

- `'coal.eia_construction'` → `'general.eia_construction'`（:2341）
- `'coal.eia_planning'` → `'general.eia_planning'`（:2376）

`_get_local_schema`（:2396-2404）的逻辑本身是前缀匹配（`key = f"{domain_code}.{report_type_code}"`、`k.startswith(f"{domain_code}.")`），**不需要改**——上游传入的 domain_code 恒为 general 后自动命中新键。

- [ ] **Step 2: 残留清零检查**

```bash
grep -n 'coal' backend/package/yuxi/services/domain_factory_service.py | grep -v '^.*#' | grep -iv 'coal_'
```
Expected: 0 行（注释与 coal_eia 等 skill 命名除外，若剩纯注释提及 coal 可留）。

- [ ] **Step 3: 语法验证 + 回归**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/integration/api/test_domain_factory_api.py -v
```
Expected: OK；测试 PASS。

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "refactor(domain-factory): LOCAL_SCHEMA_MAP 键去 coal 前缀改 general

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 写手工具——签名保留、内部强制 general

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`（导入 :24-27；五处 `domain = _normalize_domain(domain)` :632/:709/:733/:780/:850）

- [ ] **Step 1: 导入常量**

:24-27 的导入块补 `GENERAL_DOMAIN_CODE`：

```python
from yuxi.repositories.domain_factory_repository import (
    GENERAL_DOMAIN_CODE,
    DomainFactoryRepository,
    _normalize_domain,
)
```

- [ ] **Step 2: 五处强制覆盖**

把五个工具函数体内的 `domain = _normalize_domain(domain)` 统一改为：

```python
    domain = GENERAL_DOMAIN_CODE  # 去领域化：形参保留兼容写手 prompts，语义恒通用域
```

涉及函数：`get_chapter_outline`(:632)、`list_report_types`(:709)、`list_chapter_keys`(:733)、`get_templates`(:780)、`create_report`(:850)。`_normalize_domain` 导入若再无其他引用则从导入块删除（先 grep 确认）。

- [ ] **Step 3: 验证**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/agents/toolkits/buildin/tools.py', encoding='utf-8').read()); print('OK')"
grep -n '_normalize_domain' backend/package/yuxi/agents/toolkits/buildin/tools.py
```
Expected: OK；grep 只剩导入行（或无，若已删）。

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py
git commit -m "refactor(agent-tools): 知识工厂五工具 domain 入参内部强制通用域（签名不变，写手侧零改动）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 路由阶段 1——参数降级为「收下但忽略」

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（upload :505-554；data-sources :124-133；history :140-149；tasks-center :619-621；outline-templates 段 :750/:772/:799/:867/:896/:923）

- [ ] **Step 1: upload 忽略客户端 domain（:508 签名保留 Form 默认值，:525/:529 改传常量）**

```python
@domain_factory.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    domain: str = Form("general"),  # 阶段1 兼容保留：客户端值被忽略，阶段3 删参
    document_type: str = Form("通用"),
    report_type_code: str = Form("通用"),
    source_report_id: str | None = Form(None),
    chapter_label: str | None = Form(None),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
```

并在文件顶部导入区加 `from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE`，函数体内两处改：

```python
        task_id, storage_path = await service.save_uploaded_file(file_content, file.filename, GENERAL_DOMAIN_CODE)
```
```python
        await service.create_task(
            domain_code=GENERAL_DOMAIN_CODE,
            ...
        )
```
响应体 `"domain": domain` 改为 `"domain": GENERAL_DOMAIN_CODE`。

- [ ] **Step 2: 三个查询端点忽略 domain 过滤**

`GET /data-sources`（:124-133）、`GET /history`（:140-149）、`GET /tasks-center`（:619-621）：Query 参数保留签名，调用服务时 domain 实参改传 `None`（不过滤；存量迁移后全量即通用域）：

```python
    domain: str | None = Query(None),  # 阶段1 兼容保留：忽略，阶段3 删参
    ...
    tasks = await service.list_pending_tasks(None)
```

- [ ] **Step 3: outline-templates 段 6 处传常量**

:750/:772/:799（Query 默认值改 `"general"`）、:867（Form 同）、:896/:923（`body.get("domain", "coal")` → `body.get("domain", GENERAL_DOMAIN_CODE)`），且调用 service 时统一传 `GENERAL_DOMAIN_CODE` 字面量、不用客户端值：

```python
            items = await svc.list_outline_templates(GENERAL_DOMAIN_CODE, report_type)
```
（:760/:782/:809/:880/:903/:926 六个调用点同规则。）

- [ ] **Step 4: 验证 + 回归 + Commit**

```bash
python -c "import ast; ast.parse(open('backend/server/routers/domain_factory_router.py', encoding='utf-8').read()); print('OK')"
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/integration/api/test_domain_factory_api.py -v
git add backend/server/routers/domain_factory_router.py
git commit -m "refactor(domain-factory): 路由 domain 参数降级为收下但忽略（阶段1，阶段3 删参）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```
Expected: OK；PASS。

---

### Task 6: 数据脚本——存量 coal → general（B2，幂等）

**Files:**
- Create: `scripts/governance/dedomain_coal_to_general.py`

- [ ] **Step 1: 写脚本**

```python
"""去领域化存量迁移：domain_code 'coal' → 'general'（设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md §4.1）。

幂等可重跑。默认 dry-run 只统计；--apply 才写库。
用法（宿主仓库根执行，脚本经 stdin 进容器）：
    MSYS_NO_PATHCONV=1 docker exec -i api-dev python - < scripts/governance/dedomain_coal_to_general.py -- --apply
（不带 -- --apply 即 dry-run）
"""
import argparse
import asyncio

from sqlalchemy import text

from yuxi.repositories.domain_factory_repository import (
    GENERAL_DOMAIN_CODE,
    GENERAL_DOMAIN_NAME,
    DomainFactoryRepository,
)
from yuxi.storage.postgres.manager import pg_manager

# (表, 域列)。含 report_types 与 domain_entity_schemas（数据字典，写手工具查询依赖）。
# 执行前先核对表名列名：grep __tablename__ backend/package/yuxi/storage/postgres/models_domain_entity.py
TARGETS = [
    ("domain_factory_learned_templates", "domain_code"),
    ("domain_factory_outlines", "domain_code"),
    ("domain_factory_prompt_configs", "domain_code"),
    ("domain_factory_reports", "domain_code"),
    ("domain_factory_tool_usage", "domain"),
    ("report_types", "domain_code"),
    ("domain_entity_schemas", "domain_code"),
]


async def main(apply: bool) -> None:
    repo = DomainFactoryRepository()
    general = await repo.get_or_create_general_domain()
    print(f"通用域行: id={general.id} code={general.code}")

    async with pg_manager.get_async_session_context() as session:
        for table, col in TARGETS:
            rows = (
                await session.execute(
                    text(f"SELECT {col}, count(*) FROM {table} WHERE {col} <> :c GROUP BY {col}"),
                    {"c": GENERAL_DOMAIN_CODE},
                )
            ).all()
            print(f"[{'apply' if apply else 'dry-run'}] {table}.{col} 待迁移: {rows}")
            if apply and rows:
                await session.execute(
                    text(f"UPDATE {table} SET {col} = :c WHERE {col} <> :c"),
                    {"c": GENERAL_DOMAIN_CODE},
                )

        task_rows = (
            await session.execute(
                text(
                    "SELECT count(*) FROM domain_factory_tasks t "
                    "JOIN domain_factory_domains d ON t.domain_id = d.id "
                    "WHERE d.code <> :c"
                ),
                {"c": GENERAL_DOMAIN_CODE},
            )
        ).scalar()
        print(f"[{'apply' if apply else 'dry-run'}] domain_factory_tasks 待重指向: {task_rows}")
        if apply and task_rows:
            await session.execute(
                text(
                    "UPDATE domain_factory_tasks t SET domain_id = :gid "
                    "FROM domain_factory_domains d WHERE t.domain_id = d.id AND d.code <> :c"
                ),
                {"gid": general.id, "c": GENERAL_DOMAIN_CODE},
            )
    print("完成（general 行名为 " + GENERAL_DOMAIN_NAME + "；domains 表其他历史行冻结保留）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    asyncio.run(main(parser.parse_args().apply))
```

- [ ] **Step 2: 核对表名列名**

```bash
grep -n "__tablename__" backend/package/yuxi/storage/postgres/models_domain_entity.py
```
若 `DomainEntitySchema` 的表名不是 `domain_entity_schemas`，修正 TARGETS 对应行。

- [ ] **Step 3: 容器内导入自检 + dry-run**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev python -c "import yuxi; print('import OK')"
MSYS_NO_PATHCONV=1 docker exec -i api-dev python - < scripts/governance/dedomain_coal_to_general.py
```
Expected: `import OK`；dry-run 打印各表待迁移统计（learned_templates 应有 ~1055 条量级的大纲/模板数据或其他非 general 值统计）。

- [ ] **Step 4: apply + 复跑验证幂等**

```bash
MSYS_NO_PATHCONV=1 docker exec -i api-dev python - < scripts/governance/dedomain_coal_to_general.py -- --apply
MSYS_NO_PATHCONV=1 docker exec -i api-dev python - < scripts/governance/dedomain_coal_to_general.py -- --apply
```
Expected: 第一次打印非空统计并迁移；第二次全部为空列表/0（幂等）。

- [ ] **Step 5: 冒烟验证迁移效果**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev python -c "
import asyncio
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository
async def main():
    repo = DomainFactoryRepository()
    print('domains:', [d['code'] for d in await repo.list_domains()])
    print('learned by general:', len(await repo.list_learned_templates(domain_code='general', limit=5)))
    print('chapter keys:', len(await repo.list_chapter_keys('general', 'eia_report')))
asyncio.run(main())
"
```
Expected: `general` 在 domains 列表中；learned/chapter keys 迁移后可按 general 查到。

- [ ] **Step 6: Commit**

```bash
git add scripts/governance/dedomain_coal_to_general.py
git commit -m "chore(domain-factory): 去领域化存量迁移脚本 coal→general（幂等，dry-run 默认）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 前端——api.js 摘除 domains 方法

**Files:**
- Modify: `web/src/apis/domain_factory_api.js`

- [ ] **Step 1: 删除四个 domains 方法与 demo 数据的 domain 参数化**

- 删除 `getDomains`(:118-120 附近)、`createDomain`(:123-127)、`updateDomain`(:129-133)、`deleteDomain`(:135-138) 四个方法。
- `buildDemoTasks`/`buildDemoHistory`(:29-63) 去掉 `domain` 形参，`domain: 'general'`、`domain_label: '通用域'` 写死；`DEMO_CONTEXTS`(:65-66) 的 `domain: 'demo'` 改 `'general'`、label `'通用域'`。
- `fetchDataSources`/`fetchHistory` 的 demo 回退里 `params?.domain || 'coal'` → `'general'`。

- [ ] **Step 2: 验证 + Commit**

```bash
cd web && pnpm run lint && cd ..
grep -n "getDomains\|createDomain\|updateDomain\|deleteDomain" web/src/apis/domain_factory_api.js
```
Expected: lint 过；grep 0 行。

```bash
git add web/src/apis/domain_factory_api.js
git commit -m "refactor(web): 去领域化——domain_factory_api 摘除 domains CRUD 方法

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 前端——GeneralDataView + DataSourceDashboard 摘除领域 UI

**Files:**
- Modify: `web/src/views/GeneralDataView.vue`
- Modify: `web/src/components/domain-factory/DataSourceDashboard.vue`

- [ ] **Step 1: GeneralDataView 简化为纯容器**

删除 domains/selectedDomain/loadingDomains 状态、fetchDomains、handleDomainChange（:22-52），template 只留：

```vue
<template>
  <!-- [pisuan-custom] 通用域「数据源管理」屏：去领域化后无领域维度 -->
  <DataSourceDashboard @task-open="handleTaskOpen" />
</template>
```

`handleTaskOpen` 与 router 逻辑（:54-57）保留。

- [ ] **Step 2: DataSourceDashboard script 摘除**

逐处（锚点为 2026-10-29 工作树）：
- props 删 `domains`/`selectedDomain`/`loadingDomains`，emits 删 `update:domain`/`domains-refreshed`（:11-16）。
- 删 `localDomain`/`handleDomainChange`/`domainOptions`（:118-133）。
- `fetchTasks`/`fetchHistory`（:165-191）去掉 domain 参数逻辑，`fetchDataSources()`/`fetchHistory()` 不再传 domain。
- 删 `newDomain`/`handleCreateDomain`（:305-320 附近）。
- 上传表单：删 `uploadDomain` 状态与 `typeOptions` 的按域解析（:327-350），`openUpload` 不再依赖 `props.domains`；`handleUpload`（:428-455）删「请选择行业领域」校验与 `formData.append('domain', ...)`（:437）。

- [ ] **Step 3: DataSourceDashboard template 摘除**

- 删领域筛选卡整块 `<div class="domain-card">…</div>`（:512-535，含内部新建领域按钮）。
- 删 pending 表「领域」列与 history 表「领域」列（列定义 :602 与 :712 的 `<span>{{ record.domain_label }}</span>` 单元格及对应 column 配置）。
- 上传弹窗删「行业领域」表单项（:762-766）。

- [ ] **Step 4: 样式清理**

删除仅被 domain-card 使用的样式（:932-960 附近的 `.domain-card/.domain-toolbar/.domains`）——先 grep 确认无其他引用再删。

- [ ] **Step 5: 验证**

```bash
cd web && pnpm run lint && cd ..
grep -rn "行业领域\|selectedDomain\|domains-refreshed\|createDomain" web/src/views/GeneralDataView.vue web/src/components/domain-factory/DataSourceDashboard.vue
```
Expected: lint 过；grep 0 行。

- [ ] **Step 6: Commit**

```bash
git add web/src/views/GeneralDataView.vue web/src/components/domain-factory/DataSourceDashboard.vue
git commit -m "refactor(web): 数据源管理屏摘除领域筛选/新建领域/行业下拉/领域列

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 前端——剩余组件摘除

**Files:**
- Modify: `web/src/components/domain-factory/OutlineTemplate.vue`
- Modify: `web/src/components/domain-factory/AttributionTaskTable.vue`
- Modify: `web/src/views/DomainEntityBuilderView.vue`
- Modify: `web/src/views/PromptConfigView.vue`
-（EtlWorkbench.vue **不改**：:1019 领域 tag 显示 `domain_label`，迁移后数据即「通用域」，零改动达成；:103-105 `task.domain` 迁移后即 'general'，语义正确）

- [ ] **Step 1: OutlineTemplate**

删领域下拉（:12-14）与 `selectedDomain`/`domains` 状态（:284 附近）及其 fetchDomains（:377-383）；所有请求参数删 `domain: selectedDomain.value`（:360/:415/:438/:479），后端阶段 1 已忽略、阶段 3 删参。

- [ ] **Step 2: AttributionTaskTable**

删「领域」列定义（:31）。

- [ ] **Step 3: DomainEntityBuilderView**

先读 :640-870 确认 `domainOptions`（:691）的数据来源：若来自实体分组 taxonomy（project_basic 等），:19/:486 的使用**保留**（那是实体分组筛选，不是行业维度）；仅删「行业 (domain_code)」表单项（:142-146），并把 :852 `copy.domain_code = copy.domain_code || currentDomain.value` 改为 `copy.domain_code = 'general'`。

- [ ] **Step 4: PromptConfigView**

:96 模板文本 `## 行业领域：` → `## 文档类型：`。

- [ ] **Step 5: 验证 + Commit**

```bash
cd web && pnpm run lint && cd ..
grep -rn "行业领域" web/src/
```
Expected: lint 过；grep 0 行。

```bash
git add web/src/components/domain-factory/OutlineTemplate.vue web/src/components/domain-factory/AttributionTaskTable.vue web/src/views/DomainEntityBuilderView.vue web/src/views/PromptConfigView.vue
git commit -m "refactor(web): 大纲模板/归属/实体字典/提示词配置摘除行业领域维度

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: 阶段 3——路由删参 + domains 端点下线 + 测试收口

**Files:**
- Test (modify): `backend/test/integration/api/test_domain_factory_api.py`
- Modify: `backend/server/routers/domain_factory_router.py`
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（仅删 4 个 domains CRUD 包装方法）

- [ ] **Step 1: 先写/改集成测试（TDD：本任务的目标态）**

`backend/test/integration/api/test_domain_factory_api.py` 改造：
- :13-19 `test_get_domains_admin_ok` 删除（端点下线）。
- :55-60 遍历断言中的 `/api/domain-factory/domains` 从标准用户 403 用例路径列表里移除。
- :73-75 未认证用例从 `/domains` 改打 `/api/domain-factory/data-sources`。
- 新增两个用例（追加到文件，风格与现有一致）：

```python
async def test_upload_without_domain_field_ok(test_client, admin_headers):
    """去领域化：上传不再要求 domain 表单字段，响应 domain 恒 general。"""
    files = {"file": ("dedomain-smoke.txt", b"通用域去领域化冒烟内容", "text/plain")}
    res = await test_client.post("/api/domain-factory/upload", headers=admin_headers, files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["domain"] == "general"


async def test_contexts_single_general_domain(test_client, admin_headers):
    """去领域化：contexts 只返回通用域单元素。"""
    res = await test_client.get("/api/domain-factory/contexts", headers=admin_headers)
    assert res.status_code == 200
    domains = res.json().get("domains") or []
    assert [d["code"] for d in domains] == ["general"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/integration/api/test_domain_factory_api.py -v
```
Expected: `test_upload_without_domain_field_ok` FAIL（422，domain 必填）；`test_contexts_single_general_domain` 可能 PASS（迁移后数据已单域，端点分组逻辑未删则返回多组——若历史 domains 行导致多元素则 FAIL）。

- [ ] **Step 3: 删参 + 下线端点**

router：
- upload 删 `domain: str = Form("general")` 参数与 :525/:529 的实参（service 侧 create_task 的 domain_code 形参**保留**，router 传 `GENERAL_DOMAIN_CODE`）；响应体 `"domain": GENERAL_DOMAIN_CODE` 保留。
- :124-133/:140-149/:619-621 删 Query(domain) 参数（Task 5 已改传 None，此处删参即可）。
- outline-templates 段 :750/:772/:799 删 Query 参数、:867 删 Form 参数、:896/:923 删 `body.get("domain", ...)`，调用点恒传 `GENERAL_DOMAIN_CODE`（Task 5 已就位）。
- 删 domains CRUD 三端点（:44-122）。

service：删 `get_domains`/`create_domain`/`update_domain`/`delete_domain` 四个包装方法（:463-477 附近；repo 方法保留不触达）。

- [ ] **Step 4: 跑测试确认通过**

```bash
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/integration/api/test_domain_factory_api.py /app/test/unit/repositories/test_domain_factory_domain_aliases.py -v
```
Expected: 全 PASS。若 `test_contexts_single_general_domain` 因 contexts 响应含历史 coal 组而失败：检查 service contexts 聚合（:5773-5776）——迁移后 report_types 全为 general，正常应只剩一组；若仍多组，按分组逻辑排查数据而非改代码掩盖。

- [ ] **Step 5: Commit**

```bash
git add backend/server/routers/domain_factory_router.py backend/package/yuxi/services/domain_factory_service.py backend/test/integration/api/test_domain_factory_api.py
git commit -m "refactor(domain-factory): 路由 domain 参数删除、domains CRUD 下线，集成测试收口去域契约

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: 收尾——changelog + 全量回归 + E2E 冒烟

**Files:**
- Modify: `docs/develop-guides/changelog.md`

- [ ] **Step 1: changelog 条目**

在 `docs/develop-guides/changelog.md` 顶部日期区块追加：

```markdown
- 通用域知识工厂去领域化（行为级）：「行业领域」维度废弃，后端收敛为 GENERAL_DOMAIN_CODE='general'
  常量（服务层 8 处兜底、LOCAL_SCHEMA_MAP 键、写手五工具内部覆盖、路由参数收下即忽略→删除）；
  前端数据源管理/大纲模板/归属/实体字典摘除领域 UI；存量数据迁移脚本
  scripts/governance/dedomain_coal_to_general.py（8 表 coal→general + tasks 重指向，幂等）。
  domains 表冻结保留，/eia 段与写手 prompts 零改动。设计：docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md
```

- [ ] **Step 2: 全量回归**

```bash
make format
MSYS_NO_PATHCONV=1 docker exec api-dev pytest /app/test/unit/repositories/ /app/test/integration/api/test_domain_factory_api.py -v
cd web && pnpm run lint && cd ..
```
Expected: format 无 diff 或自动修完；测试全 PASS；lint 过。

- [ ] **Step 3: E2E 冒烟（需栈内 LLM key 可用；凭据读 .env 的管理员账号）**

```bash
# 1) 登录取 token（ADMIN 用户密码见 .env）
curl -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"<admin>","password":"<password>"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
# 2) 无 domain 字段上传
curl -s -X POST http://localhost:8000/api/domain-factory/upload -H "Authorization: Bearer <token>" \
  -F file=@<任一小体积 md/txt 样例>
# Expected: {"success":true,...,"domain":"general"}
# 3) 轮询任务至 WAITING_REVIEW（泛化依赖 LLM，约数分钟）
curl -s http://localhost:8000/api/domain-factory/data-sources -H "Authorization: Bearer <token>"
# Expected: 新任务 status 经 PARSING→GENERALIZING→WAITING_REVIEW
```

完整「审核→提交→入库」段（commit→Milvus→图谱）不在 headless 冒烟范围——泛化完成后在 UI（EtlWorkbench）人工走完三步向导并提交，核对 KB 出现新文档、图谱落 `*_general_*` 键，对应 spec §4.4 验收单。

- [ ] **Step 4: 提交收尾 + 汇报**

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(changelog): 通用域去领域化（行为级）落地记录

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

汇报内容须含：迁移脚本两轮输出（证明幂等）、测试结果、E2E 冒烟截图/响应。
