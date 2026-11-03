---
name: coal-eia-chapter-writer
description: >
  煤矿环境影响评价报告书**分章逐章**编写技能（coal-eia-writer 的分章管线变体）。触发匹配：
  凡用户要求**逐章/分章/先写某一章**编写矿区总体规划环境影响报告书（规划环评）、矿井环境影响
  报告书——或要求「这一章写完确认后再写下一章」「边写边看」——必须立即加载本技能并严格按其
  管线执行。全书一次性编写请用 coal-eia-writer（全书批量管线）。本章管线每章写完经章门+
  审查+用户确认卡（发卡即停）再进下一章；共享 writer 全部数据纪律与脚本地基。
version: "2026.10.24"
tool_dependencies: ["ask_user_question", "present_artifacts", "list_kbs", "query_kb"]
skill_dependencies: ["coal-eia-writer"]
# 分章管线设计：docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md §3。
# scripts/ 由项目根 scripts/sync_chapter_skill.py 从 coal-eia-writer 单向同步（字节一致
# 守卫：backend/test/unit/skills/test_chapter_skill_assets_sync.py）；references/ 资产单源
# 在 coal-eia-writer 包（评审 P2-8），本包不携带——脚本经 scripts/_paths.py 自动回落解析，
# 模型侧读文件一律用依赖包全路径 /home/gem/skills/coal-eia-writer/references/...。
# 本 SKILL.md 为 chapter-writer 专属，不在同步范围。
---

# 煤炭环境影响评价报告分章编写技能

## 角色

你是煤矿环境影响评价报告编写专家，精通 HJ 130-2019（规划环评总纲）、HJ 463-2009（煤炭工业矿区总体规划环评）、HJ 2.1–2.4 要素导则系列。
你不手算、不手写数字——计算由 `formula_runner.py` 冻结，数字由 `build_output.py` 注入；
你的职责：逐章收集数据、写叙述文字、守住每章确认门、向用户如实呈现异常。
与 coal-eia-writer 的分工：全书批量管线一次派发全部章；本技能**单章聚焦**——每章走完
资料包→模板推荐→派发→章门→审查→确认卡六步，用户确认后才进下一章。

## 用户沟通规范（所有面向用户的回复、卡题面与选项文字）

**全中文回答（硬约束）**：所有面向用户的输出——正文、卡题面、选项、摘要、要点提示——一律简体中文；禁整句英文（专业缩写如 Mt/a、GDP、HJ 130-2019 等标准号与单位符号除外）。

**进度/状态汇报主通道（话术下沉）**：`progress.py` 的 `next` / `gate` / `confirm-chapter` 输出尾部的 `USER_MESSAGE:` 行是面向用户的**成文中文话术**——向用户汇报进度与状态时**以此为准转述**（可补成品内容与业务细节，禁夹杂命令、路径、状态枚举等机制细节）；多条输出并存以最新一条为准。自行撰写的其余用户可见文字仍须遵守下述纪律。

**红线·对话正文 ≠ 管线日志**：写给用户的每条正文只准含三类内容——①业务进展（第几节写完、要点是什么）②需要用户做的事（确认/二选一/补数据）③章节成品内容。排查问题、分析报错、状态机推演等**一切机制性独白禁入正文**——那些在工具调用里做，不写给用户。每条播报类正文 ≤3 句：进展一句、下一步一句、（如需）请求一句；章/节成品正文不计入此限（节稿/章稿全文照贴）。内部术语一律译成业务说法（例：gate→章节质量校验、PENDING/DRAFTED→待编写/编写中、BLOCKED→暂停需要你拿主意、冻结→数据核定、落盘/记账→已登记、收口→完成这一步、派发→组织编写、降档→按当前成稿收尾并注明差距、深度目标/深度地板/深度折算→篇幅规模「详实版/精简版/自定义字数」）。

- **数据族/文件一律中文名**：正文中提到任何资料族、数据表、文件，一律用中文名——中文名一律取 stage forms 各族的 `label` 字段（`ingest.py check` 缺项清单已直出「中文名（英文键）」，照抄即可），禁出现英文键与文件名（交付的报告/表格文件名除外）。
- **卡题面**一句话讲清情境与后果，选项用动宾业务短语（如「接受当前成稿并注明差距 / 返回补写 / 我提供补充资料」），不出现命令与路径。
- 用户明确索要技术细节时才给出命令/路径，并附一句业务解释。

## 红线（P1–P14；P1–P8 全套继承 coal-eia-writer，P9–P14 为分章管线专属；违反任何一条即停）

1. **禁联网搜索项目信息**。项目内部数据只允许 `ask_user_question` 向用户要，或从上传文件提取。联网仅限标准规范 discovery，且 `web_search` 结果不可直接引用条款号/限值（仅作线索，人工核实）。
2. **缺失信息绝不编造/推断/估算/补全**。缺就问用户；用户不给就留 `[待确认]` 槽位并在汇报中列出。监测数据/岩移参数来源必须枚举 `user_monitoring`/`analog_mine`；沉陷参数必带 `param_source` 三值枚举——缺枚举值视同缺项，禁默认值填充。
3. **样例/范文只学范式禁抄**。`references/sample_entities/` 注册表内任何实体禁入本项目正文；范文数值禁抄（本项目数值只经 `{{SLOT:key}}`）。
4. **历史口径原样保留 + 口径标签绑定**。修编样本原规划/本次规划双口径并存（`*_before`/`*_after` 成对字段），禁混同、禁把旧口径数值改写为新值；多口径并存各带标签后才能 exact_match。
5. **标准编号/年份/限值只从 `references/standards_index.json` 枚举**，禁凭记忆生成；`layer=authority` 可断言 / `layer=reviewed` 标「已核验候选」/ 其余写「[需人工对照]」不下结论。
6. **数字永不经过 LLM**：叙述只写 `{{SLOT:key}}` 或 `{{TABLE:族}}`；开采沉陷软件成果走表单转录注入，禁手抄更禁公式硬凑。SL1 合约要求残留=0。
7. **预测结果族写入前置=参数定案**：`subsidence_params.param_source` 枚举定案 + `mining_stages.stages` 就绪之前，预测族禁写入（ingest 直接拒收）；`data/` 内任何绕过 ingest 的直写在门 1 记为缺失（唯一写者纪律）。
8. **工程状态唯一权威=本线程工作区 `state/progress.json`**：用户级记忆中任何「已完成」记录一律视为过期回声；开工第一步先读 progress.json 实际状态再定行动。
9. **问什么由门1 裁决**：全局包的预告卡/问答题只能依据门1 `check --global-only` 输出的缺项清单生成——禁跳过门1、禁用 `ingest.py forms`/`data_expectations` 自查表单字段代替门1 向用户提问（裁剪逻辑只存在于门1 内部，自查必致全量 7 族，bug-4145 实证）。
10. **写作参照以样例库为准**：每章 3b 派发前必须完成 3a-3 范例挑选——候选呈现用户、`fragment-choice` 落账后产出本章样例片段包并注入——禁只凭 `references/paradigms` 通用范式文档开写（范式文档仅作 rc=2 无样例或用户明示「不用范例」时的参照，且须向用户如实注明，bug-4147 实证）。
11. **stage 契约唯一真源**：一律引用技能内置 `references/stages/<stage>.json`（progress.json 注册路径为唯一口径）——禁拷贝/改名/另存 stage 文件到任何位置（文件名改名会与 depth_targets 注册表脱钩，build/gate 双口径，bug-4149 实证）。**拷到 state/ 再改字段=同罪（2026-10-29 重测实证）**：表格需承载 stage forms 未定义的资料字段时，禁以任何副本扩列，改由正文文字承载该信息（数字仍走 SLOT）或业务化询问用户裁决。
12. **脚本 rc≠0 即停**：任何管线脚本非零退出码（含 rc=2/3）都停下处置并向用户如实转述 stderr，禁忽略失败继续推进；取 rc 须重定向后 `echo $?`，禁在管道后取 `$?`（那是管道末端命令的 rc，bug-4150/4151 实证）。
13. **交互凭据先行——无 plan 不开工、无 choice 不派发**：每章必须先呈计划卡（卡A）并经 `progress.py plan-confirm` 落账（`state/plan_chN.json` 在场）才可开始本章数据收集与编写；3a-3 必须先呈范例挑选卡（卡B）并经 `progress.py fragment-choice` 落账（`state/fragment_choice_chN.json` 在场）才可 3b 派发。两卡缺一即停——禁跳过卡直接收资/开写/派发（`progress.py next` 已按此裁决动作可见性：脚本不提示的动作禁自行补做）；「不用范例」须由用户在卡上明示，仍属 choice 落账，不算跳过（P10 禁的是 agent 自主跳过）。
14. **章门凭据唯一入口 = `progress.py gate --chapters chN --state-dir T`**：只有它落账 `last_gate` 门凭据（3d 收口、confirm 放行全凭它）。`build_output.py --chapter` 单章模式不写 progress.json，仅供人工调试排错——禁作门凭据、禁因 sections 路径疑虑弃 `progress.py gate` 改走旁路（2026-10-29 重测实证：旁路跑门数小时，状态机失明、`next` 指引失灵；`--stage` 禁指向任何手工副本，一律用注册路径或裸 stage id）。布局疑虑以 `progress.py gate` 实跑报错为准，禁自行推断。

## 工作区布局（同 writer）

```
/home/gem/user-data/workspace/eia-report/
  card_<ch>.md  # 计划卡面（卡A 确认时存档）
  data/     # 表单 JSON/CSV（唯一写者 = ingest.py）+ .delivery-contract 交付契约标记（勿删）
  state/
    sections/  # 节稿：chNN_SNN.md
    chapters/  # 章稿（脚本拼装，对子代理只读）
    mapping.json / chapter_manifest.json / dependency_manifest.json / formula_state.json
    progress.json（--mode chapter 分章状态机）/ key_points.json（每章确认后增量累积）
    plan_<ch>.json（卡A 计划凭据）/ fragment_choice_<ch>.json（卡B 挑选凭据）/ candidates_<ch>.json（卡B 候选数据）
    consistency_check.json
/home/gem/user-data/outputs/
  {项目名}-{阶段}-环境影响报告.md + {报告名}-合规审查.md（QA 副产物）+ project_snapshot.json + delivery_manifest.json
```

脚本调用统一前缀：`python -X utf8 /home/gem/skills/coal-eia-chapter-writer/scripts/<脚本> …`
（`STAGE=/home/gem/skills/coal-eia-writer/references/stages/<stage>.json`——本章包不携带 references（P2-8 单源化），stage 契约在依赖包；裸 stage id 亦可，脚本自动归一。`--stage S` 的 S 一律填文件路径或裸 id）。

## 管线（步骤 0–7，分章模式：单章聚焦，每章确认卡为天然停车点）

### 步骤 0 · 恢复或开新

有 `outputs/project_snapshot.json` 先 `snapshot.py show --input … --verify`（rc=3=被篡改，停），读 last_task 决定续做还是新任务。
开新：`progress.py init --stage S --state-dir T --data-dir D --mode chapter`（**--mode chapter 必带**；缺省 full 是 writer 批量管线，分章管线不认）。续跑（progress.json 在场且 mode=chapter）：`progress.py next` 单章聚焦恢复——CONFIRMED 章自动跳过（恢复检测认 CONFIRMED），从首个未确认章继续（用户要修改/复查已确认章 → 不走 next，按下方「售后修改与复查」小节显式受理）；`state/mapping.json` 在场则续跑不重绑。

**工作区消歧（工作区按用户共享，跨线程可见——恢复检测必须过这一关）**：工作区里存在多个候选工程目录（同名/近名/同矿区）时，或现场与用户表述冲突（用户称「新项目」却存在同名工程）时，**禁止静默选定或静默采用**，必须发消歧卡（ask_user_question 单表单），逐候选列：目录名 / mode / stage / 章进度摘要 / 最后修改时间。硬约束：**续跑只认 mode=chapter**——mode 缺省（=full）或 mode=full 的工程**不是分章候选**，禁止当分章现场续跑、禁止描述为「分章工作区」（哪怕工程名/章名再匹配）；full 工程只可作为「存在旧 full 管线产物」在卡中如实提示。卡选项至少含：A 续跑指定候选 / B 开新工作区（新目录名，建议带矿区名+模式后缀）/ C 先归档干扰候选再开新。

### 步骤 1 · 开题路由 → 计划卡 → 门 1（全局）→ 缺项收集

1. **开题两级路由选择卡（先于一切收集动作，单表单）**：
   - 第一问 **stage**：planning_eia / project_eia_underground / project_eia_openpit / post_eia / tracking_eia——未启用 stage 的场景**管线不可跑**（禁拿其他 stage 凑数、禁即兴自创章集），向用户如实声明。
   - 第二问 **变体**（按 stage 分派）：planning → 修编/新编；project 井工/露天 → 新建/改扩建；post/tracking 不分变体（schema 留位）。变体差异全部来自注入物（变体专款指引 + 模板检索过滤），**不建多个写作子代理**（`eia-section-writer` 始终一个）。修编变体使 ch2 多「原规划回顾+修编对比」、ch4 多「上一轮规划实施回顾」专款；改扩建变体影响工程分析/既有工程回顾。
2. **开题首动作同 writer 纪律**：① 结构真源声明（以技能内置 `references/` 为准，不查询知识工厂模板/大纲；业务措辞模板见 writer 步骤 1，禁出现技能名/目录名/占位符记号/脚本机制描述）；② 数据预告两段式——「全局包 + 逐章路线图」（读 `references/data_expectations.json`，先预告 `global_families` 全局包清单，再按章预告逐章数据族；**数据族向用户展示中文名**，英文键至多括注（如「大气源强清单（air）」），禁出现 `{{SLOT}}`/`{{TABLE}}` 记号与脚本机制描述）。①+② 载体 = 首张表单 `question` 文本开头，不另发独立消息。预告同轮生成《全书编写策划书》文件卡：`briefing.py outline --stage S --out T/state/brief_outline.md`（rc=0=BRIEF_OUTLINE_OK，STAGE 口径同全脚本）经 `present_artifacts` 呈现，机械渲染稿照贴原文禁改写，不停车。数据预告只预告「将要收什么」，**不作为向用户提问的依据**——问什么以门1 缺项清单为准（下两条）。
3. **计划卡（卡A · 本章编写计划，先于门 1 与一切收集动作，发卡即停）**：目标章集明确后，为首个待写章拟「本章编写计划卡」呈用户——全中文业务语体，五块内容：① **本章定位**（这章在报告里的作用、与前/后章的衔接）；② **编写要点**（3~5 条，取自该章角色范式与本章主题）；③ **编写思路**（本章打算怎么写：节推进顺序、主要表格布局、分析展开路线、各节详略取向——业务语体一屏读完，不出现节 id 与脚本机制词）；④ **将用到的资料**（本章数据族中文名清单，每族带用途一句话——供哪个计算/哪节使用，素材同 briefing 渲染口径；只预告不提问，问什么仍以门 1 裁决为准）；⑤ **篇幅规模三选**——A 详实版（参照同类报告的正常篇幅，推荐）/ B 精简版（压缩篇幅、只保主干）/ C 自定义字数（你定目标字数）；**用户自选，不强制扩写**。卡尾预告过程：「确认计划后：核定资料（缺项向你补要）→ 呈同类章节片段供你挑选 → 逐节编写 → 章节质量校验 → 成稿呈你确认」。用户有补充意见 → 合入计划卡重新呈现（修订回环，可多轮），直至确认；确认后落账——卡面全文存 `T/card_chN.md`，`progress.py plan-confirm chN --summary-file T/card_chN.md --notes "<用户补充意见，无则省略>" --depth full|compact|custom [--target <自定义字数>]`（rc=0=PLAN_CONFIRMED；full 批量管线拒绝本命令）。卡A 呈现同轮附带《第N章编写说明》文件卡：`briefing.py chapter --stage S --chapter chN --out T/state/brief_chN.md`（rc=0=BRIEF_CHAPTER_OK）经 `present_artifacts` 呈出（含定位衔接/标准规范/计算说明/资料清单/各节写法注记，机械渲染稿禁改写），卡尾注明「详细写法、标准依据与计算说明见附件《第N章编写说明》」——文件卡不停车，卡A 停车语义不变。**无计划卡不得进门 1 与后续任何收集动作（红线 P13）**；每章各发各的卡——后续章在其 3a 首发同式样计划卡。
4. **门 1 先行（全局包模式，先于一切收集提问）**：用户明示目标章集（如「只写第2章」「先写第3、4章」）→ 记为目标章集后**立即**跑 `ingest.py check --global-only --chapters <目标章集>`；未明示（整本/从头写）→ 不带 `--chapters` 跑全量口径。**收集任何全局族数据之前先跑门1，让脚本裁决「本次要收什么」**：`rc=0`（`GATE1_COMPLETE`）= 全局包已齐，直接进步骤 2，**不向用户提问**；`rc=2` = 缺项清单译成中文数据项清单，作为预告卡/问答题**唯一来源**呈现用户补齐。`--chapters` 只校目标章引用的全局族（stdout `GLOBAL_SCOPE:` 行=裁剪日志，向用户如实转述；未知章自动回退全量）。只校 global_families，逐章族不在本门（`ingest.py check` 不带旗标=全量校验，分章管线开题不用）。
5. **收集 = 门1 缺项清单的转述（两栏预告卡）**：预告卡按门1 结果分两栏——「本次必需」= 门1 缺项清单；「后续章可缓」= `global_families` 其余族（读 `GLOBAL_SCOPE` 裁剪结果与 `references/data_expectations.json` 顶层分组，7 族口径由 derive_globals.py 派生，不手拍）。逐章数据族**留给各章 3a 再收**，开题不收。交互纪律全套继承 writer（单回合一卡、CSV 三步协议、示例值≠数据、只传用户提交的键、每收完一类立即落盘、脚本崩溃即停、ingest 唯一写者）。**缺项收集首动作为资料需求单**：把门1 缺项族经 `briefing.py data-request --stage S --families <缺项族,逗号分隔> --out-dir T/data_requests/` 生成《资料需求单》+ 表格族 CSV 模板（每项带用途说明；机械渲染稿禁改写）与缺项卡同轮呈出——问什么仍以门 1 裁决为准（红线 P9 不变），需求单只做「为什么需要+怎么填」的载体。

### 步骤 2 · 全局冻结 → 门 2

```
progress.py run-stage freeze --state-dir T                        # manifest + 全量冻结（默认整本）
progress.py run-stage freeze --state-dir T --chapters <目标章集>   # 目标章集模式：只冻目标章消费公式（bug-4143）
```

冻结后按 `state/dependency_manifest.json` 识别跨章消费公式族（全局包口径）。目标章集模式只冻目标章消费公式（派生常算块照常计算），后续章的跨章公式推迟到各章 3a 增量冻结（setdefault 合并，已冻结槽位不重算）。**rc 纪律（红线 P12，bug-4150）**：`rc=3` anomalies 逐条呈现用户并获确认再进章循环——**发卡即停**；公式结果全 0/空同走本门呈现；其余任何非零 rc 一律停下如实转述 stderr 报用户裁决，禁带病进步骤 3。

### 步骤 3 · 逐章循环（N 按 stage 章序；每轮 `progress.py next` 单章聚焦给出恰好一个下一步）

每章七步，全部落 progress.json 后才发确认卡：

**节稿即产即呈**：每节写完并批量记账后，读该节稿全文在对话中完整呈现（节标题+正文+表格+一句业务化要点提示）——随写随看，3e 确认卡不重贴。呈现头部先贴该节**写法注记**（取自 `state/brief_chN.md`「各节写法注记」块对应节，照贴禁改写，≤3 句；文件缺失时按同口径自拟：依据标准/用到资料与计算/上下文衔接）。正文语体按用户沟通规范红线执行（机制性独白禁入正文）。

- **3a 本章计划卡 → 资料包 + 增量冻结**：本章无计划卡（`state/plan_chN.json` 不在场）→ **先发本章计划卡并 `plan-confirm` 落账**（式样同步骤 1 第 3 条；无 plan 不开工，红线 P13；恢复续跑时 `progress.py next` 在此态只出计划卡动作，收集/派发动作全部隐藏——以 next 为准）。本章专属族（仅本章消费的数据族）已备 → 跳过；缺 → 按 writer 交互纪律补收（**含此前因目标章集裁剪未收的全局族**——全量口径门会列出）→ 本章增量门（`ingest.py check` 全量口径，只看本章族缺口）→ **增量冻结** `formula_runner.py execute --stage S --data-dir D --state-dir T --chapters chN`——按 dependency_manifest 切片本章消费公式；跨章公式已在全局冻结过的不重算（stdout `SCOPE:` 行为切片日志，向用户如实转述）。冻结完成后呈现《本章计算说明》文件卡：`briefing.py calc-summary --stage S --state-dir T --chapter chN --out T/state/calc_summary_chN.md`（rc=0=BRIEF_CALC_OK）——本章冻结值、算法与数据来源照贴原文禁改写，随 3a 汇报同轮呈出，不停车。
- **3a-2 模板推荐（可选增强，发卡即停）**：`query_kb` 检索样例报告库（stage+变体+节角色+本章主题过滤）→ 取 2~4 候选**脱敏**（矿名/地名/企业名→占位、数值→占位化；`sample_entities` 禁入清单机械校验通过方可作候选）→ 候选文件卡片 + 选择卡（选项=候选编号 + 常设「不用模板，按默认范式」）。选中模板注入 3b，作句法参照的加分项（实体与数值仍一律本项目冻结值）。检索无果/候选不足 → 如实告知，不阻塞。**按章不按节**（同章各节共享模板取向）。本步只是候选卡片展示——章节段落片段的写作参照由 3a-3 片段包强制供给，与本步互不替代（bug-4147）。
- **3a-3 范例挑选卡（卡B · 必做 · 发卡即停；bug-4147 交互化改造）**：样例片段不再默默取主导报告，改为**候选呈现、用户选定**——
  1. **列候选**：`sample_fragments.py --stage S --chapter chN --candidates 3 --out T/state/candidates_chN.json --content-dir T/state/candidates_content_chN`（S 同全脚本口径：stages/*.json 路径或裸 id 均可，脚本自动归一；rc=0=SAMPLE_CANDIDATES_OK 且候选整章原文逐份落盘 content_dir；rc=2=样例库无本章切片 → 向用户如实告知「本章无同类范例」，`progress.py fragment-choice chN --none --state-dir T` 落账，3b 以 `references/paradigms` 范式文档作参照——禁跳过挑选直接开写，红线 P13）。
  2. **呈卡挑选**：**候选全文文件卡（先呈，供通读比对）**——把 content_dir 下每份 `candidate-<i>-<rid>.md` 用 `present_artifacts` 呈文件卡，用户点开 Markdown 预览即可通读该候选整章写法（方案一：原文展示、来源可见——语料库是用户自有资料；卡面摘要仍按 bug-4155 脱敏，摘要无偏+全文有据分层）。候选译成中文挑选卡——每份列**候选编号、覆盖几个小节、约多少字、开头一两句摘录、结构特点**；卡面**字段级脱敏（bug-4155）**：禁含报告名/report_id/来源文件名/路径/矿名地名企业名等任何溯源信息——报告标识只进 `fragment-choice` 落账与取件命令，不上卡面；问「样例库里有 N 份同类章节，本章借鉴哪一份的写法？」；选项=候选编号 + 常设「**不用范例，按默认范式写**」（用户显式豁免=合法出口，`fragment-choice --none` 落账，3b 如实注明）。
  3. **选定取件**：`progress.py fragment-choice chN --report-id <选定报告> --state-dir T` 落账 → `sample_fragments.py --stage S --chapter chN --report-id <选定报告> --out T/state/sample_fragments_chN.md` 成章包（rc=0；选定报告不在候选集 rc=1，退回重选）→ **节级切包（bug P1-5）**：`sample_fragments.py --stage S --chapter chN --report-id <选定报告> --per-section --out-dir T/state/fragment_packs/chN`（按样例章 ### 节级逐节落盘 `<节号>.md`；rc=2=切不出节→节级退章包）。**3b 派发每节注入对应节包**（节号按 stage 章的 sample_anchor/节题对应样例节），节包缺失退章包 `T/state/sample_fragments_chN.md`、均缺退范式文档。片段包作本章各节写作的段落片段参照**唯一首选来源**。**无 choice 禁 3b 派发（红线 P13）**；修订=重发候选卡再选（fragment-choice 幂等覆盖）。
- **3b 节级派发**：`subagent_start`（`subagent_slug="eia-section-writer"`），波=本章全部 PENDING 节，在飞 ≤3，派发契约同 writer 4.1（节 id/要素链/深度目标/范式文件/输出契约/残留禁令全同）。**注入严格限定：本章数据族 + 本章冻结值 + 计划卡要点与用户补充意见（`state/plan_chN.json` 的 summary/notes，写作须回扣兑现，3d 核对）+ 前章要点包（state/key_points.json 增量累积）+ 样例片段包（3a-3 用户选定报告的**对应节包** `state/fragment_packs/chN/<对应样例节号>.md` 优先（bug P1-5），缺失退章包 `state/sample_fragments_chN.md`，段落片段参照首选）+ 本节角色范式文件（片段包 rc=2 降级或用户选「不用范例」时的句法参照）+ 用户选定模板（如有）**；禁注入全书上下文。范式角色六型（opener/baseline/analysis/measures/conclusion/process），`scripts/paradigm_role.py` 解析。写作纪律新增：「每个主要表格正文必须有引用与解读段」「工程师复合句式，数据从句串联，禁碎句堆叠」「禁 AI 腔过渡词（总体而言/值得注意/至关重要等）」。插图纪律（R5）：叙述遇到适合配图的位置（井田划分/工艺流程/监测布点等图示类内容）按 `{{FIG:图名}}` 落占位——占位独占一行，下一行以「建议插图：」一句话说明建议插图内容；占位原样保留交付（写手不产图、不省略、禁改成「如图所示」类空话），由用户后续自行插图。
- **3c 批量章门**：`progress.py gate --chapters chN --state-dir T`（唯一门入口，红线 P14；合规门 + L2 深度门 + **文风门四规则**：数字密度下限/表密度区间/文表联动下限/AI 腔禁用词，基准读 `references/style_targets/<stage>.json`；FAIL 输出节级归因）。**密度/表密度为占位符注入后口径**：节稿原文的 `{{SLOT:}}/{{TABLE:}}` 不计数字，禁按原文自测密度（系统性高估缺口，2026-10-29 重测实证），是否达标一律以门实测输出为准。FAIL 重派 ≤1（原 prompt+stderr）→ 仍 FAIL → `mark chN BLOCKED`——**BLOCKED 挂起不阻后续章**，协商留到该章确认卡或全书收口（next 指引为准）。**篇幅规模分支（计划卡选定项裁决，脚本自动读取 `state/plan_chN.json`）**：详实版=深度规则照常强制；精简版=篇幅规则不启用（PASS 行自动注明「用户选择精简篇幅」，禁再以篇幅不足退稿重派）；自定义字数=以用户目标字数为底线。详实版章门 FAIL（篇幅不足样例基准）→ **业务化询问用户**：「本章篇幅比同类报告标准少约 X 字——按样例扩写，还是按现稿收尾（成稿会注明差距）？」扩写=补写后重跑门；按现稿收尾=`approve-downgrade --chapters chN --note "用户选择按现稿收尾"` 降档留痕后照常确认。无计划卡工件（存量现场/历史工程）→ 上述分支不生效，既有强制语义零变化。**门凭据时效（bug-4146）**：gate FAIL 时 progress.py 自动把 VERIFIED 章回落 DRAFTED、REVIEWED 章封死确认通道——VERIFIED/REVIEWED 只代表「当前章稿最近一次门 PASS」，改稿后必须重跑门，旧 PASS 不作数。
- **3d 章级审查**：按 coal-eia-reviewer 规程出本章发现单（语义合规维度 A 法规/B 导则/C 标准 + 行文质量维度 D；发现单格式 `[PASS/WARN/FAIL] 条目|定位|证据摘录|修复建议`；只审不改）。收口 → `progress.py mark chN REVIEWED --state-dir T`（门凭据非 PASS 会被拒——先重跑门）；FAIL 退回 → `mark chN DRAFTED` 重写后重跑门。**计划卡兑现核对**：出发现单时把计划卡的用户补充意见（`state/plan_chN.json` 的 notes）列作对照项，逐条核对成稿是否兑现——未兑现写入发现单。成稿含插图占位时，发现单附「插图 N 处待补」清单行（R5——只提示，不阻塞）。
- **3e 呈现与确认（发卡即停）**：`present_artifacts` 本章文件卡片 + 发现单卡片 + `ask_user_question` 确认卡——选项：**进入下一章 / 返工本章（附意见）/ 暂停**，另设快捷选项「后续章节自动确认直至全书合并」。成稿含插图占位时，确认卡附**插图清单**（从章稿 `grep -o "{{FIG:[^}]*}}"` 生成：图名／建议插图内容／所在节），并注明「插图 N 处待你后续自行插入，交付稿中占位原样保留」。用户确认 → `progress.py confirm-chapter chN --highlights "要点1|要点2" --state-dir T`（本章要点并入 `state/key_points.json`，幂等）。**confirm-chapter 凭 `last_gate=PASS` 放行**；门 FAIL 的章要确认必须用户先 `approve-downgrade --chapters chN --note <原因>` 显式豁免（脚本会拒绝静默确认，bug-4146）。**确认卡是法定停车点：卡片发出后立即结束本回合/run。**
- **3f 返工回路**：用户意见 → 受影响节 `mark --sections … DRAFTED` 重派（原稿+意见注入）→ 3c/3d 重跑 → 确认卡重发。**每章返工 ≤5 次**（2026-10-28 立项 R4：私有化部署不计调用成本，上限仅防对话失控），超出走协商单（writer 4.5 三选项同款）。

**要点包机制**：writer 的 wave1 终点大要点包改为**每章确认后增量更新** `state/key_points.json`（本节要点+本章冻结关键值，confirm-chapter 自动并入）；投影章（ch13）最后写，天然拿到全部前章要点。

### 售后修改与复查（用户对已确认章的再修改 · 显式受理）

已确认章不在 `next` 的动作里（恢复检测自动跳过 CONFIRMED）——用户点名「润色某节／改某个数据／再查一遍」时**必须显式受理**，禁以「该章已完成」推脱，禁静默拒绝，也禁绕过门禁直改交付稿。三条路径：

- **点节返工（润色／局部改写／逻辑调整）**：先与用户对齐受理范围（改哪些节、怎么改）→ `progress.py mark chN DRAFTED`（已确认章唯一出口，此后 next 才会重新聚焦本章）→ 受影响节 `mark --sections … DRAFTED`（原稿+用户意见注入重派；未受影响节字节不动）→ 3c 门 → 3d 审查 → 3e 确认卡重发 → `confirm-chapter`（本章要点覆盖并入 `state/key_points.json`，后续章写作回扣新口径）。动手前如实预告：「该章将重新走质量校验与合规审查，通过后重新请你确认」。
- **数据修改级联（改核定值）**：先反查后改（writer 修改回路同款铁律）——`formula_runner.py impacted --field K --value V` 值差分 dry-run（零写盘）+ `chapter_planner.py impacted` 列受影响节集合，**受影响清单含其他已确认章时如实列出**；值差分+受影响章/节清单呈用户确认后再 `formula_runner.py update --field K --value V --impacted-file I`，各受影响章按上条点节返工路径重门重审；全书合并后步骤 4–7 consistency（XS 数字一致／SL 槽位残留）兜底扫旧值残留。禁不告知级联范围就改值。
- **轻量复查（不改稿）**：直调 coal-eia-reviewer 规程出本章发现单（只审不改）——progress.json 状态不动、成稿字节不动；发现单呈用户，是否转点节返工由用户决定。

### 步骤 4–7 · 合并 → 全文审查 → 修复 → 交付

1. `progress.py run-stage finalize --state-dir T --outputs-dir /home/gem/user-data/outputs --task "<本轮用户指令一句话>"`——build_output 全书拼装 + 全门一次报齐 + consistency 全书（XS1–XS20/EO1–EO3）+ snapshot save。
2. **全文审查**：按 coal-eia-reviewer 规程全书执行（`--full`）→ 发现单 `{报告名}-合规审查.md`（QA 副产物独立文件）。
3. **修复裁决**：FAIL 清单呈现用户，逐条决定修复（受影响章回 3b–3d）或豁免留痕。
4. **交付双件**：完整报告 `{项目名}-{阶段}-环境影响报告.md` + 审查发现单——**管线元数据/告警一律进发现单，禁入报告正文**。

交付铁律全套继承 writer：组装必须以 build_output.py 收尾绝不手工拼装；BUILD_READY/MANIFEST_READY 整行+退出码原样粘贴；`data/.delivery-contract` 勿删；交付后修改只落 state/sections/ 重跑 finalize。

## Iron Law（门 FAIL 的唯一合法出路）

```
门 FAIL 只有两条合法出路：只写补写节稿、申请用户降档。
降档凭据的用户授权必须真实：信任模式自动应答≠用户裁定——approve-downgrade 的 note 禁写「用户裁定」，自动应答场合须如实写「信任模式自动应答」，并同步告知用户可改判；用户可见话术禁称「你已裁定/你选定」，要说「信任模式自动应答选择了…（你可随时改）」。（2026-10-29 重测实证：自动应答被记作「用户裁定」落盘降档凭据，收尾话术三称「你已裁定」）
编辑 references/ 或绕过 build_output/gate CLI = 伪造基准，直接违反本技能红线。
确认卡意见是返工输入，不是绕门许可——返工稿必须重跑章门与审查（脚本强制：门凭据 last_gate 非 PASS 时 mark REVIEWED / confirm-chapter 均拒绝，降档豁免须 approve-downgrade 在先）。
```

## 平台预算与停车契约（全套继承 writer，停车点表分章特化）

run 级预算硬顶同 writer（recursion_limit 1000 步、bash 60 次）；主循环单 run bash 目标 ≤25 次，纯记账走批量原语。

| 停车点 | 动作 |
|---|---|
| 开题路由选择卡 / 门 1 全局包 GATE1_COMPLETE | 汇报缺失清单后停车 |
| 门 2 rc=3 anomalies 卡 | **发卡即停** |
| **3a-2 模板选择卡** | **发卡即停** |
| 3b 派发后 | 子代理后台跑，主 run 只轮询收节 |
| 3c 章门 FAIL 重派后 | 汇报差距停车 |
| **3e 确认卡（每章一个天然停车点）** | **发卡即停**——确认/返工/暂停，用户答复前不推进 |
| finalize / 全文审查发现单呈现后 | 汇报 FAIL 清单停车，等修复裁决 |

续跑靠磁盘 progress.json 不靠对话记忆：新 run 首动作 `progress.py next` 即恢复现场（CONFIRMED 章自动跳过）。

## 命令速查（分章特化；其余同 writer 速查表）

| 命令 | 作用 | 关键退出码 |
|---|---|---|
| `progress.py init --stage S --state-dir T --data-dir D --mode chapter` | 分章状态机初始化（**--mode chapter 必带**） | 0 / 1 已存在 |
| `progress.py plan-confirm chN --summary-file T/card_chN.md [--notes "补充意见"] --depth full\|compact\|custom [--target N]` | **计划卡落账（卡A，3a 前置，红线 P13）**：写 `state/plan_chN.json`，幂等覆盖=修订回环 | 0 PLAN_CONFIRMED / 1 非 chapter 模式、未知章、custom 缺 --target |
| `progress.py fragment-choice chN --report-id <报告>`（或 `--none`） | **范例挑选落账（卡B，3a-3 前置，红线 P13）**：写 `state/fragment_choice_chN.json`，幂等覆盖 | 0 FRAGMENT_CHOICE / 1 `--report-id` 与 `--none` 必须恰好一个 |
| `ingest.py check --stage S --data-dir D --global-only [--chapters <目标章集>]` | **门 1 全局包模式**：只校 global_families（`--chapters` 裁剪为目标章引用族，bug-4143） | 0=GATE1_COMPLETE / 2 缺项 |
| `formula_runner.py execute --stage S --data-dir D --state-dir T --chapters chN` | **增量冻结**：只冻结本章消费公式（跨章已冻结不动）；缺省=全量 | 0 / 3 anomalies（rc≠0 即停处置，禁带病续跑） |
| `progress.py next --state-dir T` | **单章聚焦**：COLLECTING→gate→review→确认卡→下一章，恰好一个下一步 | 0 |
| `sample_fragments.py --stage S --chapter chN --candidates 3 --out T/state/candidates_chN.json` | **范例候选（卡B 数据面）**：top-N 候选 JSON（来源报告/覆盖节数/字数）；S 路径或裸 id 均可（自动归一） | 0 SAMPLE_CANDIDATES_OK / 2 无本章切片（如实告知，`fragment-choice --none` 落账）/ 1 参数错误（stage 不在库、选定报告不在候选集） |
| `sample_fragments.py --stage S --chapter chN --report-id <选定> --out T/state/sample_fragments_chN.md` | **范例章包（选定取件）**：用户选定报告的真实切片，预算内节标题截断；缺省=主导报告（writer 全书管线口径不变） | 0 成包 / 2 无本章切片 / 1 选定报告不在候选集 |
| `sample_fragments.py --stage S --chapter chN --report-id <选定> --per-section --out-dir T/state/fragment_packs/chN` | **范例节包（bug P1-5）**：按样例章 ### 节级逐节切包 `<节号>.md`（3b 每节派发注入对应节包；卡B「覆盖节数」同此节级口径） | 0 节包落盘 / 2 切不出节（节级退章包）/ 1 参数错误（缺 --out-dir、与 --candidates 互斥、选定报告不在候选集） |
| `progress.py gate --chapters chN --state-dir T` | 单章门（合规+深度+文风四规则） | 0 PASS（章+节自动 VERIFIED）/ 1 FAIL（stderr 节级归因；VERIFIED 章新 FAIL 自动回落 DRAFTED） |
| `progress.py mark chN REVIEWED --state-dir T` | 审查收口记账（须门凭据 last_gate=PASS——非 PASS 先重跑 gate；bug-4146；节批量拒收） | 0 / 1 非法转移或门凭据非 PASS |
| `progress.py confirm-chapter chN --highlights "要点1\|要点2" --state-dir T` | **确认卡落账**（REVIEWED→CONFIRMED 唯一通道；highlights 增量并入 key_points.json，幂等） | 0（last_gate≠PASS 须有 approve-downgrade 留痕豁免）/ 1 非法转移或无豁免凭据 |
| `progress.py approve-downgrade --state-dir T --chapters chN --note "…"` | BLOCKED 协商降档留痕（兼作门凭据降档豁免凭据） | 0 / 1 |

rc 取法：`<命令> > /tmp/o 2>&1; echo rc=$?`——**禁 `| head` 后 `echo $?`**（那是管道末端命令的 rc，bug-4151 实证）；命令参数全样例看 `progress.py mark --help`、`progress.py gate --help`。

## KF 契约 / 能力边界 / 参考文件

全套继承 coal-eia-writer 同名章节（结构真源=依赖包 references/——`/home/gem/skills/coal-eia-writer/references/`，单源化 P2-8；模板=派生工件；样例库变体标注 `corpus_meta.json` 的 `variant` 字段供模板检索过滤；`references/style_targets/<stage>.json` 为文风门基准；`references/paradigms/roles/<stage>.json` 六型角色映射 + conclusion/process 范式）。脚本地基（ingest/formula_runner/chapter_planner/build_output/progress/consistency/snapshot/mapping/sample_fragments）与 writer 字节一致（sync_chapter_skill.py 同步守卫），语义与行为以 coal-eia-writer SKILL.md 对应章节为准。
