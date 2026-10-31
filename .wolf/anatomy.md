# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-31T01:44:36.469Z
> Files: 57 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/


## ../../Users/Lenovo/AppData/Local/Temp/


## ../../Users/Lenovo/AppData/Local/Temp/claude/


## ../../Users/Lenovo/AppData/Local/Temp/eia-values/


## ../../Users/Lenovo/AppData/Local/Temp/pisuan-visual-qa/


## ../../tmp/


## ../../项目管理/环评引用的国标/


## ../pisuan-localized/docker/volumes/pisuan/threads/shared/admin/workspace/workspace/

- `DEPRECATED-首次尝试遗留现场说明.md` — ⚠️ 本目录下的 state/ data/ outputs/ 为首次编写尝试遗留（勿复用） (~119 tok)

## ../pisuan-localized/docker/volumes/pisuan/threads/shared/admin/workspace/workspace/hxmc-planning-rev2-chapter/state/

- `progress.json` (~3790 tok)

## ./

- `.git-commit-msg-bug4176.txt` (~164 tok)
- `.git-commit-msg-wolf.txt` (~116 tok)

## .archify/workflow-corpus-writer-20261023-071348/


## .claude/


## .claude/rules/


## .claude/skills/


## .claude/worktrees/agent-a0d6fa8031673041d/web/src/components/eia-data/


## .claude/worktrees/agent-ad806a5ba88b3016a/backend/package/yuxi/knowledge/chunking/ragflow_like/parsers/


## .claude/worktrees/agent-ad806a5ba88b3016a/backend/test/unit/backends/


## .claude/worktrees/agent-aebd7b9bf4ee92274/web/src/components/eia-data/


## .claude/worktrees/t9-tune/backend/package/yuxi/services/


## .claude/worktrees/t9-tune/backend/test/unit/services/


## .claude/worktrees/task13-llm-cls/backend/package/yuxi/services/


## .claude/worktrees/task13-llm-cls/backend/server/routers/


## .claude/worktrees/task13-llm-cls/backend/test/unit/services/


## .claude/worktrees/task13-llm-cls/docs/develop-guides/


## .claude/worktrees/task14-enrich/backend/package/yuxi/agents/toolkits/buildin/


## .claude/worktrees/task14-enrich/backend/package/yuxi/extensions/regulation_library/


## .claude/worktrees/task14-enrich/backend/test/unit/extensions/


## .claude/worktrees/task14-enrich/docs/develop-guides/


## .claude/worktrees/task15-table-chunking/backend/package/yuxi/extensions/regulation_library/


## .claude/worktrees/task15-table-chunking/backend/package/yuxi/knowledge/chunking/ragflow_like/


## .claude/worktrees/task15-table-chunking/backend/package/yuxi/knowledge/chunking/ragflow_like/parsers/


## .claude/worktrees/task15-table-chunking/backend/test/unit/extensions/


## .claude/worktrees/task15-table-chunking/backend/test/unit/knowledge/


## .claude/worktrees/task15-table-chunking/docs/develop-guides/


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


## backend/.../coal-eia-writer/（2026-10-24 chapter-writer Task 1 新增）


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


## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/

- `SKILL.md` — 分章管线设计：docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md §3。 (~4625 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/

- `progress.py` — coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。 (~15368 tok)
- `style_targets.py` — 文风基准生成：从 samples_bank/<stage>/slices/ 实测每章指标，产出 style_targets/<stage>.json。 (~1568 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/tests/

- `test_build_output_fig.py` — R5 插图占位回归：{{FIG:图名}} 合法保留 + 空图名/畸形 FAIL + SLOT/TABLE 残留不回归。 (~480 tok)
- `test_chapter_state_machine.py` — 分章模式状态机测试：REVIEWED/CONFIRMED 增态 + confirm-chapter + 分章 next 编排。 (~2346 tok)
- `test_gate_credential_link.py` — 门凭据时效链测试（bug-4146）：VERIFIED/REVIEWED/CONFIRMED 三通道全部凭「最近一次真跑门」放行。 (~1576 tok)
- `test_interaction_cards.py` — 章节编写交互卡点测试（卡A计划卡 + 卡B范例挑选 + next 联动 + 篇幅模式）： (~1793 tok)
- `test_progress_path_guard.py` — 账面路径守卫测试（bug-4172）：init/gate/run-stage 对 stage_path/data_dir 的存在性快速失败。 (~951 tok)
- `test_run_stage_chapters.py` — run-stage freeze --chapters 透传（bug-4143 方案A）：目标章集模式切片冻结，缺省全量零变化。 (~575 tok)
- `test_style_targets.py` — style_targets 生成测试：mini-bank fixture 精确数值 + 章目录对齐纪律（清单外目录忽略上报）。 (~1180 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-reviewer/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — pisuan 移植（2026-09-30）：运行时映射与改编范围见 (~6343 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/

- `progress.py` — coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。 (~15368 tok)
- `sample_fragments.py` — 样例片段包生成器：stage + 章节 → samples_bank 同章真实切片（派发注入唯一参照来源，bug-4147）。 (~2000 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/

- `test_chapter_state_machine.py` — 分章模式状态机测试：REVIEWED/CONFIRMED 增态 + confirm-chapter + 分章 next 编排。 (~2346 tok)
- `test_interaction_cards.py` — 章节编写交互卡点测试（卡A计划卡 + 卡B范例挑选 + next 联动 + 篇幅模式）： (~1793 tok)
- `test_progress_path_guard.py` — 账面路径守卫测试（bug-4172）：init/gate/run-stage 对 stage_path/data_dir 的存在性快速失败。 (~951 tok)
- `test_run_stage_chapters.py` — run-stage freeze --chapters 透传（bug-4143 方案A）：目标章集模式切片冻结，缺省全量零变化。 (~575 tok)
- `test_sample_fragments.py` — 样例片段包测试（bug-4147）：主导报告选择 / 预算节标题截断 / 空章降级 rc=2 / 确定性。 (~2302 tok)

## backend/package/yuxi/agents/skills/buildin/compliance-checker/


## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/


## backend/package/yuxi/agents/skills/buildin/template-recommender/


## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/

- `tools.py` — Pydantic: DoubaoSearchInput (~13276 tok)

## backend/package/yuxi/agents/toolkits/debug/


## backend/package/yuxi/agents/toolkits/kbs/


## backend/package/yuxi/agents/toolkits/mysql/


## backend/package/yuxi/config/


## backend/package/yuxi/config/static/


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

- `domain_factory_repository.py` — Domain Factory 数据访问层 - Repository (~13976 tok)

## backend/package/yuxi/services/

- `domain_factory_service.py` — Domain Factory Service - 领域知识工厂服务层 (~80186 tok)
- `graph_builder.py` — 知识图谱构建服务：将领域工厂结构化数据写入 Neo4j 图谱 (~19261 tok)
- `graph_query_service.py` — 图谱查询服务:封装 Cypher,供工具直查 Neo4j 图谱。 (~4951 tok)

## backend/package/yuxi/services/skills/


## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/


## backend/package/yuxi/utils/

- `__init__.py` — get_docker_safe_url (~181 tok)
- `string_utils.py` — 通用字符串处理工具。 (~345 tok)

## backend/scripts/


## backend/scripts/governance/

- `dedomain_chapter_templates_graph.py` — 去领域化图谱侧存量迁移：ChapterTemplate / DomainOutline 的 domain 'coal' → 'general'，并重写内嵌域的节点 id。 (~1328 tok)
- `merge_chapter_templates.py` — 存量 ChapterTemplate 治理脚本（bug-4167 spec §4.4）：归一 canonical、合并重复、纠挂、编号结构化、删测试子树、meta 回写。 (~9250 tok)

## backend/server/


## backend/server/routers/

- `domain_factory_router.py` — Domain Factory API Router - 领域知识工厂路由 (~23002 tok)

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

- `test_domain_factory_api.py` — 领域知识工厂 router 集成测试（/api/domain-factory/*）。 (~1332 tok)

## backend/test/integration/services/


## backend/test/scripts/

- `test_merge_chapter_templates.py` — merge_chapter_templates 治理脚本单测：纯函数规划逻辑 + dry-run 零写断言（不连库）。 (~6015 tok)

## backend/test/unit/


## backend/test/unit/agents/

- `test_builtin_discovery.py` — 内置定义发现与失败边界。 (~2345 tok)

## backend/test/unit/agents/skills/


## backend/test/unit/backends/


## backend/test/unit/extensions/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/repositories/

- `test_agent_repository_deep_research.py` — CollectingDb: add, test_discovered_presets_creates_orchestrator_and_subagents, get_by_slug, test_dis (~694 tok)
- `test_agent_repository.py` — FakeDb: add, test_merge_agent_config_json_preserves_omitted_context_fields_and_hidden_skills, test_m (~4132 tok)
- `test_domain_factory_domain_aliases.py` — 去领域化常量与别名归一单元测试（设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md）。 (~213 tok)

## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/

- `test_normalize_chapter_key.py` — 章节标题归一化与聚合身份键解析单测（不连图库）。 (~1311 tok)
- `test_outline_detail_assembler.py` — get_outline_template_detail 薄装配测试：图谱 meta + PG 大纲行富字段合并（bug-4167）。 (~1158 tok)
- `test_outline_producer.py` — test_group_assets_by_chapter_buckets_by_chapter, test_assemble_deterministic_outline_fields, test_ll (~2228 tok)

## backend/test/unit/services/skills/


## backend/test/unit/storage/

- `test_domain_factory_outline_repo.py` — test_upsert_and_get_outline, test_list_chapter_keys_and_backfill, test_upsert_outline_normalizes_can (~694 tok)

## backend/test/unit/toolkits/


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

- `changelog.md` — 版本变更记录 (~39768 tok)

## docs/intro/


## docs/superpowers/plans/

- `2026-10-29-dedomain-behavioral.md` — 方案 B：通用域去领域化（行为级）Implementation Plan (~6751 tok)

## docs/superpowers/specs/

- `2026-10-29-outline-template-idempotency-design.md` — 大纲模板幂等与缺项修复设计（bug-4167） (~1316 tok)

## docs/vibe/

- `2026-10-27-chapter-writer-user-test-plan.md` — 分章节环评报告写作 · 用户测试方案 (~1123 tok)
- `2026-10-27-post-confirm-revision-and-figure-slots.md` — 交付后章节修改 + 插图占位 · 需求文档 (~476 tok)
- `2026-10-29-chapter-writer-clear-rerun-test.md` — 分章管线清空重测报告（planning_eia / ch2 全自主轮） (~2270 tok)
- `2026-10-29-etl-pipeline-dedomain-design.md` — 通用域知识工厂 ETL 管线：现状梳理与去领域化设计 (~2963 tok)

## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/


## scripts/


## scripts/governance/

- `dedomain_coal_to_general.py` — 去领域化存量迁移：domain_code 'coal' 等历史域值 → 'general'（设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.m (~1725 tok)

## web/


## web/e2e/fixtures/


## web/public/providers-logo/


## web/src/apis/

- `domain_factory_api.js` — Domain Knowledge Factory API (~3026 tok)

## web/src/assets/css/


## web/src/components/


## web/src/components/common/


## web/src/components/domain-factory/

- `AttributionTaskTable.vue` — Vue: setup (~1209 tok)
- `DataSourceDashboard.vue` — Vue: setup (~8137 tok)
- `OutlineTemplate.vue` — Vue: setup (~6104 tok)

## web/src/components/eia-data/


## web/src/components/factory-core/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/


## web/src/stores/


## web/src/utils/


## web/src/views/

- `DomainEntityBuilderView.vue` — Vue component (~13930 tok)
- `GeneralDataView.vue` — Vue: setup (~139 tok)
- `PromptConfigView.vue` — Vue: setup (~3069 tok)

## web/test/unit/

