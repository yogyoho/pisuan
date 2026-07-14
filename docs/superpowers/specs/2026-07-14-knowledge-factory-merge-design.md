# 知识工厂数据加工完善与升级设计文档

> 日期: 2026-07-14 | 状态: 待评审
> 前置: [知识图谱治理设计](./2026-07-13-knowledge-graph-governance-design.md)

## 1. 背景与动机

### 1.1 AI 测试暴露的结构性断裂

AI 编写第5章时:
- `get_chapter_outline("环境影响识别与评价指标体系")` ✅ 返回大纲
- `get_templates("环境影响识别与评价指标体系")` ❌ 返回空（模板在ETL子章节上）
- `child_chapters` ❌ 返回空（标准章节无 HAS_CHILD 关系）

根因: 标准13章（seed 的 level=1）和 ETL 子章节（level=2-3）在同一图谱但无关联。模板/插槽/法规全在子章节上，标准章节是空壳。

### 1.2 多报告合并缺失

- 仅加工1份报告（伊宁矿区），数据源单一
- 同一章节来自不同报告会重复，无去重
- 代码已承认: `domain_factory_repository.py:374` "聚合合并在后续版本"

### 1.3 分章节上传不支持

- 环评报告700+页，需分章上传
- 当前每次上传=独立 Document，无法归并到一份逻辑报告

## 2. 核心架构: 标准13章作为合并锚点

```
                 ┌─────────────────────────────────────┐
                 │  标准13章 (coal/eia_report)          │
                 │  = 合并锚点 (level=1, 已seed)        │
                 └──────────┬──────────────────────────┘
                            │ HAS_CHILD
       ┌────────────────────┼────────────────────────┐
       ▼                    ▼                         ▼
┌──────────────┐    ┌──────────────┐        ┌──────────────┐
│ 报告A         │    │ 报告B         │        │ 报告C         │
│ 横城矿区      │    │ 伊宁矿区      │        │ 分章上传      │
│              │    │              │        │              │
│ 5.1 影响识别  │    │ 5.1 因子识别  │        │ 5.1 识别方法  │
│ 5.2 因子筛选  │    │ 5.2 评价因子  │        │ 5.2 因子筛选  │
│ 模板/插槽/法规│    │ 模板/插槽/法规│        │ 模板/插槽/法规│
└──────┬───────┘    └──────┬───────┘        └──────┬───────┘
       │                   │                       │
       └───────────────────┼───────────────────────┘
                           ▼
                ┌─────────────────────────┐
                │  合并后的第5章知识        │
                │  templates = 去重后的并集 │
                │  key_points = 并集去重    │
                │  regulations = 并集去重   │
                │  source_count = 3        │
                └─────────────────────────┘
```

标准13章是固定的合并锚点。每份报告的 ETL 子章节都挂到对应标准章节下。多份报告的模板/大纲自动聚合。

## 3. 两层合并设计

### 3.1 层1: 分章节上传 → 合并到一份报告

**场景**: 700页报告太大，用户分3次上传第3/5/6章。

**数据模型**:
- `domain_factory_tasks` 新增 `source_report_id`（逻辑报告ID）和 `chapter_label`（章节标签如"3"/"5"）
- 同一 source_report_id 的多个 task 属于同一份报告

**流程**:
```
用户创建"横城矿区环评报告" → source_report_id = sr_001
上传"第3章.docx" → task.source_report_id = sr_001, chapter_label = "3"
上传"第5章.docx" → task.source_report_id = sr_001, chapter_label = "5"
上传"第6章.docx" → task.source_report_id = sr_001, chapter_label = "6"

每章独立 ETL → 入图谱时:
  Document.source_report_id = sr_001
  ChapterTemplate 按章节编号(chapter_label)挂到标准第N章
```

**图谱**:
```
(:SourceReport {id: 'sr_001', title: '横城矿区环评报告'})
  ←CONTRIBUTES_TO← (:Document {source_report_id: 'sr_001'})
  ←HAS_CHAPTER→ (:ChapterTemplate {chapter_label: '5', ...})
  ←HAS_CHILD→ (标准第5章)
```

### 3.2 层2: 多份报告 → 合并到一个领域模板

**场景**: 报告A(横城) + 报告B(伊宁) → coal/eia_report 领域知识。

**合并逻辑**（commit pipeline Stage 2.9 之后新增 Stage 2.10）:

```
对同一 canonical_chapter_key 下的多个 ChapterTemplate（来自不同报告）:

1. ParagraphTemplate 去重:
   - 按 text_pattern hash 去重
   - 保留1条, source_count += 被合并数
   - frequency = source_count / 总报告数

2. key_points 并集:
   - 收集所有子章节的 key_points
   - 去重后写入标准章节节点

3. regulations 并集:
   - 收集所有子章节的 regulations
   - 去重后写入标准章节节点

4. writing_example:
   - 取所有报告中最长的 sample_original
```

## 4. P0: 标准↔ETL 关联 + get_templates 递归

### 4.1 HAS_CHILD 关联脚本

**文件**: `scripts/governance/link_standard_chapters.py`

按章节编号前缀匹配 ETL 子章节到标准章节:

```python
# ETL 子章节 "5.1 环境影响因子识别" → 标准第5章
# 匹配规则: 章节编号首数字 = 标准章节 order
```

**Cypher**:
```cypher
// 对每个 ETL 子章节(level > 1), 按编号首数字找到标准章节, 建 HAS_CHILD
MATCH (sub:ChapterTemplate)
WHERE sub.level > 1 AND sub.canonical_chapter_key IS NOT NULL
  AND sub.title =~ '^[0-9]+\\.'
WITH sub, split(sub.title, '.')[0] AS chapter_num
MATCH (std:ChapterTemplate)
WHERE std.level = 1 AND std.`order` = toInteger(chapter_num)
  AND std.id STARTS WITH 'CH_coal_eia_report_std_'
MERGE (std)-[:HAS_CHILD]->(sub)
```

注意: 需处理 ETL title 含双编号的情况（"1.1.1 3.1.1 地形地貌"），用清洗后的编号匹配。

### 4.2 get_templates 递归查询

**文件**: `backend/package/yuxi/services/graph_query_service.py`

当顶级章节查不到模板时，递归查子章节:

```python
async def get_templates(self, domain, report_type, canonical_key):
    # 1. 先查本章节模板
    templates = self._query_templates(canonical_key)
    if templates:
        return templates
    # 2. 递归查子章节模板
    child_keys = self._query_child_keys(domain, report_type, canonical_key)
    all_templates = []
    for child_key in child_keys:
        all_templates.extend(self._query_templates(child_key))
    return all_templates
```

**Cypher（递归）**:
```cypher
MATCH (ch:ChapterTemplate {canonical_chapter_key: $key})
OPTIONAL MATCH (ch)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
OPTIONAL MATCH (sub)-[:HAS_SLOT]->(s:Slot)
OPTIONAL MATCH (pt:ParagraphTemplate {canonical_chapter_key: sub.canonical_chapter_key})
OPTIONAL MATCH (pt)-[:CITES]->(lr:LegalReference)
RETURN pt, collect(DISTINCT s), collect(DISTINCT lr)
```

### 4.3 get_chapter_outline child_chapters 增强

HAS_CHILD 关系建好后，`get_chapter_outline` 的 `child_chapters` 自然有值。无需改代码，只需确保 Cypher 的 OPTIONAL MATCH HAS_CHILD 生效（已有）。

## 5. P0: 分章节上传支持

### 5.1 数据模型扩展

`domain_factory_tasks` 新增字段:
- `source_report_id VARCHAR(64)` — 逻辑报告ID（同报告的多个章节task共享）
- `chapter_label VARCHAR(64)` — 章节标签（如"3"/"5"/"6"）

```sql
ALTER TABLE domain_factory_tasks ADD COLUMN IF NOT EXISTS source_report_id VARCHAR(64);
ALTER TABLE domain_factory_tasks ADD COLUMN IF NOT EXISTS chapter_label VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_df_tasks_source_report ON domain_factory_tasks(source_report_id);
```

### 5.2 上传接口扩展

上传时可选传 `source_report_id` 和 `chapter_label`:
- 首次上传: 后端自动生成 source_report_id，返回给用户
- 后续上传: 用户传入同一个 source_report_id + 新 chapter_label

### 5.3 ETL 入图谱时关联

`graph_builder._build_skeleton_aggregation` 中，ChapterTemplate 创建时:
- 如果 task 有 chapter_label，按 chapter_label 首数字挂到标准章节
- Document 节点标记 source_report_id

## 6. P1: 多报告模板去重合并

### 6.1 commit pipeline Stage 2.10（新增）

在 Stage 2.9（outline 产出）之后，新增 Stage 2.10（知识合并）:

```python
# Stage 2.10: 多报告知识合并
await self._merge_cross_report_knowledge(task_detail)
```

### 6.2 合并逻辑

```python
async def _merge_cross_report_knowledge(self, task_detail):
    """合并当前报告的知识到标准13章（去重+聚合）。"""
    domain = normalize_domain(task_detail["domain"])
    report_type = normalize_report_type(task_detail["report_type_code"])

    for order in range(1, 14):
        std_chapter_id = f"CH_{domain}_{report_type}_std_{order}"

        # 1. 收集该标准章节下所有子章节的 ParagraphTemplate
        # 2. 按 text_pattern hash 去重
        # 3. 合并 key_points / regulations 到标准章节
        # 4. 更新 source_count / frequency
```

### 6.3 去重策略

| 数据类型 | 去重键 | 合并策略 |
|---------|--------|---------|
| ParagraphTemplate | text_pattern hash | 保留1条，source_count++ |
| key_points | 文本完全匹配 | 并集去重 |
| regulations | 标准编号(GB/HJ) | 并集去重 |
| writing_example | — | 取最长 |
| Slot | slot.name | 保留，entity_ref 取非空值 |

## 7. P1: slot_validation 接入 ETL

### 7.1 接入点

commit pipeline Stage 2.5（图谱构建）之前，插入 slot 校验:

```python
# Stage 2.4b: slot 事后校验（新增）
from yuxi.services.slot_validation_service import SlotValidationService
svc = SlotValidationService()
report = await svc.validate_slots(paragraph_slots, entity_schemas)
if report["conflicts"]:
    logger.warning(f"slot 校验发现冲突: {report['conflicts']}")
    # 不阻塞，但记录到 task.error_message
```

### 7.2 entity_ref LLM 归类

替代当前 `entity_meta_service.py` 的子串匹配:
- slot_validation_service 已有 LLM 归类能力（validate_slots 内部）
- 校验时顺带修正 entity_ref
- 写回图谱

## 8. 实施路线图

| Phase | 内容 | 优先级 | 依赖 |
|-------|------|--------|------|
| Phase 1 | HAS_CHILD 关联脚本 + get_templates 递归 | P0 | 无 |
| Phase 2 | 分章节上传（source_report_id + chapter_label） | P0 | Phase 1 |
| Phase 3 | 多报告去重合并（Stage 2.10） | P1 | Phase 1 |
| Phase 4 | slot_validation 接入 ETL | P1 | 无 |
| Phase 5 | ETL 源头映射标准结构 | P2 | Phase 1-3 |

## 9. 不变量

1. 标准13章是唯一的合并锚点（level=1, id 含 std_ 前缀）
2. 所有 ETL 子章节必须挂到对应标准章节（HAS_CHILD）
3. get_templates 顶级章节查不到时递归查子章节
4. ParagraphTemplate 按 text_pattern hash 全局去重
5. 多报告合并不删除数据，只去重和聚合
6. source_count 准确反映贡献的报告数
