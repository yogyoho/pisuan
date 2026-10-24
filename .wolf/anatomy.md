# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-24T14:38:02.130Z
> Files: 48 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/

- `syncdev-syncs-uncommitted-backend.md` (~162 tok)

## ../../Users/Lenovo/AppData/Local/Temp/


## ../../Users/Lenovo/AppData/Local/Temp/claude/


## ../../Users/Lenovo/AppData/Local/Temp/eia-values/


## ../../Users/Lenovo/AppData/Local/Temp/pisuan-visual-qa/


## ../../tmp/


## ../../项目管理/环评引用的国标/


## ./


## .archify/workflow-corpus-writer-20261023-071348/

- `candidate.json` (~2527 tok)

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

- `SKILL.md` — 分章管线设计：docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md §3。 (~2308 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-reviewer/

- `SKILL.md` — 审查设计：docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md §4。 (~884 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — pisuan 移植（2026-09-30）：运行时映射与改编范围见 (~6086 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/

- `baseline.md` — 节角色范式：现状与概况节（baseline） (~380 tok)
- `conclusion.md` — 节角色范式：结论与论证收束节（conclusion） (~326 tok)
- `process.md` — 节角色范式：程序与过程节（process） (~223 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/

- `build_output.py` — coal-eia-report v2 — build_output.py：单次原子组装（步骤5–7）+ 章门（两层模型）。 (~16087 tok)
- `corpus_meta.py` — 切片 + 人工核正 (~3965 tok)
- `derive_globals.py` — global_families 派生：data_expectations.json 顶层增 global_families（build 派生，不手拍）。 (~1022 tok)
- `formula_runner.py` — coal-eia-report v2（T2 重写） — formula_runner.py：冻结计算层（步骤2，门2 的数据面）。 (~17429 tok)
- `ingest.py` — coal-eia-report v2 (T1 副本——geo 逻辑原样，见 docs/designs/coal-eia-report-v2.md 两层模型改造点清单) — ingest.py：data (~10583 tok)
- `paradigm_role.py` — 节角色解析器：stage + section_id -> paradigm role（派发契约查表唯一入口）。 (~556 tok)
- `progress.py` — coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。 (~11526 tok)
- `style_targets.py` — 文风基准生成：从 samples_bank/<stage>/slices/ 实测每章指标，产出 style_targets/<stage>.json。 (~1410 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/

- `test_chapter_state_machine.py` — 分章模式状态机测试：REVIEWED/CONFIRMED 增态 + confirm-chapter + 分章 next 编排。 (~2120 tok)
- `test_corpus_variant.py` — corpus_meta variant 变体标注测试：标题即判规则 + --add-variant 就地补标注零扰动。 (~1117 tok)
- `test_formula_runner_scope.py` — formula_runner --chapters 章级切片测试：scope 解析 + compute 块 guard + 增量冻结合并 + SCOPE_FALLBACK。 (~1281 tok)
- `test_formula_runner_static_transcribe.py` — bug-4137 静态转录回归：stage forms JSON 族的顶层标量登记为 {family}.{field} 槽位。 (~860 tok)
- `test_global_families.py` — global_families 派生测试：冻结依赖族派生 + ingest check --global-only 门1 全局模式。 (~1641 tok)
- `test_paradigm_roles.py` — 范式角色分型测试：roles/<stage>.json schema + stage 全覆盖 + ch13 重归型钉死 + 解析器拒派语义。 (~1007 tok)
- `test_style_gate.py` — 文风门测试：四规则判定 + banned 词节级归因 + 基准缺失/章 ABSENT 的 skip 上报。 (~1196 tok)
- `test_style_targets.py` — style_targets 生成测试：mini-bank fixture 精确数值 + 章目录对齐纪律（清单外目录忽略上报）。 (~1108 tok)

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

- `eia_standard_repository.py` — 环评标准条目人工核实裁决仓储（eia_standard_reviews，P3 运营唯一真相）。 (~510 tok)

## backend/package/yuxi/services/

- `eia_limit_extract_service.py` — 语料限值提取服务（spec 2026-10-19 W2/W3 后端 + Task 13 B 通道）。试跑→暂存；裁决→转正；候选→立表；引用→W1 辅助。 (~4128 tok)
- `eia_limit_row_mapping.py` — 限值行形 ↔ standard_indicators 扁平指标双向映射（P1 合流；spec 2026-10-22 §4）。 (~1046 tok)

## backend/package/yuxi/services/skills/

- `shared.py` — get_skill_dependency_options, confirm_skill_install_draft, delete_skill, delete_skills_batch (~6747 tok)

## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/


## backend/package/yuxi/utils/


## backend/scripts/


## backend/server/


## backend/server/routers/


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

- `test_builtin_discovery.py` — 文件发现、真实 PostgreSQL 落库与 HTTP 可见性。 (~2749 tok)

## backend/test/unit/

- `test_eia_standard_service.py` — eia_standard_service 纯函数单测：核实载荷校验（action 白名单、note 类型、未知字段拒收）+ 引用码归一。 (~2032 tok)

## backend/test/unit/agents/skills/

- `test_chapter_skill_assets_sync.py` — chapter-writer 资产同步守卫：两包 scripts/ + references/ 逐文件字节一致（spec §5 打包契约）。 (~989 tok)

## backend/test/unit/backends/


## backend/test/unit/extensions/


## backend/test/unit/graphs/


## backend/test/unit/knowledge/


## backend/test/unit/knowledge/eval/


## backend/test/unit/middlewares/


## backend/test/unit/plugins/


## backend/test/unit/routers/


## backend/test/unit/server/


## backend/test/unit/services/

- `test_eia_canonical_md_goldens.py` — 金标准回归：canonical md 内核 × 33 份真实语料（宿主机专用，开发机跑）。 (~1066 tok)
- `test_eia_limit_extract_service.py` — eia_limit_extract_service 单测：试跑幂等 / 行裁决转正 / 候选立表。 (~2459 tok)
- `test_eia_limit_row_mapping.py` — 限值行形 ↔ 扁平指标双向映射单测（P1 合流 Task 2）。 (~1098 tok)

## backend/test/unit/services/skills/

- `test_skill_service.py` — _UnitOfWork: commit, rollback, test_allowed_skill_access_levels_by_role, test_create_remote_skill_dr (~21166 tok)

## backend/test/unit/storage/


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

- `changelog.md` — 版本变更记录 (~36480 tok)

## docs/intro/


## docs/superpowers/plans/

- `2026-10-22-standards-limit-merge.md` — P1 标准限值合流（Q2=A 物理合并）实施计划 (~10985 tok)
- `2026-10-24-chapter-writer-reviewer.md` — 分章节环评写作与独立合规校验技能 实施计划 (~2563 tok)

## docs/superpowers/specs/

- `2026-10-24-chapter-writer-reviewer-design.md` — 分章节环评写作技能与独立合规校验技能 设计文档 (~2312 tok)

## docs/vibe/

- `2026-10-23-coal-eia-writer-writing-test-plan.md` — coal-eia-writer 环评报告写作测试方案（B 先行 · 对比法 · 页面验证性测试） (~926 tok)
- `2026-10-24-chapter-writer-reviewer-smoke.md` — 分章写作 + 独立合规审查 冒烟记录（Task 9） (~1525 tok)
- `2026-10-24-writing-test-defects.md` — 横城 B 测试对比评估与缺陷台账 (~1110 tok)

## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/


## scripts/

- `sync_chapter_skill.py` — chapter-writer 技能包资产同步：coal-eia-writer 的 scripts/ + references/ 单向镜像覆盖。 (~1198 tok)

## web/


## web/e2e/fixtures/


## web/public/providers-logo/


## web/src/apis/


## web/src/assets/css/


## web/src/components/


## web/src/components/common/


## web/src/components/domain-factory/


## web/src/components/eia-data/


## web/src/components/factory-core/

- `GeneralLayout.vue` — Vue: setup (~1613 tok)

## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/

- `index.js` — Declares AppLayout (~3642 tok)

## web/src/stores/


## web/src/utils/


## web/src/views/

- `DomainFactoryView.vue` — Vue: 通用域, setup (~7812 tok)
- `GeneralOverviewView.vue` — Vue: setup (~5661 tok)
- `GeneralWorkbenchView.vue` — Vue: setup (~357 tok)

## web/test/unit/

- `.wolf/chapter-smoke/dialog/auto_approve.py` — 冒烟受控自动批准循环（execute/read 才批，ask卡/write_file 停）；依赖 drive.py，DB 对齐防 409。~110 行
- `.wolf/chapter-smoke/outputs/ch2-横城章稿.md` — 冒烟产物：agent 生成的 ch2 注入前章稿（9821 字符，57 SLOT+10 TABLE）
- `.wolf/chapter-smoke/outputs/ch2-合规审查发现单.md` — reviewer 章级审查发现单（FAIL1/WARN4/PASS3+移交3）
- `.wolf/chapter-smoke/dialog/q_latest.py` — 容器内查 agent_runs 最新 run 的小脚本（auto_approve 依赖）
