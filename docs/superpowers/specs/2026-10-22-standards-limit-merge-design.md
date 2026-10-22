# P1 标准限值合流设计（Q2=A 物理合并）

日期：2026-10-22 ｜ 分支：pisuan-custom ｜ 状态：待用户评审

前置：图 A/图 B 合流对比（`docs/vibe/prototypes/2026-10-22-standards-merge-before-after.html`）
已演示，用户裁定 Q2 = **A 物理合并**（eia_standard_limit_rows 迁入 standard_indicators，
单表单真相）；语料管线对照分析与 #1–#4、#7 修复已完成（`docs/vibe/2026-10-22-corpus-pipeline-online-vs-offline.md`）。

## 1. 现状三套存储（实测普查，2026-10-22 容器只读查询）

| 存储 | 现状 | 角色 |
|---|---|---|
| `standards_index.json` → `limit_tables` | 7 表全 `needs_verification=true`，仅 gb3096/gb12348 各 1 行样例锚点，其余 0 行 | 文件锚点（SKILL 直接读） |
| `eia_standard_limit_rows` | **0 行** | 乙通道 DB（StandardsPanel 录入 + 语料限值提取转正 + 候选立表迁移） |
| `standard_indicators` | 667 行，全部 `source='enrich'`，`verified_at` 全 NULL（GB 8978-1996 461 + GB 3838-2002 206） | 甲通道（regulation_library enrich 抽取） |

病灶：三套互不相认。StandardsPanel 只读 1+2 合并；写手工具 `lookup_standard_indicator` 只读 3；
enrich 重跑 `DELETE FROM standard_indicators WHERE doc_code=:code` 全表扫删（会冲掉未来专家行）；
限值断言授权（门 1 纪律）靠文件 flag，与 DB 真相脱节。

## 2. 目标态（图 B）

**standard_indicators 单表单真相，行级双层标注**：

- **权威层**：`source='expert'` 且 `verified_at` 非空（页面确认/转正即 born-verified）
- **候选层**：`source='enrich'`；其中 `verified_at` 非空 = 候选·已核验（regulation-library
  表单元级核验），NULL = 候选·需人工对照
- 层级优先序：权威 > 候选·已核验 > 候选·需人工对照；统一查询每行带 `layer` 字段
- enrich 语义不变：候选层是「可被重跑刷新的派生数据」；专家行是不可再生成的运营资产

## 3. Schema 变更（standard_indicators 加两列）

standard_indicators 无 ORM 模型（raw SQL + `ensure_schema()`），变更落在 `ensure_schema()`：

```sql
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS table_key VARCHAR(64);
ALTER TABLE standard_indicators ADD COLUMN IF NOT EXISTS page_row_id VARCHAR(32);
CREATE INDEX IF NOT EXISTS ix_si_table_key ON standard_indicators (table_key);
```

- `table_key`：页分组视图键（`gbt14848_category_limits` 等），专家行必填；enrich 行 NULL
- `page_row_id`：页面行重组键。异构行形（LIMIT_TABLE_SCHEMAS）拍平映射时，一行页面数据
  可能拆成多行扁平指标（见 §4），同源行共享同一 `page_row_id`；enrich 行 NULL

`doc_code` 专家行取 `code_ref`（如 `GB/T 14848-2017`），与 enrich 行同键对齐——统一查询
天然把同一国标的权威行与候选行并置。

## 4. 异构行形 → 扁平指标映射（服务边界内拍平，页面视图重组）

LIMIT_TABLE_SCHEMAS 七表行形保留为 **页面编辑/校验契约**（服务边界校验后拍平）：

| 页面行形字段 | 扁平映射 |
|---|---|
| `pollutant` | `pollutant` |
| `category` | `category` |
| `period` / `phase` | `period` |
| `limit_value` | `limit_value`，`metric=''` |
| `day` / `night` | **拆两行**：`metric='昼间'`/`metric='夜间'`，`limit_value=day/night`，同 `page_row_id` |
| `a_value` | `limit_value=a_value`，`metric='A值'` |
| `region_type` | `category` |
| `grade` | `category` |
| `unit` | `unit` |

页面 GET 按 `table_key` 分组、`page_row_id` 重组回行形（单行直还原，拆两行按 `metric` 拼
day/night）。`LIMIT_TABLE_SCHEMAS` 与 `EiaLimitTableRegistry.columns_schema` 不动。

## 5. 生产者改造（三入口全量重指向）

1. **StandardsPanel 手工录入**（`eia_standard_service.save_limit_rows`）：校验后拍平写
   standard_indicators，`source='expert'`，`verified_at=now()`、`verified_by=username`
   （born-verified），`table_key`/`page_row_id` 填充。整表替换 = 按旧 `page_row_id` 集合
   删除后重插（事务内）。
2. **语料限值提取转正**（`eia_limit_extract_service.upsert_row`）：confirm/edited 目标改写
   standard_indicators（同 born-verified 语义——人工裁决即确认）；`eia_limit_extract_rows`
   暂存与留痕逻辑不动。
3. **候选立表**（`register_candidate` + `EiaLimitTableRegistry`）：注册表流程不变（页面
   schemas 渲染仍靠它）；后续录入走入口 1。

**enrich 收窄**（`enrichment_service.enrich_regulation_file`）：

```sql
-- 旧：DELETE FROM standard_indicators WHERE doc_code = :code
DELETE FROM standard_indicators WHERE doc_code = :code AND source = 'enrich'
```

专家行从此对 enrich 重跑免疫（图 B ✓④）。

## 6. 统一分层查询（query_indicators 升级）

`query_indicators(doc_code, pollutant)` 返回行追加派生字段：

- `layer`：`authority`（source=expert）/ `reviewed`（enrich+verified_at）/ `candidate`
  （enrich 无 verified_at）
- `table_key`：透传
- 排序：权威行优先，再按 doc_code/unit_no
- 锚点 join：`standards_index.json` 双点——`standards[]`（按 code 匹配 doc_code）注入
  `tier`；`limit_tables[code_ref]` 注入表级 `needs_verification` 为 `table_nv`。由
  **服务端** join 注入（读文件已在同进程，不做新存储）

`lookup_standard_indicator`（writer 工具）零改动透传新字段；SKILL 写作纪律接 §8。

## 7. 消费者改造

- **StandardsPanel 后端**（`eia_standard_service.list_limit_tables`）：合并逻辑改为
  文件锚点行（`source='file'`，seed 展示）+ standard_indicators 专家行（按 table_key 分组
  重组）。表级 `verified` 改为派生判定：该 table_key 存在专家行即 true（查询时计算，
  不再依赖文件 flag 翻转）。
- **`export_limit_rows` 端点废除**：DB 已是唯一真相，DB→文件整表物化失去意义。文件锚点行
  冻结为 seed（占位示例与行形演示）。前端 `exportLimits` 按钮与 API 封装同撤。
  `eia_standard_reviews` 的导出（62 条标准级核实，粒度不同）**不动**。
- **门 1 体检卡 / `get_gate1_checks`**：不动（规则规格读文件）。

## 8. SKILL 接线（写手侧纪律）

- 门 1 与 步骤 4 写前对账：限值断言优先查 `lookup_standard_indicator`；
  `layer='authority'` 可下结论；`reviewed` 可引用并标注「已核验候选」；`candidate` 或
  全无 → 标注「[需人工对照]」，不下结论（图 B ②③）
- SKILL.md 相应小节补一行数据面说明：限值真相 = 统一分层查询 API；standards_index.json
  limit_tables 仅 seed 与表级 flag 展示

## 9. 迁移（一次性脚本）

实测 `eia_standard_limit_rows` 为 0 行，**无数据迁移**。脚本仅做：
1. `ensure_schema()` 加列（幂等）
2. 校验无 orphan：`SELECT count(*) FROM eia_standard_limit_rows` 打印归档值（0），
   表保留不删（降级为退役表，结构留档）

无文件迁移：seed 锚点 2 行原地保留。

## 10. 测试与验收

- 单测（container pytest）：
  - 拍平映射 round-trip：七表行形 → 拆平 → 页面重组逐表断言（day/night 拆两行同
    page_row_id 是关键用例）
  - born-verified：save_limit_rows 后行 `source='expert'` 且 verified_at 非空
  - enrich 收窄：同 doc_code expert 行在 enrich 重跑后幸存
  - 分层查询：authority > reviewed > candidate 排序与 layer 派生
  - 表级 verified 派生：有专家行 = true；无 = 沿用文件 flag
- 集成冒烟：StandardsPanel 页面录入 GB/T 14848 一行 → lookup_standard_indicator 查到
  authority 行 → enrich 重跑该 doc_code 后行不丢
- 回归：`eia_standard_reviews` 导出、门 1 体检卡、语料限值提取试跑→暂存链不受影响

## 11. 明确不做

- eia_standard_reviews（标准级核实）不动
- regulation-library 表单元级核验（set_unit_verification）不动
- standards_index.json standards[]/gate1 结构不动
- 退役表 eia_standard_limit_rows 不 DROP（留档）
- Neo4j 图面（RegulationGraphWriter）不动
