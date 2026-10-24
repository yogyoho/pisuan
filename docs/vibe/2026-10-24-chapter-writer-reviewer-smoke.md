# 分章写作 + 独立合规审查 冒烟记录（Task 9）

> 计划：`docs/superpowers/plans/2026-10-24-chapter-writer-reviewer.md` Task 9
> 日期：2026-10-24 ｜ 运行栈：pisuan-localized（api 5050 / web 5173）

## 9.1 预配置智能体挂载三技能（已完成，API 实测）

两个前置动作（新技能包进运行栈必做，官方链重建后仅需重跑一次）：

1. **同步代码进栈**：`docker stop pisuan-localized-web-1` → `.\scripts\sync-dev.ps1` → `docker start pisuan-localized-web-1`（reviewer 包随 backend/package 进容器 /app/package）。
2. **触发内置技能同步**：新增 buildin 包不会自动注册——热重载不重跑 `init_builtin_skills`。两条通道任选：
   - 管理端：Skills 管理页「同步内置技能」按钮（`POST /api/system/skills/builtin/sync`，superadmin）；
   - 容器直调（本次采用）：`docker exec pisuan-localized-api-1 python -c "...init_builtin_skills(db)..."`。

3. **挂载**：管理端智能体「环评写作助手」（slug `agent-b8decd45b324`）→ 技能勾选三件套。本次经 `PUT /api/agent/agent-b8decd45b324`（body 只带 `config_json`）把 `context.skills` 置为 `["coal-eia-writer", "coal-eia-chapter-writer", "coal-eia-reviewer"]`，model/tools/subagents/knowledges 原样未动。DB 与 skill-sources 双验证通过。

**观察点（留裁决）**：该智能体 system_prompt 写死「严格按 coal-eia-writer 管线执行」——分章/审查请求靠技能 description 触发词路由，prompt 措辞可能偏置分派；真实对话冒烟时观察，必要时改为「按用户请求在三技能间路由」。

## 9.2 分章冒烟（CLI 可证部分完成；对话级留真实会话）

CLI 证据（transcript：`.wolf/chapter-smoke/transcript.txt`，全部真实 planning_eia 数据）：

| 验收点 | 结果 | 证据 |
|---|---|---|
| 2 门1 只查全局包 | ✅ | `ingest.py check --global-only` 报 6 个全局族缺失清单（mine_plan/subsidence_params/water/air/noise/solid_waste），SUMMARY missing_forms=6，收集语义 rc=0 |
| 3 确认卡守卫（CLI 半边） | ✅ | `mark ch1 CONFIRMED` 拒+指引 confirm-chapter；`confirm-chapter ch1`（未 REVIEWED）拒+声明合法路径；节批量 REVIEWED 拒（章级专属） |
| 5 文风门判定输出 | ✅ | 横城原报告 ch2 切片 × planning_eia 基准 → FAIL：AI 腔「总体而言」（节 2.4.1 归因）——与 9.3 reviewer 独立发现交叉印证 |
| 11 stage 拒未启用 | ⚠️ 对话契约 | CLI 层无硬门：`init --stage post_eia.json` 物理文件在、init 照常成功；「拒未启用」由 SKILL.md 路由选择卡（LLM 层）承担。是否给 CLI 加 stage 白名单硬门→留裁决 |
| 11 修编变体过滤 | ✅（数据面） | corpus_meta 17 份 planning variant 字段 Task 5 已落盘验收；路由问法属对话层 |
| 1 文件卡片 / 3 确认卡三选项应答 / 10 模板推荐卡 | ⏳ 真人会话 | 属 agent 对话交互产物，CLI 无法替代；runbook：管理员登录 → 环评写作助手 → 「分章编写横城矿区规划环评，只写 ch2」→ 走 完选择卡→门1→派发→gate→review→确认卡 |

CLI 注意：`progress.py init --stage` 收 **stage JSON 文件路径**（`references/stages/planning_eia.json`），非 stage 名。

## 9.3 reviewer 独立冒烟（已完成，发现单 v2）

发现单：`.wolf/reviewer-smoke/横城矿区总体规划（修编）环境影响报告书-合规审查.md`

- 方法：D/C 维度对 13 章原始切片机械全量实测（`style_targets._metrics` + 标准号正则 × standards_index）；A/B 条款定向 grep 取证。
- 结论：A 2 PASS/1 WARN（修编回顾无集中成节）；B 3 PASS；C WARN 14 项不在册（含 GB50359-2005 疑旧版年）；D FAIL 3 类——表密度下限 7 章（ch1/3/5/6/7/9/10）、数字密度 2 章（ch11/13）、AI 腔 6 处（总体而言×5 + 重要意义×1）；ch4/ch8/ch12 全带内。
- **方法修订（bug-4134）**：初版按 `## 数字` 头拆分重建合并稿丢表格密集块，ch4/ch5/ch6 数据失真——已推翻，以原始切片直测为准（bank 布局=每章每报告恰一文件，勿再拼拆）。

## 遗留

- 真人对话冒烟（9.2 runbook 上表⏳行）需用户参与，确认卡为天然停车点。
- 运行栈滞后基线：pisuan-localized 指针停在 db86e752（Task 1 前），已删文件（如 paradigms/_roles.json）每轮 sync-dev 复发——官方链 `sync-upstream.ps1` 再生可根治。
