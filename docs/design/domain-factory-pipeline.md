# 领域知识工厂 Pipeline 设计文档

> 版本：2.0
> 日期：2026-05-16
> 状态：已实现

## 一、系统概述

领域知识工厂（Domain Knowledge Factory）是 Yuxi 平台的核心模块，负责将行业报告文档（PDF/Word/Markdown）自动解析为**五层可复用知识资产**：文档骨架、句式模板、标准条款、表格结构、逻辑关系。

核心设计思想是**"先分类再入库"的二维模板空间**：

```
维度1: domain（行业）        煤炭采掘 / 石油化工 / 矿产勘探
维度2: report_type（报告类型） 环境影响评价 / 地质勘查 / 可行性研究 ...

domain × report_type = 独立隔离的模板空间
```

同一行业下，不同报告类型的章节骨架、引用标准、段落模板完全不同，必须隔离存储。

### 1.1 五层可复用资产

| 层级 | 资产 | 图谱节点 | 复用价值 |
|------|------|---------|---------|
| L1 | 文档骨架 | DomainOutline / ChapterTemplate / ParagraphRole | 最高 — 定义报告的目录和叙述顺序 |
| L2 | 句式模板 | ParagraphTemplate / Slot | 高 — 泛化后的参数化句式 |
| L3 | 标准条款 | LegalReference | 中 — 分层筛选后可复用 |
| L4 | 表格结构 | TableSchema | 中 — 列定义+行骨架可跨项目复用 |
| L5 | 逻辑关系 | CausalChain / ConditionRule / DataFlow | 最高级 — 因果推理、条件分支、数据溯源 |

### 1.2 核心源文件

| 文件 | 职责 |
|------|------|
| `backend/package/yuxi/services/domain_factory_service.py` | ETL 流水线、段落分类、泛化、法律引用、公式/图片/表格提取、逻辑关系提取 |
| `backend/package/yuxi/services/graph_builder.py` | Neo4j 知识图谱构建、骨架聚合、节点/关系写入 |
| `backend/package/yuxi/repositories/domain_factory_repository.py` | PostgreSQL 数据访问层（任务、模板、领域、报告类型） |
| `backend/package/yuxi/storage/postgres/models_domain_factory.py` | SQLAlchemy 数据模型定义 |
| `backend/server/routers/__init__.py` | HTTP 路由注册 |
| `web/src/components/domain-factory/EtlWorkbench.vue` | 前端 ETL 审核工作台 |
| `web/src/components/domain-factory/DataSourceDashboard.vue` | 前端数据源管理（上传+领域选择） |

---

## 二、Pipeline 流程

### 2.1 总体流程

```
文档上传 → 选择 domain + report_type
  ↓
  PARSE（解析段落 + 识别章节结构）
  ↓
  CLASSIFY（段落分类）
  ├─ heading         → 骨架提取
  ├─ legal_reference → 法律引用结构化提取（场景A: 正则 / 场景B: LLM）
  ├─ formula         → 公式结构 + 变量映射
  ├─ figure          → 多模态 VLM 提取
  ├─ table           → 表格 Schema 提取（含列角色）
  ├─ list            → 列表式结构化提取
  ├─ parameter       → 泛化为句式模板（≤5 slot）
  └─ narrative       → 参考素材，直接入库
  ↓
  LEGAL_EXTRACT（法律引用结构化提取，双场景）
  ↓
  GENERALIZE（仅对 parameter 型段落调用 LLM 泛化）
  ↓
  LOGIC_EXTRACT（逻辑关系提取：因果链/条件分支/数据引用链）
  ↓
  WAITING_REVIEW（半自动审核：AI 置信度 + 人工确认）
  ↓
  COMMIT → VECTOR INGEST（LightRAG 向量入库）+ GRAPH INGEST（Neo4j 图谱入库）
```

### 2.2 流水线阶段详解

入口方法：`DomainFactoryService._etl_pipeline_async(context)`

#### 阶段 1：PARSE（解析）

- 调用 `parse_source_to_markdown(file_path)` 将文档转为 Markdown + HTML
- 调用 `_parse_markdown_to_paragraphs()` 按章节/段落切分
  - 表格以完整 HTML 块存储（不分行），与原文 Markdown 表格做行数对齐匹配
  - 标题解析出 section_path（如 `["1", "2", "3"]` 表示 1.2.3）
  - 支持中文数字编号转换（一、二 → 1、2）
- 状态流转：`UPLOADED` → `PARSING`

#### 阶段 1.5：CLASSIFY（分类，在 PARSE 内执行）

- 调用 `classify_paragraphs(paragraphs)` 对每个段落标记 `classify_type`
- 8 种类型，按优先级依次判定：

| # | classify_type | 识别条件 | 后续处理 |
|---|--------------|---------|---------|
| 1 | `heading` | `para.is_title == True` | 骨架提取 |
| 2 | `table` | `para.is_table == True` | 表格 Schema |
| 3 | `figure` | `_is_figure()` — Markdown 图片语法/占位符 | VLM 多模态 |
| 4 | `formula` | `_is_formula()` — LaTeX/数学表达式/标题关键词 | 公式结构提取 |
| 5 | `list` | `_is_list_block()` — 连续编号行 ≥60% | 结构化列表 |
| 6 | `legal_reference` | `_is_legal_reference()` — 法律引用正则 | 法律引用提取 |
| 7 | `parameter` | 含数值 + 长度 < 500 字 | LLM 泛化 |
| 8 | `narrative` | 以上均不匹配 | 直接入库 |

#### 阶段 1.6：LEGAL_EXTRACT（法律引用提取）

双场景提取：

- **场景A**（编制依据列表）：`extract_legal_references()` 用正则从 `legal_reference` 段落批量提取
  - 匹配模式：`（N）《名称》{，文号}{，日期}`
  - 产出：124 条/典型文档，含 9 层分类 + scope + effective_date
- **场景B**（正文标准引用）：`extract_legal_references_from_text()` 用 LLM 从含标准编号的正文段落语义提取
  - 产出：标准编号、名称、引用类型（applicability/compliance/classification）、绑定实体

#### 阶段 1.7：公式 / 图片 / 表格提取

- **公式**：`_extract_formulas()` → `extract_formula()` 对 `formula` 类型段落提取
  - SYMBOL_MAP（14 个物理量符号）映射变量名+单位
  - `_infer_formula_purpose()` 根据标题/章节路径推断公式用途
  - `_symbol_to_entity_ref()` 映射到实体引用 key
- **图片**：`_extract_figures()` → `extract_figure_with_vlm()` 对 `figure` 类型段落调用多模态 LLM
  - 识别图片类型（流程图/位置图/数据图表/照片）
  - 流程图提取步骤序列（ProcessFlow → ProcessStep）
- **表格**：`_extract_table_schemas()` 对 `table` 类型段落提取列定义模板
  - 支持 HTML 表格和 Markdown 表格
  - 列角色判定：key / structural / classification / data / reference / derived
  - 表格类型识别：key_value / monitoring / compliance / standard_limit
  - 自动提取 structural_rows（非 data/derived 列的行数据）

#### 阶段 2：GENERALIZE（泛化）

- 状态流转：`PARSING` → `GENERALIZING`
- **只对 `classify_type == "parameter"` 的段落调用 LLM**，其他类型跳过
- 调用 `generalize_paragraphs()` → `_generalize_text()` 进行段落级泛化
- 每段落产出：
  - `generalized`：泛化后模板文本（含 `{{slot_name}}` 和 `[叙述标记]`）
  - `slots`：slot 数组（≤5 个/段落），每个含 name/type/entity_ref/value/unit/vocabulary
  - `metadata`：章节标签等元信息
  - `quality_score`：模板质量评分（0~1）
- Slot 类型兜底：`_valid_types = {"parameter", "enum", "descriptive", "reference"}`，无效 type 自动回退为 `parameter`
- 数据去重：所有数据统一写入 `para.template`，不再在根级重复存储

#### 阶段 2.5：LOGIC_EXTRACT（逻辑关系提取）

- 调用 `extract_logical_relationships(paragraphs)` 用 LLM 按章节粒度分析
- 三种逻辑关系：
  - `causal_chains`：因果链（前提 → 推理 → 结论）
  - `conditions`：条件分支（IF ... THEN ...）
  - `data_refs`：数据引用链（段落引用表格/前文数据）
- 产出存储在 `task.logical_relations` 中，图谱入库时写入 CausalChain / ConditionRule / DataFlow 节点

#### 阶段 3：WAITING_REVIEW（审核）

- 状态流转：`GENERALIZING` → `WAITING_REVIEW`
- 计算 AI 置信度 `ai_confidence`（基于泛化成功率）
- 收集未识别 slot（`_collect_unrecognized_slots`）
- 前端 ETL 工作台展示分类标签 + 结构化元数据 + 置信度

#### 阶段 4：COMMIT（提交入库）

- 入口：`commit_task()` → `_commit_pipeline_async()`
- 执行两个入库流程：
  1. **向量入库**：构建结构化 Markdown → LightRAG 知识库入库
  2. **图谱入库**：调用 `GraphBuilder.build_knowledge_graph()` 写入 Neo4j
- 触发学习模板保存：`_save_learned_templates_from_task()` → `repo.upsert_learned_template()`
  - 按 `(domain_code, report_type_code, chapter, slot_signature)` 唯一约束去重
- 模板回流机制：`reingest_task()` 支持实体确认后重映射和重新入库

---

## 三、数据模型

### 3.1 PostgreSQL 表

#### domain_factory_domains

| 列 | 类型 | 说明 |
|----|------|------|
| id | SERIAL PK | 主键 |
| code | VARCHAR(64) UNIQUE | 领域编码（coal, chem, mineral） |
| name | VARCHAR(128) | 领域名称（煤炭采掘、石油化工、矿产勘探） |
| description | TEXT | 领域描述 |

#### report_types（视图/配置）

报告类型通过 `domain_factory_repository.list_report_types()` 查询，按 domain 分组返回。当前配置的领域×报告类型：

| 领域 | 报告类型 code | 名称 |
|------|-------------|------|
| coal | eia_report | 环境影响评价报告 |
| coal | feasibility_report | 可行性研究报告 |
| coal | geological_exploration | 固体矿物地质勘查报告 |
| chem | eia_report | 环境影响评价报告 |
| chem | feasibility_report | 可行性研究报告 |
| mineral | eia_report | 环境影响评价报告 |
| mineral | feasibility_report | 可行性研究报告 |
| mineral | geological_exploration | 地质勘查报告 |

#### domain_factory_tasks

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(64) PK | 任务 ID |
| domain_id | INTEGER FK | 关联领域 |
| file_name | VARCHAR(255) | 文件名 |
| storage_path | VARCHAR(1024) | 存储路径 |
| status | VARCHAR(32) | UPLOADED/PARSING/GENERALIZING/WAITING_REVIEW/COMMITTED/FAILED |
| report_type_code | VARCHAR(64) | 报告类型编码（默认 "通用"） |
| ai_confidence | INTEGER | AI 置信度（0~100） |
| base_info | JSON | 提取的变量值（从 slot 收集） |
| source_paragraphs | JSON | 解析后的段落数组（含分类+模板） |
| structured_blocks | JSON | 结构化块（含段落和表格） |
| raw_markdown | TEXT | 原始 Markdown |
| raw_html | TEXT | 原始 HTML |
| template_payload | JSON | 全局模板（前端聚合用） |
| template_metadata | JSON | 模板元数据（unrecognized_slots, domain_code） |
| logical_relations | JSON | 逻辑关系（causal_chains, conditions, data_refs） |

#### domain_factory_learned_templates

| 列 | 类型 | 说明 |
|----|------|------|
| id | SERIAL PK | 主键 |
| domain_code | VARCHAR(64) | 领域编码 |
| report_type_code | VARCHAR(64) | 报告类型编码 |
| chapter | VARCHAR(255) | 章节路径 |
| generalized | TEXT | 泛化模板文本 |
| slots | JSON | slot 定义 |
| slot_signature | VARCHAR(255) | slot 签名（用于去重） |
| sample_original | TEXT | 样例原文 |
| match_count | INTEGER | 被匹配次数 |
| extra_meta | JSON | 额外元信息 |

唯一约束：`(domain_code, report_type_code, chapter, slot_signature)`

### 3.2 段落数据结构（source_paragraphs 中的每个元素）

```json
{
  "id": "p_42",
  "content": "原文内容",
  "title": "标题文本（仅 heading 类型有值）",
  "is_title": false,
  "is_table": false,
  "section_path": ["1", "2", "3"],
  "parent_title": "自然和社会经济概况",
  "classify_type": "parameter",

  "template": {
    "generalized": "{{项目名称}}位于{{地理位置}}，[地理地势描述]，属{{地貌类型}}",
    "original": "原文内容",
    "slots": [
      {"name": "项目名称", "type": "parameter", "entity_ref": "project_name", "value": "横城矿区"},
      {"name": "地理位置", "type": "parameter", "entity_ref": "location", "value": "宁夏东部"},
      {"name": "地貌类型", "type": "enum", "entity_ref": "landform_type",
       "vocabulary": ["丘陵","平原","山地","高原","盆地","沙漠","戈壁"]}
    ],
    "metadata": {"chapter": "3.1", "tags": ["自然环境"]},
    "quality_score": 0.95,
    "formula": {...},
    "table_schema": {...},
    "legal_references": [...]
  }
}
```

### 3.3 Slot 四类分类体系

| 类型 | type 值 | 值域 | 新项目填充方式 |
|------|---------|------|-------------|
| 参数型 | `parameter` | 自由文本/数值 | 用户手动填写 |
| 枚举型 | `enum` | 固定词汇表（vocabulary） | 下拉选择 |
| 描述型 | `descriptive` | 半结构化文本 | 参考模板改写 |
| 引用型 | `reference` | 外部知识库 | 从知识库关联 |

兜底规则：空 type 或未知 type 自动回退为 `parameter`。

### 3.4 法律引用结构

```json
{
  "name": "中华人民共和国环境保护法",
  "code": null,
  "type": "law",
  "scope": "national",
  "authority": "全国人大",
  "effective_date": "2015-01-01",
  "status": "effective",
  "superseded_by": null,
  "source_para_id": "p_15"
}
```

9 层分类体系：

| type 值 | 层级 | scope |
|---------|------|-------|
| law | 法律 | national |
| admin_regulation | 行政法规 | national |
| local_regulation | 地方性法规 | regional |
| ministry_rule | 部门规章 | national |
| local_rule | 地方规章 | regional |
| technical_standard | 技术规范 | national |
| national_plan | 国家规划 | national |
| local_plan | 地方规划 | regional |
| project_material | 项目资料 | project |

---

## 四、知识图谱结构

### 4.1 节点类型

| 节点 | 标签 | 属性 | 来源 |
|------|------|------|------|
| 文档 | Document | id, title, domain, domain_code, report_type_code | 上传文件 |
| 章节 | Section | id, title, path, level, order | heading 段落 |
| 段落模板 | ParagraphTemplate | id, generalized, original, slot_count, quality_score, classify_type | parameter 段落泛化 |
| 插槽 | Slot | id, name, type, entity_ref, value, unit, vocabulary | 泛化产出 |
| 实体模式 | EntitySchema | id, name, category, data_type | 实体确认 |
| 法律引用 | LegalReference | id, name, code, type, scope, authority, effective_date, status, superseded_by | 法律引用提取 |
| 表格模式 | TableSchema | id, name, table_type, columns, structural_rows | 表格提取 |
| 公式模板 | FormulaTemplate | id, name, original, format, purpose, variables | 公式提取 |
| 流程 | ProcessFlow | id, name, figure_type, caption | 图片 VLM 提取 |
| 步骤 | ProcessStep | id, name, type | 流程图步骤 |
| 领域大纲 | DomainOutline | id, domain, report_type, source_count, last_updated | 骨架聚合 |
| 章节模板 | ChapterTemplate | id, title, level, order, rigidity, frequency | 骨架聚合 |
| 段落角色 | ParagraphRole | id, role, order, typical_length, contains_data, required_slots | 骨架聚合 |
| 因果链 | CausalChain | id, cause_para_id, effect_para_id, relation | 逻辑关系提取 |
| 条件规则 | ConditionRule | id, expression, consequence, source, frequency | 逻辑关系提取 |
| 数据流 | DataFlow | id, para_id, source, data_fields | 逻辑关系提取 |

### 4.2 关系类型

| 关系 | 起点 → 终点 | 属性 |
|------|------------|------|
| HAS_SECTION | Document → Section | order |
| HAS_CHILD | Section → Section | — |
| NEXT_SECTION | Section → Section | order |
| COMPOSED_OF | Section → ParagraphTemplate | order |
| HAS_SLOT | ParagraphTemplate → Slot | — |
| CITES | Slot → EntitySchema | — |
| CONSTRAINS | LegalReference → Section | — |
| HAS_FORMULA | Section → FormulaTemplate | — |
| USES_VARIABLE | FormulaTemplate → Slot | symbol |
| HAS_PROCESS_FLOW | Section → ProcessFlow | — |
| STEP | ProcessFlow → ProcessStep | order |
| CONTRIBUTES_TO | Document → DomainOutline | — |
| HAS_CHAPTER | DomainOutline → ChapterTemplate | — |
| REQUIRES_PARAGRAPH_ROLE | ChapterTemplate → ParagraphRole | order |
| REALIZED_BY | ParagraphRole → ParagraphTemplate | confidence, frequency |
| REQUIRED_WHEN | ConditionRule → ChapterTemplate | condition |
| CAUSES | ParagraphTemplate → ParagraphTemplate | order |
| SOURCED_FROM | DataFlow → TableSchema | column |

### 4.3 GraphBuilder 构建 9 步

入口：`GraphBuilder.build_knowledge_graph()`

```
Step 1: _create_document_node        — 创建 Document 节点
Step 2: _build_sections_and_templates — 创建 Section/ParagraphTemplate/Slot + 关系
Step 3: _build_entity_schema_nodes    — 创建 EntitySchema + CITES 关系
Step 4: _build_legal_reference_nodes  — 创建 LegalReference（含 effective_date/status/superseded_by）
Step 5: _build_table_schema_nodes     — 创建 TableSchema + 列定义
Step 6: _build_formula_template_nodes — 创建 FormulaTemplate + USES_VARIABLE 关系
Step 7: _build_process_flow_nodes     — 创建 ProcessFlow/ProcessStep + STEP 关系
Step 8: _build_skeleton_aggregation   — 跨文档聚合 DomainOutline/ChapterTemplate/ParagraphRole
Step 9: _build_logical_relationship_nodes — 创建 CausalChain/ConditionRule/DataFlow
```

### 4.4 骨架聚合算法

`_build_skeleton_aggregation()` 在同一 `(domain, report_type)` 下跨文档聚合：

1. MERGE 创建或更新 DomainOutline 节点，`source_count` 自增
2. 对每份文档的章节树，MERGE 创建 ChapterTemplate，按 section_path 对齐
3. 计算 `frequency`（出现该章节的文档数 / 总文档数）
4. 判定 `rigidity`：
   - frequency ≥ 0.9 → `rigid`（刚性章节）
   - frequency ≥ 0.5 → `flexible`（弹性章节）
   - frequency < 0.5 → `conditional`（条件章节）
5. 对每个章节内的 parameter 段落，按模板 hash 去重合并为 ParagraphRole
6. 创建 REQUIRES_PARAGRAPH_ROLE / REALIZED_BY 关系

### 4.5 法律引用时效性管理

`_build_legal_reference_nodes()` 中的 Cypher：

```cypher
MERGE (ref:LegalReference {id: $ref_id})
SET ref.effective_date = $effective_date,
    ref.status = $status,
    ref.superseded_by = $superseded_by
// 自动标记被替代的旧版本
OPTIONAL MATCH (old:LegalReference {code: $code, status: 'effective'})
WHERE old.id <> $ref_id AND old.effective_date < $effective_date
SET old.status = 'superseded', old.superseded_by = $ref_id
```

### 4.6 逻辑关系精确关联

`_build_logical_relationship_nodes()` 使用 `_find_template_id_for_para()` 将 para_id 精确映射到已创建的 ParagraphTemplate 节点，而非模糊匹配文本内容。这确保了因果链和数据引用链的端到端精确性。

---

## 五、关键算法

### 5.1 模板质量评估

`evaluate_template_quality(generalized, slots)` → `float (0~1)`

评分规则：
- 基准分 1.0
- slot 数量 >5 → 每多一个扣 0.1
- 无语义命名（方位1、特征2等）→ 每个扣 0.2
- 固定单位单独提取为 slot → 每个扣 0.15
- slot 名称 >8 字 → 每个扣 0.1
- enum 型 slot 缺 vocabulary → 每个扣 0.1
- 有叙述占位符 → 加 0.05

### 5.2 Slot-Variable 统一

废弃独立的 EXTRACT 阶段。Slot 同时作为提取变量：

```
泛化产出 slot → slot.value 即提取结果
                    ↓
                base_info（前端展示用）
```

从段落级 slot 值收集到 `form_data`，不再调用 LLM 全局提取。

### 5.3 分章节提取

`extract_by_chapter()` — 按章节分组后对每组段落用 LLM 提取局部变量：

1. `_group_by_chapter()` 按 section_path 首级分组
2. `_get_local_schema()` 按章节路径匹配预定义的局部 Schema（LOCAL_SCHEMA_MAP）
3. 只用该章节的段落作为上下文，LLM 提取精度远高于全局提取
4. 当前已配置：`coal.eia_construction` 和 `coal.eia_planning` 的部分章节 Schema

### 5.4 公式变量映射

`extract_formula()` → `_extract_formula_symbols()`：

- SYMBOL_MAP 覆盖 14 个常见物理量（C/Q/u/H/LA/We/X/Y/W/li/Hi/cot 等）
- 每个变量映射到 name + unit + entity_ref
- `_infer_formula_purpose()` 根据标题和章节路径推断公式用途（预测浓度/噪声/涌水量/沉降等）

### 5.5 表格列角色判定

`_infer_column_role()` 按优先级判定：

1. key_value 表格 → 第一列固定为 `key`
2. 标准限值表格 → 分类列为 `structural`，数值列为 `data`
3. 关键词匹配：标准→reference, 达标→derived, 浓度→data, 监测点→structural
4. 兜底：数值占比 >50% → data，否则 structural

---

## 六、前端交互

### 6.1 上传流程

1. 选择行业（domain）→ 二级联动加载报告类型（report_type）
2. 上传文件 → 创建任务（`report_type_code` 写入 task）
3. 任务进入 ETL Pipeline

### 6.2 ETL 审核工作台（EtlWorkbench.vue）

- **三栏布局**：章节导航 | 原文查看器 | 结构化元数据
- **段落分类标签**：每个段落前显示分类标记（heading/legal_reference/parameter/table/narrative/formula/figure/list）
- **AI 置信度**：高置信度（≥80%）显示 ✓，低置信度显示 ⚠
- **批量操作**：
  - "一键确认高置信度"
  - "仅显示待审核"
  - 审核进度条
- **数据源**：统一从 `para.template` 读取（不再有根级重复字段）

### 6.3 数据源管理（DataSourceDashboard.vue）

- 领域筛选器：行业选择 + 报告类型选择（二级联动）
- 任务列表展示 `report_type_code` 对应的中文标签

---

## 七、测试验证

### 7.1 端到端测试结果

测试文件：`横城矿区总体规划环评报告书.md`（219,514 字符，3091 行）
测试环境：Docker 容器内直接导入运行

| 测试 | 结果 | 详情 |
|------|------|------|
| 基础设施 | PASS | 3 领域（coal/chem/mineral），报告类型二级联动正常 |
| 文件加载 | PASS | Markdown 解析 → 2970 段落 |
| CLASSIFY | PASS | heading:363, parameter:1761, narrative:692, legal_reference:145, formula:9 |
| parent_title | PASS | 2956/2956 回填率 100% |
| 法律引用 | PASS | 124 条，4 类型（technical_standard:76, law:19, admin_regulation:19, national_plan:10），46 条含生效日期 |
| 公式提取 | PASS | 9 个公式，变量映射正常（如 W→产能/产量 Mt/a） |
| 质量评估 | PASS | 好模板=1.00，差模板=0.00 |
| GraphBuilder | PASS | 9 个构建方法全部存在，domain_code + report_type_code 参数正确 |
| Slot 兜底 | PASS | 无 type → parameter，未知 type → parameter |
| 逻辑关系 | PASS | 1 因果链 + 2 条件分支 + 26 数据引用 |
| repo 参数 | PASS | upsert_learned_template 含 report_type_code |

### 7.2 分类覆盖率

实际测试结果（横城矿区文档，Markdown 格式无标准表格）：

| 类型 | 数量 | 说明 |
|------|------|------|
| parameter | 1761 | 含数值的参数型段落，占比最高 |
| narrative | 692 | 叙述性正文 |
| heading | 363 | 章节标题 |
| legal_reference | 145 | 法律/标准引用 |
| formula | 9 | 公式/计算模型 |
| table | 0 | 文档中无 `|---|` 标准表格格式 |
| figure | 0 | 纯 Markdown 文件无图片 |
| list | 0 | 无连续编号列表块 |

---

## 八、已知限制与后续计划

### 8.1 当前限制

1. **LOCAL_SCHEMA_MAP 覆盖不全**：仅配置了 coal.eia_construction 和 coal.eia_planning 的部分章节，其他领域/报告类型需要补充
2. **图片 VLM 依赖外部服务**：图片 URL 需要可访问（MinIO 内网可能需要 base64 编码中转）
3. **骨架聚合需要 ≥2 份同类型文档**：单份文档时 rigidity 全部为 rigid（frequency=1.0），无法区分刚性/弹性
4. **Markdown 格式文档无表格**：测试用的 `.md` 文件不含标准表格格式，实际 `.docx` 文件通过 HTML 表格处理

### 8.2 后续优化方向

1. 补全更多领域/报告类型的 LOCAL_SCHEMA_MAP
2. 表格 Schema 提取增强：对复杂合并表头的支持
3. 图片 VLM 的 MinIO 内网访问方案
4. 逻辑关系提取的章节粒度优化（减少 LLM 调用）
5. 模板匹配器（TemplateMatcher）与 domain×report_type 隔离的适配
