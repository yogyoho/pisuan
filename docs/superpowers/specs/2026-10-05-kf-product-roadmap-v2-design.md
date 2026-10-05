# 知识工厂产物路线 v2 设计（条件化模板三层形态 + scope×region 事实维度）

> 日期：2026-10-05 ｜ 分支 pisuan-custom
> 状态：设计已获方向性批准（roadmap v2 + 措施两步走 + 6 维条件词表 + 三层模板形态），待用户审阅本 spec
> 证据底座：38 份样例报告全量章树实测（`.wolf/corpus-census/`），非推测

---

## 0. 本 spec 固化的决策记录

| # | 决策 | 状态 |
|---|---|---|
| AD-1 | 模板产物线（learned_templates 叙述/散文泛化产物）冻结，进入观察期；工厂重定位为「文档结构提取器 + 区域事实仓库」 | 已批准（2026-10-04） |
| AD-2 | 措施库两步走（先入库后联通） | 已批准（2026-10-04） |
| AD-3 | 条件词表 6 维度（§3.2） | 已确认（2026-10-05） |
| AD-4 | 模板产物形态 = 骨架 + 变体规则 + 每章配置 三层；固化模板仅为渲染导出物 | 已确认（2026-10-05） |
| AD-5 | P1-0/P1-2/P1-1a 提前排期（统一泛化双产物、废弃叙述路径、结构化输出通道） | 已批准（2026-10-04） |
| AD-6 | scope×region 维度进工厂（§4） | 已批准（roadmap v2） |
| AD-7 | 消费通道三期（§5） | 已批准（roadmap v2） |
| AD-8 | Q4 整合的 8 项拍板（PR-1 等） | 推荐已列（§9），随本 spec 一并确认 |

## 1. 背景与定位

**一句人话**：以前工厂想"从旧报告里学出模板卖给写手"，实测发现散文模板没人要（写手 v2 自带更强的领域先验）；但旧报告里真正值钱的是**骨架规律、区域事实、项目事实、措施库**。本 spec 把工厂的产物线转向这四样。

三条不变原则：
1. **工厂产物不进 v2 运行时热路径**——只走生成期冷替换链（PR-1）
2. **D2 死产出停机**——每个新产物必须指名消费者；模板线若复测取用仍为 0 则同样停机
3. **测量先于优化**——产物取用率埋点先行（依赖 bug-353 修复）

## 2. 语料实测基础

41 份样例 docx（`C:\项目管理\样例文件`）全量普查，产物存 `.wolf/corpus-census/`：

| 文件 | 内容 |
|---|---|
| `census.json` | 逐份机械指标（大小/段落/表格数/标题样本）；含 3 条修正记录（bug-355） |
| `chapters.json` | **38 份完整章树**（≥8 章）+ 1 简本 + 1 部分骨架（淖毛湖报批版） |
| `labels.json` | 逐份条件标签（族/矿型/修编提示） |

**五族骨架**（实测分布）：

| 族 | 份数 | 章数 | 骨架要点 |
|---|---|---|---|
| 规划环评 | 18 | 13±2 | 方案分析→区域→回顾→识别→预测→承载力→论证→减缓→（清洁生产/公参/管理监测轮转）→结论；4 种变体 |
| 项目环评 | 13 | 17-19 | 工程分析→政策符合性→区域→【沉陷(井工)/爆破(露天)】→要素章→选址→风险→清洁生产→管理监测→损益→结论 |
| 后评价 | 2 | 16-17 | 沿用项目环评（露天）骨架 + 后评价口径章名 |
| 跟踪评价 | 1 | 11 | 独有骨架（落实情况→演变趋势→对比评估→后续措施） |
| 复垦方案 | 3 | 9 | 三份同构；v1 不进模板产品（挂账，见 §10） |

**关键规律**（规则表的数据来源）：
- 井工 7/7 有「地表沉陷预测」章、0/7 有爆破章；露天 6/6 反之——**系统性分岔，全量证实**
- 修编报告 18/18 必含回顾性评价章
- 新导则口径（+三线一单及空间管控、+不确定性分析）已在五间房（章级）、淖毛湖报批版（节级）出现，正在扩散
- 要素章顺序（大气↔地表水、固废↔土壤、选址/清洁生产位置）存在 5-6 种轮转——判定为院家风，**不进规则**（§3.7）
- 区域敏感性产生专章/专节（淖毛湖 6.10 胡杨林沙漠公园、6.11 乡镇影响；纳林希里 1.5.x 敏感目标清单）

**普查工程教训**（进 ETL 解析器健壮性，bug-355）：WPS 病态 docx（.rels 引用 NULL 部件）会令 python-docx 崩溃，需 zip 级手术；`UniDocSa` 文件头 = WPS 私有格式真损坏；解析失败必须记 error 而非静默零值。

## 3. 产品一：条件化报告模板（三层形态）

### 3.1 为什么是三层而不是固化 N 份（决策 AD-4 依据）

- 组合空间：6 维条件组合 30-50 种，语料仅覆盖 ~12 种；固化模板在未见组合上失灵，退回手工——等于没有产品
- 导则修订：三层改 1 处重渲染；固化改 N 份必漂移
- 区域敏感性是 per-project 的，只有配置层能表达
- **决定性证据**：v2 技能 `references/stages/` 现存 5 份手写 stage JSON（planning_eia / project_eia_openpit / project_eia_underground / post_eia / tracking_eia）——正是固化形态及其维护之苦。三层渲染产物**直接兼容该格式**，消费者现成
- 固化模板保留为**渲染导出物**（渲染缓存/交付存档），不是真相源

### 3.2 条件词表（6 维，AD-3）

| # | 维度 | 键 | 取值 | 生效范围 |
|---|---|---|---|---|
| D1 | 报告类型 | `report_family` | planning_eia / project_eia / post_eia / tracking_eia | 全局必填 |
| D2 | 矿型 | `mine_type` | underground / openpit | 仅 project_eia |
| D3 | 导则口径 | `guideline_version` | legacy / revised2019（+三线一单、不确定性） | planning_eia |
| D4 | 评价轮次 | `round` | first / revision（post/tracking 由 D1 承载） | planning_eia |
| D5 | 区域敏感性 | `sensitive_targets` | 自由标签列表（胡杨林沙漠公园/乡镇/保护区/水源地…） | 全局 |
| D6 | 政策要求 | `policy_flags` | 布尔开关集（如 `total_control`） | 全局 |

### 3.3 三层数据模型

源文件 = repo 内版本化 JSON 资产（`backend/templates/coal_mining/report_skeletons/`），**零新表零后端改动**（对齐最小化 yuxi 核心改动约束）；工厂侧登记（outlines/learned_templates 关联）挂 P2。

```jsonc
// layer-1 骨架：<family>.json —— 5 份
{
  "family": "planning_eia",
  "canonical_order": ["总则", "规划方案分析", "区域概况", "回顾评价", "识别与指标",
    "预测与评价", "承载力", "综合论证", "减缓措施", "清洁生产", "公参", "管理监测", "结论"],
  "chapters": { "总则": { "slot_id": "PLN-01", "hj463_ref": "A.1" }, ... }
}

// layer-2 变体规则：rules.json —— 1 份，确定性 if-then
{ "rules": [
  { "id": "R1", "when": {"report_family": "project_eia", "mine_type": "underground"},
    "add": ["沉陷预测"], "remove": ["爆破影响"], "evidence": "井工 7/7" },
  { "id": "R2", "when": {"report_family": "project_eia", "mine_type": "openpit"},
    "add": ["爆破影响"], "evidence": "露天 6/6" },
  { "id": "R3", "when": {"report_family": "planning_eia", "guideline_version": "revised2019"},
    "add": ["三线一单", "不确定性"], "evidence": "五间房章级;淖毛湖报批版节级" },
  { "id": "R4", "when": {"report_family": "planning_eia", "round": "revision"},
    "require": ["回顾评价"], "evidence": "修编 18/18" },
  { "id": "R5", "when": {"sensitive_targets": "*"},
    "add_section_under": {"预测与评价": "对{sensitive_target}影响分析"}, "evidence": "淖毛湖 6.10/6.11" },
  { "id": "R6", "when": {"policy_flags": "total_control"},
    "add": ["总量控制"], "evidence": "郭家台 ch16" },
  { "id": "R8", "when": {"report_family": "post_eia"},
    "base": "project_eia/openpit", "rename_suffix": "后评价", "add": ["措施优化调整"], "evidence": "白音华 2/2" },
  { "id": "R9", "when": {"report_family": "tracking_eia"},
    "base": "tracking_eia_standalone", "evidence": "淖毛湖跟踪 11 章" }
] }

// layer-3 每章配置：<family>-chapters.json —— 按章深度/表格/节菜单
{ "沉陷预测": { "depth": "deep", "tables": ["地表沉陷敏感目标一览表", "保护煤柱留设表", "预测参数表"],
    "sections": ["预测模型", "预测参数", "预测方案", "移动变形预测", "影响分析", "岩移观测计划"] }, ... }
```

**章序轮转的处置**：canonical_order 取语料多数派（规划环评 A 序 10/15；项目环评要素章取主流序）。院家风差异不进规则、不做配置（§3.7）。

### 3.4 渲染器

- 输入：6 维条件 JSON + 三层源文件；输出：章节清单（stage JSON 兼容格式）+ 人类可读骨架文档
- 确定性纯函数，无 LLM 调用，预估 ~100 行 Python（`backend/scripts/render_report_skeletons.py`，属构建/交付脚本而非运行时组件）
- 规则命中全部留痕（`applied_rules: [R1,R4,...]`）——模板可解释，工程师可审计"这章为什么在"

### 3.5 消费通道

1. **主通道（v1）**：渲染产物 → 人工核实 → v2 技能 `references/stages/*.json` 版本升级（PR-1 冷替换链，含硬编码排除清单）。运行期不热替换。
2. **工厂侧登记（P2）**：渲染骨架可选登记进 `DomainFactoryOutline`，使工厂管理页可见模板产品线；不做写作时读取。

### 3.6 验收标准（语料适配度测试）

1. 半自动标注：38 份语料 → 6 维条件（文件名规则 + 人工校对，标注结果存 `.wolf/corpus-census/conditions.json`）
2. 渲染器对每份语料出骨架，与 `chapters.json` 实测章树对比：
   - **槽位集合完全匹配 ≥ 36/38**
   - **章序完全一致 ≥ 30/38**（轮转差异按已声明院家风豁免后计）
   - 不匹配项逐份出差异单：改规则，或标记院家风豁免，二选一，禁止静默忽略
3. 渲染产物通过现有 v2 stage JSON 的消费方冒烟（stage 清单加载 + 章节数校验）

### 3.7 非目标

- 不复刻各设计院的章序家风（内容等价、顺序不同的一律归一）
- 不覆盖复垦方案族（v1 挂账，§10）
- 不做运行时热替换（PR-1 三重闸不动摇）
- 不用 LLM 生成骨架（规则确定性优先；LLM 只在 §6 的泛化批次里干自己该干的）

## 4. 产品二：scope×region 事实维度（AD-6）

### 4.1 数据模型变更

| 对象 | 变更 |
|---|---|
| `DomainFactoryTask` | +`project_name`、`region_label`、`region_key`（region_key 为规范化行政区/流域键） |
| `DomainFactoryLearnedTemplate` | +`scope` 列（universal / regional / project）；**不进唯一约束** |
| 新表 `domain_factory_regional_facts` | `fact_type`(monitoring/sensitive_target/measure/constraint)、`region_key`、`content`、`source_task_id`、`status`(draft/confirmed/retired)、`year`、`source_ref` |
| 先例 | `LegalReference.scope`（graph_builder.py:585-599，national/…）已验证 scope 字段模式可行 |

### 4.2 归属判定（三级，riding 已批准批次）

- **L1 规则**： revive 已死的 classify_tags 通道做确定性预归类（矿区名/行政区词表/监测口径词表）
- **L2 LLM**： 搭 P1-0 统一泛化便车，同一次调用附带产出 scope/region 建议（**零新增 LLM 调用**）；默认 project（最保守）
- **L3 人工**： WAITING_REVIEW 界面确认，可批量改判

### 4.3 聚合与泄漏处置

- 聚合取**最窄 scope**（min-permissive）：universal 产物必须全部证据 regional/project 时降级，反向不自动升级
- 泄漏处置 = **批量退役**（status→retired），不自动改正文；写手侧发现泄漏走人工通道
- B 类区域事实（监测数据/敏感目标/措施/约束，见取材地图）是 `regional_facts` 的内容来源；C 类项目事实（矿山实体/自家工程数）**禁止**进 universal/regional

## 5. 消费通道三期（AD-7）

| 期 | 通道 | 改动 |
|---|---|---|
| 现在 | 一地区一 KB（按 region_key 分库，查询侧天然隔离） | 零后端代码，运营规范 |
| P1-1b | `get_slot_registry` 独立新工具，接口从第一天带 `scope/region/fact_type` | 后端新增只读工具 |
| P2 | 导出端点 → 分区域参考 JSON → PR-1 冷替换链进 v2 | 后端导出 + 人工核实闸 |

## 6. 同批落地：P1-0 / P1-2 / P1-1a（AD-5）

- **P1-0 统一泛化双产物**：散文段落泛化一次调用产出（散文泛化文本 + scope/region 建议），废除参数/叙述双轨
- **P1-2 废弃叙述路径**：删除 `_extract_narrative_summaries`（service:3237-3326，读泛化回声字段的死逻辑，bug-336）；`para["template"]` 写入路径（service:896）随之移除
- **P1-1a 结构化输出通道**：泛化 LLM 走结构化输出 + 闭式类型词表
- **分类器收敛**：`classify_paragraphs`（service:1601）7 路规则收敛为 5 结构类 + 散文回退；叙述/参数区分彻底废弃（2026-10-02 Q1 决议的延伸结论）
- 覆盖率统计口径（service:922 分母）随产物定义同步修订

## 7. 缺陷前置修复（硬门槛）

| bug | 内容 | 位置 | 状态 |
|---|---|---|---|
| bug-354 | 校验链读 `para["type"]`，实际字段是 `classify_type` → L1/L2 校验全部空转 | pre_commit_validator.py:32 | **Phase 0 必修** |
| bug-353 | service:648 调用不存在的 `_increment_learned_template_match_counts` 被静默吞 → match_count 永不增量 | domain_factory_service.py:648 | **Phase 0 必修**（取用率测量前置） |
| bug-355 | WPS 病态 docx（NULL 关系/UniDocSa）致解析崩溃或静默零值 | 普查脚本；同型风险在 ETL 解析入口 | ETL 解析器加防护 + 失败显式告警 |

## 8. 对抗验证修正（roadmap 工作流 4 项，已并入上文）

1. 样例实体是 **24 矿**不是 22（_index.json samples=24）
2. manager.py 上游共享 → scope 列等模型变更走 **additive 白名单**，改前 git 判定出处，附先例提交
3. eia-section-writer 无 query_kb（沙箱 DB-only）→ 区域数据由**编排者主路径**取数并注入派工契约；SKILL.md 豁免需加红线 6（区域数值只经 ingest 表单→{{TABLE}} 渲染）+ source 枚举映射（regional→analog_mine+analog_source）
4. 措施消费面向 = ch9/ch10（非 7.x）；payload 字段名 zoning

## 9. Q4 整合 8 项拍板（随本 spec 一并确认）

| # | 决策点 | 推荐 |
|---|---|---|
| PR-1 | references 生成期冷替换口子 | **开**（三重闸：版本升级链+人工核实+排除清单；本 spec §3.5 即其第一用户） |
| M11 | gate1_code_checks 接线 | 接线（standards_check.py，warn 级进门 1） |
| M12 | 实体泄漏机械门 | 新建（scripts 原则破例显式记录） |
| C5 接口 | 注册表读接口 | 独立新工具 get_slot_registry |
| 埋点 | 取用率测量 | 工具内自动埋点（tools.py 上游共享层先 git 判定出处） |
| M9 时点 | v1 孤儿删除 | 押后至 V7-V9 完成 |
| R4 | seed_gen 跨栈通道 | README 明确人工通道 + 清理残留 |
| cw_k | formula_runner 缺参静默 0 | 显式破例记录 |

## 10. 风险与开放问题

| # | 事项 | 处置 |
|---|---|---|
| O1 | ~~HJ 463/130 入库形态~~ **已决（2026-10-05）**：两者均存于「环评标准规范库」`kb_9ks49hyvfj`——规范本体独立成库的预设成立。一地区一KB 之外，KB 角色分三类：规范库（全局共享，不分区）/ 样例库（可按区域分）/ 写手产物库 | 已关闭；分库规范写进 W4 运营文档 |
| O2 | 每章配置层 v1 只配高频差异章；**全量表单清单需先跑「表格→章节归位」统计**（census 未做） | P2 数据作业 |
| O3 | 横城 md 表体全失（171 表只剩表题）——docx 原件已定位（报批版 192 表） | 回源重转，P1 作业 |
| O4 | 3 份空/坏文件（塔然高勒真损坏） | 塔然高勒弃用；语料池按 38 份计 |
| O5 | 复垦方案族（3 份 9 章同构）不在 v2 写手范围 | 挂账；有消费需求时作为第 6 骨架接入 |
| O6 | 模板线取用率若持续为 0 | D2 停机原则同样适用于本产品线 |

## 11. 阶段计划

| 窗口 | 内容 | 验证 |
|---|---|---|
| W0 | bug-353/354 修复 + 取用率埋点 | 单测 + 埋点落表 |
| W1 | P1-0/P1-2/P1-1a 批次 + 分类器收敛 | 单测（分类器 5+1 用例）+ 横城样例 ETL 重跑对比 |
| W2 | 三层源文件 v1 + 渲染器 + 语料适配度测试 | §3.6 验收（≥36/38、≥30/38） |
| W3 | scope×region 落库（§4，additive 白名单流程） | 迁移脚本 + L1/L2 归属抽检 |
| W4 | 消费通道：一地区一KB 规范 + get_slot_registry + 导出端点 | 接口测试 + 冷替换演练 |

## 12. 关联文档与数据

- 语料证据：`.wolf/corpus-census/{census,chapters,labels}.json`
- 会话记录：`docs/vibe/2026-10-04-kf-eia-writer-review-and-integration.md`
- 前序设计：`docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md`、`docs/vibe/2026-10-02-etl-redesign-requirements.md`
- 规范本体：HJ 463-2009 附录 A/B（`.wolf/hj463_extract.md`）、HJ 130-2019 附录 C/E/F（`.wolf/hj130_extract.md`）
- 工作流产物：roadmap `tasks/wtp5kvzey.output`、取材地图 `tasks/wg1rj4gim.output`
- 实现差距审计（2026-10-05，基线 e227a57a）：[2026-10-05-kf-product-roadmap-v2-gap-audit.md](2026-10-05-kf-product-roadmap-v2-gap-audit.md)——W0 落地/W1-W4 未动逐项实证 + 排期依赖图
