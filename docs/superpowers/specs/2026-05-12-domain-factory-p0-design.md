# P0: 模板回流机制 + 实体确认后重映射 + 废弃代码清理

## 背景

领域知识工厂的 ETL 流水线中，泛化阶段生成的段落模板只写入 `source_paragraphs[].template` 和 Neo4j 图谱，不会回流到模板库。解析阶段的 `TemplateMatcher` 仍然依赖 `backend/templates/coal_mining/headers/` 下的 30 个静态 JSON 文件。

实体确认后，新增的实体只对未来文档生效，已处于 `WAITING_REVIEW` 状态的任务的插槽映射不会自动更新。

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 模板存储 | 新建 DB 表 | 最干净，支持领域隔离、去重评分、增删改查 |
| 去重策略 | 插槽名集合 + 章节归属 | 同章节下插槽名重叠是可靠的同类模板信号，无需 LLM 调用 |
| 回流时机 | commit_task 时 | 避免未审核数据污染模板库 |
| 重映射范围 | 同领域所有 WAITING_REVIEW 任务 | 新实体对所有待审核任务都有价值，开销小 |

## 1. 新表：domain_factory_learned_templates

```sql
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

**去重逻辑**：

`slot_signature` = 将所有 slot name 按字母排序后用 `|` 拼接。

同一 `(domain_code, chapter, slot_signature)` 三元组视为同一类模板：
- 新模板：INSERT
- 已有模板：`source_count += 1`，`generalized` 取字符数更长者，`sample_original` 取更长者

## 2. 模型与 Repository

### 2.1 SQLAlchemy 模型

在 `models_domain_factory.py` 中新增 `DomainFactoryLearnedTemplate` 类，字段与上述表结构对应。

提供 `to_dict()` 方法返回：
```python
{
    "id", "domain_code", "chapter", "generalized",
    "slots", "slot_signature", "source_count",
    "sample_original", "metadata",
    "created_at", "updated_at"
}
```

### 2.2 Repository 方法

在 `DomainFactoryRepository` 中新增：

| 方法 | 用途 |
|------|------|
| `upsert_learned_template(domain_code, chapter, generalized, slots, slot_signature, sample_original, metadata)` | 幂等写入，ON CONFLICT 更新 source_count 和取较长内容 |
| `list_learned_templates(domain_code, limit=200)` | 按频率降序返回，供 TemplateLibrary 加载 |
| `delete_learned_template(id)` | 删除指定模板 |
| `count_learned_templates(domain_code)` | 统计数量 |

## 3. 泛化结果回流

### 3.1 回流触发点

在 `_commit_pipeline_async` 的"阶段3: 完成"之前（知识库入库和图谱构建之后），新增回流步骤：

```
_learned_templates_from_task(task_detail) → 写入 DB
```

仅对已审核确认的任务执行，不在 `_etl_pipeline_async` 泛化阶段执行。

### 3.2 回流逻辑

```python
async def _save_learned_templates_from_task(self, task_detail: dict) -> int:
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
            continue  # 跳过过短的模板

        slots = template.get("slots", [])
        slot_names = sorted(s.get("name", "") for s in slots if isinstance(s, dict))
        slot_signature = "|".join(slot_names)

        # 章节归属：优先用标题段落的 title，否则用 section_path 构造
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

    return saved
```

## 4. TemplateLibrary 集成

### 4.1 加载策略

修改 `TemplateLibrary`，支持双源加载：

1. 先从静态 JSON 文件加载（种子数据，不删除）
2. 再从 DB `domain_factory_learned_templates` 加载（按 `source_count DESC` 排序）
3. 合并时：DB 模板追加到模板列表，如果 `chapter` + `slot_signature` 与文件模板重复，DB 模板优先（因为经过了人工审核）

### 4.2 实现方式

在 `TemplateLibrary` 中新增 `_load_from_db()` 方法：

```python
def _load_from_db(self) -> None:
    """从 DB 加载学习到的模板"""
    # 同步调用异步 repository —— 使用 asyncio.run 或由调用方传入 event loop
    # 将 DB 模板转换为与 JSON 文件模板相同的格式
    # 追加到 self.templates
```

由于 `TemplateLibrary.load_templates()` 是同步方法，而 DB 查询是异步的，需要在 `DomainFactoryService` 层面协调：service 在 `_get_template_matcher()` 时先从 DB 加载模板，然后注入到 `TemplateLibrary`。

具体方案：

- `TemplateLibrary` 新增 `add_templates_from_list(templates: list[dict])` 方法，支持外部注入模板
- `DomainFactoryService._get_template_matcher()` 中，加载文件模板后，再从 repository 查询 DB 模板注入

### 4.3 DB 模板格式

DB 模板转换为 `TemplateMatcher` 所需格式的映射：

| DB 字段 | Matcher 格式字段 |
|---------|-----------------|
| `chapter` | `title` (匹配用) |
| `generalized` | `generalized_pattern` |
| `slots` | `slots` |
| `domain_code` | `domain` |
| `source_count` | `score` (排序用) |

## 5. 实体确认后重映射

### 5.1 触发时机

在 `confirm_proposed_entities()` 保存实体完成后，追加重映射步骤。

### 5.2 重映射逻辑

```python
async def _remap_waiting_review_tasks(self, domain_code: str) -> int:
    """对同领域 WAITING_REVIEW 任务重新映射插槽的 entity_ref"""
    # 1. 获取同领域所有 WAITING_REVIEW 任务
    pending_tasks = await self.repo.list_pending_tasks_by_domain(domain_code)

    # 2. 重新加载 SlotEntityMapper（它会自动读取最新实体库）
    from yuxi.services.entity_meta_service import SlotEntityMapper
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

            mapped_slots = mapper.map_slots(raw_slots, paragraph_context=para.get("content", ""))

            # 检测是否有变化
            for i, slot in enumerate(mapped_slots):
                old_ref = raw_slots[i].get("entity_ref", "") if i < len(raw_slots) else ""
                new_ref = slot.get("entity_ref", "")
                if new_ref and not old_ref:
                    raw_slots[i]["entity_ref"] = new_ref
                    changed = True

        if changed:
            await self.repo.update_task(task_id, {"source_paragraphs": paragraphs})
            updated += 1

    return updated
```

### 5.3 Repository 新增方法

在 `DomainFactoryRepository` 中新增：

```python
async def list_pending_tasks_by_domain(self, domain_code: str) -> list[dict]:
    """按领域代码查找所有 WAITING_REVIEW 状态的任务"""
```

需要 JOIN `DomainFactoryDomain` 表通过 `code` 字段筛选。

## 6. 废弃代码清理

### 6.1 删除 DomainFactorySavedSection

涉及的文件和位置：

| 文件 | 操作 |
|------|------|
| `models_domain_factory.py` | 删除 `DomainFactorySavedSection` 类 |
| `domain_factory_repository.py` | 删除 `get_saved_section`, `list_saved_sections`, `get_saved_section_by_domain_type`, `upsert_saved_section`, `save_section`, `delete_saved_section` 方法 |
| `domain_factory_service.py` | 删除 `get_saved_sections`, `get_saved_section_detail`, `import_saved_section`, `_build_section_tree_from_paragraphs`, `_merge_section_trees`, `_flatten_section_tree`, `_generate_writing_guidance`, `_generate_entity_bindings` 及所有 golden outline 相关方法 |
| `domain_factory_router.py` | 删除 `/saved-sections` 相关的 4 个端点 |
| `domain_factory_api.js` | 删除 `getSavedSections`, `getSavedSectionDetail`, `importSavedSection` 三个方法 |
| `manager.py` | 删除 `domain_factory_saved_sections` 建表语句 |
| `migrate_domain_factory.sql` | 删除 `domain_factory_saved_sections` 建表段 |

### 6.2 删除 structured_data 列

| 文件 | 操作 |
|------|------|
| `models_domain_factory.py` | 删除 `DomainFactoryTask.structured_data` 列 |
| `domain_factory_service.py` | 删除 `get_task_detail` 和 `save_task_step` 中对 `structured_data` 的引用 |
| `migrate_domain_factory.sql` | 移除建表语句中的 `structured_data` 列 |
| `manager.py` | 移除建表语句中的 `structured_data` 列 |

### 6.3 迁移脚本更新

在 `migrate_domain_factory.sql` 中追加：

```sql
-- 清理废弃表和列
DROP TABLE IF EXISTS domain_factory_saved_sections;
ALTER TABLE domain_factory_tasks DROP COLUMN IF EXISTS structured_data;

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

## 7. 文件变更清单

| 文件 | 变更类型 |
|------|---------|
| `storage/postgres/models_domain_factory.py` | 新增 `DomainFactoryLearnedTemplate`，删除 `DomainFactorySavedSection`，删除 `structured_data` |
| `repositories/domain_factory_repository.py` | 新增 4 个 learned_template 方法 + 1 个 `list_pending_tasks_by_domain`，删除 6 个 saved_section 方法 |
| `services/domain_factory_service.py` | 新增 `_save_learned_templates_from_task` + `_remap_waiting_review_tasks`，修改 `_commit_pipeline_async`、`confirm_proposed_entities`、`_get_template_matcher`，删除 saved_section 和 golden outline 相关代码 |
| `services/template_library.py` | 新增 `add_templates_from_list` 方法 |
| `routers/domain_factory_router.py` | 删除 4 个 saved-sections 端点，新增模板管理端点（可选） |
| `storage/postgres/manager.py` | 更新建表语句 |
| `scripts/migrate_domain_factory.sql` | 追加新表、清理旧表 |
| `apis/domain_factory_api.js` | 删除 3 个 saved-sections API |
