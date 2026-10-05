# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-16

## User Preferences
- (2026-10-05) 消除词形/口径分裂时拒绝映射层（replace 链、别名兼容补丁），要求真实数据统一——直接改 DB 字典/存量/静态资产，前后一个词形；方案选择上偏好爆炸半径小的方向（coal vs coal_mining 一案选定 coal：DB 主导词形，零数据迁移）
- [2026-10-01] 最大限度不修改 yuxi 核心代码（上游共有代码面），否则上游同步/rebase 麻烦。改前先 git 判定代码块出处：pisuan 自有扩展（如领域工厂 report 工具链）可改；上游共有代码必须动时先向用户说明。判据：git log -S + git show upstream/main:<path>。

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- Communication in Chinese for project discussion, English for code comments
- Large changes should have a requirements document in `docs/vibe/` with date prefix

## Key Learnings
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining
- [2026-10-03] KB 存储层现状（代码+现场双重验证，推翻 7 月设计文档）：LightRAG 已退役——knowledge/runtime.py:12-14 只注册 Milvus/Dify/Notion，lightrag.py 未注册不可创建，运行栈 2 个 KB 全是 milvus 型（煤矿环评报告模板库 id=3 / 环评标准规范库 id=4），默认类型 = row.kb_type or "milvus"（manager.py:73）。MilvusKB 检索 = Milvus 向量+BM25 稀疏+混合融合+可选 reranker。KB 级图谱新引擎 = knowledge/graphs/MilvusGraphService（knowledge_graph_index 任务，LLM 抽取 chunk→Entity→RELATION 写 Neo4j + MilvusGraphVectorStore 实体向量），当前栈从未跑过（PG 图谱表 0 行、Neo4j 无 Chunk/Entity 标签）。Neo4j（容器名 graph!）里活着的是领域工厂结构图谱（ParagraphTemplate 870/ChapterTemplate 571/...）。domain_factory commit 的结构化入库分支（_ingest_structured_document/_get_lightrag_instance）在 milvus 栈上是死代码，hasattr 守卫使其永远走 manager.index_file Markdown 回退（PG knowledge_chunks 3169 行即其产物）。
- [2026-10-03] 本宿主机是 Windows 且默认自动休眠：休眠冻结整个 Docker VM（容器日志静止、连接死亡、lease 过期），唤醒后被 durable 收敛器落 FAILED。判定「应用挂死」前先排除宿主机休眠——看容器日志里每 30s 的 arq health 心跳是否中断，心跳断=宿主机睡了，不是 bug。长任务前须关休眠：powercfg /change standby-timeout-ac 0。
- [2026-10-03] 改名栈（pisuan-localized）的 Redis 模型缓存键是 `pisuan:model_cache`——cache.py 里的 REDIS_CACHE_KEY 字符串也被机械改名层改掉了；db0 里另有旧栈遗留 `yuxi:model_cache:v2` 与本栈无关。查/删缓存前必须 `redis-cli --scan --pattern '*model*'` + `INFO keyspace` 先定位真实键。模型端点换地址要动三层：.env OPENAI_API_BASE、DB model_providers.base_url、Redis pisuan:model_cache（rebuild 只在 provider UI 保存或 lifespan 启动时触发；手工重建=容器内跑 get_all_model_providers+model_cache.rebuild，脚本结尾要 os._exit(0) 否则 pg_manager 挂住进程）。
- [2026-10-03] 容器内访问宿主机服务（如 llama.cpp gemma4）必须用 `http://host.docker.internal:<port>`，不能用 127.0.0.1（那是容器自身 loopback）；宿主机 LAN IP 变更后旧地址全断。改动走两份 .env（pisuan/ 与 pisuan-localized/）+ `docker compose stop/rm api worker && up -d --no-deps --no-build`（--no-deps 必加：compose 会因 env 漂移连依赖一起重建，而 minio 镜像本地已缺失会炸）。容器是临时文件系统：docker cp 进 /tmp 的脚本在重建后消失，重拷即可。
- [2026-10-03] pisuan-localized 运行栈容器内 Python import 名是 `pisuan`（不是 `yuxi`）：sync-dev 同步时会做机械改名，连测试文件也改（所以容器内 pytest 引 `pisuan.services...`）；裸 docker exec python 需 `import pisuan.*`。
- [2026-10-03] 运行栈 HTTP 层不能用 seed_initial_users.py 的种子密码登录（用户已改密）；对已批准的服务层动作，走 `docker exec api python /tmp/xx.py` 直接调 service 方法（import pisuan.*），不绕 Web 认证。
- [2026-10-03] 运行栈 postgres 库名是 `yuxi_know`（容器内 env POSTGRES_DB），不是 yuxi；worker 用 watchfiles 监听 /app/server /app/package 热重载，sync-dev 后 P0.1 代码即时生效，无需重启。

- [2026-10-02] 任务中心新协议：Tasker.enqueue(*, name, task_type, payload, timeout_seconds) 无 coroutine 参数；执行按 task_registry.py 的 _TASK_DEFINITIONS 分发，Handler 必须是模块级函数、签名 handler(context: TaskContext)，参数一律从 context.payload 重建；新任务类型必须注册，否则 _build_task_data 直接 ValueError。
- [2026-10-02] 文档解析唯一业务入口是 yuxi.services.ocr_service.parse_document（解析系统默认 OCR 引擎+构造参数）；unified.parse_source_to_markdown/parse_resolved_document 是内部入口，上游 #843 后直调会报「OCR 文件缺少已解析的 ocr_engine」。
- [2026-10-02] 运行栈是 pisuan-localized 容器组（pisuan-localized-api-1/worker-1/postgres-1，端口 5050），代码经 scripts/sync-dev.ps1 同步并机械改名（yuxi→pisuan）；容器内无 yuxi 模块、无 ruff。
- [2026-10-01] 带 runtime: ToolRuntime 注入参数的 @tool 必须配显式 args_schema（BaseModel），否则 langchain 推断 schema 会把 ToolRuntime dataclass 卷进 args model，pydantic .schema() 崩 -> 全平台 chat run manifest_persist_failed。现有 24 工具均遵守，assemble_report 曾漏（bug-327）。

- **ETL Pipeline stages:** PARSE → CLASSIFY → GENERALIZE → WAITING_REVIEW → COMMIT
- **Frontend tab alignment:** ETL workbench 4 tabs map to pipeline: parse → generalize → entities → commit
- **Data flow:** All frontend edits go through `source_paragraphs[].template`, never `form_schema`
- **Save endpoint:** `saveTaskStep(id, {step: 'structured', payload: {source_paragraphs, structured_blocks}})`
- **Commit endpoint:** `commitTask(id, {form, structured, source_paragraphs, knowledge_base_id})`
- **Ant Design Vue** is the UI framework for this project (a-card, a-tabs, a-tree, a-table, etc.)
- **Docker-based dev:** `docker exec web-dev` for pnpm commands, `docker logs web-dev` for compilation
- **Vite HMR:** edits auto-reload, check logs for compilation errors after changes
- **远程仓库布局：** `origin` = yogyoho/pisuan，`upstream` = xerrors/Yuxi。同步走 `scripts/sync-upstream.ps1`（ff main → rebase pisuan-custom），但注意上游已重写过历史（见下条），脚本里的 `--ff-only` 路径已失效。
- **上游历史重写（2026-08-19 诊断，2026-08-20 完成 rebase）：** xerrors/Yuxi force-push 重写了 main 历史。main 已硬重置到 9e2679b9，pisuan-custom 164 个定制提交全部重放成功（备份：`backup/pisuan-20260819` 已推 origin，`backup/main-pre-rewrite` 本地）。红线定制（HomeView/LoginView/base.css/华宇页脚/领域工厂导航）与 backup 零差异。**rebase 期间启用 rerere + .wolf 文件冲突一律 checkout --ours**。后续同步注意：上游 CLAUDE.md 是符号链接（Windows 下类型冲突会炸，见 buglog）；v0.7.2 新增 .env 必填密钥 JWT_SECRET_KEY/API_KEY_DERIVATION_SECRET/SANDBOX_PROVISIONER_TOKEN/YUXI_INSTANCE_ID（init.sh 生成）；本地开发 .env 需 `YUXI_VERSION=0.7.1.beta1` 钉住现有镜像 tag（镜像重建受 tuna 镜像 403 阻塞）。
- **uv.lock 同步铁律：** rebase 合并 pyproject 后必须 `cd backend && uv lock` 重新生成（lock 的 manifest 哈希不匹配会让 Docker 构建 `uv sync --frozen` 失败）。当前 lock 的 wheel URL 硬编码 tuna 域名，Docker 构建网络下 403 时需换源重生。
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
- **实体分类体系（2026-07-17 Task 2 更新）：** 实体 category 从 4 个中文值改为 6 个英文 key：`project_basic`（基础工程实体）、`natural_env`（自然环境实体）、`env_quality`（环境质量与污染源实体）、`sensitive_target`（敏感目标与空间实体）、`measures_regulation`（措施与法规实体）、`impact_assessment`（环境影响评价实体）。涉及的映射点：①`coal_eia_entity_types.json` 的 `category` 字段（seed 源头）；②`domain_entity_service.py` 的 `CATEGORY_DOMAIN_MAP`（`get_taxonomy` 用）；③`domain_entity_repository.py` 的 `export_all` 里的 `domain_mappings`；④`entity_type_router.py` 的 `_entity_types_store`（in-memory demo 数据）；⑤`DomainEntityBuilderView.vue` 的 `defaultCategory` 回退值。`migrate_entity_categories.py` 是已存在的迁移脚本（用于现网 DB 迁移），不需要改。测试文件里的旧中文 category 引用需要随主代码一并更新。

- **写作侧 agent 合规性失效（2026-07-12 取证线程 ad3d19dc）：** coal-eia-writer skill 已把 5 个 report 工具声明为 tool_dependencies（`skills/buildin/__init__.py:76-86`），SkillsMiddleware 激活后对模型可见——工具**有**注入、非 plumbing 问题。但真实运行中编排者（conv30）+chapter-writer（conv31）两层对 create_report/save_chapter/assemble_report 调用次数=0：编排者读到 SKILL.md"必须用 save_chapter 不要用 write_file 绕过"仍绕过，并在 task 派发指令里写"输出为文件保存到 outputs/"把绕过传染给子 agent。判读：模型"产出文件→present"最强先验压过 prose 指令，仅靠 prompt 不够 → 走 B1+C3+A。**取证入口**：`docker exec postgres psql -U postgres -d yuxi_know`，`tool_calls JOIN messages ON message_id` 按 conversation_id 取时序工具链；thread_id 在 `agent_runs.conversation_thread_id`；子 agent 在 `subagent_threads.child_conversation_id`。spec：`docs/superpowers/specs/2026-07-12-writer-agent-compliance-design.md`。
- **arq worker max_jobs 死锁模式（2026-07-15）：** 主 agent 作为 arq job 同步 await 子 agent（也是 arq job）时，`max_jobs=1` 必死锁——主占唯一 slot 等子，子 pending 无 slot。表现：主 agent 派发子 agent 后卡住不返回（本例子 agent pending 12 分钟）。fix=`max_jobs≥2`。**关键：arq WorkerSettings 只在 worker 启动时读一次，改 max_jobs 后必须 `docker restart worker-dev` 才生效**（watchfiles 已被 commit 6d65ee8e 关闭，不热重载 WorkerSettings；改完代码看 docker logs 确认重启）。权衡：max_jobs=1 + 关 watchfiles 原本为防 OOM，max_jobs=2 让两 agent 并行（~400MB+/个）重新引入 OOM 风险，需 `docker stats worker-dev` 监控。更彻底的修法是子 agent 改为进程内协程执行（不占独立 arq slot），但改动大，暂用 max_jobs=2。判读 deadlock 的取证入口：`agent_runs` 表按 `created_by_run_id` 找子 run，看子 run `started_at` 是否远晚于 `created_at`（pending 久=slot 不够）。
- **save_chapter 只写 DB 不写文件（2026-07-15 复核 writer 合规）：** `save_chapter`(tools.py:628) 只 `repo.upsert_chapter` 写 content_md，**无文件 I/O**；07-12 设计的 C3（顺带写 preview 文件+返 preview_path）**未实现**——函数无 `runtime` 参数。`outputs/`(`/app/saves/outputs/`，`config.save_dir`=/app/saves) 仅由 `assemble_report`(tools.py:702) 写入，且**只合并 `status="done"` 章节**，写完调 `mark_assembled` 把报告推到 `assembled`。所以"章节→文件"必须走 assemble_report。当前 writer 合规缺口两层：①写手 save_chapter 标 `writing` 不标 `done`→被 assemble 排除；②编排者不调 assemble_report→无文件产出。`/app/saves/outputs/` 里旧的 300/12 字节 `report_*.md` 即之前 assemble 时无 done 章节的空壳。注意 tools.py:684 `_write_assembled_to_sandbox` 是**死代码**（assemble_report 没调它，直接写 config.save_dir/outputs）。取证入口：`tool_calls` 按 `tool_name IN('save_chapter','assemble_report')` + 看 `tool_input.status`；报告 `status!=assembled` 即未装配。agent_runs 的 conversation_thread_id 是 thread 不是 run id，找子 run 要用 `created_by_run_id`（= 主 run 的 `id`）。
- **coal-eia-writer 编排架构与 skill 加载（2026-07-15 取证，关键）：** 编排者 = DB agent `agent-b8decd45b324`，`config_json.context.skills=["coal-eia-writer"]` → 加载 coal-eia-writer SKILL.md（在 `BUILTIN_SKILLS` 里）。3 个 writer（prediction/data-survey/regulation-writer）是 subagent（`is_subagent=true`），`config_json.context` 只有 `{model,tools,excluded_tools}`，**无 system_prompt、无 skills 字段** → 运行时 system_prompt 是默认 `"You are a helpful assistant."`，skills 列表是继承的一大堆（含 coal-eia-writer）。**writer 同名 SKILL.md（`buildin/prediction-writer/SKILL.md` 等）不在 `BUILTIN_SKILLS`（`buildin/__init__.py` 只列 8 个）→ 不被 `init_builtin_skills` 同步到 `/app/saves/skills` → writer 运行时根本不加载它们 = 改 writer SKILL.md 无效（惰性文档）。** 改 writer 行为的正确杠杆：UI 页面设该 subagent 的系统提示词（写 DB `config_json.context.system_prompt`），改完即生效、**无需重启**（subagent prompt 在 run 开始时读 DB）。skill 加载链路：buildin SKILL.md →(`init_builtin_skills`,worker 启动时)→ `/app/saves/skills/{slug}` →(`sync_thread_readable_skills`,run 开始时)→ `/app/saves/threads/{tid}/skills/{slug}`。**`_dirs_equal` 只比文件列表不比内容** → 纯内容编辑不会刷新已存在 thread 的副本，必须**新起对话**（新 thread_id）才拿到新 skill；resume 旧 thread 拿到旧副本。改 `BUILTIN_SKILLS` 里的 SKILL.md（如 coal-eia-writer）→ `docker restart worker-dev` 重新同步 → 新起对话生效。**Git Bash 陷阱**：`docker exec worker-dev grep ... /app/saves/...` 里 `/app/...` 作直传参数会被 MSYS 转成 `C:/Program Files/Git/app/...` → 容器内找不到；必须 `docker exec worker-dev sh -c '... /app/...'`（路径在单引号内不转换）。判断 subagent 实际 prompt/skills：`docker logs worker-dev | grep "parent_thread_id='<tid>'"` 取 `system_prompt=`/`skills=` 字段。
- **格式化工具位置（2026-07-17）：** 宿主机无 pnpm、api-dev 容器无 ruff。前端 prettier/eslint 须在 web-dev 容器内跑：`docker exec web-dev sh -c 'cd /app && pnpm exec prettier/eslint ...'`；后端 ruff 用宿主机 `cd backend && uv run ruff ...`（同 Makefile format）。提交前格式化应 scope 到待提交路径，避免全量 format 波及工作区其他未提交改动。另：`DomainFactoryView.vue` 在 HEAD 即有 prettier drift + eslint `catch (e)` 未用变量的既有问题，不要对它全文件 `prettier --write`（会产生与任务无关的大 diff）。
- **写作成稿 P0 修复（2026-07-20，bug-124）：** 取证入口 `tool_calls JOIN messages ON message_id JOIN conversations ON conversation_id`，按 thread 看时序工具链。数据：写手 save_chapter status done仅40%、编排者 75% 跳过 assemble_report。**prompt 已正确**（DB 3 写手 system_prompt 都含 done 铁律）→ 定性模型合规，非 prompt 缺失。三处结构修复：①assemble_report 合并 done+review（`list_chapters` 改支持 list/tuple→`status.in_()`），review=完稿待审本该进草稿成稿；②C3：save_chapter 加 `runtime: ToolRuntime` + 显式 `SaveChapterInput` schema（**关键：langchain 1.3 隐式 schema 会把 runtime 泄漏进 LLM args，必须显式 args_schema 排除**，对照 ocr_parse_file/present_artifacts 都用显式 schema），done/review 顺带写 preview 文件返 preview_path 对齐"产出文件"先验；③coal-eia-writer SKILL.md 加派发铁律（每次 task 描述含 status=done 指令）。删 `_write_assembled_to_sandbox` 死代码。测试 save_chapter.ainvoke 须在 dict 加 `"runtime": obj`（assemble_report 测试即此模式）。
- **web-dev 是 Alpine（musl），Playwright 不能在其内跑浏览器**（`playwright install` 报 apt-get not found）。前端 E2E specs 须在宿主机（Windows/glibc）或 CI 跑，指向运行中的 dev server。`@playwright/test` devDep 可装进 web-dev node_modules（映射到宿主机），但浏览器二进制要宿主机装。auth fixture 读 `ADMIN_USER/ADMIN_PASS` 环境变量，不落盘。
- **后端集成测试凭证（2026-07-20）：** `test/integration/conftest.py` 读 `TEST_USERNAME/TEST_PASSWORD`（.env 或 test/.env.test），无则 skip。当前工作区无 .env，admin 用户=DB `admin`（superadmin，密码哈希不可逆）。集成测试文件结构正确但本地跑需先配凭证。
- **泛化 Schema 注入曾是空接（2026-07-20 bug-128，Phase 4）：** `domain_factory_service.py` 泛化调用处历史传 `schema_variables=[]`——泛化 prompt 的 schema 注入机制（`_format_schema_variables`）wired 但从不喂数据，slot 完全自由提取。修：`_load_entity_schema_variables(domain_code, max_items=60)` 从 `DomainEntityRepository.list_all` 拍平实体属性接入。教训：prompt 模板有占位符不代表数据真接进去，要看调用处实参。
- **规范库 §7 已被 compliance-checker skill 覆盖（2026-07-20）：** "条款引用匹配"功能目标（取章节 regulations.standard_code → query_kb 法规原文 → 逐章比对标准引用正确性 → 4 态矩阵）已由 `compliance-checker` skill 完整实现（KB 层），RegDocument 图谱层是内部结构。§8（写手查限值）缺，已补 buildin 工具 `lookup_standard_indicator` 调 `regulation_library.query_indicators`。模式：extension 的 query 函数暴露为 buildin 工具时，函数内 import + ImportError 兜底 + 无匹配 hint 引导 query_kb。
- **ask_user_question 子 agent 全局禁用（subagent/graph.py:26 `_SUBAGENT_DISABLED_TOOLS`）→ 中继协议是正解（2026-07-20）：** data-survey-writer 要问缺数据但不能直接调 ask_user_question。修在 coal-eia-writer SKILL.md（在 BUILTIN_SKILLS，改完重启 worker + 新对话生效）：写手输出 `## MISSING_DATA` 结构化块 → 编排者解析后代调 ask_user_question。无独立 writer SKILL.md（目录都不存在），writer 行为由 DB system_prompt + 编排者 task 描述决定。

- **上游 #1088（031e2c72，2026-09-30 同步）重构 skills 后端：** 删除 1813 行 `agents/skills/service.py`，拆为 `services/skills/` 包（`shared.py` 持 `init_builtin_skills` 与模块内 `get_skills_root_dir`；`remote_install.py`/`repository.py` 同删）。pisuan 在旧 service.py 的 6 行 .tmp-/.bak- 中断清理已移植到 `shared.py` 的 `init_builtin_skills`（`synced_items` 之后）。旧路径 import 直接崩，写 skills 相关代码先看新包。
- **上游 #1081（同版）`BaseContext.knowledges` 升级 `ResourceSelection` 类型（default="all"）：** 且 `context.py` 原生含 `excluded_tools`（:242）+ ExcludedToolsMiddleware——pisuan 旧版手工加的 excluded_tools 6 行字段定制已被上游超越，rebase 取上游侧，勿加回旧字段。

- **storage-migrator 是一次性任务，代码同步后必须手动重跑（2026-09-30 bug-317）：** Schema 只由 Compose 的 `storage-migrator` 容器修改（`restart: "no"`、跑完即退），api/worker 进程仅做 `require_current_schema` 版本守卫。热重载会让 api/worker 拿到新代码（含更高的 BUSINESS_SCHEMA_VERSION），但**永远不会重新触发 migrator** → 上游同步后 api 启动即被 `Database schema migration is incomplete or incompatible: business=8 (required 9)` 拦截。修法：`docker start <project>-storage-migrator-1`（挂载实时代码，迁移幂等）。**每次官方链同步/大版本追赶后都应重跑 migrator**，与 2026-07-10 的"同步后补列"条目同族。
- **镜像树迁移表名是 `pisuan_schema_migrations`（2026-09-30）：** 源码常量 `SCHEMA_VERSION_TABLE = "yuxi_schema_migrations"`，改名层在镜像里连表名字符串一起改为 `pisuan_schema_migrations`——手工 psql 验证时用后者，用源码常量名会报 relation does not exist。
- **worker 的 healthy ≠ 子进程存活（2026-09-30 bug-318）：** watchfiles 崩溃循环期间容器 healthcheck 仍报 healthy（只探容器不探 arq 子进程），且子进程死后无新文件变更不会自拉起。判活标准：日志出现 `Starting worker for N functions: ...`。修完因后 `docker restart` worker 强制重建子进程最稳。


- [2026-10-02] 本机 Bash 工具的 heredoc 会多吃一层反斜杠（脚本里写 \n 到达 python 时已是 
），且超过 ~8KB 的长命令会被截断报 "unexpected EOF"。长编辑脚本一律用 Write 工具写到临时文件再 `python 文件` 执行；heredoc 只放短脚本且避免反斜杠。
- [2026-10-02] 本机 `python -` 从 stdin 读脚本用 GBK 默认编码，UTF-8 中文锚点会乱码不匹配。必须 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`。ruff 用 `python -m ruff`（0.15.12 可用）；容器内无 ruff，`uv run` 因 site-packages 权限失败。sync-dev.ps1 后容器内路径是 /app/package/pisuan/（yuxi→pisuan 改名）。

- [2026-10-05] 存量库（business schema 已达 9==BUSINESS_SCHEMA_VERSION）上新增 ORM 模型表不会自动落库：storage_migration.main() 所有 DDL 分支都有版本门槛（create_business_tables 仅 None；ensure_business_schema 仅 {None,2,7}；upgrade_agent_resource_selection 仅 {None,2,7,8}），版本=9 时迁移器对 schema 是 no-op，热重载也不跑 create_all（lifespan 只 initialize+require_current_schema）。新表落地双路径：①ensure_business_schema DDL 列表补 CREATE TABLE IF NOT EXISTS（覆盖全新库/旧版本库）；②存量 v9 库 psql 手工建表（match_count 列先例同此）。另：migrator 容器 docker start 可重跑（bind mount ./backend/package:ro，sync 后代码即时生效）；api 容器里裸 python -c 独立初始化 pg_manager 会因未走 lifespan 初始化而挂连池，别用它验证 DB。

## Do-Not-Repeat
- [2026-10-03] domain_factory 泛化台账 `段落级泛化完成: ... skipped=N` 的 skipped 指「熔断后剩余未尝试段落」（domain_factory_service.py:3505/3531），不是模板复用数；模板复用判定在「泛化过滤」日志（todo=template 缺失或 fallback）。误读 skipped=209 为「复用失效」白查一场。断点续跑现状：复用解析（693 段载入），泛化层因历轮熔断未达持久化点而全量重跑——「只补失败段」尚不对泛化层成立。
- [2026-10-03] 排查 Redis 缓存问题时，未 `--scan` 键空间就按 worktree 源码里的键名 GET/DEL，查的是无人使用的残骸键 `yuxi:model_cache`，连环误判为「缓存被投毒/清空」折腾一小时。改名栈里一切字面量（键名、模块名、表名）都可能被改，先观察实际数据再下结论。
- [2026-10-03] Python str.count/replace 是子串匹配：深缩进文本包含浅缩进模式（24 空格行内含 20 空格模式），锚点替换必须先深后浅，且写盘前 assert count==1；连续两次替换失败说明先浅后深。
- [2026-10-03] Git Bash heredoc 除剥反斜杠外还会把中文全角引号「“”」压成 ASCII 双引号，含引号/中文标点的代码或文本一律 Write 落盘后执行，勿走 heredoc（本次 SyntaxError U+FF0C 实证）。
- [2026-10-03] 不要假设容器内与工作树同构：localized 栈 import 名/库名/凭据都与工作树不同（yuxi→pisuan、yuxi_know、密码已改），先探测再动手（用户纠正：容器中 yuxi 都替换成 pisuan）。
- [2026-10-03] 熔断/失败分支必须在结果回写之后才能 return/持久化——先落盘已成功产物再退场，否则断点续跑退化为整卷重跑（bug-342）。
- [2026-10-02] Windows Docker Desktop 上 worker 的 watchfiles 热重载在重负载长任务中会 inotify OOM 自爆（Cannot allocate memory os error 12）并连带 SIGKILL 任务——跑长 OCR/批处理前先用 compose override 去掉热重载，结束后还原；worker 重建后代码变更需手动 restart 容器才生效。

- [2026-10-02] 对从未 format 过的存量文件跑 `ruff format` 会整文件重排（domain_factory_service.py 596 行漂移），污染上游同步 diff——存量文件只做定向编辑+`python -m ruff format --check --diff` 预览，漂移超改动面就不 format；`git stash -- <file>` 会把工作树改动收进 stash，用完必须立刻 pop。
- [2026-10-01] loguru 不认 stdlib 的 exc_info kwarg：logger.error(msg, exc_info=True) 把它当 extra 静默吞掉，不打印栈。要栈用 logger.exception() 或 logger.opt(exception=True)。worker 排障别信 exc_info=True 有输出。
- [2026-10-05] 任务书写『新建』的测试文件可能实际已存在：Write 覆盖已有 141 行测试套件后才从 commit stat 的 -131 察觉。动手 Write 前先 `ls`/`git log --` 核实目标；Write 返回 "updated successfully" 即文件已存在的信号。另外 commit 后必看 --stat 数字是否与预期改动面相符（bug-356）。
- [2026-10-05] Edit 工具的 old_string 前导缩进不可作唯一性依据：domain_factory_service.py :4101（16 空格）与 :4586（20 空格）内容仅缩进不同，用 16 空格 old_string 仍报『Found 2 matches』——工具匹配会归一化前导空白。同文件多处相似行必须带相邻上下文行（如前一行的 `for p in paragraphs`）锁定唯一；改完必 grep 复核逐行落点。

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-09-30] **rebase 期间 hooks 每次工具调用后重写 `.wolf/*`，`git rebase --continue` 会因 unstaged changes 误报 "You must edit all merge conflicts..."**（此时 `git ls-files -u` 为 0、冲突早已 add 过）。这不是真冲突：builtin rebase 在 has_unstaged_changes 时直接 die。修复模式：每次 continue 前 `git stash push -m wolf-during-rebase-N -- .wolf/`；LF→CRLF warning 无害；`GIT_EDITOR=true git ...` 前缀须走 Bash（PowerShell 的 $env:GIT_EDITOR 传递不可靠）。同一 commit 的 continue 可能要连续多次 stash→continue。
- [2026-09-30] **上游大 rebase 的 .wolf 快照冲突三分法**：①纯 wolf 台账 commit（chore(wolf)/"chore: OpenWolf 台账…"）→ `git rebase --skip`，或 `GIT_SEQUENCE_EDITOR="sed -i 's/^pick X/drop X/'" git rebase --edit-todo` 批量 drop（须先解决当前冲突才能 edit-todo）；②混合 commit 中 .wolf 冲突 → `git checkout --ours -- .wolf/` + add（保留重放态版本，弃历史快照）；③rebase 完成后 autostash pop 在 .wolf 上冲突同样取 ours（hooks 会立刻刷新）。rerere 会记录全部解法，下次同类冲突自动复用。
- [2026-09-30] **上游 rebase 后必做保护文件核验**：`git show HEAD:<file> | grep <定制特征>`——base.css indigo、info.template.yaml 华宇、HomeView home-container。257 pick 大 rebase 逐个解冲突后不能凭记忆断言无损。
- [2026-07-16] `_parse_markdown_to_paragraphs` 中 Markdown 标题分支（`####` 格式）提取 `num_part` 后没有清洗 `title_text`（仍含编号前缀），导致 `current_section_title = num_part + " " + title_text` 拼接出重复编号如 `"3.1.1 3.1.1 地形地貌"`。数字标题分支（1107 行）正确调用了 `_clean_chapter_title`，Markdown 标题分支也应清洗。修复：在 `num_match` 匹配后直接取 `num_match.group(2).strip()` 作为清洗后的 `title_text`。
- [2026-07-16] `_parse_markdown_to_paragraphs` 表格行收集循环因分隔符行（`|---|:---|`）被 `is_table_line` 判 False 而提前终止，导致 `table_lines` 只剩表头 1 条，`len==1` 被当作普通段落。修复：收集循环改为跳过 `|...|` 包裹的非数据行（分隔符行）但不终止收集，使 `table_lines` 包含表头+数据行，满足 `len>=2` 触发表格识别。

- [2026-05-16] After full file rewrite, always run `pnpm run lint` before declaring done. Dead code accumulates quickly (unused imports, refs, functions). Catch blocks with unused `e` should use bare `catch {}`.
- [2026-05-17] When adding new template branches that call helper functions, ALWAYS define the function in the script section. An undefined function in a v-if/v-else-if chain causes a silent render failure for the entire branch — no error shown in UI, just blank content. This was the cause of "table paragraph click does nothing" bug (bug-108).
- [2026-05-16] Vue SFC must end with `</style>` not `</template>`. Stray closing tags cause `x-invalid-end-tag` parsing error.
- [2026-07-10] 上游大同步后，pisuan 的旧开发库可能缺合并后模型要求的列/默认值（如 `agent_runs.run_type`、`skills.is_builtin` 默认值），`create_all()` 不会补。同步后若 worker/api 崩在 `UndefinedColumn` / `NotNullViolation`，先 `docker exec postgres psql ... \d <table>` 比对模型，在 `manager.py` 补 `ALTER ... ADD COLUMN IF NOT EXISTS` 或 `ALTER COLUMN ... SET DEFAULT`。
- [2026-07-10] 合并中途 `uv.lock` 里残留冲突标记会让 worker/api 启动崩在 `Failed to parse uv.lock`（TOML 解析）。合并产生锁文件冲突时，先 `git checkout --theirs` 清标记再 `uv lock` 重生成，别让容器带着冲突标记重启。
- [2026-07-10] 领域工厂 commit/reingest 曾按 LightRAG 接口写文件记录（`kb_instance.files_meta[...]` + `_persist_file` + `database_id` 命名），LightRAG v0.7.0 移除后在 Milvus 上崩 `'MilvusKB' object has no attribute 'files_meta'`，任务转 FAILED 且 KB 无内容。改动领域工厂入库时一律用基类 `_persist_file_meta(file_id, {..., "kb_id": ...})` + `kb_manager.index_file`。相关：`slot_signature` 曾是 `VARCHAR(255)`，参数密集段落签名超限被截断、模板回流被 try/except 静默吞掉 → 已改 `TEXT`。

## Decision Log
- [2026-10-03] ETL 并发校准（方案 A 演进为可配置）：并发 10 对串行 llama.cpp 只放大队列等待（队尾 ~10min >> 客户端超时）造成健康调用被误杀、熔断误伤；超时 120→300s；并发改为管理员可配（Option 体系：domain_factory_llm，基础设置页渲染，默认 2 钳制 1-32，运行时读取下一次生效）。不放入领域工厂页面：该 knob 是端点级全局参数（模型本身是全局默认），与默认模型同屏最贴心智。配置面扩展模式：options.py 加 Option 实例 + OPTION_DEFINITIONS 注册（[pisuan-custom] 标记），lifespan ensure_options_in_db 自动建行，零迁移零前端框架改动。
- [2026-10-03] ETL 跑批遇本地端点推理停滞（12h 内第二次）：用户拍板「不干预，让超时→重试→熔断链自己走完」。运行期故障优先让 P0.1 自愈链收敛，人工只处理终态；用户自己的 llama.cpp 服务器不可擅动。

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-05-16] ETL workbench tabs redesigned from 5 → 4 to align with pipeline stages (parse/generalize/entities/commit). Removed deprecated form_schema dependency. All edits now flow through source_paragraphs.
- [2026-07-10] 98 提交的大追赶同步用 **merge** 而非项目既定的 rebase：rebase 会把 16 个定制提交逐个重放、在 21 个冲突文件上反复解同一文件；merge 一次性摊开所有冲突（判定内容相同但工作量小得多）。合并提交完成后，以后小步同步仍回 rebase 流程。
- [2026-07-12] 写作侧 agent 合规性（P0）方向选 **B1+C3+A** 而非纯 prompt 或纯简化工作流。B1=chapter-writer 工具集移除 write_file（系统级强制断捷径；机制：`subagent/graph.py` 的 `_SubAGENTToolFilterMiddleware` 升级为按 slug 附加禁用集）；C3=save_chapter 加 `runtime: ToolRuntime` + 顺带写 preview 文件 + 返 `preview_path`（把"产出文件"先验对齐到正确工具而非对抗）；A=SKILL.md/子 agent prompt 收敛（删"输出到 outputs/"诱导措辞）。Q3 决议：附加禁用集=`{write_file}`，保留 `execute`（execute 绕过不自然，先观察重放）。
- [2026-07-13] **源报告归并（分章上传）判定为过度设计并回滚**：曾计划建一等 `domain_factory_source_reports` 表 + 完整性QA/大纲隔离/重传去重，CEO 复审推翻。读码确认 `DomainFactoryOutline` 唯一键 = (domain_code, report_type_code, canonical_chapter_key)，**不同章节 → 不同 key → 不同大纲行**，传"第3章"+"第5章"自动归并成同报告类型的完整大纲——分章上传零代码已可用。`upsert_outline` 的"覆盖"语义（`domain_factory_repository.py:374`，注释"聚合合并在后续版本"）只在**同一章节被多份不同报告重复上传**时触发，那是"跨报告聚合"另一诉求，非分章上传。**教训：复审先问"现有 (domain, report_type) 归并是否已满足"，别默认加表。**

- [2026-07-14] **Neo4j result.single() 多记录 warning 修复模式**：当 Cypher MATCH 可能返回多条同属性节点时，在 MATCH 后加 `WITH ch LIMIT 1` 再做 OPTIONAL MATCH/collect 聚合，确保 result 只有一行。比 `next(iter(result), None)` 更干净（Cypher 层面解决，Python 层不变）。治理脚本去重 Cypher 需分步执行（先迁移关系、再删重复节点），不能用单条 Cypher 动态设置关系类型——Neo4j MERGE 不支持动态 relationship type。

- [2026-09-30] **coal-eia-writer 管线化 v2 移植设计定稿（brainstorming 闭环，commit 159bfa9e）**：五项决策——①slug 原地替换（context.skills 绑定零改动）②一期只走独立路径（单文件交付，mapping/章树绑定缓行）③新建通用 eia-section-writer 子代理（3 旧角色 writer 摘除不删，prompt 蒸馏进新子代理 DB system_prompt——不改技能包文件）④一期只验收 planning_eia ⑤合成项目进验收 checklist、真实项目上线前独立试跑。移植机制=忠实移植：scripts/references 一行不改，SKILL.md 只按映射表改编。**关键实证：** pisuan 沙箱与 v2 原运行时同构——技能挂载 `/home/gem/skills/{slug}/`（VIRTUAL_SKILLS_PATH）、workdir 虚拟根 `/home/gem/user-data/`、文件工具 7 件套同名；上传附件确认后落 workdir `/uploads/{file_id}_{name}`（attachment_service._store_attachment:188），ingest.py file 可直连。**唯一实质语义适配：** ask_user_question 是问题制（1–5 questions/次，question_id→answer），非 v2 假设的 16 项字段制表单 → 16 项/卡改 5 项/卡，字段 name→question_id、label+placeholder 合并进 question 文本、数值校验交给 ingest.py（「ingest 唯一校验者」哲学）。spec：`docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md`。


- [2026-10-02] 本机 Bash 工具的 heredoc 会多吃一层反斜杠（脚本里写 \n 到达 python 时已是 
），且超过 ~8KB 的长命令会被截断报 "unexpected EOF"。长编辑脚本一律用 Write 工具写到临时文件再 `python 文件` 执行；heredoc 只放短脚本且避免反斜杠。
- [2026-10-02] 本机 `python -` 从 stdin 读脚本用 GBK 默认编码，UTF-8 中文锚点会乱码不匹配。必须 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`。ruff 用 `python -m ruff`（0.15.12 可用）；容器内无 ruff，`uv run` 因 site-packages 权限失败。sync-dev.ps1 后容器内路径是 /app/package/pisuan/（yuxi→pisuan 改名）。

## Do-Not-Repeat

- [2026-09-30] **派发实现子代理必须禁用后台监视器模式**：首个 Tasks 1+2 实现者把文件拷贝委派给「后台监视器」异步执行，两轮 ~67k tokens 后目标目录不存在、零提交，且中途汇报听起来进展正常（buglog-319 同源）。修复：提示词开头加 CRITICAL 铁律（每条命令同步亲自跑、逐步核对 Expected、禁 watcher/deferred）；控制器在派发前与收到完成通知后都先做只读状态核查（目录存在性/git log），不轻信汇报文字。

## Key Learnings (append 2026-09-30 task3)
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining
- Skill 投影链路：worker 启动 init_builtin_skills 只把 buildin 同步到 skill-sources/shared/<slug> 并 upsert skills 表（保留 enabled 不动）；用户投影 skill-projections/<uid>/ 是 DB 驱动、只含 enabled=true 的技能，且在 Agent Run 初始化时才懒刷新（composite.py sync_agent_context_skills）。新增 buildin 技能若 DB 已有同名 disabled 行（历史残留），投影永远不出现。
- 运行栈容器内包名是 pisuan（改名层），python -c 需 import pisuan.* 而非 yuxi.*；POSTGRES_URL 为 +asyncpg 形式。skills 表无 is_deleted 列。
- 长时间 docker exec python + pg_manager 池偶发 "error connecting in pool-1" 挂起；一次性查询用 asyncpg.connect 直连更稳。
- **docs/vibe 被 .gitignore 忽略（2026-09-30 Task5）：** 存档类文件（assets/...）要进 git 必须 `git add -f`（精确列文件，勿整目录），`git add docs/vibe/...` 会被静默拒绝且 git status 不显示未跟踪。Task5 提交 33507661 即用 -f 提交了 2 个存档文件。


- **[2026-10-01] 修改 yuxi 核心代码必须加行内定制标记**（用户明确要求）：上游文件中任何语义改动，改动处加 `# [pisuan-custom] <语义说明>` 注释（Python；CSS/JS/Vue 各有对应形态，见 upstream-sync-guide.md 第七节）。用途：rebase 冲突解决后 `git grep -n '\[pisuan-custom\]'` 核对定制语义存活。此前已修的 bug-327（tools.py，pisuan 自有代码无需标记）与 bug-328（summary.py，上游文件已补 3 处标记）。

- **[2026-10-01] 知识工厂模板访问词汇错位（E2E V3 误判未命中的根因）**：弱模型凭直觉调用 `list_report_types(domain="coal_mining")`、`get_templates(report_type="planning_eia")`——字典真实 code 是 `coal` + `eia_report`（planning_eia 是技能 stage 名非 report_type）。库内 coal/eia_report 实有 604 条大纲（445 条含 purpose/overview/key_points/writing_hints）+ 28 条段落模板（全部是 ch3 现状调查节，伊宁语料）。修复方向：SKILL.md 开题/修复轮补词汇指南（code 枚举 + list_chapter_keys 先行）。模板泛化只遮蔽 1 个数值，实体裸露 → 只能作结构/句式参照，配合 sample_entities/yining.json 禁入清单。
- **[2026-10-01] 章门深度口径**：build_output.py `_effective`（:310 附近）= 非表格行、非标题行，剥 `\s\|-*#{}` 后计数——表格不计入有效字符，深度地板靠正文散文达成。ch3 floor=27100 为全书第三高（ch6 47300 > ch4 32900 > ch3 27100）。

- **[2026-10-01][Decision Log] E2E 暂停点：知识工厂补语料优先于继续跑章节**（用户决策）：coal 域只有 ch3 一章正文（伊宁 -3.docx），ch4-13 无段落模板参照；用户先上传加工样例报告全书，再恢复 coal-eia-writer 全面测试。恢复时的 nudge 应带知识工厂词汇指南（list_report_types() 无参 → coal/eia_report → list_chapter_keys → get_templates）。编排者 system_prompt 已含串行派发纪律（在飞 ≤1 + 429 停车令），DB agents.id=9，404 字符。
- **[2026-10-02] 知识工厂 ETL 评审结论（office-hours 全链评审，12 代理+DB 实测）：** 五症状全根因化——泛化在横城任务(a44afc93)真实成功率≈0：761/761 槽位全为 `_generalize_fallback` 名「数值」；法规场景B 存活 0/1997（para["template"] 被泛化/摘要整体替换，svc:668-684 写 vs :841-847/:864-867 覆盖）；narrative 摘要=输入前 50 字（setdefault generalized 回显 :3596 vs :3288）；公式 SYMBOL_MAP 15 项跨域撞名（下沉公式 W→产能/产量）+12 停用词致下标字母成变量；图片 URL HTTP401+`databases/unknown` 路径（<img> 带不了 token）；list=0（逐行成段致「≥2行」规则永不触发）；logical_relations 模型无列 setattr 静默丢弃；结构化入库死分支（MilvusKB 无 _ingest_structured_document，恒 Markdown 兜底，runtime.py 注册表只有 Dify/Milvus/Notion）；_chinese_to_arabic 逐字替换「十二」→「102」；MD表↔HTML表 html_table_index++ 纯位置配对。default_model 默认 DeepSeek-V4-Flash（siliconflow）。评审四镜头 verdict：数据面/失败模式/需求对齐=structurally_flawed，可维护性=sound_with_flaws；共识=阶段骨架保留、产物数据平面重构。终报待用户拍板验收标准换轨/死产出停机/范围三决策。
- 2026-10-02 泛化规模化天然实验：横城全本761/761兜底 vs 伊宁3.1 13/13成功(141个语义槽名0兜底)。同代码同提示词同模型→失败是provider级(配额/限流)而非内容/模型能力级。教训：①槽位机制本身没坏，坏在无重试+静默兜底+覆盖率指标；②逐段独立调用下文档规模对单次调用质量零贡献，规模只是失败放大器；③worker重建丢日志，重负载夜间任务后必须保留日志才能取证。
- 2026-10-02 ad99f4c9逐段时间线：参数段调用序2-70成功19/21，6.1.3.3起210段仅4段漏网→泛化失败突变点在调用顺序而非内容/章节，坐实provider级硬墙(配额/限流)。叙述段摘要全文档(含成功窗口)均为≤50字echo截断+0 key_points=独立代码bug(读取generalized回显字段)，与断供无关。
- 2026-10-02 gemma4 A/B审查：同文档换有额度模型→兜底2.7% vs DeepSeek 94%，配额假设终审结案。泛化LLM环节本身可用；剩余缺陷全在机制层：①YAML提示词文字\"双层大括号\"但示例全单括号→2075处混用；②type合法集4类从未命中，非法强转parameter；③跨模型同段槽名/覆盖不稳定(idx7: 1槽vs5槽；同义异名)，77%唯一率使slot_signature聚合失效→槽位注册表必要性实锤；④叙述提取读错字段=模型无关的代码bug；⑤ai_confidence两次均71与真实成功率6%→97%完全脱钩。
- 2026-10-02 提示词括号修复学到的：①_render_prompt是纯字符串replace不是format——YAML写{{}}原样到达模型，无需转义；但{content}等4个占位符必须保持单括号（replace按字面找{content}，写成{{content}}会残留杂括号）；②代码内联f-string版提示词的{{}}运行时塌缩为单括号，要出双括号需四重{{{{}}}}；③YAML旧版提示词遮蔽_PROMPT_DEFAULTS新版（新版含5槽上限+语义命名规则），切换是D2决策；④get_domain_factory_service docstring写单例实为per-call新实例→prompt缓存按任务失效。
## Decision Log 追加
- 2026-10-02 D2决策（用户确认）：①验收换轨——北极星从ai_confidence覆盖率改为写手取用率+成稿要素覆盖率（用户认可"产出必须被下游取用"的验收观）；②死产出停机——无消费者产物停止计算写入；③本轮范围仅ETL，commit/入库链（graph假成功、structured ingest孤儿、learned template upsert塌缩、retry无守卫）后续单独立项。需求文档=docs/vibe/2026-10-02-etl-redesign-requirements.md。注意用户节奏偏好：先修确定性小缺陷（如双括号）验证方向，再批准大改。
- 2026-10-02 泛化逻辑四项决议（用户发起第二轮设计评审后定稿）：Q1参数/叙述=区分产物不区分段落身份，散文段统一一次泛化产双产物；Q2公式正确提取的前提是解析层OMML→LaTeX（线性化已丢失下标/上标信息），产物为命名计算对象，符号表从「式中」规约行提取、严禁静态SYMBOL_MAP；Q3图片已在解析时上传MinIO但挂databases/unknown域+前端裸连401，改ETL自有命名空间+图题规则推断figure_type+鉴权API展示；Q4列表类型产出恒为0的根因是解析层逐行切段先于分类发生，决议停机（行内枚举由统一泛化吸收）。
- 2026-10-02 测量教训（bug-338）：PG ARE 无 lookbehind，(?!\{)\{ 自废恒0；\{[^{] 把双括号内部{也计数。正确法=先剥双括号再数剩余。修正后bug-335真实规模：修复前49处/修复后1处（残留=模型畸形括号组，非归一化缺口）。任何正则计数先用构造样本双向验证。

## Key Learnings (append 2026-10-04 D1-D6 + graph build)
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining

- agnes 免费层只 sustains 单并发请求：graph 抽取 extractor concurrency_count 必须 =1，且同一时间只允许一个 graph-build job（两个 KB 并行 = 2 路并发 → 429 风暴）；attempt 1/3、2/3 的瞬态 429 由内置重试（delay 2s）吸收，无需干预。
- worker/api 由 watchfiles 热重载：任何 backend 文件保存都会重启 worker 并杀掉在跑的 arq graph job。策略 = 改完全部代码 + 提交后，最后触发构建，之后不再碰 backend 文件。
- commit 管线阶段顺序：入库(阶段2.x，~4503) 在图谱构建(阶段2.5) 之前；D3 后入库是真实调用（yuxi.knowledge.runtime.knowledge_base 的 get_kb_executor/index_file），相关单测必须 mock 该 runtime 与 service._upload_original_to_minio。
- 容器内 pytest 的 INTERNALERROR '//app not in subpath of /app' = assertion-rewrite pyc 被污染（//app 参数跑过一次后按 mtime+size 持续复用）；rm -rf /app/test/**/__pycache__ 即愈。永远不要给容器内 pytest 传 //app 路径。
- GitBash 的 MSYS 路径改写对 docker exec 参数无孔不入（引号内、MSYS_NO_PATHCONV 均不可靠）；可靠通道 = Write 写 $TEMP 脚本 + tr -d '\r' | docker exec -i sh；Write 工具产物是 CRLF，管道前必须 tr。
- api 容器内服务端口是 5050（localhost:8000 连接拒绝）；容器内自调 API 用 minted token + http://localhost:5050。
- docs/vibe/ 整体 gitignore（.gitignore:78），需求文档只留本地，不入库。
- graph-build 触发链：POST /api/knowledge/databases/{kb}/graph-build/config（锁 extractor，仅 extractor_type 锁定，模型/并发可改）→ POST .../graph-build/index（409 若同库在跑；不同库可并行——这正是 429 风险）。status 端点不返回 running/progress 字段（键名未知），监控进度用 worker 日志 grep "图谱构建：抽取"。
- pre-existing lint 欠账先例：HEAD 上 domain_factory_service.py 16 处 E501、tools.py 3 处、test_commit_pipeline_status.py 1 处——判定归属用 `git stash` 对拍 HEAD；自己的新行必须 ≤120。
- agnes key 在 Redis pisuan:model_cache 内、经环境变量传递不落盘；API key UI 只做掩码显示。

## Do-Not-Repeat (2026-10-04)

- 不要在上一个 graph-build job 未到终态时触发第二个（不同 KB 可并行 → agnes 429 风暴）。触发前用 worker 日志确认前一个已 构建完成/构建失败。
- 不要给容器内 pytest 传 //app 或未 tr 的 CRLF 脚本；一次污染整个文件的 pyc。
- 不要用 sleep N 链等待容器状态——被 harness 拦截；用 Monitor until-loop。

## Decision Log (2026-10-04)

- 图谱抽取模型选定 openai2:agnes-2.5-flash（免费层，~5-7s/chunk，json_object 约束输出）；本地 gemma-4-E4B 因 thinking-prose 不可用；付费 deepseek 被否（未获批准不得自行动用付费 API）。
- D1-D6 与 P0.1 合并为单个提交 9b74874d（两批改动在同批文件中交织，hunk 级拆分风险大于收益）。
- lightrag.py 删除与 pyproject.toml 残留依赖（上游共有）按"最大限度不动上游"原则推迟，已记录在 vibe 文档 deferred 清单。

## Key Learnings (append 2026-10-04 ETL 数据平面裁决)
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining

- **match_count ETL 增量断链（bug-353）**：service:648 调的 _increment_learned_template_match_counts 根本不存在，:649-650 try/except 静默吞 → 「1107 模板 0 复用」有两个根因：槽名 77% 唯一率（已知）+ match_count 永无增量（新发现）。修复前任何「模板复用率」观测都是 0，观察期判停标准会失真。
- **段落级校验链字段错位（bug-354）**：pre_commit_validator.py:32 / service:4101/:4131 读 para["type"]，段落真实字段是 classify_type → L1 恒跳过全部段落、L2 整体不被调用、parameter_paragraphs 恒 0。单测 fixture 合成 type 字段是掩盖源——校验类单测必须用生产真实字段名。
- **「大纲管理页只写 Neo4j」是过时说法**：confirm_outline_extract（service:5144-5168）已双写 PG+Neo4j（:5162 注释自证）；只有 updateOutlineTemplate（OutlineTemplate.vue:493→PUT outline-templates）落点待核。2026-07-16 的 knowledge-factory-design.md §7.2 叙述已不准确。另 OutlineTemplate.vue:173/:467/:490 对 expected_charts 有 read+write 人工闭环——ETL 停写恒空数组可以，删列删 API 字段不行。
- **Neo4j FormulaTemplate 疑似写而无读**：get_templates 返回载荷（graph_query_service:194-200）只有 text_pattern/slots/legal_references 不含公式；expected_formulas 断链（task_detail 无顶层键）。公式对象化（Q2/P2）落地时必须先指认消费通道，否则派生面按 D2② 复议。

## Do-Not-Repeat (2026-10-04 ETL 数据平面)

- 不要把「模板 0 复用」单归因于槽名碎片化就设计观察期判停——match_count 增量断链（bug-353）不修，观察期数据恒为 0，会误判停回流。
- 校验/守卫类改动不要再写合成 type 字段的 fixture（bug-354 教训）；改前先 grep 生产赋值链确认字段名（classify_type）。
- 「写而无读」判定必须全仓 grep（web/src + backend/test + scripts + agents md），只查 service 会漏掉 OutlineTemplate.vue 这类 UI 人工闭环消费者（expected_charts 差点误删列）。

## Key Learnings (append 2026-10-04 KF×v2 整合设计)
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining

- **coal-eia-writer v2 实施状态**：资产已落地（scripts/10 脚本+references 全套），eia-section-writer 是 DB-only 子代理（agents id=13，无代码 preset）——环境重建即失。SKILL.md tool_dependencies=6 件无 save_chapter。
- **v2 文档口径三处漂移（对账成本源）**：合约计数 SKILL.md L167「XS1-XS18」/L264「XS1-XS12+EO1-EO3」/consistency_contracts.json 实测「XS1-XS20+EO1-EO3(23 条)」三者互相矛盾；data_expectations 是 31 族不是 33（spec V4 勘误：派生视图族不产空白不进门）；冻结槽位 35 vs 有值槽位 49 口径未对账。
- **v2 门禁的 doc-impl 断层**：standards_index.json gate1_code_checks 在册但 scripts/ 零实现（门1 标准号体检宣称无实现）；consistency.py 无 sample_entities 消费代码（实体泄漏防线纯 prompt 纪律，SL3 范文指纹门因 references/samples/ 缺失恒休眠）——实体链是 v2 全管线最薄防线。
- **seed_gen.py 落库端 verified-absent**：_import_template_outline/knowledge_factory schemas 在 pisuan 仓库与运行栈容器双向不存在——v2→工厂的出向通道实际是跨栈人工通道。
- **工厂三件套在 v2 语境的现状**：运行时取用率=0（纪律性调用+found=false 兜底常态化）；get_templates 图 831 vs PG 211 双库漂移+39 Slot 未 canonical；KB 库内唯一语料=样例书本身（横城同一文件×3 重复），query_kb 召回天然带样例实体与「范文数值禁入」红线冲突。
- **「数字链」是 v2 最强环节**：formula_runner 唯一写者→Decimal+ROUND_HALF_EVEN→make_inject 未知键硬 FAIL→残留扫描→XS2 ±2% warn，机制/实现/E2E 三层齐备——工厂任何供给改造不得进入该热路径（{{SLOT}} 词汇真源=state/formula_state.json）。
- check_content_contract 从未接线（tools.py 仅 L880 定义+单测引用）——v2 语境翻案依据：consistency.py 23 合约终验能力覆盖面远超它，且它对 {{SLOT}} 注入正文会系统性误报。

## Key Learnings (append 2026-10-04 样例报告价值分析 ch1-3)
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining
- backend/test/横城矿区总体规划环评报告书.md 是 coal-eia-writer v2 的样例语料（即红线3/standards_index「横城 9 处实证」来源）；该 md 副本所有表格仅存表题（表1.4-1…表3.4-25），表体数值在 md 中不可得，引用样例表值必须回查原始 PDF/DOCX。

## Key Learnings (append 2026-10-04 样例报告与导则)
- (2026-10-05) TemplateLibrary 加载机制：TEMPLATES_DIR 递归 rglob 所有 json（跳过 routing_* 文件），目录名不参与加载；领域过滤只认模板 JSON 的 domain 字段（get_templates_by_domain）与 matcher.match 的 context.domain 严格相等。templates/coal_mining/ 整目录 pisuan-owned（upstream main 无此路径），30 个 headers json 全带 domain: coal_mining

- **运行栈为 pisuan-localized-*（非 api-dev）**：当前 docker ps 显示 pisuan-localized-api-1/worker-1/web-1 等；两个工作树（pisuan / pisuan-localized）的 .env 都**没有管理员凭据**（CLAUDE.md「从 .env 读取管理员账户」已过期）。验证运行栈数据：优先 API 只读查询（需向用户要凭据），docker exec 须先报批。
- **HJ 463-2009 已由用户入库 KB**（2026-10-04 用户确认）：不要再说「KB 里只有样例报告没有规范本体」。导则相关路线设计的焦点是**角色标记与消费方式**（normative vs sample），不是导入。HJ 130-2019 是否已入库未确认。hj130.pdf（.wolf/ 下 800KB）= HJ 130-2019 总纲发布稿本体，非样例报告；hj463_extract.md / hj130_extract.md 为本地转写文本。
- **横城 md（backend/test/横城矿区总体规划环评报告书.md）表体全失**：grep 管道表格 0 行，仅存 171 个表题；伊宁 extract/fulltext.md 291 表有表体。工厂 6 轮 ETL 跑的是残本——表格类产物贫瘠的结构性原因之一；横城关键表（8.7-1 优化建议汇总/10.2-1 监测计划/11.1-1 清洁生产对标）须回源 docx。
- **写作者取材单位=表单行不是散文摘要**（31 族 fixture 铁证）；31 族分布 A≈7/B≈7/C≈10/D≈6，C 类（向业主要数）最多——数字链供给形态是表单而非语料检索；query_kb 召回预测章必然带出样例实体，是实体禁入红线最高危区。

## Decision Log (2026-10-04 产物路线 v2)
- **用户拍板**：①产物路线修正方案整体认可（scope×region 双标签、regional_facts 立项、一地区一 KB、learned_templates 冻结扩容、P2 重排、4 处验证修正全收）；②措施库两步走接受（一期散文级+区域库保底，行级抽取器后置）。spec 待写：docs/superpowers/specs/2026-10-04-kf-product-roadmap-v2-design.md。
- **工厂定位重述（用户已认可）**：模板产物冻结 ≠ 工厂没用——工厂从「模板工厂」转型为「文档结构化提取器 + 区域事实仓库」，写作管线上游供料商；取用率电表对工厂整体生效，转型后仍 0 取用则 D2 停机原则一视同仁。
- **用户新增事实**：手头有约 50 份样例报告（此前仅知 2 份全文本）；设想「基于导则从 50 份提取通用报告模板、按条件生成多份变体」——分析方向：导则定骨架（HJ463 附录A）、样例定变体（条件统计），交付走 PR-1 冷替换链；变体条件必须从语料实测归纳，不许猜。

### Key Learnings（2026-10-05 语料普查追加）
- 样例语料 docx 标题格式四种方言：①第X章（中文数字+加粗）②第1章（阿拉伯数字）③N 标题（无第/章字，如"1 总 则"）④自定义样式（如"标题 4(一)条"）。Heading 1 样式匹配在多数文件上失效；**目录行带 \t页码 后缀是最可靠的章树来源**（census.json headings_sample 已含）。
- WPS 生成的 docx 两种病态：.rels 引用 'NULL' 部件（python-docx KeyError，需 zip 手术剥关系条目）；UniDocSa 文件头（私有格式，真损坏）。census 脚本必须记 error 而非静默零值（bug-355）。
- 五大报告族骨架实测：规划环评 13 章 4 变体（回顾↔识别换序阵营 + 10-12 章轮转 + 新导则三线一单/不确定性）；项目环评 17-19 章（井工=沉陷章 / 露天=爆破章系统性分岔）；复垦方案 9 章三份同构；后评价沿用项目环评骨架；跟踪评价 11 章独有。

### Decision Log（2026-10-05 追加）
- 模板产物形态裁决：三层（骨架+变体规则+每章配置）胜出固化 N 份。决定性证据是 v2 技能 references/stages/ 下 5 份手写 stage JSON 正是固化形态及其维护之苦；三层渲染产物直接兼容该格式（消费者现成，D2 合规）。固化模板降级为渲染导出物。6 维条件词表用户已确认。
- 章序轮转（大气↔地表水等 5-6 种排法）判定为院家风，不进变体规则、不做配置；canonical_order 取语料多数派。

### Key Learnings（2026-10-05 KB 角色追加）
- 环评规范本体 KB：「环评标准规范库」kb_9ks49hyvfj，HJ 463-2009 与 HJ 130-2019 均已入库（用户确认）。KB 角色分三类：规范库（全局共享不分区）/ 样例库（可按 region_key 分区）/ 写手产物库。此前"KB 内容未验证勿断言"的教训由此部分解除：规范库内容已知，样例库构成仍需盘点。

### Decision Log（2026-10-05 W0 计划追加）
- match_count 语义裁决：learned_templates.match_count 只记 ETL 语料标题命中（语料适配度信号，bug-353 修复即此）；写作侧消费计数走新台账表 domain_factory_tool_usage。两种语义不共用一列（可信度随行原则）。
- matcher 注入链关键事实：_get_template_matcher = 静态 headers 库 + add_templates_from_list 注入 DB 学习模板，学习模板 template_id = f"learned_{db_id}"——只有该前缀回写 match_count。
- tools.py 是上游共享：任何改动带 [pisuan-custom] 注释；埋点为 fire-and-forget（module 级 task set 防 GC），绝不阻断工具主流程。

### Key Learnings（2026-10-05 bug-354 审查追加）
- Windows 宿主 Git Bash 跑 `docker exec <c> pytest /app/...` 会被 MSYS 路径转换改写成 `C:/Program Files/Git/app/...` → pytest 报 file not found（exit 4），极易误判为容器里没文件。加 `MSYS_NO_PATHCONV=1` 前缀即可。
- pre_commit_validator 段落 dispatch 字段是 classify_type（与 graph_builder/domain_factory_service 一致）；段落级 fixture 必须写 classify_type，slot 级的 "type" 是 slot 属性，两者别混。

## Do-Not-Repeat (2026-10-05 bug-354 qualrev)
- 2026-10-05: 不要假设 pisuan-localized 工作树文件内容 == 其 git HEAD。sync-dev.ps1 会把源仓未提交改动同步过去（工作树 HEAD 可能停在旧 commit 但文件已是新版）。做"对旧代码跑测试"的变异验证前，先 grep 实际文件内容确认基线，否则红/绿侧结论会反转。

## Do-Not-Repeat (2026-10-05 W0 收尾)
- 2026-10-05: 宿主机 `cd backend && uv run ...` 会改写 backend/uv.lock（本机 uv 与锁定 lock 版本漂移），跑 ruff 后必须 `git checkout -- backend/uv.lock`，否则会把锁文件噪声带进提交。
- 2026-10-05: 上游共享文件做定向 format 前先验证基线干净：`git show <base>:<file> | ruff format --check --stdin-filename <path> -` 通过 ⇒ 整文件 format 的 diff 只会落在新增块，可安全执行；基线不干净才需要手动只排新增行。

### Key Learnings（2026-10-05 W0 收尾追加）
- changelog 惯例：无「未发布」区块，定制工作以 `### pisuan 定制增量（日期）` 日期小节挂在当前版本节（v0.7.3）内、扁平 bullet，插入位置在该版本最后一个日期小节之后、下一个 `## ` 版本节之前。
- 本仓 ruff 门禁实际范围 = `backend/package`（CI ruff.yml + make lint 均不含 test/）；ruff 版本以 backend/uv.lock 锁定为准（勿用宿主机全局 ruff，版本不同 format 规则可能有差异）。
- 项目 isort 配置（ruff I）要求 `import pytest` 与 yuxi 一方 import 之间不留空行、段间不空行——与常见 isort 空行风格不同，手写 import 后须跑 `ruff check --select I --fix` 校准。

## Decision Log (2026-10-05 W0)

- **W0 关闭裁决**：E2E 冒烟暴露 bug-359（学习模板匹配死路）后，用户裁决不入 W0、作 W1 首项。理由：占位符→regex 语义直接决定 match_count 数据质量，修得糙会污染测量数据本身；W1 本就是模板/语料适配窗口；先例 template_generator.py:252-256 可循。
- **冒烟方法论**：单元三层全绿 ≠ 链路通电——「用 matcher 对学习模板标题自匹配」是低成本端到端证伪手段，W1 修完 bug-359 后必须复跑同款冒烟验证。
- **W0 交付点**：d687c812（已推送 origin/pisuan-custom），回归基线 1018/0/3；后续窗口以此为准。

- (2026-10-05, W1/bug-359) Decision Log: D1 词形统一方向定为 coal（DB 主导词形，真实统一无映射，删 replace 链；备选 coal_mining 因需迁移字典/静态侧被否）；D2 学习模板 match_rule=fallback_keywords[chapter 去编号全串]，命中语义=标题精确再现，拒二元组防假阳；D3 接受 static 遮蔽，match_count 语义=学习模板提供静态集没有的覆盖。交付点=spec 2026-10-05-bug-359 + plan 2026-10-05-w1-bug-359。

### 2026-10-05 W1-T1 会话补充（bug-359 词形统一）

- **Key Learning**：所谓"全量回归基线 1018 passed/0 failed/3 skipped"实际对应 `pytest /app/test/unit/services`（恰好 1021 collected）。命令 `pytest /app/test` 在本仓会因 unit 与 integration 存在同名测试文件（test_builtin_discovery / test_mcp_router / test_memory_service，均无 __init__.py，pytest 默认 prepend importmode）触发 "import file mismatch" 收集错误——这是仓库既有结构问题，与任何代码改动无关；分目录跑（unit、integration、e2e 分开）可绕开。
- **Key Learning**：`uv run` 首次运行会重建 backend/.venv 并改写 backend/uv.lock（3 行），用完必须 `git checkout -- backend/uv.lock`。ruff format 对基线不 clean 的文件会产生任务无关 diff（如 template_generator.py ~L159 空行），应只保留语义改动、回退 format 噪声。
- **Do-Not-Repeat (2026-10-05)**：不要用 `pytest /app/test` 单会话跑全量当作回归守护——会撞既有 basename 冲突误判为改动引入；用 `/app/test/unit/services`（基线口径）或分目录跑。

## Do-Not-Repeat (2026-10-05 bug-359 W1 Task 2)
- 2026-10-05: 追加任务书提供的测试代码块时必须逐字照抄，不要即兴加"占位/防御"行——本次混入一行任务文本中不存在的 `add_templates_from_from_list = None`（自纠错，未进测试运行即删）。追加后固定两步核对：git diff 纯新增+零删除、与任务文本逐行比对（bug-361）。
- (2026-10-05, W1/bug-359 Task 3) Key Learning ×2: ①容器运行栈内 /app/templates 不存在——compose api 服务只 bind mount server/package/test，镜像层也无 backend/templates；TEMPLATES_DIR 落空 → 容器栈 ETL 静态模板从未参与匹配（learned-only）。冒烟断言"静态共存"在本栈不可满足。已立案 bug-363（Dockerfile+compose 补挂载是 W1 候选，需评估静态模板突然参匹配的行为影响）。②pisuan.storage.postgres 是 namespace 包无 re-export，pg_manager 必须从 pisuan.storage.postgres.manager 导入（冒烟脚本曾踩坑，bug-362）。Do-Not-Repeat: 写跨栈验证脚本前先确认容器内路径/挂载布局与包导入路径。

### Key Learnings（2026-10-05 W1 bug-359 收尾追加）

- 容器栈 /app/templates 不存在：compose api 服务仅 bind mount server/package/test，镜像层 docker/api.Dockerfile 亦无 templates COPY；TemplateLibrary() 默认路径（__file__ 上溯四级 + templates）在容器内解析 /app/templates 落空，静态模板从不参与容器栈 ETL 匹配（learned-only），立案 bug-363（W1 后续候选：Dockerfile+compose 补 templates，需评估静态模板参与匹配的行为影响）
- pisuan.storage.postgres 是 namespace 包无 re-export，pg_manager 实例在 manager.py:1842，规范导入 from pisuan.storage.postgres.manager import pg_manager（bug-362）
