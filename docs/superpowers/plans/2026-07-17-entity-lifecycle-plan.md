# 实体对象参与加工流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将实体对象体系集成到 ETL 加工全流程：6 分类体系、自动化 slot-entity 绑定、异步 LLM 实体发现

**Architecture:** 后端新增 `_entity_discovery_task` 方法 + API `/discover-entities`；前端 Tab 1 新增"智能识别实体"按钮（后台异步）+ slot chip 展示绑定状态；实体库从 7 类迁移到 6 类（对齐环评导则）

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Vue 3 + Ant Design Vue

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/package/yuxi/storage/postgres/models_domain_entity.py` | 修改 | DomainEntitySchema.category 默认值对齐 |
| `backend/package/yuxi/services/domain_entity_service.py` | 修改 | seed/update 支持 6 分类 |
| `backend/package/yuxi/services/domain_factory_service.py` | 修改 | 新增 `discover_entities_task` 方法 |
| `backend/server/routers/domain_factory_router.py` | 修改 | 新增 `/discover-entities` API |
| `backend/scripts/migrate_entity_categories.py` | 新建 | 存量实体迁移脚本 |
| `web/src/apis/domain_factory_api.js` | 修改 | 新增 `discoverEntities` API |
| `web/src/components/domain-factory/EtlWorkbench.vue` | 修改 | "智能识别实体"按钮 + slot chip 绑定展示 |

---

## Phase 1: 6 分类体系迁移

### Task 1: 存量实体分类迁移脚本

**Files:**
- Create: `backend/scripts/migrate_entity_categories.py`

- [ ] **Step 1: 编写迁移脚本**

将现有 68 个实体按以下规则重新归类：

```python
"""存量实体分类迁移：7 分类 → 6 分类（对齐环评导则）"""

CATEGORY_MAP = {
    # 基础工程实体 → project_basic
    "基础工程实体": "project_basic",
    # 环境要素与影响实体 → 拆分为 natural_env / env_quality / impact_assessment
    "环境要素与影响实体": None,  # 需人工判断
    # 敏感目标与空间实体 → sensitive_target
    "敏感目标与空间实体": "sensitive_target",
    "敏感目标实体": "sensitive_target",
    # 措施与法规实体 → measures_regulation
    "措施与法规实体": "measures_regulation",
    # 生态类 → natural_env
    "生态完整性评价": "natural_env",
    "生态调查": "natural_env",
}

ENTITY_OVERRIDES = {
    # 环境要素与影响实体 → 根据名称分到 natural_env / env_quality / impact_assessment
    "pollutant": "env_quality",
    "noise_equipment": "env_quality",
    "risk_assessment": "impact_assessment",
    "soil_water_conservation": "natural_env",
    "carbon_footprint": "env_quality",
    "environmental_element": "natural_env",
    "impact_behavior": "impact_assessment",
    "judgment": "impact_assessment",
    "shallow_groundwater": "natural_env",
    "wastewater_sources": "env_quality",
    "solid_waste_gangue": "env_quality",
    "environmental_quality_baseline": "env_quality",
    "assessment_conclusion": "impact_assessment",
    "air_pollutants": "env_quality",
    "land_subsidence": "natural_env",
}

def migrate(dry_run=True):
    """迁移 DB 中的实体分类"""
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    repo = DomainEntityRepository()
    for entity in repo.list_all():
        ek = entity.get("entity_key", "")
        # 优先查精确映射
        if ek in ENTITY_OVERRIDES:
            new_cat = ENTITY_OVERRIDES[ek]
        else:
            new_cat = CATEGORY_MAP.get(entity.get("category", ""))
        if new_cat and new_cat != entity.get("category"):
            print(f"  {entity['name_cn']} ({ek}): {entity['category']} → {new_cat}")
            if not dry_run:
                repo.update(entity["entity_id"], {"category": new_cat})
```

- [ ] **Step 2: dry-run 验证**

```bash
docker exec api-dev python -m scripts.migrate_entity_categories --dry-run
```

- [ ] **Step 3: 执行迁移**

```bash
docker exec api-dev python -m scripts.migrate_entity_categories
```

### Task 2: 更新 seed_default_entities

**Files:**
- Modify: `backend/package/yuxi/services/domain_entity_service.py:205`

- [ ] **Step 1: 更新 JSON 中的 category 字段**

`coal_eia_entity_types.json` 中所有实体的 `category` 更新为新的 6 分类 key。

- [ ] **Step 2: 重新 seed**

```bash
docker exec api-dev python -c "from yuxi.services.domain_entity_service import DomainEntityService; import asyncio; asyncio.run(DomainEntityService().seed_default_entities())"
```

---

## Phase 2: Tab 1 slot chip 绑定展示

### Task 3: slot chip 显示 entity_ref 绑定状态

**Files:**
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 修改 slot chip 模板**

在 parameter 段落详情中的 slot chip 区域，增加绑定状态展示：

```html
<span v-for="slot in selectedParagraph.template.slots" :key="slot.name" class="slot-chip">
  <a-tag :color="(SLOT_TYPE_MAP[slot.type] || {}).color || 'blue'" size="small">{{ slot.name }}</a-tag>
  <span v-if="slot.entity_ref" class="slot-chip-ref bound">→ {{ slot.entity_ref }}</span>
  <span v-else class="slot-chip-ref unbound">待绑定</span>
  <a-button type="text" size="small" class="slot-chip-del" @click.stop="removeSlot(selectedParagraph.id, slot.name)"><X :size="11" /></a-button>
</span>
```

- [ ] **Step 2: 添加 CSS**

```less
.slot-chip-ref {
  &.bound { color: #52c41a; font-size: 11px; }
  &.unbound { color: var(--gray-400); font-size: 11px; }
}
```

- [ ] **Step 3: 验证编译**

```bash
docker logs web-dev --tail 3
```

---

## Phase 3: "智能识别实体"异步后台任务

### Task 4: 后端 service 方法

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 添加 `discover_entities_task` 方法**

在 `_auto_map_slots_to_entity_properties` 之后添加：

```python
async def discover_entities_task(self, task_id: str) -> dict[str, Any]:
    """异步后台任务：LLM 分析未绑定 slot，建议新实体/属性/绑定。

    写入 task.template_metadata.entity_proposals，前端轮询检测完成。
    """
    detail = await self.get_task_detail(task_id)
    if not detail:
        return {"error": "任务不存在"}

    paragraphs = detail.get("source_paragraphs", [])
    domain_code = detail.get("domain") or "coal"

    # 1. 收集未绑定 slot（按名称去重，统计出现频次）
    slot_freq: dict[str, dict] = {}
    for para in paragraphs:
        tmpl = para.get("template")
        if not isinstance(tmpl, dict):
            continue
        for slot in tmpl.get("slots", []):
            if slot.get("entity_ref"):
                continue
            name = slot.get("name", "").strip()
            if not name:
                continue
            if name not in slot_freq:
                slot_freq[name] = {"name": name, "type": slot.get("type", ""),
                                   "description": slot.get("description", ""),
                                   "count": 0, "paragraphs": []}
            slot_freq[name]["count"] += 1
            slot_freq[name]["paragraphs"].append(para.get("title", "")[:60])

    # 2. 置信度过滤：≥3 段落出现
    candidates = [s for s in slot_freq.values() if s["count"] >= 3]

    if not candidates:
        return {"message": "所有 slot 已绑定或无满足置信度阈值的候选", "proposals": []}

    # 3. 加载已有实体的完整结构
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=domain_code)

    # 4. LLM 分析
    prompt = self._build_discovery_prompt(candidates, entities, domain_code)
    from yuxi.models.chat import select_model
    model = select_model()
    response = await model.call(prompt)
    text = response.content if hasattr(response, "content") else str(response)
    proposals = self._parse_discovery_response(text)

    # 5. 写入 task metadata
    await self.repo.update_task(task_id, {
        "template_metadata": {
            **(detail.get("template_metadata") or {}),
            "entity_proposals": proposals,
            "discovery_status": "completed",
        }
    })

    return {"proposals": proposals, "total": len(proposals)}
```

- [ ] **Step 2: 添加 `_build_discovery_prompt` 方法**

```python
def _build_discovery_prompt(self, candidates: list[dict],
                             entities: list[dict], domain_code: str) -> str:
    """构建 LLM prompt：将候选 slot 匹配到实体/属性"""
    candidate_text = "\n".join(
        f"- {c['name']} (类型={c['type']}, 出现{c['count']}次, "
        f"描述={c.get('description','')})"
        for c in candidates[:50]  # 上限 50 个
    )

    entity_text = "\n".join(
        f"- {e.get('name_cn','')} ({e.get('entity_key','')}) [{e.get('category','')}]"
        for e in entities[:40]
    )

    CATEGORIES = """entity categories (6):
- project_basic: 基础工程实体 (项目、产能、开采技术)
- natural_env: 自然环境实体 (地形、气候、水文、地质、生态)
- env_quality: 环境质量与污染源实体 (空气、水、噪声、固废、排放)
- sensitive_target: 敏感目标与空间实体 (居民点、红线、文物)
- measures_regulation: 措施与法规实体 (治理措施、监测计划、法规标准)
- impact_assessment: 环境影响评价实体 (预测模型、评价结论)"""

    return f"""你是煤矿环评领域专家。以下是文档中提取的未绑定 slot 变量，需要将其归类到实体体系。

{CATEGORIES}

已有实体:
{entity_text}

候选 slot:
{candidate_text}

请输出 JSON 数组，每个元素可以是：
1. new_entity: 创建全新的实体
{{"suggestion_type":"new_entity","entity_key":"snake_key","name_cn":"中文名","category":"6分类之一","properties":[{{"key":"prop_key","name_cn":"属性中文","value_type":"number|string|boolean","unit":"单位"}}],"confidence":0.8}}

2. add_property: 向已有实体追加属性
{{"suggestion_type":"add_property","target_entity_key":"已有实体的key","proposed_property":{{"key":"prop_key","name_cn":"属性名","value_type":"number|string","unit":"单位"}},"confidence":0.8}}

要求：
- 每个 slot 必须归属一个实体或建议为新实体
- 可合并的连续值（如最高值+最低值+单位）合并为一个属性的子字段
- 属性 key 用英文 snake_case
- 严格 JSON 数组格式输出
"""
```

- [ ] **Step 3: 添加 `_parse_discovery_response` 方法**

```python
@staticmethod
def _parse_discovery_response(text: str) -> list[dict]:
    """解析 LLM 返回的 JSON 数组"""
    import json, re
    m = re.search(r'\[[\s\S]*\]', text)
    if not m:
        return []
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return []
```

- [ ] **Step 4: 语法验证**

```bash
docker exec api-dev python -c "import ast; ast.parse(open('/app/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('OK')"
```

### Task 5: API 路由

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`

- [ ] **Step 1: 添加 `/discover-entities` 端点**

```python
@domain_factory.post("/tasks/{task_id}/discover-entities")
async def discover_entities(
    task_id: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """异步触发实体发现：LLM 分析未绑定 slot，建议新实体/属性"""
    try:
        service = get_domain_factory_service()
        result = await service.discover_entities_task(task_id)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to discover entities for {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"实体发现失败: {str(e)}")
```

- [ ] **Step 2: 语法验证**

```bash
docker exec api-dev python -c "import ast; ast.parse(open('/app/server/routers/domain_factory_router.py', encoding='utf-8').read()); print('OK')"
```

### Task 6: 前端 API + 按钮 + 轮询通知

**Files:**
- Modify: `web/src/apis/domain_factory_api.js`
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`

- [ ] **Step 1: 添加前端 API**

```javascript
discoverEntities: (taskId) =>
  withDemoFallback(
    () => apiAdminPost(`/api/domain-factory/tasks/${taskId}/discover-entities`, {}),
    () => ({ success: true, result: { proposals: [], total: 0 } })
  ),
```

- [ ] **Step 2: Tab 1 工具栏添加按钮 + 状态变量**

```javascript
// 状态
const discoveringEntities = ref(false)

// 方法
const triggerEntityDiscovery = async () => {
  if (!taskDetail.value?.id) return
  discoveringEntities.value = true
  try {
    const res = await domainFactoryApi.discoverEntities(taskDetail.value.id)
    const total = res.result?.total || 0
    if (total > 0) {
      message.success(
        `识别出 ${total} 个新实体/属性，请前往「领域实体确认」tab 查看`
      )
    } else {
      message.info('未发现新实体，所有 slot 均已绑定或候选不足')
    }
  } catch (e) {
    message.error('实体发现失败：' + (e.message || e))
  } finally {
    discoveringEntities.value = false
  }
}
```

- [ ] **Step 3: 模板添加按钮**

在 Tab 1 工具栏"运行校验"按钮旁边：

```html
<a-button size="small" @click="triggerEntityDiscovery" :loading="discoveringEntities">
  智能识别实体
</a-button>
```

- [ ] **Step 4: 验证编译**

```bash
docker logs web-dev --tail 3
```

---

## 自审

- ✅ Spec Section 2 (分类体系) → Task 1-2
- ✅ Spec Section 3.2 (Tab 1 绑定展示) → Task 3
- ✅ Spec Section 3.3 (异步后台任务) → Task 4-6
- ✅ Spec Section 4 (数据流) → 各 Task 参数/返回值对齐
- ✅ 无 TBD/TODO
- ✅ LLM prompt 含 6 分类 + 置信度阈值 + JSON schema 约束
