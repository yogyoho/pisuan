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

## 6. 信息架构

`/domain-factory/eia-data`（DomainFactory 环评域磁贴进入）：

- **数据总览**（本设计首批交付，`DatasetStatsPanel`）
- 数值护栏词表（一期）
- 元数据标注 / 标准备案 / 评测用例（二、三期逐个挂 tab）

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
