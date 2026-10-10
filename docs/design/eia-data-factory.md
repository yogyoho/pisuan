# 环评域数据工厂（eia-data-factory）设计

> 2026-10-09 定稿 · 范围裁决：B「环评域数据工厂」 · 评测裁决：C（数据质量面板 + 用例库 + 埋错召回）
> 关联：[eia-skill2rag.md](eia-skill2rag.md)（RAG 目标库设计）、coal-eia-writer 技能

## 1. 背景与范围

coal-eia-writer 技能经多批硬化后已沉淀约 20 个数据集（语料、事实槽位、词表、范式、标准库等），
分散在 `references/` 与运行态 `data/`/`state/` 中，缺少统一的加工、确认、质量管理入口。

本设计在 DomainFactory 下新建「环评域数据工厂」页面（`/domain-factory/eia-data`），

- **管**：人工层数据（候选确认、标注核实、用例管理）的 CRUD 与流水线触发
- **不管**：技能现有数据文件本身——它们是内置兜底真源，保持字节不变

## 2. 普查结论（数据集总表）

 stages/*.json 是全技能唯一结构真源（5 文件，schema_linter L1-L5 体检）；bank_index 等
为派生产物（bank_compile 七产物幂等确定性）；运行态 `data/`/`state/` 由 ingest.py 独占写、
在技能外，不属本页面管理范围。samples/（指纹池）与 samples_bank/slices/（带溯源案例库）
分工明确、非冗余。

## 3. 命名对照表（UI 显示名 ← 文件真源）

| UI 显示名 | 文件真源 | eia-skill2rag 概念 |
| --- | --- | --- |
| 案例语料库 | samples_bank/*/slices/ + samples/ + bank_index | §九 样例语料层 |
| 语料元数据 | samples_bank/corpus_meta.json | §九 第 1 层 |
| 元数据人工标注 | samples_bank/corpus_meta_annotations.json | §九 第 1 层（人工） |
| 附件图件清单 | samples_bank/attachment_checklist.json | §九 第 4 层 |
| 章节范文 | references/chapter_examples/ | 范文参照 |
| 章节事实槽位 | references/section_expectations/*.json | §九 第 2 层 |
| 数值护栏词表 | scripts 管线产物（curated_lexicon） | §五 W4-7 |
| 标准与限值库 | references/standards_index.json | 法规限值 |
| 计算公式参数 | references/formulas.json | 数值一致性 |
| 备料数据清单 | references/data_expectations.json | 备料检查 |
| 句式范式目录 | references/paradigms/forms_catalog.json | §九 第 3 层 |
| 写作范式 | references/paradigms/*.md + _roles.json | §九 第 3 层 |
| 一致性契约 | references/consistency_contracts.json | 数值一致性 |
| 篇幅深度基准 | references/depth_targets/ | 篇幅控制 |
| 术语库 | references/terminology.md | 术语一致性 |
| 合规清单 | references/compliance_checklist.md | 合规检查 |
| 样例实体注册表 | references/sample_entities/ | 实体脱敏 |
| 质询问题库 | 预留 | §九 第 5 层 |
| 深度标注片段库 | 预留 | §五 W6-9 |
| 评测用例集 | 预留 | 持续 golden set |
| 法规条款库 | 预留 | 条款问答/等级判定评测 |

UI 规则：显示名为主，文件名降级为详情技术标识（tooltip）。

## 4. 存储架构：DB 覆盖层 + 逐数据集开关 + builtin 兜底（方案乙修订版）

```
UI 确认/开关 → DB（运营唯一真相）
    → 显式「导出/物化」→ references/overrides/（gitignored 运行态）
        → 管线脚本读取：activation.enabled && 覆盖存在 → overlay 合并 builtin
          否则 → 纯 builtin（字节不变）
```

- 技能现有数据集**不动**，始终作为兜底；页面对各数据集有独立启停开关
- overrides 目录名与「section_expectations 开关控重写例外」为 §0 待裁决点，实施前再确认
- overlay provider 是 seam 抽象：v1 = 文件物化；将来 DB 直连 / MCP / API 参与脚本执行
  只换 provider，脚本保持纯 stdlib、零 DB 依赖、离线确定性

## 5. 三期路线

1. **一期（当前）**：统计总览页（已交付）→ 词表全栈（DB 表 + /eia/lexicon/* API +
   词表 tab + bank_compile v1.2 跨节聚合消费 + E2E 真实发布）
2. **二期**：元数据人工标注确认流 UI 化、standards_index 41 条核实流、评测用例库 CRUD、
   埋错质检召回跑批器
3. **三期**：报告入库流水线任务化（挂 domain-factory 任务流）、预留位落位、
   条款问答/等级判定评测接口（待部分二 RAG 链）

## 6. 信息架构与页面流转

`/domain-factory`（知识工厂）→ 环评域磁贴 → `/domain-factory/eia-data`（数据总览 hub）→
各管理子页（子路由，back-btn 回总览）：

```
/domain-factory
└── /eia-data                P0 数据总览（hub：指标带 + 分层构成 + 体检，磁贴进入各子页）
    ├── /eia-data/lexicon    P1 数值护栏词表（已交付 2026-10-09）
    ├── /eia-data/meta       P2 语料元数据标注（二期首件）
    ├── /eia-data/standards  P3 标准与限值库（二期后续）
    ├── /eia-data/eval       P4 评测用例集（二期：CRUD + 埋错召回跑批）
    └── /eia-data/ingest     P5 报告入库（三期：入库流水线任务化）
```

流转规则：总览页「数据分层构成」chip 与指标带是唯一入口层（可点击 chip + 待办数徽标）；
子页一律 `requiresAuth`，写操作按数据集分级（确认流 required_user / 物化导出与开关 admin）；
子页不互相跳转，回总览再流转（保持 hub-and-spoke，面包屑靠 back-btn）。

## 7. 统计总览页设计要点

- 立场：Data-Dense Dashboard——科技感来自数据密度与对齐，不来自装饰
- 禁 AI 味清单：渐变大色块 / 毛玻璃 / 发光边框 / emoji / 均质卡片阵 / 甜甜圈阵 /
  营销标题 / 彩色弥散阴影——一律不使用
- 视觉：base.css 变量（--main-600 靛蓝单色数据序列、--second-600 橙仅告警、
  --gray-200 发丝线、卡片 --main-0 底 6px 圆角无阴影）、`font-variant-numeric: tabular-nums`
- 布局：指标带 6 位 → 语料规模分布 + 省份分布 → 数据分层构成（五层价值模型）→
  词表候选三分类堆叠 + 事实槽位档位堆叠 → 数据质量体检（warn/info 两级发现项）
- 数据源：`GET /api/domain-factory/eia/stats` 只读聚合技能语料文件（mtime 指纹缓存，
  无 DB 依赖）；词表候选口径 = 比率/浓度型单位白名单 + n≥2 报告门槛 + 强清洗
  （与语料普查对齐：A 类 30 项逐 stage 一致，range_ready 6 项与人工裁决一致）

## 8. 功能页面明细（P0–P5）

| 页面 | 路由 | 核心功能 | 数据集 | 状态 |
| --- | --- | --- | --- | --- |
| P0 数据总览 | `/eia-data` | 指标带 6 位、语料规模/省份分布、五层分层构成（磁贴入口）、词表候选与槽位档位堆叠、质量体检（warn/info 发现项）；只读，mtime 指纹缓存 | 全部（只读聚合） | ✅ 已交付 |
| P1 数值护栏词表 | `/eia-data/lexicon` | 语料扫描候选导入（幂等 + 预置状态）、状态机确认流（入选/驳回/撤回）、值簇拆分（子口径携带裁决值集）、覆盖层导出物化 + 开关（admin）、提及明细 | 数值护栏词表（覆盖层） | ✅ 已交付 |
| P2 语料元数据标注 | `/eia-data/meta` | 31 份报告元数据总览（自动层只读：province/stage/standards_cited/scale_candidates）、人工标注确认流（year_hint / scale_mt_a 裁决，从候选簇快选或手输）、标注导入（存量人工层入库）+ 导出物化（admin）、覆盖率统计（x/31） | 语料元数据（自动层只读）+ 元数据人工标注（CRUD） | 🚧 二期首件 |
| P3 标准与限值库 | `/eia-data/standards` | 62 条标准索引浏览（tier 分档）、41 条 needs_verification 逐条核实流（核实/修正条目/备注）、核实进度统计 | 标准与限值库 | 二期后续 |
| P4 评测用例集 | `/eia-data/eval` | golden set 用例 CRUD（章节×输入×期望）、埋错质检召回跑批器、召回率报告；质询问题库/法规条款库预留位落此 | 评测用例集、质询问题库、法规条款库 | 二期 |
| P5 报告入库 | `/eia-data/ingest` | 报告入库流水线任务化（挂 domain-factory 任务流）、附件清单核对（入库前 gate）、深度标注片段库落位 | 附件图件清单（核对 gate）、深度标注片段库 | 三期 |

**完备性检查结论**（每个数据集必须落到四档操作级别之一，不留悬空）：

- **只读展示**（P0 聚合，无运营态）：章节范文、计算公式参数、备料数据清单、写作范式、
  一致性契约、术语库、合规清单、样例实体注册表
- **管线派生**（不设页，bank_compile/校准幂等重建）：bank_index、句式范式目录、
  篇幅深度基准、章节事实槽位（受 P1 覆盖层影响）
- **确认流 / CRUD**（DB 覆盖层 + 显式物化，方案乙）：数值护栏词表（P1）、语料元数据
  人工层（P2）、标准库核实（P3）、评测用例（P4）
- **流水线触发**：报告入库（P5）；案例语料库本体在 P0 只读、P5 入库时扩充

## 9. 数据集清单 × 管理页面对应关系（22 项）

| # | 数据集 | 文件真源 | 管理归属 | 操作级别 |
| --- | --- | --- | --- | --- |
| 1 | 案例语料库 | samples_bank/*/slices/ + samples/ + bank_index | P0 展示 / P5 入库扩充 | 只读 + 流水线 |
| 2 | 语料元数据（自动层） | samples_bank/corpus_meta.json | P2 | 只读（标注裁决的对照面） |
| 3 | 元数据人工标注 | samples_bank/corpus_meta_annotations.json | P2 | 确认流 CRUD + 导出物化 |
| 4 | 附件图件清单 | samples_bank/attachment_checklist.json | P5（入库核对 gate） | 流水线 |
| 5 | 章节范文 | references/chapter_examples/ | P0 | 只读 |
| 6 | 章节事实槽位 | references/section_expectations/*.json | 管线派生（受 P1 影响） | 派生产物 |
| 7 | 数值护栏词表 | references/overrides/curated_lexicon.json（gitignored） | **P1 ✅** | 确认流 + 导出物化 + 开关 |
| 8 | 标准与限值库 | references/standards_index.json | P3 | 确认流（核实） |
| 9 | 计算公式参数 | references/formulas.json | P0 | 只读 |
| 10 | 备料数据清单 | references/data_expectations.json | P0 | 只读 |
| 11 | 句式范式目录 | references/paradigms/forms_catalog.json | 管线派生 | 派生产物 |
| 12 | 写作范式 | references/paradigms/*.md + _roles.json | 无页（内置人工层，字节不变） | — |
| 13 | 一致性契约 | references/consistency_contracts.json | 无页（内置） | — |
| 14 | 篇幅深度基准 | references/depth_targets/ | 管线派生 | 派生产物 |
| 15 | 术语库 | references/terminology.md | 无页（内置） | — |
| 16 | 合规清单 | references/compliance_checklist.md | 无页（内置） | — |
| 17 | 样例实体注册表 | references/sample_entities/ | 无页（内置） | — |
| 18 | 质询问题库 | 预留 | P4 关联 | CRUD（落位后） |
| 19 | 深度标注片段库 | 预留 | P5 关联 | 流水线（落位后） |
| 20 | 评测用例集 | 预留 | **P4** | CRUD |
| 21 | 法规条款库 | 预留 | P4 / 三期评测接口 | CRUD（落位后） |
| 22 | 词表覆盖层物化 | overrides/curated_lexicon.json ← DB 词表 | P1 导出产物 | 运行态（开关删文件即回 builtin） |
