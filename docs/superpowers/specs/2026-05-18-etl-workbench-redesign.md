# ETL 清洗工作台全链路重设计方案

> 日期：2026-05-18
> 状态：已批准，待实施

## 背景

当前 ETL 工作台存在三个核心问题：

1. **分类质量差** — WAITING_REVIEW 任务中 602/725 段落无 classify_type，pipeline 基本没起作用
2. **规则黑盒** — 分类/泛化规则硬编码在 service.py 中，用户无法查看、修改、评估
3. **前端不可编辑** — Tab 1 只读展示，无法修正错误的结构化元数据；表格详情区空间不足

目标用户：领域专家（如环评工程师），期望上传报告后 AI 自动提取，专家快速校验修正后入库。

## 设计方案：规则驱动重设计

将 pipeline 规则从代码中抽离为可 CRUD 的配置，工作台围绕"规则 → 结果 → 校验"闭环设计。

---

## §1 统一的 Pipeline 配置管理

合并现有 Prompt 模板管理与新增规则管理，统一为一个"Pipeline 配置"页面。

### 入口

替代现有"Prompt 模板管理"，路由 `/domain-factory/pipeline-config`。Hero 区按钮文字改为"Pipeline 配置"。

### 区块 1：LLM Prompt 模板（复用现有）

从 `PromptConfigView.vue` 迁移 4 个 prompt 编辑器：
- extract_prompt（文档解析/信息抽取）
- template_prompt（模板泛化）
- schema_generation_prompt（Schema 生成）
- section_generalization_prompt（章节泛化）

新增：段落级泛化 prompt（用于 parameter 段落的 LLM 泛化调用）。

每个编辑器保留现有功能：textarea 编辑、变量插入、重置为默认。

### 区块 2：分类规则表（新增）

新增 `domain_factory_rules` 数据表：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PRIMARY KEY | |
| domain_code | VARCHAR(64) | 领域代码，NULL 表示全局 |
| rule_type | VARCHAR(32) | classify / slot_pattern / narrative_subtype / legal_pattern |
| name | VARCHAR(128) | 规则名称，如"参数型-单位检测" |
| pattern | TEXT | 正则表达式或关键词 JSON |
| target_type | VARCHAR(32) | 命中后的 classify_type |
| priority | INTEGER | 越小越先执行 |
| enabled | BOOLEAN DEFAULT TRUE | |
| hit_count | INTEGER DEFAULT 0 | 命中统计 |
| miss_count | INTEGER DEFAULT 0 | 未命中统计 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

管理界面：
- 规则列表，按 rule_type 分组，显示命中/未命中统计
- 编辑弹窗：修改 pattern、target_type、priority
- 测试功能：输入文本 → 显示哪些规则命中
- "重置为默认"按钮：从代码中的默认值恢复

### 区块 3：泛化模板库（增强已有）

基于已有 `domain_factory_learned_templates` 表，新增管理界面：
- 按 domain 分组浏览
- 查看模板内容、slot 定义、命中次数
- 手动添加/修改/删除模板

### 区块 4：分类评估统计

- 最近 N 个任务的分类分布饼图
- 各规则的命中率和准确率
- LLM 分类的平均置信度趋势

---

## §2 结构化元数据校验 Tab 改造

### 按钮精简

**删除**：
- "确认高置信度" — AI 自己处理
- "保存修改" — 编辑后自动标记 dirty，离开段落时自动保存

**保留**：
- "确认审核 / 撤销审核" — 切换按钮
- "下一步" — 流程步骤导航

### JSON 编辑模式

JSON 开关增强：
- 切换后 textarea 可编辑
- 底部"应用修改"和"重置"按钮
- 应用时 JSON 校验，失败高亮错误行
- 成功后刷新详情面板

### 表格类型折叠布局

表格段落详情面板改为 `a-collapse`：

| 面板 | 默认状态 | 可编辑 |
|------|---------|--------|
| 原始表格 | 展开 | HTML 编辑模式（textarea） |
| 表格 Schema | 折叠 | 列名/角色/单位/词表可编辑 |
| 结构行数据 | 折叠 | 表格单元格可点击编辑 |

每个面板 header 显示摘要信息（Schema 显示列数、结构行显示行数）。

### 段落列表交互优化

- Shift+点击多选段落，批量确认审核
- 右键上下文菜单：确认审核 / 跳转到 Slot 变量校验 / 复制内容

---

## §3 分类质量保障机制

### 三阶段分类器

替代当前的 if-else 硬编码分类，改为独立可诊断的三阶段流程：

**阶段 1：规则匹配（确定性）**
- 从 `domain_factory_rules` 表加载分类规则，按 priority 排序
- 每个段落按顺序匹配，命中即标记
- 结果带 rule_id 和 classification_reason，可溯源
- 适用：table（含 `<table>` 标签）、legal_reference（含标准号）、heading（is_title）、parameter（含单位模式+slot 名称）

**阶段 2：LLM 分类（模糊段落）**
- 阶段 1 未匹配的段落批量送入 LLM
- prompt 中注入领域上下文 + 分类定义 + 少量示例
- 返回 classify_type + confidence + reason

**阶段 3：回退策略**
- 仍无法分类的段落标记为 narrative
- 记录原因（"无规则命中 + LLM 置信度低于阈值"）
- 前端用灰色标签显示原因

### 关键约束

- 每个段落必须得到一个 classify_type，不允许空值
- 每个分类结果附带 `classified_by`（rule_id / llm / fallback）和 `classification_reason`
- 前端 Tab 1 可按 `classified_by` 筛选，快速定位低质量项

---

## §4 前端组件拆分

将 1700 行的 `EtlWorkbench.vue` 拆分为可独立维护的组件。

### 组件结构

```
components/domain-factory/
├── EtlWorkbench.vue              # 壳组件：流程步骤条 + tab 切换 + 共享状态
├── etl/
│   ├── StructuredMetaTab.vue     # Tab 1: 结构化元数据校验
│   ├── SlotVerifyTab.vue         # Tab 2: Slot 变量校验
│   ├── EntityConfirmTab.vue      # Tab 3: 实体确认
│   ├── CommitTab.vue             # Tab 4: 入库确认
│   ├── detail-panels/
│   │   ├── HeadingDetail.vue
│   │   ├── TableDetail.vue       # 含折叠编辑
│   │   ├── LegalRefDetail.vue
│   │   ├── FormulaDetail.vue
│   │   ├── FigureDetail.vue
│   │   ├── ParameterDetail.vue
│   │   └── NarrativeDetail.vue
│   ├── ParagraphList.vue         # 中栏段落列表
│   └── ChapterNav.vue            # 左栏章节导航树
└── PipelineConfigView.vue        # Pipeline 配置页（替代 PromptConfigView）
```

### 状态管理

共享状态（task 数据、source_paragraphs、structured_blocks）用 provide/inject 或 Pinia store。各 tab 组件只管理自己的局部状态。

### 改造策略

逐个抽出，不一次性重写：
1. 先抽 detail-panels（最独立）
2. 再抽 ChapterNav 和 ParagraphList
3. 最后拆 tab 组件，EtlWorkbench 变薄壳

---

## §5 页面布局与导航整合

### 整体导航

```
知识工厂首页
  ├─ 数据源管理 tab
  ├─ ETL 清洗工作台 tab（内部 4 步流程）
  └─ "Pipeline 配置"入口
       ├─ LLM Prompt 模板
       ├─ 分类规则表
       ├─ 泛化模板库
       └─ 分类评估统计
```

### ETL 工作台底部状态栏

```
[领域] [报告类型] [段落 45/92 已审核]  [← 上一步] [下一步 →]
```

去掉"AI 置信度"（pipeline 内部指标），改为审核进度。

### 底部导航按钮

| 按钮 | 行为 |
|------|------|
| ← 上一步 | 回到上一个 tab，保留编辑状态 |
| 下一步 → | 未保存修改时提示保存；跳转下一 tab |
| 最后一步 | 按钮文字变为"确认入库" |

---

## 实施优先级

### P0：分类质量修复（解决根因）

1. 诊断 602 个空分类段落的根因
2. 实现三阶段分类器（§3）
3. 新增 `domain_factory_rules` 表 + CRUD API
4. 修复已知 bug（_SLOT_PATTERNS、variables 未定义、parent_title）

### P1：规则管理界面

1. 合并 Pipeline 配置页（§1）
2. 分类规则表管理 UI
3. 泛化模板库管理 UI
4. 分类评估统计面板

### P2：Tab 1 交互改造

1. 表格折叠布局 + 可编辑（§2）
2. JSON 编辑模式增强
3. 按钮精简
4. 批量操作（Shift+点击、右键菜单）

### P3：前端组件拆分

1. 抽出 detail-panels
2. 抽出 ChapterNav、ParagraphList
3. 拆分 tab 组件
4. 共享状态管理重构
