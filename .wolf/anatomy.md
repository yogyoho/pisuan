# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-11-03T11:25:58.352Z
> Files: 30 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/

- `gitea-admin-api-quirks.md` (~148 tok)
- `integration-flow-tests-wiped-shared-db.md` (~295 tok)

## ../../Users/Lenovo/AppData/Local/Temp/


## ../../Users/Lenovo/AppData/Local/Temp/claude/


## ../../Users/Lenovo/AppData/Local/Temp/eia-values/


## ../../Users/Lenovo/AppData/Local/Temp/pisuan-visual-qa/


## ../../tmp/


## ../../项目管理/环评引用的国标/


## ../pisuan-localized/


## ../pisuan-localized/docker/volumes/pisuan/threads/shared/admin/workspace/workspace/


## ../pisuan-localized/docker/volumes/pisuan/threads/shared/admin/workspace/workspace/eia-report/hengcheng-ch3/data/


## ../pisuan-localized/docker/volumes/pisuan/threads/shared/admin/workspace/workspace/hxmc-planning-rev2-chapter/state/


## ./


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

- `SKILL.md` — 分章管线设计：docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md §3。 (~5103 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/references/stages/


## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/


## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/tests/


## backend/package/yuxi/agents/skills/buildin/coal-eia-reviewer/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — pisuan 移植（2026-09-30）：运行时映射与改编范围见 (~6608 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/

- `build_output.py` — coal-eia-report v2 — build_output.py：单次原子组装（步骤5–7）+ 章门（两层模型）。 (~17668 tok)
- `progress.py` — coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。 (~16822 tok)
- `sample_fragments.py` — 样例片段包生成器：stage + 章节 → samples_bank 同章真实切片（派发注入唯一参照来源，bug-4147）。 (~3831 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/

- `test_depth_floor_projection.py` — 深度基线投影折算与真源统一测试（bug-4148/4149 + 评审 P0-1）： (~2223 tok)
- `test_progress_state_lock.py` — 状态锁测试（bug P3-11）：变更命令互斥持锁/next·status 只读不持锁/崩溃残留超时接管/异常释放。 (~822 tok)
- `test_sample_fragments.py` — 样例片段包测试（bug-4147）：主导报告选择 / 预算节标题截断 / 空章降级 rc=2 / 确定性。 (~4629 tok)

## backend/package/yuxi/agents/skills/buildin/compliance-checker/


## backend/package/yuxi/agents/skills/buildin/deep-reporter/


## backend/package/yuxi/agents/skills/buildin/reporter/


## backend/package/yuxi/agents/skills/buildin/slot-filler/


## backend/package/yuxi/agents/skills/buildin/template-recommender/


## backend/package/yuxi/agents/toolkits/


## backend/package/yuxi/agents/toolkits/buildin/


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


## backend/package/yuxi/services/

- `eia_corpus_task_service.py` — eia_corpus_task_service.py — 环评文件库 P2 后台任务（KB 推送 / 语料加工 / 绑定）。 (~4112 tok)
- `eia_lexicon_service.py` — 环评数值护栏词表运营服务（DB 覆盖层 + overrides 物化）。 (~6198 tok)
- `eia_meta_service.py` — 环评语料元数据人工标注服务（P2：DB 运营唯一真相 + 显式导出物化人工层文件）。 (~3151 tok)
- `eia_paradigm_service.py` — 写作范式层编辑服务（s12/s13：DB 草稿=编辑唯一真相 + admin 导出物化回写 references/paradigms/*）。 (~4171 tok)
- `eia_refs_git.py` — 环评 refs 数据仓 git 链（批次2）：导出物化 → refs-repo 工作树 commit → push 本地 Gitea。 (~1178 tok)
- `eia_refs_propagate.py` — 导出物化后的运行时传播：双包收敛（bank 输出家族镜像）→ 栈包 → skill-sources/shared（投影由 Agent Run 初始化自动刷）。 (~1211 tok)

## backend/package/yuxi/services/skills/

- `shared.py` — get_skill_dependency_options, confirm_skill_install_draft, delete_skill, delete_skills_batch (~6916 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/


## backend/package/yuxi/utils/


## backend/scripts/


## backend/scripts/governance/


## backend/server/


## backend/server/routers/

- `domain_factory_router.py` — Domain Factory API Router - 领域知识工厂路由 (~23027 tok)

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


## backend/test/integration/services/

- `_flow_isolation.py` — eia 服务层流测试的共享运行库隔离助手。 (~307 tok)
- `test_eia_lexicon_service_flow.py` — eia_lexicon 服务层全链路集成测试（不经 HTTP，无凭据依赖）。 (~2393 tok)
- `test_eia_meta_service_flow.py` — eia_meta 服务层全链路集成测试（不经 HTTP，无凭据依赖）。 (~1670 tok)
- `test_eia_standard_service_flow.py` — eia_standard 服务层全链路集成测试（不经 HTTP，无凭据依赖）。 (~1703 tok)

## backend/test/integration/storage/


## backend/test/scripts/


## backend/test/unit/

- `test_eia_paradigm_service.py` — eia_paradigm_service 单元测试：锚点校验 / 两键纪律 / preview 不写盘 / 导出字节纪律 / 漂移 / 回滚 / 撤回 / 空批拒绝。 (~4322 tok)

## backend/test/unit/agents/


## backend/test/unit/agents/skills/


## backend/test/unit/backends/


## backend/test/unit/extensions/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/repositories/


## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/

- `test_eia_corpus_process.py` — eia_corpus_process 单测：KB 为准选集 / workdir 物化 / 真 bank_compile 迷你重编译 / corpus_meta 合并 / fail fast。 (~3356 tok)
- `test_eia_refs_propagate.py` — 导出物化运行时传播的单测：重播/内容跳过/残留清理/bank 输出家族双包镜像（隔离 tmp 根，不触真实运行栈）。 (~1818 tok)

## backend/test/unit/services/skills/


## backend/test/unit/toolkits/


## docker/


## docker/minio/


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

- `changelog.md` — 版本变更记录 (~43744 tok)

## docs/intro/


## docs/superpowers/plans/


## docs/superpowers/specs/


## docs/vibe/

- `2026-10-09-eia-lexicon-stack.md` — 数值护栏词表全栈设计与实现记录（环评域数据工厂 · 一期主体） (~1729 tok)
- `2026-11-01-eia-refs-local-git-chain.md` — 2026-11-01 环评域数据文件本地 git 化链路（Gitea + docker 卷）设计定稿 (~1372 tok)

## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/


## scripts/


## scripts/governance/

- `refs_repo_distribute.py` — refs 数据仓分发：Gitea pull → skill-sources/shared → projections（批次2 分发步）。 (~1687 tok)

## web/


## web/e2e/fixtures/


## web/public/providers-logo/


## web/src/apis/


## web/src/assets/css/


## web/src/components/


## web/src/components/common/


## web/src/components/domain-factory/


## web/src/components/eia-data/

- `LexiconPanel.vue` — Vue component (~12496 tok)

## web/src/components/factory-core/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/


## web/src/stores/


## web/src/utils/


## web/src/views/


## web/test/unit/

