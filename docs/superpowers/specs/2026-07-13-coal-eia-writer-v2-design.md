# 环评写作助手 v2 设计文档

> 日期: 2026-07-13 | 状态: 待评审

## 1. 背景与动机

当前 `coal-eia-writer` v1 采用"1 个编排者 + 1 个通用 chapter-writer"架构，存在三个核心问题：

1. **单一 writer 无法覆盖三类认知任务** — 法规引用、数据分析、模型预测在系统提示词中互相稀释
2. **不支持长项目流程** — 数据收集、编写、审批无法并行，没有跨会话状态管理
3. **缺少计算工具** — LLM 直接手算复杂公式（如沉陷预测），结果不可靠

v2 基于对《2横城矿区总体规划（修编）环评报告书（报批版）》13 章样例的深度分析重新设计。

## 2. 报告结构分析（从样例提取）

### 2.1 章节分类

| 类型 | 占比 | 章节 | 写作策略 |
|------|------|------|----------|
| **模板型** | ~30% | 1总则、10环境管理、11清洁生产、12公众参与 | 法规引用+结构化填空 |
| **数据密集型** | ~45% | 2规划概况、3环境现状、4回顾评价、6影响预测 | 监测数据+模型计算 |
| **综合型** | ~25% | 5影响识别、7承载力、8综合论证、9减缓措施、13结论 | 二次加工+综合判断 |

### 2.2 章节依赖关系

```
第一层 (基础数据层 — 可并行)
  第1章 总则 / 第2章 规划概况 / 第3章 环境现状 / 第4章 回顾评价

第二层 (分析层 — 依赖基础层)
  第5章 影响识别 → 第6章 影响预测 → 第7章 承载力分析

第三层 (综合层)
  第8章 综合论证 → 第9章 减缓措施 → 第13章 结论

横向独立层
  第10章 环境管理 / 第11章 清洁生产 / 第12章 公众参与
```

### 2.3 样例关键数据

- 总字数: ~30 万字, 3533 段落, 192 表格
- 编号体系: `表X.Y-Z` (章-节-序号), 共约 290 个带编号表格
- 层级深度: 最多 5 级 (章→节→小节→细目→五级标题)
- 交叉引用格式: `{{REF:chXX/表X-Y}}` 占位符

## 3. Agent 架构: 1 组长 + 3 专业 Writer

```
┌─────────────────────────────────────────────────────┐
│              组长 (coal-eia-writer v2)               │
│                                                     │
│  职责: 规划范围 → 建 report+PPS → 波次派发 →        │
│        校验 → 装配交付 → 跨会话 checkpoint            │
│                                                     │
│  工具: create_report, get_report, set_pps_param,     │
│        assemble_report, subagent_*, ask_user_question│
│        list_chapter_keys, list_report_types           │
└──┬──────────────────┬──────────────────────┬────────┘
   │                  │                      │
   ▼                  ▼                      ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ 法规标准      │ │ 数据与现状    │ │ 预测与论证        │
│ writer        │ │ writer        │ │ writer            │
│ slug:         │ │ slug:         │ │ slug:             │
│ regulation    │ │ data-survey   │ │ prediction        │
│               │ │               │ │                   │
│ 负责章节:     │ │ 负责章节:     │ │ 负责章节:         │
│ 1 总则        │ │ 2 规划概况    │ │ 5 影响识别         │
│ 10 环境管理   │ │ 3 环境现状    │ │ 6 影响预测         │
│ 11 清洁生产   │ │ 4 回顾评价    │ │ 7 承载力           │
│ 12 公众参与   │ │               │ │ 8 综合论证         │
│               │ │               │ │ 9 减缓措施         │
│ 额外工具:     │ │               │ │ 13 结论            │
│ query_kb      │ │               │ │                   │
│ (法规库)      │ │               │ │ 额外工具:          │
│               │ │               │ │ calculate_a_value  │
│ 写好策略:     │ │ 写好策略:     │ │ calculate_water_*  │
│ 90% 模板替换  │ │ 段落模板+     │ │ lookup_subsidence  │
│ (同行业报告)  │ │ 监测数据      │ │                    │
│               │ │               │ │ 写好策略:          │
│               │ │               │ │ 公式框架复用       │
│               │ │               │ │ 参数替换+工具计算  │
└──────────────┘ └──────────────┘ └──────────────────┘

  共用基础工具: get_chapter_outline, get_report, get_templates, save_chapter
  共用技能: template-recommender, slot-filler, compliance-checker
```

### 3.1 复用现有基础设施

三个 writer 基于现有 `SubAgentBackend` 注册，`chapter-writer` 废弃：

```python
# 现有
AgentRepository.ensure_chapter_writer_subagent()

# 改为
AgentRepository.ensure_regulation_writer_subagent()
AgentRepository.ensure_data_survey_writer_subagent()
AgentRepository.ensure_prediction_writer_subagent()
```

每个 writer 共用基础工具集（`get_chapter_outline`, `get_report`, `get_templates`, `save_chapter`），差异仅在系统提示词和额外工具。

## 4. 项目生命周期（跨会话长项目）

### 4.1 四阶段模型

```
阶段 1: 启动 (1 次对话)
  ├─ 组长: 确认章节范围、大纲
  ├─ 用户: 确认/调整
  ├─ 组长: create_report → report_id
  └─ 输出: report_id + 章节列表 + PPS 骨架

阶段 2+3: 并行期 (N 次对话，持续数天)
  ├─ 数据 writer: 扫描所有章节 → 列出数据需求清单
  │   ├─ 已有数据 → 填入 PPS
  │   └─ 缺失数据 → {{MISSING:参数名}} 占位符 + asked_at 标记
  │
  ├─ 法规 writer: 独立章先行（1/10/11/12）
  ├─ 预测 writer: 模板化章先行，依赖数据章跳过
  │
  ├─ 用户补数据时:
  │   → set_pps_param → 状态变为 filled
  │   → 组长通知对应章节 writer 重写被跳过的章
  │
  └─ 每轮结束: 组长输出 checkpoint（已完成/进行中/等待数据/待审批）

阶段 4: 交付 (1-2 次对话)
  ├─ assemble_report → 解析 {{REF:...}} 和 {{MISSING:...}}
  ├─ compliance-checker 校验
  ├─ 用户终审
  └─ present_artifacts 交付
```

### 4.2 章节状态扩展

当前只有 `draft` / `done`，需扩展为：

| 状态 | 含义 | 过渡 |
|------|------|------|
| `pending_data` | 等待用户提供数据 | 用户补数据 → `draft` |
| `draft` | 子 agent 已写入初稿 | 用户审批通过 → `done` |
| `review` | 组长/用户审批中 | 审批通过 → `done` / 驳回 → `draft` |
| `done` | 终稿锁定 | 可装配 |
| `skipped` | 用户明确跳过该章 | — |

### 4.3 {{MISSING}} 占位符机制

```
正文中:
  矿区 2023 年 PM10 年均浓度为 {{MISSING:大气监测PM10_2023}} μg/m³
  评价区 SO₂ 日均浓度范围为 {{MISSING:大气监测SO2_2023}} μg/m³

PPS 中:
  entity_key: "大气监测PM10_2023"
  entity_type: "missing"
  label: "2023年PM10年均浓度"
  chapter: "第3章 环境现状"
  value: null
  asked_at: 2026-07-13
  status: "missing"

用户说 "PM10是68，SO₂是12":
  → set_pps_param({entity_key: "大气监测PM10_2023", value: 68, value_type: "number", unit: "μg/m³"})
  → 状态自动变为 filled
  → assemble_report 自动替换占位符
  → 如果该章之前因缺数据被跳过，组长派 writer 重写
```

## 5. 三层模板替换策略

编写策略优先级从高到低:

### 第一层: 整章复用 (KB 同类报告)

1. `query_kb` 搜索同类矿区报告 (如 "横城矿区 大气影响预测")
2. KB 返回匹配章节 → 结构化比对: 哪些段落/公式/表格可复用
3. 保留: 章节目号、公式框架、表格结构、分析方法
4. 替换: 矿区名称、产能数据、监测值、地理坐标等 PPS 差异项
5. 差异部分 → `{{CUSTOM:需专项编写的内容}}` 占位，后续安排

**触发条件**: writer 获取大纲后先尝试 `query_kb`，命中率 > 70% 则走整章复用流程。

### 第二层: 段落模板 (当前 get_templates 能力)

- `get_templates(canonical_chapter_key)` → 标准段落模板
- slot-filler 填充插槽
- 适用于无法整章复用的数据密集章

### 第三层: 从头写 (仅项目特有内容)

- 特定保护目标影响分析
- 当地特有的环境要素
- 用户特殊要求的定制内容

## 6. 计算工具分层

| 复杂度 | 处理方式 | 工具 |
|--------|---------|------|
| ⭐⭐ 以下 (简单加减、加权) | 沙箱 Python 直接计算 | 无额外工具 |
| ⭐⭐⭐ (固定公式) | 封装为可调用工具 | `calculate_a_value`, `calculate_water_capacity`, `calculate_noise_attenuation` |
| ⭐⭐⭐⭐ 以上 (需专业软件) | KB 查预计算结果 | `lookup_subsidence_params` (KB 查询 MSPS 软件输出) |

### 新增工具清单

| 工具名 | 挂载到 | 用途 | 优先级 |
|--------|--------|------|--------|
| `calculate_a_value` | 预测 writer | 大气环境容量 A 值法 | P0 |
| `calculate_water_capacity` | 预测 writer | 水环境容量计算 (一维稳态) | P0 |
| `lookup_subsidence_params` | 预测 writer | KB 查预计算沉陷系数 | P0 |
| `calculate_noise_attenuation` | 预测 writer | 噪声几何发散衰减 | P1 |

### 不做的

地表沉陷概率积分法、AERSCREEN 大气扩散 — 这些需要 MSPS/EIAProA 等专业软件。策略是 KB 存储预计算结果并在报告中引用"根据 XX 软件模拟结果..."

## 7. 审批与任务队列

### 7.1 审批流程

```
writer 写完章 → save_chapter(status="review")
  → 组长 mark 该章需要审批
  → 用户下次对话看到 "第 3 章待审批"
  → 用户: "第3章通过" 或 "第3章需要改XX"
  → 组长: save_chapter(status="done") 或重新派发 writer
```

### 7.2 组长每个对话结束时的 Checkpoint

```
📊 项目: 横城矿区环评报告 (report_id: rpt_xxx)
├─ ✅ 已完成 (4/13): 第1章、第10章、第11章、第12章
├─ 🔍 待审批 (2): 第2章、第5章
├─ ⏳ 等待数据 (2): 第3章(大气监测) 第4章(历史排放)
├─ ⏭ 跳过 (1): 第6章(等待第3章数据)
├─ ⬜ 未开始 (4): 第7章、第8章、第9章、第13章
│
└─ 下次你可以说:
   · "审批第2章和第5章"
   · "补充大气监测数据"
   · "继续写第7-9章"
```

## 8. 实施路线图

### Phase 1: 3-Writer 拆分 (P0)
- 废弃 chapter-writer，注册 3 个新 writer (regulation/data-survey/prediction)
- 编写各自的系统提示词 (SKILL.md)
- 更新 coal-eia-writer SKILL.md (v2)

### Phase 2: 计算工具 (P0)
- `calculate_a_value` 工具实现
- `calculate_water_capacity` 工具实现
- `lookup_subsidence_params` KB 查询

### Phase 3: 长项目支持 (P1)
- 章节状态扩展 (pending_data / review)
- {{MISSING}} 占位符自动检测
- 组长 checkpoint 输出

### Phase 4: 审批流 (P1)
- 审批状态管理
- 驳回→重写流程

### Phase 5: 三层模板 (P2)
- 整章复用 KB 搜索策略
- {{CUSTOM}} 差异标注

## 9. 不变量 (设计约束)

1. `report_id` 是全局唯一标识，跨会话复用
2. 所有章节正文经 `save_chapter` 写入，不直接操作文件系统
3. PPS 参数经 `set_pps_param` 写入，不手维护 markdown
4. 数值必须有来源 (监测报告/法规/KB)，不得编造
5. 章间引用统一用 `{{REF:...}}`，跨 writer 交叉引用无需即时解析
6. 最终交付经 `assemble_report` + `present_artifacts`
