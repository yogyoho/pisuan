# coal-eia-writer 管线化 v2 技能移植设计（pisuan）

- 日期：2026-09-30
- 状态：已评审通过（brainstorming 闭环，五项决策 + 方案一均经用户确认）
- 源技能包：`C:\Users\Lenovo\Downloads\coal-eia-report`（84 文件，2.1M，管线化 v2）
- 目标系统：pisuan（Yuxi fork，deepagents 运行时，LangGraph + FastAPI + Milvus）

## 1. 背景与目标

下载包「煤矿环境影响评价报告编写技能 管线化 v2」与本系统既有 `coal-eia-writer`（编排者 + 3 角色writer）是同一领域的两代设计。v2 的核心增量：步骤 0–7 管线（progress.py 驱动）、门禁体系（门 1 完备性 / 门 2 冻结计算 / 章门 / 终验）、「数字永不经过 LLM」（`{{SLOT:key}}` 槽位注入）、节级派发两层状态模型、红线 P1–P8。

**目标**：把 v2 技能包忠实移植进 pisuan，替换现有 coal-eia-writer，在独立交付路径上端到端跑通 `planning_eia`（矿区总体规划环评）stage，以合成项目验收。

**本次工作的定性：运行时适配，不是重新实现。** 脚本与 references 原样搬运，改动只发生在 SKILL.md 的运行时映射处。

## 2. 决策记录

| # | 决策点 | 结论 |
|---|---|---|
| Q1 | 目标形态 | **A 替换**：v2 原地取代现有 coal-eia-writer（slug 不变），老编排者退役 |
| Q2 | 交付通道 | **A 一期只走独立路径**（单文件 + present_artifacts）；章树绑定/mapping.py 缓行 |
| Q3 | 子代理体系 | **A 新建通用「节撰写者」**；3 个旧角色 writer 摘除不删除，prompt 蒸馏回收 |
| Q4 | stage 范围 | **A 一期只上 planning_eia**；underground stage 数据文件随包移植随时可开 |
| Q5 | 验收数据 | **C 混合**：合成项目进验收 checklist；真实项目试跑为上线前独立验证 |
| 方案 | 移植机制 | **方案一 忠实移植**：脚本/references 一行不改，SKILL.md 按映射表改编 |

## 3. 资产布局与替换范围（§1）

slug **原地替换**：保留 `coal-eia-writer`，目录内容整体替换。编排者 DB agent 的 `context.skills` 绑定零改动；旧版本在 git 历史，回滚 = 目录级 checkout。

```
backend/package/yuxi/agents/skills/buildin/coal-eia-writer/
  SKILL.md          ← 改编自下载包（仅替换 §4 映射表所列项）
  references/       ← 下载包 references/ 原样覆盖（v2 是现有版本超集：
                       新增 stages/×5、depth_targets/×5、sample_entities/×22 矿注册表、
                       formulas.json、standards_index.json、consistency_contracts.json、
                       data_expectations.json；同名文件取 v2 版）
  scripts/          ← 下载包 scripts/ 原样搬运（剔除 __pycache__/、.pytest_cache/）
  outlines/         ← 删除（13 章清单被 stages/planning_eia.json 章节两级清单取代）
```

明确不动：其余 buildin skill、`*.rar` 既有物、report 工具链代码（create_report/save_chapter/assemble_report 等留在代码库，仅退出本 skill 的依赖面）、3 个旧 writer 的 DB 配置。

## 4. 运行时映射表（SKILL.md 改编的唯一改动面）

### 4.1 路径与工具名

| v2 原文 | pisuan 适配 | 依据 |
|---|---|---|
| `/mnt/skills/public/coal-eia-report/` | `/home/gem/skills/coal-eia-writer/` | `VIRTUAL_SKILLS_PATH`（backends/paths.py:22） |
| `/mnt/user-data/workspace/eia-report/` | `/home/gem/user-data/workspace/eia-report/` | `VIRTUAL_PATH_PREFIX`（backends/paths.py:20） |
| `/mnt/user-data/outputs/` | `/home/gem/user-data/outputs/` | 同上 |
| `ask_clarification` | `ask_user_question` | buildin 工具 |
| `present_files` | `present_artifacts` | buildin 工具 |
| `batch_task` / `task()` | `subagent_start`（每节一次）+ `subagent_status` 轮询；一回合内批量发起 | 批量性由 `progress.py mark --sections` 等脚本原语承担 |
| `kf_resolve_template` | `list_report_types`（辅助 `get_templates`）真实调用；found=false 语义同构 | KF 契约三件套纪律保留 |
| `project_list_chapters` / `project_write_chapter` / `mapping.py bind` | **一期缓行**：SKILL.md 保留该节，标注独立路径跳过绑定 | 决策 Q2 |
| `web_search` | 同名（仅限标准规范 discovery 的红线不变） | |
| `knowledge_search` | `query_kb` | 检索纪律保留 |
| `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep`/`execute` | 同名，零适配 | deepagents 同构运行时（composite.py `_AGENT_FS_TOOLS`） |

### 4.2 表单卡片映射（唯一实质语义适配）

pisuan `ask_user_question` 为问题制（1–5 questions/次，answer=`{question_id: value}`），非 v2 假设的字段制（16 项/卡）：

| v2 概念 | pisuan 落地 |
|---|---|
| 字段 `name`（schema 英文键） | `question_id` |
| `label`+`placeholder`（中文名+单位+格式说明） | 合并为 `question` 文本 |
| `enum`→select | `options`（label/value） |
| `number`/长文本 | 自由文本；数值合法性由 `ingest.py` 落盘校验（rc=1 拒绝→译中文重问）——符合 v2「ingest 唯一校验者」哲学 |
| 单卡片 ≤16 项 | **≤5 项/卡**（平台硬上限），一份数据族分多卡，跨回合仍一回合至多一卡 |
| bug-3233/3234 反模式禁令 | 转译：`question`/`options` 纯中文禁塞 JSON；数组族禁要求填 JSON（三步协议照旧） |

答案组装：`{question_id: value}` → 编排者拼 `--values` JSON → `ingest.py forms --family F --values`（只传用户实填的键、每类收完立即落盘）。

### 4.3 上传通道（已核实）

用户对话附件确认后由 `attachment_service._store_attachment` 写入 workdir `/uploads/{file_id}_{file_name}`（沙箱视图 `/home/gem/user-data/uploads/...`）→ `ingest.py file --input …` 直连。平台单附件 ≤5MB（使用约束，写入文档，不改代码）。

### 4.4 改编原则

映射表之外的 SKILL.md 文字（红线 P1–P8、门禁定义、停车契约、修复轮规约、命令速查、能力边界）**逐字保留**；改编只发生在工具名、路径、预算参数处。

## 5. agent 配置（编排者与子代理）

### 5.1 编排者（现有 DB agent，skills 绑定不变）

| 配置项 | 调整为 |
|---|---|
| `context.skills` | `["coal-eia-writer"]`（不变） |
| `context.tools` | `["ask_user_question", "present_artifacts", "list_kbs", "query_kb", "list_report_types", "get_templates", "web_search"]`；report 链路工具全部摘除 |
| `context.subagents` | `["eia-section-writer"]`（替换旧 3 writer） |
| system_prompt | 薄指引（控制器身份 + 「一切动作以 `progress.py next` 输出为准」），管线细节全在 SKILL.md |

### 5.2 新子代理 `eia-section-writer`（DB 新建，is_subagent=true）

- **system_prompt**：通用节撰写者人设 + 3 个旧 writer prompt 的蒸馏产物（蒸馏目标放 DB prompt 而非技能包文件——不破坏 references 原样搬运原则；DB prompt 改动无需重启、新对话即生效）
- **工具**：仅沙箱文件工具；`context.tools` 不配 buildin 工具；无 `ask_user_question`（v2 原生不需要中继协议：写手缺数标 `[待确认]`，控制器汇总统一问）
- **skills**：不配（派发契约已给出全部输入路径）

### 5.3 旧 3 writer 处置

从 `context.subagents` 摘除 → 一次性蒸馏 prompt（每个 ≤10 条可执行写作规范，合入 eia-section-writer system_prompt）→ DB 配置保留不删（回滚保险）。

## 6. 交付与验收

### 6.1 交付（独立路径，v2 原纪律）

`progress.py run-stage finalize --outputs-dir /home/gem/user-data/outputs` → `build_output` 原子组装 `{项目名}-{阶段}-环境影响报告.md` + `delivery_manifest.json` + `project_snapshot.json`；BUILD_READY / MANIFEST_READY 整行 + 退出码粘贴进回复；`present_artifacts` 呈现；续跑恢复走 `snapshot.py show --verify`；交付铁律 4 条逐字保留。

### 6.2 验收 checklist（合成项目，可重复）

| # | 项 | 通过判据 |
|---|---|---|
| V1 | 脚本静态冒烟 | `scripts/tests/` 容器内 pytest 全过；全部脚本 `ast.parse` 通过 |
| V2 | 技能装载 | 新对话 `read_file /home/gem/skills/coal-eia-writer/SKILL.md` 激活；grep 无 `/mnt/`、无 `ask_clarification`/`present_files`/`batch_task`/`kf_resolve_template` 残留 |
| V3 | 开题三件套 | `list_report_types` 真实调用留痕 + 兜底声明 + 按章数据预告可见 + `ingest.py forms` 空白表单落盘 |
| V4 | 门 1 | 缺项 `GATE1_MISSING` 中文清单；补齐后 `GATE1_COMPLETE`（标准号体检/类比来源强制生效） |
| V5 | 门 2 | 自洽数据 `freeze` rc=0；缺参场景 rc=3 → anomaly 卡呈现 |
| V6 | 节级派发 | 覆盖 ≥2 章、每章 ≥1 节的真实 subagent 派发；契约含节切片/槽位词汇表/实体黑名单；节稿落 `state/sections/`；批量 gate PASS → VERIFIED |
| V7 | 全书交付 | finalize → BUILD_READY；outputs/ 单文件 + manifest；`present_artifacts` 交付成功 |
| V8 | 断点续跑 | 门 1 后停车 → 新 run `progress.py next` 恢复现场 |
| V9 | 回归隔离 | 旧 report 工具链不受影响；web 端无异常 |

真实项目试跑 = 上线前独立验证，不进 checklist。

## 7. 实施步骤、风险、回滚

### 7.1 实施步骤（writing-plans 阶段细化为 task）

1. **资产搬运**（步骤 1+2 合并为一个提交）→ 验证：84 文件对账；容器内 `scripts/tests/` pytest
2. **SKILL.md 改编** → 验证：grep 无映射前值残留；改编处之外逐字一致（人工对照）
3. **agent 配置切换** → 验证：DB 读回断言；`docker restart worker-dev` 后新对话技能同步生效（BUILTIN_SKILLS 内容变更必须重启 worker + 新起对话——cerebrum 实证）
4. **合成项目数据构造** → 验证：门 1/门 2 通过
5. **端到端验收** → 验证：V2–V8 全过、报告文件真实产出
6. **文档收尾** → `docs/vibe/2026-09-30-coal-eia-v2-port.md`（需求+checklist）、`changelog.md`、`.wolf` 台账

### 7.2 风险与核对项

| # | 风险 | 对策 |
|---|---|---|
| R1 | 脚本运行环境（沙箱 python 版本/纯标准库假设） | 步骤 1 冒烟覆盖（下载包实证 3.12/3.14 可跑） |
| R2 | 预算参数：recursion_limit 1000 需核对编排者 LangGraph 配置 | 实施时核对；bash 60 为 SKILL.md 自律数字照搬 |
| R3 | 子代理 skill 继承污染（cerebrum 实证） | 契约「禁令」段为主防线，V6 实测行为 |
| R4 | 长 run 步数 vs 700 页管线 | v2 停车契约 + progress.json 磁盘续跑，V8 覆盖 |
| R5 | 中文字符集 | 脚本统一 `-X utf8`，冒烟覆盖 |
| R6 | 附件 ≤5MB | 使用约束写入文档，不改代码 |

### 7.3 回滚

- 技能资产：git 目录级 checkout（步骤 1+2 单提交）
- agent 配置：改前 dump `config_json` 存档进需求文档，改坏即回写
- 3 旧 writer：DB 未动，`subagents` 加回即恢复
- 编排者 system_prompt：旧值全文存档进需求文档

## 8. 明确不做（一期边界）

- 章树绑定 / mapping.py 项目路径交付（Q2）
- project_eia_underground stage 的端到端验收（Q4，数据文件随包）
- 脚本平台化改造 / 进度可视化 UI（方案一否决项）
- 老编排者兼容模式（Q1 替换语义）
