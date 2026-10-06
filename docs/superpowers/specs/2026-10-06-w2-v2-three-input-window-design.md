# W2 v2 三条输入小窗 设计

> **日期**: 2026-10-06 ｜ **状态**: 已评审（Q1–Q4 四分叉经用户裁决）
> **依据**: W2 终审挂账 v2 输入三条（[2026-10-05-w2-report-skeleton-three-layer.md](../plans/2026-10-05-w2-report-skeleton-three-layer.md) 执行记录/终审记录）；roadmap v2 spec §3
> **前窗**: W2 条件化模板三层形态（3352d139 终审 READY）

## 1. 背景与目标

W2 终审挂账三条 v2 输入：

1. **order 自然值 14/35**：21 份院家风章序分歧，按文件豁免兜底（挂账④）
2. **渲染顶层缺 stage/std_ref**：seed_gen 消费渲染产物时显示名空、模板名退化（`.get` 兜底，非报错级）
3. **R2 爆破章插入位语义缺失**：add 规则 = dict 追加 → 爆破排「结论与建议」之后，反报告结构

**目标**：三条全解——渲染器拿回插入位与真源元数据，适配度判定层拿回章序容差（豁免从按文件 21 份收敛到按章白名单）。

**本窗 checklist（简要）**：
- [ ] 渲染器锚点机制 + 3 个锚点词条
- [ ] 渲染顶层 stage/stage_id/std_ref 真源化
- [ ] 6 份存档重渲 + seed_gen 冒烟复跑
- [ ] fit order 判定升级 + 位移白名单 + 豁免收敛 ≤2 份
- [ ] changelog / 勾账 / 终审

## 2. 范围

**In**：`backend/scripts/render_report_skeletons.py`、`backend/templates/coal_mining/report_skeletons/*.json`（l1 锚点词条 + rules 注释）、`rendered/` 6 份存档重渲、`backend/test/unit/test_report_skeleton_fit.py`、`backend/test/data/corpus_census/order_whitelist.json`（新）、`backend/test/data/corpus_census/conditions.json`（豁免收缩）。

**Out**：seed_gen 本体（`.get` 兜底保留给 legacy stage）、渲染产物强制重渲机制（终审⑤另立）、conditions 入库生产路径（终审①另立）、layer-3 sections 消费、消费通道代码（W4）、复垦族（O5）。

**不变量**：`backend/package/`、`backend/server/` 零 diff（延续 W2）；slot_id 不重编号（depth_targets 键对齐）；stage JSON 单一真源（D12），渲染产物保持派生工件；阈值断言只升不降。

## 3. 普查数据（设计依据）

普查工具（`.wolf/corpus-census/classify_order_divergence.py` + 邻居扩展，只读，复用 fit 测试模块 `_norm`/`_alias_index`/`_match_file` 保证口径逐位一致）。

### 3.1 序差判定分布（35 份全量）

| 判定 | 份数 | 说明 |
|---|---|---|
| natural | 14 | 精确序全等 |
| **swap-pure** | **0** | **无任何一份是相邻互换——「互换对白名单」前提被数据否定** |
| move-pure | 16 | 单章整体位移 |
| other | 5 | 全为露天件：R2 替换（固废↔爆破）+ 位移复合 |

21 份豁免 = 16 move + 5 other，逐份判定与豁免登记完全对账。

### 3.2 锚点证据（语料 hit 邻居，∞=语料文件数）

- **爆破环境影响评价**（project，5 份）：4/5 位于 `固废→环境风险` 空档（2x `土壤→[爆破]→风险`、2x `固废→[爆破]→风险`）→ **锚 = insert_after 固体废物环境影响评价**
- **三线一单及空间管控**（planning，n=1 五间房）：`论证→[三线一单]→结论` → **锚 = insert_after 规划方案综合论证及优化调整建议**
- **不确定性分析**（planning，n=1 五间房）：`环管→[不确定性]→论证` → **锚 = insert_after 环境管理、监测计划与跟踪评价**（n=1 出处标注，见 §7 风险）

### 3.3 位移词条证据（章 → 语料前置章分布）

| 章（族） | canonical 前置 | 语料前置分布 |
|---|---|---|
| 环管（planning） | 减缓措施 | 论证 10x、公众参与 6x、清洁生产 1x、不确定性 1x |
| 识别与指标（planning） | 回顾性评价 | 区域概况 3x（+canonical 14x） |
| 资源综合利用（project） | 总量控制 | 环管 5x、风险 6x、损益 1x、土壤 1x、选址 1x |
| 环境空气（project） | 地表水 | 地下水 6x（+canonical 8x） |
| 固废（project） | 声 | 土壤 6x、地表水 1x（+canonical 7x） |
| 总量控制（project） | 环管 | 选址 2x |
| 地表水（project） | 地下水 | 空气 5x |
| 损益（project） | 环管 | 资源 5x、选址 1x |
| 清洁生产（planning） | 环管 | 减缓措施 2x |
| 爆破（project） | （锚后=固废） | 土壤 2x |

## 4. 设计

### 4.1 渲染器锚点机制

**数据**：l1 `optional_chapters` 词条新增可选字段 `"insert_after": "<canonical 章题>"`。

**机制**：规则处理（add/remove/require，现行为不变）全部完成后，**后置重排 pass**——对当前在场且 l1 词条声明了 `insert_after` 的章，从原位摘出、重插到锚章之后（多章同锚保持相对序稳定；锚章不在场 → `KeyError` fail loud，延续禁静默；无锚词条维持现位）。slot_id 不重编号。

**词条落账**：§3.2 三个锚写入 `project_eia.json` / `planning_eia.json` 的 optional_chapters；`rules.json` R2/R3 的 evidence 字段补锚点出处注记。

**效果**：openpit 渲染中爆破从「结论后」回到报告中段 固废→爆破→风险 位；revised2019 渲染中 R3 两章从尾部回到语料实证位。

### 4.2 渲染顶层 stage/std_ref

- **stage_id 推导**：`family`；project 族拼 `f"{family}_{mine_type}"`。推导失败（stage 文件不存在 / project 缺 mine_type）→ fail loud
- **顶层字段**：`stage` / `stage_id` / `std_ref` 从 `references/stages/{stage_id}.json` **逐字拷贝**；替换现 `"stage_id": family` 冒充值
- **消费方**：seed_gen 零改动——渲染产物成为 seed_gen 合法输入且元数据不再退化（SEED_READY 显示名/模板名非空）
- 规划两变体（first/revised2019）共享 `planning_eia` stage 元数据；变体身份在 `generated_from.conditions`，不进顶层

### 4.3 fit order 判定升级 + 位移白名单

**数据**：`backend/test/data/corpus_census/order_whitelist.json`（新 fixture，tracked）：

```json
{
  "moves": [
    {"chapter": "环境管理、监测计划与跟踪评价", "family": "planning_eia",
     "after": ["规划方案综合论证及优化调整建议", "公众参与",
               "矿区清洁生产与循环经济分析", "不确定性分析"],
     "evidence": "论证后 10x/公众参与后 6x/清洁生产后 1x（普查 2026-10-06）"}
  ]
}
```

**判定算法**（替换现 `expected == hit_seq or ex.get("order")`）：

1. 预备条件：`multiset(expected) == multiset(hit_seq)`（不满足直接 fail，属槽位异常）
2. 精确全等 → pass
3. 否则 DFS：状态 = 当前序列；每步取一个 mover 章（该文件 family 的白名单章），从序列摘出、重插到某个 `after` 前置章（在场者）之后；目标 `hit_seq` 精确到达 → pass。visited 集去重；mover ≤ 每族 ~10，深度有界，代价可忽略
4. 不达 → 现差异单路径（豁免登记或改规则，二选一，禁静默）

白名单初值 = §3.3 表（10 条）；**T4 锚点落地后复测普查定稿**——锚点改变 expected 序，部分词条可能收缩、5 份 other 预期分解为纯位移。

### 4.4 存档重渲与冒烟

6 份存档重渲（预期变化：project_openpit 爆破位、planning_revised2019 R3 两章位、全部顶层元数据；其余 4 份仅顶层元数据）。连续两渲 **byte-identical** 校验；seed_gen 冒烟复跑同 W2 Task5 协议（4 完整 + 2 结构断言）；核对 6 份 stage_id 推导值与 `depth_targets/{stage_id}.json` 文件名对齐。

## 5. 执行序

| 任务 | 内容 | 验证 |
|---|---|---|
| T1 | 锚点机制 + l1 词条 + rules 注记 | 渲染单测：爆破/三线一单/不确定性落锚位；锚缺失 fail loud；无锚向后兼容 |
| T2 | stage/std_ref 顶层化 + stage_id 推导 | 单测：6 条件组合推导正确、字段逐字、缺文件 fail loud |
| T3 | 重渲 6 存档 + 冒烟复跑 | 双渲 byte-identical；4+2 冒烟；SEED_READY 显示名非空；depth_targets 文件名对齐 |
| T4 | 白名单 fixture + 判定升级 + 复测收敛 | 复测普查 35 份；fit 全绿（宿主 --noconftest + 容器双道）；豁免 ≤2 |
| T5 | changelog + 勾账 + 终审 | fresh-eyes 独立复验 |

T1/T2 同文件不同侧面，顺序执行避免渲染器冲突；T4 依赖 T1（expected 序变化）与 T3 无依赖可并行。

## 6. 验收标准（DoD）

1. openpit 存档中爆破位于 固废→爆破→风险 位（非结论后）；revised2019 存档 R3 两章位于锚位
2. SEED_READY 显示名/模板名非空——渲染产物喂 seed_gen 元数据不再退化
3. fit order：natural + 白名单过 **≥33/35**，文件级豁免 **≤2 份**且逐份差异单出处；阈值断言维持 ≥28
4. 白名单词条 100% 内联普查出处（章×前置分布×份数）
5. 双渲 byte-identical；4+2 冒烟全过
6. `backend/package/`、`backend/server/` 零 diff；禁碰 7 文件零卷入；提交中文 Conventional + 明确 `git add`

## 7. 风险与挂账对照

- **R3 锚 n=1**（五间房独苗，承终审②）：锚值按现语料实证落账；未来新增 revised2019 语料若相左，按同机制补词条/改锚，不出新代码
- **白名单 ↔ 新语料**：新增语料 order 不过时必须普查→补词条（带出处）或豁免（差异单），机制上被 fit 断言强制，无静默路径
- **挂账对照**：④ 章序白名单 → **本窗解决**；① conditions 生产路径、② revised2019 n=1、③ openpit 管线文档、⑤ 渲染强制重渲 → 不在本窗（⑤ 因重渲暂得刷新，机制仍缺）
- **判定层边界**：白名单只作用于 fit 测试，渲染器/seed_gen/模板消费链零感知

## 8. 裁决记录

| # | 分叉 | 裁决 | 理由 |
|---|---|---|---|
| Q1 | 白名单作用面 | 仅测试判定层 | 互换是语料评估容差，非骨架属性；canonical 序保持唯一真源 |
| Q2 | 语义先定还是普查先定 | 普查先行 | 挂账原文即「评估」；数据到手锁语义，避免拍脑袋 |
| Q3 | add 插入位语义 | 锚点声明（词汇属性） | R2/R3 统一覆盖；位序显式可审计；与白名单同词汇形成对称 |
| Q4 | 白名单形态 | 位移区间（允许前置章） | 普查实证 swap-pure=0、move 16 份——互换对概念被数据否定 |
