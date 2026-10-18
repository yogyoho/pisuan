# 环评文件库 P2：canonical md 正源归文件库 设计文档

> 日期：2026-10-18 · 状态：已批准（方案 B 终局裁定） · 前置：P1 文件库已上线（pisuan-custom@5a420f5a）

## 1. 背景与目标

环评样例语料（born-digital docx 报告书）目前走「个人目录离线脚本」产线：`prepare_corpus.py → workdir/<rid>/source.md + manifest.json（stage 人工过目）→ bank_compile.py → 技能 references 资产`。P1 文件库已提供进料区（上传/登记/分类/sha1 查重），但存储在本地卷、不产 md、与知识库（KB）和语料管线断链。

本设计把这条产线在线化，形成**单一正源、双消费方**的闭环：

```
                 ┌── 消费方①：知识库 KB（RAG）
                 │    canonical md 以 .md 文档推入 → 原生直读 → 切片/向量/图谱
 上传 docx       │
 ──→ 文件库 ─────┤  源文件一份（MinIO） + canonical md 一份（MinIO，上传即秒级产出）
      (登记/分类)  │
                 └── 消费方②：P2 语料管线（显式触发，管理员动作）
                      切片 → samples_bank 物化 · 词表扫描 → eia_lexicon
                      封面抽取 ← md 前置区（front_extract 的 docx 直读退役）
                      加工台账 → DB
```

- 文件库 = 进料/登记/分类/**canonical md 正源**/P2 数据支撑；
- KB = 分片/向量/图谱/检索问答（只消费 md，不自产）；
- 解析一次（秒级纯解析，无模型调用）、字节一份、md 一份。

## 2. 决策记录

**D1（存储正源）**：源文件正源统一为 **MinIO 一份**。文件库弃 P1 本地 bind-mount 卷，`eia_library_files` 增加 MinIO 定位与 canonical md 定位（`object_key` / `md_object_key` / `md_chars` / `md_status`）。提供一次性迁移（存量本地卷文件 → MinIO，sha1 校验后改写登记）。

**D2（markdown 正源）——方案 A/B 对比与终局裁定**：

| 维度 | 方案 A：md 正源归 KB | 方案 B（选定）：md 正源归文件库 |
|---|---|---|
| md 生产者 | KB 既有解析链（docx→Docling；pdf/图片→OCR 引擎） | 文件库上传后秒级 python-docx 内核（prepare_corpus 内核在线化） |
| md 格式 | KB 全文保真 md | **canonical md**：节号标题层级化/目录页剔除/GFM 表格/封面保留为前置区 |
| P2 规则迁移 | prepare_corpus 行规则按 Docling md 形态**全部重调 + 33 份回归**，工作量不可预估 | **零重调**——canonical md 就是 prepare_corpus 内核产物，下游直接吃 |
| KB 侧改造 | 零 | **零代码改动**——canonical md 以 `.md` 文档推入，unified.py 对 .md 原生直读（unified.py:163） |
| 运行期依赖 | 断粮风险：不推 KB 就没 md | 无——md 随上传即产出，加工不依赖 KB 任务链 |
| 回退成本 | 推送链路铺开后需拆状态耦合 | 直通推送不下发即回现状 |
| 解析算力 | docx 走 Docling 秒级；pdf 走 VL 引擎约 20s/页 | 全部秒级 |
| RAG 适配性 | 现状不变 | 节号化标题利于结构切分；封面前置区对 RAG 无害 |
| pdf 边界 | 天然支持 | v1 仅 docx 产 canonical md；pdf 可登记可用但标「md 不适用」，P2 管线仅消费 docx——诚实边界 |

**裁定过程**：PaddleOCR-VL-1.6（本地）接入后曾短暂倾向 A（「KB 解析质量不可控」短板看似被补齐），经风险复核确认：VL 是视觉模型只吃 PDF/图片，**docx 在 KB 走 Docling、不经过 VL**，A 的核心代价（规则重调）不受 VL 接入影响；而 B 的规则零重调 + KB 零改动 + 无断粮依赖使其改动风险显著更小。**终局选定 B**（2026-10-18 用户裁定）。

**D3（分工边界）**：文件库 = 进料/登记/分类/md 供给（P2 数据支撑）；KB = 分片/向量/图谱/检索问答。加工各自展开，谁也不替谁把门。

**D4（范围）**：本设计一口气到 P2 消费闭环——数据层共享 + canonical md 生产 + KB 推送 + P2 管线在线化（切片物化/词表/元数据/台账）。KB 对象级去重、扫描件 pdf 语料产线（可后补调 `paddleocr_vl_local`）若将来需要，另立需求。

**D5（KB 直通机制）**：KB 侧**零代码改动**——推送时把 canonical md 文本作为 `.md` 文档对象写入 MinIO 并 `add_file_record` 登记之，KB 既有任务链原生直读（unified.py 对 `.md` 纯文本直通）。KB 文档名取 `<原文件名>.md`。不用「docx + 直通引擎」方案（需改 unified.py docx 路由，触碰共享敏感路径）。

**D6（rid 与人工裁决资产）**：`report_id` 沿用 prepare_corpus 的 `make_rid` 形态（`{序号:03d}-{ASCII slug}`，slug 守卫同 bank_compile RID_RE）。bootstrap 导入既有 `manifest.json` 时**原样保留 rid 与 stage/mineral 人工裁决**；新上传文件 rid 由 DB id 生成，stage/mineral 由管理员在文件库补填（加工前置校验）。

## 3. canonical md 契约

**格式**（`prepare_corpus.docx_to_md` 内核在线化，唯一行为差异是封面保留）：

```markdown
{封面/扉页/签署页段落——NFKC 归一后逐段一行，即原「范围裁剪」丢弃区}
<!-- EIA-FRONT-MATTER-END -->
{正文——与现产 workdir/<rid>/source.md 逐字节一致}
```

- 正文产线不变：NFKC 归一 → 表格转 GFM → 先剔目录区段后升节号标题（`## / ### / ####`）→ 首个节号标题起为正文；
- 边界标记 `<!-- EIA-FRONT-MATTER-END -->` 独占一行，位于首个节号标题行之前；HTML 注释对 KB 切片与 GFM 渲染均惰性；
- 零节号标题的 docx：canonical md 产不出（`md_status=failed`，原因「零节号标题」），文件登记照记——与离线产线「跳过」语义一致；
- **等价性承诺**（回归验收器）：标记之后的正文与 `.wolf/corpus-workdir/<rid>/source.md`（33 份金标准）逐字节一致（容忍末尾换行差异）；前置区文本喂给 `extract_front`（纯函数移植）产出的封面字段与技能资产 `front_matter.json` 同 rid 条目一致。

## 4. 组件设计

### 4.1 canonical md 内核（纯函数模块）

新增 `yuxi/services/eia_canonical_md.py`（纯 stdlib + python-docx，无 DB/网络依赖）：

- `docx_bytes_to_canonical_md(data: bytes) -> CanonicalMd`：返回 `{md: str, front_paras: list[str], chars: int}`；移植 `docx_to_md` 全部规则函数（`strip_toc / promote_headings / table_to_gfm / iter_blocks / is_policy_conform_title`），范围裁剪改为「前置区保留 + 标记」；
- `extract_front(front_paras: list[str]) -> dict`：自技能脚本移植（七字段：report_title / eia_org / eia_org_candidates / year / project_no / cover_scale_mt_a / province），`read_front_paras`（docx zip 直读）**不移植**——退役；
- `make_rid(seq, stem)`：自 prepare_corpus 移植（rid 单一事实源）；
- `slice_report(text)` 及其 SEC_RE 体系：自 bank_compile 移植（切片内核），切片起点按标记之后正文计算；
- 技能侧三脚本**原地保留**（离线产线不动），模块 docstring 注明在线版替代关系，避免双头维护误解由后续 changelog 说明。

### 4.2 数据层（storage migration）

`eia_library_files` 新增列（一次 migration）：

| 列 | 语义 |
|---|---|
| `object_key` | MinIO 源文件对象定位（迁移后非空；弃 `stored_path` 本地卷语义） |
| `md_object_key` | canonical md 对象定位；NULL=未产出 |
| `md_status` | `ready / failed / not_applicable(pdf 等) / pending_backfill(存量迁移行初值)` |
| `md_chars` / `md_failed_reason` | 产 md 字符数 / 失败原因 |
| `report_id` | rid（unique，D6） |
| `stage` / `mineral` | 人工裁决元数据（bank_compile manifest 语义，加工前置） |
| `kb_id` / `kb_file_id` / `kb_status` / `pushed_at` / `push_error` | KB 推送镜像（待推送/已推送/解析中/已入库/失败） |
| `processed_at` | 最近一次 P2 加工完成时间 |

新表 `eia_corpus_process_log`（加工台账）：文件 id、sha1、动作（slice/lexicon/front_matter/recompile）、产物摘要（切片数、rid）、操作者、时间。

迁移脚本：存量 `stored_path` 本地卷文件上传 MinIO（sha1 校验）→ 回填 `object_key`，`md_status` 置 `pending_backfill` 供一次性回填任务重产 md。

### 4.3 上传流（文件库服务改造）

上传（sha1 查重拒收语义不变）→ MinIO put 源文件 → docx 则**同步秒级**产 canonical md → MinIO put md → 登记（`md_status=ready`）。md 产出失败不阻断登记（`md_status=failed` + 原因）。pdf 等非 docx：登记照记，`md_status=not_applicable`。

### 4.4 KB 推送（D5 机制）

- 前置：绑定专用 KB。Option `eia_corpus_kb_id` 持久化目标库 id；未配置时推送动作报错并引导（设置页或首次推送时一键创建「环评样例语料」库）。
- 动作：按文件/按文件夹显式推送（管理员）。实现：canonical md 文本写 MinIO（KB 可读路径）→ `KnowledgeManager.add_file_record(kb_id, item, params={文件名: <原文件名>.md})` → KB 既有 parse→index 任务链。
- 状态镜像：`kb_status` 随 KB 文件状态回读（列表列展示），失败行显示原因并可重推。重推语义：已推送且 md 未变 → no-op；md 已重产（sha1 变化）→ **替换**（删旧 KB 文档后重新登记，保持一对一镜像）；从未推送 → 首推。
- 删除语义：文件库删除默认只删自身（含 MinIO 两对象 + KB 推送镜像字段），**不动 KB 资产**；admin 可显式勾选同步删除 KB 文档。

### 4.5 P2 语料加工（显式触发，管理员动作）

- **触发**：按文件/按文件夹「加工」动作。前置校验：`md_status=ready` 且 `stage`（`mineral` 缺省 `coal`）已填，否则拒绝并指明缺项。
- **单文件加工**：① 切片（`slice_report`）→ 切片写技能资产 `samples_bank/<stage>/slices/chN/<rid>__<N>.md` + SL3 指纹池 `samples/<stage>/chN__<rid>.md`（运行栈内技能 references 目录，写作技能运行时零改动）；② 封面抽取（前置区 → `extract_front`）→ 入 DB（eia_meta 语料元数据，现状延续）；③ 词表扫描 → `eia_lexicon`（现状延续）；④ 台账记录。
- **全库重编译**（每轮加工批次末尾自动执行，亦可单独触发）：以 DB manifest（全部已登记 rid/stage/mineral + MinIO md）为输入，移植 bank_compile 主流程重产全局衍生物——`bank_index.json` / `forms_catalog.json` / `section_expectations/<stage>.json` / `depth_targets`（calibrate 子进程照旧）+ `--prune` 清理 rid 已不在 DB manifest 的残留切片。确定性/幂等语义与离线版逐条一致（sort_keys、newline="\n"、拒绝空 bank_index）。
- **技能资产的 git 提交**：运行栈写入落在本机 pisuan-localized 克隆，由维护者经 sync-back 流程回 pisuan 提交——文档化步骤，不做自动化。

### 4.6 bootstrap 导入（41 份存量语料）

管理员端点：接受既有 `manifest.json`（.wolf/corpus-workdir 现产物）上传 → 按 `file_name` 匹配文件库登记 → 回填 `report_id` / `stage` / `mineral`（D6 人工裁决资产原样保留）。配合批量上传 41 份 docx 后，一轮「全库加工」即重建全部 skill 资产，离线产线退役。

### 4.7 前端（文件库 UI）

LibraryPanel 增量：列表列（md 状态、KB 状态、stage）；行内动作（查看 md、推 KB、重推、加工）；工具栏批量动作（按文件夹推 KB/加工、全库重编译入口）；stage/mineral 行内编辑。颜色/组件沿用 base.css 变量与现有 P1 惯例。

## 5. 错误处理与边界

| 场景 | 语义 |
|---|---|
| docx 产 md 失败（零节号标题/解析异常） | 登记照记，`md_status=failed` + 原因；可手工「重产 md」 |
| pdf/pptx 等上传 | `md_status=not_applicable`；推送/加工动作对其禁用（诚实边界） |
| 推 KB 时未配置目标库 | 报错引导配置/创建；不静默选库 |
| KB 解析/索引失败 | `kb_status=failed` 镜像原因；重推幂等（同 md sha1 不重复登记） |
| 加工时 stage 未填 | 拒绝并列出缺项文件清单 |
| 全库重编译零可编译报告 | 拒绝执行（绝不产空 bank_index），报错保留现产物 |
| canonical md 与 KB 文档一致性 | KB 文档内容 = md 对象字节；重产 md 后 KB 侧显示「内容已漂移」提示可重推 |

## 6. 测试策略

- **金标准回归**（内核验收器，开发机容器内跑）：33 份 corpus docx → canonical md → 断言①正文与 `.wolf/corpus-workdir/<rid>/source.md` 逐字节一致；②`extract_front(前置区)` 与技能资产 `front_matter.json` 同 rid 条目一致；③`slice_report` 切片数/章号集与 `bank_index.json` 一致。语料目录只读挂载，金标准文件不入 git（路径参数化，缺环境时跳过并显式声明）。
- **单测**：内核函数移植后行为不变（规则函数逐个用例）；上传流（MinIO 用 fakes/本地 mock）；推送服务（mock KnowledgeManager）；加工服务切片物化与台账；重编译幂等（同输入同字节）；迁移脚本（临时卷 → MinIO fake）。
- **集成**（容器内 pytest，绝不指向运行栈数据；`test_eia_lexicon_service_flow.py` 既有红线不变）：上传→md→推 KB（mock）→加工→重编译 全链路。
- **端到端 QA**：运行栈真实上传 1–2 份 docx → md 查看 → 推 KB（真实 KB）→ 加工 → 浏览器（isolatedContext）验证状态列与 MetaPanel/词表落库。

## 7. 不做什么（YAGNI）

- 不改 KB 解析器/注册表/unified.py（D5 保证）；不动技能三脚本离线行为；不做 pdf 语料 md 产线（另立需求）；不做 KB 对象级去重；不做技能资产 git 自动回写；不做多 KB 目标绑定（单库 Option 起步）。
