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

## 4. P0: 标准↔ETL 关联 + 子章节归一化 + get_templates 递归

### 4.0 子章节归一化（跨报告章节标题统一）

**问题**: 不同报告的同一子章节标题不同但语义等价:
```
报告A: 5.1 环境影响识别
报告B: 5.1 矿区环境影响因子识别
报告C: 5.1 污染类影响因子识别
```
不归一化则每个报告的"5.1"是独立节点，模板无法跨报告聚合。

**方案**: 从 outlines/ MD 的"写作骨架"解析标准子章节结构，seed 到图谱作为 level=2 锚点，ETL 子章节按编号映射。

**标准子章节来源**: outlines/ MD 已定义每章的标准子节结构:
```markdown
## 写作骨架
5.1 环境影响识别
  5.1.1 识别方法（矩阵法/清单法）
5.2 评价因子筛选
5.3 重点评价要素确定
```

**归一化流程**:
```
ETL 子章节 "5.1 矿区环境影响因子识别"
  ↓ 按编号 "5.1" 匹配标准子章节
  → canonical_chapter_key = "环境影响识别"（标准名）
  → original_title = "矿区环境影响因子识别"（保留原始名）
  ↓
不同报告的 "5.1 xxx" 共享同一 canonical_chapter_key → 模板自然聚合
```

**三级映射策略**:
| 级别 | 匹配方式 | 场景 | 可靠性 |
|------|---------|------|--------|
| 1. 编号匹配（默认） | "5.1" → 标准5.1 | 报告遵循导则编号 | 高 |
| 2. 标题相似度（fallback） | 编辑距离/LLM匹配标准子章节名 | 编号不同但内容相同 | 中 |
| 3. 父章节兜底 | 无法匹配 → 挂标准第5章（不设子章节key） | 结构完全不同 | 低 |

**图谱结构（三级锚点）**:
```
标准第5章 "环境影响识别与评价指标体系" (level=1, std_5)
  ├─HAS_CHILD→ 标准子节 "环境影响识别" (level=2, std_5_1)
  │    ├─HAS_CHILD→ ETL子节 "5.1 矿区环境影响因子识别" (报告B)
  │    ├─HAS_CHILD→ ETL子节 "5.1 污染类影响因子识别" (报告C)
  │    └─HAS_CHILD→ ETL子节 "5.1 环境影响识别" (报告A)
  ├─HAS_CHILD→ 标准子节 "评价因子筛选" (level=2, std_5_2)
  │    └─HAS_CHILD→ ETL子节 "5.2 评价因子筛选" (报告A/B/C)
  └─HAS_CHILD→ 标准子节 "重点评价要素确定" (level=2, std_5_3)
```

### 4.1 标准子章节 seed 脚本

**文件**: `scripts/seed_standard_subchapters.py`

从 outlines/ MD 的"写作骨架"段解析标准子章节，seed 到图谱:

```python
# 解析 outlines/ch05-影响识别.md "写作骨架" 段:
#   5.1 环境影响识别 → {parent_order:5, sub_order:1, key:"环境影响识别", level:2}
#   5.2 评价因子筛选 → {parent_order:5, sub_order:2, key:"评价因子筛选", level:2}
#   5.3 重点评价要素确定 → {parent_order:5, sub_order:3, key:"重点评价要素确定", level:2}

# Cypher:
# MERGE (sub:ChapterTemplate {id: "CH_coal_eia_report_std_5_1"})
# SET sub.canonical_chapter_key = "环境影响识别",
#     sub.level = 2, sub.`order` = 1, sub.title = "5.1 环境影响识别"
# MERGE (std)-[:HAS_CHILD]->(sub)  -- 标准第5章 → 标准子节
```

### 4.2 ETL 子章节映射到标准子章节

ETL 创建 ChapterTemplate 时，按编号匹配标准子章节:

```python
# ETL 子章节 title = "5.1 矿区环境影响因子识别"
# 1. 提取编号前缀: "5.1" → parent=5, sub=1
# 2. 查标准子章节: std_5_1 (canonical_chapter_key="环境影响识别")
# 3. 设置 ETL 节点:
#    - canonical_chapter_key = "环境影响识别"（标准名，非原始标题）
#    - original_title = "矿区环境影响因子识别"（保留原始名）
#    - HAS_CHILD → 标准子节 std_5_1（而非直接挂标准第5章）
```

### 4.3 HAS_CHILD 关联脚本（存量数据）

**文件**: `scripts/governance/link_standard_chapters.py`

对存量 ETL 子章节，按编号前缀建 HAS_CHILD 到标准子章节:

```cypher
// ETL 子章节 "5.1 矿区环境影响因子识别" → 标准子节 std_5_1
MATCH (etl:ChapterTemplate)
WHERE etl.level > 1 AND etl.title =~ '^[0-9]+\\.'
WITH etl, split(replace(etl.title, ' ', '.'), '.') AS parts
  // 提取前两级编号: "5.1.xxx" → parent=5, sub=1
WITH etl, parts[0] AS parent_num, parts[1] AS sub_num
MATCH (std_sub:ChapterTemplate)
WHERE std_sub.id = 'CH_coal_eia_report_std_' + parent_num + '_' + sub_num
MERGE (std_sub)-[:HAS_CHILD]->(etl)
// 同时归一化 canonical_chapter_key
SET etl.canonical_chapter_key = std_sub.canonical_chapter_key
```

### 4.4 get_templates 递归查询

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

**Cypher（递归查子章节模板）**:
```cypher
MATCH (ch:ChapterTemplate {canonical_chapter_key: $key})
OPTIONAL MATCH (ch)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
OPTIONAL MATCH (pt:ParagraphTemplate {canonical_chapter_key: sub.canonical_chapter_key})
OPTIONAL MATCH (pt)-[:HAS_SLOT]->(s:Slot)
OPTIONAL MATCH (pt)-[:CITES]->(lr:LegalReference)
RETURN pt, collect(DISTINCT s), collect(DISTINCT lr)
```

### 4.5 get_chapter_outline child_chapters 增强

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
| Phase 1 | 标准子章节 seed（从 outlines/ 解析 level=2 锚点） + 存量 ETL 子章节 HAS_CHILD 关联 + canonical_chapter_key 归一化 | P0 | 无 |
| Phase 2 | get_templates 递归查询（顶级查不到时查子章节） | P0 | Phase 1 |
| Phase 3 | 分章节上传（source_report_id + chapter_label） | P0 | Phase 1 |
| Phase 4 | 多报告去重合并（Stage 2.10 + hash 去重 + 大纲并集） | P1 | Phase 1 |
| Phase 5 | slot_validation 接入 ETL commit pipeline | P1 | 无 |
| Phase 6 | ETL 源头映射标准子章节结构（新数据入库即归一化） | P2 | Phase 1-4 |

## 9. 不变量

1. 标准13章是唯一的顶级合并锚点（level=1, id 含 std_ 前缀）
2. 标准子章节是子级合并锚点（level=2, id 含 std_N_M 前缀）
3. ETL 子章节按编号映射到标准子章节，canonical_chapter_key 用标准名（非原始标题）
4. 不同报告的同编号子章节共享同一 canonical_chapter_key → 模板自然聚合
5. get_templates 顶级章节查不到时递归查子章节
6. ParagraphTemplate 按 text_pattern hash 全局去重
7. 多报告合并不删除数据，只去重和聚合
8. source_count 准确反映贡献的报告数
