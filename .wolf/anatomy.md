# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-07-11T15:13:41.686Z
> Files: 33 tracked | Anatomy hits: 0 | Misses: 0

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


## backend/package/yuxi/agents/backends/


## backend/package/yuxi/agents/backends/sandbox/


## backend/package/yuxi/agents/buildin/


## backend/package/yuxi/agents/buildin/chatbot/


## backend/package/yuxi/agents/buildin/deep_agent/


## backend/package/yuxi/agents/middlewares/


## backend/package/yuxi/agents/skills/buildin/

- `__init__.py` — Declares from (~1006 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — 煤矿环评编排者：create_report→派 chapter-writer 子 agent→assemble_report；保留 PPS 参数参考/富文本规范/章节速查 (~1050 tok)

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

- `tools.py` — Pydantic: PresentArtifactsInput; 写作侧 5 工具 create_report/get_report/set_pps_param/save_chapter/assemble_report (buildin category) (~5700 tok)

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


## backend/package/yuxi/knowledge/parser/

- `unified.py` — Unified parser module for markdown conversion. (~4858 tok)

## backend/package/yuxi/knowledge/utils/


## backend/package/yuxi/models/


## backend/package/yuxi/plugins/


## backend/package/yuxi/plugins/parser/


## backend/package/yuxi/repositories/

- `agent_repository.py` — AgentRepository: is_builtin_agent, resolve_agent_is_subagent, normalize_agent_share_config, user_can, ensure_chapter_writer_subagent (写作侧子 agent 注册) (~6099 tok)
- `domain_factory_repository.py` — Domain Factory 数据访问层 - Repository + 写作侧 report/chapter/pps CRUD (create_report/get_report_snapshot/upsert_pps_param/upsert_chapter/lookup_chapter_order/list_chapters/mark_assembled) (~8878 tok)

## backend/package/yuxi/services/

- `domain_factory_service.py` — Domain Factory Service - 领域知识工厂服务层 (~62435 tok)
- `ref_resolver.py` — {{REF:chXX/表X-Y}} 位置编号解析器。assemble 时扫各章 content_md 现算。 (~557 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/

- `manager.py` — PostgreSQL 数据库管理器 - 支持知识库和业务数据 (~15286 tok)
- `models_domain_factory.py` — Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表 + 写作侧 report/chapter/pps 三表 (DomainFactoryReport/Chapter/PPS) (~3866 tok)

## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/


## backend/server/utils/

- `lifespan.py` — lifespan (~1320 tok)

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
- `test_report_tools.py` — test_create_report_tool, test_get_report_and_set_pps_tools, test_save_chapter_tool, test_save_chapte (~1062 tok)

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

- `changelog.md` — 版本变更记录 (~10896 tok)

## docs/superpowers/plans/

- `2026-07-11-writing-backbone.md` — 写作侧确定性骨架 Implementation Plan (子项目 2) (~9895 tok)

## docs/superpowers/specs/

- `2026-07-11-writing-backbone-design.md` — 写作侧确定性骨架（Sub-project 2）— design (~1627 tok)

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

