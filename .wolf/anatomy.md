# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-13T13:25:26.958Z
> Files: 61 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/


## ../../Users/Lenovo/AppData/Local/Temp/

- `patch_migration_tests.py` — RED 前置：为 v14 迁移扩 storage_migration 单测（6 处 fake + parametrize + 断言）。 (~513 tok)

## ../../Users/Lenovo/AppData/Local/Temp/claude/


## ../../Users/Lenovo/AppData/Local/Temp/eia-values/


## ../../tmp/


## ./


## .claude/


## .claude/rules/


## .claude/skills/


## .code-review-graph/


## .git/


## .github/


## .github/ISSUE_TEMPLATE/


## .github/workflows/


## .ruff_cache/


## .superpowers/brainstorm/492-1791332830/content/


## .superpowers/brainstorm/502-1791304488/content/


## 2026-10-09 数值护栏词表全栈新增文件


## backend/


## backend/.ruff_cache/


## backend/.ruff_cache/0.15.12/


## backend/package/


## backend/package/yuxi.egg-info/


## backend/package/yuxi/

- `storage_migration.py` — 在 API、worker 与 Sandbox 启动前完成一次性存储迁移。 (~2362 tok)

## backend/package/yuxi/agents/


## backend/package/yuxi/agents/backends/


## backend/package/yuxi/agents/backends/sandbox/


## backend/package/yuxi/agents/buildin/


## backend/package/yuxi/agents/buildin/chatbot/


## backend/package/yuxi/agents/buildin/deep_agent/


## backend/package/yuxi/agents/middlewares/


## backend/package/yuxi/agents/presets/subagents/

- `data_survey_writer.py` — 数据与现状写手预置子智能体（pisuan 环评写作链路）。 (~454 tok)

## backend/package/yuxi/agents/skills/buildin/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/

- `bank_compile.py` — bank_compile.py — 样例库 → 技能衍生物的确定性编译器（geo-sample-bank 核心）。 (~8008 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/

- `test_bank_compile_expectations.py` — section_expectations 测试：数值抽取 / field 归并 / 报告覆盖率 / tier 划档 / unmapped 池 / 节文本切分。 (~3086 tok)

## backend/package/yuxi/agents/skills/buildin/compliance-checker/


## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/


## backend/package/yuxi/agents/skills/buildin/template-recommender/


## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — Pydantic: DoubaoSearchInput (~12792 tok)

## backend/package/yuxi/agents/toolkits/debug/


## backend/package/yuxi/agents/toolkits/kbs/


## backend/package/yuxi/agents/toolkits/mysql/


## backend/package/yuxi/config/


## backend/package/yuxi/config/static/


## backend/package/yuxi/knowledge/


## backend/package/yuxi/knowledge/chunking/


## backend/package/yuxi/knowledge/chunking/ragflow_like/


## backend/package/yuxi/knowledge/chunking/ragflow_like/parsers/


## backend/package/yuxi/knowledge/chunking/ragflow_like/utils/


## backend/package/yuxi/knowledge/eval/


## backend/package/yuxi/knowledge/graphs/


## backend/package/yuxi/knowledge/graphs/adapters/


## backend/package/yuxi/knowledge/implementations/


## backend/package/yuxi/knowledge/utils/


## backend/package/yuxi/models/


## backend/package/yuxi/plugins/


## backend/package/yuxi/plugins/parser/


## backend/package/yuxi/repositories/

- `eia_entity_repository.py` — 环评 sample_entities 实体补充的数据访问边界（P3；DB 运营唯一真相，仅添加）。 (~670 tok)
- `eia_formula_repository.py` — 环评 formulas 参数参考值裁决的数据访问边界（P3；DB 运营唯一真相）。 (~729 tok)
- `eia_stage_repository.py` — 环评 stages forms 口径字段裁决的数据访问边界（P2；DB 运营唯一真相）。 (~830 tok)
- `eia_standard_repository.py` — 环评标准条目人工核实裁决仓储（eia_standard_reviews，P3 运营唯一真相）。 (~625 tok)

## backend/package/yuxi/services/

- `eia_data_service.py` — 环评域数据工厂（coal-eia-writer 技能）只读统计服务。 (~6958 tok)
- `eia_entity_service.py` — 环评 sample_entities 实体补充服务（P3-2：DB 补充唯一真相 + 显式导出物化注册表 + _index）。 (~2807 tok)
- `eia_formula_service.py` — 环评 formulas 参数参考值编辑服务（P3-1：DB 覆盖唯一真相 + 显式导出物化 formulas.json）。 (~2140 tok)
- `eia_lexicon_service.py` — 环评数值护栏词表运营服务（DB 覆盖层 + overrides 物化）。 (~4780 tok)
- `eia_stage_service.py` — 环评 stages forms 口径字段编辑服务（P2：DB 裁决唯一真相 + 显式导出物化 stages/<stage>.json）。 (~4010 tok)
- `eia_standard_service.py` — 环评标准条目人工核实服务（P3：DB 运营唯一真相 + 显式导出物化 standards_index.json）。 (~4271 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `manager.py` — PostgreSQL 数据库管理器 - 支持知识库和业务数据 (~31234 tok)
- `models_domain_factory.py` — Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表 (~7619 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/

- `domain_factory_router.py` — Domain Factory API Router - 领域知识工厂路由 (~16193 tok)

## backend/server/utils/


## backend/templates/coal/


## backend/templates/coal/headers/


## backend/templates/coal_mining/report_skeletons/


## backend/test/


## backend/test/api/


## backend/test/data/


## backend/test/data/corpus_census/


## backend/test/e2e/


## backend/test/integration/


## backend/test/integration/api/

- `test_eia_p3_flow.py` — eia formulas/entities/datasets API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。 (~1429 tok)
- `test_eia_stage_flow.py` — eia stages/sections/gate1 API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。 (~1136 tok)

## backend/test/integration/services/


## backend/test/unit/

- `test_eia_data_service.py` — eia_data_service 单元测试：统计结构完整性 + 词表候选清洗/三分类规则。 (~1114 tok)
- `test_eia_lexicon_service.py` — eia_lexicon_service 单元测试：导入预置 / 区间构建 / 语料扫描与提及收集。 (~1562 tok)
- `test_eia_standard_service.py` — eia_standard_service 纯函数单测：核实载荷校验（action 白名单、note 类型、未知字段拒收）+ 引用码归一。 (~2261 tok)

## backend/test/unit/backends/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/

- `test_eia_data_sections.py` — eia_data_service P2 只读视图测试：节级明细（get_sections）+ 备料清单（get_data_expectations）。 (~882 tok)
- `test_eia_dataset_view.py` — eia_data_service.get_dataset_view 单测（P3-3：三数据集只读抽屉数据通道）。 (~946 tok)
- `test_eia_entity_service.py` — EiaEntityService 单测（P3-2：sample_entities 仅添加 + 文本级导出物化注册表 + _index）。 (~2041 tok)
- `test_eia_formula_service.py` — EiaFormulaService 单测（P3-1：formulas 参数参考值 DB 覆盖 + 文本级导出物化）。 (~2074 tok)
- `test_eia_stage_service.py` — eia_stage_service 测试（P2：stages forms 口径字段编辑 + 导出物化）。 (~3318 tok)
- `test_eia_standard_gate1.py` — eia_standard_service.get_gate1_checks 测试（P2-3 门 1 体检卡）。 (~542 tok)
- `test_storage_migration.py` — _Session: execute, commit, test_storage_migration_reads_legacy_schema_before_cutover, session_contex (~6875 tok)

## backend/test/unit/storage/


## backend/test/unit/toolkits/

- `test_lookup_regional_fact.py` — lookup_regional_fact 工具测试（writer 消费区域事实仓库，P1-2）。 (~1300 tok)

## docker/


## docker/nginx/


## docker/sandbox_provisioner/


## docker/volumes/milvus/etcd/member/snap/


## docker/volumes/milvus/milvus/data/pprof/


## docker/volumes/milvus/milvus/rdb_data/


## docker/volumes/milvus/milvus/rdb_data_meta_kv/


## docker/volumes/milvus/minio/.minio.sys/


## docker/volumes/milvus/minio/.minio.sys/buckets/.bloomcycle.bin/


## docker/volumes/milvus/minio/.minio.sys/buckets/.usage-cache.bin/


## docs/design/


## docs/develop-guides/

- `changelog.md` — 版本变更记录 (~29307 tok)
- `data-factory-ui.md` — 数据工厂 UI 规范 (~2058 tok)

## docs/intro/


## docs/superpowers/plans/


## docs/superpowers/specs/


## docs/vibe/

- `2026-10-12-eia-data-factory-p1-gaps.md` — 环评域数据工厂 × coal-eia-writer 技能数据对账 —— P1 缺口补齐需求 (~1589 tok)
- `2026-10-12-eia-data-factory-p2-pages.md` — 环评域数据工厂 P2/P3 页面补齐需求（专家参与度二分） (~1084 tok)
- `2026-10-12-eia-data-factory-p3-pages.md` — 环评数据工厂 P3 页面（formulas 参数编辑 / sample_entities 补充 / 三数据集只读抽屉） (~1527 tok)
- `2026-10-13-p2p3-prototype-fidelity-rework.md` — P2/P3 实现页原型保真重构（严格参照 2026-10-12-eia-p2-ui.html） (~565 tok)

## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/

- `2026-10-12-eia-p2-ui.html` — 环评域数据工厂 P2/P3 · 高保真 UI 原型 (~16889 tok)
- `data-factory-ui.md` — 数据工厂 UI 规范：P2 原型提炼的组件配方/暗色映射/token 正名映射 (~3800 tok)

## scripts/


## web/


## web/src/apis/

- `eia_data_api.js` — EIA Data Factory API (~304 tok)
- `eia_entity_api.js` — EIA Entity API (~288 tok)
- `eia_formula_api.js` — EIA Formula API (~288 tok)
- `eia_stage_api.js` — EIA Stage API (~346 tok)
- `eia_standard_api.js` — EIA Standard API (~412 tok)

## web/src/assets/css/


## web/src/components/


## web/src/components/domain-factory/


## web/src/components/eia-data/

- `DatasetStatsPanel.vue` — Vue: setup (~7924 tok)
- `EntitiesPanel.vue` — Vue: setup (~2744 tok)
- `ExpectationsPanel.vue` — Vue: setup (~1379 tok)
- `factory-ui.less` — 数据工厂原型配方（P2/P3 七屏共用的单次定义）。 (~4255 tok)
- `FormulasPanel.vue` — Vue: setup (~3725 tok)
- `LexiconPanel.vue` — Vue component (~8123 tok)
- `MetaPanel.vue` — Vue: setup (~4386 tok)
- `SectionsPanel.vue` — Vue component (~6139 tok)
- `StandardsPanel.vue` — s11 复刻：页头双通道导出 + gate1 体检卡 + 核实清单 seg/搜索自绘表 + 限值单卡 chips 单表视图。 (~6200 tok)

## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/

- `index.js` — Declares AppLayout (~2674 tok)

## web/src/stores/


## web/src/views/

- `EiaEntitiesView.vue` — Vue: setup (~37 tok)
- `EiaExpectationsView.vue` — Vue: setup (~40 tok)
- `EiaFormulasView.vue` — Vue: setup (~37 tok)
- `EiaLexiconView.vue` — Vue: setup (~36 tok)
- `EiaSectionsView.vue` — Vue: setup (~37 tok)
- `EiaStandardsView.vue` — 裸壳挂载 StandardsPanel（s11 批次瘦身边际）。 (~40 tok)
