# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-16

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- Communication in Chinese for project discussion, English for code comments
- Large changes should have a requirements document in `docs/vibe/` with date prefix

## Key Learnings

- **ETL Pipeline stages:** PARSE → CLASSIFY → GENERALIZE → WAITING_REVIEW → COMMIT
- **Frontend tab alignment:** ETL workbench 4 tabs map to pipeline: parse → generalize → entities → commit
- **Data flow:** All frontend edits go through `source_paragraphs[].template`, never `form_schema`
- **Save endpoint:** `saveTaskStep(id, {step: 'structured', payload: {source_paragraphs, structured_blocks}})`
- **Commit endpoint:** `commitTask(id, {form, structured, source_paragraphs, knowledge_base_id})`
- **Ant Design Vue** is the UI framework for this project (a-card, a-tabs, a-tree, a-table, etc.)
- **Docker-based dev:** `docker exec web-dev` for pnpm commands, `docker logs web-dev` for compilation
- **Vite HMR:** edits auto-reload, check logs for compilation errors after changes
- **远程仓库布局：** `origin` = yogyoho/pisuan ≈ 上游 xerrors/Yuxi 的镜像；本地 `upstream/main` ref 可能过时，`git fetch upstream` 后 `origin/main` 与 `upstream/main` 通常同一 commit。同步走 `scripts/sync-upstream.ps1`（ff main → rebase pisuan-custom）。
- **deepagents 钉死 `<0.6.8`：** 0.6.10 移除了 `SubagentTransformer`，而 `yuxi/agents/middlewares/subagent_task.py` 仍 `from deepagents import SubagentTransformer`。上游已升 0.6.12（其代码已适配），pisuan 未适配 → 该约束必须保留；合并后必须 `uv lock` 让锁一致。
- **DB 迁移机制：** 无 Alembic，靠 `manager.py` 的 DDL 列表（`CREATE/ALTER ... IF NOT EXISTS`）每次启动跑。`create_all()` 只建不存在的表，不会给已存在的旧表补列/补默认值。
- **LightRAG 已在 v0.7.0 移除（关键约束）：** `knowledge/__init__.py` 只注册 `milvus/dify/notion`，`LightRagKB` 不再 import/register，`implementations/lightrag.py` 是孤儿文件；lightrag 类型的旧 KB 加载时被 `manager.py:184` skip。领域工厂结构化入库（`_ingest_structured_document`/`ingest_outline_collection`/`[OUTLINE]` 产出）全是 LightRAG 专属方法 → 现已是死代码。写作侧 skill 要消费 `[OUTLINE]` 必须先把结构化入库迁移到 Milvus（用 `knowledge_chunks.extraction_result/tags` 承载）。当前煤矿目标库 = `kb_cgsguljhor`（煤矿环评报告模板库，milvus）。
- **Milvus KB 文件入库正确姿势：** 文件记录走 DB `knowledge_files` 表 —— `_persist_file_meta(file_id, meta)`（meta 必须含 `kb_id`，不是 `database_id`）设为 status=PARSED + markdown_file，再 `kb_manager.index_file(kb_id, file_id)`。不是 LightRAG 的内存 `files_meta` 字典 + `_persist_file`。`_save_markdown_to_minio` 是基类方法，Milvus 也有。
- **前端文件/文件夹图标系统：** 彩色类型图标走 `web/src/utils/file_icon.js` 的 `resolveFileIconUrl(name,{isDir,folderVariant})` → 按 `folderVariant`(default/personal/favorite/agent/enterprise/knowledge/trash) 映射到 `web/src/assets/icons/files/folder*.svg`，由 `components/common/FileTypeIcon.vue` 渲染为 `<img :src>`（size 由 prop 控制）。改文件夹样式只需替换对应 SVG 资源，无需动组件；按钮图标另用 lucide-vue-next，不用这里的资源。所有 folder 变体共享同一套后片(带 tab 凸起)+前片(圆角矩形)路径，差别仅在叠加的白色语义装饰(personal=头像/favorite=五角星/agent=机器人)。2026-07-11 把工作区用到的 default/personal/favorite/agent 四个换成 Windows 金黄渐变风格（后片 `#E5AC3C→#B98015`、前片 `#FFE49C→#F1AC3E`），enterprise/knowledge/trash 未改。
- **domain_factory_service.py 大文件 surgical 纪律：** 该文件 ~5000 行，`ruff format` 全文件会产生 ~407 行无关变更（缩进/引号/换行调整）。提交前必须 `git diff --stat` 检查；若 ruff format 已跑，`git checkout` 回退后手动重做仅目标区域的 Edit。Task 2/3 均按此模式操作（纯插入 0 删除）。
- **select_model 导入策略：** `yuxi.models.chat.select_model` 在 domain_factory_service.py 原为函数内导入（8 处）。Task 3 已在模块级（line 68）加 `from yuxi.models.chat import select_model`，函数内的旧导入保持不动（无冲突，surgical）。新增的 `_llm_chapter_meta` 直接用模块级 `select_model()`，测试通过 `patch.object(mod, "select_model", ...)` mock。
- **buildin 工具可见性（Task 5 结论）：** `@tool(category="buildin")` 装饰的工具会被 `toolkits/__init__.py` 导入 buildin 模块时自动收集到 `_all_tool_instances`，`get_tool_instances_by_category('buildin')` 能列出它们。但注意 `resolve_configured_runtime_tools` 只注入 `context.tools` 中点名的 buildin 工具（按需加载），不是所有 buildin 工具默认注入 agent —— 即"registry 可见"≠"运行时默认注入"。Task 5 的 buildin 路径满足 brief Step 5 的断言（registry 可见即可）；实际写作 skill（Task 6）调用这两个工具时，需要确保 agent 的 `context.tools` 包含它们或通过 skill-gated 机制注册。
- **buildin tools.py 测试 mock 模式：** 测试 `@tool` 装饰的 async 函数时，`monkeypatch.setattr(tools_mod, "DomainFactoryRepository", lambda: AsyncMock(get_outline=AsyncMock(return_value=fake)))` 替换模块级 import，再用 `await fn.ainvoke({...})` 调用。注意 `@tool` 装饰器把函数变成 `BaseTool` 实例，调用走 `.ainvoke()` 不是直接 `await fn()`。
- **hashstr 导入路径：** `hashstr` 定义在 `yuxi/utils/hash_utils.py`，由 `yuxi/utils/__init__.py` 再导出。项目惯例是 `from yuxi.utils import hashstr`（见 `domain_factory_service.py`、`graph_builder.py`）。**不存在 `yuxi.utils.func_utils`** —— 若 brief/文档写 `from yuxi.utils.func_utils import hashstr`，那是错的，用 `from yuxi.utils import hashstr`。
- **写作侧 report 状态机：** `domain_factory_reports.status` 生命周期 `draft → writing → assembled`。`upsert_chapter` 在章节首次写入时把 report 从 `draft` 推进到 `writing`（`if rpt.status == "draft": rpt.status = "writing"`）。测试 snapshot 断言时要记得 `upsert_chapter` 已触发推进，不能仍断言 `"draft"`。
- **Phase A 工具程序化 e2e 验证模式：** 不经 agent 直接调 buildin 工具时，用 `from langgraph.prebuilt.tool_node import ToolRuntime` 构造最小 `ToolRuntime(state={}, context={}, config={}, stream_writer=lambda *a,**k:None, tool_call_id='tc_e2e', store=None)`，再 `await tool.ainvoke({...})`。assemble_report 的 `runtime.context` 会被 `_write_assembled_to_sandbox` 用 `getattr(runtime_context, "thread_id", None)` 取 thread_id；dict context 时 thread_id 回退为 "shared"，不影响验证。docker exec api-dev python -c "..." 跑即可，不需要 HTTP 层。
- **SDD task 收尾 gitignore 约束：** `.wolf/memory.md`（.gitignore:96）和 `.superpowers/sdd/*`（.superpowers/sdd/.gitignore:1 *）都是 gitignored 本地文件，`git add` 不会把它们纳入提交。SDD task 收尾提交只包含 `docs/develop-guides/changelog.md` + `.wolf/anatomy.md` 等已 tracked 文件；报告/memory/anatomy 描述更新是本地参考，不进 git。

- **写作侧 agent 合规性失效（2026-07-12 取证线程 ad3d19dc）：** coal-eia-writer skill 已把 5 个 report 工具声明为 tool_dependencies（`skills/buildin/__init__.py:76-86`），SkillsMiddleware 激活后对模型可见——工具**有**注入、非 plumbing 问题。但真实运行中编排者（conv30）+chapter-writer（conv31）两层对 create_report/save_chapter/assemble_report 调用次数=0：编排者读到 SKILL.md"必须用 save_chapter 不要用 write_file 绕过"仍绕过，并在 task 派发指令里写"输出为文件保存到 outputs/"把绕过传染给子 agent。判读：模型"产出文件→present"最强先验压过 prose 指令，仅靠 prompt 不够 → 走 B1+C3+A。**取证入口**：`docker exec postgres psql -U postgres -d yuxi_know`，`tool_calls JOIN messages ON message_id` 按 conversation_id 取时序工具链；thread_id 在 `agent_runs.conversation_thread_id`；子 agent 在 `subagent_threads.child_conversation_id`。spec：`docs/superpowers/specs/2026-07-12-writer-agent-compliance-design.md`。

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-05-16] After full file rewrite, always run `pnpm run lint` before declaring done. Dead code accumulates quickly (unused imports, refs, functions). Catch blocks with unused `e` should use bare `catch {}`.
- [2026-05-17] When adding new template branches that call helper functions, ALWAYS define the function in the script section. An undefined function in a v-if/v-else-if chain causes a silent render failure for the entire branch — no error shown in UI, just blank content. This was the cause of "table paragraph click does nothing" bug (bug-108).
- [2026-05-16] Vue SFC must end with `</style>` not `</template>`. Stray closing tags cause `x-invalid-end-tag` parsing error.
- [2026-07-10] 上游大同步后，pisuan 的旧开发库可能缺合并后模型要求的列/默认值（如 `agent_runs.run_type`、`skills.is_builtin` 默认值），`create_all()` 不会补。同步后若 worker/api 崩在 `UndefinedColumn` / `NotNullViolation`，先 `docker exec postgres psql ... \d <table>` 比对模型，在 `manager.py` 补 `ALTER ... ADD COLUMN IF NOT EXISTS` 或 `ALTER COLUMN ... SET DEFAULT`。
- [2026-07-10] 合并中途 `uv.lock` 里残留冲突标记会让 worker/api 启动崩在 `Failed to parse uv.lock`（TOML 解析）。合并产生锁文件冲突时，先 `git checkout --theirs` 清标记再 `uv lock` 重生成，别让容器带着冲突标记重启。
- [2026-07-10] 领域工厂 commit/reingest 曾按 LightRAG 接口写文件记录（`kb_instance.files_meta[...]` + `_persist_file` + `database_id` 命名），LightRAG v0.7.0 移除后在 Milvus 上崩 `'MilvusKB' object has no attribute 'files_meta'`，任务转 FAILED 且 KB 无内容。改动领域工厂入库时一律用基类 `_persist_file_meta(file_id, {..., "kb_id": ...})` + `kb_manager.index_file`。相关：`slot_signature` 曾是 `VARCHAR(255)`，参数密集段落签名超限被截断、模板回流被 try/except 静默吞掉 → 已改 `TEXT`。

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-05-16] ETL workbench tabs redesigned from 5 → 4 to align with pipeline stages (parse/generalize/entities/commit). Removed deprecated form_schema dependency. All edits now flow through source_paragraphs.
- [2026-07-10] 98 提交的大追赶同步用 **merge** 而非项目既定的 rebase：rebase 会把 16 个定制提交逐个重放、在 21 个冲突文件上反复解同一文件；merge 一次性摊开所有冲突（判定内容相同但工作量小得多）。合并提交完成后，以后小步同步仍回 rebase 流程。
- [2026-07-12] 写作侧 agent 合规性（P0）方向选 **B1+C3+A** 而非纯 prompt 或纯简化工作流。B1=chapter-writer 工具集移除 write_file（系统级强制断捷径；机制：`subagent/graph.py` 的 `_SubAGENTToolFilterMiddleware` 升级为按 slug 附加禁用集）；C3=save_chapter 加 `runtime: ToolRuntime` + 顺带写 preview 文件 + 返 `preview_path`（把"产出文件"先验对齐到正确工具而非对抗）；A=SKILL.md/子 agent prompt 收敛（删"输出到 outputs/"诱导措辞）。Q3 决议：附加禁用集=`{write_file}`，保留 `execute`（execute 绕过不自然，先观察重放）。
- [2026-07-13] **源报告归并（分章上传）判定为过度设计并回滚**：曾计划建一等 `domain_factory_source_reports` 表 + 完整性QA/大纲隔离/重传去重，CEO 复审推翻。读码确认 `DomainFactoryOutline` 唯一键 = (domain_code, report_type_code, canonical_chapter_key)，**不同章节 → 不同 key → 不同大纲行**，传"第3章"+"第5章"自动归并成同报告类型的完整大纲——分章上传零代码已可用。`upsert_outline` 的"覆盖"语义（`domain_factory_repository.py:374`，注释"聚合合并在后续版本"）只在**同一章节被多份不同报告重复上传**时触发，那是"跨报告聚合"另一诉求，非分章上传。**教训：复审先问"现有 (domain, report_type) 归并是否已满足"，别默认加表。**

- [2026-07-14] **Neo4j result.single() 多记录 warning 修复模式**：当 Cypher MATCH 可能返回多条同属性节点时，在 MATCH 后加 `WITH ch LIMIT 1` 再做 OPTIONAL MATCH/collect 聚合，确保 result 只有一行。比 `next(iter(result), None)` 更干净（Cypher 层面解决，Python 层不变）。治理脚本去重 Cypher 需分步执行（先迁移关系、再删重复节点），不能用单条 Cypher 动态设置关系类型——Neo4j MERGE 不支持动态 relationship type。
