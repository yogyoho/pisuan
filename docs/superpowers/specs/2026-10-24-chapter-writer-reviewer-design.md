# 分章节环评写作技能与独立合规校验技能 设计文档

- 日期：2026-10-24
- 状态：待用户审阅
- 决策来源：横城 B 测试对比评估（`docs/vibe/2026-10-24-writing-test-defects.md`）+ 设计讨论（2026-10-24 会话，四问收敛：双轨制/A2 全局包+逐章补充/独立 reviewer/一期文件卡片可见性）
- 关联：缺陷台账 #5/#6/#7/#11 的技能侧解法大部分落在本设计

## 1. 背景与证据

横城 B 测试（glm-5.3-flash，13 章 77 节全自动）暴露两类问题，构成本设计的动机：

**结构层**（缺陷台账）：分章深度偏斜（ch2 0.43/ch4 0.35 薄、ch8 2.88/ch10·ch13 2.45 厚）、管线元数据附录混入交付物、结论章 28 个待确认不收敛、表格量仅原文 53%。

**行文层**（本次新增量化证据，style_compare.py 实测 AI 稿 vs 原文）：

| 指标 | AI 稿 | 原文 | 差距 |
|---|---:|---:|---|
| 均句长 | 51 字 | 68 字 | -25%（碎句化，工程师复合数据长句缺失） |
| 数字/千字 | 16.7 | 20.6 | -19%（ch7 承载力仅一半：17.9 vs 39.5） |
| 表行/万字 | 42 | 73 | -42%（ch4 最重：21 vs 106） |
| 「见表/由表」正文引用 | 0.0/千字 | 0.3/千字 | 文表割裂——正文不引用自己的表格 |
| AI 腔（总体而言/值得注意/旨在…） | 30 处 | 6 处 | 5 倍（「总体而言」22 处） |
| 程式语堆叠（符合/满足/落实/达标） | 2.7/千字 | 1.4/千字 | 2 倍，官样空转风险 |

结论：文风问题可量化、可门禁、可审查，不必依赖主观判断。

## 2. 总体架构（三件套）

| 件 | 性质 | 职责 |
|---|---|---|
| `coal-eia-writer` | 现技能 | 按缺陷台账独立升级（另行排期）；终验接入 reviewer 全文审查 |
| `coal-eia-chapter-writer` | **新技能** | 逐章交互式写作管线：全局必备包 → 逐章循环 → 合并 → 全文审查 → 交付 |
| `coal-eia-reviewer` | **新技能** | 语义合规 + 行文质量审查规程，两级粒度（章级/全文），独立可用于人工/外部报告 |

共享资产：`eia-section-writer` 子代理、writer 包脚本（ingest/progress/formula_runner/build_output/consistency）、references（stages/depth_targets/data_expectations/samples_bank）。

用户价值：分章模式把横城实测的「10 runs/8 接力被迫停车」变成正常节奏（每章确认卡即合法停车点），且边写边看；reviewer 同时服务自产报告与外部报告审查。

## 3. coal-eia-chapter-writer 管线设计

### 3.1 步骤 0 · 恢复或开新

同 writer：`snapshot.py show --verify` + `progress.py next` 恢复现场；`state/mapping.json` 续跑不重绑。progress.json 章状态机扩展（见 §3.5）。

### 3.2 步骤 1 · 全局必备包收集 → 门 1（全局）

- `data_expectations.json` 扩展 `global_families` 分组：**跨 ≥2 章消费的数据族 + 冻结公式依赖族**（预计 4~5 族：规划方案/逐矿沉陷参数/标准确认/敏感目标；以依赖图实际计算为准，build 脚本从 stage JSON 派生，不手工拍）
- 开题首动作同 writer 纪律：结构真源声明 + 数据预告（预告改为「全局包 + 逐章路线图」两段式，用户可见）
- 门 1 只查全局包；交互纪律全套继承（单回合一卡、CSV 三步协议、示例值≠数据、ingest 唯一写者）

### 3.3 步骤 2 · 全局冻结 → 门 2

`formula_runner.py execute --chapters <跨章消费公式集>` 冻结跨章基础公式（规划产能/W_max 基参/水量平衡骨架）。门 2 rc=3 anomalies 逐条呈现确认，同 writer（发卡即停）。

### 3.4 步骤 3 · 逐章循环（N 按 stage 章序 1..13）

每章六步，全部落 progress.json 后才发确认卡：

- **3a 本章资料包**：该章专属族（仅本章消费的数据族）已备 → 跳过；缺 → 按现行交互纪律补收 → 本章增量门（只校本章族）→ **增量冻结** `formula_runner execute --chapters chN`（按 dependency_manifest 切片本章公式；仅本章消费的公式冻结，跨章公式已在全局冻结过的不动）
- **3b 节级派发**：eia-section-writer 子代理，波=本章全部 PENDING 节，在飞 ≤3，契约同 writer 4.1，**注入严格限定：本章数据族 + 本章冻结值 + 前章要点包（key_points 增量累积）+ 本章 samples_bank 风格基准切片**；禁注入全书上下文
- **3c 批量章门**：`progress.py gate`（含 §3.6 文风门）；FAIL 重派 ≤1 → BLOCKED（不中断后续章，协商留到该章确认卡）
- **3d 章级审查**：按 coal-eia-reviewer 规程出本章发现单（语义合规维度 A–C + 行文质量维度 D）
- **3e 呈现与确认**：`present_artifacts` 本章文件卡片 + 发现单卡片 + `ask_user_question` 确认卡（选项：**进入下一章 / 返工本章（附意见）/ 暂停**，另设快捷选项「后续章节自动确认直至全书合并」）——发卡即停
- **3f 返工回路**：用户意见 → 受影响节 mark DRAFTED 重派（原稿+意见注入）→ 3c/3d 重跑；每章返工 ≤2 次，超出走协商单（writer 4.5 三选项同款）

要点包机制变化：writer 的 wave1 终点大要点包改为**每章确认后增量更新** key_points.json（本节要点+本章冻结关键值）；投影章（ch13）最后写，天然拿到全部前章要点——分章模式的依赖图优势。

### 3.5 状态机与续跑

章状态：`PENDING → COLLECTING → COLLECTED → FROZEN → DRAFTED → VERIFIED → REVIEWED → CONFIRMED`，旁路 `BLOCKED`。CONFIRMED 为本技能新增（用户确认过门），恢复检测按最高到达态续跑（CONFIRMED 章跳过 3a–3e）。run 停车点表：同 writer 契约 + 每章确认卡为天然停车点。

### 3.6 文风门（chapgate 新增，可机械判定）

新建 `references/style_targets/<stage>.json`：**每章基准由 build 脚本从 samples_bank 切片实测生成**（首版以横城 004-2-2021-1 播种），字段：

```json
{
  "ch4": {"num_per_k_min": 12, "tbl_per_10k_min": 80, "tbl_per_10k_max": 160,
          "fig_table_ref_min": 1, "banned_phrases": ["总体而言", "值得注意", "至关重要", "旨在", "重要意义", "换言之"]}
}
```

门规则（进 `progress.py gate` 章级判定，与 L2 深度门同层）：
- **数字密度**：章正文数字/千字 ≥ 基准下限（基准=bank 实测 × 0.8，下同）
- **表格密度**：表行/万字 ∈ [下限, 上限]（上限治 ch13 型膨胀：结论章 bank 实测 0 表行 → 上限 10）
- **文表联动**：正文「由表/见表/详见表」引用次数 ≥ max(1, 主要表格数 × 0.5)
- **AI 腔禁用词**：命中 banned_phrases 即 FAIL（词表并入 bug-367 残留扫描词表机制）
- 均句长为软指标：偏离基准 ±40% 记 WARN 不 FAIL（句式是风格不是错误）

写作侧配套（eia-section-writer 契约升级，两技能共用）：注入本章风格基准切片；纪律新增「每个主要表格正文必须有引用与解读段」「工程师复合句式，数据从句串联，禁碎句堆叠」「禁 AI 腔过渡词」。

### 3.7 步骤 4–7 · 合并 → 全文审查 → 修复 → 交付

1. `build_output` 全书拼装 + 全门一次报齐（交付铁律同 writer：BUILD_READY/MANIFEST_READY 粘贴、禁手工拼装）
2. consistency 全书跑（XS1–XS18/EO1–EO3 跨章合约）
3. snapshot save
4. **全文审查**：reviewer 规程全书执行 → 发现单 `{报告名}-合规审查.md`
5. 修复裁决：FAIL 清单呈现用户，逐条决定修复（受影响章回 3b–3d）或豁免留痕
6. 交付双件：完整报告 `{项目名}-{阶段}-环境影响报告.md` + 审查发现单（QA 副产物独立文件）——**管线元数据/告警一律进发现单，禁入报告正文**（根治缺陷 #6）

## 4. coal-eia-reviewer 技能设计

### 4.1 输入输出

- 输入：报告 md（单章或全书路径）+ stage + 可选章号；模式参数 `--chapter chN` / `--full`
- 输出：`{报告名}-合规审查.md`——逐条发现：`[PASS/WARN/FAIL] 清单条目 | 章节定位 | 证据摘录 | 修复建议`

### 4.2 审查维度

| 维度 | 内容 | 判定方式 |
|---|---|---|
| A 法律法规层 | 引用正确性、程序完备性（compliance_checklist.md §1） | LLM 语义，逐条给证据 |
| B 技术导则层 | 评价等级/范围/模型选用/方法学符合性（§2，HJ 130-2019 等） | LLM 语义，逐条给证据 |
| C 标准规范层 | 标准号在册、限值引用、功能区划匹配（§3 + standards_index.json 在册校验可机械化先跑） | 机械+语义 |
| D 行文质量 | §3.6 文风指标全量化评分（均句长/数字密度/表密度/文表联动/AI 腔/程式语堆叠） + 段落逻辑抽查（章内上下文衔接、前后章呼应）；统计值复用章门已算指标，reviewer 侧重评分解读与逻辑抽查 | 统计脚本 + LLM 抽查 |

### 4.3 职责边界与纪律

- **只审不改**：产出发现单，不直接修改报告稿
- **FAIL 须有据**：每条 FAIL 必须引用清单条目 + 报告原文证据摘录；无证据禁判 FAIL
- 机械门（格式/深度/槽位/数值跨章一致/计算正确）不属 reviewer——chapgate+consistency+formula 冻结门已覆盖，不重复
- 独立可用性：可对人工/外部报告执行（无需写作管线在场），这是它的独立价值点

### 4.4 执行形态

技能=指令包。reviewer SKILL.md 定义审查规程、发现单格式、维度判定标准；写作技能 SKILL.md 在 3d/全文步骤写明「按 coal-eia-reviewer 规程对本章/全书执行审查」。预配置智能体挂载三技能（用户开题时以 @skill 选择完整/分章模式）。

## 5. 打包与资产复用

投影为整树复制（`copy_skill_tree_no_symlinks`），技能须自包含。**方案：repo 单一源 + 同步守卫**：

- 单一源 = `coal-eia-writer/scripts/` 与共用 references；`coal-eia-chapter-writer` 包内 scripts/+共用 references/ 由同步脚本生成（项目根 `scripts/sync_chapter_skill.py`，与 sync-upstream 同层，来源→目标单向覆盖）
- 单测 `test_chapter_skill_assets_sync`：断言两树共用资产字节一致，漂移即红（CI 兜底）
- reviewer 包最小化：SKILL.md + compliance_checklist.md 副本 + standards_index.json 副本（同源同步）
- 投影层零改动

## 6. 错误处理与边界

- 章门 FAIL：重派 ≤1 → BLOCKED，协商三选项（补数据/批准降档/[待确认] 收尾），不中断后续章
- 章级审查 FAIL：**不阻断推进**（发现单随确认卡呈现，用户在确认卡自行裁决带病推进或先修）
- 全文审查 FAIL：交付前用户逐条裁决
- 降档：`approve-downgrade` 语义同 writer，留痕
- Iron Law 全套继承：门 FAIL 唯一合法出路=补写节稿/申请降档；guidance 文本按缺陷 #3 改写（不暗示编辑 references/）
- 平台预算：bash 60 次/run、recursion_limit 1000；分章模式每章确认卡天然停车，预算压力低于 wave 模式

## 7. 测试与验收标准

| # | 验收项 | 核查方式 |
|---|---|---|
| 1 | ch2 过门后对话出现本章文件卡片 | 横城样本分章冒烟 |
| 2 | 门 1 只查全局包（≤5 族），逐章写 ch2 不要求 ch6 专属族 | progress/门输出断言 |
| 3 | 确认卡三选项+返工回路跑通（返工后章门重跑） | 冒烟 |
| 4 | 增量冻结只跑本章公式，跨章冻结值不被重算 | formula_runner scope 单测 |
| 5 | 文风门四项机械判定生效（含 banned_phrases 命中 FAIL） | 单测 + 冒烟 |
| 6 | 全书合并后产出可定位到章节的审查发现单 | 冒烟 |
| 7 | reviewer 独立模式对任意外部报告可用 | 用横城原文跑 --full 冒烟 |
| 8 | writer 现有测试零回归 | 全目录 pytest |
| 9 | 资产同步守卫测试在位且通过 | 单测 |

单测清单：formula_runner `--chapters` scope；progress.py CONFIRMED 态机；style_targets 生成脚本；文风门四规则；资产同步守卫；data_expectations global_families 派生。集成：横城 ch2 端到端冒烟（资料包→冻结→派发→章门→审查→确认卡）。

## 8. 范围外

- 文件库聚合/报告工作台 UI（二期，视一期文件卡片使用反馈决定）
- coal-eia-writer 缺陷台账升级（独立排期，本设计只约定 reviewer 接入点）
- 项目树交付路径（维持缓行）
- project_eia_underground 等未启用 stage（维持一期 planning_eia）

## 9. 风险与依赖

| 风险 | 缓解 |
|---|---|
| formula_runner 章级切片工程量（dependency_manifest 精度） | 先支持章粒度 scope，节粒度不做；切片不准时回退全量冻结（正确性优先，性能次之） |
| style_targets 基准仅 planning_eia 一种 stage 有 bank 支撑 | 基准生成脚本按 stage 惰性生成，缺 bank 的 stage 记 ABSENT 跳过文风门（如实汇报） |
| samples_bank 切片风格基准=单一样本（横城）过拟合 | bank 后续扩充时基准自动随 build 更新；门限取 0.8 宽松系数 |
| 逐章确认交互轮次多（13 轮） | 这正是用户要的体验（每章可见+确认）；确认卡提供「后续章节自动确认直至全书合并」快捷选项降低负担 |
