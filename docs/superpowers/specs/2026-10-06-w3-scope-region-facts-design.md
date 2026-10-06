# W3 scope×region 事实维度落库 设计

> **日期**: 2026-10-06 ｜ **状态**: 已评审（Q1–Q3 三分叉经用户裁决）
> **依据**: roadmap v2 spec §4（W3 骨架）；gap-audit §2.4（W3 0/4）；本日双路探索（数据层 + 归因挂点）
> **前窗**: W2v2 三条输入小窗（96088d4e 收口）

## 1. 背景与目标

知识库工厂当前 4 domain / 8 任务 / 211 learned_templates，全部**无 scope（universal/regional/project）与 region（矿区/规划区）维度**——模板复用无法分级、区域事实无法沉淀、「一地区一KB」分库无键。

**目标**：scope×region 维度落库——任务/模板/区域事实三处数据模型落定，L1 规则 / L2 泛化便车 / L3 人工确认三级归属判定打通，min-permissive 写时聚合生效；泄漏退役与 L3 改判以薄 API 交付（UI 归 W4）。

**本窗 checklist（简要）**：
- [ ] 数据模型：Task +4 列、LearnedTemplate +scope 列、新表 domain_factory_regional_facts（三轨幂等落地）
- [ ] L1 确定性规则（词表命中）+ classify_paragraphs 并列信号键
- [ ] L2 泛化便车（零新增 LLM 调用）+ 回写
- [ ] min-permissive 写时聚合（含 extra_meta 归因集）
- [ ] regional_facts 写入流（draft/confirmed/retired）+ B 类映射
- [ ] 薄 API：confirm-region 级联 + facts 批量退役
- [ ] 存量回填：8 任务 L1（模板不回填）
- [ ] changelog / 勾账 / 终审

## 2. 范围

**In**：`backend/package/yuxi/storage/postgres/models_domain_factory.py`、`manager.py`（ensure 块 additive）、`backend/scripts/migrate_domain_factory.sql`、`backend/scripts/backfill_task_scope.py`（新）、`backend/package/yuxi/services/domain_factory_service.py`、`backend/package/yuxi/services/domain_factory_region.py`（新：词表 + L1 规则 + 聚合纯函数）、`backend/server/routers/domain_factory.py`（薄路由）、单测 + 容器集成测试。

**Out**：W4 UI 与列表/筛选接口、LearnedTemplate 历史回填（Q3 裁决：不回填）、唯一约束 4列(模型)/3列(库) 分叉收口（只知悉不收）、泄漏自动检测、横城 ETL rerun（bug-334 parked）。

**不变量**：manager.py ensure 只加不改（additive 白名单）；classify_tags 语义零变动（test_w1_prose_pipeline 钉住）；上游共有代码最大约束不动；graph 侧 LegalReference.scope（national/regional/project，graph_builder.py:583-629）不动、词汇不混用（任务/模板 scope 用 universal/regional/project）。

## 3. 设计输入（探索结论，行号为 2026-10-06 快照）

### 3.1 数据层

- DomainFactoryTask（models L41-105）：`id=String(64)` PK；索引命名 `idx_df_tasks_*`
- DomainFactoryLearnedTemplate（L108-149）：**无 source-task 归因列**；有 `extra_meta JSON` 列（L130，本窗归因集复用它）；模型层唯一约束 4 列（L113-115）vs 库内 3 列（manager.py:1572、migrate sql:69）分叉已知不收
- 建表先例 DomainFactoryToolUsage（L328-356 + manager.py:1659-1670）：create_all（:586-593）不补列补表 → 存量库靠 ensure DDL（`ADD COLUMN IF NOT EXISTS`）+ migrate sql **三轨幂等**
- 列添加两风格：ensure 用 `ALTER TABLE IF EXISTS ... ADD COLUMN IF NOT EXISTS`；migrate sql 用 `DO $$ ... information_schema.columns ... $$`（:136-144 先例）

### 3.2 归因挂点

- **L1**：classify_paragraphs（service:1626，纯函数）既有词表 :1613-1617（monitoring/compliance/standard_limit）；跳过分支重置 classify_tags（:1639-1641）被 test_w1_prose_pipeline.py:78-79 钉住
- **L2**：GeneralizedTemplate schema（:36-44）+ _PROMPT_DEFAULTS（:241-275）+ 回写（:872-921）；**structured 通道物化 schema 默认值（:3579-3582）→ 新字段默认必须 None**；fallback（:3631）保守
- **L3**：confirm_proposed_entities（service:6213，router:353）+ _remap_waiting_review_tasks（:6317-6361，批量先例）
- **B/C 类**：DomainEntitySchema.category（models_domain_entity.py:23），6 类（service:6086-6094）：C=project_basic；B=natural_env/env_quality/sensitive_target/measures_regulation/impact_assessment

## 4. 设计

### 4.1 数据模型（三轨幂等）

**DomainFactoryTask +4 列**（roadmap 3 列 + scope 第 4 列；理由：任务级判定结论承载分库键与聚合证据）：

| 列 | 类型 | 语义 |
|---|---|---|
| project_name | VARCHAR(255) NULL | 项目名（L1/L2 产出） |
| region_label | VARCHAR(255) NULL | 区域展示名（如「伊宁矿区北区」） |
| region_key | VARCHAR(128) NULL，INDEX `idx_df_tasks_region` | slug 键（如 yining-beiqu / hengcheng） |
| scope | VARCHAR(32) NULL | 判定结论 universal/regional/project；NULL=未判 |

**DomainFactoryLearnedTemplate +1 列**：`scope VARCHAR(32) NULL`——不进唯一约束（roadmap 原文）；NULL=无证据不参与聚合（Q3）。

**新表 domain_factory_regional_facts**（建表仿 ToolUsage 先例）：

```sql
CREATE TABLE IF NOT EXISTS domain_factory_regional_facts (
    id SERIAL PRIMARY KEY,
    fact_type VARCHAR(32) NOT NULL,               -- monitoring|sensitive_target|measure|constraint
    region_key VARCHAR(128),                      -- NULL=未归属（靠 source_task_id 追补）
    content TEXT NOT NULL,                        -- 事实内容（实体名+描述/值）
    source_task_id VARCHAR(64) REFERENCES domain_factory_tasks(id) ON DELETE SET NULL,
    entity_key VARCHAR(255),                      -- 源实体键：去重与溯源（本表超出 roadmap 的唯一新增列）
    status VARCHAR(32) NOT NULL DEFAULT 'draft',  -- draft|confirmed|retired
    year INTEGER,
    source_ref TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dfrf_region_type_status ON domain_factory_regional_facts(region_key, fact_type, status);
CREATE INDEX IF NOT EXISTS idx_dfrf_source_task ON domain_factory_regional_facts(source_task_id);
```

**三轨落地**：模型 Column 定义 + manager.py ensure（4+1 个 ADD COLUMN IF NOT EXISTS、CREATE TABLE、2 索引，注释标 `[pisuan-custom] W3`）+ migrate_domain_factory.sql 新章节（列添加沿用 DO $$ 风格）。

### 4.2 归属判定：证据/判定分层 + L1/L2/L3

**分层语义**：「建议」（规则/LLM 产出，NULL=无证据，不参与聚合）≠「判定」（task.scope 落定值）。写优先级 **L1 > L2 > COMMITTED 兜底 project**；L3 confirm-region 人工覆盖（三列+scope 可改）。不加 provenance JSON 列（YAGNI：溯源走回填报告 + L3 审计）。

- **L1**（domain_factory_region.py 新模块）：`REGION_VOCAB` 词表常量（矿区/规划区名→slug，初值取自存量 8 任务与 4 domain 注册名的矿区词提取，slug 格式 `^[a-z0-9-]+$` 单测校验）+ 行政区闭集词表（仅作辅助信号词，不作 region_key，Q2）+ 年份正则。规则纯函数：输入段落文本 → region 信号（label+key）与 fact_type 信号。挂载：classify_paragraphs 内以**并列 JSON 键**（region_signals / fact_signals）写回段落记录，不碰 classify_tags 本体（跳过分支行为零改动）。任务级：**文档身份（file_name/document_type/report_type_code）词表命中** → 写 task 三列 + scope='regional'（不扫正文——正文引用矿区名的项目报告会误判 regional；计划 T2 落账修订）。backfill 脚本对 8 存量任务跑同规则。
- **L2**（零新增 LLM 调用，便车泛化）：GeneralizedTemplate +`scope`/`region` 可选字段（**默认 None**——structured 通道不得物化默认值，防全量假性 project 证据污染 min 计算）；_PROMPT_DEFAULTS 说明可选输出；_normalize_template_response 兼容缺省；回写循环读到建议 → **仅当本任务对应列仍为 NULL 时写入**（L1 优先语义）；fallback 路径保持 None
- **L3**：confirm-region API 人工改判（见 4.6）

**兜底**：任务进入 COMMITTED 时 scope 仍 NULL → 写 project（最保守）；已有值不动。

### 4.3 fact_type ↔ B 类映射

| B 类 category | fact_type | 判定 |
|---|---|---|
| natural_env | monitoring | 现状/背景值 |
| env_quality | monitoring | 质量/监测数据 |
| sensitive_target | sensitive_target | 直映 |
| measures_regulation | measure 或 constraint | L1 关键词拆分：标准限值/法规禁止→constraint；工程/治理措施→measure；歧义 fallback=measure（L3 可改） |
| impact_assessment | constraint | 评价结论构成区域约束 |

C 类（project_basic）不入 universal/regional 模板、不入 regional_facts（roadmap 禁令）。

### 4.4 写入流（挂既有确认点，不新增管线）

1. **draft**：confirm_proposed_entities（service:6213）确认 B 类实体时同步插 regional_facts：status=draft、region_key=task.region_key（可 NULL）、entity_key、source_ref=段落出处、year 规则抽取（可 NULL）；去重键 (source_task_id, entity_key) 已存在则跳过
2. **confirmed**：confirm-region 级联——task 三列+scope 落定 → 同任务全部非 retired facts **覆盖式**回填 region_key（含纠偏：L3 改判 A→B 时旧 stamp 一并更新，审计靠 updated_at）+ status draft→confirmed → 该任务归因集内模板聚合重算（4.5）
3. **retired**：retire API 批量 status→retired（不删行，留审计）

### 4.5 min-permissive 聚合（write-time + 归因集）

窄序 **project < regional < universal**；`min_permissive_scope(evidences) -> scope|None` 纯函数（domain_factory_region.py）：

| 证据集（非 NULL task.scope；NULL 不参与） | 结果 |
|---|---|
| 空 | None（模板 scope 不动） |
| 全 project / 全 regional | project / regional |
| 混合 | 取最窄 |
| universal 现值 + 全 regional（或全 project）证据 | 降级 regional（或 project） |
| 任何方向 | **永不自动升级** |

**归因集**（解 confirm-region 重算的归因洞）：聚合时把贡献任务 id 并入 `LearnedTemplate.extra_meta.contributing_task_ids`（既有 JSON 列，union 不覆盖）；每次聚合证据 = 归因集内任务**当前** task.scope 全量重读（任务行持久，证据随 L3 改判变富）。confirm-region 级联凭 extra_meta 定位受影响模板重算。

时机：回写循环（service:872-921）完成时聚合本批次写入的模板；confirm-region 级联重算归因集命中者。

### 4.6 薄 API + 存量回填

- `POST /domain-factory/tasks/{task_id}/confirm-region` body `{region_label, region_key?, scope}` — router:353 邻域仿 confirm-entities；级联 4.4-2
- `POST /domain-factory/regional-facts/retire` body `{fact_ids: [int]}` → status=retired
- `backend/scripts/backfill_task_scope.py`：8 存量任务跑 L1，逐任务打印（file_name/命中词/scope/region）对照表；幂等（只填 NULL）；**learned_templates 零改动**（Q3）

## 5. 执行序

| 任务 | 内容 | 验证 |
|---|---|---|
| T1 | 模型 3 处 + ensure + migrate sql 三轨 | 容器 ensure 复跑无 diff；列/表/索引 existence 断言 |
| T2 | domain_factory_region.py（词表+L1+聚合纯函数）+ backfill 脚本 | 单测：词表命中/未命中/歧义 fallback/slug 格式/聚合五分支；回填报告 8 任务 |
| T3 | L2 便车（schema+prompt+normalize+回写）+ classify_paragraphs 并列键 | 单测：双通道显式产出/缺省 None；LLM 调用数断言不变；test_w1_prose_pipeline 零回归 |
| T4 | 写入流（confirm_proposed_entities 挂 facts draft） | 单测：B 类映射/C 类拒绝/去重 |
| T5 | 薄 API ×2 + 级联 | 容器集成：confirm-region 三步级联、retire、归因集重算 |
| T6 | changelog + 勾账 + 终审 | fresh-eyes 独立复验 |

T3/T4 同文件强顺序；T1→T2→(T3∥T4)→T5→T6。

## 6. 验收标准（DoD）

1. 三轨 DDL 一致幂等：容器内 ensure 复跑零 diff；migrate sql 与 ensure 列集一致
2. L1/L2 判定：词表命中/未命中/歧义 fallback 单测全绿；L2 双通道显式产出、无默认值物化；LLM 调用数与改动前持平（断言）；test_w1_prose_pipeline 零回归
3. 聚合：min-permissive 五分支单测全覆盖，永不升级
4. 写入流：B 类映射落 facts、C 类拒绝、(source_task_id, entity_key) 去重
5. 薄 API 容器集成：confirm-region 级联三步（任务列→facts 确认→归因集模板重算）；retire 幂等
6. 回填：8 任务报告产出、只填 NULL 幂等；learned_templates diff=0（211 行 scope 保持 NULL）
7. 不变量：manager.py additive；禁碰文件零卷入；中文 Conventional 提交 + 明确 `git add`

## 7. 风险与挂账

- **LearnedTemplate 无归因列** → write-time 归因集落 extra_meta 兜住 confirm-region 重算；W3 之前历史批次无归因集，其模板不参与级联重算（范围已知，Q3 语义下安全）
- **唯一约束 4列/3列分叉** → 只知悉不收（既有挂账）
- **classify_paragraphs 被单测钉住** → 新信号并列键，跳过分支不动；回归由 DoD-2 断言
- **新矿区 slug** → 词表人工维护 + L3 confirm-region 传入；无 pinyin 运行时依赖
- **roadmap §4 对照**：数据模型✓ L1✓ L2便车✓ L3批量✓ min-permissive✓ 泄漏=批量退役✓ B/C 禁令✓；UI→W4

## 8. 裁决记录

| # | 分叉 | 裁决 | 理由 |
|---|---|---|---|
| Q1 | 窗口范围 | A：模型+L1/L2/L3 全量+写时聚合+facts 写入流；退役/改判薄 API，UI 归 W4 | 单窗闭环数据链，UI 复杂度隔离到 W4 |
| Q2 | region_key 形态 | A：矿区/规划区词表 slug（yining-beiqu/hengcheng 式）；行政区名仅作 L1 辅助信号词，不作 region_key | slug 稳定可作分库键；行政区粒度过粗 |
| Q3 | 存量回填 | A：8 任务 L1 规则回填；211 模板不回填 | 规则可复核；空 scope=无证据不参与聚合，min-permissive 下安全 |
