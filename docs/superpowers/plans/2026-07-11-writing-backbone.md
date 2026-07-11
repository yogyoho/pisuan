# 写作侧确定性骨架 Implementation Plan (子项目 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把写作侧 PPS / 章节注册表 / `{{REF}}` / 装配从"LLM 自觉维护 markdown"升级为 DB 持久化 + 确定性装配 + 子 agent 编排,支撑环评报告跨会话点状写作。

**Architecture:** 3 张新表(reports / report_chapters / report_pps)+ 5 个 buildin 工具(create_report / get_report / set_pps_param / save_chapter / assemble_report)+ 纯代码 `{{REF}}` resolver(assemble 时扫 content 现算)+ chapter-writer 子 agent(coal-eia-writer 升级为编排者,每章派临时实例)。Phase A(任务 1-5)= 后端确定性核心,可独立交付;Phase B(任务 6-8)= agent 编排。

**Tech Stack:** Python 3.13 / SQLAlchemy 异步 / FastAPI / LangChain `@tool` + `ToolRuntime` / 子 agent 机制(`ensure_*_subagent` + `subagent_start`/`task`)/ Pytest。

## Global Constraints

- pythonic,3.12+ 语法;中文提交,Conventional Commits。
- DB 迁移靠 `backend/package/yuxi/storage/postgres/manager.py` DDL 列表(`CREATE/ALTER ... IF NOT EXISTS`),无 Alembic;`create_all()` 只建不存在的表,新列必须配幂等 ALTER。
- 改文件后 `make format`(`python -m ruff format` + `ruff check`);测试在容器跑:`docker exec api-dev pytest /app/test/unit/<path> -v`。
- **Surgical**:`domain_factory_service.py` / `tools.py` 等大文件只改目标段,不整文件 reformat(改后 `git diff --cached --stat` 自检)。
- **复用优先**:桥(子项目1)的 `get_chapter_outline` / `get_templates` / `domain_factory_outlines` / `entity_bindings`;既有 `present_artifacts` / `subagent_start` / `task` / `ensure_*_subagent`。
- 命名:报告主句柄是 `report_id`(跨会话);`{{REF}}` 位置编号 `{{REF:chXX/表X-Y}}`;PPS 的 `entity_key` 链桥 `entity_bindings`。
- **前置依赖**:子项目 1(桥)已完成(commit `38a86def` 及之前);子 agent 机制已有。

---

## File Structure

| 文件 | 责任 | 动作 | 任务 |
|---|---|---|---|
| `backend/package/yuxi/storage/postgres/models_domain_factory.py` | 3 个新模型 `DomainFactoryReport`/`ReportChapter`/`ReportPps` | 改 | 1 |
| `backend/package/yuxi/storage/postgres/manager.py` | 3 张表 DDL | 改 | 1 |
| `backend/package/yuxi/repositories/domain_factory_repository.py` | report/chapter/pps CRUD | 改 | 1 |
| `backend/package/yuxi/services/ref_resolver.py` | `{{REF}}` resolver(纯代码) | 建 | 4 |
| `backend/package/yuxi/agents/toolkits/buildin/tools.py` | 5 个新 `@tool` | 改 | 2,3,5 |
| `backend/package/yuxi/repositories/agent_repository.py` | `ensure_chapter_writer_subagent` | 改 | 6 |
| `backend/server/utils/lifespan.py` | 启动注册 chapter-writer | 改 | 6 |
| `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md` | 改为编排者工作流 | 改 | 7 |
| `backend/test/unit/services/test_ref_resolver.py` | resolver 单测 | 建 | 4 |
| `backend/test/unit/toolkits/test_report_tools.py` | 报告工具单测 | 建 | 2,3,5 |
| `backend/test/unit/storage/test_report_repo.py` | 存储 CRUD 单测 | 建 | 1 |
| `docs/develop-guides/changelog.md` | 记录 | 改 | 8 |

---

# Phase A — 后端确定性核心(独立可交付)

## Task 1: 存储——3 张表 + repository

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`
- Modify: `backend/package/yuxi/storage/postgres/manager.py`
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`
- Test: `backend/test/unit/storage/test_report_repo.py`(建)

**Interfaces:**
- Produces: 模型 `DomainFactoryReport` / `DomainFactoryReportChapter` / `DomainFactoryReportPps`;repo 方法 `create_report(...)`、`get_report_snapshot(report_id)`、`upsert_pps_param(...)`、`upsert_chapter(...)`、`list_chapters(report_id, status_only=None)`。任务 2/3/5 消费。

- [ ] **Step 1: 写失败测试**

创建 `backend/test/unit/storage/test_report_repo.py`:

```python
import pytest
from yuxi.storage.postgres.manager import pg_manager
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    await pg_manager.close()
    pg_manager._initialized = False


@pytest.mark.asyncio
async def test_create_report_and_chapter_and_pps():
    repo = DomainFactoryRepository()
    rep = await repo.create_report(
        thread_id="t1", title="伊宁矿区环评", domain_code="coal",
        report_type_code="eia_report", kb_id="kb_x", created_by="admin",
    )
    assert rep["id"]
    rid = rep["id"]

    ch = await repo.upsert_chapter(
        report_id=rid, canonical_chapter_key="地下水环境影响预测",
        chapter_order=5, title="5 地下水", content_md="正文…", summary="地下水预测",
        status="done",
    )
    assert ch["status"] == "done"

    pps = await repo.upsert_pps_param(
        report_id=rid, entity_key="groundwater_level", name="地下水位",
        value="10", value_type="number", unit="m", source="监测",
    )
    assert pps["value"] == "10"

    snap = await repo.get_report_snapshot(rid)
    assert snap["status"] == "draft"
    assert any(c["canonical_chapter_key"] == "地下水环境影响预测" for c in snap["chapters"])
    assert any(p["entity_key"] == "groundwater_level" for p in snap["pps"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec api-dev pytest /app/test/unit/storage/test_report_repo.py -v`
Expected: FAIL(模型/方法未定义)

- [ ] **Step 3: 加 3 个模型**(追加到 `models_domain_factory.py` 末尾)

```python
class DomainFactoryReport(Base):
    """写作侧 - 报告根对象"""
    __tablename__ = "domain_factory_reports"
    id = Column(String(64), primary_key=True)
    title = Column(Text, nullable=False)
    domain_code = Column(String(64), nullable=False)
    report_type_code = Column(String(64), nullable=False, default="通用")
    kb_id = Column(String(128), nullable=True)
    thread_id = Column(String(64), nullable=True)  # 创建会话溯源
    status = Column(String(32), nullable=False, default="draft")  # draft|writing|assembled
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class DomainFactoryReportChapter(Base):
    """写作侧 - 章节注册表(确定性)"""
    __tablename__ = "domain_factory_reports_chapters"
    __table_args__ = (
        UniqueConstraint("report_id", "canonical_chapter_key", name="uq_dfrch_report_key"),
        Index("idx_dfrch_report", "report_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), nullable=False, index=True)
    canonical_chapter_key = Column(Text, nullable=False)
    chapter_order = Column(Integer, nullable=True)  # outline 序
    title = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")  # pending|writing|done|skipped
    content_md = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {"canonical_chapter_key": self.canonical_chapter_key,
                "chapter_order": self.chapter_order, "title": self.title,
                "status": self.status, "summary": self.summary}


class DomainFactoryReportPps(Base):
    """写作侧 - PPS 项目级参数值"""
    __tablename__ = "domain_factory_reports_pps"
    __table_args__ = (
        UniqueConstraint("report_id", "entity_key", name="uq_dfrpps_report_entity"),
        Index("idx_dfrpps_report", "report_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), nullable=False, index=True)
    entity_key = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(32), nullable=True)  # number|string|enum
    unit = Column(String(64), nullable=True)
    source = Column(Text, nullable=True)
    confidence = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {"entity_key": self.entity_key, "name": self.name, "value": self.value,
                "value_type": self.value_type, "unit": self.unit, "source": self.source}
```

- [ ] **Step 4: 加 DDL**(追加到 `manager.py` 的 domain_factory DDL 段)

```python
            "CREATE TABLE IF NOT EXISTS domain_factory_reports ("
            "    id VARCHAR(64) PRIMARY KEY,"
            "    title TEXT NOT NULL,"
            "    domain_code VARCHAR(64) NOT NULL,"
            "    report_type_code VARCHAR(64) NOT NULL DEFAULT '通用',"
            "    kb_id VARCHAR(128),"
            "    thread_id VARCHAR(64),"
            "    status VARCHAR(32) NOT NULL DEFAULT 'draft',"
            "    created_by VARCHAR(64),"
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE TABLE IF NOT EXISTS domain_factory_reports_chapters ("
            "    id SERIAL PRIMARY KEY,"
            "    report_id VARCHAR(64) NOT NULL,"
            "    canonical_chapter_key TEXT NOT NULL,"
            "    chapter_order INTEGER,"
            "    title TEXT,"
            "    status VARCHAR(32) NOT NULL DEFAULT 'pending',"
            "    content_md TEXT,"
            "    summary TEXT,"
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    UNIQUE(report_id, canonical_chapter_key)"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_dfrch_report ON domain_factory_reports_chapters(report_id)",
            "CREATE TABLE IF NOT EXISTS domain_factory_reports_pps ("
            "    id SERIAL PRIMARY KEY,"
            "    report_id VARCHAR(64) NOT NULL,"
            "    entity_key TEXT NOT NULL,"
            "    name TEXT,"
            "    value TEXT,"
            "    value_type VARCHAR(32),"
            "    unit VARCHAR(64),"
            "    source TEXT,"
            "    confidence VARCHAR(32),"
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    UNIQUE(report_id, entity_key)"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_dfrpps_report ON domain_factory_reports_pps(report_id)",
```

- [ ] **Step 5: 加 repository 方法**(追加到 `DomainFactoryRepository` 类,`upsert_outline` 附近;用 `hashstr` 生成 report id,与项目惯例一致)

```python
    async def create_report(self, *, thread_id, title, domain_code, report_type_code, kb_id, created_by) -> dict:
        from yuxi.utils.func_utils import hashstr  # 项目既有
        import uuid
        rid = f"rpt_{hashstr(thread_id + title + str(uuid.uuid4()), 10)}"
        async with pg_manager.get_async_session_context() as session:
            row = DomainFactoryReport(id=rid, title=title, domain_code=domain_code,
                                      report_type_code=report_type_code or "通用", kb_id=kb_id,
                                      thread_id=thread_id, status="draft", created_by=created_by)
            session.add(row)
            await session.commit()
        return {"id": rid, "title": title, "status": "draft"}

    async def get_report_snapshot(self, report_id) -> dict | None:
        async with pg_manager.get_async_session_context() as session:
            r = (await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))).scalar_one_or_none()
            if not r:
                return None
            chs = (await session.execute(select(DomainFactoryReportChapter).where(DomainFactoryReportChapter.report_id == report_id).order_by(DomainFactoryReportChapter.chapter_order))).scalars().all()
            pps = (await session.execute(select(DomainFactoryReportPps).where(DomainFactoryReportPps.report_id == report_id))).scalars().all()
            return {"id": r.id, "title": r.title, "status": r.status,
                    "report_type_code": r.report_type_code, "domain_code": r.domain_code, "kb_id": r.kb_id,
                    "pps": [p.to_dict() for p in pps],
                    "chapters": [c.to_dict() for c in chs],
                    "registry": [{"canonical_chapter_key": c.canonical_chapter_key, "title": c.title, "summary": c.summary}
                                 for c in chs if c.status == "done"]}

    async def upsert_pps_param(self, *, report_id, entity_key, name, value, value_type, unit, source, confidence=None) -> dict:
        async with pg_manager.get_async_session_context() as session:
            row = (await session.execute(select(DomainFactoryReportPps).where(
                DomainFactoryReportPps.report_id == report_id, DomainFactoryReportPps.entity_key == entity_key))).scalar_one_or_none()
            if row is None:
                row = DomainFactoryReportPps(report_id=report_id, entity_key=entity_key, name=name,
                                             value=value, value_type=value_type, unit=unit, source=source, confidence=confidence)
                session.add(row)
            else:
                row.name, row.value, row.value_type, row.unit, row.source = name, value, value_type, unit, source
                if confidence: row.confidence = confidence
            await session.commit()
            return row.to_dict()

    async def upsert_chapter(self, *, report_id, canonical_chapter_key, chapter_order=None, title=None,
                             content_md=None, summary=None, status="writing") -> dict:
        async with pg_manager.get_async_session_context() as session:
            row = (await session.execute(select(DomainFactoryReportChapter).where(
                DomainFactoryReportChapter.report_id == report_id,
                DomainFactoryReportChapter.canonical_chapter_key == canonical_chapter_key))).scalar_one_or_none()
            if row is None:
                row = DomainFactoryReportChapter(report_id=report_id, canonical_chapter_key=canonical_chapter_key,
                                                 chapter_order=chapter_order, title=title, content_md=content_md,
                                                 summary=summary, status=status)
                session.add(row)
            else:
                if chapter_order is not None: row.chapter_order = chapter_order
                if title is not None: row.title = title
                if content_md is not None: row.content_md = content_md
                if summary is not None: row.summary = summary
                row.status = status
            # 报告状态推进
            rpt = (await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))).scalar_one_or_none()
            if rpt and rpt.status == "draft": rpt.status = "writing"
            await session.commit()
            return row.to_dict()

    async def list_chapters(self, report_id, status_only=None) -> list[dict]:
        async with pg_manager.get_async_session_context() as session:
            stmt = select(DomainFactoryReportChapter).where(DomainFactoryReportChapter.report_id == report_id).order_by(DomainFactoryReportChapter.chapter_order)
            if status_only: stmt = stmt.where(DomainFactoryReportChapter.status == status_only)
            rows = (await session.execute(stmt)).scalars().all()
            return [{"canonical_chapter_key": r.canonical_chapter_key, "chapter_order": r.chapter_order,
                     "title": r.title, "status": r.status, "content_md": r.content_md, "summary": r.summary} for r in rows]
```

> `hashstr` 的确切导入路径以代码库为准(项目已有,如 `yuxi.utils.func_utils` 或 `yuxi.utils`);implementer 用 `grep -rn "def hashstr" backend/package` 确认后导入。

- [ ] **Step 6: 重启 api-dev 让 DDL 生效,跑测试**

```bash
docker restart api-dev && sleep 30
docker exec api-dev pytest /app/test/unit/storage/test_report_repo.py -v
```
Expected: PASS

- [ ] **Step 7: surgical ruff + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/storage/postgres/models_domain_factory.py package/yuxi/storage/postgres/manager.py package/yuxi/repositories/domain_factory_repository.py
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/storage/test_report_repo.py
git commit -m "feat(writing-backbone): report/chapter/pps 存储 + repository"
```

---

## Task 2: 工具——create_report / get_report / set_pps_param

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`
- Test: `backend/test/unit/toolkits/test_report_tools.py`(建)

**Interfaces:**
- Consumes: Task 1 的 `create_report` / `get_report_snapshot` / `upsert_pps_param`。
- Produces: 3 个 `@tool`(category="buildin")。

- [ ] **Step 1: 写失败测试**

创建 `backend/test/unit/toolkits/test_report_tools.py`:

```python
import pytest
from unittest.mock import AsyncMock
import yuxi.agents.toolkits.buildin.tools as tools_mod


@pytest.mark.asyncio
async def test_create_report_tool(monkeypatch):
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository",
                        lambda: AsyncMock(create_report=AsyncMock(return_value={"id": "rpt_1", "title": "T", "status": "draft"})))
    out = await tools_mod.create_report.ainvoke(
        {"thread_id": "t1", "title": "T", "domain": "coal", "report_type": "eia_report", "kb_id": "kb_x"})
    assert out["id"] == "rpt_1"


@pytest.mark.asyncio
async def test_get_report_and_set_pps_tools(monkeypatch):
    snap = {"id": "rpt_1", "status": "writing", "pps": [], "chapters": [], "registry": []}
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository",
                        lambda: AsyncMock(get_report_snapshot=AsyncMock(return_value=snap),
                                          upsert_pps_param=AsyncMock(return_value={"entity_key": "k", "value": "v"})))
    rep = await tools_mod.get_report.ainvoke({"report_id": "rpt_1"})
    assert rep["status"] == "writing"
    p = await tools_mod.set_pps_param.ainvoke(
        {"report_id": "rpt_1", "entity_key": "k", "name": "n", "value": "v", "value_type": "number", "unit": "m", "source": "s"})
    assert p["value"] == "v"
```

- [ ] **Step 2: 跑测试确认失败** — `docker exec api-dev pytest /app/test/unit/toolkits/test_report_tools.py -v` → FAIL

- [ ] **Step 3: 实现 3 个工具**(追加到 `tools.py` 末尾)

```python
CREATE_REPORT_DESCRIPTION = """
为一篇环评报告创建持久化报告对象。后续所有写作(章节/参数/装配)都针对 report_id 操作,
支持跨会话点状写作。一次创建,多会话复用。
"""


@tool(category="buildin", tags=["报告"], display_name="创建报告", description=CREATE_REPORT_DESCRIPTION)
async def create_report(thread_id: str, title: str, domain: str, report_type: str, kb_id: str) -> dict:
    repo = DomainFactoryRepository()
    return await repo.create_report(thread_id=thread_id, title=title, domain_code=domain,
                                    report_type_code=report_type, kb_id=kb_id, created_by=None)


GET_REPORT_DESCRIPTION = """
取报告全景快照:status + PPS 参数列表 + 章节注册表(含已完成章摘要,供交叉引用)。
每章写作前调用一次注入上下文。
"""


@tool(category="buildin", tags=["报告"], display_name="取报告快照", description=GET_REPORT_DESCRIPTION)
async def get_report(report_id: str) -> dict:
    repo = DomainFactoryRepository()
    out = await repo.get_report_snapshot(report_id)
    return out or {"error": f"报告不存在: {report_id}"}


SET_PPS_PARAM_DESCRIPTION = """
设置/更新一个项目参数(PPS)。entity_key 优先用 get_chapter_outline 返回的 entity_bindings 的 key;
value_type 取 number|string|enum。设置后全报告复用。
"""


@tool(category="buildin", tags=["报告", "PPS"], display_name="设置项目参数", description=SET_PPS_PARAM_DESCRIPTION)
async def set_pps_param(report_id: str, entity_key: str, name: str, value: str,
                        value_type: str, unit: str, source: str) -> dict:
    repo = DomainFactoryRepository()
    return await repo.upsert_pps_param(report_id=report_id, entity_key=entity_key, name=name,
                                       value=value, value_type=value_type, unit=unit, source=source)
```

- [ ] **Step 4: 跑测试** — `docker exec api-dev pytest /app/test/unit/toolkits/test_report_tools.py -v` → PASS(3 测试)
- [ ] **Step 5: 验证工具可达** — `docker exec api-dev python -c "from yuxi.agents.toolkits.service import get_tool_instances_by_category; print([t.name for t in get_tool_instances_by_category('buildin') if 'report' in t.name or 'pps' in t.name])"` → 列出 3 个
- [ ] **Step 6: surgical ruff + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/agents/toolkits/buildin/tools.py
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/test/unit/toolkits/test_report_tools.py
git commit -m "feat(writing-backbone): create_report/get_report/set_pps_param 工具"
```

---

## Task 3: 工具——save_chapter(懒建 + status)

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`
- Test: `backend/test/unit/toolkits/test_report_tools.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 `upsert_chapter`。chapter_order 由 outline 序推导(implementer 查 `domain_factory_outlines` 同 report_type 的章节序,给 canonical_chapter_key 定 order;查不到则 None)。

- [ ] **Step 1: 追加失败测试**

```python
@pytest.mark.asyncio
async def test_save_chapter_tool(monkeypatch):
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository",
                        lambda: AsyncMock(upsert_chapter=AsyncMock(return_value={"canonical_chapter_key": "k", "status": "done"})))
    out = await tools_mod.save_chapter.ainvoke(
        {"report_id": "rpt_1", "canonical_chapter_key": "k", "title": "T",
         "content_md": "正文", "summary": "摘", "status": "done"})
    assert out["status"] == "done"
```

- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 实现 save_chapter**(追加到 `tools.py`)

```python
SAVE_CHAPTER_DESCRIPTION = """
懒建/更新一章。canonical_chapter_key 用 get_chapter_outline 的大纲章节名。
content_md 为本章 markdown 正文(含 {{REF:chXX/表X-Y}} 交叉引用占位符)。
status 取 writing|done|skipped;done 时 content_md 不能为空。
"""


@tool(category="buildin", tags=["报告", "章节"], display_name="保存章节", description=SAVE_CHAPTER_DESCRIPTION)
async def save_chapter(report_id: str, canonical_chapter_key: str, title: str,
                       content_md: str, summary: str, status: str) -> dict:
    if status == "done" and not (content_md or "").strip():
        return {"error": "status=done 时 content_md 不能为空"}
    repo = DomainFactoryRepository()
    order = await repo.lookup_chapter_order(report_id, canonical_chapter_key)  # 见 Step 4
    return await repo.upsert_chapter(report_id=report_id, canonical_chapter_key=canonical_chapter_key,
                                     chapter_order=order, title=title, content_md=content_md,
                                     summary=summary, status=status)
```

- [ ] **Step 4: 加 `lookup_chapter_order` 到 repository**(从 outline 序推导:查同 domain+report_type 的 outlines,按 id 顺序给 key 排名;已在库的章节也参与排序)

```python
    async def lookup_chapter_order(self, report_id, canonical_chapter_key) -> int | None:
        # 报告所属 report_type,从 domain_factory_outlines 取 canonical_chapter_key 的出现序
        async with pg_manager.get_async_session_context() as session:
            rpt = (await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))).scalar_one_or_none()
            if not rpt: return None
            rows = (await session.execute(select(DomainFactoryOutline.canonical_chapter_key).where(
                DomainFactoryOutline.domain_code == rpt.domain_code,
                DomainFactoryOutline.report_type_code == rpt.report_type_code).order_by(DomainFactoryOutline.id))).all()
            keys = [r[0] for r in rows]
            return (keys.index(canonical_chapter_key) + 1) if canonical_chapter_key in keys else None
```

- [ ] **Step 5: 跑测试** → PASS(4 测试)
- [ ] **Step 6: surgical ruff + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/agents/toolkits/buildin/tools.py package/yuxi/repositories/domain_factory_repository.py
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/toolkits/test_report_tools.py
git commit -m "feat(writing-backbone): save_chapter 工具(懒建 + outline 序 + 空内容校验)"
```

---

## Task 4: `{{REF}}` resolver(纯代码)

**Files:**
- Create: `backend/package/yuxi/services/ref_resolver.py`
- Test: `backend/test/unit/services/test_ref_resolver.py`(建)

**Interfaces:**
- Produces: `resolve_refs(chapters: list[dict]) -> tuple[str, list[dict]]`,输入 = Task 1 的 `list_chapters` 输出(每章 {chapter_order, content_md, ...}),返回(合并后 markdown, unresolved_refs)。Task 5 调用。

- [ ] **Step 1: 写失败测试**

创建 `backend/test/unit/services/test_ref_resolver.py`:

```python
from yuxi.services.ref_resolver import resolve_refs


def test_resolve_table_ref_and_flag_unresolved():
    chapters = [
        {"chapter_order": 2, "title": "ch2", "content_md": "## 2.1\n见 {{REF:ch05/表5-3}}。\n\n**表5-3 监测结果**\n|a|b|\n"},
        {"chapter_order": 5, "title": "ch5", "content_md": "标题\n**表5-3 大气监测**\n|x|y|\n引用 {{REF:ch09/图9-1}} 未写。"},
    ]
    merged, unresolved = resolve_refs(chapters)
    assert "表5-3" in merged  # ch05 的表5-3 被解析进 ch2 的引用
    assert any("图9-1" in u.get("ref", "") or "图9-1" in str(u) for u in unresolved)


def test_chapters_merged_in_order():
    chapters = [
        {"chapter_order": 5, "content_md": "第五"},
        {"chapter_order": 2, "content_md": "第二"},
    ]
    merged, _ = resolve_refs(chapters)
    assert merged.index("第二") < merged.index("第五")
```

- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 实现 resolver**

```python
"""{{REF:chXX/表X-Y}} 位置编号解析器。assemble 时扫各章 content_md 现算。"""
import re

_REF_RE = re.compile(r"\{\{REF:([^/]+)/([^}]+)\}\}")
_CAP_TABLE_RE = re.compile(r"\*\*(表[\d\-\.]+)\s*[^*\n]*\*\*")
_CAP_FIGURE_RE = re.compile(r"!\[(图[\d\-\.]+)[^\]]*\]")
_CAP_SECTION_RE = re.compile(r"^#{1,6}\s*((?:\d+(?:\.\d+)*)\s+\S.*)$", re.MULTILINE)


def _chapter_alias(order: int) -> str:
    return f"ch{order:02d}"


def _build_target_map(chapters: list[dict]) -> dict[str, set[str]]:
    """{chXX: {可引用目标集合}}"""
    targets: dict[str, set[str]] = {}
    for ch in chapters:
        order = ch.get("chapter_order")
        if order is None:
            continue
        alias = _chapter_alias(order)
        md = ch.get("content_md") or ""
        s = set()
        s.update(m for m in _CAP_TABLE_RE.findall(md))
        s.update(m for m in _CAP_FIGURE_RE.findall(md))
        s.update(m[0] for m in _CAP_SECTION_RE.findall(md))  # "N.N 标题"
        targets[alias] = s
    return targets


def resolve_refs(chapters: list[dict]) -> tuple[str, list[dict]]:
    """按 chapter_order 合并章节,解析 {{REF}}。返回 (merged_markdown, unresolved_refs)。"""
    ordered = sorted([c for c in chapters if c.get("content_md")], key=lambda c: c.get("chapter_order") or 9999)
    merged = "\n\n".join(c["content_md"] for c in ordered)
    targets = _build_target_map(ordered)
    unresolved: list[dict] = []

    def _replace(m: re.Match) -> str:
        ch_alias, target = m.group(1).strip(), m.group(2).strip()
        avail = targets.get(ch_alias)
        if avail is None:
            unresolved.append({"ref": m.group(0), "reason": f"章节 {ch_alias} 未写入"})
            return m.group(0)  # 保留可见占位符
        # 精确或包含匹配目标
        if target in avail or any(target in t for t in avail):
            return f"见{target}"
        unresolved.append({"ref": m.group(0), "reason": f"{ch_alias} 中未找到 {target}"})
        return m.group(0)

    resolved = _REF_RE.sub(_replace, merged)
    return resolved, unresolved
```

- [ ] **Step 4: 跑测试** → PASS(2 测试)
- [ ] **Step 5: ruff + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/services/ref_resolver.py
git add backend/package/yuxi/services/ref_resolver.py backend/test/unit/services/test_ref_resolver.py
git commit -m "feat(writing-backbone): {{REF}} 位置编号 resolver(纯代码,assemble 现算)"
```

---

## Task 5: 工具——assemble_report(合并 + 解析 + 写沙箱)

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`(更新报告 status)
- Test: `backend/test/unit/toolkits/test_report_tools.py`(追加)

**Interfaces:**
- Consumes: Task 1 `list_chapters`;Task 4 `resolve_refs`;`ToolRuntime` + `sandbox_outputs_dir`(沙箱写)。

- [ ] **Step 1: 追加失败测试**(mock repo + resolver,验证写沙箱路径返回)

```python
@pytest.mark.asyncio
async def test_assemble_report_tool(monkeypatch, tmp_path):
    chapters = [{"chapter_order": 1, "content_md": "# ch1\n正文"}]
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository",
                        lambda: AsyncMock(list_chapters=AsyncMock(return_value=chapters), mark_assembled=AsyncMock(return_value=None)))
    # mock sandbox 写:跳过实际 FS,验证返回结构
    async def fake_write(*a, **k):
        return "/home/gem/user-data/outputs/report.md"
    monkeypatch.setattr(tools_mod, "_write_assembled_to_sandbox", fake_write)
    out = await tools_mod.assemble_report.ainvoke({"report_id": "rpt_1", "runtime_context": {}})
    assert out["artifact_path"].endswith("report.md")
    assert out["unresolved_refs"] == []
```

- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 实现 assemble_report + 沙箱写助手**(追加到 `tools.py`;沙箱写参考 `present_artifacts` 的 `runtime`/`sandbox_outputs_dir` 用法)

```python
import asyncio

ASSEMBLE_REPORT_DESCRIPTION = """
按 outline 序合并所有 done 章节 + 解析 {{REF}} → 成稿 markdown,写入沙箱 outputs。
未解析的 {{REF}} 保留为可见占位符并列出。返回 {markdown, artifact_path, unresolved_refs}。
随后可用 present_artifacts 展示给用户。
"""


async def _write_assembled_to_sandbox(runtime_context: dict, report_id: str, markdown: str) -> str:
    from yuxi.agents.backends.sandbox.paths import sandbox_outputs_dir  # 参考 present_artifacts
    thread_id = runtime_context.get("thread_id") or "shared"
    out_dir = sandbox_outputs_dir(thread_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{report_id}.md"
    await asyncio.to_thread(path.write_text, markdown, "utf-8")
    return f"/home/gem/user-data/outputs/report_{report_id}.md"


@tool(category="buildin", tags=["报告", "装配"], display_name="装配报告", description=ASSEMBLE_REPORT_DESCRIPTION)
async def assemble_report(report_id: str, runtime: ToolRuntime) -> dict:
    from yuxi.services.ref_resolver import resolve_refs
    repo = DomainFactoryRepository()
    chapters = await repo.list_chapters(report_id, status_only="done")
    markdown, unresolved = resolve_refs(chapters)
    artifact_path = await _write_assembled_to_sandbox(runtime.context, report_id, markdown)
    await repo.mark_assembled(report_id)
    return {"markdown": markdown[:500] + ("..." if len(markdown) > 500 else ""),
            "artifact_path": artifact_path, "unresolved_refs": unresolved}
```

> `ToolRuntime` 已在 `tools.py` 顶部导入(见 `present_artifacts`)。`sandbox_outputs_dir` 的确切路径以 `yuxi/agents/backends/sandbox/paths.py` 为准。`runtime.context` 的 `thread_id` 取法参考 `present_artifacts` 实现。

- [ ] **Step 4: 加 `mark_assembled` 到 repository**

```python
    async def mark_assembled(self, report_id):
        async with pg_manager.get_async_session_context() as session:
            rpt = (await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))).scalar_one_or_none()
            if rpt: rpt.status = "assembled"
            await session.commit()
```

- [ ] **Step 5: 跑测试** → PASS(5 测试)
- [ ] **Step 6: surgical ruff + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/agents/toolkits/buildin/tools.py package/yuxi/repositories/domain_factory_repository.py
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/toolkits/test_report_tools.py
git commit -m "feat(writing-backbone): assemble_report 工具(确定性合并 + {{REF}} 解析 + 沙箱交付)"
```

**Phase A 至此可独立交付**:create_report → set_pps_param → save_chapter(逐章)→ assemble_report,全程工具驱动、DB 持久化、跨会话、确定性装配。

---

# Phase B — Agent 编排

## Task 6: chapter-writer 子 agent 注册

**Files:**
- Modify: `backend/package/yuxi/repositories/agent_repository.py`(加 `ensure_chapter_writer_subagent`,仿 `ensure_general_purpose_subagent`)
- Modify: `backend/server/utils/lifespan.py`(启动注册)
- Test: `backend/test/unit/repositories/test_chapter_writer_subagent.py`(建)

**Interfaces:**
- Produces: 一个 `chapter_writer` 子 agent(slug=`chapter-writer`,SubAgentBackend,预装报告工具:get_chapter_outline/get_report/get_templates/set_pps_param/save_chapter)。Task 7 的 SKILL 用 `subagent_start`/`task` 派发它。

- [ ] **Step 1: 写失败测试**

```python
import pytest
from yuxi.storage.postgres.manager import pg_manager
from yuxi.repositories.agent_repository import AgentRepository


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await pg_manager.close()
    pg_manager._initialized = False


@pytest.mark.asyncio
async def test_ensure_chapter_writer_subagent_idempotent():
    repo = AgentRepository()
    a1 = await repo.ensure_chapter_writer_subagent()
    a2 = await repo.ensure_chapter_writer_subagent()
    assert a1.slug == "chapter-writer"
    assert a1.id == a2.id  # 幂等
```

- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 实现 `ensure_chapter_writer_subagent`**(仿 `ensure_general_purpose_subagent`,改 slug/name/runtime_tools)

```python
    async def ensure_chapter_writer_subagent(self, *, created_by: str | None = None) -> Agent:
        """幂等注册 chapter-writer 子 agent(聚焦单章写作)。"""
        # 复用 ensure_general_purpose_subagent 的查/建模式,改:
        #   slug = "chapter-writer", name = "章节写手"
        #   runtime_config.tools = [get_chapter_outline, get_report, get_templates, set_pps_param, save_chapter]
        #   backend_id = SubAgentBackend 的 backend id(同 general-purpose)
        #   is_subagent = True
        ...  # implementer: 照 ensure_general_purpose_subagent 结构,替换上述字段
```

> implementer:`grep -n "ensure_general_purpose_subagent" backend/package/yuxi/repositories/agent_repository.py`,照其结构复制一份,替换 slug/name/tools/backend 字段。

- [ ] **Step 4: lifespan 启动注册**(在 `ensure_deep_research_agents()` 调用后追加)

```python
        try:
            await repository.ensure_chapter_writer_subagent()
        except Exception as e:
            logger.error(f"Failed to ensure chapter-writer subagent: {e}")
```

- [ ] **Step 5: 重启 api-dev + 跑测试** → PASS
- [ ] **Step 6: 验证子 agent 已注册** — `docker exec postgres psql -U postgres -d yuxi_know -c "SELECT slug,is_subagent FROM agents WHERE slug='chapter-writer';"` → 1 行
- [ ] **Step 7: surgical ruff + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/repositories/agent_repository.py
git add backend/package/yuxi/repositories/agent_repository.py backend/server/utils/lifespan.py backend/test/unit/repositories/test_chapter_writer_subagent.py
git commit -m "feat(writing-backbone): 注册 chapter-writer 子 agent(预装报告工具)"
```

---

## Task 7: coal-eia-writer SKILL 改为编排者

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`
- Modify: `backend/package/yuxi/agents/skills/buildin/__init__.py`(tool_dependencies 加报告工具 + subagent_start/task)

**说明**:纯 prompt + 依赖编辑,无单测;验证 = 依赖可达 + 无残留"自觉维护 PPS.md/registry.md"指令。

- [ ] **Step 1: 改写 SKILL.md 工作流**(替换原 PPS.md/registry.md/{{REF}} 手维护段为新工具流程)

新工作流骨架(替换 SKILL.md 的"第三步 PPS"~"第五步 装配"段):

```markdown
## 工作流(确定性骨架版)

### 0. 建报告(一次性)
- create_report(thread_id, title, domain, report_type, kb_id) → report_id
- 后续所有操作都带 report_id;跨会话用 report_id 续接。

### 1. 逐章写作(派 chapter-writer 子 agent,可并行)
对每个要写的章节,用 subagent_start 派 chapter-writer 子 agent,指令:
  "写 [canonical_chapter_key] 章:先 get_chapter_outline 取大纲,再 get_report 取 PPS+注册表,
   get_templates 取模板,填充插槽(缺参数 set_pps_param 或 ask_user_question),
   写 markdown(交叉引用用 {{REF:chXX/表X-Y}}),save_chapter(status=done)。"
等待各子 agent 完成(subagent_await / task)。

### 2. 点状编辑(任意会话)
- 用户请求改某章/某参数:get_report(report_id) 看现状 → 派该章 chapter-writer(load→edit→save_chapter)
  或直接 set_pps_param。

### 3. 装配
- assemble_report(report_id) → 解析 {{REF}} → present_artifacts(artifact_path) 交付。
- 若返回 unresolved_refs 非空 → 修对应章后重 assemble。
```

删除原"自觉维护 PPS/registry markdown"的指令;保留领域知识(章节类型/数据源/评价等级等)。

- [ ] **Step 2: 更新 `__init__.py` 的 coal-eia-writer tool_dependencies**(加报告工具 + 派发工具)

```python
tool_dependencies=(
    "get_chapter_outline", "get_templates",           # 桥
    "create_report", "get_report", "set_pps_param",   # 报告(本子项目)
    "save_chapter", "assemble_report",
    "subagent_start", "subagent_await",               # 派 chapter-writer
    "present_artifacts", "ask_user_question", "list_kbs", "query_kb",
),
```

- [ ] **Step 3: 验证依赖可达 + 无残留**

```bash
docker exec api-dev python -c "from yuxi.agents.skills.buildin import BUILTIN_SKILLS; s=[x for x in BUILTIN_SKILLS if x.slug=='coal-eia-writer'][0]; print(s.tool_dependencies)"
grep -nE "PPS\.md|registry\.md|自觉维护" backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md  # 应为空
```

- [ ] **Step 4: 提交**

```bash
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md backend/package/yuxi/agents/skills/buildin/__init__.py
git commit -m "feat(skills): coal-eia-writer 改为编排者(派 chapter-writer 子 agent + 报告工具流)"
```

---

## Task 8: 端到端验证 + changelog + OpenWolf

**Files:**
- Modify: `docs/develop-guides/changelog.md`、`.wolf/anatomy.md`、`.wolf/memory.md`

- [ ] **Step 1: Phase A 端到端(工具直驱,不经 agent)**

```bash
docker exec api-dev python -c "
import asyncio
from yuxi.agents.toolkits.buildin.tools import create_report, set_pps_param, save_chapter, assemble_report
async def run():
    r = await create_report.ainvoke({'thread_id':'t1','title':'测试','domain':'coal','report_type':'eia_report','kb_id':'kb_cgsguljhor'})
    rid = r['id']
    await set_pps_param.ainvoke({'report_id':rid,'entity_key':'capacity','name':'产能','value':'300','value_type':'number','unit':'万t/a','source':'可研'})
    await save_chapter.ainvoke({'report_id':rid,'canonical_chapter_key':'test_ch','title':'1 测试章','content_md':'# 1 测试章\n正文见 {{REF:ch02/表2-1}}。','summary':'测试','status':'done'})
    # assemble 需要 runtime(沙箱写);程序化验证用 mock runtime_context
    class RT: context={'thread_id':'t1'}
    out = await assemble_report.ainvoke({'report_id':rid,'runtime':RT()})
    print('STATUS', r['status'], 'UNRESOLVED', out['unresolved_refs'])
asyncio.run(run())
"
```
Expected: report 建好、PPS 入库、章节入库;assemble 返回 unresolved_refs(因 ch02 未写)。

- [ ] **Step 2: DB 断言**

```bash
docker exec postgres psql -U postgres -d yuxi_know -c "SELECT status FROM domain_factory_reports ORDER BY created_at DESC LIMIT 1;"
docker exec postgres psql -U postgres -d yuxi_know -c "SELECT canonical_chapter_key,status FROM domain_factory_reports_chapters ORDER BY id DESC LIMIT 3;"
docker exec postgres psql -U postgres -d yuxi_know -c "SELECT entity_key,value FROM domain_factory_reports_pps ORDER BY id DESC LIMIT 3;"
```

- [ ] **Step 3: 更新 changelog**(v0.7.1 开发记录顶部加一条)

```markdown
- 新增写作侧确定性骨架(子项目2):report/chapter/pps 持久化 + create_report/get_report/set_pps_param/save_chapter/assemble_report 五工具 + {{REF}} 位置编号 resolver(assemble 现算)+ chapter-writer 子 agent;coal-eia-writer 改为编排者,每章派临时子 agent。PPS=项目级实体值(链桥的 entity_bindings)。支撑环评报告跨会话点状写作。详见 [spec](../superpowers/specs/2026-07-11-writing-backbone-design.md)。
```

- [ ] **Step 4: OpenWolf 收尾**(anatomy 加新文件、memory 追加)
- [ ] **Step 5: 提交**

```bash
git add docs/develop-guides/changelog.md .wolf/anatomy.md .wolf/memory.md
git commit -m "docs(writing-backbone): 端到端验证 + changelog"
```

---

## Self-Review(已执行)

- **Spec 覆盖**:§3 决策→任务 1-7 全覆盖(决策1→T1;2→T2/3/5;3→T1 PPS+T2;4→T3 懒建;5→T4 resolver;6→T1 report_id+T2/3 取 report_id;7→T6/T7);§7 resolver→T4;§8 工作流→T7;§9 错误→T3(空内容校验)+T5(unresolved)+T4(unresolved 标记);§10 前置→Global Constraints;§12 验收→T8。
- **Placeholder**:implementer 注释处(ensure_chapter_writer_subagent 的"照 ensure_general_purpose_subagent 复制"、hashstr 导入路径、sandbox_outputs_dir 路径)是"以代码库为准"的精准指引(给 grep 命令),非 TBD——可接受;其余步骤均有完整代码。
- **类型一致**:`create_report/get_report/set_pps_param/save_chapter/assemble_report/resolve_refs/lookup_chapter_order/mark_assembled` 跨任务签名一致;`get_report_snapshot` 返回 {pps,chapters,registry} 与 T2 测试一致。
- **分阶段**:Phase A(T1-5)独立可交付(工具直驱,不经 agent);Phase B(T6-8)依赖 A。两阶段边界清晰。
