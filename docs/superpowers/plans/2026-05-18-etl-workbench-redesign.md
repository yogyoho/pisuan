# ETL 工作台全链路重设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ETL pipeline 的分类/泛化规则从硬编码抽离为可管理配置，修复分类质量，改造前端工作台支持编辑和规则管理。

**Architecture:** 后端新增 `domain_factory_rules` 表存储分类规则，pipeline 改为三阶段分类器（规则→LLM→回退）。前端合并 Prompt 管理与规则管理为统一 Pipeline 配置页，ETL 工作台 Tab 1 增加编辑能力和折叠布局。

**Tech Stack:** Python 3.12+ / FastAPI / SQLAlchemy / Vue 3 + Ant Design Vue / PostgreSQL

---

## Phase 1: 后端分类质量修复（P0）

### Task 1: 诊断空分类根因

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 查询数据库，分析空分类段落的特征**

Run:
```bash
docker exec postgres psql -U postgres -d yuxi_know -c "
SELECT
  CASE WHEN p->>'content' IS NULL OR p->>'content' = '' THEN 'empty' ELSE 'has_content' END as content_state,
  CASE WHEN p->>'is_title' = 'true' THEN 'title' ELSE 'non_title' END as is_title,
  COUNT(*) as cnt
FROM domain_factory_tasks, json_array_elements(source_paragraphs::json) AS p
WHERE status = 'WAITING_REVIEW' AND (p->>'classify_type' IS NULL OR p->>'classify_type' = '')
GROUP BY 1, 2 ORDER BY cnt DESC;"
```

Expected: 看到空分类段落的 content 状态分布（空内容 / 有内容 / 标题 / 非标题）

- [ ] **Step 2: 检查 _classify_paragraphs 方法的异常处理**

Read `domain_factory_service.py` and find `_classify_paragraphs`. Look for try/except blocks that silently catch exceptions and leave classify_type empty. Record the exact line numbers.

Expected: Identify where exceptions are swallowed, resulting in no classify_type being set.

- [ ] **Step 3: 确认根因后提交诊断笔记**

Create a note in `.wolf/cerebrum.md` under `## Key Learnings` documenting the root cause of empty classifications.

---

### Task 2: 修复已知分类 Bug

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

_前提：以下 bug 已在之前的会话中定位但需要在当前代码中验证状态。_

- [ ] **Step 1: 验证 _SLOT_PATTERNS 修复状态**

Run:
```bash
docker exec api-dev sh -c "sed -n '1334,1338p' /app/package/yuxi/services/domain_factory_service.py"
```

Expected: 三个字符串通过隐式拼接组成一个完整的正则（无逗号分隔）。

- [ ] **Step 2: 验证 schema_variables=[] 修复状态**

Run:
```bash
docker exec api-dev sh -c "grep 'schema_variables' /app/package/yuxi/services/domain_factory_service.py | head -5"
```

Expected: `schema_variables=[]` 而非 `schema_variables=variables`。

- [ ] **Step 3: 验证 parent_title title_map 修复状态**

Run:
```bash
docker exec api-dev sh -c "grep 'key not in title_map' /app/package/yuxi/services/domain_factory_service.py"
```

Expected: 找到 `if key not in title_map:` 确保不会覆盖重复路径。

- [ ] **Step 4: 如果任何修复未生效，应用修复并提交**

Verify syntax: `python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"`

Commit: `git commit -m "fix: 验证并确认分类 pipeline 已知 bug 修复状态"`

---

### Task 3: 新增 domain_factory_rules 数据表

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/manager.py`
- Create: `backend/package/yuxi/storage/postgres/models_rules.py`
- Modify: `backend/package/yuxi/storage/postgres/__init__.py`

- [ ] **Step 1: 创建 rules ORM 模型**

Create `backend/package/yuxi/storage/postgres/models_rules.py`:

```python
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class DomainFactoryRule(Base):
    __tablename__ = "domain_factory_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=True, comment="领域代码，NULL=全局")
    rule_type = Column(String(32), nullable=False, comment="classify/slot_pattern/narrative_subtype/legal_pattern")
    name = Column(String(128), nullable=False, comment="规则名称")
    pattern = Column(Text, nullable=False, comment="正则表达式或关键词JSON")
    target_type = Column(String(32), nullable=True, comment="命中后的classify_type")
    priority = Column(Integer, nullable=False, default=100)
    enabled = Column(Boolean, nullable=False, default=True)
    hit_count = Column(Integer, nullable=False, default=0)
    miss_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 在 manager.py 中添加建表语句**

Find the domain factory table creation block in `manager.py` (after the existing `domain_factory_prompt_configs` table) and add:

```python
"CREATE TABLE IF NOT EXISTS domain_factory_rules ("
"    id SERIAL PRIMARY KEY,"
"    domain_code VARCHAR(64),"
"    rule_type VARCHAR(32) NOT NULL,"
"    name VARCHAR(128) NOT NULL,"
"    pattern TEXT NOT NULL,"
"    target_type VARCHAR(32),"
"    priority INTEGER NOT NULL DEFAULT 100,"
"    enabled BOOLEAN NOT NULL DEFAULT TRUE,"
"    hit_count INTEGER NOT NULL DEFAULT 0,"
"    miss_count INTEGER NOT NULL DEFAULT 0,"
"    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
"    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
")",
"CREATE INDEX IF NOT EXISTS idx_dfr_type ON domain_factory_rules(rule_type)",
"CREATE INDEX IF NOT EXISTS idx_dfr_domain ON domain_factory_rules(domain_code)",
```

- [ ] **Step 3: 验证语法**

Run: `python -c "import ast; ast.parse(open('backend/package/yuxi/storage/postgres/manager.py', encoding='utf-8').read()); print('OK')"`

- [ ] **Step 4: 重启 api-dev 让建表生效**

Run: `docker restart api-dev`

Wait 10s, then verify:
```bash
docker exec postgres psql -U postgres -d yuxi_know -c "\d domain_factory_rules"
```

Expected: Table with all columns.

- [ ] **Step 5: 提交**

```bash
git add backend/package/yuxi/storage/postgres/models_rules.py backend/package/yuxi/storage/postgres/manager.py
git commit -m "feat: 新增 domain_factory_rules 数据表"
```

---

### Task 4: 迁移硬编码规则到默认种子数据

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/manager.py`
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 在 manager.py 建表后插入默认规则种子**

Add after the CREATE TABLE statement for `domain_factory_rules`:

```python
# Default classification rules (seed)
"INSERT INTO domain_factory_rules (rule_type, name, pattern, target_type, priority) VALUES "
"('classify', '表格-HTML标签', r'<table[\\s>]', 'table', 10) ON CONFLICT DO NOTHING",
"INSERT INTO domain_factory_rules (rule_type, name, pattern, target_type, priority) VALUES "
"('classify', '标题-文档标题行', '', 'heading', 5) ON CONFLICT DO NOTHING",
"INSERT INTO domain_factory_rules (rule_type, name, pattern, target_type, priority) VALUES "
"('legal_reference', '法律引用-标准号', r'(?:GB|HJ|MT|JT|TB|DL|YS|SL|HY|CJJ|JGJ|ZBJ|HG|SH)\\s*[/－-]?\\s*\\d+', 'legal_reference', 20) ON CONFLICT DO NOTHING",
"INSERT INTO domain_factory_rules (rule_type, name, pattern, target_type, priority) VALUES "
"('legal_reference', '法律引用-法规名称', r'《[^》]+(?:标准|规范|导则|办法|条例|规定|细则|大纲|技术要求)', 'legal_reference', 21) ON CONFLICT DO NOTHING",
"INSERT INTO domain_factory_rules (rule_type, name, pattern, target_type, priority) VALUES "
"('slot_pattern', '参数型-slot名称', r'(?:面积|距离|长度|宽度|深度|高度|厚度|坡度|浓度|排放量|产能|产量|储量|水量|流量|人口|户数|投资|温度|湿度|风速|降水量|水位|标高|占地|规模|容量|负荷|效率|利用率|达标率|合格率|回收率|去除率|处理率)', 'parameter', 30) ON CONFLICT DO NOTHING",
```

Note: These are the initial seed rules extracted from the current hardcoded patterns. More rules will be added iteratively based on evaluation results.

- [ ] **Step 2: 在 domain_factory_service.py 中添加从数据库加载规则的方法**

Add to `DomainFactoryService`:

```python
async def load_classify_rules(self, domain_code: str | None = None) -> list[dict]:
    """从数据库加载启用的分类规则，按 priority 排序"""
    async with pg_manager.get_async_session_context() as session:
        query = select(DomainFactoryRule).where(DomainFactoryRule.enabled == True).order_by(DomainFactoryRule.priority)
        if domain_code:
            query = query.where(
                (DomainFactoryRule.domain_code == domain_code) | (DomainFactoryRule.domain_code.is_(None))
            )
        result = await session.execute(query)
        rules = result.scalars().all()
        return [
            {
                "id": r.id,
                "rule_type": r.rule_type,
                "name": r.name,
                "pattern": r.pattern,
                "target_type": r.target_type,
                "priority": r.priority,
            }
            for r in rules
        ]
```

- [ ] **Step 3: 添加规则 CRUD 方法**

```python
async def list_rules(self, rule_type: str | None = None) -> list[dict]:
    async with pg_manager.get_async_session_context() as session:
        query = select(DomainFactoryRule).order_by(DomainFactoryRule.priority)
        if rule_type:
            query = query.where(DomainFactoryRule.rule_type == rule_type)
        result = await session.execute(query)
        return [
            {"id": r.id, "domain_code": r.domain_code, "rule_type": r.rule_type,
             "name": r.name, "pattern": r.pattern, "target_type": r.target_type,
             "priority": r.priority, "enabled": r.enabled,
             "hit_count": r.hit_count, "miss_count": r.miss_count}
            for r in result.scalars().all()
        ]

async def update_rule(self, rule_id: int, data: dict) -> dict | None:
    async with pg_manager.get_async_session_context() as session:
        rule = await session.get(DomainFactoryRule, rule_id)
        if not rule:
            return None
        for key, value in data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        await session.commit()
        return {"id": rule.id, "name": rule.name}

async def reset_rules_to_default(self) -> int:
    """重置所有规则为默认值（删除后重新种子）"""
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(DomainFactoryRule.__table__.delete())
        await session.commit()
        return result.rowcount
```

- [ ] **Step 4: 验证语法并提交**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
git add -A && git commit -m "feat: 迁移硬编码规则到数据库，添加规则 CRUD 方法"
```

---

### Task 5: 添加规则管理 API 路由

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`

- [ ] **Step 1: 添加规则 CRUD 路由**

```python
@domain_factory.get("/rules")
async def list_rules(
    rule_type: str | None = Query(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    service = get_domain_factory_service()
    rules = await service.list_rules(rule_type)
    return {"items": rules}


@domain_factory.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    data: dict[str, Any],
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    service = get_domain_factory_service()
    result = await service.update_rule(rule_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="规则不存在")
    return result


@domain_factory.post("/rules/reset")
async def reset_rules(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    service = get_domain_factory_service()
    count = await service.reset_rules_to_default()
    return {"deleted": count, "message": "规则已重置为默认值"}


@domain_factory.post("/rules/test")
async def test_rule(
    data: dict[str, Any],
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """测试规则：输入文本 + pattern，返回是否命中"""
    import re
    text = data.get("text", "")
    pattern = data.get("pattern", "")
    try:
        matched = bool(re.search(pattern, text))
        return {"matched": matched, "pattern": pattern}
    except re.error as e:
        return {"matched": False, "error": str(e)}
```

- [ ] **Step 2: 添加前端 API 方法**

Modify `web/src/apis/domain_factory_api.js`:

```javascript
  // Rules management
  getRules: (params = {}) =>
    withDemoFallback(
      () => apiAdminGet(buildUrl('/api/domain-factory/rules', params)),
      () => ({ items: [] })
    ),

  updateRule: (ruleId, data) =>
    withDemoFallback(
      () => apiAdminPut(`/api/domain-factory/rules/${ruleId}`, data),
      () => ({})
    ),

  resetRules: () =>
    withDemoFallback(
      () => apiAdminPost('/api/domain-factory/rules/reset', {}),
      () => ({})
    ),

  testRule: (data) =>
    withDemoFallback(
      () => apiAdminPost('/api/domain-factory/rules/test', data),
      () => ({ matched: false })
    ),
```

- [ ] **Step 3: 验证并提交**

```bash
python -c "import ast; ast.parse(open('backend/server/routers/domain_factory_router.py', encoding='utf-8').read()); print('OK')"
git add -A && git commit -m "feat: 规则管理 CRUD API + 前端 API 方法"
```

---

### Task 6: 实现三阶段分类器

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 重写 _classify_paragraphs 为三阶段分类**

Replace the existing `_classify_paragraphs` method with a three-stage classifier that:

1. **Stage 1 (Rules)**: Load rules from DB, match each paragraph by priority. Mark with `classified_by: "rule:{rule_id}"`.
2. **Stage 2 (Heuristics)**: For paragraphs not matched by rules, apply lightweight heuristics (is_title → heading, HTML table → table, etc.). Mark with `classified_by: "heuristic"`.
3. **Stage 3 (Fallback)**: Anything remaining gets `classify_type: "narrative"`, `classified_by: "fallback"`, and `classification_reason: "无规则命中"`.

Key constraints:
- Every paragraph MUST get a classify_type. No empty values allowed.
- Each result includes `classified_by` and `classification_reason` fields.
- The method must not throw — wrap each stage in try/except with logging.

- [ ] **Step 2: 在段落模板中添加分类溯源字段**

Ensure `_classify_paragraphs` sets these fields on each paragraph:

```python
para["classified_by"] = "rule:5"  # or "heuristic" or "fallback"
para["classification_reason"] = "命中规则: 参数型-slot名称"
```

- [ ] **Step 3: 更新规则命中统计**

After classification, update `hit_count` / `miss_count` for each rule that was loaded.

- [ ] **Step 4: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 5: 重启服务，上传文档测试**

```bash
docker restart api-dev
```

Upload a document and verify:
```bash
docker exec postgres psql -U postgres -d yuxi_know -c "
SELECT p->>'classify_type' as type, p->>'classified_by' as source, count(*)
FROM domain_factory_tasks, json_array_elements(source_paragraphs::json) AS p
WHERE id = (SELECT id FROM domain_factory_tasks ORDER BY created_at DESC LIMIT 1)
GROUP BY 1, 2 ORDER BY count DESC;"
```

Expected: Zero empty classify_type. All paragraphs have a source (rule/heuristic/fallback).

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: 三阶段分类器 — 规则匹配 → 启发式 → 回退，确保零空分类"
```

---

## Phase 2: Pipeline 配置管理页（P1）

### Task 7: 创建 PipelineConfigView.vue

**Files:**
- Create: `web/src/views/PipelineConfigView.vue`
- Modify: `web/src/router/index.js`

- [ ] **Step 1: 创建 Pipeline 配置页面框架**

Create `web/src/views/PipelineConfigView.vue` with:
- Header with back button, title "Pipeline 配置", save/refresh buttons
- `a-tabs` with 4 panes: LLM Prompt 模板 / 分类规则表 / 泛化模板库 / 分类评估
- The LLM Prompt 模板 pane migrates the existing content from `PromptConfigView.vue`

- [ ] **Step 2: 实现分类规则表 pane**

- Fetch rules via `domainFactoryApi.getRules()`
- Display in `a-table` with columns: name, rule_type, pattern, target_type, priority, enabled (switch), hit_count/miss_count
- Row click opens edit modal
- "新增规则" button
- "重置为默认" button with confirm dialog
- "测试规则" input: text input + pattern, show match result

- [ ] **Step 3: 实现泛化模板库 pane**

- Fetch learned templates from existing API
- Display in table grouped by domain_code
- Click to expand template details (generalized text, slots, sample_original)
- Delete button per template

- [ ] **Step 4: 实现分类评估统计 pane**

- Fetch recent tasks' classification stats
- Display classification distribution as a simple bar chart or tag summary
- Show per-rule hit rates

- [ ] **Step 5: 更新路由**

Replace the existing `/domain-factory/prompt-config` route:
```javascript
{
  path: 'pipeline-config',
  name: 'DomainFactoryPipelineConfig',
  component: () => import('../views/PipelineConfigView.vue'),
}
```

- [ ] **Step 6: 更新 Hero 区入口**

In `DomainFactoryView.vue`, change the "Prompt 模板管理" button to "Pipeline 配置" and update the route to `/domain-factory/pipeline-config`.

- [ ] **Step 7: 验证并提交**

```bash
cd web && pnpm run lint
git add -A && git commit -m "feat: Pipeline 配置管理页 — 合并 Prompt + 规则 + 模板库 + 评估统计"
```

---

## Phase 3: Tab 1 交互改造（P2）

### Task 8: 表格详情折叠布局 + 可编辑

**Files:**
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 将表格详情改为 a-collapse**

Replace the current flat layout for table type with:

```html
<a-collapse :bordered="false" size="small" class="table-detail-collapse">
  <a-collapse-panel key="raw" header="原始表格">
    <a-textarea v-model:value="tableEditContent" :rows="6" />
  </a-collapse-panel>
  <a-collapse-panel key="schema" header="表格 Schema">
    <!-- Schema columns editing -->
  </a-collapse-panel>
  <a-collapse-panel key="rows" header="结构行数据">
    <a-table :data-source="..." :columns="..." size="small" bordered />
  </a-collapse-panel>
</a-collapse>
```

- [ ] **Step 2: 添加表格编辑状态**

Add reactive refs:
- `tableEditContent` — for raw HTML editing
- Schema column editing: inline editing in the column list (a-input for name, a-select for role)
- Row cell editing: click cell to edit

- [ ] **Step 3: 编辑后回写到 selectedParagraph**

On blur/change, update `selectedParagraph.template.table_schema` and `selectedParagraph.content`.

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: 表格详情折叠布局 + 可编辑"
```

---

### Task 9: JSON 编辑模式增强

**Files:**
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: JSON 模式改为可编辑 textarea**

Replace the readonly `<pre>` with `<a-textarea>`. Add state:

```javascript
const jsonEditDraft = ref('')
const jsonEditError = ref('')

// When switching to JSON mode, initialize draft
watch(detailJsonMode, (v) => {
  if (v && selectedParagraph.value) {
    jsonEditDraft.value = JSON.stringify(selectedParagraph.value, null, 2)
    jsonEditError.value = ''
  }
})
```

- [ ] **Step 2: 添加"应用修改"和"重置"按钮**

```html
<div v-if="detailJsonMode" class="detail-section">
  <a-textarea v-model:value="jsonEditDraft" :rows="20" class="json-editor" />
  <div v-if="jsonEditError" class="json-error">{{ jsonEditError }}</div>
  <div class="json-actions">
    <a-button size="small" type="primary" @click="applyJsonEdit">应用修改</a-button>
    <a-button size="small" @click="resetJsonEdit">重置</a-button>
  </div>
</div>
```

- [ ] **Step 3: 实现 applyJsonEdit 和 resetJsonEdit**

```javascript
const applyJsonEdit = () => {
  try {
    const parsed = JSON.parse(jsonEditDraft.value)
    // Update selectedParagraph fields from parsed JSON
    Object.assign(selectedParagraph.value, parsed)
    jsonEditError.value = ''
    message.success('已应用修改')
  } catch (e) {
    jsonEditError.value = `JSON 格式错误: ${e.message}`
  }
}

const resetJsonEdit = () => {
  jsonEditDraft.value = JSON.stringify(selectedParagraph.value, null, 2)
  jsonEditError.value = ''
}
```

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: JSON 编辑模式 — 可编辑 textarea + 应用/重置"
```

---

### Task 10: 按钮精简 + 批量操作

**Files:**
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 删除"确认高置信度"按钮**

Remove the `confirmHighConfidence` function and its button from the template.

- [ ] **Step 2: 删除独立的"保存修改"按钮**

Save happens automatically when leaving a paragraph (via watch on selectedParagraph).

- [ ] **Step 3: 添加 Shift+点击多选**

```javascript
const lastClickedIndex = ref(-1)

const handleParagraphClick = (para, index, event) => {
  if (event.shiftKey && lastClickedIndex.value >= 0) {
    const start = Math.min(lastClickedIndex.value, index)
    const end = Math.max(lastClickedIndex.value, index)
    for (let i = start; i <= end; i++) {
      const p = filteredParagraphs.value[i]
      if (p) reviewedParagraphIds.value.add(p.id)
    }
  } else {
    selectedParagraph.value = para
  }
  lastClickedIndex.value = index
}
```

- [ ] **Step 4: 底部状态栏调整**

Replace AI 置信度 with 审核进度: `段落 X/Y 已审核`.

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: Tab 1 按钮精简 + Shift 批量审核 + 状态栏调整"
```

---

## Phase 4: 前端组件拆分（P3）

### Task 11: 抽出 detail-panels

**Files:**
- Create: `web/src/components/domain-factory/etl/detail-panels/` (7 files)
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 抽出 HeadingDetail.vue**

Extract the `v-else-if="selectedParagraph.classify_type === 'heading'"` block into `HeadingDetail.vue`. Props: `paragraph`. No emits (read-only for now).

- [ ] **Step 2: 抽出 TableDetail.vue**

Extract the table detail block into `TableDetail.vue`. Props: `paragraph`, `structuredBlocks`. Includes the collapse layout from Task 8.

- [ ] **Step 3: 抽出剩余 5 个 detail panels**

LegalRefDetail, FormulaDetail, FigureDetail, ParameterDetail, NarrativeDetail — each is a simple extract of the corresponding `v-else-if` block.

- [ ] **Step 4: 更新 EtlWorkbench.vue 引用**

Replace inline template blocks with:
```html
<HeadingDetail v-else-if="selectedParagraph.classify_type === 'heading'" :paragraph="selectedParagraph" />
<TableDetail v-else-if="selectedParagraph.classify_type === 'table'" :paragraph="selectedParagraph" :structured-blocks="structuredBlocks" />
<!-- ... etc -->
```

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "refactor: 抽出 7 个 detail-panel 组件"
```

---

### Task 12: 抽出 ChapterNav 和 ParagraphList

**Files:**
- Create: `web/src/components/domain-factory/etl/ChapterNav.vue`
- Create: `web/src/components/domain-factory/etl/ParagraphList.vue`
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 抽出 ChapterNav.vue**

Extract the chapter tree navigation (toggle button + a-tree). Props: `chapterTree`, `collapsed`, `filterKey`. Emits: `update:collapsed`, `update:filterKey`.

- [ ] **Step 2: 抽出 ParagraphList.vue**

Extract the paragraph list with classify type filter, tags, confidence, review badges. Props: `paragraphs`, `filterClassify`, `reviewedIds`. Emits: `select` (paragraph + index + event), `batch-review`.

- [ ] **Step 3: 更新 EtlWorkbench.vue**

Replace inline template with the new components.

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "refactor: 抽出 ChapterNav + ParagraphList 组件"
```

---

### Task 13: 拆分 Tab 组件

**Files:**
- Create: `web/src/components/domain-factory/etl/StructuredMetaTab.vue`
- Create: `web/src/components/domain-factory/etl/SlotVerifyTab.vue`
- Create: `web/src/components/domain-factory/etl/EntityConfirmTab.vue`
- Create: `web/src/components/domain-factory/etl/CommitTab.vue`
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 抽出 StructuredMetaTab.vue**

Contains the three-column layout for Tab 1. Uses ChapterNav, ParagraphList, and detail-panels. Receives task data via provide/inject or props.

- [ ] **Step 2: 抽出 SlotVerifyTab.vue**

Contains the three-column layout for Tab 2. Local state for slot editing.

- [ ] **Step 3: 抽出 EntityConfirmTab.vue**

Contains entity proposal table + edit modal. Mostly self-contained.

- [ ] **Step 4: 抽出 CommitTab.vue**

Contains stats summary, variable table, knowledge base selector, commit button.

- [ ] **Step 5: EtlWorkbench.vue 变为薄壳**

```html
<template>
  <div class="etl-workbench">
    <!-- 流程步骤条 -->
    <div class="flow-steps">...</div>
    <!-- Tab 内容 -->
    <StructuredMetaTab v-show="activeTab === 'parse'" :task="task" ... />
    <SlotVerifyTab v-show="activeTab === 'generalize'" :task="task" ... />
    <EntityConfirmTab v-show="activeTab === 'entities'" :task="task" ... />
    <CommitTab v-show="activeTab === 'commit'" :task="task" ... />
    <!-- 底部导航 -->
    <div class="flow-nav">...</div>
  </div>
</template>
```

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "refactor: EtlWorkbench 拆分为 4 个 Tab 子组件 + 薄壳"
```

---

## 自查清单

| Spec 要求 | 对应 Task |
|-----------|----------|
| §1 Pipeline 配置页合并 | Task 7 |
| §1 分类规则表 CRUD | Task 4, 5 |
| §1 泛化模板库管理 | Task 7 |
| §1 分类评估统计 | Task 7 |
| §2 按钮精简 | Task 10 |
| §2 JSON 编辑模式 | Task 9 |
| §2 表格折叠布局 | Task 8 |
| §2 批量操作 | Task 10 |
| §3 三阶段分类器 | Task 6 |
| §3 零空分类保证 | Task 6 |
| §3 分类溯源字段 | Task 6 |
| §4 组件拆分 | Task 11, 12, 13 |
| §5 导航整合 | Task 7 |
| §5 底部状态栏调整 | Task 10 |
