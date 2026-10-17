# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-17T14:26:46.454Z
> Files: 69 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/

- `e2e-test-prerequisites.md` (~394 tok)
- `team-channel-report-discipline.md` (~211 tok)

## ../../Users/Lenovo/AppData/Local/Temp/

- `patch_bug446.py` — One-shot patcher for bug-446: add v17 stubs/param/assertions to test_storage_migration.py (~566 tok)
- `t9_expected.txt` (~58 tok)

## ../../Users/Lenovo/AppData/Local/Temp/claude/


## ../../Users/Lenovo/AppData/Local/Temp/eia-values/


## ../../Users/Lenovo/AppData/Local/Temp/pisuan-visual-qa/

- `visual-qa.js` — fs: login (~2363 tok)

## ../../tmp/


## ./

- `docker-compose.yml` — Docker Compose services (~5902 tok)

## .claude/


## .claude/rules/


## .claude/skills/


## .code-review-graph/


## .git/


## .github/


## .github/ISSUE_TEMPLATE/


## .github/workflows/


## .ruff_cache/


## .superpowers/brainstorm/4341-1791977035/content/


## .superpowers/brainstorm/492-1791332830/content/


## .superpowers/brainstorm/502-1791304488/content/


## .superpowers/brainstorm/725-1791941692/content/


## .superpowers/brainstorm/793-1791972344/content/


## 2026-10-09 数值护栏词表全栈新增文件


## backend/


## backend/.ruff_cache/


## backend/.ruff_cache/0.15.12/


## backend/package/


## backend/package/yuxi.egg-info/


## backend/package/yuxi/

- `storage_migration.py` — 在 API、worker 与 Sandbox 启动前完成一次性存储迁移。 (~2552 tok)

## backend/package/yuxi/agents/


## backend/package/yuxi/agents/backends/


## backend/package/yuxi/agents/backends/sandbox/


## backend/package/yuxi/agents/buildin/


## backend/package/yuxi/agents/buildin/chatbot/


## backend/package/yuxi/agents/buildin/deep_agent/


## backend/package/yuxi/agents/middlewares/


## backend/package/yuxi/agents/presets/subagents/


## backend/package/yuxi/agents/skills/buildin/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — pisuan 移植（2026-09-30）：运行时映射与改编范围见 (~6031 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/

- `corpus_meta.py` — 切片 + 人工核正 (~3181 tok)
- `front_extract.py` — front_extract.py — 语料封面/前置区元数据抽取器（spec 2026-10-16-corpus-meta-pipeline-refactor）。 (~2145 tok)
- `prepare_corpus.py` — prepare_corpus.py — 样例语料 docx → bank_compile 输入格式（hardening-design spec §五 解析边界）。 (~2509 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/

- `test_corpus_meta.py` — corpus_meta 测试：省名三级判定 / 标准号归一 / 附件两种形态抽取 / 条目归一 / (~2652 tok)
- `test_front_extract.py` — front_extract 测试：docx 前置区五字段 / rid 全量排序位复算 / 体裁与去重门 / 幂等 (~1604 tok)
- `test_prepare_corpus.py` — prepare_corpus 测试：节号标题识别 / 目录页剔除 / 表格 GFM / 标题层级提升。 (~1572 tok)

## backend/package/yuxi/agents/skills/buildin/compliance-checker/


## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/


## backend/package/yuxi/agents/skills/buildin/template-recommender/


## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — Pydantic: DoubaoSearchInput (~13213 tok)

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

- `eia_lexicon_repository.py` — 环评数值护栏词表数据访问层 - Repository (~1773 tok)
- `eia_library_repository.py` — 环评文件库仓储（eia_library_folders / eia_library_files，P1 进料区）。 (~1066 tok)
- `eia_paradigm_repository.py` — 写作范式层草稿的数据访问边界（每资产 (asset_kind, asset_id) 至多一份活跃草稿）。 (~683 tok)

## backend/package/yuxi/services/

- `eia_lexicon_service.py` — 环评数值护栏词表运营服务（DB 覆盖层 + overrides 物化）。 (~5473 tok)
- `eia_library_service.py` — 环评文件库服务（P1 进料区：上传即登记，加工属 P2 显式触发）。 (~1504 tok)
- `eia_meta_service.py` — 环评语料元数据人工标注服务（P2：DB 运营唯一真相 + 显式导出物化人工层文件）。 (~2576 tok)
- `eia_paradigm_scan.py` — 范式 md 专名扫描（承方向 A A1 红线：导出写入前 0 命中）。 (~519 tok)
- `eia_paradigm_service.py` — 写作范式层编辑服务（s12/s13：DB 草稿=编辑唯一真相 + admin 导出物化回写 references/paradigms/*）。 (~3899 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `manager.py` — PostgreSQL 数据库管理器 - 支持知识库和业务数据 (~32214 tok)
- `models_domain_factory.py` — Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表 (~8932 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/

- `domain_factory_router.py` — Domain Factory API Router - 领域知识工厂路由 (~21186 tok)

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

- `test_eia_paradigm_flow.py` — eia_paradigm API 层集成测试（认证门槛；全链业务语义由服务层测试覆盖）。 (~826 tok)

## backend/test/integration/services/

- `test_eia_lexicon_service_flow.py` — eia_lexicon 服务层全链路集成测试（不经 HTTP，无凭据依赖）。 (~1962 tok)

## backend/test/unit/

- `test_eia_lexicon_suppression_ops.py` — eia_lexicon_service 抑制名单运营单元测试：列表 / 手工添加校验 / 撤回 / 扫描差集。 (~1309 tok)
- `test_eia_library_service.py` — eia_library_service 单测：sha1 命名/去重、越限拒收、移动、删除、清单过滤（仓储以内存桩替身）。 (~1587 tok)
- `test_eia_meta_service.py` — eia_meta_service 单测：标注载荷校验（year_hint/scale_mt_a/report_title/eia_org 取值域）+ list_reports 合并透出。 (~1407 tok)
- `test_eia_paradigm_scan.py` — eia_paradigm_scan 单元测试：专名扫描集构建与命中（承方向 A A1 红线）。 (~794 tok)
- `test_eia_paradigm_service.py` — eia_paradigm_service 单元测试：锚点校验 / 两键纪律 / preview 不写盘 / 导出字节纪律 / 漂移 / 回滚 / 撤回 / 空批拒绝。 (~4114 tok)

## backend/test/unit/backends/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/


## backend/test/unit/storage/


## backend/test/unit/toolkits/

- `test_ask_user_question_card_guard.py` — ask_user_question 卡片反模式校验（bug-4011）单元测试。 (~570 tok)

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

- `changelog.md` — 版本变更记录 (~31733 tok)
- `design.md` — 产品体验与界面设计规范 (~2442 tok)

## docs/intro/


## docs/superpowers/plans/

- `2026-10-14-paradigm-layer-edit.md` — 写作范式层查询与编辑页 实现计划 (~20516 tok)
- `2026-10-15-lexicon-suppression-ui.md` — 数值护栏词表 · 抑制名单 UI 实施计划 (~6499 tok)
- `2026-10-16-corpus-meta-pipeline-refactor.md` — 语料元数据抽取管线重构实施计划 (~11565 tok)
- `2026-10-17-eia-file-library.md` — 环评文件库（P1）实施计划 (~11098 tok)

## docs/superpowers/specs/

- `2026-10-14-factory-landing-design.md` — 知识工厂首页重设计：Landing 化 + 通用域模块化 (~989 tok)
- `2026-10-15-lexicon-suppression-ui-design.md` — 数值护栏词表 · 抑制名单 UI 设计（2026-10-15） (~1296 tok)
- `2026-10-16-corpus-meta-pipeline-refactor-design.md` — 语料元数据抽取管线重构设计（front-extract 侧车 + cover 层） (~1546 tok)
- `2026-10-17-eia-file-library-design.md` — 环评文件库（P1）设计 (~1774 tok)

## docs/vibe/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/

- `2026-10-15-lexicon-mentions-drawer.html` — 提及明细抽屉重设计 · 数值护栏词表（2026-10-15） (~2667 tok)
- `2026-10-15-lexicon-rename-redesign.html` — 改名对话框重设计 · 数值护栏词表（2026-10-15） (~2433 tok)
- `2026-10-17-eia-library-ui.html` — 环评文件库 · 高保真 UI 原型 (~8152 tok)

## scripts/


## web/


## web/src/apis/

- `base.js` — 统一构建查询参数，保留 0 和 false，省略空值。 (~2994 tok)
- `eia_data_api.js` — EIA Data Factory API (~628 tok)
- `eia_lexicon_api.js` — EIA Lexicon API (~689 tok)
- `eia_paradigm_api.js` — EIA Paradigm API (~329 tok)

## web/src/assets/css/

- `base.css` — Styles: 1 rules, 153 vars (~2187 tok)
- `extensions.less` — Styles: 21 rules (~4284 tok)
- `main.less` — Styles: 43 rules, 2 vars (~1328 tok)
- `shorts.css` — Styles: 12 rules (~144 tok)

## web/src/components/


## web/src/components/domain-factory/


## web/src/components/eia-data/

- `EiaDataLayout.vue` — Vue: setup (~1331 tok)
- `FormsPanel.vue` — Vue: setup (~2986 tok)
- `LexiconPanel.vue` — Vue component (~12013 tok)
- `LibraryPanel.vue` — Vue: setup (~3574 tok)
- `MetaPanel.vue` — Vue component (~6076 tok)
- `ParadigmExportModal.vue` — Vue: setup (~900 tok)
- `ParadigmsPanel.vue` — Vue: setup (~2805 tok)

## web/src/components/factory-core/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/

- `index.js` — Declares AppLayout (~3461 tok)

## web/src/stores/

- `theme.js` — Exports useThemeStore (~556 tok)

## web/src/views/

- `DomainFactoryView.vue` — Vue: 通用域, setup (~7471 tok)
- `EiaFormsView.vue` — Vue: setup (~35 tok)
- `EiaLibraryView.vue` — Vue: setup (~36 tok)
- `EiaParadigmsView.vue` — Vue: setup (~38 tok)

## web/test/unit/

- `GeneralLayout.vue` — Vue: 通用域壳(216px侧栏+分组导航+RegulationEnrichPanel抽屉), setup (~1900 tok)
