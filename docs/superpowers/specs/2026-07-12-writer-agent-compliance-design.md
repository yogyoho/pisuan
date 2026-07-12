# 写作侧 Agent 合规性（P0）— design

> 子项目 2（写作侧确定性骨架）的收尾。骨架（report 3 张表 / `{{REF}}` resolver / `assemble_report` / chapter-writer 子 agent）逐工具已验证可用，但 LLM 在真实运行中**绕过了 report-DB 骨干**。本 spec 解决"agent 有工具却走捷径"的合规性问题。承接 [2026-07-11-writing-backbone-design.md](./2026-07-11-writing-backbone-design.md)。

## 1. 背景与动机（取证）

2026-07-12 对线程 `ad3d19dc-1de6-40b2-9f25-9b35a19d37af`（用户请求"编写环评报告第5章 矿区开发环境影响回顾性评价"，单章点请求）的 `tool_calls` 取证：

- **编排者（conv 30）做对的**：读 SKILL.md → `list_kbs` → `get_chapter_outline` / `get_templates` / `query_kb` → `task` 派发 chapter-writer 子 agent → `present_artifacts`。编排形状正确，KB 桥工作正常。
- **编排者没做的**：从未调 `create_report` / `save_chapter` / `assemble_report` / `get_report` / `set_pps_param`；且在派发指令里明确写"本章最终需要输出为完整的 docx/文本格式文件，保存到 outputs/"——**主动把"写文件"作为输出契约下发给子 agent**。
- **chapter-writer 子 agent（conv 31）**：随之 `write_file` 写 `第5章_矿区开发环境影响回顾性评价.md`，也未调任何 report-DB 工具。
- 全程两层 agent 对 5 个 report-DB 工具调用次数 = **0**。`report_type` 还传错（`"eia"` 而非 `"eia_report"`）。

**判读**：SKILL.md 已写"⚠️ 必须用 `save_chapter`，不要用 `write_file` 绕过"，agent 读到了仍绕过、并把绕过传染给子 agent。这是典型的"模型最强先验（产出文件 → present 文件）压过 prose 指令"。**仅靠更强 prompt 不足以根治**——证据是现有 prompt 已足够明确仍被绕过。

## 2. 范围

| | 内容 |
|---|---|
| **本版** | **B1**（chapter-writer 收窄 `write_file`）+ **C3**（`save_chapter` 产出预览文件）+ **A**（SKILL.md / chapter-writer prompt 收敛） |
| **不在本版** | 禁 `execute`（YAGNI，先看禁 `write_file` 是否足够）；附件落盘通道；B2（`present_artifacts` 拒裸文件）/ B3（write_file 拦截 middleware）；`report_type` DB code 的强校验（仅 prompt 提醒） |

## 3. 核心决策

1. **B1 — 系统级强制**：chapter-writer 子 agent 的工具集移除 `write_file`，让 `save_chapter` 成为章节正文唯一存档出口。断掉最自然的捷径。
2. **C3 — 对齐先验**：`save_chapter` 顺带产出可预览文件 + 返回 `preview_path`，让 agent"产出文件 → present"的本能在**正确工具内**被满足，而不是对抗它。
3. **A — prompt 伴随**：SKILL.md 清除诱导写文件的措辞、把 `save_chapter` 钉到显眼位置；chapter-writer system prompt 钉死"正文唯一出口是 `save_chapter`"。
4. **Q3 决议**：B1 附加禁用集 = `{write_file}`，**保留 `execute`**。理由：`execute` 绕过（`printf > file.md`）对模型不自然，自发送概率远低于 `write_file`，禁 `write_file` 已收绝大部分收益；保留 `execute` 避免误伤未来正当命令需求。若重放仍见 `execute` 绕过，再纳入。

## 4. B1 详细设计

**现状**（`backend/package/yuxi/agents/buildin/subagent/graph.py`）：
- `_SUBAGENT_DISABLED_TOOLS = frozenset({"present_artifacts", "ask_user_question", "install_skill"})` —— **全局**，对所有子 agent 生效。
- `_SubAgentToolFilterMiddleware`（每次模型调用）+ `get_graph` 构建期都调 `_filter_disabled_tools`。
- `write_file` / `execute` 由 `create_agent_filesystem_middleware`（sandbox backend）注入，**不受 `context.tools` 控制**——所以不能靠 agent 工具配置移除，必须在 filter 层动手。

**改动**：
- `_filter_disabled_tools` 增加**按 slug 的附加禁用集**：chapter-writer slug → 附加 `{write_file}`。
- 实现方式（planning 阶段定细节，优先 (a)）：
  - (a) `_SubAgentToolFilterMiddleware` 从 runtime context 读 `agent_slug`，命中 `chapter-writer` 时合并附加禁用集 —— 与现有 slug 机制一致，最小侵入。
  - (b) `SubAgentContext` 带 `extra_disabled_tools` 字段，由 chapter-writer agent 配置注入。
- `_SubAgentToolFilterMiddleware.awrap_model_call` 与 `get_graph`（构建期）**两处都要生效**：构建期注册进 ToolNode 决定可执行性，运行期 filter 决定模型可见性。

**边界**：只影响 chapter-writer，不动其它子 agent；保留 `execute`（见 Q3 决议）。

## 5. C3 详细设计

**现状**（`backend/package/yuxi/agents/toolkits/buildin/tools.py`）：
- `save_chapter(report_id, canonical_chapter_key, title, content_md, summary, status)` —— 无 `runtime`，不写沙箱。
- `assemble_report` 经 `_write_assembled_to_sandbox(runtime_context, report_id, markdown)` 写 `report_{report_id}.md` 到 `sandbox_outputs_dir(thread_id)`。

**改动**：
- `save_chapter` 签名加 `runtime: ToolRuntime`（与 `assemble_report` 一致）。
- 存完 DB 后，复用 `sandbox_outputs_dir` 写预览文件 `chapter_preview_{report_id}_{canonical_chapter_key}.md`，返回值加 `preview_path`。
- **DB 仍是唯一真相源**：`content_md` 照常入 `domain_factory_report_chapters`；预览文件只是"即看"用，文件名带 `preview_` 前缀以区别于 `assemble_report` 的成稿 `report_{id}.md`。
- **单章交付链**：chapter-writer `save_chapter` → 返 `preview_path` → 编排者 `present_artifacts(preview_path)`。`assemble_report` 留给"整报告成稿"场景。

**实现注意**：`_write_assembled_to_sandbox` 当前写死 `report_{report_id}.md`，抽一个通用 `_write_md_to_sandbox(runtime_context, filename, markdown)` 给 `save_chapter` / `assemble_report` 复用（surgical，不破坏 assemble 现有行为与文件名）。

## 6. A 详细设计

- **SKILL.md**（`backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`）：
  - 删"输出为 docx/文本格式文件保存到 outputs/"等诱导写文件的措辞——**重点复核第四步"逐章写作"的派发指令模板**，把"写 markdown 正文 … save_chapter 存档"改为明确"save_chapter 存档并返回 preview_path；编排者用 preview_path 做 present_artifacts"，不再出现"子 agent 写文件交付"。
  - `report_type="eia_report"` 警告框保持显眼（这次传成了 `"eia"`）。
- **chapter-writer system prompt**（`ensure_chapter_writer_subagent` 注册的 agent 配置）：钉死"正文唯一出口是 `save_chapter`；你没有 `write_file`；`save_chapter` 返回的 `preview_path` 即本章交付物"。

## 7. 测试与验收

- **B1 单测**：chapter-writer slug 解析出的工具集断言**不含 `write_file`**（含 `execute`、含 `save_chapter`）；其它子 agent slug 仍含 `write_file`。
- **C3 单测**（扩 `test/unit/toolkits/test_report_tools.py::test_save_chapter_tool`）：断言返回 `preview_path`、预览文件落盘、DB `content_md` 仍持久（真相源不变）。
- **A**：prompt 驱动，manual 验证（按既有 spec 惯例，prompt 难单测）。
- **端到端验收（强靶子）**：**重放**"编写环评报告第5章 矿区开发环境影响回顾性评价"，断言 `tool_calls` 链出现 `create_report` → `save_chapter`（返回含 `preview_path`）→ `present_artifacts`；**无 `write_file` 写章节正文**；`domain_factory_report_chapters` 出现对应行。

## 8. 非目标

- 禁 `execute`（观察重放结果后再定）。
- 附件（图表/大表）落盘通道（YAGNI，当前 failing 场景不涉及）。
- B2（`present_artifacts` 拒裸文件）/ B3（write_file 拦截 middleware）—— 等 B1+C3 效果评估后再决定是否需要。
- `report_type` DB code 强校验（本版仅 prompt 提醒）。
