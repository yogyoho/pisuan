# 青云素雅主题换肤实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将平台主题从「科技蓝」（blue #2563eb）整体更换为「青云素雅」（indigo #4f46e5 + 微阴影描边形制），并偿还两类风格债务：16 个文件的残留 antd 图标、散落组件的硬编码色值。

**Architecture:** 四层结构（CSS 变量层 base.css/base.dark.css → AntD token 层 stores/theme.js → 组件内联样式 → 图标），按「先收编（值不变纯重构）→ 再换值 → 再迁移图标 → 品牌页对齐 → 验收同步」五步提交，每步独立可验证可回滚。

**Tech Stack:** Vue 3 + ant-design-vue + @lucide/vue + Pinia + Less；无后端改动。

**Spec:** `docs/superpowers/specs/2026-09-29-qingyun-theme-retheme-design.md`（Token 唯一色值依据）

**执行状态**（断点续跑）：T1 ✅ `993e0e1f`、T2 ✅ `b3817d27`、T3 ✅ `558d892a`、T4 ✅ `1475a197`/`604b5725`/`5b027a87`/`bfd885af`/`3f8df8eb`、T5 ✅ `21a362ed`、T6 ✅ `2befe9ec`/`f77e828f`/`087cf28f`、T7 ✅ `a0c3fb72`/`613c2e96`/`4df22a12`/`4bb6fc14`/`0e659eec`/`0eaee722`/`a0b90f17`/`826a68aa`/`be9f4798`（T7 规格审查抓出 Robot 导出名缺陷 → 修复 `a0b90f17` 并全库 lucide 导入名运行时核验；质量审查抓出 pnpm-lock 漂移 → `be9f4798` 一次性容器 `pnpm install --lockfile-only` 收敛（含 fontsource 历史欠账双向收敛，FROZEN_OK 独立复跑验证）+ `826a68aa` 两处打磨；遗留债：AgentChatComponent is-spinning 动态绑定+死规则、TodoListTool 自建 keyframes）、T8（可自动化部分）✅ `6cd094e4`/`a3bd0506`/`2e0f3ed8`/`8e7da771`（规格审查一处退回 → 披露修复 `8e7da771`：--red-50→--color-error-50 明色 1/255 微差非精确等值，裁定保留改名、changelog 披露扩四处；质量审查 Ready=Yes。口径记录：①机检 #1 HEX_CLEAN 按实质门禁口径达成——55 行 var(--x,#fallback) 合规回退按 T6 三分法不打标（字面 HEX_CLEAN 不可达）；②标记统计口径=新增「含 hex 且含标记」行 4→77（申报 88/13 为不同口径，实质结论一致）；③Step 3 lint 验证对象勘误——容器 eslint 的是 localized 派生树而非本工作树，官方链同步后须以正确树复跑全量 lint 闭环。流程事故：T8 质量审查代理擅自 stash 工作树（bug-315），用户 WIP 已从 stash 恢复，Do-Not-Repeat 已立规）（均过规格+质量双审；T3 裁定：base.css 块级 [pisuan-custom] 标记达标、second-40 扩展档明度微逆可接受；T4 裁定：暗色 --main-color 收敛为 #7279f5 提亮档复刻旧体系落差结构，`--main-color-rgb` 落地值 明 `79, 70, 229` / 暗 `114, 121, 245`）。
T4 口径裁定（T3 质量审查移交）：暗色图表锚点保留 `--chart-palette-1: var(--main-400)` 机制（解析为 indigo-400 #818cf8，暗底可读），palette 2..10 照抄浅色字面值；`--page-bg` 变量在 base.css 不存在，page 类 0 行为正确结果；chartColors.js:28/37 陈旧注释（「拂晓蓝」「know 项目」）随 T4 顺手修正。
审查移交备注：① T3 注意图表变量实际名为 `--chart-palette-*`（非 --chart-N），且 chartColors.js 的 hex 为 getComputedStyle fallback，需同步换值；② T4 需在 base.css/base.dark.css 增设 `--main-color-rgb` 通道别名（明 79,70,229 / 暗 77,148,247）并改写组件内 rgba(22,119,255,*)/rgba(24,144,255,*) 旧蓝为 rgba(var(--main-color-rgb), 原透明度)（EtlWorkbench L1805/L1943、DomainFactoryView L411 等，grep 全量）；③ T6 需处理 KnowledgeGraphSection.vue:193 antd 旧蓝→绿渐变（SVG stop 不解析 var()，用字面 indigo 对 #4f46e5→#a5b4fc）+ 注释措辞、HomeViewV2 L652-660/L1202 rgba 旧蓝、4 处未定义变量引用规范化（ContextUsageRing --warning-color/--error-color、AgentPanel --error-600、PdfPreview --color-danger，仅 fallback==规范值时改名）、bug-307：EtlWorkbench.vue:2077 `var(--blue-400, #4096ff)` 未定义变量活 fallback（旧 antd 蓝存活，改 `var(--main-color)`）；④ T8 changelog 补披露 + 勘误：theme.js:9「上游默认拂晓蓝 #1890ff」为历史失准注释（上游原值实为青碧系 #24839b，#1890ff 系 pisuan 首个定制提交引入的中间态），随台账收尾勘误；OutlineTemplate.vue 预估 5 处均为既有 var() fallback 未动、语义变量名按 base.css 实际名替代（--color-*-500/700 系）、#dc2626→--color-error-700 与 #999→--gray-600 两处非精确等值、#1677ff/#1890ff→--main-color 为计划内就近映射。

---

## 执行环境约束（每个 Task 都适用）

- 工作目录：`C:\workspace\pisuan`（pisuan-custom 分支）
- 前端 lint（宿主机无 pnpm，一律走容器）：`docker exec pisuan-localized-web-1 sh -c 'cd /app && ./node_modules/.bin/eslint <改动文件...> && echo LINT_OK'`；注意容器挂载的是 **localized 树**，改动须先 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1` 同步过去再 lint
- 期望输出统一为 `LINT_OK`；HMR 报错检查：`docker logs pisuan-localized-web-1 --since 2m 2>&1 | grep -iE "error|failed"`
- 后端零改动；`backend/**`、`info.template.yaml` 不碰
- 每步提交信息中文 + Conventional Commits + `Co-Authored-By: Claude Code <noreply@anthropic.com>`
- 所有 base.css / base.dark.css / theme.js 改动行必须带 `// [pisuan-custom]` 或 `/* [pisuan-custom] */` 行内标记（CSS 文件中放在改动行行尾或上一行）

## 色值处置决策树（收编任务通用）

```
遇到一个裸 hex：
├─ 在 <style> 或 style 属性中（CSS 上下文）？
│   ├─ 映射表能对应变量（见 T1.2 映射表）→ 替换为 var(--*)
│   ├─ 外部产品品牌色（OpenAI 绿、GitHub 黑等）→ 保留 + 行尾注释 /* 品牌色，不随主题 */
│   └─ 无对应变量的一次性装饰色 → 保留 + 行尾注释 /* 一次性装饰色 */
└─ 在 <script> 中（JS 上下文）？
    ├─ 喂给 ECharts/Canvas（不解析 CSS 变量）→ 不收编；若承载主题色 → 留给 Task 4 更新值
    └─ 其他 → 能用 var() 的场景（内联 style 字符串）→ var()；否则同上分类
```

---

### Task 1: 色值收编 — 高密度文件（utils 与 domain-factory 群）

**Files:**
- Modify: `web/src/utils/chartColors.js`（25 处，图表调色板 → **值更新延后到 Task 4**，本任务仅加文件头注释说明其为主题承载常量）
- Modify: `web/src/utils/modelIcon.js`（16 处，外部模型品牌色 → **保留**，逐行补 `/* 品牌色 */` 注释）
- Modify: `web/src/components/domain-factory/EtlWorkbench.vue`（32 处）
- Modify: `web/src/components/domain-factory/DataSourceDashboard.vue`（29 处）
- Modify: `web/src/views/DomainFactoryView.vue`（21 处）
- Modify: `web/src/components/domain-factory/OutlineTemplate.vue`（5 处）
- Modify: `web/src/views/DomainEntityBuilderView.vue`（4 处）

- [ ] **Step 1: 生成每个文件的精确色值清单**

```bash
cd C:/workspace/pisuan
for f in web/src/utils/chartColors.js web/src/utils/modelIcon.js \
  web/src/components/domain-factory/EtlWorkbench.vue \
  web/src/components/domain-factory/DataSourceDashboard.vue \
  web/src/views/DomainFactoryView.vue \
  web/src/components/domain-factory/OutlineTemplate.vue \
  web/src/views/DomainEntityBuilderView.vue; do
  echo "== $f"; grep -nE "#[0-9a-fA-F]{3,8}\b" "$f" | head -40
done
```

- [ ] **Step 2: 逐文件按决策树处置**

CSS 上下文替换映射表（就近原则，色相差 <15° 才可替代，否则归入保留类）：

| 裸值 | 替换为 |
|---|---|
| `#2563eb` `#1890ff` `#1677ff` | `var(--main-color)` |
| `#3b82f6` | `var(--main-500)` |
| `#1d4ed8` | `var(--main-700)` |
| `#93c5fd` | `var(--main-300)` |
| `#60a5fa` | `var(--main-400)` |
| `#dbeafe` | `var(--main-100)` |
| `#eff6ff` | `var(--main-50)` |
| `#e4e4e7` `#e5e7eb` | `var(--gray-200)` |
| `#f4f4f5` `#f5f5f5` `#f9fafb` | `var(--gray-100)` |
| `#71717a` `#6b7280` | `var(--gray-500)` |
| `#3f3f46` `#374151` | `var(--gray-700)` |
| `#18181b` `#1f2937` | `var(--gray-900)` |
| `#16a34a` `#22c55e` | `var(--success-color)` |
| `#dc2626` `#ef4444` | `var(--error-color)` |
| `#d97706` `#f59e0b` | `var(--warning-color)` |

变量名以 `grep -E "^\s+--(gray|success|error|warning)" web/src/assets/css/base.css` 实际输出为准；若上表变量名不存在，用实际名替代并在提交信息中注明。

ECharts/Canvas 上下文的主题蓝（`#2563eb` 系）→ 不替换，记入「Task 4 待更新清单」（在文件顶部用 `// TODO(task4): 换肤时更新为 indigo` 临时标记，Task 4 完成后删除标记）。

- [ ] **Step 3: lint 与视觉零变化验证**

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
docker exec pisuan-localized-web-1 sh -c 'cd /app && ./node_modules/.bin/eslint src/utils/chartColors.js src/utils/modelIcon.js src/components/domain-factory/ src/views/DomainFactoryView.vue src/views/DomainEntityBuilderView.vue && echo LINT_OK'
```

浏览器（用户已登录的 http://localhost:5173）检查领域工厂、ETL 工作台页面观感与改前一致（本步纯重构，唯一允许的变化是注释）。

- [ ] **Step 4: Commit**

```bash
git add web/src/utils/chartColors.js web/src/utils/modelIcon.js web/src/components/domain-factory/ web/src/views/DomainFactoryView.vue web/src/views/DomainEntityBuilderView.vue
git commit -m "refactor: domain-factory 与 utils 色值收编（值不变纯重构）"
```

---

### Task 2: 色值收编 — 中低密度零散文件

**Files:**（按密度降序）

| 文件 | 处数 | 预处置 |
|---|---|---|
| `web/src/components/GraphCanvas.vue` | 18 | 知识图谱实体类型色（数据可视化语义）→ 保留 + 注释；主题蓝除外（→ Task 4 清单） |
| `web/src/components/common/PdfPreview.vue` | 7 | C1 收编 |
| `web/src/components/extensions/SkillCardList.vue` | 5 | C1 收编 |
| `web/src/components/ToolCallingResult/tools/TodoListTool.vue` | 4 | C1 收编（状态色用语义变量） |
| `web/src/stores/theme.js` | 3 | **跳过**（token 定义值，Task 5 换值） |
| `web/src/components/UserManagementComponent.vue` | 3 | C1 收编 |
| `web/src/components/McpEnvEditor.vue` | 2 | C1 收编 |
| `web/src/components/KnowledgeGraphSection.vue` | 2 | 同 GraphCanvas 原则 |
| `web/src/components/DepartmentManagementComponent.vue` | 2 | C1 收编 |
| `web/src/components/ContextUsageRing.vue` | 2 | SVG stroke 上下文 → var() 可用则收编 |
| `web/src/components/ApiKeyManagementComponent.vue` | 2 | C1 收编 |
| `web/src/views/LoginView.vue` | 1 | 留给 Task 6（品牌页） |
| `web/src/views/HomeView.vue` | 1 | 留给 Task 6（品牌页） |
| `web/src/utils/markdown_preview.js` | 1 | C1 收编（若为代码高亮主题色则保留） |
| `web/src/components/knowledge/DatabaseCreateFlowModal.vue` | 1 | C1 收编 |
| `web/src/components/extensions/SkillInstallFlowModal.vue` | 1 | C1 收编 |
| `web/src/components/MessageInputComponent.vue` | 1 | C1 收编 |
| `web/src/components/GlobalSearchModal.vue` | 1 | C1 收编 |
| `web/src/components/AgentPanel.vue` | 1 | C1 收编 |

- [ ] **Step 1: 全清单生成**（同 Task 1 Step 1 命令模式，覆盖上表 19 文件；含 3 位 hex：`grep -nE "#[0-9a-fA-F]{3,8}\b"`）
- [ ] **Step 2: 逐文件处置**（同 Task 1 决策树与映射表）
- [ ] **Step 3: 收尾检查 HomeViewV2**（不在 6 位 hex 清单中，单独查 3 位/rgba 遗留）：

```bash
grep -nE "#[0-9a-fA-F]{3}\b|rgba?\(" web/src/views/HomeViewV2.vue | grep -v "var(--" | head -20
```

发现的旧主题色（`#1890ff`/`#2563eb` 系）记入 Task 6 清单；纯装饰色保留。

- [ ] **Step 4: sync-dev + lint（上表全部文件）+ 浏览器抽查知识库/对话/管理页观感不变**
- [ ] **Step 5: Commit**

```bash
git add web/src/components/ web/src/utils/markdown_preview.js
git commit -m "refactor: 零散组件色值收编（值不变纯重构）"
```

---

### Task 3: 换肤 — base.css 变量值替换

**Files:**
- Modify: `web/src/assets/css/base.css`（main/second/chart/shadow/page-bg 档位值）

- [ ] **Step 1: 导出现值基线**（供 diff 自检）

```bash
grep -nE "^\s+--(main|second|chart|shadow|page)" web/src/assets/css/base.css > /tmp/base-tokens-before.txt
cat /tmp/base-tokens-before.txt
```

- [ ] **Step 2: main 色阶 blue → indigo（档位对档位，变量名不变，全部行尾加 `/* [pisuan-custom] 青云素雅 */`）**

| 档 | 旧（blue） | 新（indigo） |
|---|---|---|
| 50 | `#eff6ff` | `#eef2ff` |
| 100 | `#dbeafe` | `#e0e7ff` |
| 200 | `#bfdbfe` | `#c7d2fe` |
| 300 | `#93c5fd` | `#a5b4fc` |
| 400 | `#60a5fa` | `#818cf8` |
| 500 | `#3b82f6` | `#6366f1` |
| 600 | `#2563eb` | `#4f46e5` |
| 700 | `#1d4ed8` | `#4338ca` |
| 800 | `#1e40af` | `#3730a3` |
| 900 | `#1e3a8a` | `#312e81` |
| 950（如有） | `#172554` | `#1e1b4b` |

`--main-color` / `--main-color-rgb` 等别名变量：`#2563eb` → `#4f46e5`（rgb 串 `37, 99, 235` → `79, 70, 229`）。以 Step 1 实际清单为准，凡值在旧列中的变量一律换新列同档值。

- [ ] **Step 3: second 辅助色 cyan → orange（点缀橙，档位同法）**

| 档 | 旧（cyan） | 新（orange） |
|---|---|---|
| 50 | `#ecfeff` | `#fff7ed` |
| 100 | `#cffafe` | `#ffedd5` |
| 200 | `#a5f3fc` | `#fed7aa` |
| 300 | `#67e8f9` | `#fdba74` |
| 400 | `#22d3ee` | `#fb923c` |
| 500 | `#06b6d4` | `#f97316` |
| 600 | `#0891b2` | `#ea580c` |
| 700 | `#0e7490` | `#c2410c` |
| 800 | `#155e75` | `#9a3412` |
| 900 | `#164e63` | `#7c2d12` |

若现值与旧列不符（历史微调），以「色相 cyan→orange、明度档位不变」为原则取 Tailwind orange 对应档。

- [ ] **Step 4: chart 10 色 → 靛蓝锚点环（--chart-1..10 顺序对应）**

```
1 #4f46e5  2 #0ea5e9  3 #8b5cf6  4 #14b8a6  5 #f59e0b
6 #f43f5e  7 #06b6d4  8 #10b981  9 #d946ef  10 #64748b
```

同时更新 `web/src/utils/chartColors.js` 的对应常量值（Task 1 留下的 TODO(task4) 标记处，完成后删除标记）。

- [ ] **Step 5: 阴影减淡 + 页面底**

```
--shadow-0: rgba(0,0,0,.02)   保持
--shadow-1: rgba(0,0,0,.05) → rgba(0,0,0,.04)
--shadow-2: rgba(0,0,0,.08) → rgba(0,0,0,.05)
--shadow-3: rgba(0,0,0,.12) → rgba(0,0,0,.08)
--shadow-4: rgba(0,0,0,.16) → rgba(0,0,0,.10)
--shadow-5: rgba(0,0,0,.20) → rgba(0,0,0,.12)
--page-bg:  → #fafafa          （核对现值后改；同时确认卡片描边消费 --gray-200=#e4e4e7 无需动）
```

- [ ] **Step 6: diff 自检**（只允许映射表内的值变化）

```bash
grep -nE "^\s+--(main|second|chart|shadow|page)" web/src/assets/css/base.css > /tmp/base-tokens-after.txt
diff /tmp/base-tokens-before.txt /tmp/base-tokens-after.txt
```

Expected: 仅 main/second/chart/shadow/page 行变化，变量名与行序零变化。

- [ ] **Step 7: sync-dev + 浏览器巡检（工作台/对话/知识库/领域工厂 浅色态）+ Commit**

```bash
git add web/src/assets/css/base.css web/src/utils/chartColors.js
git commit -m "feat: base.css 主色换靛蓝、辅助色换橙、图表色环与阴影减淡（青云素雅）"
```

---

### Task 4: 换肤 — base.dark.css 对应更新

**Files:**
- Modify: `web/src/assets/css/base.dark.css`

- [ ] **Step 1: 导出暗色基线**（同 Task 3 Step 1 命令，文件换 base.dark.css）
- [ ] **Step 2: main 档位换 indigo**——暗色文件中承担主色角色的档（现为 blue-500 `#3b82f6` 者）→ `#6366f1`（indigo-500）；其余出现的 blue 系值按 Task 3 Step 2 表档位映射。三底色（`#0a0a0a`/`#18181b`/`#262626`）**不动**。
- [ ] **Step 3: second 档位换 orange**（同 Task 3 Step 3 表）
- [ ] **Step 4: chart 10 色**与浅色一致（同 Task 3 Step 4 值）
- [ ] **Step 5: 描边变量现值核对**：暗色描边若非 `#2a2a2e` 则更新为 `#2a2a2e`（仅描边角色变量，不动 gray 全阶）
- [ ] **Step 6: diff 自检（同 Task 3 Step 6 模式）→ sync-dev → 浏览器切深色巡检同四页 → Commit**

```bash
git add web/src/assets/css/base.dark.css
git commit -m "feat: base.dark.css 主色/辅助色/图表色对齐青云素雅（底色保持 zinc 系）"
```

---

### Task 5: 换肤 — theme.js AntD token

**Files:**
- Modify: `web/src/stores/theme.js:12-36`

- [ ] **Step 1: 更新 token 值**（保留两处 `// [pisuan-custom]` 注释锚点，改值并更新注释中的主题名）

```js
  // [pisuan-custom] 公共主题配置 - 青云素雅主题 (Tailwind indigo-600)：主色与字体均为 pisuan 定制（上游默认拂晓蓝 #1890ff + 系统字体栈），同步时保留
  const commonTheme = {
    token: {
      fontFamily:
        '"Inter Variable", "Inter", "PingFang SC", "Noto Sans SC", "Microsoft Yahei", "微软雅黑", Arial, sans-serif',
      colorPrimary: '#4f46e5',
      colorLink: 'var(--main-color)',
      colorLinkHover: 'var(--main-600)',
      colorLinkActive: 'var(--main-800)',
      borderRadius: 10,
      wireframe: false
    }
  }
```

暗色覆盖块：`colorPrimary: '#3b82f6'` → `#6366f1`，注释改为 `// [pisuan-custom] 暗色主色提亮为 indigo-500（上游 darkAlgorithm 不覆盖主色），同步时保留`

- [ ] **Step 2: sync-dev + lint theme.js + 浏览器确认 AntD 组件（按钮/链接/选中态/分页）主色变靛蓝、圆角变 10**
- [ ] **Step 3: Commit**

```bash
git add web/src/stores/theme.js
git commit -m "feat: AntD token 对齐青云素雅（indigo 主色 + 圆角 10）"
```

---

### Task 6: 品牌页对齐（HomeViewV2 / HomeView / LoginView）

**Files:**
- Modify: `web/src/views/HomeViewV2.vue`
- Modify: `web/src/views/HomeView.vue`
- Modify: `web/src/views/LoginView.vue`

- [ ] **Step 1: 枚举三页品牌色引用**

```bash
grep -nE "#1890ff|#2563eb|#3b82f6|#4096ff|rgba?\(\s*(37|24|59)\s*,|rgba?\(\s*22\s*,\s*119" \
  web/src/views/HomeViewV2.vue web/src/views/HomeView.vue web/src/views/LoginView.vue
```

- [ ] **Step 2: 替换规则**

| 旧值 | 新值 |
|---|---|
| `#2563eb` / `#1890ff` | `var(--main-color)`（CSS 上下文）或 `#4f46e5`（JS/渐变上下文） |
| `#3b82f6`（渐变端点/暗色引用） | `#6366f1` |
| `rgba(37,99,235,*)` / `rgba(22,119,255,*)` | `rgba(79,70,229,*)` 保持原透明度 |

渐变保留结构只换端点色；`[pisuan-custom]` 标记行保持。

- [ ] **Step 3: sync-dev + 浏览器验收 Landing（`/`）与登录页（`/login`）明暗两态 → Commit**

```bash
git add web/src/views/HomeViewV2.vue web/src/views/HomeView.vue web/src/views/LoginView.vue
git commit -m "feat: Landing 与登录页品牌色对齐青云素雅"
```

---

### Task 7: 图标迁移 — @ant-design/icons-vue → @lucide/vue（16 文件）

**Files:**

```
web/src/components/AgentChatComponent.vue      web/src/components/ChunkParamsConfig.vue
web/src/components/dashboard/FeedbackModalComponent.vue
web/src/components/domain-factory/DataSourceDashboard.vue
web/src/components/domain-factory/EtlWorkbench.vue
web/src/components/domain-factory/OutlineTemplate.vue
web/src/components/MessageInputComponent.vue   web/src/components/QuerySection.vue
web/src/components/ToolCallingResult/tools/CalculatorTool.vue
web/src/components/ToolCallingResult/tools/TodoListTool.vue
web/src/views/DataBaseInfoView.vue             web/src/views/DomainEntityBuilderView.vue
web/src/views/DomainFactoryView.vue            web/src/views/DomainOutlineTemplateView.vue
web/src/views/LoginView.vue                    web/src/views/PromptConfigView.vue
```

- [ ] **Step 1: 名称映射表**（antd → @lucide/vue；执行时先跑 Step 2 的存在性校验再动手）

| antd | lucide | antd | lucide |
|---|---|---|---|
| QuestionCircleOutlined | CircleHelp | SyncOutlined | RefreshCw |
| RightOutlined | ChevronRight | SaveOutlined | Save |
| FileTextOutlined | FileText | RobotOutlined | Bot |
| DownOutlined | ChevronDown | PauseOutlined | Pause |
| SearchOutlined | Search | DownloadOutlined | Download |
| PlusOutlined | Plus | CloseCircleOutlined | CircleX |
| DeleteOutlined | Trash2 | ClockCircleOutlined | Clock |
| UpOutlined | ChevronUp | CheckCircleOutlined | CircleCheck |
| ThunderboltOutlined | Zap | SendOutlined | Send |
| ReloadOutlined | RotateCw | RedoOutlined | Redo2 |
| ArrowLeftOutlined | ArrowLeft | EyeOutlined | Eye |
| InboxOutlined | Inbox | CopyOutlined | Copy |
| ArrowUpOutlined | ArrowUp | UploadOutlined | Upload |
| ToolOutlined | Wrench | LikeOutlined | ThumbsUp |
| LeftOutlined | ChevronLeft | FileWordOutlined | FileType2 |
| FileSearchOutlined | FileSearch | FilePdfOutlined | FileText |
| ExperimentOutlined | FlaskConical | DislikeOutlined | ThumbsDown |
| DatabaseOutlined | Database | CloudUploadOutlined | CloudUpload |
| AuditOutlined | ClipboardCheck | UserOutlined | User |
| SettingOutlined | Settings | NumberOutlined | Hash |
| LockOutlined | Lock | KeyOutlined | KeyRound |
| ExclamationCircleOutlined | CircleAlert | | |

- [ ] **Step 2: 映射名存在性校验**（@lucide/vue 命名与旧 lucide-vue-next 有差异，逐个确认导出存在）

```bash
docker exec pisuan-localized-web-1 node --input-type=module -e "
import * as l from '@lucide/vue';
const names = ['CircleHelp','ChevronRight','FileText','ChevronDown','Search','Plus','Trash2','ChevronUp','Zap','RotateCw','ArrowLeft','Inbox','ArrowUp','RefreshCw','Save','Bot','Pause','Download','CircleX','Clock','CircleCheck','Send','Redo2','Eye','Copy','Upload','Wrench','ThumbsUp','ChevronLeft','FileType2','FileSearch','FlaskConical','ThumbsDown','Database','CloudUpload','ClipboardCheck','User','Settings','Hash','Lock','KeyRound','CircleAlert'];
const missing = names.filter(n => !(n in l));
console.log(missing.length ? 'MISSING: ' + missing.join(',') : 'ALL_OK');
"
```

Expected: `ALL_OK`。缺失的用 `Object.keys(l).filter(k=>k.toLowerCase().includes('<关键词>'))` 就近查找并回填映射表。

- [ ] **Step 3: 逐文件迁移**（16 文件，每文件一个内部循环）

每文件流程：
1. `grep -n "Outlined" <file>` 列出导入与用法
2. import 行：antd 导入删除；lucide 名并入**现有**的 `from '@lucide/vue'` 导入（若无则新增，按字母序插入）
3. 模板中 `<XxxOutlined class="icon" />` → `<Xxx :size="16" class="icon" />`——**size 取该用法处原 CSS `font-size` 的 px 值**（antd 字体图标靠 font-size 定尺寸，lucide SVG 靠 size/width；替换后删除该处专门控制图标字号的 font-size 声明，保留布局类声明）
4. `theme="twoTone"` 等 antd 专有 props 直接删除；`@click` 等事件绑定原样保留
5. 每文件完成后立即 lint（sync-dev → 容器 eslint 单文件）

- [ ] **Step 4: 全量收尾**

```bash
grep -rn "@ant-design/icons-vue" web/src --include="*.vue" --include="*.js"
```

Expected: 零输出。然后移除依赖：`web/package.json` 删除 `"@ant-design/icons-vue"` 行，并在容器内验证 web 能正常构建（HMR 无报错）。

- [ ] **Step 5: 图标视觉核对**——浏览器过一遍：对话页（发送/点赞/复制/工具）、领域工厂（上传/下载/同步）、登录页（用户/锁）。重点：尺寸无跳变、线条粗细一致。
- [ ] **Step 6: Commit**（每 3-4 文件一个 commit，格式：`refactor: <文件群> 图标迁移 lucide`；最后一个 commit 一并删除 package.json 依赖：`chore: 移除 @ant-design/icons-vue 依赖`）

---

### Task 8: 验收、文档与双端同步

- [ ] **Step 1: 机检三项**

```bash
cd C:/workspace/pisuan
# 1. 裸 hex 归零（白名单：assets/css/base* 变量定义处 + 含 [pisuan-custom] 的行内来历注释行）
grep -rnE "#[0-9a-fA-F]{6}\b" web/src --include="*.vue" --include="*.less" --include="*.js" \
  | grep -v "assets/css/base" | grep -v "\[pisuan-custom\]" || echo "HEX_CLEAN"
# 2. antd 图标归零
grep -rn "@ant-design/icons-vue" web/src --include="*.vue" --include="*.js" || echo "ICONS_CLEAN"
# 3. 定制标记不减
git grep -l "\[pisuan-custom\]" -- web/src | wc -l
```

Expected: `HEX_CLEAN`、`ICONS_CLEAN`、标记文件数 ≥ 改前（当前基线 15）。机检 #1 的豁免口径：变量定义文件（base.css/base.dark.css）与含 `[pisuan-custom]` 标记的来历注释行；其余任何命中行逐条人工判读，不允许扩大豁免。

- [ ] **Step 2: 视觉巡检**——7 页 × 明暗：Landing `/`、登录 `/login`、工作台、对话、知识库、领域工厂、管理后台。截图存 `.wolf/designqc-captures/`（用户已登录态页面由用户确认，未登录态可自动化）。暗色态特别留意 KnowledgeGraphSection 进度条（渐变为浅色字面对，SVG stop 限制下的既批准取舍）
- [ ] **Step 2.5: 收尾杂项（T6 质量审查移交）**：①`HomeView.vue` / `LoginView.vue` 文件头各补一行 `[pisuan-custom]` 定制声明注释（对齐 HomeViewV2 形制，防上游覆盖无告警）②清理 EtlWorkbench.vue 3 个基线既有 no-unused-vars（`Plus`/`proposedDomainCode`/`parameterParagraphs`）与 LoginView.vue 1 个（`onUnmounted`），lint 清零，提交信息中披露为存量债务清理
- [ ] **Step 3: pnpm 全量 lint**：`docker exec pisuan-localized-web-1 sh -c 'cd /app && ./node_modules/.bin/eslint src --ext .vue,.js'` → 零 error
- [ ] **Step 4: changelog 条目**（`docs/develop-guides/changelog.md` v0.7.3 功能与修复节追加）：

```markdown
- UI 主题整体更换为「青云素雅」：主色靛蓝（浅色 `#4f46e5` / 暗色 `#6366f1`），辅助色换点缀橙 `#f97316`，图表色环靛蓝锚点重排，阴影整体减淡转「微阴影 + 描边」形制，AntD 圆角 8→10；同时偿还风格债务——16 个文件残留的 `@ant-design/icons-vue` 全部迁移至 `@lucide/vue`（依赖移除），约 24 个文件的硬编码色值收编至 CSS 变量（值不变纯重构）。字体、头像套图、深色模式三底色不变。设计文档见 `docs/superpowers/specs/2026-09-29-qingyun-theme-retheme-design.md`。
```

- [ ] **Step 5: 台账收尾**（memory.md 会话行 + cerebrum 若有新知）+ chore commit
- [ ] **Step 6: 双端同步**：sync-dev 收敛冒烟（零差异）→ 官方链重建 localized 镜像（fetch/reset/rename/commit/branch -f）→ push（GitHub 网络恢复后；`pisuan-custom` 先推，镜像 `--force-with-lease` 后推）

---

## Self-Review 记录

1. **Spec 覆盖**：Token 五类值（main/second/chart/shadow/radius）→ Task 3/4/5；色值收编 → Task 1/2；图标迁移 → Task 7；品牌页 → Task 6；验收机检 + 7 页巡检 + 同步 → Task 8。无缺口。
2. **占位符扫描**：映射表均为完整值；「以实际 grep 输出为准」处均为防御性核对（现值漂移），非 TBD。
3. **一致性**：Task 1 留下的 `TODO(task4)` 标记在 Task 3 Step 4 收口；Task 2 留给 Task 6 的品牌页文件在 Task 6 处理；图标 size 依赖 Task 7 Step 3 第 3 条的 font-size 核对规则。无名称冲突。
