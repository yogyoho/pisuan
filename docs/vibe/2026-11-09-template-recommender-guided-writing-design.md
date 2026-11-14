# template-recommender 重构设计：逐节引导写作（高用户参与模式）

- 日期：2026-11-09
- 状态：设计已获用户批准（对话内交互卡 / 一体化单技能 / 落盘工作区 三项裁定）；2026-11-10 增补知识库检索参照轨（用户裁定）；2026-11-10 增补卡面推荐项高亮与选项 description 说明行
- 关联：`backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md`

## 1. 背景与目标

平台现有两个报告写作技能都是**管线执行模式**，用户参与度低：

- `coal-eia-writer`：全书批量管线，一次派发全部章，用户只在少量停车点确认；
- `coal-eia-chapter-writer`：分章管线，每章一组既定卡片（计划卡→挑选卡→确认卡），参与度略高但写作过程仍由管线主导。

现有 `template-recommender` 技能是一次性 Markdown 大灌输出（章节树+模板详情+插槽+原文引用一次性全部倒出），无交互、无选择、无写作推进，与 `slot-filler`（批量填槽）配合的链路在真实使用中参与感差。

**目标**：把 `template-recommender` 重构为第三种写作模式——**逐节引导写作**，用户对每一个叶子章节亲自参与四步：**选章节 → 选模板 → 补数据 → 确认成稿**，确认后自动推荐进入下一节，循环直至目标范围完成。

## 2. 范围与边界（硬边界）

**改动面（全部为提示词层 + 一处工具描述）：**

| 文件 | 改动 |
|------|------|
| `backend/package/pisuan/agents/skills/buildin/template-recommender/SKILL.md` | 重写（本文档主体） |
| `backend/package/pisuan/agents/skills/buildin/slot-filler/SKILL.md` | 仅 frontmatter description + 开头一段：声明批量填槽旧流程已由 template-recommender 逐节引导流接管，其余保留（兼容存量会话） |
| `backend/package/pisuan/agents/toolkits/buildin/tools.py` | `GET_TEMPLATES_DESCRIPTION` 一句话更新（提及逐节引导流） |

**零改动红线：**

- `coal-eia-writer/` 与 `coal-eia-chapter-writer/` 两个目录**任何文件不动**（SKILL.md、scripts/、references/ 全部零改动）；
- 前端、卡片协议、`ask_user_question` 后端机制零改动。

**只读引用（非改动）**：沙箱内跨技能只读路径 `/home/gem/skills/coal-eia-writer/references/` 下的语料资产：

- `samples_bank/` — 真实报告切片（样例库）；
- `paradigms/` — 通用范式文档；
- `sample_entities/` — 样例实体禁抄注册表。

## 3. 三模式定位

| 模式 | 技能 | 粒度 | 用户参与 |
|------|------|------|----------|
| 全书批量管线 | coal-eia-writer | 整本 | 低（少量停车点） |
| 分章管线 | coal-eia-chapter-writer | 章 | 低-中（章级卡片） |
| **逐节引导写作（本技能）** | template-recommender | **叶子节** | **高（每节四步全参与）** |

**触发路由**（写入 frontmatter description，供模型路由）：用户要「边选边写、逐节确认、模板我自己挑」→ 本技能；用户要整本/整章自动管线 → 另两个技能。本技能正文不主动推给用户另两技能的分工（用户问起才提）。

## 4. 交互流程：四卡循环

### 4.0 开局定位（一次性）

1. `list_kbs` 确认对话已选知识库范围；零 KB → 如实告知需先在对话设置选择，停。多 KB 且领域不同 → 开局确认卡让用户选定范围。
2. `get_mindmap` 取章节树；`list_report_types` / `list_chapter_keys` 取合法口径。
3. 结合用户目标（点名章节 / 关键字 / 整本）在树上定位目标范围，展开为**叶子节清单**（推进顺序 = 报告章节号顺序）。
4. **恢复检测**：工作区已有 `progress.json` → 以文件为唯一权威（会话记忆视为过期回声），呈进度摘要（已完成/待写/跳过各多少节，下一节是哪个），问「继续下一节 / 复查某节 / 开新报告」。
5. **报告名**：用户目标中未提报告名时，开局确认卡一并问（也用作工作区目录 slug）。

### 4.1 卡1 · 选节卡（发卡即停）

- question：报告进度一句话（第 M 节/共 N 节）+ 推荐「下一节写〈节号 节名〉」；
- options：推荐节（标推荐，首位）+ 同章其他待写节按顺序补位（合计 ≤4）+「先停一下」；`allow_other` 开（用户可自行输入节名/关键字换节）；
- 待写节超出选项容量 → question 文本注明可自行输入节名。

### 4.2 卡2 · 选模板卡（发卡即停；仅多候选时发）

1. 对选定节调 `get_templates(domain, report_type, canonical_chapter_key)` 取结构化模板候选；同时查 `samples_bank/` 是否有同章真实切片（有则脱敏后作「样例参照」候选）。结构化模板查无结果时，再用 `query_kb` 以该节主题词检索知识库相关段落，命中的段落脱敏后作「知识库参照」候选并入候选清单；三路（结构化模板/知识库参照/样例参照）都为空才走候选=0 分支。
2. **候选全文先呈**：每份候选用 `present_artifacts` 呈文件卡（泛化模板/插槽清单/原文引用或样例切片全文），文件卡不停车。
3. **候选 ≥2** → 选择卡：选项 = 候选摘要（来源标注「模板库」/「样例参照」+ 结构特点 + 约多少段），推荐项标首位，常设「都不用，按常规写法」；合计 ≤5，`allow_other` 开。
4. **候选 =1** → 不发选择卡，正文一句话说明采用哪份，直接进 4.3（用户不同意可随时叫停）。
5. **候选 =0** → 如实告知该节无模板无样例，选项：「按常规写法直接写 / 换一节 / 先停一下」。

### 4.3 卡3 · 补全卡（附正文组装建议；发卡即停）

1. **正文先给组装建议**（对话消息，非卡片）：该节如何从模板展开成段落——段落骨架（开头定性句 → 数据落点 → 预测/分析主体 → 措施/结论收尾）+ 插槽清单表：
   - 已自动填充：值 + 来源（知识库检索/对话上下文）+ 置信度；
   - 待你补充：插槽名 + 要什么数据 + 格式示例（示例只写在 question/正文，禁做进 options）。
2. **补全卡**：待补插槽**逐项自由文本问题**（不提供 options），每卡 ≤5 问，超出分多卡连发；
3. 用户回答后：插槽值注入模板 → 组装该节草稿 → `write_file` 落 `sections/<节号>.md` → 对话中全文呈现节稿。

### 4.4 卡4 · 确认卡（发卡即停；法定停车点）

- question：本节成稿已呈现并保存，怎么处理？
- options：「确认，写下一节〈下一节名〉」（推荐，首位）/「要改」（选后在自定义输入附修改意见）/「先停一下」。
- **确认** → 更新 progress.json → 回 4.1 推荐下一节；
- **要改** → 按意见重写该节（意见涉及换模板/换数据时回卡2/卡3，否则直接重写）→ 重呈 → 卡4 重发；同节返工不设硬上限，连续多轮无收敛则如实说明并请用户给方向；
- **暂停** → 呈进度一句话收尾，回合结束。

### 4.5 完成摘要

目标范围全部节 confirmed/skipped → 呈各节清单（节号/节名/状态/成稿文件）+ 一句话收尾，问「还有其他章要写吗 / 就到这里」。

### 4.6 已确认节的修订（显式受理）

用户点名改已确认节 → 列受影响范围（改插槽值时反查同名参数的其他已确认节，如实列出级联）→ 用户确认 → 改值/改写 → 重呈 → 卡4 重发 → progress.json 同步更新。禁静默拒绝，禁绕过确认直改成稿。

## 5. 数据源双轨

| 来源 | 内容 | 引用方式 |
|------|------|----------|
| **知识库**（主源） | 章节树（get_mindmap）、结构化段落模板（get_templates：泛化模板+插槽+原文引用+标准编码）、补充检索（query_kb） | 对话设置中已选 KB，现有工具链 |
| **coal-eia-writer 语料**（辅源，只读） | `samples_bank/` 真实报告切片、`paradigms/` 通用范式文档、`sample_entities/` 禁抄注册表 | 沙箱路径 `/home/gem/skills/coal-eia-writer/references/...`，read_file 直读 |

- 语料适用于煤矿环评领域；其他领域或路径不存在 → 自动降级 KB-only，如实说明一句，不阻塞流程。
- 语料检索方式 = 沙箱文件工具（目录列举用 execute 的 ls，读内容用 read_file），不为本技能新写任何脚本。
- **样例纪律**：样例切片**只学结构与写法，禁抄**——`sample_entities/` 注册表实体与范文数值禁入本项目正文；样例候选上卡面**先脱敏**（矿名/地名/企业名→占位、数值→占位化），溯源信息（报告名/文件名/路径）不上卡面；本项目数据一律来自知识库检索或用户补全。
- **检索参照轨**：结构化模板（get_templates）查无结果时，`query_kb` 以节主题词检索知识库相关段落，脱敏后作「知识库参照」候选，与样例参照同一套卡面纪律。

## 6. 工作区状态（跨会话）

```
/home/gem/user-data/workspace/template-writing/<报告名slug>/
  progress.json          # 进度唯一权威
  sections/<节号>.md     # 每节确认稿
```

`progress.json` schema：

```json
{
  "report_name": "...",
  "domain": "...",
  "report_type": "...",
  "kbs": ["..."],
  "sections": [
    {
      "key": "4.2",
      "title": "地表水环境影响预测",
      "path": ["第四章 环境影响预测", "4.2"],
      "status": "pending | confirmed | skipped",
      "template_source": "kb | sample | none",
      "template_summary": "采用的模板/样例一句话",
      "slots": {
        "<插槽名>": {"value": "...", "source": "user | kb:<KB名> | context", "confidence": "高 | 中 | 低"}
      },
      "draft": "sections/4.2.md"
    }
  ],
  "updated_at": "ISO 时间"
}
```

- 状态以文件为唯一权威；每节确认/跳过后立即写盘（write_file，若平台弹写审批属正常流程）。
- 恢复：开局读 progress.json 实际状态决定续写点，禁凭会话记忆推断进度。

## 7. 纪律继承（写入 SKILL.md 的硬约束）

1. **发卡即停**：每张卡发出后立即结束回合，禁同回合连发多卡等答案；补全槽位 >5 拆多张补全卡逐张收集时，每张仍是一次提问等待，同属卡3 环节。
2. **交互卡红线**：填写类数据项禁做成选择题；选项 2-5 个且必须真实枚举，禁示例占位文本；示例/格式说明只写在 question 文本。
3. **数据纪律**（继承 slot-filler）：禁编造——自动填充仅限高置信度且可溯源；中/低置信度一律进补全卡由用户确认；数值保留原始精度与单位；同名参数全书同值。
4. **样例纪律**：见 §5。
5. **进度纪律**：progress.json 唯一权威；会话记忆是回声。
6. **用户沟通规范**（全平台硬约束）：全中文业务语体；零机制词/路径/状态枚举/命令；每条播报类正文 ≤3 句；卡题面一句话讲清情境与后果，选项用动宾业务短语。

## 8. SKILL.md 结构草案

```
---
name: template-recommender
description: 逐节引导写作（高用户参与）：逐节推荐模板（交互卡自选）→ 组装建议与补数 → 确认成稿 → 自动推进下一节。
  触发：用户要逐节/边选边写/模板自己挑的报告编写；整本整章自动管线走 coal-eia-writer / coal-eia-chapter-writer。
version: "2026.11.09"
tool_dependencies: ["list_kbs", "get_mindmap", "query_kb", "get_templates", "list_report_types",
                    "list_chapter_keys", "ask_user_question", "present_artifacts",
                    "read_file", "write_file", "edit_file"]
skill_dependencies: []
---
# 逐节引导写作
## 角色与三模式分工
## 用户沟通规范
## 红线（数据/样例/交互/进度）
## 工作区布局
## 操作流程：开局定位 → 四卡循环 → 修订回环 → 完成摘要
## 卡片式样（各卡 question/options 构成）
```

## 9. 验收标准与 checklist

- [ ] SKILL.md 重写完成，frontmatter version `2026.11.09`，含三模式路由、四卡循环、双数据源、纪律六条
- [ ] slot-filler SKILL.md 仅 description + 开头一段更新为接管声明，正文协议未动
- [ ] tools.py `GET_TEMPLATES_DESCRIPTION` 更新，其余零改动
- [ ] `docs/develop-guides/changelog.md` 补记
- [ ] writer / chapter-writer 两目录字节零改动（git diff 核对）
- [ ] 运行栈落栈：api reseed 后 `skill-sources/shared` 跟上；admin 投影卷手动同步并 md5 核对本轮改动文件
- [ ] E2E 实测一轮完整四卡流：选节 → 选模板（≥2 候选呈文件卡）→ 补全（自由文本）→ 确认 → 自动推荐下一节
- [ ] E2E 实测恢复：新会话续写，进度从 progress.json 恢复且与文件一致
- [ ] E2E 实测降级：语料路径不可达时 KB-only 不阻塞、有如实说明
- [ ] E2E 实测样例候选：卡面脱敏（无矿名/报告名/数值原文），禁抄纪律在成稿中成立

## 10. 非目标

- 报告级整书组装/导出/交付（后续独立需求）；
- 前端真模态弹窗组件（本轮用对话内交互卡，模态弹窗如需另立项）；
- coal-eia-writer / coal-eia-chapter-writer 的任何改动；
- 语料跨领域泛化（语料仅煤矿环评，其他领域自动 KB-only）；
- 插槽计算/公式冻结等重管线能力（本技能数据一律来自检索或用户）。

## 11. 增补：卡面推荐项高亮渲染（2026-11-10）

用户实测反馈：提问卡选项只有标题、推荐项无视觉区分，无法快速定位推荐模板。考证结论：交互卡协议本就支持——选项 `label` 置首位且含 "(Recommended)" 时前端对推荐项高亮（HumanApprovalModal 标题主色加粗 / AskUserQuestionTool 药丸主色描边），选项 `description` 字段渲染为标题下方说明行（前后端归一化均透传）；缺口在触发标记仅认英文，而本技能沟通规范又禁英文标记，推荐项从未高亮。

- 前端（各一处条件）：高亮触发标记扩为 "(Recommended)" /「（推荐）」/ "(推荐)" 任一，向后兼容其他技能既有约定；
- tools.py：ASK_USER_QUESTION_DESCRIPTION 补 description 字段用法与推荐标记口径；
- SKILL.md：沟通规范 6 改为「推荐选项置首位 + 标题末尾加「（推荐）」（确有推荐倾向才标，禁每题都标）」；卡2 第 4 步选项构成改为「脱敏短标题 + description（来源/结构特点/约多少段）」。

**E2E 已验证（2026-11-10）**：服务端驱动真实 run（`backend/scripts/verify_card2_highlight.py`，agnes-3.0-flash）跑通开局卡→卡1→卡2，三卡推荐项均置首位带标记、候选说明行齐全；真实卡2 payload 挂真实 HumanApprovalModal 渲染高亮确认。附发现：模型偶发把 questions 数组字符串化传入（前端归一化已兼容）；卡2 第 4 步「候选超 4 份择优取前 4、其余如实说明」纪律在实测中成立。
