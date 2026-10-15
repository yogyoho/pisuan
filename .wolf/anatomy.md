# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-15T11:45:09.333Z
> Files: 28 tracked | Anatomy hits: 0 | Misses: 0

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

- `storage_migration.py` — 在 API、worker 与 Sandbox 启动前完成一次性存储迁移。 (~2489 tok)

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


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/


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

- `eia_paradigm_repository.py` — 写作范式层草稿的数据访问边界（每资产 (asset_kind, asset_id) 至多一份活跃草稿）。 (~683 tok)

## backend/package/yuxi/services/

- `eia_paradigm_scan.py` — 范式 md 专名扫描（承方向 A A1 红线：导出写入前 0 命中）。 (~519 tok)
- `eia_paradigm_service.py` — 写作范式层编辑服务（s12/s13：DB 草稿=编辑唯一真相 + admin 导出物化回写 references/paradigms/*）。 (~3899 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `manager.py` — PostgreSQL 数据库管理器 - 支持知识库和业务数据 (~31605 tok)
- `models_domain_factory.py` — Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表 (~8911 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/

- `domain_factory_router.py` — Domain Factory API Router - 领域知识工厂路由 (~19453 tok)

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


## backend/test/unit/

- `test_eia_paradigm_scan.py` — eia_paradigm_scan 单元测试：专名扫描集构建与命中（承方向 A A1 红线）。 (~794 tok)
- `test_eia_paradigm_service.py` — eia_paradigm_service 单元测试：锚点校验 / 两键纪律 / preview 不写盘 / 导出字节纪律 / 漂移 / 回滚。 (~3556 tok)

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


## docs/intro/


## docs/superpowers/plans/

- `2026-10-14-paradigm-layer-edit.md` — 写作范式层查询与编辑页 实现计划 (~20516 tok)

## docs/superpowers/specs/

- `2026-10-14-factory-landing-design.md` — 知识工厂首页重设计：Landing 化 + 通用域模块化 (~989 tok)

## docs/vibe/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/


## scripts/


## web/


## web/src/apis/

- `eia_paradigm_api.js` — EIA Paradigm API (~329 tok)

## web/src/assets/css/


## web/src/components/


## web/src/components/domain-factory/


## web/src/components/eia-data/

- `EiaDataLayout.vue` — Vue: setup (~1297 tok)
- `FormsPanel.vue` — Vue: setup (~2986 tok)
- `ParadigmExportModal.vue` — Vue: setup (~900 tok)
- `ParadigmsPanel.vue` — Vue: setup (~2805 tok)

## web/src/components/factory-core/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/

- `index.js` — Declares AppLayout (~3396 tok)

## web/src/stores/


## web/src/views/

- `DomainFactoryView.vue` — Vue: 通用域, setup (~7471 tok)
- `EiaFormsView.vue` — Vue: setup (~35 tok)
- `EiaParadigmsView.vue` — Vue: setup (~38 tok)

## web/test/unit/

