# 分章节环评写作与独立合规校验技能 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 `coal-eia-chapter-writer`（逐章交互写作管线）与 `coal-eia-reviewer`（语义合规+行文质量审查）两个新技能，及共享地基（六角色范式分型、文风门、章级冻结切片、CONFIRMED 态机、资产同步守卫）。

**Spec:** `docs/superpowers/specs/2026-10-24-chapter-writer-reviewer-design.md`（§3 管线 / §4 reviewer / §5.1 角色分型 / §7 十项验收）。

**Architecture:** 单一源 `coal-eia-writer/scripts/` + 共用 references；chapter-writer 包由项目根 `scripts/sync_chapter_skill.py` 生成（字节一致守卫单测）；reviewer 包最小（SKILL.md + checklist/index 副本同源同步）；投影层零改动。新代码全部落在技能包 `scripts/` 与 references，**不动 yuxi 平台核心**。

**Tech Stack:** 技能包 Python 脚本（pytest 单测随包 `scripts/tests/`）；SKILL.md 为 Markdown 契约；容器 `pisuan-localized-api-1`。

**执行约定（全程适用）：**
- 分支 `pisuan-custom` 直接开发；改动后 `powershell.exe -NoProfile -File scripts/sync-dev.ps1` 热同步（须先 `docker stop pisuan-localized-web-1`，跑完 `docker start`，瞬态锁用 `-Revert` 恢复）。
- 技能脚本测试在容器内跑：`MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/skill-sources/shared/coal-eia-writer/scripts/tests -q`（容器布局是 skill-sources/skill-projections，**无** /app/package 路径）；宿主跑需 temp-dir 拷贝模式（bug-4030 前车）。
- ruff：宿主 `python -m ruff check backend/package/yuxi/agents/skills/`；每 Task 提交前过。
- 提交信息中文 Conventional Commits，结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 严禁运行 `backend/test/integration/services/test_eia_lexicon_service_flow.py`（清空词表）。
- 一期 stage 仅 `planning_eia`；未启用 stage 的映射/基准文件不做（惰性生成，ABSENT 如实上报）。

---

### Task 1: 范式角色分型——roles 目录化 + conclusion/process 范式 + ch13 重新归型

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/paradigms/roles/planning_eia.json`（现有 `_roles.json` 77 节映射迁入 + ch13 十节按 conclusion 重归型）
- Create: `references/paradigms/conclusion.md`、`references/paradigms/process.md`（结构骨架/去实体化范文/反模式硬禁令/节尾收束段，格式对齐 `baseline.md`）
- Modify: `references/paradigms/_roles.json` → 删除（内容迁出后）
- Modify: `SKILL.md` 步骤 4.1 契约中 `references/paradigms/_roles.json` 路径 → `references/paradigms/roles/<stage>.json`（仅路径与查表说明，其余契约不动）
- Create: `scripts/tests/test_paradigm_roles.py`

- [x] **Step 1.1 (TDD 红)**：写 `test_paradigm_roles.py`——① `roles/<stage>.json` schema：`roles` 键值六合法值（opener/baseline/analysis/measures/conclusion/process）；② planning_eia 映射覆盖 stage sections 清单全部 77 节（读 `references/stages/planning_eia.json` 对账，多节少节都红）；③ ch13 全部节 ∈ {conclusion, measures}；④ 未知角色值断言抛错（查表函数对非法值拒派语义）。容器内跑确认红。
- [x] **Step 1.2**：迁映射——现 `_roles.json` 内容为基，ch13 按结论章语义重归（S01 总体结论/S03 环保措施结论→conclusion；S09 措施汇总类→measures；其余逐节语义判型并在 JSON `_comment` 记归型理由）。
- [x] **Step 1.3**：写 `conclusion.md`（结论先行/逐条溯源前章/禁新增实体与数值——EO3 语义化；范文从 samples_bank/planning_eia/slices/ch13/ 去实体化提取）与 `process.md`（程序合规叙事：公参过程/两轮公示/意见处理）。
- [x] **Step 1.4 (绿)**：容器内测试全绿；`grep -rn "_roles.json" backend/package/yuxi/agents/skills/` 仅剩新路径引用（或零引用）。

**Verify:** 容器 pytest 绿 + SKILL.md 路径更新 + `git grep _roles` 无残留。

### Task 2: style_targets 基准生成脚本

**Files:**
- Create: `scripts/style_targets.py`（从 `references/samples_bank/<stage>/slices/chN/` 实测生成 `references/style_targets/<stage>.json`；复用 compare 逻辑：数字/千字、表行/万字、均句长；基准=实测×0.8 下限 / ×1.25 上限；`fig_table_ref_min = max(1, 主要表格数×0.5)`；`banned_phrases` 常量表：总体而言/值得注意/至关重要/旨在/重要意义/换言之/毋庸置疑/不言而喻/众所周知/不难发现/进一步凸显）
- Create: `references/style_targets/planning_eia.json`（运行产物，横城 bank 播种）
- Create: `scripts/tests/test_style_targets.py`

- [x] **Step 2.1 (TDD 红)**：测试用 mini-bank fixture（两章各 2 切片）断言生成的 JSON 结构与数值（密度计算口径：正文剥表格/剥标记/剥空白）。**章目录对齐警告**：bank slices 章目录含碎片段（ch0/ch0101/ch1200/ch1600 等瑕疵目录名），生成时必须按 `references/stages/<stage>.json` 章清单对齐，不盲信目录名。
- [x] **Step 2.2**：实现生成脚本；CLI：`python style_targets.py --stage planning_eia --bank <bank_dir> --out <out_json>`。
- [x] **Step 2.3 (绿)**：测试绿后对真实 bank 生成 planning_eia 基准落盘；spot-check ch4 表密度下限 ≈ 85（实测 106×0.8）、ch13 表上限 ≈ 10（原文结论章近 0 表）。

**Verify:** 单测绿 + `references/style_targets/planning_eia.json` 在场且 ch1–ch13 全覆盖（bank 缺章记 ABSENT）。

### Task 3: chapgate 文风门（四规则 + banned_phrases 进残留扫描）

**Files:**
- Modify: `scripts/progress.py`（gate 章级判定追加文风四规则：数字密度下限/表密度区间/文表联动下限/AI 腔禁用词——读 `references/style_targets/<stage>.json`，缺文件=文风门 skip 如实上报）
- Modify: 残留扫描词表所在处（`build_output.py` 或 progress.py 内 bug-367 词表常量——先 `grep -n "总体而言\|元话语\|残留" scripts/*.py` 定位）并入 banned_phrases
- Create: `scripts/tests/test_style_gate.py`

- [x] **Step 3.1 (TDD 红)**：四规则各一通过/一失败 fixture（构造小章稿 md + style_targets fixture）：① 数字密度低于下限 FAIL；② 表行超上限 FAIL；③ 正文无「由表/见表/详见表」而主要表格 ≥2 FAIL；④ 含「总体而言」FAIL；⑤ 全过 PASS；⑥ style_targets ABSENT → 文风门 skip（gate 仍 rc=0 但 stdout 报 STYLE_GATE_SKIPPED）。
- [x] **Step 3.2**：实现 gate 集成；失败输出含节级归因（哪节/哪指标/实测 vs 基准）。
- [x] **Step 3.3 (绿)**：测试绿；对既有 writer 测试目录跑全量确认零回归。

**Verify:** `MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests -q` 全绿。

### Task 4: formula_runner 章级切片（--chapters scope）

**Files:**
- Modify: `scripts/formula_runner.py`（`execute` 增 `--chapters ch2,ch6`：按 `state/dependency_manifest.json` 取目标章节消费的公式子集冻结；跨章公式已冻结的不重算；不带参数=全量，行为不变）
- Create: `scripts/tests/test_formula_runner_scope.py`

- [x] **Step 4.1 (TDD 红)**：fixture manifest + 公式集：`--chapters ch2` 只冻结 ch2 消费公式，ch6 专属公式 formula_state 不出现；重复执行幂等；不带 `--chapters` 全量路径回归不破。
- [x] **Step 4.2**：实现 scope 过滤（消费=该章 sections 的 uses 并集；切片不准回退全量并在 stdout 报 SCOPE_FALLBACK——正确性优先）。
- [x] **Step 4.3 (绿)**：测试绿 + 既有 formula_runner 测试零回归。

**Verify:** 容器 pytest 全绿。

### Task 5: data_expectations global_families 派生 + corpus_meta variant 字段

**Files:**
- Modify: `references/data_expectations.json`（顶层增 `global_families`：由 build 逻辑派生——跨 ≥2 章 per_chapter 出现的族 ∪ 冻结依赖族；不手拍）
- Modify: `scripts/progress.py` 或新 `scripts/derive_globals.py`（派生函数 + `ingest.py check --global-only` 语义：门1 全局包模式只校 global_families）
- Modify: `references/samples_bank/corpus_meta.json`（增 `variant` 字段：planning 17 份即标 13 修编/3 新编；标题空缺的 11 份 project/post 记 `needs_review`；带 `variant_basis`）
- Create: `scripts/tests/test_global_families.py`

- [x] **Step 5.1 (TDD 红)**：fixture expectations（3 章小样）断言派生：族出现在 ≥2 章 → global；单章族不进。
- [x] **Step 5.2**：实现派生 + 门1 全局模式开关；对真实 planning_eia 派生并落盘（预期 4~5 族，与 spec 预估比对，偏差记 `_comment`）。
- [x] **Step 5.3 (绿)**：测试绿。
- [x] **Step 5.4**：corpus_meta variant 落盘（脚本改写保持 JSON 其余字段零扰动；planning 标题即判：含「修编」→revision，不含→new）。
- [x] **Step 5.5**：needs_review 的 11 份标注补齐——LLM 读各报告 ch1/ch2 切片首段判「新建/改扩建（含调整规模）/不适用」初值 + 呈用户确认后回写；确认前不落终值。

**Verify:** 单测绿 + `data_expectations.json` global_families 在场 + corpus_meta 全部 33 份带 variant（或 needs_review）。

### Task 6: progress.py CONFIRMED 态机 + 分章编排

**Files:**
- Modify: `scripts/progress.py`（章状态增 `CONFIRMED`：`confirm-chapter chN` 命令；`next` 分章模式输出序：COLLECTING→模板推荐→派发→gate→review→确认卡→下一章；key_points 增量：`confirm-chapter` 时把本章 highlights 并入 `state/key_points.json`；恢复检测认 CONFIRMED 跳过前序）
- Create: `scripts/tests/test_chapter_state_machine.py`

- [x] **Step 6.1 (TDD 红)**：状态机测试：PENDING→…→VERIFIED→REVIEWED→CONFIRMED 全链；CONFIRMED 章 next 跳过；BLOCKED 不阻后续章；key_points 增量合并幂等。
- [x] **Step 6.2**：实现（`init --mode chapter` 区分分章模式，默认 full 保持现行为零变化）。
- [x] **Step 6.3 (绿)**：测试绿 + writer 现有 progress 测试零回归。

**Verify:** 容器 pytest 全绿（重点：`--mode full` 默认路径字节级不变）。

### Task 7: chapter-writer SKILL.md + 资产同步守卫

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/SKILL.md`（按 spec §3 全文展开：步骤 0–7 契约、A2 全局包、3a-2 模板推荐、3a–3f 逐章循环、文风门/审查接入点、确认卡与停车契约、Iron Law 继承+guidance 改写（缺陷#3：只写补写节稿/申请降档两条合法出路））
- Create: `scripts/sync_chapter_skill.py`（项目根：coal-eia-writer 的 scripts/+共用 references 单向覆盖到 chapter-writer 包；排除 chapter-writer 专属 SKILL.md）
- Create: `backend/package/yuxi/agents/skills/buildin/coal-eia-chapter-writer/scripts/`、`references/`（同步产物）
- Create: `backend/test/unit/skills/test_chapter_skill_assets_sync.py`（宿主可收集路径——放 backend/test 下，勿放技能包内）

- [ ] **Step 7.1**：写 SKILL.md（骨架照 coal-eia-writer 分节：角色/红线/工作区/管线步骤/预算停车/命令速查/能力边界；交互纪律全套继承；3a-2 与 3e 两处发卡即停显式写明；**开题两级路由选择卡**（stage 拒未启用 + 变体问法按 stage 分派，spec §3.2））。
- [ ] **Step 7.2**：写同步脚本并执行生成 chapter-writer 包资产。
- [ ] **Step 7.3 (TDD)**：守卫测试断言两包共用文件字节一致（hash 清单比对）；人为改一处跑红再恢复。
- [ ] **Step 7.4**：`python -c "import ast; ast.parse(...)"` 语法过 + ruff 过 + 提交。

**Verify:** 守卫测试绿 + chapter-writer 包结构完整（SKILL.md + scripts + references）。

### Task 8: reviewer SKILL.md + 接入点

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/coal-eia-reviewer/SKILL.md`（审查规程：输入输出契约（--chapter/--full、`{报告名}-合规审查.md` 发现单格式 `[PASS/WARN/FAIL] 条目|定位|证据摘录|修复建议`）、四维度判定标准（A 法规/B 导则/C 标准（standards_index 在册机械先跑）/D 行文质量（复用章门统计值+段落逻辑抽查））、FAIL 须证据纪律、只审不改、独立可用说明）
- Create: `coal-eia-reviewer/references/compliance_checklist.md`、`standards_index.json`（从 writer 包同步，纳入 sync_chapter_skill.py 清单）
- Modify: `coal-eia-writer/SKILL.md` 步骤 5–7（终验接入一句：「全书一致性 PASS 后按 coal-eia-reviewer 规程执行全文审查，发现单作为 QA 副产物交付，管线元数据/告警禁入报告正文」——缺陷#6 解）
- Modify: `coal-eia-chapter-writer/SKILL.md`（3d/全文步骤引 reviewer 规程——Task 7 已含则此处校对）

- [ ] **Step 8.1**：写 reviewer SKILL.md。
- [ ] **Step 8.2**：同步清单扩展 + 守卫测试覆盖 reviewer 副本。
- [ ] **Step 8.3**：writer SKILL.md 接入句 + 全文 grep 校对两处引用一致。

**Verify:** 守卫测试绿；两 SKILL.md 对 reviewer 的引用路径存在。

### Task 9: 横城 ch2 端到端冒烟 + reviewer 独立冒烟（验收 §7）

**Files:** 无新增（验收执行 + 缺陷记录）

- [ ] **Step 9.1**：预配置智能体（管理端）挂载三技能（coal-eia-writer/chapter-writer/reviewer）——手动配置步骤，留截图/说明。
- [ ] **Step 9.2**：分章冒烟：横城 5 份资料走 chapter-writer——验收 1（ch2 文件卡片）/2（门1 只查全局包）/3（确认卡三选项+返工）/4（增量冻结 scope 日志）/5（文风门判定输出）/10（模板推荐链路含跳过路径）/11（stage 拒未启用+修编变体过滤）。
- [ ] **Step 9.3**：reviewer 独立冒烟：对横城原文 `--full` 产出发现单——验收 7。
- [ ] **Step 9.4**：缺陷即发现即记 buglog；验收结果汇总回填本计划 checkbox 并汇报。

**Verify:** 十项验收中 1/2/3/4/5/7/10 实测通过；6/8/9 由前序 Task 单测+冒烟覆盖确认。
