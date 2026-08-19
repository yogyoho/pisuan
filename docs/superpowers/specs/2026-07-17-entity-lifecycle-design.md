# 实体对象参与加工流程的设计

> 日期: 2026-07-17 | 状态: 待评审

## 1. 概述

### 1.1 问题

领域知识工厂的 ETL 加工流程中，实体对象与加工环节脱节：

- **泛化阶段**: LLM prompt 不含实体 schema 上下文，slot 自由提取，`entity_ref` 始终为空
- **校验阶段**: Tab 1 无 slot→entity.property 绑定入口
- **实体进化**: Tab 3 同步 LLM 调用，用户等待 10-30s 体验差；无规则约束 LLM 提取边界

### 1.2 核心理念

**自下而上发现 + 自上而下收敛**——混合路径渐进式构建正向飞轮：

```
文档1 → LLM自由提取 → auto-match → 剩余 LLM建议 → 人工确认 → DB
文档2 → LLM参考已有属性提取 → auto-match → 更少剩余 → 人工确认
文档3 → LLM精确提取 → auto-match命中率高 → 几乎无剩余
```

---

## 2. 实体分类体系

基于 HJ/T 130-2019 导则 13 章 + 现有 7 类实体，定义 6 大分类：

| 分类 key | 名称 | 覆盖章节 | 典型实体 |
|---------|------|---------|---------|
| `project_basic` | 基础工程实体 | 第1-2章 | project_main, design_capacity, mining_technology |
| `natural_env` | 自然环境实体 | 第3.1章 | topography, climate_meteorology, surface_water, hydrogeology |
| `env_quality` | 环境质量与污染源实体 | 第3.3, 5章 | air_quality, water_quality, pollutant, noise_source |
| `sensitive_target` | 敏感目标与空间实体 | 第3, 6章 | residential, ecological_redline, cultural_relic |
| `measures_regulation` | 措施与法规实体 | 第9, 10章 | prevention_measure, regulation, monitoring_plan |
| `impact_assessment` | 环境影响评价实体 | 第5-7, 13章 | impact_behavior, assessment_conclusion, formula_model |

每类实体包含 `properties` —— 如 `topography` 实体有属性 `altitude_min`, `altitude_max`, `relative_relief_min` 等。

---

## 3. 实体参与加工的三个阶段

### 3.1 阶段一：泛化时的实体感知（增强 LLM Prompt）

**改动**: `_generalize_text` 的 LLM prompt 中注入"已有实体属性提示"。

**规则**: 不是把所有实体塞入 prompt（token 成本太高），而是：
1. 根据段落的 `classify_type` 和 `section_path` 定位所属领域
2. 只注入该领域 1-2 个相关实体的属性列表作为"参考但非强制"
3. 属性列表以紧凑格式：`参考实体: topography(海拔最低值, 海拔最高值, 地貌类型)`

**行为**: LLM 仍可自由提取新 slot，但 prompt 引导其**优先匹配**已知属性名。

**开关**: 初期可关闭（效率考虑），实体库积累 20+ 属性后打开。

### 3.2 阶段二：校验时的绑定展示（Tab 1 只读）

**改动**: Tab 1 参数段落详情面板中，slot chip 展示绑定状态，只读：

```
Slot (12)
┌──────────────────────────────────────────────────────┐
│ [参数型] 矿区名称     → topography.mine_name    ✓    │
│ [参数型] 海拔最低值   → topography.altitude_min ✓    │
│ [描述型] 地貌类型     → 未绑定                       │
└──────────────────────────────────────────────────────┘
```

**不提供手动绑定操作**——729+ 个 slot 逐条绑定工作量太大。绑定全部走自动化：
1. ETL 泛化完成 → `_auto_map_slots_to_entity_properties` 自动匹配已有属性
2. 用户点"智能识别实体"→ 后台 LLM 处理剩余未绑定 slot
3. Tab 3 确认后自动填充 `entity_ref`

Tab 1 的 slot chips 仅**展示绑定状态**，`✓` = 已绑定，无标记 = 待识别。用户无需逐条操作。

### 3.3 阶段三：实体进化触发（Tab 1 异步后台任务）

**触发**: Tab 1 工具栏新增"智能识别实体"按钮。

```
┌─ 工具栏 ─────────────────────────────────────┐
│ 类型筛选  [全部] [参数] ...    [运行校验] [智能识别实体] │
└──────────────────────────────────────────────┘
```

**流程**:

```
用户点击 [智能识别实体]
  → 按钮 loading 状态，用户可继续审查其他段落
  → 后台异步 LLM 任务（不阻塞 UI）:
    1. 收集全部 slot（按名称去重，entity_ref 非空的跳过）
    2. 加载已有实体+属性作为约束
    3. LLM 分析 → 输出建议:
       - 新实体 + 属性列表
       - 已有实体新属性
       - 已有属性绑定建议
    4. 结果写入 task.template_metadata.entity_proposals
  → 完成后弹出通知: "识别出 N 个新实体属性，[前往确认]"
  → 用户点击通知 → 跳转 Tab 3 查看结果
```

**约束规则**:

| 维数 | 规则 | 实现 |
|------|------|------|
| 领域限定 | slot 必须归属 6 大分类之一 | LLM prompt 中给分类列表 |
| 置信度阈值 | ≥3 个不同段落出现同名 slot 才建议新属性 | 预处理过滤 |
| 粒度控制 | 可合并的连续值（如最低+最高+单位）→ 建议合并为单个属性组 | LLM prompt 示例 |
| 完整性要求 | 建议属性必须给出 key / name_cn / value_type / unit（可推 测为 "unknown"） | JSON schema 验证 |

---

## 4. 数据流

```
Tab 1: [智能识别实体]
  └→ POST /tasks/{id}/discover-entities (后台任务)
       ├→ 收集未绑定 slot
       ├→ LLM 分析（按分类分批，每批 ≤30 slot）
       ├→ 输出 entity_proposals JSON
       └→ 写入 task.template_metadata
            └→ 前端轮询检测完成 → 通知用户

Tab 3: 用户确认
  ├→ 查看 proposal 列表（按分类 tabs）
  ├→ 勾选确认 → batch confirm
  ├→ 写入 domain_entity_schemas (new entity / add property)
  └→ 触发 re-map: 更新当前任务所有 slot 的 entity_ref

Tab 1: 绑定操作
  └→ 下拉选择已有属性 → 即时写 slot.entity_ref → 保存到 source_paragraphs
```

---

## 5. 实体属性 Schema

```json
{
  "entity_key": "topography",
  "name_cn": "地形地貌",
  "category": "natural_env",
  "properties": [
    {
      "key": "altitude_min",
      "name_cn": "海拔最低值",
      "value_type": "number",
      "unit": "m"
    },
    {
      "key": "altitude_max", 
      "name_cn": "海拔最高值",
      "value_type": "number",
      "unit": "m"
    }
  ]
}
```

`entity_ref` 格式: `"topography.altitude_min"`

---

## 6. 实施路线

| Phase | 内容 | 优先级 | 依赖 |
|-------|------|--------|------|
| Phase 1 | 6 分类体系迁移 + 现有实体归类 | P0 | 无 |
| Phase 2 | Tab 1 slot chip 展示绑定状态（只读） | P0 | Phase 1 |
| Phase 3 | "智能识别实体"后台异步任务 | P0 | Phase 1 |
| Phase 4 | 泛化 LLM prompt 注入实体属性 | P1 | Phase 1 |
| Phase 5 | Tab 3 展示 proposal + 批量确认 | P1 | Phase 3 |

---

## 7. 自审

- ✅ 无 TBD/TODO
- ✅ 各阶段数据流一致：slot → entity_ref → DB → Neo4j
- ✅ 6 分类映射到 EIA 报告章节，边界清晰
- ✅ 约束规则有定量标准（≥3 段落出现）
