# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-11-06T10:40:24.402Z
> Files: 20 tracked | Anatomy hits: 0 | Misses: 0

## ../../Users/Lenovo/.claude/plans/


## ../../Users/Lenovo/.claude/projects/C--workspace-pisuan/memory/

- `localhost-5173-is-localized-stack.md` (~371 tok)

## ../../Users/Lenovo/AppData/Local/Temp/

- `fill_yining_csvs.py` — Fill Yining ch3 data-request CSVs (test data, C route). (~1545 tok)

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

- `SKILL.md` — 分章管线设计：docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md §3。 (~5326 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/references/stages/


## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/

- `build_output.py` — coal-eia-report v2 — build_output.py：单次原子组装（步骤5–7）+ 章门（两层模型）。 (~18002 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/tests/

- `test_emit_chapter_doc.py` — 章级成稿文档（--emit-doc）测试：门 PASS 凭据写盘 / FAIL 不写盘 / 文件名安全化 / 幂等。 (~1214 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-reviewer/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/

- `SKILL.md` — pisuan 移植（2026-09-30）：运行时映射与改编范围见 (~6803 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/samples_bank/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/section_expectations/


## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/

- `briefing.py` — Agent 业务内容简报渲染器（交互体验重塑 2026-11-04，docs/vibe/2026-11-04-agent-briefing-layer.md）。 (~5208 tok)
- `progress.py` — coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。 (~17886 tok)
- `sample_fragments.py` — 样例片段包生成器：stage + 章节 → samples_bank 同章真实切片（派发注入唯一参照来源，bug-4147）。 (~3835 tok)

## backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/

- `test_briefing.py` — briefing 渲染器测试：outline/chapter/data-request/calc-summary 四子命令。 (~2817 tok)
- `test_progress_guidance_paths.py` — progress.py next 指引路径口径回归（bug-4213）：COLLECTING 两分支（无 choice/已选）指引的 (~526 tok)

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

- `eia_formula_service.py` — 环评 formulas 参数参考值编辑服务（P3-1：DB 覆盖唯一真相 + 显式导出物化 formulas.json）。 (~2356 tok)

## backend/package/yuxi/services/skills/


## backend/package/yuxi/storage/minio/


## backend/package/yuxi/storage/postgres/


## backend/package/yuxi/utils/


## backend/package/pisuan/repositories/

- `domain_entity_category_repository.py` — 实体分类字典数据访问（v23）：`list_categories`（按 sort_order, code；可含停用）/`get`/`create`（未指定 sort_order 时取 max+10 排尾部）/`update`（只改 name_cn/description/sort_order/is_active，code 不可改）/`delete`/`reorder`（缺失与重复校验，sort_order 重算为 10/20/30…）/`rank_map`（code→sort_order，供泛化 prompt 排序）；`validate_category_code` 强制 `^[a-z][a-z0-9_]{0,63}$` (~112 行)


## backend/scripts/

- `verify_entity_chain_e2e.py` — 通用域实体双链路 E2E（Q1 实体注入泛化/Q2 LLM 提议→确认级联），探针+零残留清理（2026-11-13）。 (~1800 tok)
- `verify_source_etl_e2e.py` — E2E ①：合成 docx→真实 worker ETL→WAITING_REVIEW，断言数据源列表/工作台详情/段落树/泛化 slot/校验只读；快照学习模板 match_count 基线写入 `/tmp/e2e_probe_matchcounts.json`，任务 id 写 `/tmp/e2e_probe_task_id.txt` 供 ③ 消费（2026-11-14）。 (~1600 tok)
- `verify_workbench_remap_e2e.py` — E2E ②：证明「确认实体 remap 匹配源是静态 17 类型文件」断链 + 「旧快照全量保存覆盖 entity_ref」缺陷；快照/还原其它 WAITING_REVIEW 任务段落（2026-11-14）。 (~2200 tok)
- `verify_commit_chain_e2e.py` — E2E ③：commit→KB 文件/分块 + learned_templates + outlines + KB 归属 + 图谱节点 5 类产物，并用 StructuredTool.ainvoke 验证 get_templates/lookup_regional_fact 消费端；图谱节点快照差集删除 + 共享节点属性回滚 + 任务中心行/match_count 清理（2026-11-14）。 (~2600 tok)
- `verify_builder_extraction_e2e.py` — E2E ④：实体构建器提取链路（mock `pisuan.models.chat.select_model`，其余生产代码）——三态比对/grounded 证据/实例值不入库/落库/remap 绑定与属性改名刷新，快照还原其它 pending 任务 + 行数指纹零残留（2026-11-14）。 (~1900 tok)

## backend/scripts/governance/

- `normalize_property_value_types.py` — 实体属性值类型治理（幂等，默认 dry-run，`--apply` 写库）：把误写成模板 slot 类型的 `parameter` 按 key 归一（以「数值」结尾→Float，其余→String），历史别名交写入路径，未知类型报错交人工；2026-11-15 修掉 8 实体 44 条属性，否则这些实体页面保存必 400、导出无法回导。 (~700 tok)
- `audit_slot_binding.py` — 插槽→实体属性绑定质量审计（只读）：按 L1 精确/L1 歧义/L2 包含/L3 模糊/ORPHAN/DANGLING/BARE 分级回溯 WAITING_REVIEW 任务与学习模板全部非空 entity_ref，量化 bug-4288（69.9% L3 模糊错绑）；`--out` 全量 JSON。 (~400 tok)
- `reconcile_corpus_fields.py` — Route A 对账（只读）：coal-eia-writer stages 字段清单→属性候选，两级匹配（精确→包含）与 52 实体对账，输出 covered/gaps（按表单族分组）/零锚定实体三清单；实测 226 字段仅 19 覆盖、41 实体零锚定。 (~400 tok)
- `trash_entities.py` — 实体批量回收工具（默认 dry-run，`--apply` 落库）：校验 key 状态→统计引用面→备份→软删→学习模板/pps 引用清空→remap→复核残留归零；npp_model_parameters 清理即用此。 (~350 tok)
- `induce_entities_from_corpus.py` — Route B 语料普查（LLM 逐切片抽取，断点续跑）：project_eia 井工+露天 212 切片→结构感知采样（≤30K 全文，超长取标题大纲+表格行+正文开头）→agnes-3.0-flash 抽「数据对象+属性(name_cn/type/unit/samples)」→逐切片落盘 /tmp/route-b/slices/→聚合 candidates.json（按对象+属性合并计数，对账 db-exact/new-prop/new-object）；`--stride N` 试点抽样、`--merge-only` 仅聚合。 (~450 tok)
- `apply_corpus_induction.py` — Route B 归纳落库五阶段（幂等可续跑）：`--plan` 同义簇合并（~70 组人工梳理）+现有实体路由（沉陷族→land_subsidence 等）+属性过滤（实体内重复/跨实体同名剔除）→`--translate` LLM 批量 snake_case 键→`--classify` LLM 六分类→`--apply` 走 DomainEntityService 正常编辑流→`--conform` 键小写化/无选项 Enum 降级/超长 hint 截断；51→293 实体落地即此工具。 (~500 tok)
- `discover_bind_backfill.py` — 空槽绑定 discover 流批量回填（断点续跑）：突破内建三道闸（≥3 段落/candidates[:50]/entities[:40]），全局按槽名去重 50 名/批 + 全量实体目录入 prompt；bind_slot 校验+实体内挽回、add_property 解析转绑定，真新增入 entity_proposals 待确认；槽位绑定 1476→3049。 (~400 tok)


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

- `test_eia_lexicon_flow.py` — eia_lexicon 全链路集成测试：导入幂等 → 确认流 → 拆分 → 导出物化 → 开关闭环。 (~1848 tok)

## backend/test/integration/services/


## backend/test/integration/storage/


## backend/test/scripts/


## backend/test/unit/


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

- `test_eia_formula_service.py` — EiaFormulaService 单测（P3-1：formulas 参数参考值 DB 覆盖 + 文本级导出物化）。 (~2370 tok)
- `test_domain_entity_extraction.py` — 实体提取契约单测：三态比对矩阵/dict 形属性兼容/无证据拒绝/partial 只写定义/new 建实体/键与值类型校验/改名拒绝（14 例，2026-11-14）。 (~1500 tok)
- `test_domain_entity_usage.py` — 实体引用影响面单测：四类来源（模板/待审核任务/报告参数/区域事实）混合计数、中文名后缀归一为属性 key、悬空引用与未使用属性、非本实体引用忽略、实体不存在抛 ValueError（3 例，Fake repo，2026-11-14）。 (~900 tok)
- `test_domain_entity_import.py` — 实体配置导入单测：按 entity_key 跨环境对齐/无 entity_id 可创建/异域与缺键缺名与文件内重复拒绝/dry_run 不写不 remap/值类型别名归一/仅更新才 remap（8 例，Fake repo，2026-11-15）。 (~800 tok)
- `test_domain_entity_lifecycle.py` — 实体软删/回收站/乐观锁单测（11 例）：删除=soft_delete、不存在报错、恢复拒绝活跃行、恢复后按 get_by_id 重载、purge 拒绝活跃行、purge 删除回收站行、新建/克隆拒绝回收站键、update 透传 expected_updated_at/force、row 消失报「移入回收站」、list_entities 带 trash_total（SimpleNamespace + AsyncMock 伪 repo，2026-11-15）。 (~420 tok)
- `test_domain_entity_categories.py` — 实体分类字典（v23）单测：taxonomy 按字典 sort_order 渲染（含空分类）/停用且为空才隐藏/字典外历史分类兜底追加/实体 category 走字典校验/删除有实体的分类被拒/调序重写 sort_order/泛化 prompt 按字典顺序取前 N（10 例，Fake repo + monkeypatch，2026-11-15）。 (~1100 tok)
- `test_graph_relation_rules.py` — relation_rules 在 graph_builder 的求值单测：关系名净化/slot 值收集/条件匹配/命中落边与目标 MERGE 去重/未命中零写入/不支持动作计数（6 例，FakeTx 不连 Neo4j，2026-11-14）。 (~900 tok)

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

- `changelog.md` — 版本变更记录 (~45494 tok)

## docs/intro/


## docs/superpowers/plans/

- `2026-11-04-agent-briefing-layer.md` — Agent 业务简报渲染层（briefing 层）实施计划 (~11591 tok)
- `2026-11-09-template-recommender-guided-writing.md` — template-recommender 逐节引导写作重构实施计划（8 任务，含 SKILL.md 全文） (~4400 tok)

## docs/superpowers/specs/


## docs/vibe/

- `2026-11-04-agent-briefing-layer.md` — Agent 交互体验重塑：业务内容分层渲染层（briefing 层） (~1398 tok)
- `2026-11-05-chapter-doc-delivery.md` — 章级交付文档与用户可选合并（2026-11-05） (~629 tok)
- `2026-11-05-template-recommendation-fix.md` — 段落模板推荐口径统一与 writer 范例链接线（2026-11-05） (~536 tok)
- `2026-11-09-template-recommender-guided-writing-design.md` — template-recommender 重构设计：逐节引导写作四卡循环（已获批，2026-11-09） (~1900 tok)
- `2026-11-13-通用域知识工厂全景梳理.md` — 通用域 7 页全景：数据加工→消费、页间矩阵、外部关系、端点映射、已知问题（prompt 键断裂） (~6800 tok)
- `2026-11-14-通用域知识工厂页面诊断与重构清单.md` — 7 页逐页诊断 + X1–X11 跨页缺陷 + 后端横切审计 + 4 条真实栈 E2E 实证 + P0–P3 重构清单 (~9000 tok)
- `2026-11-14-领域实体构建器页面设计诊断.md` — 实体构建器单页深挖：字段契约体检、AI 提取闭环三重断裂、关系规则无消费方、泛化 cap 60 覆盖实测、三档改进建议；§8 实体提取规则化（三链路规则强度对比 + 规则五层 L1–L5 + P0/P1/P2 落地顺序） (~5800 tok)
- `2026-11-15-实体软删与并发保存.md` — P1-3/P1-4 收尾任务书：现状（硬删无退路、属性 splice、无并发控制）、范围（v24 deleted_at、repo 过滤+软删/恢复/彻底删除+FOR UPDATE 比对、service 回收站语义与键占位、trash/restore/purge 端点与 409、前端抽屉/冲突弹窗/撤销条）、不做（属性墓碑、自动清理、字段级 merge）、Checklist 与落地记录 (~1200 tok)

## docs/vibe/assets/2026-09-30-coal-eia-v2-port/


## docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/


## docs/vibe/prototypes/


## scripts/


## scripts/governance/


## web/


## web/e2e/fixtures/


## web/public/providers-logo/


## web/src/apis/


## web/src/assets/css/


## web/src/assets/docs/

- `entity-construction-spec.md` — 实体对象构建规范的唯一来源（Vite `?raw` 引入，页面「构建规范」弹窗直接渲染）：实体/属性/值域定义、建实体四条判据与本库反例、key/name_cn/synonyms 命名、实体级与属性级字段口径（Object vs String、单位、枚举、必填、提取提示、遗留别名禁用）、六分类归属、引用与变更、提交前 10 项检查清单 (~120 行)


## web/src/components/


## web/src/composables/

- `useEntitySchemas.js` — 实体构建器状态中枢：taxonomy/schemas/分类字典 `categories` 三路并发加载、编辑副本 `draft` 与 `baselineJson` 快照脏态判定（`isDirty`）、CRUD/克隆/导入导出、分类 CRUD 与 `moveCategory`（成功后统一 reload 并 `preserveDraft`）、`treeData`（按字典顺序）、`promptCoverage`（复算后端泛化 60 上限口径，排序键 = 字典顺序 + name_cn）、`categoryOptions`（字典为准，停用分类仅在已被使用时列出）、`usage`/`usageLoading`/`usageError`（选中即拉影响面，reqId 防串台，`fetchUsage` 供删除前取最新）；固定 `DOMAIN_CODE='general'`，导出 `KEY_PATTERN`/`VALUE_TYPE_OPTIONS`/`normalizeValueType`/`validateEntityDraft`/`computePromptCoverage` (~563 行)


## web/src/components/common/


## web/src/components/domain-factory/

- `entity/EntityTree.vue` — 实体构建器左栏：域分组树（节点顺序即分类字典顺序，空分类也渲染）+ 搜索（搜 name_cn/entity_key/description/synonyms，命中词 `<mark>` 高亮）+ 每域「+ 新建实体」入口 + 实体删除图标（只 emit，确认弹窗与引用影响面由页面统一处理）；`a-tree` 显式 `:open-animation="false"`（避开库内 `getTreeNodeProps` 在节点离场帧读 `entity.parent` 的崩溃）；emit `select(key)`/`delete(entityId)` (~174 行)
- `entity/EntityEditor.vue` — 实体编辑右栏：基础元数据表单 + 嵌套 PropertyTable（透传 promptCoverage/entityKey/usage）/RelationRuleEditor/EntityUsagePanel（仅已落库实体）+ sticky 操作条（保存/取消/克隆/查看JSON/删除，删除只 emit）；`defineModel('entity')` (~160 行)
- `entity/EntityUsagePanel.vue` — 「使用情况」卡片：段落模板/待审核任务/报告参数/区域事实四类引用计数、未使用属性与悬空引用告警、ghost collapse「最近引用明细」（待审核任务 + 前 8 个模板）；props usage/loading/error (~160 行)
- `entity/PropertyTable.vue` — 属性结构表（「提取提示词」列、「进 prompt / 未进」标记按 `promptCoverage` 复算后端 60 上限、「引用」列按 `usage.properties[key]` 汇总四类来源并给出分解 tooltip，0 标「未使用」）+ 属性定义弹窗；覆盖提示文案指向「分类管理」（顺序前移可换回名额）；删除属性与属性键改名都先走 `Modal.confirm` 影响面（有引用列四类条数、无引用只提示不可恢复，改名取消不落草稿）；删掉的属性留在内存并由「撤销条」原位找回，草稿被整体替换（保存后重载/取消/换实体）即失效；`defineModel('properties')` 就地增删改 (~370 行)
- `entity/EntityTrashDrawer.vue` — 回收站抽屉（520px）：列出软删实体（中文名 / entity_key / 分类 / 删除时间），恢复与彻底删除都只 emit（彻底删除走 `Modal.confirm` 危险按钮二次确认）；每次打开 emit `open` 让页面重拉，状态不在此组件缓存 (~120 行)
- `entity/RelationRuleEditor.vue` — 图谱关系推理规则编辑：条件 JSON 非空对象校验、actions 只允许 `create_edge` 且 relation 为英文标识，目标 entity_key 不存在时告警；`defineModel('rules')` (~232 行)
- `entity/EntityExtractWizard.vue` — AI 提取向导弹窗：上传（≤5MB）→ 三态比对（new/partial/matched）+ grounded/coverage 提示 + 默认勾选规则 + 导入；emit `imported` (~480 行)
- `entity/EntityJsonModal.vue` — 实体 JSON 查看弹窗（复制/下载）；`defineModel('open')` (~72 行)
- `entity/CategoryManager.vue` — 「分类管理」弹窗：行内改名（blur/Enter 提交）、上移下移（整体 reorder）、启用停用开关（失败回滚）、删除空分类（有实体时按钮禁用并提示）、底部新增（校验 `^[a-z][a-z0-9_]{0,63}$`）；行数据是父级 `categories` 的本地副本，成功后只 emit `changed` 由页面 reload；文案说明顺序决定树序与泛化 prompt 取舍；`defineModel('open')` (~254 行)


## web/src/components/eia-data/

- `DatasetStatsPanel.vue` — Vue component (~8712 tok)

## web/src/components/factory-core/


## web/src/components/modals/


## web/src/components/model-management/


## web/src/layouts/


## web/src/router/


## web/src/stores/


## web/src/utils/


## web/src/views/

- `DomainEntityBuilderView.vue` — 领域实体构建器页面（编排层）：`useEntitySchemas` + EntityTree + EntityEditor + CategoryManager，统一脏状态确认（切树/新建/克隆/导入/`onBeforeRouteLeave`/`beforeunload`）、`?entity_key=` 深链、空态三入口、导入/克隆/分类管理弹窗、删除影响面确认（`confirmDelete`：先 `fetchUsage` 列四类引用，失败即取消；编辑器与树两个入口共用）；页头次操作依次为 构建规范（弹窗渲染 `entity-construction-spec.md`）/ 分类管理 / 回收站（带 trash_total 计数）/ 导出 / 导入 / AI 提取；删除确认口径为「移入回收站，可恢复」 (~390 行)


## web/test/unit/

