# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-07-20T11:20:35.219Z
> Files: 14 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.docker/


## ../../tmp/


## ./


## .claude/


## .claude/rules/


## .claude/skills/


## .code-review-graph/


## .github/


## .github/ISSUE_TEMPLATE/


## .github/workflows/


## .gstack/qa-reports/


## .ruff_cache/


## .superpowers/sdd/


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


## backend/package/yuxi/agents/buildin/subagent/


## backend/package/yuxi/agents/middlewares/


## backend/package/yuxi/agents/skills/


## backend/package/yuxi/agents/skills/buildin/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — 煤矿环评报告编写 v2 (~1699 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/outlines/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/chapter_examples/


## backend/package/yuxi/agents/skills/buildin/compliance-checker/


## backend/package/yuxi/agents/skills/buildin/data-survey-writer/


## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/prediction-writer/


## backend/package/yuxi/agents/skills/buildin/regulation-writer/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/


## backend/package/yuxi/agents/skills/buildin/template-recommender/


## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — Pydantic: PresentArtifactsInput (~9341 tok)

## backend/package/yuxi/agents/toolkits/debug/


## backend/package/yuxi/agents/toolkits/kbs/


## backend/package/yuxi/agents/toolkits/mysql/


## backend/package/yuxi/config/


## backend/package/yuxi/config/static/


## backend/package/yuxi/extensions/


## backend/package/yuxi/extensions/regulation_library/


## backend/package/yuxi/knowledge/


## backend/package/yuxi/knowledge/chunking/


## backend/package/yuxi/knowledge/chunking/ragflow_like/


## backend/package/yuxi/knowledge/chunking/ragflow_like/parsers/


## backend/package/yuxi/knowledge/chunking/ragflow_like/utils/


## backend/package/yuxi/knowledge/eval/


## backend/package/yuxi/knowledge/graphs/


## backend/package/yuxi/knowledge/graphs/adapters/


## backend/package/yuxi/knowledge/implementations/


## backend/package/yuxi/knowledge/parser/


## backend/package/yuxi/knowledge/utils/


## backend/package/yuxi/models/


## backend/package/yuxi/plugins/


## backend/package/yuxi/plugins/parser/


## backend/package/yuxi/repositories/


## backend/package/yuxi/services/

- `domain_factory_service.py` — Domain Factory Service - 领域知识工厂服务层 (~78298 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/


## backend/package/yuxi/utils/


## backend/scripts/


## backend/scripts/governance/


## backend/server/


## backend/server/routers/

- `domain_factory_router.py` — Domain Factory API Router - 领域知识工厂路由 (~9462 tok)

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


## backend/test/scripts/


## backend/test/unit/


## backend/test/unit/agents/


## backend/test/unit/agents/middlewares/


## backend/test/unit/agents/toolkits/buildin/

- `test_tools.py` — TDD tests for v2 calculation tools and save_chapter state extension. (~1894 tok)

## backend/test/unit/backends/


## backend/test/unit/extensions/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/repositories/


## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/


## backend/test/unit/storage/


## backend/test/unit/toolkits/

- `test_graph_fallback_visibility.py` — get_chapter_outline 图谱回退可见性测试（P1: bug-127）。 (~762 tok)
- `test_lookup_standard_indicator.py` — §8 lookup_standard_indicator 工具测试（规范库 writer 工具）。 (~505 tok)

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


## docker/volumes/yuxi/threads/shared/admin/workspace/agents/


## docs/design/


## docs/develop-guides/


## docs/superpowers/plans/


## docs/superpowers/specs/


## docs/vibe/

- `2026-07-20-eia-system-deep-review.md` — 环评写作系统深度复审 + P0 修复 + 全面测试报告 (~1533 tok)
- `2026-07-20-system-module-analysis.md` — Yuxi 系统模块能力分析 (~7320 tok)
- `2026-07-20-upgraded-features-checklist.md` — 五大需求领域以外 — 系统升级功能模块清单 (~1860 tok)

## packages/yuxi-cli/src/yuxi_cli/

- `client.py` — from: authorize_path, close, health, discovery + 19 more (~2617 tok)
- `domain_factory.py` — Domain Factory CLI — batch upload, task inspection, and pipeline triggers. (~2212 tok)
- `main.py` — API router (~3312 tok)

## web/


## web/e2e/


## web/e2e/fixtures/


## web/src/apis/


## web/src/assets/css/


## web/src/assets/icons/files/


## web/src/components/

- `SettingsModal.vue` — Vue: setup (~3388 tok)

## web/src/components/domain-factory/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/extensions/regulation-library/


## web/src/layouts/


## web/src/router/


## web/src/stores/


## web/src/utils/


## web/src/views/

