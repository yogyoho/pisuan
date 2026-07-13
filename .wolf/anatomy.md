# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-07-13T03:06:42.365Z
> Files: 64 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.docker/

- `daemon.json` (~52 tok)

## ../../tmp/


## ./

- `_extract_eia_structure.py` — p (~1919 tok)
- `_extract_eia_structure2.py` — p (~1091 tok)

## .claude/


## .claude/rules/


## .claude/skills/


## .code-review-graph/


## .github/


## .github/ISSUE_TEMPLATE/


## .github/workflows/


## .ruff_cache/


## .superpowers/sdd/

- `followups-report.md` — 写作侧确定性骨架 — 4 个 Review Follow-up Fixes (~302 tok)
- `original-upload-report.md` — Original File Upload to MinIO — Report (~369 tok)
- `p0-task1-report.md` — P0 Task 1: ExcludedToolsMiddleware (~680 tok)
- `p0-task2-3-report.md` — P0 Task 2 + Task 3 Report (~599 tok)
- `task-1-report.md` — Task 1 Report: 存储——3 张表 + repository (~701 tok)
- `task-2-report.md` — Task 2 Report: create_report / get_report / set_pps_param 工具 (~387 tok)
- `task-3-report.md` — Task 3 Report: save_chapter 工具(懒建 + status) (~554 tok)
- `task-4-report.md` — Task 4 Report: `{{REF}}` resolver (纯代码) (~609 tok)
- `task-5-report.md` — Task 5 Report: assemble_report 工具(合并 + 解析 + 写沙箱) (~649 tok)
- `task-6-report.md` — Task 6 Report: chapter-writer 子 agent 注册 (~423 tok)
- `task-7-fix-report.md` — Task 7 Fix: canonical_chapter_key Backfill Mismatch (~561 tok)
- `task-7-report.md` — Task 7 Report: coal-eia-writer SKILL 改为编排者 (~388 tok)
- `task-8-report.md` — Task 8 Report: 端到端验证 + changelog + OpenWolf 收尾 (~614 tok)

## backend/


## backend/.ruff_cache/


## backend/.ruff_cache/0.15.12/


## backend/package/


## backend/package/yuxi.egg-info/


## backend/package/yuxi/


## backend/package/yuxi/agents/

- `base.py` — BaseAgent: module_name, id, get_info, get_config + 2 more (~5465 tok)
- `context.py` — Define the configurable parameters for the agent. (~5467 tok)

## backend/package/yuxi/agents/backends/

- `composite.py` — from: glob, aglob, wrap_tool_call, awrap_tool_call + 6 more (~2338 tok)

## backend/package/yuxi/agents/backends/sandbox/

- `backend.py` — ProvisionerSandboxBackend: id, read (~7669 tok)

## backend/package/yuxi/agents/buildin/


## backend/package/yuxi/agents/buildin/chatbot/

- `graph.py` — ChatbotAgent: get_graph, main (~1261 tok)

## backend/package/yuxi/agents/buildin/deep_agent/


## backend/package/yuxi/agents/buildin/subagent/

- `graph.py` — _SubAgentToolFilterMiddleware: wrap_model_call, awrap_model_call, get_info, get_graph (~1538 tok)

## backend/package/yuxi/agents/middlewares/

- `excluded_tools.py` — ExcludedToolsMiddleware — 从模型可见工具列表中移除 agent 配置的 excluded_tools。 (~348 tok)

## backend/package/yuxi/agents/skills/buildin/

- `__init__.py` — Declares from (~1063 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — 煤矿环评报告编写 v2 (~567 tok)

## backend/package/yuxi/agents/skills/buildin/compliance-checker/

- `SKILL.md` — 合规性校验 (~460 tok)

## backend/package/yuxi/agents/skills/buildin/data-survey-writer/

- `SKILL.md` — 数据与现状 Writer (~316 tok)

## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/prediction-writer/

- `SKILL.md` — 预测与论证 Writer (~330 tok)

## backend/package/yuxi/agents/skills/buildin/regulation-writer/

- `SKILL.md` — 法规标准 Writer (~335 tok)

## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/

- `SKILL.md` — 智能填槽 (~632 tok)

## backend/package/yuxi/agents/skills/buildin/template-recommender/

- `SKILL.md` — 段落模板智能推荐 (~533 tok)

## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — Pydantic: PresentArtifactsInput (~7610 tok)

## backend/package/yuxi/agents/toolkits/debug/


## backend/package/yuxi/agents/toolkits/kbs/


## backend/package/yuxi/agents/toolkits/mysql/


## backend/package/yuxi/config/


## backend/package/yuxi/config/static/


## backend/package/yuxi/knowledge/

- `base.py` — FileStatus: load_metadata, get_create_params_config, validate_additional_params, normalize_additiona (~18255 tok)

## backend/package/yuxi/knowledge/chunking/


## backend/package/yuxi/knowledge/chunking/ragflow_like/


## backend/package/yuxi/knowledge/chunking/ragflow_like/parsers/


## backend/package/yuxi/knowledge/chunking/ragflow_like/utils/


## backend/package/yuxi/knowledge/eval/


## backend/package/yuxi/knowledge/graphs/


## backend/package/yuxi/knowledge/graphs/adapters/


## backend/package/yuxi/knowledge/implementations/


## backend/package/yuxi/knowledge/parser/

- `unified.py` — Unified parser module for markdown conversion. (~4858 tok)

## backend/package/yuxi/knowledge/utils/


## backend/package/yuxi/models/


## backend/package/yuxi/plugins/


## backend/package/yuxi/plugins/parser/


## backend/package/yuxi/repositories/

- `agent_repository.py` — AgentRepository: is_builtin_agent, resolve_agent_is_subagent, normalize_agent_share_config, user_can (~7166 tok)
- `domain_factory_repository.py` — Domain Factory 数据访问层 - Repository (~9382 tok)

## backend/package/yuxi/services/

- `chat_service.py` — Agent runtime streaming service. (~15101 tok)
- `domain_factory_service.py` — Domain Factory Service - 领域知识工厂服务层 (~62945 tok)
- `file_preview.py` — OfficePreviewConversionError: is_office_pdf_preview_file, is_ascii_text_file, is_binary_preview_type (~2725 tok)
- `ref_resolver.py` — {{REF:chXX/表X-Y}} 位置编号解析器。assemble 时扫各章 content_md 现算。 (~626 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `manager.py` — PostgreSQL 数据库管理器 - 支持知识库和业务数据 (~15286 tok)
- `models_domain_factory.py` — Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表 (~3859 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/


## backend/server/utils/

- `lifespan.py` — lifespan (~1381 tok)

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


## backend/test/unit/agents/

- `test_auto_artifacts.py` — Test _auto_present_artifacts: scan outputs dir and register .md files as artifacts. (~739 tok)

## backend/test/unit/agents/middlewares/

- `test_excluded_tools.py` — _Request: override, test_sync_filters_excluded_tools, handler, test_async_filters_excluded_tools + 1 (~994 tok)

## backend/test/unit/backends/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/repositories/

- `test_chapter_writer_subagent.py` — test_ensure_chapter_writer_subagent_idempotent (~184 tok)

## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/

- `test_outline_producer.py` — test_group_assets_by_chapter_buckets_by_chapter, test_assemble_deterministic_outline_fields, test_ll (~1466 tok)
- `test_ref_resolver.py` — test_resolve_table_ref_and_flag_unresolved, test_chapters_merged_in_order, test_resolve_section_ref (~355 tok)

## backend/test/unit/storage/

- `test_domain_factory_outline_repo.py` — test_upsert_and_get_outline, test_list_chapter_keys_and_backfill (~530 tok)
- `test_report_repo.py` — test_create_report_and_chapter_and_pps (~384 tok)

## backend/test/unit/toolkits/

- `test_domain_factory_tools.py` — test_get_chapter_outline_tool_returns_dict, test_get_templates_tool_returns_list (~330 tok)
- `test_report_tools.py` — test_create_report_tool, test_get_report_and_set_pps_tools, test_save_chapter_tool, test_save_chapte (~1302 tok)

## docker/

- `api.Dockerfile` — 使用轻量级Python基础镜像 (~532 tok)
- `web.Dockerfile` (~257 tok)

## docker/nginx/


## docker/sandbox_provisioner/

- `Dockerfile` — Docker container definition (~97 tok)

## docker/volumes/milvus/etcd/member/snap/


## docker/volumes/milvus/milvus/data/pprof/


## docker/volumes/milvus/milvus/rdb_data/


## docker/volumes/milvus/milvus/rdb_data_meta_kv/


## docker/volumes/milvus/minio/.minio.sys/


## docker/volumes/milvus/minio/.minio.sys/buckets/.bloomcycle.bin/


## docker/volumes/milvus/minio/.minio.sys/buckets/.usage-cache.bin/


## docs/design/


## docs/develop-guides/

- `changelog.md` — 版本变更记录 (~10896 tok)

## docs/superpowers/plans/

- `2026-07-11-writing-backbone.md` — 写作侧确定性骨架 Implementation Plan (子项目 2) (~9895 tok)
- `2026-07-12-agent-compliance.md` — Agent 合规性强制 Implementation Plan (P0) (~603 tok)
- `2026-07-13-coal-eia-writer-v2-plan.md` — 环评写作助手 v2 实施计划 (~7360 tok)

## docs/superpowers/specs/

- `2026-07-11-writing-backbone-design.md` — 写作侧确定性骨架（Sub-project 2）— design (~1627 tok)
- `2026-07-12-agent-compliance-design.md` — Agent 合规性强制(P0)— design (~471 tok)
- `2026-07-12-writer-agent-compliance-design.md` — 写作侧 Agent 合规性（P0）— design (~1315 tok)
- `2026-07-13-coal-eia-writer-v2-design.md` — 环评写作助手 v2 设计文档 (~2627 tok)

## docs/vibe/


## web/


## web/src/apis/


## web/src/assets/css/


## web/src/assets/icons/files/


## web/src/components/


## web/src/components/domain-factory/

- `EtlWorkbench.vue` — Vue: setup (~21525 tok)

## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/stores/


## web/src/views/

