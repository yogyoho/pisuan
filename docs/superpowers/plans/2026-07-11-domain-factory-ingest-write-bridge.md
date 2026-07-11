# 入库→写作的桥 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在领域工厂 commit 阶段产出 writer 可消费的结构化章节大纲（`domain_factory_outlines`）+ 结构化模板工具，打通入库→写作的桥。

**Architecture:** commit 流水线新增 OutlineProducer 阶段（非阻断）：按章把 ETL 已抽资产（learned_templates/法规/表格/公式/图/图谱实体）确定性组装成大纲的 7 个结构化字段；同一次 LLM 调用产出 `canonical_chapter_key` + 4 个散文字段；upsert 进新表。新增 2 个 buildin 工具 `get_chapter_outline` / `get_templates` 供 4 个写作 skill 调用，query_kb 回归纯自由检索。

**Tech Stack:** Python 3.13 / SQLAlchemy（异步）/ FastAPI / LangChain `@tool` / Pytest / 现有 `select_model` LLM 通道。

## Global Constraints

- 后端代码 pythonic，用较新语法（3.12+）；中文提交信息，Conventional Commits。
- DB 迁移靠 `backend/package/yuxi/storage/postgres/manager.py` 的 DDL 列表（`CREATE/ALTER ... IF NOT EXISTS`），无 Alembic；`create_all()` 只建不存在的表，**已存在表的新列必须配幂等 ALTER**。
- 文件改动后必须 `make format`（`python -m ruff format` + `ruff check`）；测试在容器跑：`docker exec api-dev pytest /app/test/unit/<path> -v`。
- 不要用过度防御/回退掩盖设计问题；遵循 OpenWolf：改文件后更新 `.wolf/anatomy.md`、追加 `.wolf/memory.md`、bug 记 `.wolf/buglog.json`。
- 命名约束：大纲表用 `canonical_chapter_key`（LLM 归一化名），**绝不**复用 header 里误导的 `standard_code` 字段名；`regulations[].standard_code` 才是真法规编号。
- **前置依赖（不属本计划任务，但落地前须满足）**：(1) `mcp-server-chart` MCP 启用（否则 expected_charts 给了也画不出）；(2) docling `image_refs` bug 修复（否则表格/图表抽取喂不饱——不影响桥跑通，只影响字段丰度）。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `backend/package/yuxi/storage/postgres/models_domain_factory.py` | `DomainFactoryOutline` 模型；给 `DomainFactoryLearnedTemplate` 加 `canonical_chapter_key` 列 | 改 |
| `backend/package/yuxi/storage/postgres/manager.py` | `domain_factory_outlines` 建表 DDL + `learned_templates` 加列 ALTER | 改 |
| `backend/package/yuxi/repositories/domain_factory_repository.py` | `upsert_outline` / `get_outline` / `list_chapter_keys` / `backfill_template_chapter_key` | 改 |
| `backend/package/yuxi/services/domain_factory_service.py` | `OutlineProducer`（`_group_assets_by_chapter` / `_assemble_deterministic_outline` / `_llm_chapter_meta` / `_produce_outlines_async`）+ 接入 commit 流水线 | 改 |
| `backend/package/yuxi/agents/toolkits/buildin/tools.py` | `get_chapter_outline` / `get_templates` 两个 `@tool` | 改 |
| `backend/package/yuxi/agents/skills/buildin/{coal-eia-writer,compliance-checker,template-recommender,slot-filler}/SKILL.md` | 改指向新工具 | 改 |
| `backend/test/unit/services/test_outline_producer.py` | OutlineProducer 单测 | 建 |
| `backend/test/unit/toolkits/test_domain_factory_tools.py` | 两个工具单测 | 建 |
| `docs/develop-guides/changelog.md` | 记录 | 改 |

---

## Task 1: 存储层——大纲模型 + 建表 + learned_templates 加列 + repository

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`
- Modify: `backend/package/yuxi/storage/postgres/manager.py`
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`
- Test: `backend/test/unit/storage/test_domain_factory_outline_repo.py`（建）

**Interfaces:**
- Produces: `DomainFactoryOutline` 模型；repository 方法 `upsert_outline(...)`、`get_outline(domain_code, report_type_code, canonical_chapter_key) -> dict|None`、`list_chapter_keys(domain_code, report_type_code) -> list[str]`、`backfill_template_chapter_key(domain_code, report_type_code, chapter_raw, canonical_chapter_key) -> int`。后续 Task 2-5 依赖这些签名。

- [ ] **Step 1: 写失败测试（repository CRUD）**

创建 `backend/test/unit/storage/test_domain_factory_outline_repo.py`：

```python
import pytest
from yuxi.storage.postgres.manager import pg_manager
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository


@pytest.mark.asyncio
async def test_upsert_and_get_outline():
    repo = DomainFactoryRepository()
    await repo.upsert_outline(
        domain_code="coal",
        report_type_code="eia_report",
        canonical_chapter_key="地下水环境影响预测",
        chapter_id="5.2",
        chapter_title="地下水环境影响预测",
        purpose="预测开采对地下水的影响",
        overview="本章预测...",
        key_points=["水位下降", "水质影响"],
        content_requirements=["水位降深", "影响半径"],
        regulations=[{"code": "GB/T 14848", "title": "地下水质量标准"}],
        entity_bindings=[{"entity_key": "groundwater_level", "value_type": "number"}],
        writing_example="预测结果表明...",
        writing_hints="先给水文地质参数，再用数值法",
        expected_tables=[], expected_charts=[], expected_formulas=[], expected_figures=[],
        source_task_ids=["t-1"], source_count=1, prose_based_on_source_count=1,
    )
    got = await repo.get_outline("coal", "eia_report", "地下水环境影响预测")
    assert got is not None
    assert got["chapter_title"] == "地下水环境影响预测"
    assert "水位下降" in got["key_points"]


@pytest.mark.asyncio
async def test_list_chapter_keys_and_backfill():
    repo = DomainFactoryRepository()
    keys = await repo.list_chapter_keys("coal", "eia_report")
    assert "地下水环境影响预测" in keys
    n = await repo.backfill_template_chapter_key("coal", "eia_report", "5.2", "地下水环境影响预测")
    assert n >= 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec api-dev pytest /app/test/unit/storage/test_domain_factory_outline_repo.py -v`
Expected: FAIL（`DomainFactoryOutline` 不存在 / `upsert_outline` 未定义）

- [ ] **Step 3: 加模型 `DomainFactoryOutline` + 给 LearnedTemplate 加列**

在 `models_domain_factory.py` 的 `DomainFactoryLearnedTemplate` 类里，`chapter` 字段后加：

```python
    canonical_chapter_key = Column(Text, nullable=True, index=True)  # OutlineProducer 回填的归一化章节名
```

并在文件末尾（`DomainFactoryPromptConfig` 之后）加新模型：

```python
class DomainFactoryOutline(Base):
    """领域知识工厂 - 章节结构化大纲（writer 的主数据源）"""

    __tablename__ = "domain_factory_outlines"
    __table_args__ = (
        UniqueConstraint(
            "domain_code", "report_type_code", "canonical_chapter_key",
            name="uq_dfo_domain_rt_key",
        ),
        Index("idx_dfo_domain_rt", "domain_code", "report_type_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=False)
    report_type_code = Column(String(64), nullable=False, default="通用")
    canonical_chapter_key = Column(Text, nullable=False)
    chapter_id = Column(String(128), nullable=True)
    chapter_title = Column(Text, nullable=True)
    # Tier1 文字
    purpose = Column(Text, nullable=True)
    overview = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True, default=list)
    content_requirements = Column(JSON, nullable=True, default=list)
    regulations = Column(JSON, nullable=True, default=list)
    entity_bindings = Column(JSON, nullable=True, default=list)
    writing_example = Column(Text, nullable=True)
    writing_hints = Column(Text, nullable=True)
    # Tier1 artifact
    expected_tables = Column(JSON, nullable=True, default=list)
    expected_charts = Column(JSON, nullable=True, default=list)
    expected_formulas = Column(JSON, nullable=True, default=list)
    expected_figures = Column(JSON, nullable=True, default=list)
    # Tier2 占位
    content_contract = Column(JSON, nullable=True, default=list)
    dependencies = Column(JSON, nullable=True, default=list)
    # 聚合/来源
    source_task_ids = Column(JSON, nullable=True, default=list)
    source_count = Column(Integer, nullable=False, default=1)
    prose_based_on_source_count = Column(Integer, nullable=True)
    rigidity = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_code": self.domain_code,
            "report_type_code": self.report_type_code or "通用",
            "canonical_chapter_key": self.canonical_chapter_key,
            "chapter_id": self.chapter_id,
            "chapter_title": self.chapter_title,
            "purpose": self.purpose,
            "overview": self.overview,
            "key_points": self.key_points or [],
            "content_requirements": self.content_requirements or [],
            "regulations": self.regulations or [],
            "entity_bindings": self.entity_bindings or [],
            "writing_example": self.writing_example,
            "writing_hints": self.writing_hints,
            "expected_tables": self.expected_tables or [],
            "expected_charts": self.expected_charts or [],
            "expected_formulas": self.expected_formulas or [],
            "expected_figures": self.expected_figures or [],
            "source_count": self.source_count,
            "rigidity": self.rigidity,
        }
```

- [ ] **Step 4: 加建表 DDL + 加列 ALTER 到 `manager.py`**

在 `manager.py` 的 `ensure_business_schema`（或 domain_factory DDL 段，紧挨 `domain_factory_learned_templates` 建表语句之后）追加：

```python
            "ALTER TABLE IF EXISTS domain_factory_learned_templates ADD COLUMN IF NOT EXISTS canonical_chapter_key TEXT",
            "CREATE TABLE IF NOT EXISTS domain_factory_outlines ("
            "    id SERIAL PRIMARY KEY,"
            "    domain_code VARCHAR(64) NOT NULL,"
            "    report_type_code VARCHAR(64) NOT NULL DEFAULT '通用',"
            "    canonical_chapter_key TEXT NOT NULL,"
            "    chapter_id VARCHAR(128),"
            "    chapter_title TEXT,"
            "    purpose TEXT,"
            "    overview TEXT,"
            "    key_points JSONB DEFAULT '[]',"
            "    content_requirements JSONB DEFAULT '[]',"
            "    regulations JSONB DEFAULT '[]',"
            "    entity_bindings JSONB DEFAULT '[]',"
            "    writing_example TEXT,"
            "    writing_hints TEXT,"
            "    expected_tables JSONB DEFAULT '[]',"
            "    expected_charts JSONB DEFAULT '[]',"
            "    expected_formulas JSONB DEFAULT '[]',"
            "    expected_figures JSONB DEFAULT '[]',"
            "    content_contract JSONB DEFAULT '[]',"
            "    dependencies JSONB DEFAULT '[]',"
            "    source_task_ids JSONB DEFAULT '[]',"
            "    source_count INTEGER NOT NULL DEFAULT 1,"
            "    prose_based_on_source_count INTEGER,"
            "    rigidity VARCHAR(16),"
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    UNIQUE(domain_code, report_type_code, canonical_chapter_key)"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_dfo_domain_rt ON domain_factory_outlines(domain_code, report_type_code)",
```

- [ ] **Step 5: 加 repository 方法**

在 `domain_factory_repository.py` 的 `DomainFactoryRepository` 类里（`upsert_learned_template` 之后）加：

```python
    async def upsert_outline(self, *, domain_code, report_type_code, canonical_chapter_key,
                             chapter_id=None, chapter_title=None, purpose=None, overview=None,
                             key_points=None, content_requirements=None, regulations=None,
                             entity_bindings=None, writing_example=None, writing_hints=None,
                             expected_tables=None, expected_charts=None, expected_formulas=None,
                             expected_figures=None, source_task_ids=None, source_count=1,
                             prose_based_on_source_count=None) -> DomainFactoryOutline:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                    DomainFactoryOutline.canonical_chapter_key == canonical_chapter_key,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = DomainFactoryOutline(
                    domain_code=domain_code, report_type_code=report_type_code or "通用",
                    canonical_chapter_key=canonical_chapter_key, chapter_id=chapter_id,
                    chapter_title=chapter_title, purpose=purpose, overview=overview,
                    key_points=key_points or [], content_requirements=content_requirements or [],
                    regulations=regulations or [], entity_bindings=entity_bindings or [],
                    writing_example=writing_example, writing_hints=writing_hints,
                    expected_tables=expected_tables or [], expected_charts=expected_charts or [],
                    expected_formulas=expected_formulas or [], expected_figures=expected_figures or [],
                    source_task_ids=source_task_ids or [], source_count=source_count,
                    prose_based_on_source_count=prose_based_on_source_count,
                )
                session.add(row)
            else:
                # Tier1 单报告：直接覆盖确定性字段；聚合合并在后续版本
                row.chapter_id = chapter_id or row.chapter_id
                row.chapter_title = chapter_title or row.chapter_title
                row.purpose = purpose or row.purpose
                row.overview = overview or row.overview
                row.key_points = key_points or row.key_points
                row.content_requirements = content_requirements or row.content_requirements
                row.regulations = regulations or row.regulations
                row.entity_bindings = entity_bindings or row.entity_bindings
                row.writing_example = writing_example or row.writing_example
                row.writing_hints = writing_hints or row.writing_hints
                row.expected_tables = expected_tables or row.expected_tables
                row.expected_charts = expected_charts or row.expected_charts
                row.expected_formulas = expected_formulas or row.expected_formulas
                row.expected_figures = expected_figures or row.expected_figures
                row.prose_based_on_source_count = prose_based_on_source_count
            await session.commit()
            return row

    async def get_outline(self, domain_code, report_type_code, canonical_chapter_key) -> dict[str, Any] | None:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                    DomainFactoryOutline.canonical_chapter_key == canonical_chapter_key,
                )
            )
            row = result.scalar_one_or_none()
            return row.to_dict() if row else None

    async def list_chapter_keys(self, domain_code, report_type_code) -> list[str]:
        from sqlalchemy import distinct
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline.canonical_chapter_key).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                )
            )
            return [r[0] for r in result.all() if r[0]]

    async def backfill_template_chapter_key(self, domain_code, report_type_code, chapter_raw, canonical_chapter_key) -> int:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryLearnedTemplate
        from sqlalchemy import update
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                update(DomainFactoryLearnedTemplate)
                .where(
                    DomainFactoryLearnedTemplate.domain_code == domain_code,
                    DomainFactoryLearnedTemplate.report_type_code == report_type_code,
                    DomainFactoryLearnedTemplate.chapter == chapter_raw,
                )
                .values(canonical_chapter_key=canonical_chapter_key)
            )
            await session.commit()
            return result.rowcount or 0
```

- [ ] **Step 6: 跑测试确认通过**

Run: `docker exec api-dev pytest /app/test/unit/storage/test_domain_factory_outline_repo.py -v`
Expected: PASS（2 个测试通过；DDL 在启动时建表——若未建，重启 api-dev 触发 `ensure_business_schema`）

- [ ] **Step 7: format + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/storage/postgres/models_domain_factory.py package/yuxi/storage/postgres/manager.py package/yuxi/repositories/domain_factory_repository.py
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/storage/test_domain_factory_outline_repo.py
git commit -m "feat(domain-factory): 新增 domain_factory_outlines 表 + repository + learned_templates.canonical_chapter_key"
```

---

## Task 2: OutlineProducer——资产分组 + 确定性组装（纯函数 TDD）

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（加两个静态/纯方法）
- Test: `backend/test/unit/services/test_outline_producer.py`（建）

**Interfaces:**
- Produces: `DomainFactoryService._group_assets_by_chapter(task_detail) -> dict[str, dict]`（key=原始章节标识，value=该章资产聚合）、`_assemble_deterministic_outline(assets) -> dict`（产出 content_requirements/regulations/entity_bindings/expected_*/writing_example 7 字段）。Task 3/4 消费这两个。

- [ ] **Step 1: 写失败测试（纯函数）**

创建 `backend/test/unit/services/test_outline_producer.py`：

```python
from yuxi.services.domain_factory_service import DomainFactoryService


def test_group_assets_by_chapter_buckets_by_chapter():
    task_detail = {
        "source_paragraphs": [
            {"id": "p1", "title": "5.2 地下水", "classify_type": "parameter",
             "template": {"generalized": "水位{{水位值}}", "slots": [{"name": "水位值"}], "sample_original": "水位10m"}},
            {"id": "p2", "title": "5.2 地下水", "classify_type": "narrative", "template": {}},
            {"id": "p3", "title": "5.3 声环境", "classify_type": "parameter",
             "template": {"generalized": "噪声{{噪声值}}", "slots": [{"name": "噪声值"}], "sample_original": "噪声55dB"}},
        ],
        "structured_blocks": [],
    }
    svc = DomainFactoryService.__new__(DomainFactoryService)
    groups = svc._group_assets_by_chapter(task_detail)
    assert "5.2 地下水" in groups and "5.3 声环境" in groups
    assert len(groups["5.2 地下水"]["templates"]) == 1


def test_assemble_deterministic_outline_fields():
    assets = {
        "templates": [{"slots": [{"name": "水位值"}, {"name": "影响半径"}], "sample_original": "水位10m"}],
        "paragraphs": [{"classify_type": "parameter"}, {"classify_type": "narrative"}],
        "legal_refs": [{"code": "GB/T 14848", "title": "地下水质量标准"}],
        "entities": [{"entity_key": "groundwater_level", "value_type": "number", "unit": "m"}],
        "tables": [{"table_type": "standard_limit", "columns": [{"name": "污染物", "role": "key"}]}],
        "formulas": [{"formula_template": "S=Q/T", "variables": [{"name": "Q", "symbol": "Q"}]}],
        "charts": [{"chart_type": "line", "data_source": "water_level"}],
        "figures": [{"figure_type": "process_flow"}],
    }
    svc = DomainFactoryService.__new__(DomainFactoryService)
    out = svc._assemble_deterministic_outline(assets)
    assert "水位值" in out["content_requirements"]
    assert out["regulations"][0]["code"] == "GB/T 14848"
    assert out["entity_bindings"][0]["entity_key"] == "groundwater_level"
    assert out["expected_tables"][0]["table_type"] == "standard_limit"
    assert out["writing_example"] == "水位10m"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec api-dev pytest /app/test/unit/services/test_outline_producer.py -v`
Expected: FAIL（方法未定义）

- [ ] **Step 3: 实现 `_group_assets_by_chapter` + `_assemble_deterministic_outline`**

在 `domain_factory_service.py` 的 `DomainFactoryService` 类里（`_save_learned_templates_from_task` 之前）加：

```python
    @staticmethod
    def _group_assets_by_chapter(task_detail: dict) -> dict[str, dict]:
        """按原始章节标题分组 ETL 已抽资产。章节标识取段落 title（去空白），无 title 的归 '未分类'。"""
        groups: dict[str, dict] = {}
        for para in task_detail.get("source_paragraphs", []):
            ch = (para.get("title") or para.get("chapter") or "未分类").strip()
            g = groups.setdefault(ch, {"templates": [], "paragraphs": [], "legal_refs": [],
                                       "entities": [], "tables": [], "formulas": [],
                                       "charts": [], "figures": []})
            g["paragraphs"].append(para)
            tmpl = para.get("template") or {}
            if tmpl.get("generalized") or tmpl.get("slots"):
                g["templates"].append(tmpl)
        # 结构化资产按章回填（ETL 抽取产物里若带 chapter/title 则归入对应组）
        for key, items, target in (
            ("legal_references", task_detail.get("legal_references", []), "legal_refs"),
            ("table_schemas", task_detail.get("table_schemas", []), "tables"),
            ("formulas", task_detail.get("formulas", []), "formulas"),
            ("entities", task_detail.get("entities", []), "entities"),
        ):
            for item in items or []:
                ch = (item.get("chapter") or item.get("title") or "未分类").strip()
                groups.setdefault(ch, {"templates": [], "paragraphs": [], "legal_refs": [],
                                        "entities": [], "tables": [], "formulas": [],
                                        "charts": [], "figures": []})[target].append(item)
        return groups

    @staticmethod
    def _assemble_deterministic_outline(assets: dict) -> dict:
        """从分好组的资产确定性组装大纲的 7 个结构化字段。"""
        slots: list[str] = []
        for tmpl in assets.get("templates", []):
            for s in tmpl.get("slots") or []:
                name = s.get("name") if isinstance(s, dict) else s
                if name and name not in slots:
                    slots.append(name)
        roles = sorted({p.get("classify_type") for p in assets.get("paragraphs", []) if p.get("classify_type")})
        content_requirements = slots + [f"段落类型:{r}" for r in roles]

        regulations = [
            {"code": r.get("code"), "title": r.get("title"),
             "effective_date": r.get("effective_date"), "scope": r.get("scope"),
             "standard_code": r.get("standard_code") or r.get("code")}
            for r in assets.get("legal_refs", [])
        ]
        entity_bindings = [
            {"entity_id": e.get("entity_id"), "entity_key": e.get("entity_key"),
             "role": e.get("role"), "value_type": e.get("value_type"), "unit": e.get("unit")}
            for e in assets.get("entities", [])
        ]
        expected_tables = [
            {"table_type": t.get("table_type"), "purpose": t.get("purpose"),
             "columns": t.get("columns") or [], "standard_code": t.get("standard_code")}
            for t in assets.get("tables", [])
        ]
        expected_formulas = [
            {"formula_template": f.get("formula_template"),
             "variables": f.get("variables") or [], "purpose": f.get("purpose")}
            for f in assets.get("formulas", [])
        ]
        expected_charts = [
            {"chart_type": c.get("chart_type"), "purpose": c.get("purpose"),
             "data_source": c.get("data_source")}
            for c in assets.get("charts", [])
        ]
        expected_figures = [
            {"figure_type": fg.get("figure_type"), "purpose": fg.get("purpose"),
             "generation_hint": fg.get("generation_hint")}
            for fg in assets.get("figures", [])
        ]
        # writing_example：取最长 sample_original
        samples = [t.get("sample_original") for t in assets.get("templates", []) if t.get("sample_original")]
        writing_example = max(samples, key=len) if samples else None

        return {
            "content_requirements": content_requirements,
            "regulations": regulations,
            "entity_bindings": entity_bindings,
            "expected_tables": expected_tables,
            "expected_formulas": expected_formulas,
            "expected_charts": expected_charts,
            "expected_figures": expected_figures,
            "writing_example": writing_example,
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec api-dev pytest /app/test/unit/services/test_outline_producer.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5: format + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/services/domain_factory_service.py
git add backend/package/yuxi/services/domain_factory_service.py backend/test/unit/services/test_outline_producer.py
git commit -m "feat(domain-factory): OutlineProducer 资产分组 + 确定性字段组装"
```

---

## Task 3: OutlineProducer——LLM 章节归一 + 散文

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`
- Test: `backend/test/unit/services/test_outline_producer.py`（追加）

**Interfaces:**
- Produces: `async def _llm_chapter_meta(self, chapter_title, deterministic, seed_keys) -> dict`，返回 `{canonical_chapter_key, purpose, overview, key_points, writing_hints}`。Task 4 调用它。

- [ ] **Step 1: 追加失败测试（mock LLM）**

在 `test_outline_producer.py` 追加：

```python
import asyncio
from unittest.mock import AsyncMock, patch


def test_llm_chapter_meta_parses_json_and_reuses_seed_key():
    svc = DomainFactoryService.__new__(DomainFactoryService)
    fake_resp = type("R", (), {"content": '{"canonical_chapter_key":"地下水环境影响预测",'
                                          '"purpose":"预测开采对地下水影响",'
                                          '"overview":"本章预测...",'
                                          '"key_points":["水位下降"],'
                                          '"writing_hints":"先水文地质参数"}'})()
    with patch("yuxi.services.domain_factory_service.select_model_lazy", AsyncMock(return_value=type("M", (), {"call": AsyncMock(return_value=fake_resp)})())):
        # select_model 是函数导入；按实际导入路径 mock（见 Step 3 实现）
        import yuxi.services.domain_factory_service as mod
        with patch.object(mod, "select_model", return_value=type("M", (), {"call": AsyncMock(return_value=fake_resp)})()):
            out = asyncio.run(svc._llm_chapter_meta(
                "5.2 地下水环境影响预测", {"content_requirements": ["水位降深"]},
                seed_keys=["地下水环境影响预测"]))
    assert out["canonical_chapter_key"] == "地下水环境影响预测"
    assert "水位下降" in out["key_points"]
```

> 注：`select_model` 在 service 里是函数内 `from yuxi.models.chat import select_model` 导入。为了让 mock 生效，Step 3 把导入提到模块级（`from yuxi.models.chat import select_model` 在文件顶部），测试 mock 模块属性。

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec api-dev pytest /app/test/unit/services/test_outline_producer.py::test_llm_chapter_meta_parses_json_and_reuses_seed_key -v`
Expected: FAIL（`_llm_chapter_meta` 未定义 / select_model 路径问题）

- [ ] **Step 3: 实现 `_llm_chapter_meta`**

先把 `from yuxi.models.chat import select_model` 加到 `domain_factory_service.py` 顶部 import 区（若已在函数内 import，提到顶部以便测试 mock）。然后在 `DomainFactoryService` 类里加：

```python
    CHAPTER_META_PROMPT = """你是煤炭环评报告章节分析专家。为下列章节产出结构化元数据。

章节标题：{title}
该章已抽出的内容要点：{requirements}

【已存在的规范章节名列表（优先复用，避免新建同义名）】
{seed_keys}

严格输出 JSON（不要 markdown 围栏）：
{{
  "canonical_chapter_key": "规范章节名（优先从上面列表选；都不贴切才新建，用简练通用的中文名，如'地下水环境影响预测'）",
  "purpose": "1-2 句：本章在环评中的作用与编写目的",
  "overview": "2-3 句：本章概述",
  "key_points": ["要点1", "要点2", "要点3-5个"],
  "writing_hints": "本章专属写作提示（如：先列现状值再列标准值；用表格呈现监测点位）"
}}
"""

    async def _llm_chapter_meta(self, chapter_title: str, deterministic: dict, seed_keys: list[str]) -> dict:
        import re as _re
        prompt = self.CHAPTER_META_PROMPT.format(
            title=chapter_title,
            requirements=", ".join(deterministic.get("content_requirements", [])[:30]) or "（无）",
            seed_keys=", ".join(seed_keys) or "（首次，无已有规范名）",
        )
        fallback_key = chapter_title
        try:
            model = select_model()
            response = await model.call(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            m = _re.search(r"\{[\s\S]*\}", text)
            if not m:
                raise ValueError("LLM 未返回 JSON")
            data = m.group(0)
            import json as _json
            parsed = _json.loads(data)
            parsed.setdefault("canonical_chapter_key", fallback_key)
            for k in ("purpose", "overview", "key_points", "writing_hints"):
                parsed.setdefault(k, [] if k == "key_points" else None)
            return parsed
        except Exception as e:
            logger.warning(f"章节元数据 LLM 调用失败（不阻断）: {e}")
            return {
                "canonical_chapter_key": fallback_key,
                "purpose": None, "overview": None, "key_points": [], "writing_hints": None,
            }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec api-dev pytest /app/test/unit/services/test_outline_producer.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 5: format + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/services/domain_factory_service.py
git add backend/package/yuxi/services/domain_factory_service.py backend/test/unit/services/test_outline_producer.py
git commit -m "feat(domain-factory): OutlineProducer LLM 章节归一化 + 散文元数据"
```

---

## Task 4: OutlineProducer 编排 + 接入 commit 流水线 + 回填模板

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（`_produce_outlines_async` + 接入 `_commit_pipeline_async` 阶段2.9）
- Test: `backend/test/unit/services/test_outline_producer.py`（追加集成 mock）

**Interfaces:**
- Consumes: Task 1 的 `upsert_outline` / `list_chapter_keys` / `backfill_template_chapter_key`；Task 2 的分组/组装；Task 3 的 `_llm_chapter_meta`。
- Produces: commit 流水线在"阶段2.8 模板回流"之后、"阶段3 完成"之前调用 `_produce_outlines_async`（非阻断）。

- [ ] **Step 1: 追加失败测试（编排，mock 依赖）**

```python
@pytest.mark.asyncio
async def test_produce_outlines_async_writes_rows_and_backfills(monkeypatch):
    svc = DomainFactoryService.__new__(DomainFactoryService)
    svc.repo = AsyncMock()
    svc.repo.list_chapter_keys = AsyncMock(return_value=[])
    svc.repo.upsert_outline = AsyncMock()
    svc.repo.backfill_template_chapter_key = AsyncMock(return_value=1)
    svc.get_task_detail = AsyncMock(return_value={
        "source_paragraphs": [
            {"id": "p1", "title": "5.2 地下水", "classify_type": "parameter",
             "template": {"generalized": "水位{{水位值}}", "slots": [{"name": "水位值"}], "sample_original": "水位10m"}},
        ],
    })
    svc._llm_chapter_meta = AsyncMock(return_value={
        "canonical_chapter_key": "地下水环境影响预测", "purpose": "p", "overview": "o",
        "key_points": ["k"], "writing_hints": "h"})
    n = await svc._produce_outlines_async("task-1", "coal", "eia_report")
    assert n == 1
    svc.repo.upsert_outline.assert_awaited_once()
    svc.repo.backfill_template_chapter_key.assert_awaited_once_with("coal", "eia_report", "5.2 地下水", "地下水环境影响预测")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec api-dev pytest /app/test/unit/services/test_outline_producer.py::test_produce_outlines_async_writes_rows_and_backfills -v`
Expected: FAIL（`_produce_outlines_async` 未定义）

- [ ] **Step 3: 实现 `_produce_outlines_async`**

在 `DomainFactoryService` 类里加：

```python
    async def _produce_outlines_async(self, task_id: str, domain_code: str, report_type_code: str) -> int:
        """commit 阶段：逐章组装大纲 + LLM 归一/散文 → upsert。非阻断由调用方保证。"""
        task_detail = await self.get_task_detail(task_id)
        groups = self._group_assets_by_chapter(task_detail)
        seed_keys = await self.repo.list_chapter_keys(domain_code, report_type_code)
        count = 0
        for chapter_raw, assets in groups.items():
            deterministic = self._assemble_deterministic_outline(assets)
            meta = await self._llm_chapter_meta(chapter_raw, deterministic, seed_keys)
            canonical_key = meta["canonical_chapter_key"]
            await self.repo.upsert_outline(
                domain_code=domain_code, report_type_code=report_type_code,
                canonical_chapter_key=canonical_key,
                chapter_id=chapter_raw.split()[0] if chapter_raw[:1].isdigit() else None,
                chapter_title=chapter_raw,
                purpose=meta.get("purpose"), overview=meta.get("overview"),
                key_points=meta.get("key_points") or [], **deterministic,
                writing_hints=meta.get("writing_hints"),
                source_task_ids=[task_id], source_count=1, prose_based_on_source_count=1,
            )
            # 回填 learned_templates.canonical_chapter_key（供 get_templates 检索）
            await self.repo.backfill_template_chapter_key(domain_code, report_type_code, chapter_raw, canonical_key)
            if canonical_key not in seed_keys:
                seed_keys.append(canonical_key)
            count += 1
        logger.info(f"章节大纲产出: {count} 章, domain={domain_code}, report_type={report_type_code}")
        return count
```

- [ ] **Step 4: 接入 commit 流水线（阶段2.9，非阻断）**

在 `domain_factory_service.py` 的 `_commit_pipeline_async` 里，定位"阶段2.8: 模板回流"块（约 4008-4015 行，`except Exception as e: logger.warning(f"模板回流失败...")`）之后、`if not knowledge_base_id:`之前，插入：

```python
            # ========== 阶段2.9: 章节大纲产出 (OUTLINE) ==========
            try:
                await context.set_progress(92.0, "正在产出章节大纲...")
                await context.set_message("正在产出章节大纲...")
                outline_count = await service._produce_outlines_async(
                    task_id, task.domain.code if task.domain else "coal", task.report_type_code or "通用"
                )
                logger.info(f"章节大纲产出完成: {outline_count} 章")
            except Exception as e:
                logger.warning(f"章节大纲产出失败（不阻断入库）: {e}")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `docker exec api-dev pytest /app/test/unit/services/test_outline_producer.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 6: format + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/services/domain_factory_service.py
git add backend/package/yuxi/services/domain_factory_service.py backend/test/unit/services/test_outline_producer.py
git commit -m "feat(domain-factory): OutlineProducer 接入 commit 流水线（非阻断）+ 回填模板章节归一名"
```

---

## Task 5: 两个 buildin 工具 get_chapter_outline / get_templates

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`
- Test: `backend/test/unit/toolkits/test_domain_factory_tools.py`（建）

**Interfaces:**
- Produces: `@tool get_chapter_outline(domain, report_type, canonical_chapter_key) -> dict` 与 `@tool get_templates(domain, report_type, canonical_chapter_key=None) -> list[dict]`，category="buildin"。4 个写作 skill（Task 6）调用它们。

- [ ] **Step 1: 写失败测试（mock repository）**

创建 `backend/test/unit/toolkits/test_domain_factory_tools.py`：

```python
import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.tools import BaseTool
import yuxi.agents.toolkits.buildin.tools as tools_mod


@pytest.mark.asyncio
async def test_get_chapter_outline_tool_returns_dict(monkeypatch):
    fake = {"canonical_chapter_key": "地下水环境影响预测", "chapter_title": "地下水", "regulations": []}
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: AsyncMock(get_outline=AsyncMock(return_value=fake)))
    fn = tools_mod.get_chapter_outline
    out = await fn.ainvoke({"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地下水环境影响预测"})
    assert out["canonical_chapter_key"] == "地下水环境影响预测"


@pytest.mark.asyncio
async def test_get_templates_tool_returns_list(monkeypatch):
    fake = [{"generalized": "水位{{水位值}}", "slots": [{"name": "水位值"}], "chapter": "5.2"}]
    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: AsyncMock(list_learned_templates_by_key=AsyncMock(return_value=fake)))
    fn = tools_mod.get_templates
    out = await fn.ainvoke({"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "地下水环境影响预测"})
    assert isinstance(out, list) and out[0]["generalized"].startswith("水位")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker exec api-dev pytest /app/test/unit/toolkits/test_domain_factory_tools.py -v`
Expected: FAIL（工具未定义）

- [ ] **Step 3: 实现两个工具**

在 `tools.py` 顶部 import 区加：

```python
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository
```

在文件末尾加：

```python
GET_CHAPTER_OUTLINE_DESCRIPTION = """
取某章节的结构化大纲（入库→写作的桥产出）。
返回 purpose/overview/key_points/content_requirements/regulations/entity_bindings/
expected_tables/expected_charts/expected_formulas/expected_figures/writing_example/writing_hints。
writer 写每章前调用此工具获取本章编写蓝图；compliance-checker 用它取 regulations。
canonical_chapter_key 是归一化章节名（如"地下水环境影响预测"），不是原始章节号。
"""


@tool(
    category="buildin",
    tags=["知识工厂", "大纲"],
    display_name="取章节大纲",
    description=GET_CHAPTER_OUTLINE_DESCRIPTION,
)
async def get_chapter_outline(domain: str, report_type: str, canonical_chapter_key: str) -> dict:
    """获取指定章节的结构化大纲。"""
    repo = DomainFactoryRepository()
    out = await repo.get_outline(domain, report_type, canonical_chapter_key)
    return out or {"error": f"未找到章节大纲: {domain}/{report_type}/{canonical_chapter_key}（该章可能尚未入库）"}


GET_TEMPLATES_DESCRIPTION = """
取某章节（或全部）的结构化段落模板（来自 learned_templates）。
返回 [{generalized, slots, chapter, sample_original, standard_code}]。
template-recommender 用它推荐段落模板；slot-filler 用它取插槽定义。
"""


@tool(
    category="buildin",
    tags=["知识工厂", "模板"],
    display_name="取段落模板",
    description=GET_TEMPLATES_DESCRIPTION,
)
async def get_templates(domain: str, report_type: str, canonical_chapter_key: str | None = None) -> list[dict]:
    """获取结构化段落模板。"""
    repo = DomainFactoryRepository()
    return await repo.list_learned_templates_by_key(domain, report_type, canonical_chapter_key)
```

并在 `domain_factory_repository.py` 加 `list_learned_templates_by_key`（`list_learned_templates` 附近）：

```python
    async def list_learned_templates_by_key(self, domain_code, report_type_code, canonical_chapter_key=None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            stmt = select(DomainFactoryLearnedTemplate).where(
                DomainFactoryLearnedTemplate.domain_code == domain_code,
                DomainFactoryLearnedTemplate.report_type_code == report_type_code,
            )
            if canonical_chapter_key:
                stmt = stmt.where(DomainFactoryLearnedTemplate.canonical_chapter_key == canonical_chapter_key)
            result = await session.execute(stmt)
            return [r.to_dict() for r in result.scalars().all()]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker exec api-dev pytest /app/test/unit/toolkits/test_domain_factory_tools.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5: 验证工具被 agent 可见（若不可见则调整 category）**

Run: `docker exec api-dev python -c "from yuxi.agents.toolkits.service import get_tool_instances_by_category; print([t.name for t in get_tool_instances_by_category('buildin') if 'chapter_outline' in t.name or 'templates' in t.name])"`
Expected: 打印 `['get_chapter_outline', 'get_templates']`。**若为空**：说明 buildin 类目工具未默认注入 agent 运行时——改到 `category="knowledge"`（跟随 list_kbs/query_kb）并在 `toolkits/kbs/tools.py` 的 `get_common_kb_tools()` 末尾追加这两个工具实例。

- [ ] **Step 6: format + 提交**

```bash
docker exec api-dev python -m ruff format package/yuxi/agents/toolkits/buildin/tools.py package/yuxi/repositories/domain_factory_repository.py
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/package/yuxi/repositories/domain_factory_repository.py backend/test/unit/toolkits/test_domain_factory_tools.py
git commit -m "feat(domain-factory): 新增 get_chapter_outline / get_templates 工具"
```

---

## Task 6: 4 个写作 skill 改指向新工具

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`
- Modify: `backend/package/yuxi/agents/skills/buildin/compliance-checker/SKILL.md`
- Modify: `backend/package/yuxi/agents/skills/buildin/template-recommender/SKILL.md`
- Modify: `backend/package/yuxi/agents/skills/buildin/slot-filler/SKILL.md`

**说明：** 纯 prompt 编辑（SKILL.md 是 LLM 剧本），无代码、无单测。改动原则：把"query_kb 过滤 [OUTLINE] / read_file 找 generalized_pattern"替换为"调用 get_chapter_outline / get_templates"。

- [ ] **Step 1: 改 coal-eia-writer**

在 `coal-eia-writer/SKILL.md` 里，把"大纲以知识库 `[OUTLINE]` 查询结果为准"那段（约 47-53 行与 209 行硬约束）改为：

```markdown
## 取大纲（每章写作前必做）
写每一章前，调用 `get_chapter_outline(domain, report_type, canonical_chapter_key)` 获取本章结构化大纲。
canonical_chapter_key 是归一化章节名（如"地下水环境影响预测"）；若不确定 key，先用 get_mindmap 或询问用户确认章节名。
按大纲的 content_requirements 与 expected_tables/charts/formulas/figures 组织本章；用 get_templates(canonical_chapter_key) 拿段落模板填插槽。
```

并删除/替换原 `[OUTLINE]` 相关的 query_kb 指引（209 行硬约束改为"大纲以 get_chapter_outline 结果为准"）。

- [ ] **Step 2: 改 compliance-checker**

在 `compliance-checker/SKILL.md` 里（约 27-31 行），把"query_kb 取 `[OUTLINE]` 的 regulations + content_requirements"改为：

```markdown
## 取法规与内容要求
对每章调用 `get_chapter_outline(domain, report_type, canonical_chapter_key)`，取其 `regulations`（含 standard_code）与 `content_requirements`，逐条核对报告内容是否满足。
```

- [ ] **Step 3: 改 template-recommender**

在 `template-recommender/SKILL.md` 里（约 47-48 行），把"query_kb + read_file /home/gem/kbs/... 取 template_id/slots/generalized_pattern"改为：

```markdown
## 取段落模板
调用 `get_templates(domain, report_type, canonical_chapter_key)` 获取该章结构化段落模板（直接含 generalized/slots/sample_original/standard_code）。
按章节递归：先取本章模板，子章节用各自 canonical_chapter_key 再取。
```

- [ ] **Step 4: 改 slot-filler**

在 `slot-filler/SKILL.md` 里（约 31 行），把"read_file /home/gem/kbs/... 取 slots"改为：

```markdown
## 取插槽定义
插槽定义来自 `get_templates(domain, report_type, canonical_chapter_key)` 返回的 `slots`（每项含 name/type/description/suggested_source）。
填充时每值带 confidence + provenance；缺口用 ask_user_question 向用户确认，绝不编造。
```

- [ ] **Step 5: 验证 skill 依赖工具可执行**

Run: `docker exec api-dev python -c "from yuxi.agents.skills.buildin import BUILTIN_SKILLS; s=[x for x in BUILTIN_SKILLS if x.slug=='coal-eia-writer'][0]; print('coal-eia-writer tool_deps:', s.tool_dependencies)"`
Expected: 打印 coal-eia-writer 现有 tool_dependencies。**把 `get_chapter_outline`、`get_templates` 加入** `coal-eia-writer`、`compliance-checker`、`template-recommender`、`slot-filler` 的 `tool_dependencies`（编辑 `skills/buildin/__init__.py` 里对应 `BuiltinSkillSpec.tool_dependencies`）。

- [ ] **Step 6: 提交**

```bash
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md backend/package/yuxi/agents/skills/buildin/compliance-checker/SKILL.md backend/package/yuxi/agents/skills/buildin/template-recommender/SKILL.md backend/package/yuxi/agents/skills/buildin/slot-filler/SKILL.md backend/package/yuxi/agents/skills/buildin/__init__.py
git commit -m "feat(skills): 4 个写作 skill 改指向 get_chapter_outline/get_templates 工具"
```

---

## Task 7: 端到端验证 + changelog + OpenWolf 收尾

**Files:**
- Modify: `docs/develop-guides/changelog.md`
- Modify: `.wolf/anatomy.md` / `.wolf/memory.md`（OpenWolf 规约）

- [ ] **Step 1: 端到端跑一遍（真实报告 commit）**

用一个已 WAITING_REVIEW 的真实煤矿任务（如 `8778bbc3` 或新上传一份），调用 commit 指定 `kb_cgsguljhor`：

```bash
TOKEN=$(curl -s -X POST http://localhost:5050/api/auth/token -d 'username=admin&password=123' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:5050/api/domain-factory/tasks/<task_id>/commit -H "Content-Type: application/json" -d '{"knowledge_base_id":"kb_cgsguljhor"}'
```

观察 `docker logs api-dev --tail 50 | grep 章节大纲`，确认 "章节大纲产出完成: N 章"。

- [ ] **Step 2: 断言落库**

```bash
docker exec postgres psql -U postgres -d yuxi_know -c "SELECT canonical_chapter_key, chapter_title, jsonb_array_length(regulations) AS regs, jsonb_array_length(content_requirements) AS reqs FROM domain_factory_outlines ORDER BY id;"
docker exec postgres psql -U postgres -d yuxi_know -c "SELECT canonical_chapter_key, count(*) FROM domain_factory_learned_templates WHERE canonical_chapter_key IS NOT NULL GROUP BY canonical_chapter_key;"
```

Expected: outlines 表有每章一行（regs/reqs 可能因抽取质量而异）；learned_templates 的 canonical_chapter_key 已回填。

- [ ] **Step 3: 冒烟工具**

```bash
docker exec api-dev python -c "
import asyncio
from yuxi.agents.toolkits.buildin.tools import get_chapter_outline, get_templates
print(asyncio.run(get_chapter_outline.ainvoke({'domain':'coal','report_type':'eia_report','canonical_chapter_key':'<某章key>'})))
print(asyncio.run(get_templates.ainvoke({'domain':'coal','report_type':'eia_report','canonical_chapter_key':'<某章key>'}))[:1])
"
```

- [ ] **Step 4: 更新 changelog**

在 `docs/develop-guides/changelog.md` 的 `v0.7.1 (current)` → 开发记录顶部加一条：

```markdown
- 新增入库→写作的桥：领域工厂 commit 阶段新增 OutlineProducer，把 ETL 已抽资产（learned_templates/法规/表格/公式/图/图谱实体）按章组装 + LLM 归一化，产出结构化章节大纲到 `domain_factory_outlines` 表（purpose/overview/content_requirements/regulations/entity_bindings/expected_tables/charts/formulas/figures/writing_example/hints）；新增 `get_chapter_outline` / `get_templates` 两个 buildin 工具；coal-eia-writer/compliance-checker/template-recommender/slot-filler 四个 skill 改指向新工具，query_kb 回归纯自由检索。章节身份走 LLM 归一化（`canonical_chapter_key`），不依赖已废弃的静态 headers/routing_config。多报告聚合（content_contract/rigidity）schema 预留、开发后置。详见 [设计 spec](../superpowers/specs/2026-07-11-domain-factory-ingest-write-bridge-design.md)。
```

- [ ] **Step 5: OpenWolf 收尾**

更新 `.wolf/anatomy.md`（新增/改动文件条目）、追加 `.wolf/memory.md` 动作行。

- [ ] **Step 6: 提交**

```bash
git add docs/develop-guides/changelog.md .wolf/anatomy.md .wolf/memory.md
git commit -m "docs(domain-factory): 入库→写作的桥 端到端验证 + changelog"
```

---

## Self-Review（已执行）

- **Spec 覆盖**：spec §3-§7 各决策均有任务（决策1→Task4；决策2→Task2+3；决策3→Task3 LLM 归一；决策4→Task1+5 分仓；决策5 砍 headers→Global Constraints）；§9 前置依赖进 Global Constraints；§10 测试分布在 Task1-5；§11 聚合留 schema 占位（Task1 建表含 content_contract/rigidity 字段），开发后置（无任务，符合 spec）；§13 验收→Task7。
- **spec 缺口修正**：spec §5.2 说 learned_templates 不改结构，但 `get_templates(canonical_chapter_key)` 需要按归一名检索——Task1 加 `canonical_chapter_key` 列 + Task4 回填，解决了 raw chapter 与 canonical key 的错位。
- **Placeholder 扫描**：无 TBD/TODO；每个 code step 都有完整代码。
- **类型一致**：`upsert_outline` / `get_outline` / `list_chapter_keys` / `backfill_template_chapter_key` / `list_learned_templates_by_key` 在定义（Task1）与消费（Task4/5）签名一致；`_group_assets_by_chapter` / `_assemble_deterministic_outline` / `_llm_chapter_meta` / `_produce_outlines_async` 在 Task2-4 一致。
