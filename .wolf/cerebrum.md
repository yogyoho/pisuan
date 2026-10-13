# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-16

## User Preferences

- **数据工厂参照设计语言 = P2 高保真原型**（用户明示「非常美观」）：新页面/组件按 docs/develop-guides/data-factory-ui.md 配方实现，不再另行出原型；注意原型内 token 是别名（--warn-50 等），实现须换算 base.css 正名。
- (2026-10-05) 消除词形/口径分裂时拒绝映射层（replace 链、别名兼容补丁），要求真实数据统一——直接改 DB 字典/存量/静态资产，前后一个词形；方案选择上偏好爆炸半径小的方向（coal vs coal_mining 一案选定 coal：DB 主导词形，零数据迁移）
- [2026-10-01] 最大限度不修改 yuxi 核心代码（上游共有代码面），否则上游同步/rebase 麻烦。改前先 git 判定代码块出处：pisuan 自有扩展（如领域工厂 report 工具链）可改；上游共有代码必须动时先向用户说明。判据：git log -S + git show upstream/main:<path>。

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- Communication in Chinese for project discussion, English for code comments
- Large changes should have a requirements document in `docs/vibe/` with date prefix

## Key Learnings
- 2026-10-07：coal-eia-writer 的 references/standards_index.json=62 条标准索引（framework/quality_limit/emission_limit/method_param/pending 五 tier，含 GB 15618 vs GB 36600 正确名称与适用对象），但 limit_tables 七张表多为空壳（gb3095 rows=[]，verified=false）——「引用错标准」先查这里：若索引有→契约没强制核对（工程问题）；若表空→知识缺口（加工问题）。诊断 W1 类缺陷前先看这个文件。
- 2026-10-07：智能体模型切换走 agents.config_json.context.model（「provider:model」前缀格式，如 deepseek:deepseek-flash）；供应商与模型清单在 model_providers 表（provider_id+enabled_models json），deepseek 供应商 enabled 含 deepseek-flash（显示名 DeepSeek-V4.1-Flash）/v4-flash/v4-pro。
- 2026-10-07：模型对比实证（同技能同 prompt）——agnes-2.5-flash：共用工区静默续跑、ask_user_question A/B/C 选项点击无效须手输；deepseek-flash：主动检测工区冲突弹结构化单选题（radio+提交可用）、真实调用 list_report_types/get_templates 并声明 found=true 免兜底、全章数据预告完整、限流纪律 「在飞≤1」被遵守。行为差异主要在模型而非技能。
- 2026-10-07：sandbox user-data 宿主机路径 = docker/volumes/pisuan/threads/shared/<uid>/workspace/（admin 即 shared/admin/workspace/workspace/…，双 workspace 层）；sandbox 容器被回收后文件仍可从宿主机直读，容器名 pisuan-localized-sandbox-<id> 不稳定，别拿容器当存储。
- 2026-10-07：页面测试证据链——节稿在宿主机上述路径 state/sections/；对话运行状态看页面 subagent 卡片（「已调用 N 工具·M 失败」）；tool_calls 表近 2h 无记录（仅消息终结落库）；429/失败以主智能体自报为准，api 容器日志 grep 429 全是端口子串误中。
- 2026-10-07：eia-section-writer 配置 knowledges=['kb_cgsguljhor','kb_9ks49hyvfj'] 但 tools=[]——知识库挂载与工具权限脱节，RAG 实际不可达（标准引用全靠模型记忆的直接原因之一）。
- 2026-10-07：W4 后端新增区行号锚（终审核实）——repo 912-1105 / service ~6737-6856 / router 418-481；ruff 16 errors 存量基线分布 repo:145、service ≤5285、router:693，全在 W4 区之前。下一窗 lint 对比：uvx ruff check 四文件=16 持平即零新增。
- 2026-10-07：domain_factory list_regional_facts 的 source_task_file_name 批量拼接在 repository 层（file_map），service 直通——changelog/spec 曾误标「service 层拼」（终审 Minor，下一窗文档顺手修正）。
- 2026-10-07：region_label 是用户自由文本（归属时随手填），凡按它 group by 的聚合都会在标签漂移时拆行——展示聚合一律按 region_key 归并（前端 Map 或后端 service，树侧 service:6827 先到非空 label 优先）；v-for :key 与归并键保持同源表达式。b1d4fb6d 先例。
- 2026-10-07：前端主题色变量表——警告最浅底色用 var(--color-warning-50)（base.css:101 #fffbe6，base.dark.css:87 #2b2111 暗色覆写）；--warning-bg 不存在（计划片段曾误引，662f47ff 已修）。写样式前先 grep base.css 变量表，别发明变量名。
- 2026-10-07：受控多选（selectedRowKeys）+ 不可逆批量操作组件，筛选/下钻改变数据集时必须同步清空选区，否则确认弹窗只显示数量的场景会连带不可见行；变更操作清空当前页后要按 total-变更数 回缩 pagination.current （Math.min(current, max(1, ceil((total-n)/pageSize)))，在 refetch 前用旧 total 求值）。662f47ff 先例。
- 2026-10-07：antd-vue InputSearch @change 回调即原生 input 事件（e.target.value 取当前值），allow-clear 点✕只发 change 不发 search——「清空即解除过滤」要在 @change 里判空触发（Panel 先例 AttributionTaskTable onKeywordChange；同目录 RegionalFactsTable radio @change 同形）。
- 2026-10-07：v-show 多子页容器各子页自行 fetch 时，切换子页不会自动刷新——改判等跨子页级联写操作后，父容器需 watch(activeSub) 调目标子页 defineExpose 的 refresh()（RegionAttributionPanel 476f8b21 先例，watch 非 immediate、mount 零触发）。
- 2026-10-07：计划 Step 门必须含 `uvx ruff format --check <改动文件>`（不止 ruff check）——计划/spec 内嵌代码片段曾带手工行尾注释对齐，逐字照抄即翻车（T2，style 0d3e2a65 收敛）；后续写计划时片段先过一遍 format。
- 2026-10-07：Windows 控制台 GBK 打印中文会乱码——验证脚本带 `PYTHONIOENCODING=utf-8`，或改为程序化相等断言（打印仅布尔/ASCII），数据本身不受影响。
- 2026-10-07：后端 lint 道——pisuan-api:0.7.3 镜像、pisuan-localized-api-1 容器、宿主均无 ruff；宿主 `uvx ruff check <文件...>`（0.16.x）可用，T1 基线四文件 16 errors（全在存量代码区，新代码零新增）。T6 对比基线就用 uvx 道。
- 2026-10-07：domain_factory_service.py 行号锚点快照——`_reaggregate_templates_for_task` :6505 之后并非类尾，实况还有 `_aggregate_template_scopes` :6512、`_get_existing_entities_full` :6727 等，类体真实末尾约 :6733（模块级 get_domain_factory_service :6858）；按行号锚点插入前必须 Read 目标区域确认，行号漂移就按锚点语义定位。
- 2026-10-07：web 前端图标实况——domain-factory 组件 import 自 `@lucide/vue`（非 CLAUDE.md 推荐的 lucide-vue-next）；DomainFactoryView 的 tab「图标」是 CSS 圆点 `span.tab-dot`（less 嵌套 &.data/&.workbench 配色），新增 tab 应加配色变体行而非引入 icon 组件。
- 2026-10-07：单测容器道惯例——service 单测用 `DomainFactoryService.__new__(DomainFactoryService)` + `svc.repo = fake` 跳过 __init__；测试为同步 def + `asyncio.run(...)`（--noconftest 下 pytest-asyncio 不可依赖）；domain_factory_repository.py 无分页无 GROUP BY（列表仅 limit），会话模式 `pg_manager.get_async_session_context()`，joinedload 为方法内局部 import（文件怪癖，勿「顺手」提升到顶部）。
- 2026-10-07：可视化伴侣服务器（brainstorming visual companion）在 Claude Code Windows 后台任务模式下约 30 分钟被 run_in_background 时限杀掉；**用 `nohup ... & disown` 在普通 Bash 调用里脱离进程树启动即可长活**（会话目录在 <project>/.superpowers/brainstorm/<pid-ts>/，重启后端口会变，须读 state/server-info 并告知用户新 URL）。
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
- **SDD task 收尾 gitignore 约束（2026-10-05 修正）：** `.wolf/memory.md` 虽列于 .gitignore:96 但**历史上已被强制追踪**（git status 常态显示 M）——gitignore 只拦未追踪文件，对已追踪文件 `git add` / `git add -A` **依然会暂存其改动**。"gitignored 会跳过"是错误认知（bug-365 实施者实测证伪）。防误提交的唯一可靠手段 = 提交一律用显式文件清单、禁 `git add -A`；memory.md 的会话台账更新刻意不入提交，靠的就是清单纪律。
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

- 2026-10-07（bug-367 剥壳实战）：LLM 改写数字密集中文段落数字必漂移——校验器（数字序列+占位符多重集逐字比对）拦截率约 15%，这类段落改用确定性词级替换对（长短语优先、词级兜底）零风险；「其下游用途是为/为 X 提供 Y」类删除式替换会制造缺谓语句（「；第 9 章…提供判断依据」），删前缀后必须抽读补「为/用于」。
- 中文门词表设计：子串误伤要预判——词表不收「登记表」（护住公众参与章真实文件名「参会人员签到登记表」），收四字「登记表单」；真实世界名词与管线术语同形时词表必须让位。
- docs/vibe 在 .gitignore 中，入库需 git add -f（项目惯例是 vibe 文档要入库，changelog 会引用它）。

- 开发栈容器名已换：pisuan-localized-{api,web,worker}-1（CLAUDE.md 里 api-dev/worker-dev 已过时）。api 容器把宿主 9p 挂载四路：/app/package→pisuan-localized/backend/package，/app/skill-sources、/app/skill-projections→pisuan-localized/docker/volumes/pisuan/（运行时卷，非 git 树），/app/user-data→docker/volumes/pisuan/threads。技能运行时同步=docker cp 进这两个卷（等同 sync-dev.ps1 效果）；test2 工作区实际宿主路径在 pisuan-localized/docker/volumes/pisuan/threads/user-data/ 下。
- 技能测试继续容器内跑（pisuan-localized-api-1 python -m pytest /tmp/…），宿主 pytest 因 langchain 缺失必炸（既知）。
- deepseek 批量改写的 prompt 必须显式写「标记/数字在输出中恰好出现一次（与输入同多重集），只能移动禁止复制」——只说"移到独立行"模型会复制一份（bug-394 三轮改写的主要失败形态）。
- heredoc 通过 docker exec 传入 stdin 会静默无输出：脚本一律写宿主临时文件→docker cp→exec python 运行。


- coal 语料题注行主流形态是章内号「表N.M-M」（7698/7969=96.6%），全局号「表N-M」仅 271；正则/解析器归纳自 geo 样例时必须先对 coal 语料实测分布（bug-402）
- 本管线 docx→md 不保留粗体（语料 0 粗体行）——依赖「**粗体**」形态的解析规则对 coal 语料全部失效
- 统计类例句池不能按文档序前 N 填充：会被主导形态灌满，须按形态配额（bank_compile lead_examples 各 20）


- prepare_corpus 全文 NFKC 归一后语料单位是 km2/m2/万m3（²³→数字），任何单位白名单/正则必须收归一形且长形排前（bug-404）
- 节号 6.10 是第十节不是小数——排序用 int 元组 (6,10)，float 会 6.10<6.2 错序
- 量词短语惰性左锚定捕获全短语（「主要声源源强」），forms label 是短词——后缀滚动匹配归并；未命中进 unmapped 池（cap 200）供人工扩充
- 语料野章号切片（ch2020/ch8760/空标题节）全部源自 028-r 已知垃圾报告（表行升标题伪影），各衍生产物一致带噪，勿在单产物层特判过滤


- 运行栈容器重启（非重建）不清 /tmp——/tmp/verify394 测试工作台跨重启存活；docker cp `<dir>/.` 融合拷贝内容进挂点目录
- 门深度地板经 resolve_targets 缺省探测技能基准——运行栈验证 eff 行内嵌的就是最新标定 floor（34806），无需显式 --targets

### 2026-10-10（P4 批次）
- localized 栈版本表实际名 pisuan_schema_migrations、库名 yuxi_know（改名层连 DB/表名一起改）；直连 psql 用 postgres/postgres。
- 改名后的词表行重扫不会再生（新名非语料逐字出现不在扫描集），清库后重建只能直插；7 条改名行事故前状态存 .wolf/corpus-workdir/lexicon_full_audit.json。
- eia_dataset_switches 主键 dataset_key 无自增 id；快照/序列脚本须查 information_schema 而非假设 id 列存在。
- docs/vibe 是 gitignored：changelog 引用设计稿路径但文件只在本地，git add 会被拒。
- 词表 get_mentions 的 mentions 行结构自 P4 起为 {rid, before, hit, after, value, unit}（三段文本），source 字段区分 current/old_fingerprint。

### 2026-10-11（P1 五校准裁决）
- bank_compile QUANTITY_RE 是词表扫描的单一真源：eia_data_service 动态加载它（skills 脚本不可反向 import 包），改它两侧同源生效；词表净口径 = QUANTITY_RE raw + _STOP_TAIL 剥尾 + 首尾 strip("的了与及和或")。
- stages/*.json 格式：CRLF + indent2 + 无尾换行 + ensure_ascii=False；label_map 跨 5 stage 先到先得合并且不解析 reuse 指针（openpit 空字段节须物理补字段才能挂载）。
- curated 挂载语义：range 挂到该口径语料自然出现的每个节（sec_label_rids），unit 门控跨单位不混布；挂载与物化是两回事（物化 8 条中 3 条控制效率子口径因 raw 口径「控制效率」无 label 映射保持跳过）。
- sync-dev 会搬运 workspace 树未跟踪文件（路径翻译 yuxi→pisuan）——workspace 留副本即可让 localized 侧机生物存活；但 -Revert 与官方链再生仍会清，运行态真相只在 DB。
- 五校准口径全为语料常量（85/90/100）：挂载护栏价值=钉死领域惯例值防写手杜撰变体；字段样式同充填率（number/unit/required false，无 caliber_field——该标记无程序消费方）。

## Do-Not-Repeat

- [2026-10-08] markdown 标题层级断言禁止用「浅前缀 not in 输出」——"## x" 是 "### x" 的子串（后两 #+空格），恒假；必须行首锚定 startswith/splitlines。另：任务书自带的测试代码也可能有 fixture 缺陷（本例 strip_toc 样例 2 行连续目录行不足 spec 的 >=3 阈值），失败时先对照 spec/docstring/实现三方裁决谁错，不要无脑改实现迁就测试。slug 化文件名→目录名时正则白名单必须考虑全中文文件名（41 份语料 10 份纯中文，纯 ASCII 得空 id）。
- 2026-10-07：写计划/生成代码时，凡「同形循环」跨层复用（SQLAlchemy Row 位置解包 ↔ dict 列表），必须按目标层实际输入形状重写（键访问 vs 位置解包）；哨兵值（None）语义在「参与计算」与「跳过」间切换时，逐处对照 docstring 与测试断言核。T1 计划两处 plan bug 皆因此（幸被 TDD 拦截，commit 2461dddc）。
- 2026-10-06：审计/核验提示单里的「声明串」必须与实况逐字节一致（含全部后缀括注）——缩写版声明致 3/19 代理误报「标题不符」（实际标题=声明+信息性后缀）。裁决规则：声明为实际标题的严格前缀且语义相同 → 判一致放行，代理仅留痕不算 FAIL。
- 2026-10-06：汇报与审计中的**数字和协议字面串**禁止凭记忆引用——W3 收口报告写「10 提交」实为 9（真源=git rev-list）；审计提示单 trailer 誊了旧串 `Claude <noreply@anthropic.com>`，现行协议是 `Claude Code <noreply@anthropic.com>`，致 7/9 审计代理误报 FAIL。今后：计数类结论先跑 rev-list/log 现查再写；trailer 等协议串以当前 system 指令为准现场誊录，不信记忆。
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

### 2026-10-10（P4 批次）
- 集成 flow 测试会 wipe 运行库表——跑之前必须先快照并验证快照行数>0（空快照=已被清过）。bug-414 92 条裁决态因此丢失。
- 禁止 docker cp 宿主 test/源码文件进 localized 容器：宿主 import 名是 yuxi，容器是 pisuan（docker cp 不做改名）；要么 sync-dev，要么容器内 sed 归一。
- MSYS 路径转换仅 MSYS_NO_PATHCONV=1 偶失效，须加 MSYS2_ARG_CONV_EXCL='*' 双保险（docker exec 参数里的 /tmp 也被转成 Windows TEMP）。
- localized 栈的 storage-migrator 必须在 C:\workspace\pisuan-localized 下 compose up——workspace 的 compose 项目会试图另起 postgres 撞 127.0.0.1:5432。
- parametrize 扩迁移档位时，「某增量迁移调用必出现」类断言要按档位条件化（v12 增量只在 ≤11 档触发，12 档只走 v13）。

### 2026-10-11（P1 五校准裁决）
- 禁止对 stages/*.json 做 json.load→dumps 全文件重写：会重排历史缩进（既有 10 空格 label 行等）产生噪声 diff——用文本级精准插入（括号计数定位 fields 数组）。
- 改 QUANTITY_RE 前必须跑全语料新旧口径多重集 diff（p1_conn_diff.py 式）：「能达|可达」扩展的词中误断风险（功能达→除尘功+能达）要实证排除而非推理豁免。
- 跑集成/flow 测试前先看 fixture 是否 wipe 运行库表（bug-414 教训持续有效）；本批只跑 unit + 技能测试。

### 2026-10-11（localized 重建事故）
- 重建链里禁止用 grep/head 过滤 apply_pisuan_rename.py 输出且不查退出码——脚本起步崩（Windows 大批量 reset 后瞬时文件锁）被掩码，yuxi 名树被当改名层提交推送。必须显式检查 $LASTEXITCODE/管道后 PIPESTATUS，并核对提交差量签名（健康重建=1978 文件 ±4410 对称；「仅 2 files changed」即是事故信号）。
- 改名层提交通差量若非对称 ±N 相等，立即停手排查，勿推送。

### 2026-10-11（P2 控制效率三子口径）
- stages/*.json 文本级插入铁律：工作树原态是 CRLF（autocrlf=true checkout 产物）时，全文绝不做行尾翻译；只对插入块用 CRLF 字面量，且 item 缩进 replace 与 join 分隔符必须同一行尾形态——嵌套两种形态会产生 \r\r\n 孤立 CR，git 判非文本（w/-text）致 diff 全文件化（bug-417）。
- 判定脚本编辑是否污染文件的权威信号：git ls-files --eol 的 w/ 列。w/-text = 有孤立 CR 或 NUL；正常应为 w/crlf 或 w/lf。
- _MEASURE_RE（eia_data_service）与 QUANTITY_RE 是两处独立口径敏感点：QUANTITY_RE 新增口径形态时必须同步检查三分类正则是否认识新形态（控制效率拉丁前缀曾全落 junk，range_ready 门控静默失效）。

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

### 2026-10-10（P4 改名对话框）
- 抑制清单 DB 化而非继续硬编码：UI 改名无法改代码常量；种子常量下沉 models_domain_factory 防 service→repo→manager import 环，service 同名再导出保单测路径。
- 三段文本后端直发而非 offset：Python 码点 vs JS UTF-16 码元在 mojibake 语料下会静默错位，前端零 offset 运算。
- 控制效率三拆分子口径不重建：值集人工指派不可复原且本就量纲混布（bug-412），保持 splitting 待重裁决反而受益。

### 2026-10-11（P1 五校准裁决）
- 连接词扩展（+能达|可达）而非启动尾清洗重设计：语料 diff 证明扩展即收敛（词表剥尾后口径一致、零词中误断实例）；尾清洗重设计（R2-R5 类）仍留 backlog。
- 五口径全数补录挂载而非驳回：值虽全为常量，护栏语义正是「领域惯例值」钉死（防杜撰变体/小数错缀复发——bug-412 同类风险的预防面）。

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
- pre-existing lint 欠账先例：HEAD 上 domain_factory_service.py 16 处 E501、tools.py 3 处、test_commit_pipeline_status.py 1 处——判定归属用 `git archive`/临时 worktree 对拍 HEAD（**禁止 git stash**——共享工作树会卷走他人未提交改动，见 DNR 2026-10-06）；自己的新行必须 ≤120。
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
- (2026-10-05, W1/bug-359 收口) Decision Log: W1 首项终审 READY（unit 2681/0/61 复跑、冒烟 hits=200/200 对 W0 0/5 翻转、DB 热核零遗留）。累积 Minor 裁决：T2-M2（confidence==0.6 断言）/T2-M3（_learned_row 漂移守卫）与 W0-1/2 归 W2 同文件捆绑做；W0-3（set[asyncio.Task] 注解）永不主动；W0-4（32 处 ruff 旧账）仅独立 chore；W0-5 流程句已入计划 preamble。终审新发现：学习模板 converted 缺 name 键 → template_match.template_name=None（纯展示层，W2 补一行）。Do-Not-Repeat: 容器内 docker exec python 脚本默认加 -u（连接池线程挂住 + 块缓冲假死，bug-364）。

### Key Learnings（2026-10-05 bug-363 传播补缺追加）
- sync-dev.ps1 的 $copyFiles 单件清单现已纳入 docker-compose.yml 与 docker/api.Dockerfile（commit 2723e3e9，原 f884d9d0）：walker 对单文件与目录同路——rewrite_text 无扩展名门槛（逐行套 STRUCTURAL+BARE 规则，与官方改名链同一函数），localized 产出按构造一致。部署面改动不再绕行官方链长链路。验证法：`git -C C:/workspace/pisuan-localized diff github/pisuan-localized -- docker-compose.yml docker/api.Dockerfile` 应只含源树新增行；出现其他差异 = rename 规则或双树漂移异常，停手核查。

### Key Learnings（2026-10-05 bug-363 清淤追加）
- localized 树曾存 9 月 26 日旧词形 `backend/templates/coal_mining/`（含 index 暂存 R 条目）——`backend/templates` 当时不在 $syncPaths（恰因它此前不是挂载路径），热同步永不覆盖、自检 diff（口径=清单内路径）天然不可见。教训：sync-dev 的可见域 = 清单域，清单外任何漂移（陈旧目录/index 暂存）都会无声留存；新路径一旦变成挂载目标，必须同时纳入 $syncPaths 并清淤。
- walker 只增不删：源树目录改名（coal_mining→coal）后，localized 侧旧行名会与新名并存被 rglob 双份加载（60 条）。删除类漂移在 dev 同步域永远需要人工/官方链处理（边界 #3 条款）。
- 可逆清淤模式：同盘 `mv` 陈旧目录至 `.wolf/` 备份位（字节保全 + 镜像 tip git 对象双重可恢复），替代 `git checkout -f` + `git clean -fd`（auto-mode 分类器正确拦截了不可逆删除：用户未点名目标，且指令链源自子代理报告）。

## Key Learnings (append 2026-10-05 bug-363 Task 2)
- 领域工厂 ETL 两阶段结构：phase-1（parse/split/classify/模板匹配）在 PARSING 态完成并持久化 source_paragraphs，phase-2（GENERALIZING，LLM 泛化）失败不回滚 phase-1 产物；模板匹配（TemplateMatcher.match，仅 is_title 段）在 phase-1 尾部执行，matched>0 时自增学习模板 match_count（bug-353 链路已在真实 ETL 验证：命中模板 match_count 落库为 1）
- pisuan.models.chat.select_model 返回的 LangChainChatAdapter 只有 .call(message, stream=False)，没有 .ainvoke
- worker 忙时（大文档 OCR/抽取）docker exec python 查询会拖到分钟级甚至超时；轻量状态通道 = postgres 容器内 psql -U postgres -d <db> 直查（实际库名 yuxi_know，来自 .env，compose 默认 yuxi 会被覆盖）
- 云 API（apihub.agnes）对 ETL 批量抽取会 rate_limit 熔断：横城 2789 段重跑 success=12/rate_limit=8/skipped=741/3867s 终止 FAILED_PROVIDER，P0-3 断点续跑语义（FAILED_PROVIDER + source_paragraphs 非空 → retry 自动 resume）

## Do-Not-Repeat (2026-10-05 bug-363 Task 2)
- (2026-10-05) 容器内 LLM 探活用 select_model(...).call()，不用 .ainvoke（AttributeError 假报不可达）；宿主侧 kill docker exec 会在容器内留孤儿 python 进程，须 docker exec kill 清理
- (2026-10-05) 长时间任务轮询不用 docker exec python 循环（后台输出缓冲丢失 + worker 忙时拖死），改用 postgres 容器 psql 直查状态表
- (2026-10-05) ETL 重跑观测对象要选 2026-10 以后上传的任务（storage_path 为绝对路径）；2026-07 旧任务 retry 会因 saves/ 相对路径直接 PackageNotFoundError（bug-365）

### Do-Not-Repeat（2026-10-05 bug-363 终审追加）
- 2026-10-05: `.wolf/buglog.json` 仓库惯例是 json `indent=2`——用 python json.dump 打补丁必须 indent=2，写 indent=1 会整文件重排（5258+/5258- 的噪声提交）；amend 前被 `git show --stat` 拦下。同理一切 JSON 台账补丁：先 `git show HEAD:file | head -3` 看缩进惯例再动手，提交后必看 stat 数字是否与预期改动面相符。
- 2026-10-05（同日修订）: 容器内裸 `python -u -c` + pg_manager「挂池」根因已查明=对同步函数做 await（`initialize()` 是同步的，manager.py:373，await 它直接 TypeError 且被管道吞掉；进程不退是 psycopg 池后台线程）。已验证正确姿势：同步 `pg_manager.initialize()`（langgraph psycopg 池会报 "AsyncConnectionPool open with no running loop"，对纯 repo 路径无害）→ `asyncio.run(服务方法)` → 末尾 `os._exit(0)`。一次性查 DB 仍优先 psql 通道；杀宿主侧 docker exec 后容器内 python 会残留孤儿，kill 后必须容器内 ps 复核。

### Decision Log（2026-10-05 bug-363 终审追加）
- 终审 READY（范围 4d7953fc..441bdccc，9 笔已推 origin/pisuan-custom）。标记纪律裁定：YAML/Dockerfile 不在 [pisuan-custom] 标记约定语法内（guide 只定义 CSS/JS/Vue/package.json 五种），部署面定制靠 guide 7.2 清单行保护（441bdccc 已补列 docker-compose.yml/api.Dockerfile 两行及合并策略）。
- 遗留待办：①bug-365（存量 storage_path 断裂，受影响 f7b40b18 一条）w1-candidate 待立项；②.wolf/bug363-stale-coal_mining-backup/（清淤可逆备份，untracked）留待 bug-365 裁定后决定去留；③横城 a44afc93 停 FAILED_PROVIDER，择机 retry 即从 p128 断点续跑（费率窗口自选）；④O6 观察窗已获首批真实数据（template_match 317/335、match_count=1×40），写手侧 writer 来源调用仍为 0，观察继续。


## 2026-10-05 晚间追加（横城 retry 第 2 跑会话）

- [2026-10-05] 触发服务层任务（如 retry_task）的容器内直调模板（已实测入队成功）：`docker exec worker python -u -c` → 同步 `pg_manager.initialize()` → `get_domain_factory_service()` → `asyncio.run(svc.retry_task(id))` → `os._exit(0)`。retry_task 语义：FAILED_PROVIDER + 非空 source_paragraphs → resume=True，重置 UPLOADED 清 error，经 tasker.enqueue 入 worker 队列执行。
- [2026-10-05] ETL 泛化模型绑定不在 .env：查 `config_options` 表 key=system_options 的 default_model（当前 `openai2:agnes-2.5-flash` 云免费档）。`.env` 的 OPENAI_API_BASE（host.docker.internal:8080 宿主代理）只服务闲聊 gguf（gemma）——探活勿误探本地代理得出「端点健康」的假乐观（本次教训：探活先查 system_options 真实绑定）。
- [2026-10-05] agnes 免费档是耗尽型配额非冷却型（实测：报错语義 reached the API rate limit for free users/upgrade to Token Plan；等 2h 后 resume 仍 45 秒即触熔断）。「等窗口再试」对该档位无效，方向只有换 provider/升级 key/接受本地模型质量折衷。- **2026-10-05 横城 retry 第 2 跑后拍板**：agnes 免费档耗尽型配额（第 3 次观测），用户选择 D=挂起静置横城 a44afc93（FAILED_PROVIDER 安全终态，resume 点 p222）。不换模型、不重试、不设自动探活；重启用 = 用户提供新 key/换 provider 后一条 retry_task。Step 2 口径采集（bug-363 挂起判定）继续挂起，阻塞点=外部配额而非代码。

## Key Learnings 重建 + DNR（2026-10-06 spec-W1 收口窗口；14:12 stash 事故后工作区版本重建）

- 【DNR 2026-10-06 14:12 事故】多 agent 共享工作树内**禁止 git stash**（push/pop/checkout 全变体）：某 agent 按旧版「git stash 对拍」建议执行，把并行工作流 7 文件未提交改动与 .wolf 台账增量（buglog bug-366~370/cerebrum +56 行/memory +278 行）整体卷入 stash@{0} 且未 pop。台账三件已捞回（buglog 整体还原 325 条/memory 增量合并/cerebrum 本块重建）；6 个禁碰文件的外部改动仍存于 stash@{0}，恢复待用户裁决，**stash 在用户确认前不得 drop**。
- buglog.json 台账写入须串行：多 agent 并发写为 last-writer-wins，subagent 报告「已写入」后控制器应读回验证（本次与 stash 事故叠加造成双重丢失表象）。
- ruff 不在 pisuan-api:0.7.3 镜像内（无二进制也无 python -m ruff）——用宿主道：`cd backend && python -m ruff ...`（0.15.12，config 由 pyproject.toml 就近发现）。
- ruff 0.15.12 E501 按**字符数**计宽，非 unicode 显示宽（两轮探针实证，此前的 unicode width 记载系误报）；实操以 `ruff check` 输出为准收行，勿目测推断。
- dict(model_dump()) 与 json.loads 的 key 存在性语义不同：前者恒物化默认字段（空串占位），setdefault 兜底网对其失效——泛化双通道（structured/prompt）同构兜底须用空值判定 `if not d.get(k)`（bug-369，fix 377440fc）。
- services 单测道分野：实例化 DomainFactoryService() 的单测（pre_commit_validator/validate_task_report/commit_pipeline_status 等）在 __init__ mkdir user-data → :ro 挂载必炸（OSError 30），失败形态与回归不可分辨。有效道：`docker run --rm -w /tmp -v ".../backend:/app" pisuan-api:0.7.3 pytest /app/test/unit/services/... -q`；判回归先跑批前基线临时 worktree 对照。

## stash 合并找回（2026-10-06）
- pre-existing lint 欠账先例：HEAD 上 domain_factory_service.py 16 处 E501、tools.py 3 处、test_commit_pipeline_status.py 1 处——判定归属用 `git stash` 对拍 HEAD；自己的新行必须 ≤120。
- (2026-10-05 W2-T2) coal-eia-writer stage JSON 结构：chapters 为 dict(cid→{title, sections})，sections 是 list[dict] 富对象（id/title/elements/uses/slots/role；此前误记 list[str]，0d3abee8 勘正）——计划脚本按 dict-of-dict 写的 .values() 会炸，layer-1 按「逐字随迁」保留富对象，渲染器节题取 title 字段。corpus_census/chapters.json 的章题字段 n 含尾随页码（如 "1 总 论 5"）与编号前缀，必须 norm()（剥空白/尾数字/第X章前缀）后才能比对。
- (2026-10-05 W2-T2) report_skeletons 三层词汇权威链：stage JSON（唯一定稿词汇）→ layer-1 canonical/optional → 语料 aliases（只登记语料原文，禁臆造）。规则引用章题必须 defined 于 canonical∪optional（alias 不算 defined）。R4 裸名「回顾评价」语料 0 章级出现，曾登记为 planning optional 槽位，控制方裁决改绑 canonical 全称「矿区开发环境影响回顾性评价」（require 语义=校验性在场，canonical 已含则 no-op）并删裸名槽位（c9b0e391）。定则：规则抽象槽名在 layer-2 绑定 stage 定稿全称，optional 槽位只放 canonical 没有的章——裸名槽位会让 require 注入重复章。10 个近形/歧义 alias 未登记留 Task 4 差异单（见 commit 1f92038a 说明）。
- (2026-10-05 W2-T2) Git Bash heredoc 写中文 JSON 可靠化模式：cat<<'EOF' 落盘后必须用 unicode 转义独立核验关键字面量（canonical==stage 重算、alias∈语料集合断言）——本次 「」“”、『』 全角标点实测存活，但若无断言属赌博。另：python -c 内联中文在 GBK 控制台会乱码，一律 PYTHONIOENCODING=utf-8 + TextIOWrapper(sys.stdout.buffer)。
- (2026-10-05 W2-T2 评审) 计划假设「underground/openpit 差集恰为沉陷/爆破章」被证伪：两 stage 实有 6 处同实异名（总则/总论、地表水双拼笔误、选址±分析、资源±评价形、结论±评价）+1 独有（爆破）。教训：凡「合并/差集」类计划假设必须先用真实两集合逐章比对再落数据；layer-1 canonical 应取单一 stage 基准（井工 20 章），变异走 alias、独有走 optional（0d3abee8）。
- (2026-10-06 W2-T2 收尾) seed_gen（scripts/seed_gen.py:123/:124）章级消费 key_elements（构造 generation_hint）与 writing_patterns 两字段、.get 容忍缺失不报错——layer-1 报告骨架章值必须随迁这两个字段（stage 章级全量携带，f7ba64e0 收口）；rule 激活型 optional 槽位（无 stage 源）按缺省 [] 不得臆造。日后改 layer-1 章值 schema 先 grep seed_gen 消费面。
### W2 三层模板窗口（2026-10-06）
- 渲染器输出章键 = slot_id 小写（CH3→ch3）对齐 depth_targets/{stage_id}.json 键；重编号 ch1..chN 会错位，seed_gen 按产物章键查表缺章即 FAIL（设计行为，禁静默默认地板）
- depth_targets 按矿型分文件（project_eia_underground/openpit.json）；optional 章 slot_id 用 OPT_N 独立命名空间（按章题对回 openpit 原键会与 underground CH12 冲突）
- l3 sections 短词菜单对 layer-1 定稿节题 0 命中（exact/子串都不全中）——v1 渲染器只消费 depth+tables，sections 留 P2 参考
- seed_gen 章级消费 key_elements/writing_patterns、节级 elements——layer-1 schema 改动前先 grep seed_gen 消费面
- 改数据裁决先查证语料实测（郭家台 ch16=「污染物总量控制分析」非裸题「总量控制」），alias 命中路径可能已天然存在
- (2026-10-06 W2-T2 终件) rules R5 host 匹配口径实测：c == host or host in c——「规划实施环境影响预测与评价」仅命中 planning ch6，tracking 章题因「总体」「后续」断子串不命中，host miss=静默 no-op（R5 note 定稿口径）；写「命中范围」类 note 前先写断言实测，勿凭章题形似推断。
- (2026-10-06 W2-T3) 语料事实：universe 35 份中无任何文档同时满足 R3（guideline_version=revised2019，仅五间房且 round=first）与 R4（round=revision 的规划全为 legacy）——「planning revision 15 章 + R3/R4」作为单产物断言不成立，须拆成五间房(R3,15章)与修编组(R4,13章)两条；验收书归并表述时先查 conditions.json 实测交集。渲染器 committed 0a1230e8，留痕语义=每动作 append（R2/R3 出现两次属预期）。
- (2026-10-06 W2-T3 评审修) Do-Not-Repeat：产物数据容器形态以唯一消费方实测为准（seed_gen.py:126 按 list 迭代 sections），勿信计划文档对「兼容格式」形态的描述——计划写 dict、权威源实为 list[dict]，逐字落地会把计划级事实错误带进产物（评审捕获，bug-367）。渲染器终态 commit 66654a9d（0a1230e8 已被其取代）。
- [2026-10-06] 宿主机跑后端单测：宿主 python(3.14) 无 langgraph 等项目依赖，backend/test/conftest.py 顶层 import 会炸——独立单测用 `python -m pytest <file> --noconftest` 绕过（测试文件自带路径解析，无需 conftest）；权威验证走容器
- [2026-10-06] 当前运行栈 = pisuan-localized-* 容器（挂载 C:\workspace\pisuan-localized，非 pisuan 工作树），api-dev 容器不存在。Docker 验证替代法：`docker run --rm pisuan-api:0.7.3 -v pisuan/backend/{server,package,templates,test,scripts}:ro→/app/... -w //app python -m pytest ...`（compose 同款挂载布局；Git Bash 下容器路径加 MSYS_NO_PATHCONV=1 防 MSYS 改写）
- [2026-10-06] layer-1 骨架模板 JSON 与 corpus_census fixtures 的写回约定：indent=2 + ensure_ascii=False + CRLF + 尾换行；json.dumps 后 bytes.replace(
,
) 写回可字节级复刻原格式
- [2026-10-06] 派工词自洽性检查：派 Task 前把指令里的每条断言与 cerebrum 已记事实交叉核对（本次 Task 5 派工词写「planning revision 产物 15 章含 R3」，与已记事实「R3×R4 语料交集为空，revision 全 legacy」直接矛盾，致实现者推理卡死 600s 被 watchdog 杀）。修法：派工前重读相关 DNR/Learnings 条目
## Key Learnings (append 2026-10-06 W2 Task5 渲染存档+seed_gen 冒烟)
- conditions.json universe 中 R3×R4 交集为空：唯一 revised2019 规划语料是五间房且 round=first，15 份 planning revision 全 legacy——「revision 且 revised2019」的渲染存档不存在，R3 触发与 round 无关。
- 渲染器 applied_rules 按 add/remove 目标逐条留痕：openpit 的 R2、revised2019 的 R3 各出现两次，是现有行为非 bug。
- 渲染产物章键 = layer-1 slot_id 小写（planning/tracking CH1 起号、project/post CH0 起号），与 depth_targets 键同形；optional 章 = opt_N。
- seed_gen 对渲染产物缺 stage/std_ref 字段不报错（.get 默认空串，仅 SEED_READY 显示名与模板名退化）——契约缺口但非错误；若要补应改渲染器，禁改 seed_gen。
- seed_gen 的 SEED_PYDANTIC 在 pisuan 布局恒为 SKIP：KF_SCHEMAS 路径 app/extensions/knowledge_factory/schemas.py 属 coal-eia v1 仓库布局，pisuan 无 backend/app；_infer_backend 解析到 agents/backend 不存在。断言数>0 即达计划门槛。
- exemptions 字段是适配度测试的语料侧注记，渲染器完全不消费（只用 6 维条件）——「无豁免干扰」只影响存档出处叙述，不影响渲染输出。
## Do-Not-Repeat 追加（2026-10-06 bug-355 窗口）
- 计划内嵌测试 fixture 涉及合成 docx/OPC 时：关系 Type 必须用真实 officeDocument reltype（python-docx 按精确 Type 找主部件）；.rels 内相对 Target 的 base = .rels 所在部件目录（word/_rels/document.xml.rels → word），写 word/document.xml 会解析成 word/word/... 恒假悬空。先在解释器里验证 fixture 可被真实实现满足，再定稿计划。
## Key Learnings 追加（2026-10-06 bug-355 窗口）
- `.wolf/corpus-census/patched/` 两份（九龙川 145MB/巴拉素 39MB）是普查术后**修复副本**，docx_guard.diagnose 判 ok 属正确直通；要在真实大文件上验证悬空修复路径，须内存注入 Target=NULL 病灶（zip 内重写 .rels 后 BytesIO 喂入），不要期待 patched 原样判 dangling。
- changelog 的 dated 小节排序为**旧→新**（09-27→10-05），新小节插在文件已有最新小节之后；同日工作并入既有同日期小节（bullet 追加到节尾），不另开小节、更不回插旧小节（w2v2 勾账 2026-10-06 实操）。
- 宿主 Python 缺 aiofiles 等依赖（2026-10-06 实测 ModuleNotFoundError），凡 import yuxi.services.* 的单测宿主必炸——只能容器道 `docker run --rm -v "C:\workspace\pisuanackend:/app:ro" pisuan-api:0.7.3 pytest ... --noconftest`；宿主 --noconftest 道仅限自包含测试（不 import yuxi 模块，如 test_docx_guard）。
- Git Bash 下 docker 传 /app 路径会被 MSYS 改写成 C:/Program Files/Git/app/...——容器命令一律加 MSYS_NO_PATHCONV=1 前缀（2026-10-06 spec-W1 Task1 实测）。
- domain_factory_service._UNIT_RE 单位字符类 m[²23]/[dha] 只认 ASCII m3，不含上标 ³——docx 语料相关 fixture/正则凡涉及 m³/h 一律写 m3/h。
- DNR(2026-10-06): 计划里测试期望值必须对照 fixture 数据重算再落笔——Task2 的 (2,3) 算术笔误（散文三值分母应为 4）被 TDD 红相揭出，实现者依规停手报告而非改实现，流程正确。
## Key Learnings 追加（2026-10-06 spec-W1 Task3 质量修复窗口）
- ruff 不在 pisuan-api:0.7.3 镜像内（无 ruff 二进制也无 python -m ruff）——ruff check/format 用宿主道：`cd backend && python -m ruff ...`（宿主 3.14 虽缺项目依赖但 ruff 自身可跑，config 由 pyproject.toml 就近发现，0.15.12 实测）
- ruff 0.15.12 E501 计宽口径【两轮探针实证修正 2026-10-06】：按**字符数**计，非 unicode 显示宽（复筛者探针：120 字符/160 显示宽的 CJK 行未被标记；此前"unicode width"记载系 impl-t3-fix 误报）。实操结论不变：以 `ruff check` 输出为准收行，勿目测字符数或显示宽推断
- dict(model_dump()) 与 json.loads 的 key 存在性语义不同：前者恒物化默认字段（空串占位），setdefault 兜底网对其失效——泛化双通道（structured/prompt）做同构兜底时须用空值判定（if not d.get(k)）而非 setdefault（377440fc I-1）
## Key Learnings (append 2026-10-06 spec-W1 Task5)
- docker run ro 挂载跑实例化 DomainFactoryService 的单测（test_commit_pipeline_status 等）会炸在 __init__ 的 mkdir user-data（Read-only file system）——加 `-w /tmp` 让相对路径落可写层即可，勿误判为代码回归。服务类单测容器道模板：`-e PYTHONPATH=/app/package -w /tmp -v ...:ro`（PYTHONPATH 保证挂载代码优先于镜像 site-packages）。
## Key Learnings 追加（2026-10-06 spec-W1 Task5 窗口）
- services 单测道分野：test_w1/test_docx_guard 自包含（__new__ 绕 __init__）→ :ro 挂载可跑；但任何实例化 DomainFactoryService() 的单测（pre_commit_validator/validate_task_report/commit_pipeline_status）在 __init__ 里 mkdir user-data/domain_factory → :ro 道必炸（OSError 30），失败形态与回归不可分辨。有效道：`docker run --rm -w /tmp -v ".../backend:/app" pisuan-api:0.7.3 pytest /app/test/unit/services/... -q`（rw 挂载 + 容器临时 workdir，不污染宿主）。判回归先跑批前基线 worktree 对照

- [2026-10-06] 任务书给定的代码块可能自带 lint 错（W2v2 Task1 测试文件 import json 未用，ruff F401 落在新 diff 内、违反 Step「零新增」预期）——逐字照抄后必跑 ruff 核对；为满足门禁删除未用 import 属 lint 合规修正而非改写设计，照做并在报告中记偏离即可。
- (2026-10-06 W2v2-T3) Do-Not-Repeat：Windows 下禁用 `f=$(python -c ...)` 捕获中文再回传 python argv——GBK/UTF-8 双重损坏（bug-373）；改单 Python 驱动进程 subprocess 列表参数。另：任务书背景预期可能漏记 generated_from.conditions 透传元数据的刷新（openpit exemptions 因 W2 存档与 selector 首匹配条件条目不同源而变），重渲前先 diff 核对旧存档 conditions 与 conditions.json 首匹配条目是否同源。

### Key Learnings（2026-10-06 W2v2 T4 fit 白名单追加）
- fit 测试 _order_pass 的「摘章→重插允许前置章之后」可达性判定：递归 DFS 必爆栈（移动序列长度无界），且栈序探索在多 mover 文件上 37s 级；best-first（heapq + 逐位差异数启发式）同语义 0.16s。可达性判定与探索顺序无关，改探索策略不改 verdict（bug-374）。
- fit order 白名单方向语义：「chapter X, after [Y]」= 从 expected 摘出 X、重插到 Y 紧后。相邻互换 [A,B]→[B,A] 的 mover 必须是 canonically 靠前的 A（摘 A 插到 B 后），不是 B——方向写反词条恒 no-op。土壤/固废互换 8x 的词条主体是土壤不是固废。
- 收敛后分布 natural=14/whitelist=21/exempt=0（35/35），阈值 order_ok>=33、exempt<=2；w2v2 渲染窗口双道（宿主+docker pisuan-api:0.7.3）46 passed（37 fit + 9 w2v2，任务书 8 为旧口径）。

- (2026-10-06 bug-376) DNR：sed 按行号删样式/代码块前，必须用带行号+显示缩进的输出（cat -A 或 sed -n '=;p'）核对边界行是「空行」还是「缩进闭合 }」——SettingsModal 删 Star 卡样式时把 2 缩进中间层闭合当空行多删，less 括号失衡，且 vite sourcemap 把报错行号错位到 script 区误导排查。纯删除类改动收口必须过编译验证（宿主无 node_modules 时用容器：docker exec web 容器 node -e less.render 提取的 style 块；bash 括号计数 python 一行即可预检）。
- (2026-10-06 bug-376) vite [vite:css] [less] 报错行号经 sourcemap 还原，SFC 场景下可能错位到非 style 区——别信行号，先提取 style 块单独喂 lessc 定位真实错误。

## Do-Not-Repeat 追加（2026-10-06 W3 Task2）
- 2026-10-06: 任务书「照抄即可」的实现代码也可能有逻辑 bug 且与其自带测试矛盾（W3 Task2 min_permissive_scope 片段把最窄者胜写成最宽者胜，1 failed 揭出）。TDD 红相时先裁决哪侧错：测试名/docstring/合同语义三方一致时测试即规格，改实现不属 bug-361 的「即兴篡改」；裁决不了才停手报 BLOCKED。与 2026-10-06 早前 DNR（测试期望算术错须停手）互补：看错的是测试还是实现。

## Do-Not-Repeat (2026-10-06 W3 Task 3)
- 2026-10-06: 任务书测试块逐字照抄后仍可能红——本次 baseline 断言期望 ["measurable"] 漏了「涌水量」命中槽名模式产生的 reusable。红相判定顺序：先对拍现场既有同 fixture 测试（test_w1_prose_pipeline.py:46 成员断言）确认真实基线，再决定修测试期望还是修实现；禁止为了让测试过而改实现语义。本次实现零改动、仅修断言（bug-378）。

## Key Learnings (append 2026-10-06 W3-T3 qualrev)
- _etl_pipeline_async 泛化块（:898-1003）的 except Exception as para_error 会吞掉块内一切异常——W3 归属挂钩插在熔断分支（:988）之前且无独立守卫，repo 瞬时故障会静默跳过 FAILED_PROVIDER 持久化（bug-342 同族）。挂建议层钩子进这个 try 必须自带 try/except，否则熔断可靠性降级。
- generalize_paragraphs 的 results dict 插入序=并发完成序（非文档序）；依赖「首个」语义的聚合要意识到这一点。
- W3-T3 验证通道：MSYS_NO_PATHCONV=1 docker run --rm -v "C:\workspace\pisuan\backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_scope_pipeline.py --noconftest -q（15 passed）；W1+T2 回归 47 passed 同命令多文件。

### Key Learnings（2026-10-05 W3 Task4 追加）
- 任务书自带的 fake repo fixture 可能与同任务书给的生产实现不自洽（bug-380：FakeRepo getter 返回无 id 键 dict，真实 repo 契约是 [{id, scope, extra_meta}]，service t[id] 即 KeyError）。修复方向永远是 fake 向真实 repo 返回 shape 同构（dict(原dict, id=i)），不是改生产代码迁就 fake。
- domain_factory_repository.py 既有 lint 旧账基线（HEAD）：I001×2 + E501×1（:144）；domain_factory_service.py 14 处（F841×5/E741×4/E501×5）。归属判定用 git show HEAD:<file> | ruff check --stdin 对拍，工作树新增违规数 > 基线即自己引入。

- 2026-10-06（W3 编排层复盘）：单窗出现 3 处计划勘误（bug-377 min-permissive 片段宽窄写反、bug-378 测试期望漏 reusable、bug-380 fake fixture 与生产代码不自洽）——共同根因：**计划里的代码块落笔时未经实跑**。后续写计划时，测试 fixture 与关键纯函数片段应先在容器道干跑一遍（哪怕只跑 pytest --collect 或直接 python -c 执行函数对照断言），再写进计划；实现者侧裁决基准不变：测试+spec+docstring 三方一致时修计划侧，实现零语义偏离。

- [2026-10-07] 按模板生成数据时，先读真实表头（含括号内枚举注解）再逐列对位；严禁凭记忆猜列名，dict.get(c,'') 的默认值会静默掩盖键不匹配（bug-361）。

- [2026-10-07] coal-eia-writer 节稿里的 {{SLOT:key}}/{{TABLE:族}} 是设计契约（SKILL.md「数字永不经过 LLM」，build_output.py 终稿渲染，SL1 门禁只查终稿残留=0）；评审节稿时看到占位符≠泄漏缺陷，别再误判（bug-362）。

### Do-Not-Repeat
- [2026-10-07] 排查 agent run 报错先查 worker 日志不是 api（arq 任务跑在 worker）；错误时间要换算时区（日志 CST=UTC+8，agent_runs 是 UTC）。
- [2026-10-07] tool_audit 守卫的 sequence 是「事件流内序号」非稳定事实——每次 resume/checkpoint 重放都重新编号；判断幂等冲突时不能把流序号当持久化事实。

### Key Learnings
- [2026-10-07] coal-eia-writer 深度地板全表失校（test2 实测）：ch11 地板 1500 vs 实际 22380（15 倍）、ch13 9000 vs 60531、ch5 3800 vs 16119——地板只防结构性缺席，不防单薄；两轮实测数据已够做 calibrate 校准（二期待办）。
- [2026-10-07] 表号/节引用格式规范不在节写者契约（SKILL.md/派发契约无此条，content_guidelines.md 仅一行 `表X-X` 且与写者实际输出/终稿格式三方不一致）；「表 X.Y-Z」含数字-数字串会与标准编号枚举正则产生模式冲突，test2 靠终稿批量改 142 处消歧——规范应左移到写作契约。
- [2026-10-07] coal-eia-writer 交付现场唯一路径是工作区 outputs/（agent finalize 生成）；外部验证勿另建 deliveries/ 之类并行目录，会造成 delivery_manifest 分裂。

## Key Learnings（2026-10-07 范式库 P0 会话追加）
- sample_entities 黑名单含类别级通用名词（自然保护区/水源地/基本农田/地下水/国道/边沟…来自 ETL 抽取噪音）；实体扫描必须用「≥3 份语料黑名单子串共现→通用词豁免」规则，否则 15+ 处误报。运行时泄露门不在 build_output.py（grep 无 sample_entities 引用），防线在契约指令层。
- 语料文件名本身含矿名实体——任何要进 skill references 的资产，溯源脚注用匿名源编号（源①-⑤），明文映射放 docs/vibe 设计文档。
- 范式/mock 派发产物过残留门前，先剔除合法 {{TABLE:}}/{{SLOT:}} 渲染标记——RESIDUE_RE 在真实管线中于渲染后扫描，裸跑必误报。
- 残留门禁词含裸 `XX`——契约/范式素材禁用「20XX 年」式占位，改示意年份；同理 [待确认] 形态的方括号只可用于缺项标注。
- 本栈容器名是 pisuan-localized-api-1/worker-1（CLAUDE.md 里的 api-dev/worker-dev 已过时）；docker exec 裸容器路径须 MSYS_NO_PATHCONV=1，docker cp 源路径用 Windows 风格。

## Decision Log（2026-10-07 追加）
- 范式文件注入体积超 800 tokens 预算（analysis.md ~1200）：用户裁决接受现状——范式完整度优先，A2 已实证行为有效；实测派发预算吃紧时再裁剪，不预防性瘦身。

- [2026-10-07] Key Learning: coal-eia 表头 cell 禁裸 `|`——stage forms 列定义枚举分隔约定为 `/`；`_md_table` 执法：表头含 `|` 硬 FAIL（防上游同步回灌），数据 cell 含 `|` 转义 `\|`（consistency 槽位寻址 `[井田|煤层]` 属正当内容）。
- [2026-10-07] Key Learning: 技能自带测试（scripts/tests/）宿主 pytest 跑不了——收集链沿包路径拉起 yuxi `__init__` → langchain 缺失；惯例是 docker cp 到容器 /tmp 或运行栈技能树内跑（运行栈有 pytest）。
- [2026-10-07] Do-Not-Repeat: 清点 JSON 内缺陷面不能只靠一种形态的 grep——纯中文列名（无 en 键前缀）躲过 `'"key …|…"'` 模式漏网；必须对 JSON 结构程序化 walk 断言归零（本次靠复核 assert 抓到第 29 处漏网）。
- 2026-10-08：清点 LLM 改写残留时不能按旧块索引去读改写后的文件——改写把标记独立成行会在块内引入空行，重 split 后索引漂移；一律按「当前违规扫描」重定位（bug-394 踩过）。
- 2026-10-08：对带既有格式漂移的文件（如 consistency.py）跑整文件 ruff format 会把无关重排卷进提交（236 行噪音）——先 `ruff format --diff` 看作用面，只手工格式化自己新增的 hunk；漂移是历史遗留，不顺手「修」。

## Key Learnings（2026-10-08 Task2 schema_linter 追加）
- 任务书 CLI 代码片段（counts.get 式增量）与其自带测试断言（零违规 stage 取 counts["L1"]==0）矛盾——原样实现必 KeyError。裁决沿用 W3 规则：测试+契约一致时以测试为准，实现侧零填充 dict.fromkeys(CHECKS,0)（第 4 起「计划代码块未实跑」族，bug-377/378 同根因）。
- coal-eia-writer stage 复合字段的真实形状：fields 字符串清单条目是行内注记 "en_name 中文label"（同串空格分隔），纯中文列名（气温）与单字母列名（m/H）合法；spec 假设的 labels/columns dict 映射在 5 stage 中不存在（实现保留为旁挂兜底）。L4 判裸奔=英文蛇名行内+映射均无中文。
- stage 枚举真实分隔符是 `|`（bug-393 旧残留，L2 管）而约定分隔符是 `/`；L5 词表分段不含 `|` 是有意的——两检查各管各的，别把 `|` 加进 L5 分段集。

- [2026-10-08] 宿主 pytest 跑不了 coal-eia-writer skill 子树测试：pytest 从 scripts/tests 上溯 rootdir=backend/pyproject.toml，按包链 import yuxi/__init__.py → 宿主无 langchain_core 必炸（从 skill workdir 跑也一样）。正解=按 plan「docker cp 后容器内跑」：docker cp scripts pisuan-localized-api-1:/tmp/xx && cd /tmp/xx && pytest tests/ -q（容器 py3.13）；容器内 /app/skill-sources 与 /app/package/pisuan 两投影可能滞后 git HEAD，别拿它们当真。

## Key Learnings (2026-10-08 coal-eia-writer hardening 追加)

- 运行栈容器名已从 `api-dev`/`worker-dev` 变为 `pisuan-localized-api-1` 等（compose 项目名切换）；docker exec/cp 前先 `docker ps` 确认，CLAUDE.md 中的旧名命令会失败。
- host pytest 跑 skill 内测试会沿包链 import `__init__.py` 触发 langchain_core 缺失（Col node error）；规范跑法是 docker cp 测试文件到容器 /tmp 工作台再 pytest。prepare_corpus 单测顶层仅标准库依赖，容器内无需 python-docx。
- promote_headings 三守卫：节号 ≤12 字符、题名 ≤30 字、无句读标点（。；，；顿号豁免）。书名号长真标题（与《规划》符合性分析，34-45 字）会被误杀——参数待 Task 4 实跑统计后定。
- 数字结尾的正文标题（如「1 抗震设防烈度 7」）与目录行形态重叠，is_toc_line 会误判单条；仅 ≥3 连续才剔除，量级待 Task 4 观察。

## 2026-10-08 corpus_meta 批次追加
- Learnings: 语料「整报告字段」（省/标准/规模）必须按 rid 聚合全部切片再判定，逐片算会被后片覆盖（bug-405）；省名整文频次判定 31/31 全自动命中，且 019「吐鲁东」正文实锤甘肃肃北——文件名直觉会错、频次+归属短语对；「青海云杉」类物种名是省名假信号。
- Learnings: 附件清单三种形态全收才算全：裸头「附录:」+编号行、「附录N:」标点、「附录1 委托书」空格分隔（最后一种最易漏）；标准号有 5 位号（GB20426），\d{1,4} 会截断。
- Learnings: planning 公参附件 required=0 是命名碎片化的真实信号（公众参与调查表/相关材料/说明 各自计数），语义聚类明确推迟，勿加 ad-hoc 同义归并。
- Do-Not-Repeat: 宿主跑技能测试须走 $TEMP/pc_host 工作台（仓库 conftest/包链会把 pytest 劫持到 yuxi.agents → langchain_core 缺失）；工作台根目录勿留测试副本（import file mismatch）。
- Do-Not-Repeat: 从 file_name 抽年份须防产能误匹配（041「2000万吨年」的 2000 不是年份）。

## 2026-10-08 数值护栏批次追加
- Learnings: section_expectations v1.1 range 双门槛（RANGE_UNITS 强度类 + distinct-rid≥5）；实测「节×强度类」粒度 31 份语料撑不起 P5-P95（644 组 580 组 n=1，n≥5 真口径仅抑尘效率 n=8）——强度类信号在自由文本且短语高方差，forms label_map 全是 extensive。激活路径：stage 级 curated 词表（跨节聚合）或部分二槽位抽取，机制自动生效。
- Learnings: ruff format 会归位旧基线 E501（bank_compile 3 处），提交前 make/ruff format 本就会清——diff 里出现基线行变化先查是否 format 所致再定夺。
- Learnings: QUANTITY_RE 量词截断垃圾形态（「所占比例分别/评价区所占比例仅」）能到 n=5-6 覆盖——未来数据变厚需短语合理性过滤，本轮靠门槛挡。

- (2026-10-08) 候选三分类规则: MEASURE_RE(回用率|利用率|处置率|*效率|完好率|入洗率|节水率|脱灰率|防渗率|达标率|覆盖率)=工程措施类; SITE_RE(频率|超标率|盖度|优势度|城镇化率|保证率|含水率|纵坡|系数|检出限|浓度)=站点背景类——站点类语料区间不构成有效界, 不宜做护栏; 尾部噪声STOP_TAIL要含「可」(除尘效率可), 「分别」残尾「分」靠GENERIC_JUNK挡

- (2026-10-08) 普查修正: label_map 实为跨5 stage forms fields 先到先得合并 178 唯一标签(planning mapped 14/unmapped 200 cap), 此前「57 mapped 全 extensive」口径作废; samples/(裸切片SL3指纹池) 与 samples_bank/slices/(带溯源标记案例库) 分工明确非冗余; bank_compile 七产物幂等可重建, stages/*.json 是全技能唯一结构真源(schema_linter L1-L5 体检, 135 缺 label 历史问题); standards_index 41/62 条 needs_verification 待人工核实=确认流最大存量; 运行态 data//state/ 在技能外由 ingest.py 独占写, 不属数据加工页范围

### 2026-10-09 环评数据工厂统计页批次
- **Key Learning**: eia_data_service 的 QUANTITY_RE 用 importlib 从 bank_compile.py 动态加载（模块可安全导入，技能测试先例），避免口径复制漂移；词表候选口径 = 比率/浓度型单位白名单 {%,dB(A),mg/L,μg/m3} + n≥2 报告门槛（普查 94/96 项全为比率型是逆推实证，几何量 km2/t 随项目走无区间意义）。
- **Key Learning**: attachment_checklist.json 的 stages[stage].base_reports 是 **int 计数**非列表；rids_without_items 是 list；insufficient_base 是 bool。
- **Key Learning**: changelog.md 新批次插入点 = 「### pisuan 定制增量（日期）」节按日期序插在「## v0.7.2」之前；corpus_meta rid 里的 20xx 数字不可当年份（「041-2000」是 2000万吨产能）。
- **Key Learning**: 当前运行栈容器名是 pisuan-localized-{api,web,worker}-1（挂 C:\workspace\pisuan-localized），api-dev 不存在；pisuan 工作树改动到运行栈走 scripts/sync-dev.ps1。
- **Do-Not-Repeat**: (2026-10-09) echarts label formatter 里 dataIndex 是序号，取原始 key 用 stages[p.dataIndex]，不要 stages.indexOf(p.dataIndex)；ResizeObserver 创建后必须 observe 具体元素；图表重试渲染前先 dispose 旧实例。
- **Do-Not-Repeat**: (2026-10-09) web 项目 icon 包实装是 `@lucide/vue`（package.json L24，lucide 官方继任包），**不是** CLAUDE.md 前端规范文字所写的 lucide-vue-next（已过时）——import 用错包名 vite 直接 500（Failed to resolve import）。核实现役写法：grep src 的 `from '@lucide/vue'`。

## Key Learnings + DNR + Decision Log（2026-10-09 数值护栏词表全栈批次追加）

### Key Learnings
- 存量库加新表必须走显式迁移函数：`create_all` 只在 business_version=None（全新库）跑。仿 tool_usage 先例写 `upgrade_business_v9_to_v10`（FOR UPDATE 行锁 + version 校验 + `metadata.create_all(tables=[...])` + 记版本表），并在 storage_migration.main() 接线 upgrade_from。版本表在改名栈叫 `pisuan_schema_migrations`（改名层连字面量都改了）。
- sync-dev 时序陷阱：热重载先拿到新常量（BUSINESS_SCHEMA_VERSION=10）而 DB 还在 9 → api 容器 RuntimeError crash-loop；先跑迁移器再 sync，或预期 crash 后迁移完 docker restart。
- bank_compile curated 挂载门控于 stages forms 字段表（label_map 来自 references/stages/*.json 的 forms.*.fields[].label，经 _map_caliber 后缀归并）；当前语料 5 个校准口径（抑尘效率/除尘效率/生活污水回用率/矿坑水回用率/设备完好率）都不在表内 → 覆盖层机制就绪但真实挂载为零。unmapped 池即 forms 补录清单。
- 集成测试必须容器跑（宿主无 langgraph）；bank_compile 纯 stdlib 可宿主跑——E2E 用 references 副本隔离（cp → 副本写 overrides → 副本内 diff），dev 树零污染。
- TEST_USERNAME/TEST_PASSWORD 缺失 → HTTP 集成测试 skip；服务层直连集成测试（get_service() 方法链 + 前后自清理）是同等覆盖面的替代路径。
- 导出物化数 ≠ range_ready 数：拆分子条目各拿一半值可能掉到 n≥5 门槛下、父条目 rejected 不占位——断言写上界（≤ measure∧range_ready）与 ≥1。

### Do-Not-Repeat
- pytest-asyncio 模块级 async fixture 必 ScopeMismatch（_function_scoped_runner 冲突）；async fixture 一律函数级，幂等初始化（pg_manager.initialize()）放进 autouse 函数 fixture。
- 服务层导出断言勿写 `materialized >= range_ready`（拆分语义使其天然可小于）。
- 宿主 curl localhost:5050 不通（端口映射差异）——API 自检用容器内 urllib。

### Decision Log
- 导入预置状态固化（用户裁决）：measure→approved / site→candidate / junk→rejected 留档 / 「控制效率」→splitting；splitting→rejected 放弃拆分允许（拆分是入口不是义务），splitting→approved 禁止直设。
- section_expectations 获「重写例外」豁免（移出字节不变清单），可逆性由 version 1.1 回落锚 + E2E diff 保证。
- E2E 隔离方案：宿主 + references 副本（bank_compile 纯 stdlib）；零风险不动 dev 树。

## Key Learnings + DNR（2026-10-10 语料元数据标注页批次追加）

### Key Learnings
- 容器内前端检查实操口径（更新 L81 旧记录）：现栈容器 `pisuan-localized-web-1` 无 pnpm，lint 用 `docker exec pisuan-localized-web-1 npx eslint <files>`；且必须先 `.\scripts\sync-dev.ps1` 文件才进容器。vite 语义：router 改动触发 page reload（非 HMR）、新文件链（动态 import）只在导航时按需编译——vite 日志无报错 ≠ 已编译过，容器内 eslint 是前置门。
- `/api/system/ready` 503 的语义：checks 四项 startup/postgres/redis/worker，本地栈 worker 服务不在 → `WorkerUnavailableError` 恒 503、容器标 unhealthy，但 API 全功能正常（业务端点全 200）。看到 unhealthy 先打 `/api/system/ready` 看 checks 明细，别按故障排查；api 容器内端口是 5050 非 8000。
- api 容器 crash-loop 期间 `docker exec python` 走 pg_manager 初始化会挂起（池/锁问题）且迁移工作可能已落库——验证 DB 状态用 asyncpg 直连：`asyncpg.connect(dsn=os.environ['POSTGRES_URL'].replace('+asyncpg',''))`（POSTGRES_URL 是 SQLAlchemy 风格带 +asyncpg 前缀）。
- P2 语料元数据形状：corpus_meta.json 31 报告 stage 分布 planning_eia 17/post_eia 2/project_eia_openpit 6/project_eia_underground 5/tracking_eia 1；annotations 人工层 18 份稀疏（year 15+scale 3）；counts 语义 annotated=有任一标注字段、scale_needs_review=27（corpus_meta scale_basis 口径，不随标注消减）。

### Do-Not-Repeat（2026-10-10 P2 对抗评审追加）
- BUSINESS_SCHEMA_VERSION 每次递增必须同步两份迁移测试：①test_storage_migration.py 六处 SimpleNamespace fake——main() 每新增一个 pg_manager.upgrade_* 调用点，fake 就缺属性 await 即 AttributeError（v10 起已红两个版本没人跑单测）；②test_schema_migration_version.py 的 `assert BUSINESS_SCHEMA_VERSION == N` 版本钉随递增手改。新迁移函数落库时这两个文件与 storage_migration.py 一并改。
- P2 修复提交 b7f63ece（对抗评审 7 条全坐实全修）：导入幽灵行过滤/迁移测试 fake/前端 min-precision-tabindex/测试判别断言。评审工作流脚本存 session workflows/scripts/p2-adversarial-review-*.js，resumeFromRunId wf_be922093-a83 可复用。

## Key Learnings (append 2026-10-10 技能图示)

- **coal-eia-writer 全技能图形化地图已存在**：`docs/vibe/2026-10-10-coal-eia-writer-skill-diagrams.html`（自包含 HTML+内联 SVG，浅深主题自适应）。下次要向新人/模型解释技能结构时直接指这个文件，不必从 SKILL.md 重新蒸馏。两图分工：图 1 分层架构（LLM 层/脚本层/磁盘状态/references 资产 + 琥珀色数值通路），图 2 步骤 0–7 流程（门 1/冻结/门 2/派发循环/要点包/finalize + 发卡即停停车点）。
- **图示时最易画错的三个机制事实**：①子代理直写 state/sections/*.md 绕过脚本层（不经过 build_output）；②progress.py next 是控制器唯一导航（每轮恰好一个下一步）；③formula_state.json 手改=build 门直接 FAIL（唯一写者纪律不只 data/ 有）。

## Key Learnings + DNR（2026-10-10 P3 标准与限值库追加）

### Key Learnings
- **含 `/` 的业务主键绝不能走 FastAPI 路径参数**：standards_index 62 条 code 中 10 条含 `/`（GB/T、HJ/T、TD/T、MT/T），uvicorn 在路由匹配前就把 %2F 解码成真实 `/`，`{code}` 段默认正则 `[^/]+` 无法跨越内部斜杠 → 恒 404（认证层都进不去，401 测试探不出）。此类主键一律走 body/query；`{code:path}` 虽可贪婪回溯但依赖隐晦。frontend/correctness 两维评审独立实证复现。
- **standards_index.json 形状事实**：top 键 version/generated/scope/tier_policy/red_line/standards/limit_tables/gate1_code_checks；standards[].code/title/role/chapters/tier/needs_verification/verified/origin(+note)；limit_tables 顶层含 `_comment` 字符串注释键（遍历时 isinstance(dict) 过滤），7 表中 gb3096_zone_limits 与 gb12348_boundary_limits 各登记 1 行样例逐字锚点（rows 非全空）；tier 五档 framework 21/pending 17/quality_limit 9/emission_limit 9/method_param 6。
- **导出翻转语义与 P2 不同**：P2 corpus_meta_annotations 导出是 `sort_keys=True + 尾换行` 全量重写；P3 standards_index 导出是 `json.dumps(ensure_ascii=False, indent=2)` 无 sort_keys 无尾换行（保原键序 round-trip 字节纪律）——两文件消费者不同，别互相抄。
- 迁移测试判别力范式（对抗评审坐实后已落地）：新增 upgrade_* 调用点的 fake 用 `_record(calls, "upgrade_vN")` 记录调用并在 legacy 参数化测试断言在场（`upgrade_from` 档位全量进 parametrize），真实建表行为由隔离 schema 真实 PG 用例兜底（仿 `_create_isolated_manager("...")` + `record_schema_version(business, N-1)` → upgrade → 断言表存在 + 版本翻新 + 幂等重跑）。

### Do-Not-Repeat（2026-10-10 P3 对抗评审追加）
- 别在测试里钉注册表数据指纹（62 条/7 表/2 行）：合法演进（加标准/加表/加样例行）必误红。期望值从文件 `json.loads` 自算（exp_total/exp_pending/exp_rows），与 needs_verification 的 sum 自洽范式同构。
- 版本表真名是 `pisuan_schema_migrations`（列 domain/version/applied_at），不是 schema_versions——DB 直查版本用 `SELECT version FROM pisuan_schema_migrations WHERE domain='business'`。
- api 容器 startup 失败（如 schema 版本落后）后进程死透不再自动重启，迁移修复后必须 `docker restart pisuan-localized-api-1`；.restart 前先看 logs 尾部判因。

### Do-Not-Repeat（2026-10-10 bug-383 追加）
- standards[].chapters 是分号分隔字符串（"；"），不是数组——Vue 模板里直接插值渲染，别 .join()。前端消费新 JSON 字段前先看实际类型（一句 python type 统计的事），字段名复数 ≠ 数组。

### 三页面深度评审实证（2026-10-10，wf_9e47706a）
- P3 standards_index 双真/双无：10 条 nv+verified 同真（手写遗留违导出协议）+7 条双无（HJ 464/710/192/446+3 行政法规逃出 nv 计数）→ 真实待办 31 非页面显示 41
- _norm_std 不去 T：语料引用全 GBxxxx 形态、注册表 GB/T 形态 → GB/T 14848/19923/50433 三条 cited_count 低估
- 语料共引 206 归一码仅 31 命中注册表（175 未编目，含真标准 GB 18596-2023/GB 27742-2011）；62 条中 31 条从未被引
- consistency.py CC1 恒 manual 死分支（standards_index 条目无 text/summary/year 键，allowed 集恒空）；gate1_code_checks 宣称有门实际零脚本实现（grep=0）
- corpus_meta.json 零运行时消费者（二期）；P1 overrides/ 从未真实物化（曾导出后关开关删除）；30 approved 中 range>=5 仅 6 项达标；P3 是三页唯一有运行时消费方的物化
- 词表 PATCH 后端支持 caliber 改名+note 编辑但 UI 只发 status；corpus_meta.py 消费 ann[province] manual basis 但 P2 页面无录入端
- [2026-10-10] eia_lexicon 拆分/改名机制：split_entry 仅接受 splitting 状态条目（_preset_status 只有控制效率预置 splitting）；拆分子条目 values_json 携带值集，但 export_overrides 仍按 values_json 内 rids 数 ≥RANGE_MIN_REPORTS=5 现算 range，<5 报告的子簇拆了也不物化；PATCH caliber 后指纹 (stage,caliber,unit) 失配，重扫必按旧名重导 fresh 行（_MEASURE_RE 命中→预置 approved），服务层无 tombstone/抑制机制——rename_in_place 必须伴生旧指纹处置才可持久；reject 是唯一重扫自稳处置。

### 词表口径抽取机制（2026-10-10 评审实证）
- 改名≠修复：export_overrides 按 (stage, 提取器产出口径名, unit) 现算取值——改名行新名语料中不存在→永久 skip「已无提及」、n_reports 显示 0；重扫按旧指纹判重→旧断章名复活（_MEASURE_RE 命中即 A 类 approved）。改名必须配 _IMPORT_BLOCKLIST（指纹级抑制）才持久
- rejected→approved 是 PATCH 放行方向：断章名行可被直接点成 approved 并物化破名区间（伤的行 80~80 会物化）——运维规程须写明禁止
- _STOP_TAIL 是单字剥尾（均/分/别/比/占），平均→平、占比分别→空 即此因；QUANTITY_RE 窗口 2-8 字最早起点规则决定头切形态（损|伤的、评|价区）
- 判官裁决范式：rejected 档消费链=0，为它改公共抽取管线是不对称代价； approved 档名称质量才是物化风险所在（处置率/综合利用率/回用率混簇）
- LexiconPanel.vue filters.status 默认 ''（全部视图）——「rejected 默认隐藏」是想当然，9 条留档行用户看得到

## Key Learnings + DNR（2026-10-10 方案B 词表修复执行追加）

### Key Learnings
- 改名 PATCH（update_entry caliber）只改口径名不改 status：原 candidate 行（评价区植被覆盖度值→评价区植被覆盖度）改名后仍是 candidate，而 export_overrides 只遍历 approved——「export skipped 里改名行 6/7」不是数据异常，第 7 个根本不进导出。预期数字前先核每行的 status 流向
- export_overrides 的 fu 检查（首见单位≠条目单位）先于 ent None 检查：改名 approved 行的 skip reason 文案是「语料首见单位已变为 None（跨单位不混布）」而非「已无提及」——fu=None 命中在前，处置语义等价，按口径名归属统计别按 reason 文案
- 方案B 后真实物化 8 条 = 3 拆分子口径（values_json 直挂不现算）+ 5 原始达标行（抑尘效率 planning 15 报告、生活污水回用率/矿坑水回用率/设备完好率/除尘效率 openpit 5-6 报告）；13 条 approved 因 distinct<5 恒 skip（含 underground 除尘效率 3、openpit 预湿的捕尘效率 2）
- 运行栈容器 pisuan-localized-api-1 是 runtime 镜像：无 ruff、无 .venv、`python -m ruff` 也没有——格式检查走宿主 `uvx ruff`（backend/ 下跑以吃 pyproject 配置）；单测 `python -m pytest test/unit/... -q` 正常可用
- 验收黄金断言是 import 的 added=0 + blocklist_skipped=7 与 counts 27/27/38/0；overrides 文件在容器 /app/package/pisuan/agents/skills/buildin/coal-eia-writer/references/overrides/curated_lexicon.json

### Do-Not-Repeat（2026-10-10 方案B 执行追加）
- 验收脚本里的诊断表达式改版后必须重跑取新版输出再引用：renamed_zero_count=[] 曾是旧版脚本残留输出，与地面真值（7 行 n_reports=0 全部成立）矛盾，为它白查一轮——诊断输出与数据操作输出分开看，异常先复算再归因
- python -c 多行中文脚本在 MSYS bash 下引号脆弱（exit 2 无输出）——一律 Write 落盘 .py 再执行（本会话再次验证）

## Key Learnings + DNR（2026-10-10 词表 92 条全量审计追加）

### Key Learnings
- 全量审计分布（92 条，6 裁决+1 对抗核验 21/21 零证伪）：reasonable 33 / minor 19 / broken 16 / mixed 24。**approved 档名称质量最好（0 broken/mixed、13 minor 全是裸名缺定语型）**；rejected 档 35/38 断章或混簇——证明三分类导入预置（junk→rejected）与方案B 裁决方向正确
- **bug-412 量纲混布**：控制效率三子口径值集 p5=0.61 与 p95=90 并存——语料对不同报告用小数分数「0.61%」与百分数「59%~90%」两种书写，拆分对话框值集按提及原值照搬无归一步骤。凡「效率/比例/占比」类拆分都要先查值集量纲
- 9 字超窗头切是断章新主形态（溶解性总固体超标率/贡献浓度占标率/石油类初始浓度设置/环保工程投资占总投资的比例）：原词 9-10 字 > 8 字窗必断。PATCH 改名可超 8 字不受窗限，但改名名不在语料逐字出现 → 扫描零命中 + 导出永久 skip（同方案B 机制，需 blocklist 伴生）
- candidate 档新发现断章 3 条：献浓度占标率（贡|献）、解性总固体超标率（溶|解性）、用地的优势度（一句 16 值对 4+ 地类）；mixed 2 条：植被覆盖度（群落 70% vs 区域 73.71% 尺度混）、风向频率（静风 12.1% 与 WNW 11.1% 同簇）
- 语境可见性 caveat：audit contexts 每条目只导出 2-3 句，n_values=15~16 的条目（设计除尘效率、underground 除尘效率、planning 抑尘效率）属「可见部分零反例但未逐值回源」——物化前全簇核验前置
- get_mentions 只回语料扫描提及（子口径 values_json 不在其中，恒 0）；子口径值集要走 repo.list_entries() 的 values_json——容器内直连 repo 曾挂起一次（原因未明），证据已足时不必硬拉

### Do-Not-Repeat（2026-10-10 全量审计追加）
- 容器内脚本读宿主 Windows 路径必 FileNotFoundError——先 docker cp 送 /tmp 再引用容器路径
- 对「改名行/子口径」跑 get_mentions 验证值集是空转（机制上恒 0），直接读 values_json

## Key Learnings + DNR（2026-10-10 P4 改名对话框设计评审追加）

### Key Learnings
- 前端图标依赖实际是 @lucide/vue（web/package.json），CLAUDE.md 写的 lucide-vue-next 已过时——LexiconPanel.vue:197 即从 @lucide/vue 导入
- base.js:74 把 400 固定映射「请求参数错误」且丢弃字符串 detail——后端 ValueError 文案到 UI 零信息；客户端预检是当前务实解
- Python 码点偏移 ≠ JS UTF-16 码元：mojibake 语料下 mark offset 高亮会静默漂移——跨语言文本标记契约用「后端直发 before/hit/after 三段」根治，禁 v-html 拼
- QUANTITY_RE 的 \s* 可吞空行致 group(0) 跨行块（实测 3/1245）——段落定位须延伸覆盖 match.end()
- business schema 迁移注册三触点：storage_migration.py upgrade_from 增档 + manager 版本白名单 + 新 upgrade 分支，缺一即 v12 库启动 RuntimeError；热重载不重跑 storage-migrator，落栈顺序=先 migrator 再放行 api/worker
- update_entry 是 session-per-call 两事务（manager.py:1909 提交）——跨事务约束（改名+抑制）须先插抑制后 save_entry
- eia_data_service 模块头不变量「纯只读、无 DB 依赖」：需查 DB 的编排放 service 层，纯函数留 data_service（宿主可单测的前提）
- 改导入/扫描语义必须同步跑 test/integration/services 全量，仅跑 unit 会漏 flow 断言红（bug-413 实证）

### Do-Not-Repeat（2026-10-10 P4 设计评审追加）
- 别在 unique 键表上裸 INSERT：循环操作（改名 A→B→A）必撞键 IntegrityError→500，一律 ON CONFLICT DO UPDATE/NOTHING
- 验收样例的行状态别凭记忆写（解性总固体超标率是 candidate 非 rejected）——写前查库，评审员连 id 都会核
- 2026-10-10：前端错误提示契约——backend router 把 ValueError 映射成 HTTPException(400, detail=字符串)，但 web/src/apis/base.js 的 publicErrorMessage 把 400 一律映射为通用「请求参数错误」，extractBusinessErrorDetail 只透传 {code,message} 对象形态 detail（字符串 detail 被有意丢弃）。词表/拆分等对话框里「口径已存在/口径名过短」等后端中文报错到 UI 全变成「请求参数错误」。要透出业务错误信息必须走 {code,message} 结构化 detail 通道。
- 2026-10-10：web/package.json 图标依赖是 @lucide/vue ^1.34.0（不是 CLAUDE.md 写的 lucide-vue-next）；eia-data 组件内 import 惯例 from '@lucide/vue'、:size=14。加图标沿现状，勿引新包。

### 2026-10-12（环评域对账 + P1 需求）
- 技能数据↔环评域工厂页面对账结论：4 页面已闭环词表/标准核实/元数据标注三链；缺口=limit_tables 仅渲染无录入、regional_facts 无写手消费工具、unmapped 池仅计数不可视。P1 三项需求定稿：docs/vibe/2026-10-12-eia-data-factory-p1-gaps.md（含验收 checklist 与 P2/P3 边界）。
- eia_* 服务的导出物化写 _SKILL_ROOT（eia_data_service.py:29 包内技能目录）：运行栈（pisuan-localized 容器）点导出落 pisuan-localized 工作树，须人工带回 pisuan-custom 提交——专家页面运营成果不自动回流 git。
- limit_tables 行 schema 按表异构（噪声 {category,day,night,unit}），_comment 明言唯一录入通道=人工对照标准原件；7 表中 5 表 rows=0 全 nv=true。

### 2026-10-12（P1 实施）
**Key Learnings**
- BUSINESS_SCHEMA_VERSION 加档是**四触点**（比既有记忆多一个）：manager 版本常量 + manager import/upgrade 方法 + storage_migration.py dispatch if-分支 + storage_migration.py `_require_supported_version(upgrade_from=...)` 元组——漏 upgrade_from 时该档存量库直接 RuntimeError 拒启（本次 v14 漏 13，GREEN 阶段单测抓到）
- v14 迁移容器落地：`docker start pisuan-localized-storage-migrator-1`（存量容器，exit 0 即成），验证 SQL 在 yuxi_know 库 `pisuan_schema_migrations` 表（不是 schema_version）；新表 eia_standard_limit_rows
- **api 启动失败后的复活方式**：uvicorn 进程死但容器存活（Up N hours），`docker start` 对运行容器是 no-op，必须 `docker restart pisuan-localized-api-1`；localized api 宿主端口 = **5050**（不是 8000）
- localized 树 backend 路径改名：backend/package/yuxi → **backend/package/pisuan**（grep 验证落栈时勿找错路径）；web 容器内 eslint/prettier 在 /app/node_modules/.bin/（宿主无 pnpm）
- 环评导出物化按 (table_key, id) 全序替换 + nv/verified 仅对有 DB 行的表翻转；list 合并露出「DB 有行而文件注册表漂移掉」的表（录入数据不因文件漂移不可见）
- 前端编辑对话框装载行必须按服务端 schema 投影（文件锚点行带 origin 溯源字段，原样提交必 400 未知限值字段）

**Do-Not-Repeat（2026-10-12）**
- Edit 工具换行连接 bug（本会话 4+ 次）：old_string 以 \n 结尾而 new_string 不带尾 \n → 静默吞并下一行（曾删掉路由装饰器/docstring/压行 import）。两串尾部换行必须一致；批量编辑后必跑 `python -c "import ast; ast.parse(...)"` + `git diff --stat` 验证
- 加业务 schema 档位漏 upgrade_from 元组（见上，v14 实证）
- sync-dev.ps1 必须从仓库根以 `powershell -File scripts/sync-dev.ps1` 跑——cwd 不对时脚本不存在报错进 stderr，链式 && 的后续校验/格式化会对旧文件生效（假绿）
- prettier 只采纳自己新行的形态：eia-data 面板有既有漂移（DomainFactoryView 先例），全文件 --write 会污染 diff；用容器 prettier 出标准 diff 后逐块判断归属

**User Preferences**
- （无新增，沿用 surgical changes / 方案乙同构既好）

## Key Learnings + DNR（2026-10-12 P2 数据工厂页批次追加）

### Key Learnings
- **sync-dev 机械改名层透测试：** pisuan 工作树测试文件写 `from yuxi.services import ...`，sync-dev.ps1 落 pisuan-localized 运行栈时机械改名为 `pisuan.services`——容器内直接 cat 测试文件会看到 pisuan 前缀，非异常。容器内包根 = `/app/package/pisuan`（editable install 映射 pisuan→/app/package/pisuan，无 yuxi 目录）。
- **web 容器 lint/prettier 通道：** 宿主无 pnpm；`docker exec pisuan-localized-web-1 sh -c "cd /app && pnpm exec prettier --write ..."` + `docker cp 容器:/app/... 宿主路径` 回拉格式化版本（防下次 sync 用未格式化版覆盖）。新文件必须先 sync-dev 容器里才有。
- **schema 加档四触点判别力补强：** 迁移单测参数化加「已当前版」档（如 v15 批次加 [15]）可钉死常量触点——常量漏改时该档在 _require_supported_version 即 RED（bug-422 教训：旧参数化 [2..N-1] 在常量停 N-1 时全绿假象）。
- **服务层测试 fake 契约最小化：** 服务端勿直接消费 ORM 行的 to_dict() 等模型方法——服务层自建静态投影（_edit_dict），repo fake 只需 SimpleNamespace 属性即可模拟（bug-421）。
- **Vue 模板字面 `}}`：** 插值内字符串字面量里的 `}}` 会提前闭合插值（解析器无字符串感知），SLOT/花括号记法一律走 script 常量绑定（bug-423）。
- **gate1 语义边界：** standards_index.gate1_code_checks 是规则规格（desc/allowed_patterns/rules）非违规明细数据源；只读卡 = 规则透出 + 注册表自检（codes 对 patterns 比对），不伪造违规计数。
- **eia_data_service 只读通道异常约定：** 同模块 get_unmapped 先例——参数校验失败 ValueError→400；资源寻址失败（eia_stage_service 的 stage/family）KeyError→404。两约定在 domain_factory_router 并存，按模块从众。
- **section_expectations 实况：** sections 为 141 节 dict（chX_SYY → {title, expected_quantities:[{caliber,corpus_freq,field,tier,unit}]}）+ 顶层 unmapped 数组；tier 实况三档 required/contextual/optional。数据 Expectations：per_chapter 为 13 元素 LIST 非 dict。

### 2026-10-13（P3 批次）
- **localized 运行栈容器内包名是 `pisuan` 不是 `yuxi`：** pisuan-localized-api-1 里包根 /app/package/pisuan，`import yuxi` 必失败；debug/演练脚本需 `sys.path.insert(0, "/app/package")` + `from pisuan.services import ...`；test 文件同样被机械改名（非异常）。
- **登录端点 `/api/auth/token` 是 form-encoded：** POST data=（表单）非 json=，json 载荷得 404/422；且运行栈管理员密码与仓库种子脚本（seed_initial_users.py zwj12138）不一致——语义集成测试按 P2 先例 skip-gated，实链验证用服务层实弹演练替代。
- **实弹演练模式（认证 E2E 被阻断时的替代验证）：** 真库插行 → 真技能文件导出 → 字节断言 → 二次导出幂等断言 → 撤行 + 字节快照还原（容器非 git 树，git_restore 不可用）；DB 残留查 0 收尾。脚本存 .wolf/corpus-workdir/。
- **docker cp 回传宿主路径必须带目录前缀：** `docker cp web-1:/app/src/x.vue src/x.vue` 报 invalid output path；目标要写 `web/src/x.vue`。
- **运行栈文件 EOL 地图（P3 实测）：** router/index.js、manager.py、storage_migration.py、models_domain_factory.py、changelog.md(CRLF/LF 注意——changelog 实为纯 LF)、sample_entities registry/_index 为 CRLF；DatasetStatsPanel.vue、formulas.json、新测试文件为 LF。replace 锚点先 `file`/od 验行尾再动手。
- **宿主 ruff 用 `python -m ruff`（0.15.12 pip 装）**，Git Bash PATH 无裸 ruff，容器内无 ruff。

### 2026-10-13（P2/P3 实现与原型偏差纠正）
- **原型评审通过 = 像素级复刻预期，不是「设计语言参照」**（用户 2026-10-13 纠正）：实现必须逐屏对照原型结构/布局/内容组织/视觉样式复刻，不得擅自改用应用既有 AntD 惯例（a-table/a-drawer/a-tabs/页面 shell）；跨 P1/P2 边界组件只改原型对应屏部分。
- **前端交付验证必须含原型↔实现可视对比**（lint/单测全绿≠视觉一致）；运行栈凭据受限时，至少用 chrome-devtools 对静态原型截图，并把实现页留待用户对照确认，不能静默跳过。
- （更正昨日条目）「不再另行出原型」仍成立，但配套含义是「实现=复刻原型」，非「实现=自由发挥」。

### Do-Not-Repeat
- （bug-424）文本级插接注入偏移忽略行首缩进——`_input_line_span` 返回的行带缩进，注入点 = 缩进宽 + 标记串长，裸用标记长度会把 value 插进键名中间（`{"name"value": 0.65, ": "q"`）。

### Do-Not-Repeat
- （bug-422）schema 加档后只 grep 方法名确认≠常量已改——四触点逐一 grep：`BUSINESS_SCHEMA_VERSION =` 行值、manager 方法、storage_migration dispatch、upgrade_from 元组；迁移测试必须加「已当前版」档位。
- （bug-423）Vue 模板插值里写含 `}}` 的字面量（含 JS 字符串）。
- 宿主直接跑 `pnpm`（不存在）——web 工具链全走 pisuan-localized-web-1 容器。
- 容器内 `cp` 回工作树用臆测路径（/workspace 不存在）——回传用 `docker cp 容器名:/app/... 宿主相对路径`。

## Key Learnings + DNR（2026-10-13 P2/P3 原型复刻改造执行追加）

### Key Learnings
- **真实后端数据形状三件套（改造期实证）：** ① `data_expectations.json` 的 `source_hint_vocabulary` 是 `{hint: 说明}` **对象**非数组（for...of 直接 TypeError），`fam.source_hint` 是 `"standards_index + user_planning"` 复合串需 split('+') 拆 chip；② `formulas.json` 的 `formula.slots` 已是 `{{SLOT:...}}` 全记法（仅 `derived_slots[].slot` 为裸名，复用前先 startsWith 守卫）；③ `formula.outputs` 是 `[{name, unit, desc?}]` 对象数组，join 前必须 map(o => o.name)。
- **前端运行栈登录态：** localStorage key 是 `user_token`（非 access_token/token），`/api/domain-factory/eia/*` 带 `Bearer <user_token>` 即 200；运行栈 admin 密码由用户在会话提供（.env 无管理员凭据，严禁 seed 生产库）。
- **共享浏览器验证协议：** 用户并发使用同一浏览器——视觉验证必须 `new_page` + `isolatedContext` 开隔离页，evaluate_script 注入登录态与导航，验完 close_page 清理；直接在用户当前页导航会互相打架（页面弹回总览即此症状）。
- **指标口径教训：** unmapped 是独立数据流而非注册口径 total 的子集——归并数必须正向计数（filter(q => q.field)），用 `total - unmapped.length` 推算在 unmapped ≫ total 时出负值（bug-426）；「覆盖章节」类指标先写清语义再选过滤条件（bug-428）。
- **节标识双记法：** unmapped.section 为原始 `chX_SYY`，注册口径节标识已规范化（`X.YY`）——两侧统一过 normSection（去 ch 前缀 + _S→.）才能按节归位（bug-427）。
- **暗色验证法：** 该项目暗色 = html 根加 `.dark` 类（base.dark.css 翻转同名 token），evaluate_script 一行 `documentElement.classList.add('dark')` 即可截暗色态；factory-ui.less 仅两处 `:root.dark &` 覆写（btn-pri 字 #0a0a0a、unmapped-row td 底 second-100/边 second-600），覆写目标在 **td** 层非 tr（探针读 tr computed 恒透明，勿误判失效）。
- **AntD drawer width prop** 落在 `.ant-drawer-content-wrapper` 的 inline style，`.ant-drawer` 本体 style.width 为空——探测宽度选对节点。

### Do-Not-Repeat
- （bug-429）数据形状假设（数组 vs 对象）放进 try/catch 大包——TypeError 被静默吞掉后页面大面积空白且无任何报错线索；形状解析要么显式炸要么拆出 try 块，勿与业务赋值同 catch。
- （bug-430）对可能已是全记法的字符串无条件二次包裹——先 startsWith 守卫。
- （bug-431）对象数组直接 join('、')——得到 [object Object]；先取字段。
- （bug-426/427）指标做减法推算 + 跨来源 key 直接字符串比对——先确认两来源的记法与集合关系。

### Decision Log
- **诚实数据映射边界（改造期沿用）：** 原型虚构指标不伪造——命中拦截无数据则删该格、P5/P50/P95 无字段则以 corpus_freq 计量条替代、导出 CSV 无端点则去掉按钮、添加人有 decided_by 无时间戳则只出人名；functional no-regression 优先于像素复刻（撤回列保留、样本下拉新增均属数据驱动必要）。

## Key Learnings + DNR（2026-10-13 词表页 s9 复刻追加）

### Key Learnings
- **词表列表接口的隐性重扫：** `GET /eia/lexicon/entries` 每次调用都跑 `_scan_all()` 全语料现扫（报告数/值数「始终现扫」是设计语义），点击筛选后行数据滞后数十秒——筛选交互密集的页面要么接受在途提示（自绘表加 opacity :loading 等价物），要么后端加扫描缓存；旧 AntD 面板同样受累（a-table :loading 转圈），非前端改造引入。
- **长中文语料串 × 表格 nowrap：** 语料扫描出的口径名是任意长句片段，`.caliber-name` 一类 nowrap 样式在 auto 表格布局下 min-content 可达 1586px 撑爆整表；真实数据驱动的自绘表首列文案长度不可假设时，用 scoped `table-layout: fixed` + %列宽 + `overflow-wrap: break-word`。
- **.ewp max-width:1180 在应用外壳内不生效：** 规则存在于样式表但计算值为 100%（环境覆盖，源未定位）；已验收的七个工厂页一致满宽渲染——单页强行收敛 1180 反而破坏一致性，保持满宽并记录。
- **lexicon 条目 decided_by 实况：** 导入预置行 decided_by='import'（非空），UI 来源列「DB · import」直读即可；decided_at 可空（导入行）。
- **抑制名单无列表端点：** blocklist 只有内部查询（import 跳过 / get_mentions 反查），无 list API——原型 s9 的「抑制名单」卡无数据可填，诚实删除并在 note-bar 保留抑制语义说明。

### Do-Not-Repeat
- 原型屏的表格列按虚构短标识（mono 短 id）设计列宽——套用到真实长文案数据前先扫一遍实况数据的长度分布，别等截图才发现撑爆。

## 2026-10-13 元数据页 s10 复刻追加

- 浏览器 DOM 探针三个坑：(1) prettier 会把按钮文本换行缩进，textContent 匹配必须 trim/去空白，精确等值会 find undefined；(2) AntD modal 关闭后 DOM 保留（display:none），判关闭要看 computed display / offsetParent 而非节点存在；(3) stage-chip「全部」文本含计数 span（"全部31"），startsWith 而非等值。
- 真实 meta 标注层只有 year_hint/scale_mt_a/note 三字段（服务端 _ANNOTATION_FIELDS 白名单，越界 400）；corpus_meta.json 自动层只读。原型 s10 的文号/机构列、编辑它们、逐行「未导出」脏标均无数据支撑，勿再造回。
- take_screenshot 偶发 captureScreenshot 协议超时转后台后 failed——立即原参重试通常一次成功，不必换参数。
- 用户反馈（s10 操作列）：表内实心主按钮（btn-pri）批量出现显重；操作列动作一律用 btn-txt 文字链（词表同款），语义靠「标注状态」pill 承担。适用全部工厂页后续改造。
- 配方 mono 字体栈裁定：原型 var(--mono) = ui-monospace/'Cascadia Code'/Consolas/'Courier New'/monospace；factory-ui.less 自创 JetBrains Mono 是偏离，已全改原型栈。后续新增等宽元素一律用原型栈，勿再引 JetBrains Mono（其余面板 scoped 内尚存 3 处 JetBrains：FormulasPanel/StandardsPanel/DatasetStatsPanel，未动待后续批次归一）。
- 原型 .num = 纯 tabular-nums（fw 400）；自创「人工覆盖加粗」类语义已被用户否决——语义区分用 title/辅助 pill，不改文字字重。

## 2026-10-13 标准页 s11 复刻追加

- **seg/chips 徽记计数必须与过滤逻辑同源**：服务端 counts.confirmed 只数 DB 裁决（0），而「已核实」过滤含文件态免核实条目（21）——徽记用服务端数、过滤用客户端谓词会显示「已核实 0」点进去 21 行。裁决：凡徽记数与点击结果需一致的场合，一律客户端 computed 同源计算；服务端 counts 只用于语义确实单一的场合。
- **限值表 source 字段实况**：七张表当前全为 `source:'file'`、needs_verification=true；页头「N 表待导出」pill 按 source==='db' 计数，全文件态时诚实缺席且 导出限值行 disabled。勿假设曾有 DB 录入残留。
- **AntD modal 取消探测时序**：click() 后 wait(400) 查 `.ant-modal-wrap` display 可能误报未关（动画未完）；复探测即 display:none。判定以复查为准，勿当场加第二次点击。
- **gate1 卡样式原样保留价值**：其 scoped 样式（gate1-m baseline 行、viol 虚线分隔、code.k chips）与原型 s7 同款且数据真实，复刻批次只需换 mono 栈，勿顺手重写。
- **pill 字体栈裁定（s11 三轮）**：工厂页状态 pill 的「粗细不符」观感实为 font-family 差异——应用全局 Inter Variable 500 比原型系统栈（Segoe UI/Microsoft YaHei）500 观感更重；计算样式 12px/500/色值本就一致。裁决：共享配方 .pill 显式声明原型正文栈。同族问题（.btn/.stage-chip/.seg 仍继承 Inter 栈）用户未点名，勿自行扩散。


## chrome 布局批次（2026-10-13）

**Key Learnings**
- 本应用无全局 button reset：自绘 `<button>` 必须显式 `appearance:none/background:none/border:none`，否则 UA 默认 ButtonFace+1.6px 描边亮色呈白盒、暗色爆浅灰盒（bug-436）。新写裸 button 极易漏。
- 样式表遍历：现代 Chrome 的 CSSStyleRule 也有 `cssRules`（CSS Nesting），walk 时须先判 `selectorText` 再判 `cssRules.length`，否则所有规则被当嵌套容器跳过、遍历结果恒空。
- 不可见/后台标签页里 CSS transition 被冻结：切暗色后 computed background 停在过渡起点旧值，貌似"覆盖未生效"。无 transition 的元素（g-tag）同批切换即现终值可作对照组；或 `el.getAnimations().forEach(a=>a.finish())` 后再读。**读 computed 前先 finish 过渡**。
- 原型 chrome（216px 侧栏/brand/g-label+g-tag/nav-item/chrome-foot）原型注释原标"非实现范围，仅评审用"；用户指令"整体布局对齐+左菜单"已使其入范围。s8 总览页应用无路由，未入菜单——用户若要 s8 入口需先建页。
- 嵌套路由收拢 8 子页为 eia-data children 时 URL/名称/meta 全不动即可；守卫用合并 to.matched，meta-less 布局路由不影响 requiresAuth。

**Do-Not-Repeat**
- (2026-10-13) 勿用"computed 值≠变量解析值"断言样式规则未生效——先排除过渡冻结与 UA 默认外观两种假象（本次 .on 暗色 #EEF2FF 实为冻结过渡起点，非规则失效）。
- (2026-10-13) 勿假设"写了 class 样式=渲染生效"：裸 button 先重置 UA 外观再谈自定义样式。

## 词表页样式对齐批（2026-10-13）

**Key Learnings**
- 原型表单件语汇就是 `.inp`（含 `select.inp`，见原型 .frm-row）——工厂页内自绘表单一律用 factory-ui `.inp`，勿引入 AntD 输入类控件（a-input-search/a-select 在原型语境里是突件，bug-437）。
- 原型 `.field-src.db` = main-600/500 靛蓝（.file 灰）：DB 来源标注本就该是靛蓝，勿再「对齐」成灰色。
- 双页样式比对必须按角色取对应元素（file↔file、db↔db），跨角色取样会得出假偏差。
- AntD 组件在本应用已被主题化为靛蓝（a-switch checked rgb(79,70,229)），颜色不突、突的是控件形态（边框/按钮/下拉箭头）——判定 AntD 是否违和看形态而非色相。

**Do-Not-Repeat**
- (2026-10-13) 工厂页新增输入/下拉时勿顺手用 AntD；先查 factory-ui 是否已有配方（.inp/.seg/.stage-chips）。

## FilterSelect 下拉批（2026-10-13）

**User Preferences**
- 原生 `<select>` 被否（「不要使用原始组件」）——工厂页下拉一律用自绘 `FilterSelect.vue`（eia-data/，触发器 .inp 语汇）；它就是应用内非 AntD 下拉的既定件，新下拉需求先复用/扩展它。

**Key Learnings**
- 自绘弹层组件放滚动容器（overflow-y:auto/hidden）内必被剪裁：要么移除容器剪裁（内容固定短时），要么 Teleport to body。fam-list 的 max-height 守卫为挡弹层被删——状态分组恒 5 项。
- 弹层菜单跨实例互斥不用专门逻辑：外点关闭监听天然覆盖（另一实例的 trigger 点击就是外点）。

**Do-Not-Repeat**
- (2026-10-13) bug-436 的 UA button 重置 DNR 当天即复发（FilterSelect .fs-opt 又漏）——**新建任何裸 <button> 的当场 checklist：appearance:none / background:none / border:none 三连，写模板时同步写样式，不留到截图才发现**。