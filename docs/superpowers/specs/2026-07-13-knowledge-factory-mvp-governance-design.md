# 知识工厂最小可行治理 (MVP) 设计文档

> 日期: 2026-07-13 | 状态: 待评审
> 前置决策: 继续使用中等模型 (DeepSeek) → 知识工厂必须治理
> 策略: 路径 2 — 最小可行治理,只修最致命缺陷,不追求全面重构

## 1. 背景与战略选择

### 1.1 灵魂拷问的答案

**问**: 不用知识工厂,直接上传到知识库是否可行?

**答**: 不可行(针对当前中等模型场景)。理由:
- 中等模型直接读原始报告 → 丢结构、漏法规、编数据
- 知识工厂的章节大纲 + 模板填空 → 输出质量和稳定性大幅提升
- 知识工厂不鸡肋,但当前实现是半成品

### 1.2 三条路径对比

| 路径 | 工作量 | 风险 | 收益 |
|------|--------|------|------|
| 1. 全面治理 | 3-4 周 | 高(改动链路长) | 知识资产化 |
| **2. 最小可行治理 (MVP)** | **1-2 周** | **低** | **止血+可控** |
| 3. 降级为增强型知识库 | 1-2 天 | 最低 | 失去模板能力 |

**选定路径 2**: 只修最致命缺陷,让数据质量不再恶化,后续再渐进增强。

### 1.3 MVP 边界

| 做 (MVP 范围) | 不做 (留给后续) |
|---------------|----------------|
| ✅ slot 事后校验(实体归类+类型一致性) | ❌ 多报告合并 |
| ✅ 提交前验证关卡 | ❌ 分章节上传归并 |
| ✅ 异常不吞(任务状态真实反映) | ❌ 前端 slot 实时校验 |
| ✅ 存量数据治理脚本 | ❌ content_contract 全量回填 |
| ✅ 实体参与(事后校验模式) | ❌ 脚本化合规检查 |
| | ❌ 事前约束(不改 schema_variables=[]) |

## 2. slot 事后校验机制 (Section 1)

### 2.1 当前问题

```
当前: LLM 自由提取 slot → 关键词子串匹配补 entity_ref → 脆弱
后果: "村庄名称"匹配到"人居类保护目标"纯属巧合
```

### 2.2 事后校验流程

```
LLM 自由提取 slot (保持灵活性,不改 schema_variables=[])
  │
  ▼
事后校验层 (新增 slot_validation_service.py)
  Step 1: slot 归类 — 每个 slot 用 LLM 归类到 EntitySchema
          输入: slot.name + slot.context(原段落)
          输出: entity_ref + 置信度
  Step 2: 类型一致性校验 — slot.type vs EntitySchema.type
          如 slot.type=number 但 entity=法规标准 → 冲突警告
  Step 3: 冲突检测 — 同名 slot 绑不同 entity
          如 "面积" 段A→占地面积 段B→矿区面积 → 冲突警告
  Step 4: 校验报告 {validated, warnings, unresolved}
  │
  ▼
通过 → 存图谱 (entity_ref 可信)
警告 → 标记 quality_flag,仍存但降级
严重冲突 → 标记 pending_review,等人工确认
```

### 2.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 归类方式 | LLM 归类(非子串匹配) | 语义理解准确 |
| 校验时机 | 泛化后、提交前 | 不影响 LLM 自由提取 |
| 校验结果 | 三级(通过/警告/待审) | 不阻塞流程,问题可见 |
| 前端联动 | 报告传给 slot 校验 Tab | 人工可修正 |

### 2.4 不做 (YAGNI)

- 不自动生成 EntitySchema 定义(人工维护)
- 不做 slot.value 值域校验(留给后续)
- 不做事前约束(不改 schema_variables=[])

## 3. 提交前验证 + 异常不吞 (Section 2)

### 3.1 当前问题

```
commit_task (domain_factory_service.py:3791):
  - 不检查任何质量
  - 子阶段异常被吞,任务仍标记 COMMITTED
  → 数据残缺但显示成功
```

### 3.2 提交前验证关卡

```
新增 pre_commit_validator.py

检查项:
  结构完整性: 每章≥1模板、text_pattern非空
  slot 基本质量: name非空、数量≤15、无重复签名
  事后校验结果: 严重冲突=0、警告数有上限
  图谱前置条件: domain/report_type归一化、key可推导

校验失败 → {passed: false, errors} → 前端阻塞
校验通过 → 进入 commit pipeline
```

### 3.3 异常不吞改造

```
当前: 所有 Stage 异常 → logger.warning → COMMITTED
改为:
  Stage 2.5 图谱构建 → 失败标记 COMMIT_FAILED(关键)
  Stage 2.8 模板回流 → 失败不阻塞(非关键),记 partial_status
  Stage 2.9 outline → 失败标记 COMMIT_PARTIAL

任务状态扩展:
  COMMITTED       — 全部成功
  COMMIT_PARTIAL  — 部分成功(图谱OK但outline失败)
  COMMIT_FAILED   — 关键失败(图谱构建失败)
```

### 3.4 不做 (YAGNI)

- 不做自动重试(用户手动)
- 不做部分回滚(失败就标记,不删已写数据)
- 不做事务性提交(Neo4j+DB 独立提交)

## 4. 存量数据治理 (Section 3)

### 4.1 存量问题

```
Neo4j 90 ChapterTemplate:
  41/90 挂在 report_type='通用' (应合并到 eia_report)
  canonical_chapter_key 全 NULL
  title 双编号 "1.1.1 3.1.1 地形地貌"
  纯编号 title "2"
  Document.domain='煤炭采掘' (应为 'coal')
```

### 4.2 治理脚本

```
scripts/governance/fix_existing_graph.py (幂等,可重复运行)

Step 1: 合并 DomainOutline 分支
  coal/通用 的 41 章节 → report_type 改 eia_report → 合并分支 → 删空'通用'节点

Step 2: 清洗 ChapterTemplate.title
  "1.1.1 3.1.1 地形地貌" → "地形地貌"
  去掉所有前导编号,只留纯标题

Step 3: 回填 canonical_chapter_key
  ChapterTemplate: key = clean_title(title)
  ParagraphTemplate: 经 Section→COMPOSED_OF 反查章节,继承 key

Step 4: 归一化 Document.domain
  '煤炭采掘' → 'coal'

Step 5: 事后校验回补
  对 819 ParagraphTemplate 重跑事后校验,补准 entity_ref

Step 6: 校验报告
  0 个 NULL key / 0 个'通用' / 0 个双编号 / entity_ref 覆盖率
```

### 4.3 治理与增量修复的关系

```
存量治理(一次性脚本) + ETL源头修复(Section 1+2) = 根治
  修当前数据          防新数据污染
         └──────┬───────┘
                ▼
        干净图谱 → 工具直查(接知识图谱治理设计)
```

### 4.4 不做 (YAGNI)

- content_contract 全量回填(留给后续)
- 多报告 outline 聚合合并(代码已承认未实现)
- slot 跨报告去重(复杂度高)
- 历史数据重建(只修不删,保留可追溯)

## 5. 实施路线图

| Phase | 内容 | 依赖 | 优先级 |
|-------|------|------|--------|
| Phase 1 | slot 事后校验服务 (slot_validation_service.py) | EntitySchema 定义 | P0 |
| Phase 2 | 提交前验证关卡 (pre_commit_validator.py) | Phase 1 | P0 |
| Phase 3 | 异常不吞改造 (commit pipeline 状态扩展) | Phase 2 | P0 |
| Phase 4 | ETL 源头修复 (归一化 + title 清洗) | 无 | P1 |
| Phase 5 | 存量数据治理脚本 (fix_existing_graph.py) | Phase 1 | P1 |

## 6. 不变量 (设计约束)

1. LLM slot 提取保持自由(不做事前约束),质量由事后校验把关
2. 提交前验证是硬关卡,校验失败不允许提交
3. 任务状态必须真实反映入库结果(COMMITTED/PARTIAL/FAILED)
4. 存量治理脚本幂等,可重复运行
5. 治理只修不删,保留数据可追溯
6. MVP 不碰多报告合并/分章节上传等复杂协作功能
