# Domain Factory P0: 模板回流 + 实体重映射 + 废弃清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现泛化模板回流到学习模板库、实体确认后自动重映射待审核任务、清理废弃代码。

**Architecture:** 新建 `domain_factory_learned_templates` 表存储学习到的模板，commit 时从已审核段落提取模板并去重写入。`TemplateLibrary` 新增外部注入方法，由 service 层协调 DB 模板加载。实体确认后遍历同领域 WAITING_REVIEW 任务更新 `entity_ref`。同时删除 `domain_factory_saved_sections` 表和 `structured_data` 列及相关死代码。

**Tech Stack:** Python 3.12+, SQLAlchemy async, PostgreSQL, Vue 3

---

### Task 1: DB Schema — 新增模型 + 清理旧模型 + 更新迁移

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`
- Modify: `backend/package/yuxi/storage/postgres/manager.py`
- Modify: `backend/scripts/migrate_domain_factory.sql`

- [ ] **Step 1: 在 `models_domain_factory.py` 中新增 `DomainFactoryLearnedTemplate` 类**

在文件末尾追加：

```python
class DomainFactoryLearnedTemplate(Base):
    """领域知识工厂 - 学习到的段落模板"""

    __tablename__ = "domain_factory_learned_templates"
    __table_args__ = (
        UniqueConstraint("domain_code", "chapter", "slot_signature", name="uq_dflt_domain_chapter_sig"),
        Index("idx_dflt_chapter", "domain_code", "chapter"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=False, index=True)
    chapter = Column(String(255), nullable=False, default="")
    generalized = Column(Text, nullable=False)
    slots = Column(JSON, nullable=False, default=list)
    slot_signature = Column(String(255), nullable=False, default="")
    source_count = Column(Integer, nullable=False, default=1)
    sample_original = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain_code": self.domain_code,
            "chapter": self.chapter,
            "generalized": self.generalized,
            "slots": self.slots or [],
            "slot_signature": self.slot_signature,
            "source_count": self.source_count,
            "sample_original": self.sample_original,
            "metadata": self.metadata or {},
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
```

- [ ] **Step 2: 在 `models_domain_factory.py` 中删除 `DomainFactorySavedSection` 类（约 line 100-123）**

删除整个 `DomainFactorySavedSection` 类定义。

- [ ] **Step 3: 在 `models_domain_factory.py` 中删除 `DomainFactoryTask.structured_data` 列**

从 `DomainFactoryTask` 类中删除这一行：
```python
    structured_data = Column(JSON, nullable=True)
```

- [ ] **Step 4: 更新 `manager.py` 的 import 和建表语句**

在 import 中将 `DomainFactorySavedSection` 替换为 `DomainFactoryLearnedTemplate`：
```python
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryTask,
    DomainFactoryPromptConfig,
    DomainFactoryLearnedTemplate,
)
```

删除 `domain_factory_saved_sections` 的建表语句块，替换为：
```python
"CREATE TABLE IF NOT EXISTS domain_factory_learned_templates ("
"    id SERIAL PRIMARY KEY,"
"    domain_code VARCHAR(64) NOT NULL,"
"    chapter VARCHAR(255) NOT NULL DEFAULT '',"
"    generalized TEXT NOT NULL,"
"    slots JSONB NOT NULL DEFAULT '[]',"
"    slot_signature VARCHAR(255) NOT NULL DEFAULT '',"
"    source_count INTEGER NOT NULL DEFAULT 1,"
"    sample_original TEXT,"
"    metadata JSONB DEFAULT '{}',"
"    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
"    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
"    UNIQUE(domain_code, chapter, slot_signature)"
")",
```

同时删除建表语句中的 `structured_data JSONB` 行和 `domain_factory_saved_sections` 相关的建表/索引语句。

- [ ] **Step 5: 更新 `migrate_domain_factory.sql`**

删除 `domain_factory_saved_sections` 建表段和 `structured_data` 列。在末尾（COMMIT 之前）追加清理和新表：

```sql
-- 清理废弃表和列
DROP TABLE IF EXISTS domain_factory_saved_sections;

-- 新增学习模板表
CREATE TABLE IF NOT EXISTS domain_factory_learned_templates (
    id SERIAL PRIMARY KEY,
    domain_code VARCHAR(64) NOT NULL,
    chapter VARCHAR(255) NOT NULL DEFAULT '',
    generalized TEXT NOT NULL,
    slots JSONB NOT NULL DEFAULT '[]',
    slot_signature VARCHAR(255) NOT NULL DEFAULT '',
    source_count INTEGER NOT NULL DEFAULT 1,
    sample_original TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_code, chapter, slot_signature)
);
CREATE INDEX IF NOT EXISTS idx_dflt_domain ON domain_factory_learned_templates(domain_code);
CREATE INDEX IF NOT EXISTS idx_dflt_chapter ON domain_factory_learned_templates(domain_code, chapter);
```

- [ ] **Step 6: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/storage/postgres/models_domain_factory.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 7: Commit**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/scripts/migrate_domain_factory.sql
git commit -m "refactor: 新增 DomainFactoryLearnedTemplate 模型，删除 SavedSection 和 structured_data"
```

---

### Task 2: Repository — 新增学习模板方法 + 删除 SavedSection 方法

**Files:**
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`

- [ ] **Step 1: 更新 import**

将 import 中的 `DomainFactorySavedSection` 替换为 `DomainFactoryLearnedTemplate`：

```python
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryTask,
    DomainFactoryLearnedTemplate,
    DomainFactoryPromptConfig,
)
```

- [ ] **Step 2: 删除所有 SavedSection 方法**

删除以下 6 个方法：
- `get_saved_section`
- `list_saved_sections`
- `get_saved_section_by_domain_type`
- `upsert_saved_section`
- `save_section`
- `delete_saved_section`

即 `# ========== Context ==========` 标注以下直到 `# ========== Prompt Config ==========` 之间的所有方法。

- [ ] **Step 3: 新增学习模板方法**

在删除 SavedSection 方法的位置（`# ========== Prompt Config ==========` 之前）插入：

```python
    # ========== Learned Templates ==========

    async def upsert_learned_template(
        self,
        domain_code: str,
        chapter: str,
        generalized: str,
        slots: list,
        slot_signature: str,
        sample_original: str | None = None,
        metadata: dict | None = None,
    ) -> DomainFactoryLearnedTemplate:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryLearnedTemplate).where(
                    DomainFactoryLearnedTemplate.domain_code == domain_code,
                    DomainFactoryLearnedTemplate.chapter == chapter,
                    DomainFactoryLearnedTemplate.slot_signature == slot_signature,
                )
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                template = DomainFactoryLearnedTemplate(
                    domain_code=domain_code,
                    chapter=chapter,
                    generalized=generalized,
                    slots=slots,
                    slot_signature=slot_signature,
                    sample_original=sample_original,
                    metadata=metadata,
                )
                session.add(template)
            else:
                existing.source_count += 1
                if len(generalized) > len(existing.generalized or ""):
                    existing.generalized = generalized
                if sample_original and len(sample_original) > len(existing.sample_original or ""):
                    existing.sample_original = sample_original
                if metadata:
                    existing.metadata = metadata
        return existing if existing else template

    async def list_learned_templates(
        self, domain_code: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = (
                select(DomainFactoryLearnedTemplate)
                .order_by(DomainFactoryLearnedTemplate.source_count.desc())
                .limit(limit)
            )
            if domain_code:
                query = query.where(DomainFactoryLearnedTemplate.domain_code == domain_code)
            result = await session.execute(query)
            templates = result.scalars().all()
            return [t.to_dict() for t in templates]

    async def delete_learned_template(self, template_id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryLearnedTemplate).where(
                    DomainFactoryLearnedTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()
            if template is None:
                return False
            await session.delete(template)
        return True

    async def count_learned_templates(self, domain_code: str | None = None) -> int:
        async with pg_manager.get_async_session_context() as session:
            query = select(func.count(DomainFactoryLearnedTemplate.id))
            if domain_code:
                query = query.where(DomainFactoryLearnedTemplate.domain_code == domain_code)
            result = await session.execute(query)
            return result.scalar() or 0
```

- [ ] **Step 4: 新增 `list_pending_tasks_by_domain` 方法**

在 Task 方法区域（`delete_task` 方法之后）追加：

```python
    async def list_pending_tasks_by_domain(self, domain_code: str) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .join(DomainFactoryDomain, DomainFactoryTask.domain_id == DomainFactoryDomain.id)
                .where(
                    DomainFactoryDomain.code == domain_code,
                    DomainFactoryTask.status == "WAITING_REVIEW",
                )
            )
            tasks = result.unique().scalars().all()
            return [t.to_summary_dict() for t in tasks]
```

- [ ] **Step 5: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/repositories/domain_factory_repository.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/repositories/domain_factory_repository.py
git commit -m "refactor: 新增学习模板 Repository 方法，删除 SavedSection 方法"
```

---

### Task 3: Service 清理 — 删除 SavedSection/Golden Outline + structured_data 引用

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

> 注意：此文件约 4100 行，删除量大。按以下步骤逐个删除方法。

- [ ] **Step 1: 删除 SavedSection 相关方法**

删除以下 service 方法（完整方法体，从 `async def` / `def` 到下一个方法定义前）：

1. `get_saved_sections` (line ~3220)
2. `get_saved_section_detail` (line ~3226)
3. `import_saved_section` (line ~3232)

- [ ] **Step 2: 删除 Golden Outline 相关方法**

删除以下方法：

1. `_build_section_tree_from_paragraphs` (line ~3253)
2. `_flatten_section_tree` (line ~3295)
3. `_calc_title_similarity` (line ~3306)
4. `_collect_section_content` (line ~3331)
5. `_generate_writing_guidance` (line ~3378)
6. `_generate_entity_bindings` (line ~3472)
7. `_get_domain_entity_names` (line ~3560)
8. `_merge_section_trees` (line ~3571)
9. `_append_sections` (line ~3628)
10. `_evolve_outline` (line ~3643)

- [ ] **Step 3: 删除 `_reingest_pipeline_async` 中的 `_evolve_outline` 调用**

在 `_reingest_pipeline_async` 方法中（约 line 3081-3087），删除：

```python
            # 更新领域大纲（Outline_Collection）
            try:
                await context.set_progress(85.0, "正在更新领域大纲...")
                await context.set_message("正在更新领域大纲...")
                await service._evolve_outline(task_detail, knowledge_base_id)
            except Exception as e:
                logger.warning(f"大纲更新失败（不阻断再入库）: {e}")
```

- [ ] **Step 4: 删除 `structured_data` 引用**

在 `get_task_detail` 方法中（约 line 2305），删除：
```python
            "structured_data": task.structured_data or {},
```

在 `save_task_step` 方法中（约 line 2383），从 field_name 列表中删除 `"structured_data"`。

- [ ] **Step 5: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "refactor: 删除 SavedSection、Golden Outline、structured_data 相关代码"
```

---

### Task 4: Router + Frontend 清理

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`
- Modify: `web/src/apis/domain_factory_api.js`

- [ ] **Step 1: 删除 router 中 saved-sections 相关端点**

在 `domain_factory_router.py` 中删除以下端点（约 line 491-539）：

1. `get_saved_sections` (GET `/saved-sections`)
2. `get_saved_section_detail` (GET `/saved-sections/{section_id}`)
3. `import_saved_section` (POST `/saved-sections/{section_id}/import`)

即 `# ========== Saved Sections ==========` 注释块下的所有路由函数。

- [ ] **Step 2: 验证 router 语法**

```bash
python -c "import ast; ast.parse(open('backend/server/routers/domain_factory_router.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: 删除前端 saved-sections API 方法**

在 `web/src/apis/domain_factory_api.js` 中删除三个方法：

1. `getSavedSections` (约 line 344-358)
2. `getSavedSectionDetail` (约 line 361-364)
3. `importSavedSection` (约 line 367-375)

- [ ] **Step 4: Commit**

```bash
git add backend/server/routers/domain_factory_router.py web/src/apis/domain_factory_api.js
git commit -m "refactor: 删除 saved-sections 路由和前端 API"
```

---

### Task 5: 模板回流 — 泛化结果保存到学习模板库

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 新增 `_save_learned_templates_from_task` 方法**

在 `_build_structured_document` 方法之后追加：

```python
    async def _save_learned_templates_from_task(self, task_detail: dict[str, Any]) -> int:
        """从已提交任务中提取高质量模板，回流到学习模板库"""
        domain_code = task_detail.get("domain", "coal")
        paragraphs = task_detail.get("source_paragraphs", [])
        saved = 0

        for para in paragraphs:
            template = para.get("template", {})
            if not isinstance(template, dict):
                continue
            generalized = template.get("generalized", "")
            if not generalized or len(generalized) < 20:
                continue

            slots = template.get("slots", [])
            slot_names = sorted(s.get("name", "") for s in slots if isinstance(s, dict))
            slot_signature = "|".join(slot_names)
            section_path = para.get("section_path", [])
            chapter = para.get("title", "") or (
                ".".join(str(p) for p in section_path) if section_path else ""
            )
            sample_original = para.get("original", para.get("content", ""))
            metadata = template.get("metadata", {})

            await self.repo.upsert_learned_template(
                domain_code=domain_code,
                chapter=chapter,
                generalized=generalized,
                slots=slots,
                slot_signature=slot_signature,
                sample_original=sample_original,
                metadata=metadata,
            )
            saved += 1

        if saved > 0:
            logger.info(f"模板回流完成: 领域={domain_code}, 保存/更新={saved} 个模板")
        return saved
```

- [ ] **Step 2: 在 `_commit_pipeline_async` 中集成回流**

在 `_commit_pipeline_async` 的图谱构建（约 line 2610 `logger.warning(f"知识图谱构建失败..."`) 之后、"阶段3: 完成" 之前，插入：

```python
            # ========== 阶段2.8: 模板回流 (LEARNED TEMPLATES) ==========
            try:
                await context.set_progress(90.0, "正在回写学习模板...")
                await context.set_message("正在回写学习模板...")
                learned_count = await service._save_learned_templates_from_task(task_detail)
                logger.info(f"模板回流: {learned_count} 个段落模板已保存")
            except Exception as e:
                logger.warning(f"模板回流失败（不阻断入库）: {e}")
```

- [ ] **Step 3: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "feat: 模板回流机制 — commit 时将泛化模板写入学习模板库"
```

---

### Task 6: TemplateLibrary 集成 — 支持从 DB 加载学习模板

**Files:**
- Modify: `backend/package/yuxi/services/template_library.py`
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 在 `TemplateLibrary` 中新增 `add_templates_from_list` 方法**

在 `template_library.py` 的 `TemplateLibrary` 类中（`load_templates` 方法之后）追加：

```python
    def add_templates_from_list(self, templates: list[dict[str, Any]]) -> None:
        """从外部列表注入模板（如 DB 学习模板）"""
        if not self._loaded:
            self.load_templates()

        for tpl in templates:
            template_id = tpl.get("id")
            if not template_id:
                continue

            converted = {
                "template_id": f"learned_{template_id}",
                "title": tpl.get("chapter", ""),
                "generalized_pattern": tpl.get("generalized", ""),
                "slots": tpl.get("slots", []),
                "domain": tpl.get("domain_code", ""),
                "score": tpl.get("source_count", 1),
                "routing": tpl.get("metadata", {}).get("routing", ""),
                "source": "learned",
            }
            self.templates[converted["template_id"]] = converted

        logger.info(f"从外部注入 {len(templates)} 个学习模板")
```

同时确保文件顶部有 `from yuxi.utils.logging_config import logger` 的 import（如缺失则添加）。

- [ ] **Step 2: 修改 `_get_template_matcher` 加载 DB 模板**

在 `domain_factory_service.py` 的 `_get_template_matcher` 方法中，在创建 `TemplateMatcher` 之后追加 DB 模板注入逻辑：

将现有的 `_get_template_matcher` 方法从：

```python
    def _get_template_matcher(self, domain: str = "coal_mining") -> Any:
        ...
        try:
            from yuxi.services.template_library import TemplateLibrary
            from yuxi.services.template_matcher import TemplateMatcher

            library = TemplateLibrary()
            templates = library.get_templates_by_domain(domain)
            if not templates:
                templates = library.get_all_templates()

            if templates:
                self._template_library = library
                self._template_matcher = TemplateMatcher(templates)
                logger.info(f"模板匹配器已加载: {len(templates)} 个模板, domain={domain}")
            else:
                logger.info("模板库为空，跳过模板匹配")
        except Exception as e:
            logger.warning(f"加载模板匹配器失败: {e}")

        return self._template_matcher
```

改为：

```python
    async def _get_template_matcher(self, domain: str = "coal_mining") -> Any:
        """获取或创建模板匹配器（延迟加载，含 DB 学习模板）"""
        if self._template_matcher is not None:
            return self._template_matcher

        try:
            from yuxi.services.template_library import TemplateLibrary
            from yuxi.services.template_matcher import TemplateMatcher

            library = TemplateLibrary()
            templates = library.get_templates_by_domain(domain)
            if not templates:
                templates = library.get_all_templates()

            # 从 DB 加载学习模板并注入
            try:
                domain_code = domain.replace("_mining", "").replace("_", "")
                if not domain_code:
                    domain_code = "coal"
                db_templates = await self.repo.list_learned_templates(domain_code=domain_code)
                if db_templates:
                    library.add_templates_from_list(db_templates)
            except Exception as db_err:
                logger.warning(f"加载 DB 学习模板失败: {db_err}")

            all_templates = list(library.templates.values())
            if all_templates:
                self._template_library = library
                self._template_matcher = TemplateMatcher(all_templates)
                logger.info(f"模板匹配器已加载: {len(all_templates)} 个模板 (含 DB 学习模板), domain={domain}")
            else:
                logger.info("模板库为空，跳过模板匹配")
        except Exception as e:
            logger.warning(f"加载模板匹配器失败: {e}")

        return self._template_matcher
```

注意：方法签名从 `def` 改为 `async def`，需要更新所有调用处。

- [ ] **Step 3: 更新 `_etl_pipeline_async` 中的 `_get_template_matcher` 调用**

在 `_etl_pipeline_async` 中（约 line 589-590），将：

```python
                matcher = service._get_template_matcher()
```

改为：

```python
                matcher = await service._get_template_matcher()
```

- [ ] **Step 4: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/template_library.py', encoding='utf-8').read()); print('OK')"
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/template_library.py backend/package/yuxi/services/domain_factory_service.py
git commit -m "feat: TemplateLibrary 支持从 DB 加载学习模板"
```

---

### Task 7: 实体确认后重映射

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 新增 `_remap_waiting_review_tasks` 方法**

在 `confirm_proposed_entities` 方法之后追加：

```python
    async def _remap_waiting_review_tasks(self, domain_code: str) -> int:
        """对同领域 WAITING_REVIEW 任务重新映射插槽的 entity_ref"""
        from yuxi.services.entity_meta_service import SlotEntityMapper

        pending_tasks = await self.repo.list_pending_tasks_by_domain(domain_code)
        if not pending_tasks:
            return 0

        mapper = SlotEntityMapper()
        updated = 0

        for task_summary in pending_tasks:
            task_id = task_summary["id"]
            task = await self.repo.get_task(task_id)
            if not task or not task.source_paragraphs:
                continue

            paragraphs = task.source_paragraphs
            changed = False

            for para in paragraphs:
                template = para.get("template", {})
                if not isinstance(template, dict):
                    continue
                raw_slots = template.get("slots", [])
                if not raw_slots:
                    continue

                try:
                    mapped_slots = mapper.map_slots(
                        raw_slots, paragraph_context=para.get("content", "")
                    )
                except Exception:
                    continue

                for i, mapped in enumerate(mapped_slots):
                    if i >= len(raw_slots):
                        break
                    old_ref = raw_slots[i].get("entity_ref", "")
                    new_ref = mapped.get("entity_ref", "")
                    if new_ref and not old_ref:
                        raw_slots[i]["entity_ref"] = new_ref
                        changed = True

            if changed:
                await self.repo.update_task(task_id, {"source_paragraphs": paragraphs})
                updated += 1

        if updated > 0:
            logger.info(f"实体重映射完成: 领域={domain_code}, 更新={updated} 个任务")
        return updated
```

- [ ] **Step 2: 在 `confirm_proposed_entities` 末尾追加重映射调用**

在 `confirm_proposed_entities` 方法的 `return` 语句之前（约 line 3900+），追加：

```python
        # 触发同领域待审核任务的重映射
        try:
            remapped = await self._remap_waiting_review_tasks(domain_code)
            if remapped > 0:
                logger.info(f"实体确认后重映射: {remapped} 个任务已更新")
        except Exception as remap_err:
            logger.warning(f"实体重映射失败（不影响实体保存）: {remap_err}")
```

- [ ] **Step 3: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "feat: 实体确认后自动重映射同领域 WAITING_REVIEW 任务"
```

---

### Task 8: 格式化 + 端到端验证

**Files:**
- All modified files

- [ ] **Step 1: 运行后端格式化**

```bash
make format
```

- [ ] **Step 2: 验证所有修改文件的语法**

```bash
python -c "
import ast
files = [
    'backend/package/yuxi/storage/postgres/models_domain_factory.py',
    'backend/package/yuxi/repositories/domain_factory_repository.py',
    'backend/package/yuxi/services/domain_factory_service.py',
    'backend/package/yuxi/services/template_library.py',
    'backend/server/routers/domain_factory_router.py',
    'backend/package/yuxi/storage/postgres/manager.py',
]
for f in files:
    ast.parse(open(f, encoding='utf-8').read())
    print(f'OK: {f}')
"
```

- [ ] **Step 3: 前端 lint**

```bash
cd web && pnpm run lint
```

- [ ] **Step 4: 重启 Docker 容器并验证**

```bash
docker restart api-dev
docker logs api-dev --tail 20 -f
```

验证日志中无 import 错误或表创建失败。检查新表是否创建：
```bash
docker exec -i postgres psql -U postgres -d yuxi_know -c "\dt domain_factory_learned_templates"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: P0 实现 — 模板回流 + 实体重映射 + 废弃清理"
```
