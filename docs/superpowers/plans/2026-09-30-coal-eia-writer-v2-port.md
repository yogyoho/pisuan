# coal-eia-writer 管线化 v2 移植实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `C:\Users\Lenovo\Downloads\coal-eia-report`（管线化 v2）忠实移植进 pisuan 的 `coal-eia-writer` skill，端到端跑通 planning_eia stage 并以合成项目验收。

**Architecture:** slug 原地替换（references/scripts 原样搬运，SKILL.md 按映射表改编）；编排者 DB agent（`agent-b8decd45b324`）切到新工具面 + 通用子代理 `eia-section-writer`；交付走独立路径（单文件）；验收 = 容器内静态门禁预检 + 真实对话 E2E。

**Tech Stack:** Git Bash（POSIX）、Docker（pisuan-localized-* 容器族）、PostgreSQL（pisuan-localized-postgres-1 / yuxi_know）、Python 3.12+（脚本纯标准库）。

**Spec:** `docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md`（决策与映射表以 spec 为准）

**分支约定:** 按项目惯例直接在 `pisuan-custom` 分支执行，不另建 worktree。

**关键环境事实（已核实，执行时勿再猜）:**
- 运行栈容器名：`pisuan-localized-api-1` / `pisuan-localized-worker-1` / `pisuan-localized-postgres-1`（不是 api-dev/worker-dev）
- 代码进运行栈：宿主机改 `C:\workspace\pisuan` 后跑 `.\scripts\sync-dev.ps1` 同步到 `C:\workspace\pisuan-localized`（容器挂载的是后者）
- api 容器内技能路径：`/app/package/yuxi/agents/skills/buildin/coal-eia-writer`
- 沙箱虚拟路径：技能=`/home/gem/skills/coal-eia-writer`，工作区根=`/home/gem/user-data`
- DB：`docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know`
- 编排者 agent：slug=`agent-b8decd45b324`（id=9，name=环评写作助手），现 config 见 Task 4
- 克隆模板行：`regulation-writer`（id=10，backend_id=`SubAgentBackend`）
- planning_eia 数据族：33 个（`references/stages/planning_eia.json` 的 `forms` 键）

---

### Task 1: 资产搬运（references/scripts 原样覆盖，删 outlines）

**Files:**
- Create/Overwrite: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/**`（来自下载包）
- Create/Overwrite: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/**`（来自下载包）
- Delete: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/outlines/`（13 个文件）
- Overwrite: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`（Task 2 改编，本任务先原样放入）

注意：本任务**不提交**——与 Task 2 合并为一个提交（spec §7.3 回滚单元）。

- [ ] **Step 1.1: 确认 git 工作区状态符合预期**

```bash
cd /c/workspace/pisuan && git status --short backend/package/yuxi/agents/skills/buildin/coal-eia-writer/
```
Expected: 全部为 ` D`（未暂存删除）——用户已于 2026-09-30 会话中手动删除旧 `coal-eia-writer/` 目录（31 文件，未暂存，`git checkout -- <dir>` 可恢复；另有 `coal-eia-writer.rar` 备份）。若出现 ` M`/`??` 等其他状态行，先与用户确认再继续。

- [ ] **Step 1.2: 整目录替换为下载包内容**

```bash
SRC="/c/Users/Lenovo/Downloads/coal-eia-report"
DST="/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-writer"
rm -rf "$DST"
mkdir -p "$DST"
cp "$SRC/SKILL.md" "$DST/SKILL.md"
cp -r "$SRC/references" "$DST/references"
cp -r "$SRC/scripts" "$DST/scripts"
find "$DST" -type d \( -name "__pycache__" -o -name ".pytest_cache" \) -exec rm -rf {} +
```
说明：`rm -rf` 删除的 outlines/ 与旧 references/scripts 都在 git 历史中，可恢复；`*.rar` 在 buildin/ 层不在本目录，不受影响。

- [ ] **Step 1.3: 文件清单对账（与下载包逐文件 diff）**

```bash
SRC="/c/Users/Lenovo/Downloads/coal-eia-report"
DST="/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-writer"
diff <(cd "$SRC" && find . -type f ! -path "*__pycache__*" ! -path "*.pytest_cache*" | sort) \
     <(cd "$DST" && find . -type f | sort)
```
Expected: 无输出（完全一致），退出码 0。

- [ ] **Step 1.4: 全部脚本语法冒烟（宿主机 python，覆盖风险 R1/R5 的静态面）**

```bash
python - <<'EOF'
import ast, pathlib
root = pathlib.Path(r"C:/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts")
files = sorted(root.rglob("*.py"))
assert files, "no scripts found"
for f in files:
    ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
print(f"OK {len(files)} scripts parsed")
EOF
```
Expected: `OK N scripts parsed`（N 应为 15 个左右：12 个顶层脚本 + calc/5 个 - tests 除外，以实际为准；>0 即可）。

- [ ] **Step 1.5: 确认代码库无 outlines/ 的硬引用**

```bash
cd /c/workspace/pisuan && grep -rn "outlines/" backend/package/yuxi --include="*.py" | grep -v __pycache__
```
Expected: 无 coal-eia-writer/outlines 相关输出（BUILTIN_SKILLS 注册是目录扫描制 `services/skills/shared.py:484`，无显式清单）。若有输出，停下评估再继续。

---

### Task 2: SKILL.md 改编（映射表逐项落地）

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`

改编原则（spec §4.4）：映射表之外的文字逐字保留。以下 Edit 若因原文空白差异匹配失败，先 Read 目标区段，以实际文件文本为准重试。

- [ ] **Step 2.1: 全局路径与工具名替换（sed 一次完成）**

```bash
DST="/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-writer"
sed -i \
  -e 's|/mnt/skills/public/coal-eia-report|/home/gem/skills/coal-eia-writer|g' \
  -e 's|/mnt/user-data|/home/gem/user-data|g' \
  -e 's|ask_clarification|ask_user_question|g' \
  -e 's|present_files|present_artifacts|g' \
  -e 's|knowledge_search|query_kb|g' \
  "$DST/SKILL.md"
grep -c "/mnt/" "$DST/SKILL.md" || true
```
Expected: `grep -c` 输出 `0`（grep 无匹配时退出码非 0，`|| true` 防中断）。

- [ ] **Step 2.2: frontmatter 替换**

old_string（文件开头到第一个 `---` 之后）:
```yaml
---
name: coal-eia-report
description: >
  煤矿环境影响评价报告书编写技能（管线化 v2）。触发匹配（bug-2234 同构）：凡用户要求编写/
  编制/生成/撰写矿区总体规划环境影响报告书（规划环评）、矿井/露天矿建设项目环境影响报告书
  （项目环评）、环评报告书、环境影响评价报告、环评章节（如地表沉陷预测/环境承载力分析）——
  不限矿区/矿井、不限地区、不限新建/改扩建/修编——必须立即加载本技能并严格按其管线执行，
  不得即兴自创问卷、表单、章集或输出格式。stage 选择：planning_eia=矿区总体规划环评 /
  project_eia_underground=井工矿建设项目环评（openpit / post_eia 二期立项）。依据 HJ 130、
  HJ 463、HJ 2.1–2.4 系列；数字永不经过 LLM，正文只写 {{SLOT:key}}/{{TABLE:族}} 由脚本注入。
license: MIT
# NOTE: allowed-tools removed 2026-09-06. Declaring allowed-tools on ANY enabled skill
# makes skills/tool_policy.py treat it as a GLOBAL agent-wide whitelist (union across all
# enabled skills), stripping every other tool incl. MCP tools (e.g. knowledge-factory_kf_*).
# That starved the whole agent to 6 built-in tools and broke knowledge-factory-dependent
# skills (bug-186). Do NOT re-add allowed-tools here until that filter is scoped to the
# active skill.
---
```
new_string:
```yaml
---
name: coal-eia-writer
description: >
  煤矿环境影响评价报告书编写技能（管线化 v2）。触发匹配（bug-2234 同构）：凡用户要求编写/
  编制/生成/撰写矿区总体规划环境影响报告书（规划环评）、矿井/露天矿建设项目环境影响报告书
  （项目环评）、环评报告书、环境影响评价报告、环评章节（如地表沉陷预测/环境承载力分析）——
  不限矿区/矿井、不限地区、不限新建/改扩建/修编——必须立即加载本技能并严格按其管线执行，
  不得即兴自创问卷、表单、章集或输出格式。stage 选择：planning_eia=矿区总体规划环评 /
  project_eia_underground=井工矿建设项目环评（openpit / post_eia 二期立项）。依据 HJ 130、
  HJ 463、HJ 2.1–2.4 系列；数字永不经过 LLM，正文只写 {{SLOT:key}}/{{TABLE:族}} 由脚本注入。
version: "2026.09.30"
tool_dependencies: ["ask_user_question", "present_artifacts", "list_kbs", "query_kb", "list_report_types", "get_templates"]
# pisuan 移植（2026-09-30）：运行时映射与改编范围见
# docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md §4。
# 原 allowed-tools NOTE 不适用本平台，删除；license: MIT 移除（平台 frontmatter 不使用）。
---
```

- [ ] **Step 2.3: 步骤 1 三件套——KF resolve 工具替换**

old_string:
```
   **开题首动作三件套（bug-2231/3066 页面实测纪律全套移植：开题第一轮一轮做完，不可拆分、不可只说不做）**——按序完成：① **真实调用** KF MCP `kf_resolve_template`（工具全名 `knowledge-factory_kf_resolve_template`，与用户是否已给阶段无关），必须在本回复留下实际工具调用记录——口头声称"已解析 / found=false"而未调用 = 未做（工具不可用或调用失败视同 `found=false`，进 ②；**`found=false` 且 `reason=missing_keywords` 时须按工具 suggestion 补 `domain_keywords`（如 `["环境影响评价","环评","煤炭",<矿区总体规划|建设项目>]`）重试 ≤1 次，仍 false 才兜底**——bug-3066：该工具硬性要求 domain_keywords，缺参时连模板库都不查即返回 false）；② `found=false` 时向用户声明：
```
new_string:
```
   **开题首动作三件套（bug-2231/3066 页面实测纪律全套移植：开题第一轮一轮做完，不可拆分、不可只说不做）**——按序完成：① **真实调用** `list_report_types`（辅以 `get_templates`）查询本机知识工厂是否已有可用报告模板（与用户是否已给阶段无关），必须在本回复留下实际工具调用记录——口头声称"已解析 / found=false"而未调用 = 未做（工具不可用或调用失败视同 `found=false`，进 ②）；② `found=false` 时向用户声明：
```

- [ ] **Step 2.4: 「用户可见即表单」——字段制改问题制**

old_string:
```
   - **用户可见即表单**：`fields` 渲染中文填写表单，`name`=schema 英文键（内部）、`label`=中文名+单位，enum→select / number→number / 长文本→textarea；**单卡片 ≤16 项**，超出分批问；面向用户一律称"数据项"，禁出现「JSON/字段/field」术语。
```
new_string:
```
   - **用户可见即表单**：`ask_user_question` 问题制卡片（1–5 问/卡），`question_id`=schema 英文键（内部）、`question` 文本=中文名+单位+填写说明（label+placeholder 合并），enum→options / 其余→自由文本填写（数值合法性由 `ingest.py` 落盘校验，rc=1 拒后译中文重问）；**单卡片 ≤5 项（平台上限）**，一份数据族分多卡，跨回合仍一回合至多一卡；面向用户一律称"数据项"，禁出现「JSON/字段/field」术语。
```

- [ ] **Step 2.5: bug-3233 反模式禁令转译**

old_string:
```
   - **字段构造反模式禁令（bug-3233）**：`label`/`placeholder` 必须纯中文文本（禁塞 JSON/字典/对象字符串）；`type=number` 字段禁建成 select-options 形态（{label,value} 字典即违规，渲染即成「JSON 当标签」）；`label` 与 `placeholder` 禁同文重复。
```
new_string:
```
   - **字段构造反模式禁令（bug-3233）**：`question`/`options` 的文本必须纯中文（禁塞 JSON/字典/对象字符串）；数值数据项禁做成选择题形态（一律自由文本填写，校验交给 ingest）；同一数据项的填写说明禁在多卡间重复粘贴冗余文本。
```

- [ ] **Step 2.6: 步骤 4 控制器——batch_task 改 subagent_start**

old_string:
```
主会话是**控制器**：薄上下文，只协调——读进度、分波派节、跑门、记账，**不亲自写节**。节稿写作全部走子代理派发——`batch_task` 优先（波=一章的全部 PENDING 节，items=各节派发契约），`task()` 兜底（单回合 ≤3 并发）。
```
new_string:
```
主会话是**控制器**：薄上下文，只协调——读进度、分波派节、跑门、记账，**不亲自写节**。节稿写作全部走子代理派发——`subagent_start`（`subagent_slug="eia-section-writer"`，每节一次派发；波=一章的全部 PENDING 节，一回合内批量发起，单回合 ≤3 并发），`subagent_status` 轮询收节。
```

- [ ] **Step 2.7: 步骤 1.3 章树绑定——一期缓行标注**

old_string:
```
3. **章树绑定（项目路径专属，D6/D12）**：门 1 前 `project_list_chapters` 拉树导出 JSON → `mapping.py bind --tree tree.json --stage S --output state/mapping.json`（核对=节序+标题一致性，非语义匹配；rc=0 才落盘）。**rc=2 不一致（树过期/被人工改动）→ 升用户确认，禁静默错写、禁带病续跑**；独立路径无项目树，跳过绑定（交付走单文件）。
```
new_string:
```
3. **章树绑定（项目路径专属，D6/D12；pisuan 一期缓行——本平台为独立路径交付，无项目树，本步整条跳过；以下为二期启用时的原文）**：门 1 前 `project_list_chapters` 拉树导出 JSON → `mapping.py bind --tree tree.json --stage S --output state/mapping.json`（核对=节序+标题一致性，非语义匹配；rc=0 才落盘）。**rc=2 不一致（树过期/被人工改动）→ 升用户确认，禁静默错写、禁带病续跑**；独立路径无项目树，跳过绑定（交付走单文件）。
```

- [ ] **Step 2.8: 交付双通道——项目路径 bullet 缓行标注**

old_string:
```
- **项目路径**：**交付子代理**分波逐节写入——每波 ≤5–10 节：读 `state/sections/chNN_SNN.md` → `project_write_chapter(chapter_id=state/mapping.json[节id], content=节稿全文, status="draft")`（chapter_id 必须取自 mapping.json，禁用章号/标题）→ `progress.py delivered --sections … --wave N` 回执。
```
new_string:
```
- **项目路径（pisuan 一期缓行——独立路径交付；原文保留供二期启用）**：**交付子代理**分波逐节写入——每波 ≤5–10 节：读 `state/sections/chNN_SNN.md` → `project_write_chapter(chapter_id=state/mapping.json[节id], content=节稿全文, status="draft")`（chapter_id 必须取自 mapping.json，禁用章号/标题）→ `progress.py delivered --sections … --wave N` 回执。
```

- [ ] **Step 2.9: KF 契约——resolve 工具替换**

old_string:
```
- **resolve 优先 + references 兜底**（步骤 1 三件套）：`knowledge-factory_kf_resolve_template` 必须真实调用（domain_keywords 必带，bug-3066）；`found=false` 必须向用户声明兜底后才用 `references/`。工具不可用/超时视同 found=false。
```
new_string:
```
- **resolve 优先 + references 兜底**（步骤 1 三件套）：`list_report_types`（辅以 `get_templates`）必须真实调用；`found=false` 必须向用户声明兜底后才用 `references/`。工具不可用/超时视同 found=false。
```

- [ ] **Step 2.10: 验证 grep（spec V2 的静态判据）**

```bash
DST="/c/workspace/pisuan/backend/package/yuxi/agents/skills/buildin/coal-eia-writer"
grep -n "/mnt/\|ask_clarification\|present_files\|batch_task\|kf_resolve_template\|knowledge_search" "$DST/SKILL.md"
echo "rc=$?"
grep -n "project_write_chapter\|project_list_chapters" "$DST/SKILL.md"
```
Expected: 第一条 grep 无匹配（rc=1）；第二条仅命中 Step 2.7/2.8 缓行标注的原文存档处（≤4 处）。

- [ ] **Step 2.11: 提交（Task 1+2 合并单提交，spec §7.3 回滚单元）**

```bash
cd /c/workspace/pisuan
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/
git commit -m "feat: coal-eia-writer 管线化 v2 技能移植（资产搬运+SKILL.md 运行时适配）

references/scripts 原样搬运自 coal-eia-report 84 文件包（剔除缓存）；
SKILL.md 按 spec §4 映射表改编：路径 /mnt→/home/gem、工具名映射、
表单卡字段制→问题制（≤5 项/卡）、章树绑定/项目路径交付一期缓行标注；
outlines/ 删除（被 stages/planning_eia.json 章节两级清单取代）。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 运行栈同步与静态验收（V1/V2）

**Files:** 无新文件（验证任务）

- [ ] **Step 3.1: 同步到运行栈（含未提交改动）**

```powershell
cd C:\workspace\pisuan; .\scripts\sync-dev.ps1
```
Expected: 同步完成无报错。若脚本报缺失/冲突，按 upstream-sync-guide.md 处理。

- [ ] **Step 3.2: 容器内跑技能自带测试（spec V1）**

```bash
docker exec pisuan-localized-api-1 pytest /app/package/yuxi/agents/skills/buildin/coal-eia-writer/scripts/tests/ -v
```
Expected: 全部 PASS（当前仅 test_ingest_bug3229.py）。

- [ ] **Step 3.3: 重启 worker 使 BUILTIN_SKILLS 重新同步**

```bash
docker restart pisuan-localized-worker-1
sleep 15
docker logs pisuan-localized-worker-1 --tail 50 2>&1 | grep -iE "Starting worker|skill"
```
Expected: 日志出现 `Starting worker for N functions: ...`（cerebrum bug-318 判活标准）。若 skill 同步报错，读完整日志定位。

- [ ] **Step 3.4: 确认技能投影已更新（新对话可见性前提）**

```bash
docker exec pisuan-localized-api-1 sh -c 'grep -c "gem/skills" /app/skill-projections/*/coal-eia-writer/SKILL.md 2>/dev/null | head -3; ls /app/skill-projections/ 2>/dev/null | head -5'
```
Expected: skill-projections 下存在 coal-eia-writer 副本且含 `/home/gem/skills` 路径（旧 `/mnt/` 为 0）。目录布局若与预期不符，先 `ls /app/skill-projections/` 探明再断言，核心判据只有一条：**投影副本的 SKILL.md 是改编后版本（含 `/home/gem/skills`）**。

---

### Task 4: 编排者配置切换（含备份存档）

**Files:**
- Create: `docs/vibe/assets/2026-09-30-coal-eia-v2-port/orchestrator-config-backup.json`（改前存档）

- [ ] **Step 4.1: 备份现 config（回滚凭据，spec §7.3）**

```bash
mkdir -p /c/workspace/pisuan/docs/vibe/assets/2026-09-30-coal-eia-v2-port
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -A -c \
  "SELECT config_json FROM agents WHERE slug='agent-b8decd45b324';" \
  > /c/workspace/pisuan/docs/vibe/assets/2026-09-30-coal-eia-v2-port/orchestrator-config-backup.json
cat /c/workspace/pisuan/docs/vibe/assets/2026-09-30-coal-eia-v2-port/orchestrator-config-backup.json
```
Expected: 文件内容为 `{"context": {"skills": ["coal-eia-writer"], "knowledges": ["kb_cgsguljhor"], "excluded_tools": [], "model": "openai2:agnes-2.5-flash"}}`（若与此不同，以实际为准——它就是回滚凭据）。

- [ ] **Step 4.2: UPDATE 编排者配置（spec §5.1）**

```bash
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "
UPDATE agents SET config_json = '{
  \"context\": {
    \"skills\": [\"coal-eia-writer\"],
    \"knowledges\": [\"kb_cgsguljhor\"],
    \"excluded_tools\": [],
    \"model\": \"openai2:agnes-2.5-flash\",
    \"tools\": [\"ask_user_question\", \"present_artifacts\", \"list_kbs\", \"query_kb\", \"list_report_types\", \"get_templates\", \"web_search\"],
    \"subagents\": [\"eia-section-writer\"],
    \"max_execution_steps\": 1000,
    \"system_prompt\": \"你是煤矿环境影响评价报告编写项目的控制器（组长）。你的全部行动剧本在 coal-eia-writer 技能中：每轮动作以 progress.py next 的输出为准，不自主发明顺序。纪律要点（与技能一致）：数据缺失问用户不编造；数字永不经过 LLM（只写 {{SLOT}}/{{TABLE}}）；门禁 rc 决定走向；发卡即停。输出全中文。\"
  }
}'::json WHERE slug = 'agent-b8decd45b324';"
```
Expected: `UPDATE 1`。

- [ ] **Step 4.3: 读回断言**

```bash
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -c \
  "SELECT config_json->'context'->>'subagents', config_json->'context'->'tools' FROM agents WHERE slug='agent-b8decd45b324';"
```
Expected: `eia-section-writer` + 7 工具清单 + `max_execution_steps=1000`（spec R2：v2 停车契约要求 run 级预算 ≥1000 步；编排者原 config 无此键走默认值，显式设齐；旧 writer 克隆行默认 300 不够）。

---

### Task 5: 创建 eia-section-writer 子代理（prompt 蒸馏入库）

**Files:**
- Create: `docs/vibe/assets/2026-09-30-coal-eia-v2-port/writer-prompts-archive.md`（3 个旧 prompt 存档）

- [ ] **Step 5.1: 存档 3 个旧 writer prompt（蒸馏来源，spec §5.3）**

```bash
OUT=/c/workspace/pisuan/docs/vibe/assets/2026-09-30-coal-eia-v2-port/writer-prompts-archive.md
echo "# 旧 3 writer system_prompt 存档（2026-09-30，蒸馏入 eia-section-writer 后退役）" > "$OUT"
for S in regulation-writer data-survey-writer prediction-writer; do
  echo -e "\n## $S\n" >> "$OUT"
  docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -A -c \
    "SELECT config_json->'context'->>'system_prompt' FROM agents WHERE slug='$S';" >> "$OUT"
done
wc -l "$OUT"
```
Expected: 文件含 3 节且行数 >30。

- [ ] **Step 5.2: INSERT eia-section-writer（从 regulation-writer 克隆结构，覆盖 prompt/tools/skills）**

蒸馏 prompt 全文（已按 3 个旧 prompt 的可迁移写作规范蒸馏，数值纪律换成 v2 口径；旧 prompt 的 save_chapter/get_report 流程与 status=done 铁律**不带入**——那是旧架构内容）：

```text
你是煤矿环境影响评价报告的**节撰写者**。每次派发只产出一节（chNN_SNN.md），严格按派发契约执行：只读契约列出的输入文件，只写自己的节稿；不碰 data/、不碰 references/、不跑 build、不派发子任务、不调用任何业务工具。所有输出全中文。

## 写作规范（自各专业写手蒸馏）
- 标准引用格式：「编号+全称+版本」，如 GB 3095-2012《环境空气质量标准》二级标准；节末列出本节引用的全部标准清单
- 数值来源全部标注（表单数据/冻结槽位/监测来源）；数值只写 {{SLOT:key}} 或 {{TABLE:族}}，绝不手算、绝不等价改写
- 监测数据写入 Markdown 表格；现状评价用单因子指数法/超标率统计；回顾对比列出历史趋势并标注变化幅度
- 预测论证用 LaTeX 公式并标注参数来源；结果用表格分情景讨论；论证结构「因为A→所以B→建议C」
- 缺失信息一律标 [待确认]/[数据未提供] 并注明缺什么，禁编造（浓度/投资/面积等具体数值）
- 禁止出现样例报告实体名（矿区/矿井/企业/地点/敏感目标）

## 输出契约
- 节稿直写到契约指定的 state/sections/chNN_SNN.md，首行 ### <节号> <节标题>，一节一稿，新增小节用 ####，禁写 #/## 章级标题
- 修改已存在的节稿前必须先 read_file 该路径，随后整节一次 write_file 完整覆盖（禁 str_replace 小步修补）
- 完成后返回 ≤8 行摘要：结构 / [待确认] 清单 / 数据缺口 / 本节要点 2–4 条
```

```bash
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "
INSERT INTO agents (slug, backend_id, name, description, icon, pics, config_json, share_config, is_default, is_subagent, created_by, created_at, updated_at)
SELECT 'eia-section-writer', backend_id, '环评节撰写者',
       'coal-eia-writer v2 管线通用节撰写者：按派发契约写一节节稿（只读契约输入，只写本节文件）',
       icon, pics,
       jsonb_set(jsonb_set(jsonb_set(config_json::jsonb,
         '{context,tools}', '[]'::jsonb, true),
         '{context,skills}', '[]'::jsonb, true),
         '{context,system_prompt}', to_jsonb('你是煤矿环境影响评价报告的**节撰写者**。每次派发只产出一节（chNN_SNN.md），严格按派发契约执行：只读契约列出的输入文件，只写自己的节稿；不碰 data/、不碰 references/、不跑 build、不派发子任务、不调用任何业务工具。所有输出全中文。

## 写作规范（自各专业写手蒸馏）
- 标准引用格式：「编号+全称+版本」，如 GB 3095-2012《环境空气质量标准》二级标准；节末列出本节引用的全部标准清单
- 数值来源全部标注（表单数据/冻结槽位/监测来源）；数值只写 {{SLOT:key}} 或 {{TABLE:族}}，绝不手算、绝不等价改写
- 监测数据写入 Markdown 表格；现状评价用单因子指数法/超标率统计；回顾对比列出历史趋势并标注变化幅度
- 预测论证用 LaTeX 公式并标注参数来源；结果用表格分情景讨论；论证结构「因为A→所以B→建议C」
- 缺失信息一律标 [待确认]/[数据未提供] 并注明缺什么，禁编造（浓度/投资/面积等具体数值）
- 禁止出现样例报告实体名（矿区/矿井/企业/地点/敏感目标）

## 输出契约
- 节稿直写到契约指定的 state/sections/chNN_SNN.md，首行 ### <节号> <节标题>，一节一稿，新增小节用 ####，禁写 #/## 章级标题
- 修改已存在的节稿前必须先 read_file 该路径，随后整节一次 write_file 完整覆盖（禁 str_replace 小步修补）
- 完成后返回 ≤8 行摘要：结构 / [待确认] 清单 / 数据缺口 / 本节要点 2–4 条'::text), true)::json,
       share_config, false, true, NULL, now(), now()
FROM agents WHERE slug = 'regulation-writer';"
```
Expected: `INSERT 0 1`。（skills 覆盖为 `[]` 防 cerebrum R3 记录的继承污染；summary_prompt/model 等沿用克隆行默认。）

- [ ] **Step 5.3: 读回断言**

```bash
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -c \
  "SELECT slug, is_subagent, config_json->'context'->>'skills', length(config_json->'context'->>'system_prompt') FROM agents WHERE slug='eia-section-writer';"
```
Expected: `eia-section-writer | t | [] | <约 900+ 字符>`。

- [ ] **Step 5.4: 提交存档文件**

```bash
cd /c/workspace/pisuan
git add docs/vibe/assets/2026-09-30-coal-eia-v2-port/
git commit -m "chore: 环评 v2 移植配置存档（编排者 config 备份 + 旧 writer prompt 存档）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 合成项目数据构造与门禁静态预检（V4/V5 前置）

在 api 容器 scratch 目录跑管线脚本（不经 UI），把门 1/门 2 的脚本行为先验明确。**门禁脚本就是验收 oracle**：check/freeze 的 rc 是客观判据。

- [ ] **Step 6.1: 生成空白表单（33 族）**

```bash
docker exec pisuan-localized-api-1 sh -c '
rm -rf /tmp/eia-accept && mkdir -p /tmp/eia-accept/data /tmp/eia-accept/state
cd /app/package/yuxi/agents/skills/buildin/coal-eia-writer
python -X utf8 scripts/ingest.py forms --stage planning_eia --data-dir /tmp/eia-accept/data
ls /tmp/eia-accept/data | head -40'
```
Expected: 退出码 0，data/ 下生成 33 个空白表单 JSON。

- [ ] **Step 6.2: 确认门 1 现在拒绝（缺项路径）**

```bash
docker exec pisuan-localized-api-1 sh -c '
cd /app/package/yuxi/agents/skills/buildin/coal-eia-writer
python -X utf8 scripts/ingest.py check --stage planning_eia --data-dir /tmp/eia-accept/data; echo "rc=$?"'
```
Expected: rc=2 + `GATE1_MISSING` 缺项清单（这正是 V4 的拒绝半边）。

- [ ] **Step 6.3: 逐族填充合成值**

填充规则（每族适用，构造「新建项目、单一口径」场景以避开双口径分支）：
- 每个 `required: true` 字段必须给值；enum 字段只能取 schema `type: enum:A|B|C` 枚举内的值
- 监测/岩移参数族：`source` 必须是 `user_monitoring` 或 `analog_mine`；沉陷参数 `param_source` 必须三值枚举之一（规范推荐/实测回归/类比矿实测）——**这是门 1 类比来源强制的考点，必须真实给枚举**
- 标准编号族：只从 `references/standards_index.json` 已录入编号中选
- 数值字段给自洽数值（产能、面积、浓度等量级合理即可，公式一致性由门 2 冻结兜底）
- 项目主体自定（如「合成test矿区」），**禁用 sample_entities 注册表内任何真实矿名**

工作方式：读 `/tmp/eia-accept/data/<族>.json` 的空白 schema → 构造该族 values JSON → `--family <族名> --values '<json>'` 落盘。首族（project）完整示例：

```bash
docker exec pisuan-localized-api-1 sh -c '
cd /app/package/yuxi/agents/skills/buildin/coal-eia-writer
python -X utf8 scripts/ingest.py forms --stage planning_eia --data-dir /tmp/eia-accept/data \
  --family project --values "{\"mine_area_name\":\"合成test矿区\",\"report_type\":\"矿区总体规划环境影响报告书\",\"stage\":\"矿区总体规划\",\"revision_flag\":false,\"commissioning_unit\":\"合成开发有限公司\",\"undertaking_unit\":\"合成环评院\"}"
echo "rc=$?"'
```
（实际键名以空白表单为准；若校验拒绝会给出缺键/非法键清单，按回执修正重试。其余 32 族同法循环。）

- [ ] **Step 6.4: 门 1 通过判据（V4）**

```bash
docker exec pisuan-localized-api-1 sh -c '
cd /app/package/yuxi/agents/skills/buildin/coal-eia-writer
python -X utf8 scripts/ingest.py check --stage planning_eia --data-dir /tmp/eia-accept/data; echo "rc=$?"'
```
Expected: rc=0 + `GATE1_COMPLETE`。`GATE1_QUALITY` warn 行逐条消化（补数或确认可接受）。

- [ ] **Step 6.5: 冻结计算 rc=0（V5 正半边）**

```bash
docker exec pisuan-localized-api-1 sh -c '
cd /app/package/yuxi/agents/skills/buildin/coal-eia-writer
python -X utf8 scripts/progress.py init --stage planning_eia --state-dir /tmp/eia-accept/state --data-dir /tmp/eia-accept/data && \
python -X utf8 scripts/progress.py run-stage freeze --state-dir /tmp/eia-accept/state; echo "rc=$?"'
```
Expected: rc=0（formula_state.json 生成、槽位有值非全 0）。若 rc=3 anomalies，逐条判读：合成数据自相矛盾则回 Step 6.3 修值；方法学性 anomaly（如类比来源提示）则记录待 E2E 卡片确认。

- [ ] **Step 6.6: 缺参场景 rc=3（V5 负半边）**

```bash
docker exec pisuan-localized-api-1 sh -c '
cd /app/package/yuxi/agents/skills/buildin/coal-eia-writer
rm -rf /tmp/eia-accept2 && mkdir -p /tmp/eia-accept2/data /tmp/eia-accept2/state
cp -r /tmp/eia-accept/data/* /tmp/eia-accept2/data/
# 删一个冻结必需族（以 formula_runner 实际依赖为准，如沉陷参数族），重跑 freeze
python -X utf8 scripts/progress.py init --stage planning_eia --state-dir /tmp/eia-accept2/state --data-dir /tmp/eia-accept2/data && \
python -X utf8 scripts/progress.py run-stage freeze --state-dir /tmp/eia-accept2/state; echo "rc=$?"'
```
Expected: rc=3 + anomalies 清单。rc 语义若不同（如缺族在 freeze 前就被拒），记录实际行为——判据本质是「缺参可被管线显式暴露而非静默通过」。

---

### Task 7: E2E 对话验收（V3、V5–V8 交互面）

与真实用户在 web 端开新对话执行（ask_user_question 卡片需要真人作答）。执行者按此剧本逐项打勾，结果记入 Task 8 的 vibe 文档。**每个 V 项独立判定，失败停下取证，不带病继续。**

- [ ] **Step 7.1（V3 开题三件套）**: 以管理员登录 web 端 → 新建对话选择「环评写作助手」agent → 发送「请为合成test矿区编写矿区总体规划环境影响报告书」。判据：①回复含 `list_report_types`/`get_templates` 的真实工具调用记录；②未命中时出现兜底声明；③首张表单 question 开头可见按章数据预告；④追问一轮后 `/home/gem/user-data/workspace/eia-report/data/` 出现空白表单（容器侧验证：定位 workdir 后 `ls`，workdir 具体宿主机路径经 `docker exec pisuan-localized-api-1 sh -c "ls /app/user-data"` 按最近修改时间定位）。

- [ ] **Step 7.2（数据收集）**: 按 Task 6 Step 6.3 的合成值逐卡作答（enum 选项点击、数值直接填写）。判据：一回合至多一卡、每卡 ≤5 项、面向用户文案无「JSON/字段」术语。**数组族必须走三步协议一次**（spec §4.3 上传通道）：控制器出 CSV 模板（`present_artifacts` 下载、UTF-8 BOM 含示例行）→ 用户 Excel 填后对话上传 → 控制器 `ingest.py file` 解析落盘（文件落 `uploads/{file_id}_{name}`）→ FORM_WRITTEN 回执含行数。全部族收完后容器侧 `ingest.py check` 间接复验（由控制器跑，rc=0）。

- [ ] **Step 7.3（V5 门 2 卡片）**: 控制器跑 freeze。若 rc=3，必须出现 anomaly 确认卡（即使此前用户说过「别再问」）；作答「按冻结值继续」。判据：卡片呈现 + 确认后推进。

- [ ] **Step 7.4（V6 节级派发）**: 观察控制器派发。判据：`subagent_start` 的 subagent_slug=`eia-section-writer`；一回合批量发起 ≥2 节；子代理产出落 `state/sections/chNN_SNN.md`（容器侧 ls 验证）；`progress.py gate` 批量跑完，PASS 章 VERIFIED。同时 `docker logs pisuan-localized-worker-1 --tail 100` 无子代理 pending 死锁（cerebrum max_jobs 教训）。

- [ ] **Step 7.5（V7 交付）**: 覆盖 ≥2 章、每章 ≥1 节 VERIFIED 后（验收范围即可，无需全 13 章——全章产出在时间允许下继续，判据不依赖）……判据：控制器不亲笔写章；收口后 `run-stage finalize` 输出 BUILD_READY + MANIFEST_READY；`/home/gem/user-data/outputs/` 出现 `合成test矿区-矿区总体规划-环境影响报告.md` + delivery_manifest.json + project_snapshot.json；`present_artifacts` 呈现可下载。

- [ ] **Step 7.6（V8 断点续跑）**: 在 V3 完成后、门 1 通过前人为终止一次 run（直接关闭对话轮即可），新开 run 发「继续」。判据：控制器首动作 `progress.py next` 恢复现场（而非从头重新收集）。

- [ ] **Step 7.7（V9 回归隔离）**: 任选一个其他 skill 的既有用法（如 deep-research）跑一轮冒烟。判据：行为正常，无工具面污染。

---

### Task 8: 文档收尾与提交

**Files:**
- Create: `docs/vibe/2026-09-30-coal-eia-v2-port.md`
- Modify: `docs/develop-guides/changelog.md`

- [ ] **Step 8.1: 写 vibe 需求文档**，内容含：需求一句话（指向 spec）、9 项验收 checklist 及逐项结果（V1–V9）、与计划的偏差记录、回滚指南（指向 `docs/vibe/assets/2026-09-30-coal-eia-v2-port/` 的两份存档 + `git revert` 技能提交 + subagents 加回旧 writer slug）、已知约束（附件 ≤5MB、单卡 ≤5 项、planning_eia only）。

- [ ] **Step 8.2: changelog.md 增补条目**（归入既有格式，一段话概述移植内容与验收结论）。

- [ ] **Step 8.3: 提交**

```bash
cd /c/workspace/pisuan
git add docs/vibe/2026-09-30-coal-eia-v2-port.md docs/develop-guides/changelog.md
git commit -m "docs: coal-eia-writer v2 移植验收记录与回滚指南

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 8.4: OpenWolf 台账**：`.wolf/memory.md` 追加会话行；`.wolf/cerebrum.md` 视执行中的新发现补充（如容器/DB 实际行为与预期的偏差）。

---

## 执行注意事项（全程有效）

1. **容器名一律 pisuan-localized-***——cerebrum 里历史记录的 api-dev/worker-dev/postgres 已是旧栈名。
2. **Git Bash 陷阱**：`docker exec <c> grep ... /app/...` 的 `/app` 会被 MSYS 转换成本地路径——必须 `docker exec <c> sh -c '... /app/...'` 把路径放进单引号内。
3. **worker 重启语义**：BUILTIN_SKILLS 内容变更后必须 `docker restart pisuan-localized-worker-1` 且**新开对话**才拿到新技能副本（`_dirs_equal` 只比文件清单不比内容）。
4. **唯一写者纪律在验收中同样生效**：合成数据只能经 `ingest.py` 落盘，绝不起草手写 data/ JSON 的捷径——那会让门 1 的行为验证失真。
5. 若执行中发现与 spec/计划冲突的事实（如容器路径、表结构不符），停下取证并回写 spec/计划，不现场即兴变更设计。

---

## 执行修正记录（Unit A，2026-09-30）

1. **Step 1.1**：用户会话中已手动删除旧 `coal-eia-writer/` 目录（31 文件，未暂存）——本步骤 Expected 由「空输出」改为「31 行未暂存 D」。
2. **Step 1.2**：原拷贝命令清单漏了 `README.md`（源包剔除缓存后净 68 文件 = SKILL.md + README.md + scripts + references）；已补 `cp "$SRC/README.md"`，对账 oracle（Step 1.3 diff 为空）裁定含 README.md 搬运。
3. **Step 2.3**：old_string 前缀笔误——实际文件为有序列表项 `1. **开题首动作三件套…`，非三空格前缀；按「以实际文本为准」执行。
4. **计划 8 处改编存在缺口**：停车点表格行（`每波 batch_task 投递后`）、步数预算段（`batch_task` 合并派发）、派发契约禁令行（`不派 task`）三处残留未覆盖；经控制器裁决补齐（subagent_start 语义对齐），SKILL.md 最终为 **8+3 处改编**。
5. **Step 2.11**：原 Expected「无差异」在 2.1+2.2 成功后字面不可成立（frontmatter 收缩 -2 行位移 + 计划内 sed 差异）；改为对齐窗口比对 + 未触碰区段抽查（红线 P1–P8 逐字保留、命令速查表 diff_rc=0 均已验证）。
6. **质量审查发现并修复（73692847 → 0f02f659 → 783ab1f4）**：SKILL.md:72/:262 沿用源包过期叙述「stage 文件在编/文件未立」，与同提交落库的 5 个 stage 文件及 frontmatter 自相矛盾——改为政策性表述「stage 文件已随包就绪，一期未验收、暂不启用」（spec Q4 的门槛是验收政策而非文件缺失）；:102 「一回合内批量发起，单回合 ≤3 并发」字面张力改为「分批发起、在飞 ≤3，有完成即补位，直至波内全部发出」；复审非阻塞 FYI :193「`subagent_start` 一回合批量发起」同类张力，控制器直接修正为「按派发协议分批补位发起」。
7. **质量审查不修项（记录在案）**：SKILL.md:28 红线段无条件假设 web_search 可用，实际该工具仅在部署配置了搜索 provider 时注册——加兜底表述超出 spec §4.4「映射表之外逐字保留」的改编边界，不改动；已知运维约束：未配 provider 的部署上 web_search 调用即失败。
8. **Task 3 执行发现（运行栈实际行为）**：① pisuan-localized 改名层内路径为 `/app/package/pisuan/...`（非 `/app/package/yuxi/...`），Step 3.2 pytest 路径按此执行（7/7 PASS，含 7 用例而非 1）；② worker 重启只跑 init_builtin_skills（同步 buildin→/app/skill-sources/shared + upsert skills 行），**不刷新**用户投影——投影 DB 驱动且惰性（composite.py sync_agent_context_skills → refresh_user_skill_projection_async，Agent-Run init 时重建）；③ 历史 skills 行 `coal-eia-writer` enabled=False（2026-05-11 v1 时代遗留），list_enabled_readable 只收 enabled=True → 投影不含它；控制器裁决经生产服务层启用 + 刷新投影（等效 UI 启用，可逆）；④ 核心判据先行验证：repo/buildin/skill-sources 三份 SKILL.md md5 一致（d61ddfeb244ffdc490451877211e8d85），/mnt/=0、旧工具名零残留；⑤ DB 访问用一次性 asyncpg 连接（容器内连接池有 'error connecting in pool-1' 挂起前科）。
9. **Task 5 策略碰撞**：`docs/vibe` 在 .gitignore:78 显式忽略，Step 5.4 的 `git add` 被拒——实现者按计划提交意图 `git add -f` 精确加 2 个存档文件（提交 33507661，仅含这 2 个文件）。回滚凭据进 git 与仓库「docs/vibe 不跟踪」策略相碰撞，已向用户显式标记；后续 Task 8 的 vibe 文档提交沿用 -f 或用户另行裁决。另：agents.config_json 为 json 列（bug-322），读回断言需显式 `::jsonb` cast；`eia-section-writer` prompt 长度 697 字符（计划「约 900+」为误估，中文按字符计实质等量，判定通过）。
10. **Task 6 预检实证（脚本行为先验，全部容器内实证）**：① 空白表单 31 族而非 33（`planning_indicators` 为 derived_view 共享 01_mine_plan.json、`projection` file=None 不产空白，bug-3208 既有行为）；② 门 1 链路 rc：空白 rc=2 GATE1_MISSING（81 缺项）→ 填满 rc=0 GATE1_COMPLETE；③ **门 1 不强制类比来源**（实测 param_source=类比矿实测+无 analog_source 仍 rc=0；脚本强制点仅在冻结 water XS12 与一致性口径层）——spec V4 括注勘误；④ **freeze rc=0 结构性不可达**（software_results 在 planning_eia schema 无声明字段，能力边界 anomaly 必现）——V5 验收签名改为「rc=3 + 仅此 1 条 anomaly + 49 槽位有值」；⑤ **`--stage` 只认路径**（progress.py init/chapter_planner/formula_runner 均裸 FileNotFoundError，仅 ingest.py 兼容名称）——SKILL.md :56 补 S 定义（da4991a0）；⑥ **progress.py next 输出残留源运行时词汇** batch_task/task()，与 SKILL.md subagent_start 映射正面冲突——SKILL.md :102 加卫兵句 + 编排者 system_prompt 注入映射句（da4991a0 + DB UPDATE，同步链重走，三方 md5=7d68f4d1）；⑦ water schema↔runner 漂移：balance 字段不可达 → reuse_rate 恒 0%（canon 称 40.3%）——Task 7 预期卡，禁用数据掩盖；⑧ capacity 单位口径怪癖（air μg/m3 入 A 值公式、water /1000）——E2E 卡候选，禁改数据；⑨ Task 7 scratch 证据留存 /tmp/eia-accept（冻结 49 槽）、/tmp/eia-accept2（负例 35 槽）、/tmp/eia-values、/tmp/fill_*.log。
11. **真实语料 fixture 集（用户追加任务，独立于 E2E）**：源=《新疆伊宁矿区北区总体规划（修编）环评报告书 报批版 2024.1.30》（52MB docx→83.7 万字符全文抽取，即 sample_entities 注册表源语料）；产物 `docs/vibe/assets/2026-09-30-coal-eia-v2-port/eia-sample-fixtures/`（31 族真值 JSON+35 CSV+values-gaps ~30 条+family-sources+README；gitignore 内保持本地）。容器实测标定：31 族装载 rc=0 零修正；数组族契约=wrapper 键 --values（裸 --rows rc=1，F-L-02）；ingest.py file 通道对本 stage 不可用（无 CSV 族注册，F-L-01）——三步协议第③步本就走 forms --values，协议不受影响；门 1 rc=2（air.boilers=[] 零值事实×缺失判据碰撞，bug-326）；冻结 rc=3 slots=117 anomalies=46（重复采动×20 数据缺口、厚煤层两带×18 方法学边界、water/air 容量输入×3、noise 区间字符串×3、能力边界×1、boilers×1）；七号井田 W_max 公式冻结 59.56m vs 报告软件值 76.58m（-22%，由能力边界 anomaly 承载）。用途：上线前真实项目试跑预演；已知兜底 F-carbon-ef/F-investment/F-soil-total 见 gaps。
