# 写作数据集线上化运营路线图（writer datasets ops roadmap）

> 状态：需求决策记录（2026-10-18 brainstorming 产出）。**逐资产的 design spec 稍后逐个补齐**，本文只固化范围裁决与优先级，不含实现细节。

## 背景与现状

写作智能体（coal-eia-writer）运行时只读技能 `references/` 静态资产。资产分两代：

**第一代（线下 Claude 会话产物，静态文件，不可运营）——本文要 DB 化的七个**：

- `section_expectations/`（章节预期）
- `depth_targets/`（深度目标）
- `chapter_examples/`（章节范例）
- `terminology.md`（术语）
- `consistency_contracts.json`（一致性契约）
- `standards_index.json`（标准索引）
- `data_expectations.json`（数值护栏基线；其 `overrides/` 子目录已是词表服务物化的 DB 层，仅基线本体仍静态）

**第二代（系统上线后按「DB 运营唯一真相 → 显式导出物化回写 references/」模式建成）**：

- 写作范式（`eia_paradigm_drafts` + 查询/编辑页 + admin 导出回写 `references/paradigms/`）
- 数值护栏词表（`eia_lexicon_service`：DB 覆盖层 + 抑制名单 + 重扫差集）
- 语料元数据人工标注（`eia_meta_service`：标注页 → 导出物化）
- 公式 / 实体 / 阶段表单（各有编辑服务）

样例进料/加工链已上线（2026-10-18）：环评文件库 canonical md → 推送语料知识库 → 全库加工重编译（bank_compile --prune → 切片 / bank_index / corpus_meta 合并）。

## 决策记录

- 2026-10-18 用户裁决：七个第一代资产全部升级为**精细运营级**（范式层深度）：DB 唯一真相 + 结构化编辑页 + 校验 + admin 导出物化回写 `references/`。
- 逐资产拆子项目，每个独立走 spec → plan → 实施；writer 消费端（读文件）零改动。
- 「复垦方案不入环评域」同日裁决，样例库终态 23+新增；入库路径见文件库 changelog 条目。

## 七资产优先级（推荐顺位，可调整）

| 顺位 | 资产 | 形态 | DB 化要点 | 相对难度 |
|---|---|---|---|---|
| ① | data_expectations.json（数值护栏基线） | json | 基线条目入 DB；overrides 物化链现成可复用；需定与 eia_lexicon_service 的治理边界 | 低-中 |
| ② | section_expectations/（章节预期） | 分阶段 md | 每阶段一个编辑对象；结构化 schema 待定义 | 中 |
| ③ | consistency_contracts.json（一致性契约） | json | 跨节一致性规则 CRUD，schema 小 | 低 |
| ④ | terminology.md（术语表） | md 列表 | 术语 CRUD + 归一校验 | 低 |
| ⑤ | standards_index.json（标准索引） | json | 标准 CRUD + 引用校验 | 低 |
| ⑥ | depth_targets/（深度目标） | md/json | 需先定义深度度量口径 | 中 |
| ⑦ | chapter_examples/（章节范例） | md 内容库 | 「编辑」形态特殊（内容管理而非规则管理） | 高 |

## 每资产子项目的统一模式

1. DB 表（运营唯一真相）+ 迁移
2. service 层：校验 / 版本 / 导出纪律（参照 `eia_paradigm_service`：锚点校验、两键纪律、round-trip 字节纪律、preview 不写盘、漂移检测、回滚、空批拒绝）
3. 查询 + 编辑页（对齐词表/范式页 UI 惯例：骨架占位、分页、暗色主题）
4. admin 导出物化回写 `references/`（字节纪律，写前 0 命中扫描等既有红线）
5. 服务层单测 + 集成测试（`backend/test`，容器内跑；导出/回写类断言到字节级）

## 待定问题（逐资产 spec 时敲定）

- 各资产 schema 与校验规则细节
- 管线编排：重编译 / 词表重扫 / 标注导入 / 导出物化是否串成「样例入库 → 数据集更新」一键任务链，还是维持散装按钮
- LLM 语义加工（预期 / 深度 / 术语随新样本自动重生成）是否纳入线上管线，模型选型与质量验收方式
- data_expectations 与 eia_lexicon_service 治理边界（合并 vs 并列）
