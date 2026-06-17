# 开发路线图

路线图可能会经常变更，如果有强烈的建议，可以在 [issue](https://github.com/xerrors/Yuxi/issues) 中提。

日志添加规范（For Agent）:


### 看板

**知识库**
- [ ] office 组件预览，docx/pptx 可以转PDF，然后前端预览 <Badge text="v0.7.1" />
- [ ] 知识库工具新增 query_keywords 工具，专门用于基于关键词命中的排序 <Badge text="v0.7.1" />
- [ ] 调研将当前知识库映射为虚拟文件系统的可行性，先明确文件树映射、权限边界、内容读取与 Agent 工具调用形态，再决定是否实现
- [ ] 增强知识库检索体验：增强 metadata、标签等
- [x] 优化思维导图构建的接口设计，支持增量构建和更新
- [ ] 个人工作区增加可检索能力（但是不做向量化） <Badge text="v0.7.1" />


**智能体**
- [ ] 子智能体缺少异步的机制 <Badge text="v0.7.1" />
- [ ] 子智能体缺少 steer 机制 <Badge text="v0.7.1" />
- [ ] 子智能体的双向通信，缺少 ask_for_main_agent 的机制
- [ ] 子智能体与子智能体的通信机制
- [ ] 如何停掉一个子智能体、查看智能体的进度
- [ ] 优化 Agent `read_file` 工具：至少对齐 DeepAgents 的读取行为
- [ ] RAG 评估支持 Agent 模式 <Badge text="v0.7.1" />
- [ ] 添加 Agent 独立调用接口，方便后续评估使用
- [ ] 任务队列 <Badge text="v0.7.2" />

**并发与分布式**
- [ ] 提高 FastAPI 的并发能力

**其他**
- [ ] 历史对话新增分组（或者叫做项目）
- [ ] 集成 Memory，基于 deepagents 的文件后端实现，需要考虑定位
- [ ] 模型供应商类型继续补齐非 OpenAI 兼容适配，并清理不再支持的 provider type 字样 <Badge text="v0.7.1" />

**仅设想**
- [ ] Yuxi-cli 相关的功能，放在后续版本中实现（不是类似于编程助手，而是管理平台的工，等各个 router 接口优化之后）
- [ ] Yuxi-cli 支持 `yuxi upload <DIR_NAME>`，将本地文件夹上传到系统中


### Bugs
- [ ] 目前的知识库的图片存在公开访问风险
- [ ] 点开对话的时候要能够自动定位到尾部，而不是最开始。
- [ ] HTML 渲染侧边模式底部有部分无法渲染，全屏情况下下面有白边
- [ ] 补充 Summary 长上下文触发后的可观测性与回归验证
- 目前的知识库的图片存在公开访问风险

### BREAKING CHANGE（不兼容变更，0.7 版本再实现）
- 将自定义provider 的实现逻辑，从文件移动到数据库中，并将相关处理代码，移出 config 文件，放到 provider 模块中
- 已补充方案文档：`docs/vibe/2026-04-18-custom-provider-db-refactor-plan.md`，明确采用“provider 一行、models 放 JSON、移除 provider 默认模型”的落地方案
- 优化知识库的 API 接口设计，使用 /{db_id}/xxx 的形式，整合 mindmap / eval 接口
- 移除 v1 版本的 provider 统一接口，改为 v2 版本的 provider 模块接口



## 版本记录

### 0.6.2 开发记录

<!-- 0.6.2 的内容请放在这里 -->
- 下放扩展管理权限：普通管理员现在可进入扩展管理并完整管理 Tools、MCP、SubAgent、Skills；同步放开 Skill 管理接口权限并补充权限测试。
- 调整 Agent 知识库默认选择：未显式配置知识库时默认启用当前用户可访问的全部知识库，显式保存空列表仍表示不启用知识库。
- 领域知识工厂 Pipeline P2 增强：新增公式提取 （提取公式结构+变量映射+用途推断），GraphBuilder 新增 FormulaTemplate 节点和 USES_VARIABLE 关系；新增图片多模态提取 （支持 vision 模型降级为文本推断），GraphBuilder 新增 ProcessFlow/ProcessStep 节点和 STEP 关系；新增分章节提取 （按 domain×report_type×chapter 预定义局部 Schema，每章节 10-20 变量分批提取）；新增骨架跨文档聚合（DomainOutline/ChapterTemplate/ParagraphRole 节点 + rigidity/frequency 聚合算法 + Document-CONTRIBUTES_TO 关系）；新增逻辑关系提取（因果链 CausalChain、条件分支 ConditionRule、数据引用链 DataFlow）写入图谱；slot type 后端兜底校验（默认 parameter、enum 必须有 vocabulary）。
- 领域知识工厂 Pipeline 重设计 Phase 1：新增 `report_type_code` 维度到 `domain_factory_tasks`/`domain_factory_learned_templates`/`domain_factory_prompt_configs` 三表；重构 `report_types` 表为 (code, domain_code) 复合唯一键并初始化煤炭/化工/交通三类报告类型数据；上传接口和前端上传弹窗支持报告类型二级联动选择（从 contexts API 动态加载）；`DomainTaskDTO` 新增 `report_type_code` 字段。
- 领域知识工厂 Pipeline 重设计 Phase 2：新增 CLASSIFY 阶段将段落分为 8 类（heading/table/figure/formula/list/legal_reference/parameter/narrative）；GENERALIZE 阶段仅对 parameter 型段落调用 LLM 泛化，跳过叙述/标题/标准引用等类型；优化泛化 Prompt 增加 slot ≤5 约束、禁止无语义编号命名、叙述占位符双模式；去除根级字段冗余（para.original/generalized/slots），前端统一从 para.template 读取；parent_title 回填用 section_path→title 映射补全。
- 领域知识工厂 Pipeline 重设计 Phase 3：ETL 工作台新增段落分类标签（8 类彩色标签）和 AI 置信度显示；实现半自动审核模式——置信度计算、一键确认高置信度、仅显示待审核过滤、审核进度条；结构化元数据面板改为模板摘要视图（泛化模板+插槽芯片+元数据），同时保留 JSON 编辑器；Tab 1 和 Tab 2 原文查看器统一支持分类标签。
- 领域知识工厂 Pipeline 重设计 Phase 4：新增法律引用提取阶段（LEGAL_EXTRACT），从 legal_reference 类型段落中用正则提取结构化法律/法规/标准引用（9 层分类：法律/行政法规/地方性法规/部门规章/地方规章/技术规范/相关规划/项目资料）；自动推断制定机关和适用范围（national/regional）；前端在元数据面板展示法律引用列表。
- 领域知识工厂 Pipeline 重设计 Phase 5：GraphBuilder 新增 LegalReference 节点和 CITES 关系；ParagraphTemplate 节点增加 classify_type 属性；Document 节点增加 domain_code/report_type_code 属性实现领域隔离；法律引用按 scope 分层写入图谱并自动累计引用频率。
- 领域知识工厂 Pipeline 补完：废弃旧全局 EXTRACT 阶段（149 变量全 None 的 LLM 调用），改为从段落级 slot 值构建 base_info 实现 slot-variable 统一；废弃全局模板 LLM 生成，前端从段落 template 聚合；新增表格 Schema 提取（列角色判定 key/structural/data/reference/derived + 4 种表格类型 key_value/monitoring/compliance/standard_limit），写入 `para.template.table_schema` 并在 GraphBuilder 中创建 TableSchema 节点；新增模板质量评估函数 `evaluate_template_quality` 自动评分写入 `quality_score`；新增正文标准引用 LLM 提取（场景B），对含标准编号的非 legal_reference 段落用 LLM 提取结构化引用；新增图谱查询 API（`/graph/templates` 按 domain×report_type 查骨架/模板/表格，`/graph/legal-references` 按 scope 过滤法律引用）。
- 领域知识工厂 Pipeline 重设计 Phase 6：全量移除前端硬编码领域/报告类型数据，所有领域和报告类型均从 PostgreSQL 动态加载；修复 `_build_entity_proposal_prompt` 中 `await` 在非 async 函数中的语法错误；修复文档类型列显示英文编码而非中文名称的问题。
- 优化评估基准自动生成：仅支持 commonrag/Milvus 知识库，默认参考 chunks 数量改为 1；多 chunk 场景复用知识库向量检索选择相似 chunks，不再对全量 chunks 重新计算 embedding，并移除前端 Embedding 模型选择。
- 修复知识库文档入库状态回退：当已解析文件缺失 `markdown_file` 解析产物时，索引流程会将文件状态恢复为未解析，便于重新解析而不是停留在索引失败。
- 优化 Agent 输入框文件 mention：用户级 workspace 文件候选改为从独立 workspace API 递归加载，不再依赖 active thread；插入时仍转换为 `/home/gem/user-data/workspace/` 沙盒虚拟路径，并修复附件上传后未立即刷新 mention 候选的问题。
- 调整知识库思维导图后端结构：将思维导图路由文件重命名为知识库语义更明确的 router，并把文件列表整理、提示词构建、AI JSON 解析等纯逻辑下沉到知识库 utils。
- 收敛知识库评估后端结构：将评估指标、单题评估、答案生成提示词和自动基准生成算法下沉到 `knowledge/eval`，`EvaluationService` 保留任务、文件和持久化编排职责。
- 新增个人工作区预览与管理：提供独立于对话 thread 的用户级 workspace API，并增加“工作区”页面，用于浏览个人 workspace 文件、预览 Markdown/文本/代码/图片/PDF；支持新建文件夹、上传文件、下载文件、删除文件/文件夹和多选删除；工作区预览支持 Markdown/TXT 在右侧预览框内切换编辑并保存，其他格式和非工作区预览默认只读；知识库与团队空间入口先展示到占位层级；默认创建 `agents/AGENTS.md`，并在 Agent 执行时将其内容追加到系统提示词。
- 加固 JWT 鉴权安全：移除历史默认密钥回退，初始化脚本支持生成并持久化 `JWT_SECRET_KEY` 与 `YUXI_INSTANCE_ID`，签发和验证令牌时校验 `iss/aud`，并在鉴权阶段拒绝已删除或登录锁定用户继续使用旧令牌访问系统。
- 扩展管理界面交互逻辑重构：将 MCP / Subagents / Skills 三个标签页从「左侧边栏 + 右侧详情面板」布局重构为「卡片式网格布局 + 路由跳转二级页面」布局，工具标签页改为卡片网格布局 + 弹窗详情（保持弹窗内容不变）。新增共享组件 `ExtensionCard`、`ExtensionCardGrid`、`ExtensionToolbar`、`ExtensionDetailLayout`，详情页（`McpDetailView`、`SubagentDetailView`、`SkillDetailView`）使用居中宽度限制，路由规划为 `/extensions/mcp/:name`、`/extensions/subagent/:name`、`/extensions/skill/:slug`。
- 统一卡片样式：`ExtensionCard` 新增 `tags` prop 支持传入 `[{label, color}]` 数组，内部使用 `<a-tag bordered=false size=small>` 渲染，与知识库卡片标签风格统一；知识库列表页 `DataBaseView` 改用 `ExtensionCard` + `ExtensionCardGrid` 替代原有自定义卡片，移除冗余 card 样式。
- 调整应用主导航：`AppLayout` 从默认窄栏升级为默认展开的侧边栏，保留折叠态图标导航；侧边栏样式收敛为 14px 文本 + 18px 图标的标准紧凑密度，并统一导航项、任务中心、GitHub、用户信息的图标与文字对齐。折叠态改为仅通过显式按钮展开，避免空白区域误触发。
- 合并智能体对话导航：移除 `AgentChatComponent` 内部聊天侧边栏，将新建对话入口和对话历史移动到 `AppLayout` 主侧边栏，并通过共享线程 store 统一管理历史列表、当前线程、重命名、删除、置顶和分页加载。
- 新增独立模型配置模块：增加 `model_providers` 表、独立管理接口和”模型配置”页面，支持 provider 基础信息、可配置模型列表端点、远端候选模型、`enabled_models` 的早期配置验证；启动时会补齐内置 provider 模板，`provider_type` 暂统一默认为 `openai`，该模块暂不接入现有运行时模型选择逻辑。远端模型加载默认使用 `/models` 获取 chat/通用模型，provider 声明 `embedding` 能力时使用 `/embeddings/models` 获取 embedding 候选，rerank 模型列表端点按供应商文档显式配置后加载；修复路由请求模型未接收 `embedding_base_url`/`rerank_base_url` 导致前端已填写仍被后端校验拦截的问题。补充手动添加模型能力：`enabled_models[i]` 新增可选 `source: “manual”|”remote”` 字段（默认 `remote`），管理员可通过”+ 手动添加”入口录入远端清单未覆盖的模型（典型：自部署 embedding/rerank），手动模型在前端跳过”远端不存在”的 stale 警告并显示「手动」标签；type 选项受 `provider.capabilities` 约束，后端在 `_normalize_payload` 与 `update_provider_config` 双层一致性校验中拦截越权写入。
- 统一前端 Markdown 预览渲染：新增共享 `MarkdownPreview` 组件与 `markdown_preview` 渲染工具，替换 Agent 消息、文件预览、知识库 chunk、任务工具结果、聊天导出等场景中的旧 `md-editor-v3/marked` 预览；支持 KaTeX、任务列表、frontmatter 卡片、Shiki 代码高亮、DOMPurify 清洗和浅层渲染缓存，并抽取 HTML 转义与代码语言归一化工具。Skill 详情页复用 `AgentFilePreview`，统一文件预览、编辑、保存和全屏交互。
- 优化远程 Skill 批量安装：`remote_skill_install_service.py` 新增 `install_remote_skills_batch()`，利用 `npx skills add --skill A --skill B --skill C` 原生多 skill 支持，将安装 N 个 skill 的仓库克隆次数从 2N 降至 1；配套新增路由 `POST /remote/install-batch`、前端 `installRemoteSkillsBatch()` API 方法和批处理 UI 逻辑
- 升级领域知识工厂入库策略：新增 `StructuredDocument` 中间结构保留章节/模板/插槽语义元数据，新增 `clean_title()` 去噪与 `build_embedding_text()` 上下文重组（行业+报告类型+章节路径+内容），在 `LightRagKB` 中实现 `_ingest_structured_document()` 结构化入库方法，入库流水线优先使用结构化入库、不支持时回退到 Markdown 方案。
- 实现领域知识工厂知识图谱构建：新增 `GraphBuilder` 服务将结构化数据写入 Neo4j，构建”写作模具库”图谱（Document/Section/ParagraphTemplate/Slot 节点 + HAS_SECTION/HAS_CHILD/NEXT_SECTION/COMPOSED_OF/HAS_SLOT 关系），入库和再入库流水线中自动触发图谱构建，失败不阻断主流程。
- 领域知识工厂实体元数据系统：新增 `entity_meta_service.py`（EntityMetaLoader/EntityMetaAdapter/EntityMetaMatcher/SlotEntityMapper 四个类），移植 coal_eia_entity_types.json（16 个实体定义），集成到 ETL 流水线——提取阶段用实体增强 Schema 变量，泛化阶段用 SlotEntityMapper 为插槽注入 entity_ref，GraphBuilder Slot 节点写入 entity_ref 属性。
- 领域知识工厂模板匹配引擎：新增 `template_library.py`（模板库加载/查询）、`template_matcher.py`（正则匹配+语义锚点+置信度计算）、`template_generator.py`（LLM 参考已有模板生成），移植 know 系统 30 个煤炭行业模板 JSON，ETL 解析阶段自动对标题段落进行模板匹配并附加 template_id / semantic_routing。
- 领域知识工厂 Pipeline 重设计：引入 domain × report_type 二维模板空间，新增段落分类器（CLASSIFY 阶段：标题/标准引用/参数/表格/叙述 五类），泛化只处理参数型段落并限制 slot ≤5，新增编制依据结构化提取和正文标准引用提取，图谱新增 DomainOutline/LegalReference/TableSchema 节点支持骨架聚合和法律引用按 scope 过滤。详细方案见 [pipeline-redesign](../vibe/2026-05-15-pipeline-redesign.md)。

---

历史版本发布记录已迁移到 [版本变更记录](./changelog.md)。

维护说明：
- roadmap 仅保留未来规划（看板/Bugs/里程碑方向）。
- 具体版本发布内容统一维护在 changelog。
