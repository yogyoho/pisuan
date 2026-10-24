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

### 9.2.1 真人对话冒烟（已完成，API 驱动 + web UI 真人应答）

驱动脚本：`.wolf/chapter-smoke/dialog/drive.py`（login/thread/send/poll/history/resume），agent=`agent-b8decd45b324`，model=openai2:agnes-3.0-flash（gemma-4-E4B 无法驱动技能管线：零工具调用+幻觉工具，已弃用本线程）。resume 协议：工具审批 `{"decisions":[...]}`；ask_user_question 应答为裸对象 `{question_id: value}`（question_id 缺省 q-1/q-2）。

已验证（对话面）：

| 项 | 结果 | 说明 |
|---|---|---|
| 工具审批停车+恢复 | ✅ | execute/write_file/edit_file 逐次停车；approve/reject+steer 均生效（reject 后模型按引导改用原命令重试） |
| 技能路由 | ✅ | 模型首读 chapter-writer SKILL.md，状态核对走 progress.py，未误入 full 管线 |
| 真实缺陷 bug-4136 | ✅ 已修 | 沙箱 python <3.12：f-string 表达式内 `\"` 反斜杠非法——`progress.py next` 在沙箱必炸（dev 容器 3.13 掩盖）。修法：FINAL 分支 precompute 到普通串再插值；仓库+孪生+栈三处同步，157 tests passed |
| 脏状态裁决 | ✅ | 旧 full 冒烟遗留 state（mode 缺省=full）+ ch2 已 VERIFIED——模型主动察觉并三选项询问；用户选 C：新建 `eia-report-hengcheng-ch`（init --mode chapter），隔离旧工程 |
| 门1 对话面 | ✅ | 复制的 state_manifest.json 指纹陈旧 → 模型用 ingest.register_file 重签（唯一写通道），复跑通过 |
| 公式定向执行 | ✅ | `formula_runner execute --chapters ch2` 冻结 scope：ch2 定性章，STATE_READY 确认（验收4 数据面） |
| 模板推荐卡（验收10） | ✅ | 3 份脱敏候选（实体/数值占位化）+ 推荐标注 + 选项卡；用户选 025-r 后按 3b 节级派发 |
| 数字纪律自检 | ✅ | 子代理正文硬写冻结数值（70km/1995年10月）被主线程查获 → 槽位化重写（{{SLOT}}/{{TABLE}}）；编号类（307/GZ25）与定性比例（1/6、1～3m）按规则保留，边界判断合理 |
| 节级机械修闭环（S01–S04） | ✅ | gate FAIL 清单驱动逐节修复：2.3.3 表引用错位、2.3.3/2.3.5/2.4.1/2.4.4 深度≥3句、表前句收束式改写；模型自行发现并 steer 修正一次错行（表2.4.1 误编号） |
| 真实缺陷 bug-4138 | ✅ 已修 | WRITER_CAP_RE 编号后缀单段量词匹配不了多级章号「表2.2-1」→ 表题全失格、表密度 0。模型沙箱自修+宿主 repo 两副本/回归测试（13 passed）/栈 skill-sources 三处同步 |
| 真实缺陷 bug-4139 | ✅ 已修 | 组装机发表号单级「表 2-N」与真实报告/写手引用多级「表2.2-N」错位；`_assign_table_numbers` 升级节感知（SECTION_HEAD_RE 取 #### 标题前两段，节内连续号），回归测试 2 例（15 passed），两副本+栈同步；模型曾欲删表题迁就被 reject+steer 纠偏 |
| 降档协商单（Iron Law 升级） | ✅ | 章级门三项缺口（7152/14599、32.0/36.2、60.3/71.3）触及结构性矛盾（数字纪律使叙述密度近乎不可达），模型拒绝机械堆字数、主动发 ask 卡升级；用户批 A（approve-downgrade）+ 仅 ch2 降档；`downgrade_approvals` 留痕含缺口数值与批准依据 |
| 章级审查（reviewer 入管线） | ✅ | 按 3d 规程 A 法规/B 导则/C 标准+D 行文四维只审不改；发现单 FAIL 1/WARN 4/PASS 3 + 移交 3（槽位口径误用、跨节表号错位、单表无解读等均为真问题），落盘 `outputs/ch2-合规审查.md`；用户裁决 accept 不返工 |
| 确认卡三选项应答（验收3） | ✅ | 14:14:58 用户在 web UI 应答 `{"q-1":"accept","q-2":"allow_partial"}`——真人真界面完成；但 ch2 停 DRAFTED，CONFIRMED 无法合法落盘（见下行设计缺口） |
| 章级状态机设计缺口 | 🆕 移交裁决 | chapter 模式获批准降档的章无 CONFIRMED 合法通道：`run_chapter_gate` 无降档感知（L2 FAIL 必 raise，gate PASS 是 VERIFIED 唯一通道）+ `confirm-chapter` 仅接受 REVIEWED + `downgrade_approvals` 只被全文 `finalize --allow-partial` 消费。模型未绕过未手改（唯一写者纪律守住了），收口呈报如实移交 |
| 文件清单呈报（验收1） | ⚠️ 口径待裁决 | 模型以 markdown 表格呈报终态文件清单（章稿 22.5KB/节稿×4/发现单/progress 留痕），未触发 UI 文件卡组件——「文件卡」验收口径（文本清单 vs 卡片渲染）留裁决 |
| 模型退化循环 | ⚠️ 观察项 | agnes-3.0-flash 在超长上下文尾部（约 40+ 工具轮后）输出 132,734 字符重复句退化，run 记 completed 但零推进；steer 收口指引（含正确键名 downgrade_approvals）后即正常收尾。长会话需防退化，必要时限时换轮 |
| 双通道并发 409 | ⚠️ 观察项 | drive.py resume 与 web UI 应答并发时互报「中断运行已被后续运行超越」（latest-run-wins 语义）；用户实际遇到并报告。多端同时驾驶同一线程需约定单通道，或 UI 侧对 409 提示刷新重试 |

**对话冒烟结论**：ch2 分章管线走完 选择卡→门1→模板推荐→4 节派发/机械修→章 gate（降档留痕）→章级审查→确认卡应答→收口呈报 全链；产出章稿（9821 字符，57 SLOT+10 TABLE 占位齐整）+ 发现单；发现交付缺陷 4 个（bug-4136~4139，均已修+测试）+ 设计缺口 1 个（降档收口通道，移交裁决）+ 模型/UX 观察项 2 个。验收 1/3/4/10 对话面完成（1 的「卡片」口径待裁决），2/5 前轮已验，11 留裁决。

## 9.3 reviewer 独立冒烟（已完成，发现单 v2）

发现单：`.wolf/reviewer-smoke/横城矿区总体规划（修编）环境影响报告书-合规审查.md`

- 方法：D/C 维度对 13 章原始切片机械全量实测（`style_targets._metrics` + 标准号正则 × standards_index）；A/B 条款定向 grep 取证。
- 结论：A 2 PASS/1 WARN（修编回顾无集中成节）；B 3 PASS；C WARN 14 项不在册（含 GB50359-2005 疑旧版年）；D FAIL 3 类——表密度下限 7 章（ch1/3/5/6/7/9/10）、数字密度 2 章（ch11/13）、AI 腔 6 处（总体而言×5 + 重要意义×1）；ch4/ch8/ch12 全带内。
- **方法修订（bug-4134）**：初版按 `## 数字` 头拆分重建合并稿丢表格密集块，ch4/ch5/ch6 数据失真——已推翻，以原始切片直测为准（bank 布局=每章每报告恰一文件，勿再拼拆）。

## 遗留

- 章级状态机降档收口缺口（9.2.1 🆕 行）：为批准降档章补合法 CONFIRMED 通道（gate 降档感知或 confirm-chapter 接受降档留痕），方案待裁决。
- 校准疑点：ch2 章地板 14599 按横城原报告全章校准，而 stage ch2 仅 4 节——style_targets 按 stage 节数折算地标的口径需专项核对（数字密度 36.2/千字 同源问题）。
- 「文件卡」验收口径（文本清单 vs UI 卡片组件）与 stage 白名单硬门（11）两项留裁决。
- 智能体模型现挂 openai2:agnes-3.0-flash（冒烟专用；gemma 无法驱动技能管线）——是否还原/固化待用户定。
- 运行栈滞后基线：pisuan-localized 指针停在 db86e752（Task 1 前），已删文件（如 paradigms/_roles.json）每轮 sync-dev 复发——官方链 `sync-upstream.ps1` 再生可根治。
