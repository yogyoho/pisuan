# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-07-11T06:57:05.330Z
> Files: 17 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../tmp/


## ./


## .claude/


## .claude/rules/


## .claude/skills/


## .code-review-graph/


## .github/


## .github/ISSUE_TEMPLATE/


## .github/workflows/


## .ruff_cache/


## .superpowers/sdd/

- `task-3-report.md` — Task 3 Report: OutlineProducer — LLM 章节归一 + 散文 (~636 tok)
- `task-4-report.md` — Task 4 Report: OutlineProducer 编排 + 接入 commit 流水线 + 回填模板 (~780 tok)
- `task-5-report.md` — Task 5 Report: 两个 buildin 工具 get_chapter_outline / get_templates (~846 tok)
- `task-6-report.md` — Task 6 Report: 4 个写作 skill 改指向新工具 (~986 tok)
- `task-7-report.md` — Task 7: 端到端验证 + changelog + OpenWolf 收尾 (~1038 tok)

## backend/


## backend/.ruff_cache/


## backend/.ruff_cache/0.15.12/


## backend/package/


## backend/package/yuxi.egg-info/


## backend/package/yuxi/


## backend/package/yuxi/agents/


## backend/package/yuxi/agents/backends/


## backend/package/yuxi/agents/backends/sandbox/


## backend/package/yuxi/agents/buildin/


## backend/package/yuxi/agents/buildin/chatbot/


## backend/package/yuxi/agents/buildin/deep_agent/


## backend/package/yuxi/agents/middlewares/


## backend/package/yuxi/agents/skills/buildin/

- `__init__.py` — Declares from (~942 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — 煤矿环评报告编写（改指向 get_chapter_outline / get_templates，query_kb 回归自由检索） (~1155 tok)

## backend/package/yuxi/agents/skills/buildin/compliance-checker/

- `SKILL.md` — 合规性校验 (~460 tok)

## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/

- `SKILL.md` — 智能填槽 (~632 tok)

## backend/package/yuxi/agents/skills/buildin/template-recommender/

- `SKILL.md` — 段落模板智能推荐 (~533 tok)

## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — buildin 工具集（含 **get_chapter_outline** / **get_templates** 入库→写作桥工具） (~4900 tok)

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

- `domain_factory_repository.py` — Domain Factory 数据访问层 - Repository（task CRUD / learned_templates upsert / **outlines: upsert_outline, get_outline, list_chapter_keys, backfill_template_chapter_key, list_learned_templates_by_key**） (~6800 tok)

## backend/package/yuxi/services/

- `domain_factory_service.py` — Domain Factory Service - 领域知识工厂服务层（含 **OutlineProducer**: `_produce_outlines_async` / `_group_assets_by_chapter` / `_assemble_deterministic_outline` / `_llm_chapter_meta`，接入 commit 阶段2.9） (~63500 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `models_domain_factory.py` — 领域工厂 SQLAlchemy 模型（task / learned_templates 含 canonical_chapter_key / **domain_factory_outlines** 含 content_contract/rigidity 占位） (~900 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/


## backend/server/utils/


## backend/templates/coal_mining/


## backend/templates/coal_mining/headers/


## backend/test/


## backend/test/api/


## backend/test/data/


## backend/test/e2e/


## backend/test/integration/


## backend/test/integration/api/


## backend/test/integration/services/


## backend/test/unit/


## backend/test/unit/backends/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/

- `test_outline_producer.py` — test_group_assets_by_chapter_buckets_by_chapter, test_assemble_deterministic_outline_fields, test_ll (~1465 tok)

## backend/test/unit/storage/


## backend/test/unit/toolkits/

- `test_domain_factory_tools.py` — test_get_chapter_outline_tool_returns_dict, test_get_templates_tool_returns_list (~344 tok)

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

- `changelog.md` — 版本变更记录 (~10813 tok)

## docs/superpowers/plans/


## docs/superpowers/specs/


## docs/vibe/


## web/


## web/src/apis/


## web/src/assets/css/


## web/src/assets/icons/files/


## web/src/components/


## web/src/components/domain-factory/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/stores/


## web/src/views/

