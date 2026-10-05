# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-05T09:04:33.530Z
> Files: 20 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/


## ../../Users/Lenovo/AppData/Local/Temp/


## ../../Users/Lenovo/AppData/Local/Temp/claude/


## ../../Users/Lenovo/AppData/Local/Temp/eia-values/


## ../../tmp/


## ./

- `docker-compose.yml` — Docker Compose services；api/worker 均 :ro 挂载 backend/templates → /app/templates（bug-363 静态模板容器激活，~5867 tok）

## .claude/


## .claude/rules/


## .claude/skills/


## .code-review-graph/


## .github/


## .github/ISSUE_TEMPLATE/


## .github/workflows/


## .ruff_cache/


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


## backend/package/yuxi/agents/presets/subagents/


## backend/package/yuxi/agents/skills/buildin/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/


## backend/package/yuxi/agents/skills/buildin/compliance-checker/


## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/


## backend/package/yuxi/agents/skills/buildin/template-recommender/


## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — Pydantic: DoubaoSearchInput (~12030 tok)

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

- `domain_factory_repository.py` — Domain Factory 数据访问层 - Repository (~9628 tok)

## backend/package/yuxi/services/

- `domain_factory_service.py` — Domain Factory Service - 领域知识工厂服务层 (~77057 tok)
- `pre_commit_validator.py` — 提交前验证关卡:commit 前校验任务数据质量,校验失败阻止提交。 (~599 tok)
- `template_library.py` — 模板库：加载、管理和查询段落模板定义 (~1843 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `manager.py` — PostgreSQL 数据库管理器 - 支持知识库和业务数据 (~27877 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/


## backend/server/utils/


## backend/templates/coal/


## backend/templates/coal/headers/


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

- `test_learned_template_match_count.py` — bug-353: _increment_learned_template_match_counts 原方法不存在被静默吞，match_count 永不增量。 (~928 tok)
- `test_pre_commit_validator.py` — bug-354: pre_commit_validator 按 classify_type 识别 parameter 段落（原读不存在的 type 字段导致校验空转）。 (~1494 tok)
- `test_template_system.py` — 单元测试：模板系统三件套（TemplateLibrary / TemplateMatcher / TemplateGenerator） (~4017 tok)
- `test_tool_usage_tracking.py` — W0 取用率埋点：台账表 repo 方法与 tools.py 接线辅助。 (~650 tok)
- `test_validate_task_report.py` — bug-354 同族：validate_task 报告统计/L2 过滤应读 classify_type（原读 type 全部落空）。 (~531 tok)

## backend/test/unit/storage/


## backend/test/unit/toolkits/


## docker/

- `api.Dockerfile` — 使用轻量级Python基础镜像；含 COPY backend/templates /app/templates（bug-363 镜像内置静态模板，~655 tok）

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

- `changelog.md` — 版本变更记录 (~20852 tok)

## docs/intro/


## docs/superpowers/plans/

- `2026-10-05-w0-bugfix-and-usage-tracking.md` — W0：bug-353/354 修复 + 工厂产物取用率埋点 实施计划 (~6810 tok)
- `2026-10-05-w1-bug-359-domain-unify-match-rule.md` — bug-359 W1 首项实施计划：domain 词形统一 + 学习模板 match_rule 注入 (~3921 tok)
- `2026-10-05-w1-bug-363-static-templates-activation.md` — bug-363 W1 第二项实施计划：静态模板容器激活 + 部署一致性清查 (~1830 tok)

## docs/superpowers/specs/

- `2026-10-05-bug-359-domain-unify-match-rule-design.md` — bug-359 修复设计：domain 词形统一 + 学习模板 match_rule 注入 (~1121 tok)
- `2026-10-05-bug-363-static-templates-activation-design.md` — bug-363 修复设计：静态模板容器激活 + 部署一致性清查 (~520 tok)

## docs/vibe/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## scripts/

- `sync-dev.ps1` — sync-dev.ps1 — 开发期快速同步：pisuan 工作树 → pisuan-localized 运行栈 (~1712 tok)

## web/


## web/src/apis/


## web/src/assets/css/


## web/src/components/


## web/src/components/domain-factory/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/stores/


## web/src/views/

