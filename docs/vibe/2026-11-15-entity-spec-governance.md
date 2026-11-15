# 实体对象构建规范 · 存量数据治理（2026-11-15）

## 目标

领域实体构建器中 71 个活跃实体对照《实体对象构建规范》
（`web/src/assets/docs/entity-construction-spec.md`）逐条审计后，一次性修复全部违规，
使 `audit_entity_spec.py` 复审归零（48 个历史悬空引用头除外，属历史遗留、不在本次范围）。

## 审计基线（2026-11-15，`.wolf/audit-entity-spec.json`）

| 规则 | 违规量 | 说明 |
|---|---|---|
| P1 属性键中文 | 180 处 / 18 实体 | 改名为英文 snake_case，name_cn 保留（引用按名兜底归一） |
| P3 值类型别名 | 162 处 / 19 实体 | 161 Numeric + 1 Date；normalize_value_type 写入时自动归一 |
| P7 实体内重名属性 | 54 对 / 11 实体 | 中英双键并存；保留英文键（类型更优者除外），删中文孪生 |
| P4 数值缺单位 | 23 处 / 6 实体 | 计数/年份 → 无量纲；面积 → km²；占比 → %；长度 → km |
| P8 “单位”拆分属性 | 15 处 / 8 实体 | 删拆分属性，单位落到对应数值属性上 |
| E2 有属性但 value_type=String | 13 实体 | 改为 Object |
| P9 抽取提示超 30 字 | 10 处 | 重写 ≤30 字（project_basic_info 1 处随 trash 消失） |
| E6 实体名带括号注记 | 4 实体 | 去括号，注记内容转别名 |
| 同名属性跨实体类型不一致 | 12 组 | 随 P7/类型统一消解 |
| 别名冲突 野生动物调查 | 1 | wildlife_transect_survey 整体并入后消失 |
| 属性集重合 ≥0.6 | engineering_basic_info ≡ project_basic_info | 保留前者（4 个任务引用），trash 后者（0 引用） |

## 关键决策

### 实体合并与回收（trash，共 19 个）

- `project_basic_info` → trash（0 引用）；`engineering_basic_info` 补 项目主体/建设性质 两属性（生命周期由服务年限覆盖，不重复加）。
- `wildlife_transect_survey` → trash；宿主 `wildlife_survey` 增补 bird_habitat；1 个任务引用显式改写。
- `protection_measures` → trash；宿主 `environmental_measures` 增补 efficiency；4 个任务引用 `protection_measures.category → environmental_measures.target_element` 显式改写。
- 16 个零属性标量实体 trash：residential, cultural_relic, water_resource, ecological_redline, pollutant, environmental_element, judgment, impact_behavior, prevention_measure, shallow_groundwater, engineering_params, project_main, construction_nature, lifecycle, mining_technology, linear_engineering。
- **保留** `regulation`、`spatial_boundary`（规范 §4 典型清单成员）。
- **保留** `protected_target` 与 `eco_protection_targets` 为两个实体（概念相近但属性集确实不同），后者分类改 sensitive_target；两者 type/target_type 均转 Enum（人居类/文物类/水资源类/生态红线类保护目标）。

### 引用安全策略

- 属性改名一律保留 name_cn → `remap_waiting_review_tasks` 现有机制按属性名把存量插槽引用自动归一为新键（含 `eco_protection_targets.保护目标名称` 这类中文后缀引用）。
- trash 实体头的任务插槽引用显式清理：有宿主映射的改写（wildlife_transect_survey→wildlife_survey、protection_measures.category→environmental_measures.target_element）；**实体级裸引用**（规范 §0：无点号引用=实体级实例，共约 340 处，遍布 6 个任务）清空置 `""`，trash 后触发一次 `remap_waiting_review_tasks` 按属性名/上下文自动回填，未回填的槽位保持未绑定态（评审时可手工映射）。
- 16 个零属性标量 trash 获规范文本直接背书：§1 反例点名「工程参数」「污染物」「环境要素」「判定结论」；「保护目标四类」属封闭取值应转为属性 Enum（已落到 protected_target.type / eco_protection_targets.target_type）。
- 删除属性的 name_cn 若在幸存属性上延续（如 最大温差 → max_temp_difference），引用自动归一；否则引用被清空后由名称/上下文自动回填（unit 拆分属性等无引用，无实际影响）。

### 分类对齐（规范 §4 口诀）

- natural_env ← climate, topography, hydrogeology, river, soil_erosion, vegetation_type, vegetation_quadrat_survey, remote_sensing_data
- env_quality ← air_quality_status, noise_quality, surface_water_quality, groundwater_quality, soil_environment, ecological_quality
- impact_assessment ← land_subsidence, landscape_ecology_assessment, biodiversity_assessment, ecological_integrity_assessment, eco_assessment_scope
- sensitive_target ← eco_protection_targets

### 语义近重名的处置口径

- P7 精确重名：全清（保英文键；中文键类型更优时反向保留并改名，如 soil_erosion 主要/次要侵蚀面积占比）。
- 指标完全相同的“数值”双份（socio_economy 第一/二/三产业增加值、固定资产投资、一般公共预算收入、人均生产总值、城镇居民人均可支配收入、矿种总数）：删中文键，英文名即幸存名，引用自动归一。
- 其余语义近重名（如 河流长度数值 vs 河长数值）**保留**，仅改名消除 P1；不做激进合并。

## Checklist

- [x] 审计产出违规清单（audit_entity_spec.py）
- [x] `docs/vibe/2026-11-15-entity-spec-governance.md`（本文）
- [x] `backend/scripts/governance/repair_entity_spec.py`：备份 → 逐实体更新 → 显式引用改写 → trash 前终检 → trash 19 实体 → 全量自动重绑定 → trash 后复核；默认 dry-run，`--apply` 落库
- [x] dry-run 通过后在 api 容器 `--apply` 执行
- [x] 复审 `audit_entity_spec.py` 归零（除 48 个历史悬空头）
- [x] UI 抽查（实体构建页，admin 本地登录）
- [ ] 提交 + 回移 pisuan-custom + wolf 台账

## 执行记录与修正（2026-11-16 落库）

- **执行顺序教训**：引用清理必须在逐实体更新**之后**。每次 `update_entity` 会触发
  `_remap_waiting_review_tasks`，其步骤 2 按静态表回填空槽——trash 实体未删除前
  `entity_index` 过滤不生效，先清掉的引用会被立刻填回（ping-pong）。最终顺序：
  更新（27）→ 清引用（74 ref / 5 任务）→ 终检 → trash（19）→ 重绑定（5 任务）→ 复核。
- **学习模板不在重映射覆盖面**：`_remap_waiting_review_tasks` 只处理待审任务，
  已学习模板插槽需显式改写——新增 `DomainFactoryRepository.rewrite_learned_template_slot_refs`，
  一次性归一 `groundwater_quality.最大值数值 → max_value_numeric`（211 个模板）。
- **别名冲突收尾**：`保护目标` 是 protected_target 的实体名，从 eco_protection_targets
  别名表移除（synonym_hits_other_name 归零）。
- **补充修正**：landscape_ecology_assessment 4 处、biodiversity_assessment 2 处、
  socio_economy 1 处数值属性补「无量纲」；environmental_quality_baseline.monitor_factors
  提示重写文本自身超 30 字，二次缩短为「例：PM10、SO2、pH、COD、氨氮」（20 字）。
- **误删自愈**：soil_erosion.secondary_erosion_area_ratio、topography.max_relative_height_diff
  曾因「删除键与改名目标同名」的幂等缺陷被误删，NEW_PROPS 按最终形态补回（UI 已确认在列）。
- **重跑幂等**：trash 步骤容忍已回收实体（ValueError 跳过 + TRASHED_OK 预检豁免）。

## 验收结果（2026-11-16 复审）

1. 复审输出：P1/P3/P4/P5/P6/P7/P8/P9/E1~E6、别名冲突、同名实体、属性集重合、跨实体类型不一致、
   中文引用头/后缀 **全部为 0**；unknown_heads = 48（历史遗留，另案）；
2. 引用面：任务插槽 4414 个非空 ref，trash 实体头残留 0；学习模板 211 个已归一；
3. trash 后 52 活跃 + 19 回收站；abdd99fa 任务 1638 槽位绑定 1605（33 个清理后未按名/上下文
   回填的槽位保持未绑定态，评审时可手工映射，符合设计）；
4. UI 抽查：六类计数 9+11+12+5+8+7=52、回收站 (19)、soil_erosion 面板
   （Object 类型、英文键 + 中文属性名 + 单位、自愈属性在列）均符合。
