# 通用域知识工厂 ETL 管线：现状梳理与去领域化设计

- 日期：2026-10-29
- 状态：设计定稿，待用户评审后进实施计划
- 分支：pisuan-custom
- 背景：`/superpowers:brainstorming` 产出。梳理通用域「知识工厂 → 数据源管理」tab 驱动的文件解析泛化管线（上传→解析→分类→泛化→审核→入库）的现状实现，给出 Top 问题方案级设计。
- 关联：docs/vibe/knowledge-factory-design.md（历史设计）、docs/vibe/2026-10-02-etl-redesign-requirements.md（P0/P1 需求，均已落地）

## 0. 用户裁定记录（本次设计的约束）

| 裁定项 | 结论 |
|---|---|
| 行业领域维度 | **废弃**。通用域不再区分 coal/chem/mineral/transport 等行业领域 |
| 去域深度 | **行为级**：前端摘除 + 后端收敛为固定「通用域」常量；DB 列与 domains 表保留冻结，不再暴露接口 |
| 存量数据 | **B2**：一次性 UPDATE 把 7 表存量 `domain_code='coal'` → `'general'`，domains 表补 general 行 |
| 执行顺序 | **B（去域）→ C（行为修复）→ A（包化拆分）** |
| 范围外 | `/domain-factory/eia/*` 路由段、eia_* 服务、环评页面**不动**（已核实零 domain 依赖） |
| 写手侧 | 五工具签名保留 domain 形参、内部忽略——agents/prompts/技能文档零改动 |
| S1-③ 产物消费断层 | 按重锚处理：管线价值 = KB RAG 语料 + 图谱事实；学习模板/大纲层降级为可选产出 |

## 1. 现状管线全生命周期

行号锚点基于 2026-10-29 工作树（service 实测 6772 行 / router 2063 行）。

### 1.1 总览

```
[前端 DataSourceDashboard]                 [后端 api-dev]                       [ARQ worker]
 上传弹窗 ──POST /domain-factory/upload──→ save_uploaded_file(:557)
   Form(domain 必填)                        └ storage/<domain>/<task_id>_name
                                            create_task(:571)
                                              └ get_domain_by_code 校验(:582)
                                              └ repo.create_task(domain_id)(:592)
                                              └ tasker.enqueue("domain_factory")(:614)
                                                                                  _etl_pipeline_async(:833)
     15s 条件轮询 ◄──状态: PARSING────────────  _etl_parse_stage(:639)
                                                                                  PARSE 段:
                                                                                  ├ ocr_service.parse_document + docx_guard 重试(:663)
                                                                                  ├ markdown→HTML→段落化(:1268)
                                                                                  ├ classify_paragraphs(:1697)
                                                                                  ├ 法规引用: 正则(:709)/LLM(:723)
                                                                                  ├ 模板匹配 matcher.match(domain|coal)(:742)
                                                                                  ├ 公式(:770)/图 VLM(:776)/章节提取(:787)/表 schema(:797)
                                                                                  └ source_paragraphs 持久化(:806)
                                                                                  GENERALIZE 段(:875):
                                                                                  ├ 泛化并发 [1,32] 默认 2(:917)
                                                                                  ├ 槽位映射 + 实体匹配(:940)
                                                                                  ├ generalize_paragraphs(:3317) 熔断器
                                                                                  ├ ai_confidence/coverage 统计(:1035)
                                                                                  └ WAITING_REVIEW(:1086)
 [EtlWorkbench 三步向导] ◄──── GET /tasks/{id} ──── 人工审核: parse→entities→commit
 保存步骤/确认实体 ◄──────── PUT /tasks/{id} 等
 提交 ──POST /tasks/{id}/commit──→ commit_task
                                    └ _commit_pipeline_async(:4468)
                                        ├ PreCommitValidator 门禁(:4505)
                                        ├ 早落 COMMITTED(:4533)            ← 状态机缺陷点
                                        ├ _build_ingest_markdown(:4558)
                                        ├ MinIO 双存(markdown+原件)
                                        ├ kb_manager.index_file→Milvus(:4597)
                                        ├ 图谱构建,失败降级 COMMIT_PARTIAL(:4643)
                                        ├ 学习模板(:4706)/大纲产出(:4719)/跨报告合并(:4732)
```

### 1.2 关键实现细节

- **解析段落化** `_parse_markdown_to_paragraphs`（:1268）：3 种标题模式（:1312-1324）；section_path 栈（:1423-1476）；HTML 表格占位整块替换（:1501-1577）；`_chinese_to_arabic`（:1606）中文数字换算存在「十一→101」缺陷，靠位置编号兜底（:1416-1421）。
- **结构分类** `classify_paragraphs`（:1697）：5 结构类型（heading/table/figure/formula/legal_reference）+ prose 兜底（prose/parameter/narrative 三值）；规则表 LEGAL_PATTERNS/_UNIT_RE/_SLOT_PATTERNS/_TABLE_SUBTYPE_KEYWORDS（:1643-1695）全部环评风味（GB|HJ|MT 等）。
- **泛化** `generalize_paragraphs`（:3317）：HTML 表格占位（:3409-3423）；<20 字符跳过（:3426）；熔断器 PROVIDER_ERROR_TYPES×连续 5 次跳闸→FAILED_PROVIDER（:271-274），已成功段落持久化，retry resume=True 断点续跑；**输入 text[:1200] 截断（:3468）会切碎 Markdown 表格**。
- **提交入库**：file_id `df_{hashstr(task_id+uuid4,8)}`（:4555）**含随机成分**，reingest 再生成 `df_ri_` 新 ID（:5577）→ 重复 KB 文档。
- **域绑定渗入**（去域对象，见 §3）：`_DOMAIN_ALIASES` 别名归一；`or "coal"` 兜底 ×4；LOCAL_SCHEMA_MAP 键 `coal.*`；上传目录/图谱键/大纲产出/实体发现全按域键控；`_REPORT_TYPE_ALIASES` 把「通用」强制映射为 `eia_report`（repo:39-45，域语义污染的旁证）。

## 2. 问题清单（严重度分级，全量）

| # | 级别 | 问题 | 锚点 | 对应方案 |
|---|---|---|---|---|
| S1-① | 高 | 领域绑死渗入通用管线：别名映射/`or "coal"` 兜底/coal 专属 schema/「通用」→eia_report 强制映射 | repo:24-45, service:742/:2340/:4719 | **B** |
| S1-② | 高 | 巨文件混居：service 6772 行、router 2063 行（通用段与 89 个 /eia 端点同文件）、EtlWorkbench 3242 行、Dashboard 1402 行（全部 pisuan 自有，可自由拆） | — | **A** |
| S1-③ | 高 | 产物消费断层：writer 已于 2026-10-22 剥离 KF 模板/大纲依赖（大纲库 1055 条零消费） | cerebrum 决策日志 | 重锚（见 §0） |
| S2-④ | 中 | enqueue 失败无兜底：仅 log「将继续执行」，任务永远 PENDING | service:622-623 | C-3 |
| S2-⑤ | 中 | commit 状态机不收敛 + 入库不幂等：COMMITTED 早落、INGESTING 缺位、reingest 不清理旧记录、file_id 含随机数 | service:4533/:4555/:5577 | C-1 |
| S2-⑥ | 中 | FAILED_PROVIDER 前端不可达：statusMap 无此状态条目、重试按钮仅 FAILED 显示 → 断点续跑 UI 断链 | DataSourceDashboard:80-96/:642-646 | C-2 |
| S2-⑦ | 中 | 泛化 LLM 输入 text[:1200] 截断含 Markdown 表格，违背「表格整块不切碎」裁定 | service:3468 | C-4 |
| S3-⑧ | 低 | EtlWorkbench rawSlots 声明后从未赋值，计数恒 0 | EtlWorkbench:45/:1920 | C-5 |
| S3-⑨ | 低 | 中文章节数字换算错：十一→"101" | service:1606/:1416 | C-5 |
| S3-⑩ | 低 | 小项组：GENERALIZING 重复 set（:875/:878）、空 template_payload 壳落库（:885-889）、批量删除逐条循环、演示回退 flag 开启时掩盖 401 | 多处 | C-5 |

## 3. 去领域化爆炸半径清单（方案 B 输入）

> 本清单 2026-10-29 全量 Grep 盘点；`✓` = 已核实不受影响。

### 3.1 数据模型（models_domain_factory.py）

| 触点 | 位置 | 去域处理 |
|---|---|---|
| `domain_factory_domains` 表 | :31-40 | 冻结；补 general 行 |
| `domain_factory_tasks.domain_id` NOT NULL FK + idx | :58-63/:99 | 保留列，统一指 general 行 |
| learned_templates 唯一约束含 domain_code | :132/:138 | 不动（值恒 general 后约束自然退化） |
| prompt_configs 唯一约束含 domain_code | :178/:182 | 同上 |
| outlines 唯一约束 uq_dfo_domain_rt_key | :207-216 | 同上 |
| reports.domain_code | :277 | 写 general |
| tool_usage.domain | :360 | 记 general |
| regional_facts | — | ✓ 无 domain 列 |

### 3.2 仓储层（domain_factory_repository.py）

- `_DOMAIN_ALIASES`（:24-38）+ `_normalize_domain`（:66-68）：保留（工具入参归一仍用），映射目标恒 general
- `_REPORT_TYPE_ALIASES`「通用」→eia_report（:39-45）：**删除该键**
- domains CRUD（:96-135）：服务层方法删除，repo 方法保留不再被路由触达
- 任务过滤 list_pending/history(domain_id)（:171-209）：不再传过滤
- learned_templates/outlines/reports/prompt_configs 全按 domain_code 过滤（:299-486/:518/:668-680/:724-801）：查询值恒 general
- 序列化输出 domain/domain_label（:953-954）：恒「通用域」

### 3.3 服务层（domain_factory_service.py，~60 处）

- `or "coal"` 兜底 ×4（:742/:751/:4360/:4719 及 :5898/:6111/:6157 的 `get("domain","coal")`）→ `GENERAL_DOMAIN_CODE`
- `create_task` 域校验（:582-584）→ 去除，外键取 general 行
- 上传目录（:558-562）→ `storage/general/`
- LOCAL_SCHEMA_MAP 键（:2341/:2376）→ `general.*` 前缀
- 模板匹配/章节提取/实体发现/槽位映射/大纲产出/模板回流/正则生成的 domain_code 形参：**签名全不动**，值由入口归一
- contexts 聚合 groupby（:5773-5776）→ 固定单元素
- `_remap_waiting_review_tasks`（:6252）：保留（实体更新仍按 general 域重映射）

### 3.4 图谱与写手消费

- graph_builder.py：章节节点 ID `CH_{domain}_{rt}_{level}_{hash}`（:63-80）、Document 属性（:214-240）、`OUTLINE_{domain}_{rt}` MERGE（:774-803）：**键结构不动**，domain 槽恒 general；存量 `*_coal_*` 节点保留只读
- tools.py 五工具（get_chapter_outline :624 / list_report_types :705 / list_chapter_keys :729 / get_templates :776 / create_report :849）：**签名保留 domain 形参**，`_normalize_domain` 后强制覆盖 general；`_track_usage`（:40-51）记 general

> **偏差回写（2026-10-31 实施后）**：存量图谱未按上文「`*_coal_*` 只读保留」执行。行为级改造（Task 6）只迁了 PG 7 表，漏迁 Neo4j，导致按 domain='general' 查询的大纲模板页返回空目录（bug-4175）。实际处置为**就地迁移**：`backend/scripts/governance/dedomain_chapter_templates_graph.py` 重写 id 前缀 `CH_coal_`→`CH_general_`、`OUTLINE_coal_`→`OUTLINE_general_` 并收敛 domain 属性（图内零 coal 残留）。只读保留不可行的原因：大纲骨架按 id MERGE，id 内嵌旧域不改，下次构建会分裂出第二个投影节点。

### 3.5 路由（domain_factory_router.py）

| 端点组 | 位置 | 处理 |
|---|---|---|
| domains CRUD ×3 | :44-122 | 删除 |
| data-sources / history / tasks-center Query(domain) | :126/:142/:621 | 删参 |
| upload Form(domain) | :508 | 阶段1 可选默认 general → 阶段3 删参 |
| outline-templates 段 Query/Form(domain="coal") ×6 | :750/:772/:799/:867/:896/:923 | 删参，内部恒 general |
| /eia 段（:938-2050） | — | ✓ 零 domain 触点，不动 |

### 3.6 前端

| 文件 | 触点 | 处理 |
|---|---|---|
| GeneralDataView.vue | domains 状态 + getDomains（:22-48） | 删 |
| DataSourceDashboard.vue | 领域筛选卡（:512-535）、domainOptions（:125-133）、fetch 参数（:165-191）、上传行业下拉（:327-350/:762-766）、新建领域（:315-318）、FormData domain（:437）、历史领域列（:712） | 全删；上传默认通用 |
| EtlWorkbench.vue | domainLabel tag（:442/:1019）、listEntitySchemas(task.domain)（:103-105） | 标签恒「通用域」；schema 查询固定 general |
| OutlineTemplate.vue | 领域选择器 + 全请求带 domain（:12-14/:284/:359-513） | 删选择器，请求不带 domain |
| AttributionTaskTable.vue | 领域列（:31） | 删列 |
| DomainEntityBuilderView.vue | 行业字段（:142-146）、domainOptions（:691-753）、copy 默认（:852） | 只删行业字段；**实体分组 taxonomy（project_basic/natural_env 等）是另一套概念，不碰** |
| PromptConfigView.vue | 模板文本「## 行业领域：」（:96） | 改中性表述 |
| domain_factory_api.js | 4 个 domains 方法 + demo 假数据（:29-66/:119-136）、fetch 参数（:144-154）、upload FormData（:274+） | 删 domains 方法；upload 不再 append domain |
| GeneralLayout / GeneralOverviewView / GeneralWorkbenchView | ✓ 无 domain 触点 | — |

### 3.7 外围

- test_domain_factory_api.py：domains CRUD/权限/401 用例（:13-93）随端点删除同步清理
- scripts/ ✓ 零匹配；eia_* 服务 ✓ 零依赖；task_registry.py 的 "domain_factory" 任务类型名与行业维度无关，不动
- 数据字典 DomainEntitySchema.domain_code / report_types.domain_code 列保留，查询恒 general

## 4. 方案 B：去领域化·行为级（详案）

### 4.1 常量锚点与数据脚本（阶段 1）

```python
# domain_factory_service.py 模块常量
GENERAL_DOMAIN_CODE = "general"
GENERAL_DOMAIN_NAME = "通用域"
```

一次性数据脚本（`scripts/` 下，幂等可重跑）：
1. `INSERT domain_factory_domains(code='general', name='通用域')` ON CONFLICT DO NOTHING
2. `UPDATE` 7 表存量 `'coal'→'general'`：learned_templates / outlines / prompt_configs / reports / tool_usage / tasks（domain_id 换指向 general 行）/ domain_entity_schemas
3. 老 coal 行不保留别名（B2 语义：名实一致）

### 4.2 阶段 2：前端摘除（§3.6 清单逐项）

### 4.3 阶段 3：路由删参 + 测试清理

两步走保证任一时刻栈内兼容：阶段 1 路由 domain 参数降级为「可选-忽略」，前端切换完成后再删参。

### 4.4 验收标准

- [ ] 通用域全部页面无「行业领域」字样与选择器
- [ ] 上传→解析→泛化→审核→提交→入库 E2E 全链路在无 domain 输入下走通
- [ ] 存量模板/大纲 UPDATE 后继续命中（泛化匹配与写手 get_templates 均可查到）
- [ ] 写手五工具传任意 domain 值（含 'coal'/'chem'/中文别名）均返回 general 语义结果
- [ ] Neo4j 新写入落 `*_general_*` 键；存量 coal 节点可读
- [ ] /eia 全段回归通过
- [ ] pytest 集成测试更新后全绿；`make format` 通过

## 5. 方案 C：行为修复批

1. **commit 幂等 + 状态机收敛**：引入 `INGESTING` 态（REVIEW_PASSED→INGESTING→COMMITTED/COMMIT_PARTIAL）；入库 file_id 改确定性 `df_{hashstr(task_id,12)}`（去 uuid4），Milvus/MinIO 同 key 覆盖实现幂等，reingest 复用同 ID；`repo.update_task` 增合法迁移枚举校验，非法迁移 raise。
2. **FAILED_PROVIDER 前端可达**：statusMap 补「服务商中断」条目；重试按钮条件扩为 `FAILED || FAILED_PROVIDER`。
3. **enqueue 兜底**：create_task 捕获 enqueue 异常 → 任务置 FAILED + 错误消息。
4. **泛化输入结构化组装**：`text[:1200]` 改为「标题 + 段落全文 + 表格 HTML 整块」组装，超长时按块丢弃尾部而非中间截断。
5. **小项组**：§2 S3-⑧⑨⑩ 逐项修复（含 `_chinese_to_arabic` 正规中文数字解析）。

## 6. 方案 A：domain_factory 包化拆分

- 后端包 `yuxi/domain_factory/`：`pipeline.py`（解析+泛化主流程）/ `classify.py`（分类规则）/ `schemas.py`（LOCAL_SCHEMA_MAP+章节提取）/ `templates.py`（模板回流+大纲）/ `ingest.py`（commit+图谱+入库）/ `entities.py`（实体+槽位）；`yuxi/services/domain_factory_service.py` 留门面 shim，对外 import 路径不变。
- 路由拆 `routers/domain_factory/general.py` + `eia.py`，`__init__.py` 汇总挂载，注册点不变。
- 前端：EtlWorkbench 拆 ParseStep/EntityStep/CommitStep + `useEtlTask` composable；Dashboard 拆 UploadModal/HistoryTable。
- 纯机械搬移：git mv + import 修复 + 全量回归验证。task_registry.py 保持纯追加声明不动。

## 7. 执行顺序与里程碑

```
B 阶段1（后端收敛+数据脚本） → B 阶段2（前端） → B 阶段3（删参+测试）
→ C（1→2→3→4→5，每项独立提交）
→ A（后端包化 → 路由拆分 → 前端拆分）
```

每步完成后 `make format` + docker 内 pytest + 对应前端 lint；B/C 阶段各跑一次 E2E。

## 8. 风险与回退

- B 是行为收敛但**可逆**（常量改回、参数复原即可），schema 级清理可日后在 B 之上补刀
- 数据脚本幂等设计，UPDATE 前自动备份受影响行数统计
- 图谱存量 coal 键已就地迁移（偏差回写见 §3.4，bug-4175）；id 前缀重写幂等可重跑，无重放风险
- /eia 段零耦合已核实，回归成本低
