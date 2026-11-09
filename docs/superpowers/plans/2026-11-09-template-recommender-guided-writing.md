# template-recommender 逐节引导写作重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `template-recommender` 技能重写为逐节引导写作四卡循环（选节→选模板→补全→确认→推进下一节），slot-filler 与 tools.py 描述同步，运行栈落栈并 E2E 实测。

**Architecture:** 纯提示词层改造（无脚本、无后端逻辑改动）：重写 SKILL.md 为四卡交互流，进度/成稿落沙箱工作区档案文件；slot-filler 仅加接管声明；tools.py 改一句工具描述。设计文档：`docs/vibe/2026-11-09-template-recommender-guided-writing-design.md`（已获批）。

**Tech Stack:** Markdown SKILL.md（提示词）、平台工具 `ask_user_question`/`present_artifacts`/`read_file`/`write_file`/`edit_file`/`execute`、Docker 运行栈（pisuan-localized-api-1）。

---

## 环境与红线备忘（执行者必读）

- **工作分支**：`pisuan-localized`（用户明示在本树直接开发；本计划一切改动都提交到本分支）。
- **零改动红线**：`backend/package/pisuan/agents/skills/buildin/coal-eia-writer/` 与 `backend/package/pisuan/agents/skills/buildin/coal-eia-chapter-writer/` 两个目录**任何文件不许动**（含 scripts/、references/）。`template-recommender/SKILL.md.bak` 是存量备份，不动。
- **改动面（全部）**：template-recommender/SKILL.md（重写）、slot-filler/SKILL.md（两处）、`backend/package/pisuan/agents/toolkits/buildin/tools.py`（一句）、`docs/develop-guides/changelog.md`（补记）、设计文档与计划文档入库。
- **提交规范**：中文 Conventional Commits，每条以 `Co-Authored-By: Claude Code <noreply@anthropic.com>` 结尾。
- **运行栈**：容器 `pisuan-localized-api-1`（端口 5050）；`/app/package` 挂载源 = 本树 `backend/package`；api 重启触发 lifespan reseed（init_builtin_skills 原子替换）→ `skill-sources/shared` 卷；**admin 投影卷惰性滞后，须手动同步**（沙箱实际读投影卷）。api 容器 watchfiles 收不到 Windows bind mount 写入事件，后端改动生效靠 `docker restart pisuan-localized-api-1`。
- **重启顺序**：先确认 milvus healthy，再重启 api（milvus 未就绪时 api lifespan 会失败退出）。
- **凭据**：运行栈 admin 密码历来由用户当场提供，禁试种子凭据。E2E 用模型切 `deepseek:deepseek-flash`（新会话默认 gemma 端点未起）。
- **沙箱宿主机路径**：`docker/volumes/pisuan/threads/shared/admin/workspace/workspace/`（双层 workspace），template-writing 档案在其下。
- docker exec 传容器内路径时 Bash 须加 `MSYS_NO_PATHCONV=1`。

---

### Task 1: 重写 template-recommender SKILL.md

**Files:**
- Modify（整文件替换）: `backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md`

- [ ] **Step 1: 用以下完整内容覆盖 SKILL.md（Write 全量写入）**

````markdown
---
name: template-recommender
description: "逐节引导写作技能（高用户参与模式）：按报告叶子章节逐节推进——模板候选卡片让用户自选，给出组装建议与待补数据，用户补全后组装成稿并确认，确认后自动推荐进入下一节。触发：用户要求逐节写、边选边写、自己挑模板编写报告（如环评报告），或要求推荐章节/段落模板。用户要整本或整章自动批量编写时属于另外两种写作模式，本技能不接，如实告知即可。"
version: "2026.11.09"
tool_dependencies: ["list_kbs", "get_mindmap", "query_kb", "get_templates", "list_report_types", "list_chapter_keys", "ask_user_question", "present_artifacts", "read_file", "write_file", "edit_file", "execute"]
skill_dependencies: []
---

# 逐节引导写作

你是报告逐节引导写作助手：一次只聚焦一个叶子章节，让用户亲自完成
「选章节 → 选模板 → 补数据 → 确认成稿」四步，确认后自动推荐进入下一节，
循环直到目标范围写完。

## 三种写作模式（模型路由用，勿把模式名抛给用户）

| 模式 | 技能 | 用户参与 |
|------|------|----------|
| 全书自动编写 | coal-eia-writer | 低 |
| 分章自动编写 | coal-eia-chapter-writer | 低 |
| 逐节引导编写（本技能） | template-recommender | 高（每节四步全参与） |

用户要整本/整章自动跑管线时不属于本技能：如实告知「整本自动编写是另一种模式」，不接、不混跑。

## 用户沟通规范（所有面向用户的文字）

1. 全中文：正文、卡题面、选项、进度播报一律简体中文；专业缩写除外（标准号、单位）。
2. 零机制词：禁出现工具名、文件路径、脚本、状态枚举、JSON 字段名；进度说「写作档案」不说路径；另两个模式对用户只说「整本自动编写 / 分章自动编写」，禁提技能名。
3. 播报短：每条进度播报 ≤3 句——进展一句、下一步一句、（如需）请求一句；节稿全文照贴不计入此限。
4. 卡题面一句话讲清情境与后果；选项用动宾业务短语（「就写这一节」「先停一下」）。
5. 资料与文件一律中文名，禁英文键与文件名（交付的报告文件名除外）。

## 红线（违反任何一条即停）

1. 发卡即停：每张卡发出后立即结束回合等用户作答；待补槽位超过 5 个拆多张补全卡时，每张仍是一次提问等待，同属补全环节。
2. 填写项禁做成选择题：数据、数值、名称、日期等填写类内容逐项自由文本提问（不带选项）；选项只放真实可选的枚举值（章节、模板候选、处置方式），每题 2-5 个；示例与格式说明只写在题面文字里，禁做进选项。
3. 禁编造：自动填充只限高置信度且可溯源（值+来源记入写作档案）；中/低置信度一律经补全卡请用户确认；哪里都没有就如实列「待补」，禁猜测填充。
4. 数值纪律：保留用户给出的原始精度与单位，不四舍五入不换算（题面明确要求单位的除外）；同一参数全部章节同一个值。
5. 样例禁抄：样例切片只学结构与写法——样例里的矿名/地名/企业名/数值禁进本项目正文；上卡面前先脱敏（实体→「某矿」「某企业」占位，数值→「××」占位）；报告名/文件名/路径等溯源信息不上卡面。
6. 进度唯一权威=写作档案：进度与成稿以工作区档案为准，会话记忆只是回声；开局先读档案再定行动。
7. 语料只读：写作技能包内的语料资料（样例库/范式文档/实体清单）只读参照，禁改动那些目录的任何文件。

## 工作区（写作档案）

```
/home/gem/user-data/workspace/template-writing/<报告名>/
  progress.json        # 进度档案（唯一权威）
  sections/<节号>.md   # 每节确认稿
```

write_file/edit_file 可能触发平台写审批，等待批准即可，禁因此绕过落盘。

progress.json 结构（每节确认或跳过后立即更新）：

```json
{
  "report_name": "某矿区总体规划环境影响报告书",
  "domain": "coal_mining",
  "report_type": "规划环评",
  "kbs": ["煤矿环评报告模板库"],
  "sections": [
    {
      "key": "4.2",
      "title": "地表水环境影响预测",
      "path": ["第四章 环境影响预测", "4.2"],
      "status": "pending",
      "template_source": "kb",
      "template_summary": "模板库五段式：源强→预测情景→预测结果→影响分析→措施",
      "slots": {
        "生产规模": {"value": "8.0 Mt/a", "source": "user", "confidence": "高"}
      },
      "draft": "sections/4.2.md"
    }
  ],
  "updated_at": "2026-11-09T10:00:00"
}
```

status 取值：pending（待写）/ confirmed（已确认）/ skipped（跳过）。
template_source 取值：kb（模板库）/ sample（样例参照）/ none（常规写法）。

## 操作流程

### 开局定位（一次性）

1. `list_kbs` 确认对话已选知识库：为零 → 告知用户先在对话设置里选择领域知识库后再来，本回合结束；多个且领域不同 → 开局卡确认范围。
2. `get_mindmap` 取章节树；`list_report_types` / `list_chapter_keys` 取合法口径（domain/report_type 用数据字典 code，禁猜）。
3. 结合用户目标定位范围：点名章节 → 该章子树；给关键字 → 树上匹配；要整本 → 全树。展开为叶子节清单（有子节的章展开到叶子节），推进顺序按章节号。
4. 探测语料：execute 列 `/home/gem/skills/coal-eia-writer/references/` 下的 samples_bank/（真实报告切片）与 paradigms/（通用范式）；目录不存在 → 正文如实说明一句「没有找到同类报告样例库，将只用知识库模板」，不阻塞。
5. 读写作档案：`/home/gem/user-data/workspace/template-writing/` 下已有本报告 progress.json → 以档案为准呈进度（完成/待写/跳过各几节、下一节是哪个），开局卡问「继续下一节 / 复查某一节 / 另开新报告」；没有 → 开局确认报告名（作档案目录名）与起始范围，建档案起步。
6. 用户目标只给了章没给报告名、或范围有歧义 → 开局卡一并问清，禁静默选定。

### 卡1 · 选节卡（每轮第一张，发卡即停）

- 题面：进度一句话（目标范围共 N 节、已完成 M 节）+「建议下一节写〈节号 节名〉」。
- 选项：推荐节（首位）+ 同章其他待写节按顺序补位，节选项合计 ≤4，末位固定「先停一下」；允许自行输入节名或关键字换节（allow_other 开）。
- 待写节超过选项容量 → 题面注明「也可以直接输入你想写的节名」。

### 卡2 · 选模板卡（候选 ≥2 才发，发卡即停）

选定节后取候选：

1. `get_templates(domain, report_type, canonical_chapter_key)` 取该节结构化模板；无结果时按 `list_chapter_keys` 核对口径后重试一次，仍无 → 如实告知该节模板库没有收录。
2. 语料可用且为本领域（煤矿环评）→ samples_bank/ 找同章真实切片作「样例参照」候选。
3. 候选全文先呈：每份候选用 present_artifacts 呈文件卡（模板：泛化模板全文+插槽清单+原文引用；样例：脱敏切片全文），文件卡不停车。
4. 候选 ≥2 → 选择卡：题面「〈节名〉找到 N 份模板/样例，用哪份？」；选项 = 候选摘要合计 ≤4（来源标「模板库」/「样例参照」+ 结构特点 + 约多少段；模板含完整插槽定义时推荐模板库候选）+ 末位「都不用，按常规写法」；allow_other 开。候选 =1 → 不发选择卡，正文一句话说明采用哪份，直接进卡3（用户不同意可随时叫停）。候选 =0 → 如实告知，选项「按常规写法直接写 / 换一节 / 先停一下」。

### 卡3 · 组装建议 + 补全卡（发卡即停）

1. 正文先给组装建议（对话消息，不是卡）：
   - 本节怎么从所选模板展开成段落：段落骨架（开头定性句 → 数据落点 → 预测/分析主体 → 措施/结论收尾）；
   - 插槽清单表分两栏：已自动填好（值+来源+置信度）/ 待你补充（插槽名+需要什么数据+格式说明）。
   自动填充只做高置信度可溯源项（红线 3）；插槽值优先取对话上文与知识库检索（query_kb），缺的列「待补」。
2. 补全卡：待补插槽逐项自由文本提问（不带选项），每卡 ≤5 问，超出拆多卡；格式说明写在题面（如「生产规模，单位 Mt/a，例：8.0」）。
3. 用户答完 → 插槽值注入模板组装本节草稿 → write_file 落 sections/<节号>.md → 对话中全文呈现节稿（节标题+正文，末尾一句要点提示）。

### 卡4 · 确认卡（法定停车点，发卡即停）

- 题面：「〈节名〉成稿已在上面呈现并存入写作档案，怎么处理？」
- 选项：「确认，写下一节〈下一节名〉」（首位）/「要改」/「先停一下」。
- 确认 → progress.json 该节置 confirmed 并写盘 → 回卡1 推荐下一节。
- 要改 → 用户附修改意见后重写（意见涉及换模板/换数据时回卡2/卡3，否则直接改）→ 重呈 → 卡4 重发；多轮仍不收敛 → 如实说明并请用户给方向。
- 停 → 播报一句进度（写到哪节、还剩几节），回合结束。

### 完成摘要

目标范围全部节 confirmed/skipped → 呈各节清单（节号、节名、状态）+ 一句话收尾，问「还有其他章要写吗 / 就到这里」。

### 已确认节的修订（用户点名时显式受理）

用户要改已确认节 → 先列受影响范围（改某参数值时，反查已确认节里用过该值的节，如实列出）→ 用户确认后改值/改写 → 重呈 → 卡4 重发 → 档案同步更新。禁拒绝受理，禁不经确认直改成稿。

## 数据源

1. 知识库（主源）：对话设置中已选的领域知识库——章节树（get_mindmap）、结构化段落模板（get_templates）、补充检索（query_kb）。
2. 写作技能语料（辅源，只读）：`/home/gem/skills/coal-eia-writer/references/` 下 samples_bank/（真实报告切片）、paradigms/（通用范式文档）、sample_entities/（样例实体禁抄清单）。检索=execute 列目录 + read_file 读内容；此语料是煤矿环评领域，其他领域按无样例处理并如实说明。
3. 两处都没有 → 如实告知并给选项（按常规写法直接写 / 换一节 / 先停一下），禁编造模板与数据。

### 模板记录字段口径（get_templates 两种返回形态）

模板记录可能来自图谱或数据库回退（看 `_source` 字段），字段名不同，按实际返回读取，禁编造字段名：

- 图谱（`_source: "graph"`）：泛化模板文本=`text_pattern`，插槽=`slots`（name/type/entity_ref），标准依据=`legal_references`（code/name）。
- 数据库回退（`_source: "db"` / `"db_fallback"`）：泛化模板文本=`generalized`，插槽=`slots`（以 name 为准，type/description 有则参考），原文引用=`sample_original`，章节=`chapter`；出现 `_degraded_note` 时按其要求向用户如实说明图谱暂不可用。
````

- [ ] **Step 2: 确认文件写盘成功（frontmatter 快查）**

```bash
head -8 backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md
```

Expected: 首行 `---`，含 `name: template-recommender`、`version: "2026.11.09"`。

- [ ] **Step 3: Commit**

```bash
git add backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md
git commit -m "feat(skills): template-recommender 重构为逐节引导写作四卡循环

选节→选模板→补全→确认→推进下一节的逐节引导流；进度与成稿落沙箱
写作档案（progress.json+sections/，无脚本）；数据源=知识库模板+writer
语料只读参照（脱敏禁抄）；继承平台沟通规范与数据纪律。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: slot-filler SKILL.md 接管声明

**Files:**
- Modify: `backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md`（仅两处，其余不动）

- [ ] **Step 1: Edit frontmatter description（精确替换）**

old:
```yaml
description: "根据上下文和用户提供的附件，智能填充段落模板中的插槽。在模板推荐完成后自动触发，为每个插槽填入数据并给出置信度，绝不编造数据，无法填充的插槽会提示用户补充。依赖 template-recommender 技能。"
```

new:
```yaml
description: "【已被接管·存量兼容】逐节引导写作流程（模板候选自选→组装建议→补全确认→推进下一节）已由 template-recommender 技能一体承担，新会话勿单独触发本技能。本技能仅供存量会话按旧协议批量填槽：根据上下文和用户提供的附件，为段落模板中的插槽填入数据并给出置信度，绝不编造数据，无法填充的插槽提示用户补充。"
```

- [ ] **Step 2: Edit 正文头部加接管声明（精确替换）**

old:
```markdown
# 智能填槽

在段落模板推荐（template-recommender）完成后，
```

new:
```markdown
# 智能填槽

> **接管声明（2026-11-09）**：逐节引导写作流程（模板候选自选 → 组装建议 → 补全确认 → 推进下一节）已由 template-recommender 技能一体承担，新会话勿单独触发本技能；以下旧版批量填槽协议仅供存量会话兼容。

在段落模板推荐（template-recommender）完成后，
```

- [ ] **Step 3: 确认改动面（git diff 只含这两处）**

```bash
git diff --stat backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md
git diff backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md | head -40
```

Expected: 仅 description 行 + 新增声明段，`skill_dependencies` 等其余 frontmatter 与正文协议未动。

- [ ] **Step 4: Commit**

```bash
git add backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md
git commit -m "docs(skills): slot-filler 声明批量填槽已由 template-recommender 接管

描述与正文头部加接管声明，旧协议保留供存量会话兼容。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: tools.py GET_TEMPLATES_DESCRIPTION 同步

**Files:**
- Modify: `backend/package/pisuan/agents/toolkits/buildin/tools.py:765`（一行）

- [ ] **Step 1: Edit 精确替换**

old:
```python
template-recommender 用它推荐段落模板；slot-filler 用它取插槽定义。
```

new:
```python
template-recommender 逐节引导流用它取模板候选；slot-filler（旧版批量填槽，已接管）用它取插槽定义。
```

- [ ] **Step 2: Python 语法校验 + 确认零行为改动**

```bash
python -c "import ast; ast.parse(open('backend/package/pisuan/agents/toolkits/buildin/tools.py', encoding='utf-8').read()); print('OK')"
git diff --stat backend/package/pisuan/agents/toolkits/buildin/tools.py
```

Expected: `OK`；diff 仅 1 行（docstring 内）。

- [ ] **Step 3: Commit**

```bash
git add backend/package/pisuan/agents/toolkits/buildin/tools.py
git commit -m "docs(tools): get_templates 工具描述同步逐节引导流分工

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: changelog 补记 + 设计/计划文档入库

**Files:**
- Modify: `docs/develop-guides/changelog.md`（v0.7.3「### 功能与修复」列表首插入一条）
- Add（gitignore 内，强制入库）: `docs/vibe/2026-11-09-template-recommender-guided-writing-design.md`
- Add（gitignore 内，强制入库）: `docs/superpowers/plans/2026-11-09-template-recommender-guided-writing.md`

- [ ] **Step 1: 在 changelog.md 的 `### 功能与修复` 行（v0.7.3 节内）之后插入首条**

```markdown
- feat(skills): template-recommender 重构为逐节引导写作（高用户参与模式）。原技能一次性 Markdown 灌出模板与插槽、无交互无推进；全书/分章自动管线（writer/chapter-writer）用户参与度低，本技能补位第三种模式——逐节四卡循环：选节卡（推荐下一叶节+可换节）→ 选模板卡（get_templates 模板候选 + writer 语料同章切片样例参照，候选全文文件卡先呈、选择卡后发，发卡即停）→ 补全卡（组装建议进正文、待补插槽逐项自由文本、每卡≤5问、填写项禁做选择题）→ 确认卡（确认即落 sections/<节号>.md 并自动推荐下一节）。进度与成稿落沙箱写作档案 template-writing/<报告名>/progress.json（无脚本，agent 文件工具直维护，跨会话恢复以档案为唯一权威）。纪律：禁编造（自动填充仅高置信度可溯源，中低置信度经补全卡确认）、数值保精度保单位、样例禁抄+卡面脱敏（sample_entities 禁抄清单）、全中文零机制词。coal-eia-writer/chapter-writer 两目录零改动（语料只读引用）；slot-filler 改描述声明接管；get_templates 工具描述同步。验证：运行栈 reseed 落栈 md5 核对 + 四卡流/跨会话恢复 E2E 实测（设计详见 docs/vibe/2026-11-09-template-recommender-guided-writing-design.md）。
```

- [ ] **Step 2: 设计与计划文档强制入库**

```bash
git add -f docs/vibe/2026-11-09-template-recommender-guided-writing-design.md
git add -f docs/superpowers/plans/2026-11-09-template-recommender-guided-writing.md
```

- [ ] **Step 3: Commit**

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(changelog): 补记 template-recommender 逐节引导流重构；设计与计划文档入库

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 静态校验与零改动红线核对

**Files:** 无新改动，纯校验。

- [ ] **Step 1: writer/chapter-writer 零改动核对**

```bash
git diff --stat HEAD -- backend/package/pisuan/agents/skills/buildin/coal-eia-writer backend/package/pisuan/agents/skills/buildin/coal-eia-chapter-writer
```

Expected: 空输出。

- [ ] **Step 2: 全部改动面核对（本计划任务 1-4 累计）**

```bash
git diff --stat HEAD~4 HEAD
git status --porcelain
```

Expected: HEAD~4..HEAD 恰含 5 个文件（template-recommender/SKILL.md、slot-filler/SKILL.md、tools.py、changelog.md、2 个 docs 文件共 6 个路径——以实际提交拆分为准逐条对上）；`git status --porcelain` 无未预期的未跟踪/改动文件（`.wolf/` 与 deploy 等存量脏文件除外）。

- [ ] **Step 3: 两个 SKILL.md frontmatter 完整性**

```bash
python -c "
import io,re
for p in ['backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md','backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md']:
    t=io.open(p,encoding='utf-8').read()
    m=re.match(r'^---\n(.*?)\n---\n',t,re.S)
    assert m, p+' frontmatter 缺失'
    fm=m.group(1)
    assert 'name: ' in fm and 'version: ' in fm and 'description: ' in fm, p+' frontmatter 字段不全'
print('FRONTMATTER_OK')
"
```

Expected: `FRONTMATTER_OK`。

---

### Task 6: 运行栈落栈与 md5 核对

**Files:** 无新改动，部署验证。

- [ ] **Step 1: 栈健康前置检查**

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'pisuan-localized-(api|milvus)'
```

Expected: `pisuan-localized-milvus-1` 为 healthy 后才进行 Step 2（milvus 未就绪则等/先起 milvus——api 在 milvus 未就绪时重启会 lifespan 失败退出）。

- [ ] **Step 2: 重启 api 触发 reseed**

```bash
docker restart pisuan-localized-api-1
```

然后：

```bash
docker logs pisuan-localized-api-1 --tail 60
```

Expected: 启动日志无 `Application startup failed`、无技能解析报错；出现正常 lifespan 完成（Milvus/知识库组件加载成功）。

- [ ] **Step 3: 定位三面落栈路径（挂载全量清单，勿 grep 过滤）**

```bash
docker inspect pisuan-localized-api-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

Expected: 能指认 ①`/app/package` 挂载源（应为 `C:\workspace\pisuan-localized\backend\package` 或等效路径）②skill-sources/shared 卷宿主路径 ③skill-projections/admin 投影卷宿主路径。后续步骤以实际指认路径为准（下称 `<shared>/<slug>/`、`<proj>/<slug>/`）。

- [ ] **Step 4: 三面 md5 核对（repo → shared → 投影）**

对两个改动的技能目录各核对（宿主侧 PowerShell Get-FileHash 或 bash md5sum 均可）：

```bash
md5sum backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md <shared>/template-recommender/SKILL.md <proj>/template-recommender/SKILL.md
md5sum backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md <shared>/slot-filler/SKILL.md <proj>/slot-filler/SKILL.md
```

Expected: template-recommender/SKILL.md 三面一致。slot-filler 若 shared 一致而投影滞后 → Step 5；三面一致则跳过 Step 5。

- [ ] **Step 5: 投影卷手动同步（仅当 Step 4 发现滞后）**

```bash
cp <shared>/template-recommender/SKILL.md <proj>/template-recommender/SKILL.md
cp <shared>/slot-filler/SKILL.md <proj>/slot-filler/SKILL.md
# 重跑 Step 4 核对归一
```

注意：禁直接 cp 进 shared（reseed 会用挂载源快照整目录回灌）——shared 以 reseed 为准，手动只补投影。

- [ ] **Step 6: 记录落栈证据**

把 Step 4/5 的 md5 输出贴进任务汇报（执行代理的最终报告须含三面 md5 表）。

---

### Task 7: E2E 实测（需用户配合页面操作）

**Files:** 无代码改动；实测产出=进度档案与节稿（沙箱内）。

- [ ] **Step 1: 实测前置（执行代理准备，告知用户）**

- 栈健康（Task 6 已过）；用户在对话页登录（admin 密码用户当场提供，禁试种子凭据）。
- 新建对话：模型切 `deepseek:deepseek-flash`；对话设置勾选知识库「煤矿环评报告模板库」（以实际在册 KB 为准）。

- [ ] **Step 2: 主流程实测（用户操作，执行代理按清单核验）**

用户在对话页输入触发语（示例）：「我想逐节写煤矿矿井环评报告的第四章，模板我自己挑，每节写完我确认」。

逐卡核验清单（执行代理据对话记录核验）：

1. **开局**：有知识库范围确认/报告名确认（未给报告名时问），无机制词、全中文。
2. **卡1 选节卡**：推荐下一叶子节标首位；选项 ≤5（节选项 ≤4+停车项）；可自行输入换节。
3. **卡2 选模板卡**：候选全文先出文件卡；候选 ≥2 才有选择卡，候选摘要标来源（模板库/样例参照）；样例候选卡面已脱敏（无矿名/报告名/数值原文）。
4. **卡3**：组装建议在正文（段落骨架+插槽两栏表）；待补插槽为自由文本问题且不带选项；自动填充值带来源与置信度。
5. **卡4 确认卡**：节稿全文在对话呈现；确认后播报 ≤3 句并自动推荐下一节（回卡1）。
6. **用户换模板/要改**：返工回路按意见执行且不丢已填数据。

- [ ] **Step 3: 档案落盘交叉核对（执行代理宿主机直查）**

```bash
ls "docker/volumes/pisuan/threads/shared/admin/workspace/workspace/template-writing/"
# 以实际报告名 slug 进入后：
cat "docker/volumes/pisuan/threads/shared/admin/workspace/workspace/template-writing/<报告名>/progress.json"
ls "docker/volumes/pisuan/threads/shared/admin/workspace/workspace/template-writing/<报告名>/sections/"
```

Expected: progress.json 与页面确认进度一致（status/template_source/slots 与对话应答对应）；sections/ 下有确认节的 md 文件且内容=对话呈现稿。

- [ ] **Step 4: 跨会话恢复实测**

用户新建一个对话（同账号），输入「继续写我的报告」。

Expected: 智能体读档案呈进度摘要并问「继续下一节 / 复查某一节 / 另开新报告」，续写点与档案一致（不从头开始、不重写已确认节）。

- [ ] **Step 5: 实测问题闭环**

任何一项不符 → 记录现象与对话证据 → 修 SKILL.md 措辞（走 Task 1 同款 Edit + 重启 reseed + 投影同步）→ 复测该项；修了什么记入 `.wolf/buglog.json`（bug-NNN 结构）。

---

### Task 8: 收尾

- [ ] **Step 1: changelog 验证句回填实测结果（新提交，不 amend）**

把 Task 4 条目中「验证：…」一句替换为实测实际结果（如「运行栈 reseed 落栈三面 md5 归一；四卡流 E2E 实测通过（含换节/换模板/跨会话恢复）；发现并修复 <N> 处措辞问题（bug-NNN…）」）：

```bash
git add docs/develop-guides/changelog.md
git commit -m "docs(changelog): 回填逐节引导流 E2E 实测结果

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 2: OpenWolf 记账**

- `.wolf/memory.md` 追加本轮动作行；
- `.wolf/cerebrum.md` Key Learnings 补一条（get_templates 双形态字段口径：graph=text_pattern/legal_references，db=generalized/sample_original——后续任何模板消费方都受用）；
- `.wolf/anatomy.md` 如有新文件则补条目（本计划预期的计划文档与设计文档条目若缺则补）；
- 有 bug 修复则 `.wolf/buglog.json` 追加。

- [ ] **Step 3: 完成汇报**

向用户汇报：改动清单（5 文件路径）、三面 md5 表、E2E 核验清单逐项结果、遗留问题（如有）。

---

## Self-Review 记录

1. **Spec 覆盖**：设计文档 §2 改动面→Task 1-4；§3 三模式路由→Task 1 SKILL.md「三种写作模式」节；§4 四卡循环→SKILL.md 操作流程；§5 双数据源+样例纪律→SKILL.md 数据源节+红线 5；§6 工作区→SKILL.md 工作区节；§7 纪律→SKILL.md 沟通规范+红线；§8 frontmatter/结构→Task 1 全文；§9 checklist→Task 5/6/7/8 逐项对应。无缺口。
2. **占位符扫描**：Task 6 Step 3/4 的 `<shared>/<proj>/<报告名>` 为运行时探测值，Step 3 已给出探测命令，属「探测后代入」而非 TBD；其余步骤全部给出完整内容。
3. **类型一致性**：progress.json schema（status/template_source/slots.source/confidence/draft）在 SKILL.md 工作区节与 Task 7 核验清单一致；卡片约束（≤5 问/卡、节选项 ≤4+停车项、候选 ≤4+常设项）各处一致。
