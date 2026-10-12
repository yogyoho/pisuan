# 数据工厂 UI 规范

本文档将从 [环评数据工厂 P2 高保真原型](../vibe/prototypes/2026-10-12-eia-p2-ui.html)（已评审通过的设计语言）提炼的组件配方固化为规范，适用于领域数据工厂系列页面（环评及后续领域的知识库工厂界面）。全站通用原则、token 用法与 Do/Don't 见[界面设计规范](./design)，本文不重复；两者冲突时以 design.md 为准。

设计令牌唯一来源是 `web/src/assets/css/base.css` / `base.dark.css`。原型 HTML 中的 `--warn-50`、`--mono` 等变量是原型自建的别名层，**实现时禁止照抄别名**，按下表换算为 base.css 正名。

## 1. 原型别名 → base.css 正名映射

| 原型别名 | base.css 正名 | 说明 |
| --- | --- | --- |
| `--text` / `--text-2` / `--text-3` | `--color-text` / `--color-text-secondary` / `--color-text-tertiary` | 文本三级 |
| `--hairline` | `--gray-200` | 通用边框/分割线 |
| `--success-50` / `-500` / `-700` | `--color-success-50` / `-500` / `-700` | 成功态 |
| `--error-50` / `-500` / `-700` | `--color-error-50` / `-500` / `-700` | 错误态 |
| `--warn-50` / `-700` / `-900` | `--color-warning-50` / `-700` / `-900` | 警告/待办态 |
| `--info-50` / `-700` | `--color-info-50` / `-700` | 信息提示 |
| `--second-50` / `-500` / `-600` / `-100` | 同名存在（base.css `--second-*`） | 点缀橙，仅警示/强调 |
| `--mono` | `'JetBrains Mono', Consolas, monospace` | 见先例 `DatasetStatsPanel.vue` `.ds-mono` |
| `--shadow-pop` | AntD 浮层默认阴影 | 不自造阴影常量 |

## 2. 版面骨架

- 页面容器：`max-width: 1180px`，`padding: 20px 24px 40px`；数据密度优先，不做营销式大留白。
- **页头卡（page-head）**：白底 + 1px 边框 + 8px 圆角的卡片，底纹为 22px 网格点阵（`radial-gradient(circle at 1px 1px, var(--main-200) 1px, transparent 0)`，暗色用 `--main-100`），上叠左→右渐变扫白（`linear-gradient(90deg, var(--gray-0) 0%, var(--gray-0) 55%, transparent 100%)`），保证左侧文字可读。结构：34px 主色浅底圆角图标位（`--main-50` 底 + `--main-600` 图标，暗色 `--main-100` 底）+ 16px/600 标题 + 12px 三级色副标 + 右侧操作区。先例：`EiaSectionsView.vue`。
- 区块间距 12px；页头与内容区之间 12px。

## 3. 组件配方

以下尺寸为原型实测值。class 名是原型参考名，Vue 落地放 scoped less（组件内前缀随意，但配方值不变）。

### 3.1 按钮（三档 + sm）

| 档 | 配方 | 用途 |
| --- | --- | --- |
| 主 `btn-pri` | 高 30px，`padding: 0 12px`，圆角 6px，13px，`--main-color` 实底白字（暗色字用 `#0a0a0a`），hover `brightness(1.08)` | 每屏唯一主操作（导出物化、保存） |
| 次 `btn-sec` | 白底 1px `--gray-200` 边框，`--color-text-secondary` 字，hover 边框 `--main-400` + 字 `--main-600` + 底 `--main-10` | 返回、次要操作 |
| 文本 `btn-txt` | `--main-600` 字，`padding: 0 6px`，hover 底 `--main-50` | 表格行内操作 |
| 小 `btn-sm` | 高 26px，`padding: 0 9px`，12px 字 | 密集区（chips 行、行内） |

### 3.2 pill 状态标签与 dot 状态点

- pill：高 20px，`padding: 0 8px`，圆角 999px，12px/500，浅底深字。六变体：主色（`--main-50`+`--main-600`）、成功、警告、错误、灰（`--gray-100`+`--gray-600`）、橙（`--second-50`+`--second-600`）。
- dot：6px 圆点 + 3px 同色光环（`box-shadow: 0 0 0 3px color-mix(in srgb, <色> 18%, transparent)`）。绿=就绪，橙=待办，灰=无。用于列表项右上角或 fam 项内，不与 pill 表达同一状态。

### 3.3 输入框

高 30px，1px `--gray-200` 边框，圆角 6px，13px，白底；focus 边框 `--main-500` + `box-shadow: 0 0 0 2px var(--main-50)`（暗色 ring 用 `--main-100`）；placeholder 用三级文本色。

### 3.4 卡片与卡片头

- 卡：`--gray-0` 底 + 1px `--gray-150` 边框 + 8px 圆角，无阴影。
- 卡头 `card-hd`：`padding: 12px 16px`，下边框 1px；14px/600 标题 + 12px 三级色副标（`hd-sub`）+ 右侧操作区（`hd-right`，`margin-left: auto`）。

### 3.5 指标带（metric-strip）

横向 grid（`grid-auto-flow: column; grid-auto-columns: 1fr`），格间 1px 左边框；每格 `padding: 13px 18px`，12px 三级色标签在上、22px/700 数值在下。纪律：

- 数值必须 `font-variant-numeric: tabular-nums`，单位用 `<small>`（12px/400 三级色）。
- 强调格：左侧 2px 主色竖条（`::before`，`--main-500`，上下留 12px）。
- 告警格：数值直接用 `--second-600`（橙），不加底色。

### 3.6 数据表

- 表头：12px/500 三级色，`padding: 9px 12px`，下边框 1px，`white-space: nowrap`。
- 单元格：13px，`padding: 9px 12px`，下边框 `--gray-100`；行 hover 底 `--gray-50`（transition .12s）。
- 数值列右对齐 + tabular-nums。
- **警示行**（如 unmapped）：整行 `--second-50` 底 + `border-bottom: 1px dashed var(--second-100)`（暗色底 `--second-100`），hover 保持橙底不变灰。
- 表脚 `tbl-foot`：`padding: 9px 16px`，12px 三级色，承载口径说明/合计。

### 3.7 筛选 chip 与分段器

- `stage-chip`：高 28px，`padding: 0 12px`，圆角 6px，1px 边框白底，12px 次级色字；可带计数（`cnt` 11px 三级色 tabular）。选中态：底 `--main-50`（暗 `--main-100`）+ 边框 `--main-400` + 字 `--main-600` + 600 字重。
- `src-chip`：高 22px 圆角 999px，内嵌 `b` 计数（11px 主色 tabular）；高亮态边框 `--main-300` 底 `--main-10`。
- `seg` 分段器：外层 1px 边框圆角 6px，按钮间 1px 分隔；选中同 stage-chip 选中态。少量互斥视图切换用 seg，多目标筛选用 chip 组。

### 3.8 split 左右布局

`grid-template-columns: 264px 1fr; gap: 12px`。左列表（搜索头 + 滚动区）+ 右详情卡。列表项：

- `padding: 8px 12px`，13px，底边框 `--gray-100`，hover 底 `--gray-50`。
- 选中态：底 `--main-50`（暗 `--main-100`）+ `box-shadow: inset 2px 0 0 var(--main-500)` 左侧主色条，**不改字重不加粗**。
- 待办项缀 5px 橙色 mini-dot；计数右对齐 11px 三级色 tabular。

先例：`SectionsPanel.vue`（族列表）、`EntitiesPanel.vue`（样例清单）。

### 3.9 体检卡（gate1-card）

页头顶部横卡：30px 主色 badge 位 + 14px/600 标题 + 副标；下方三等分指标格（`padding: 11px 16px`，格间左边框），每格 20px/700 数值（tabular）+ 12px 标签 + 右缘 11px 说明。数值语义色：归零/达标 `--success-700`，超限 `--second-600`，其余正文色。禁用区（如规则只读表）整块 `opacity: .45; pointer-events: none`。先例：`StandardsPanel.vue` 门 1 体检卡。

### 3.10 公式/表达式暗色块（expr-block）

`--gray-1000` 深底、圆角 8px、`padding: 16px 18px`、mono 13.5px、行高 1.9、字色 `#e4e4e7`；token 着色：函数 `--main-300` 紫、变量 `--second-500` 橙、运算符 `--gray-500`、注释 `--gray-700` 缩小；右上角 11px 只读角标（`ro-tag`）。深浅模式都保持深底（表达式块是"代码展品"，不随主题翻转）。只读边界说明配 note-bar 放块下方。

### 3.11 技术标识徽标

- `slot-chip`：mono 11px，`--main-50` 底（暗 `--main-100`）+ `--main-700` 字（暗 `--main-300`），圆角 4px，`padding: 1px 6px`。用于 slot 路径、字段名。
- `code.k`：mono 12px，`--gray-100` 底 + `--gray-700` 字（暗 `--gray-300`），圆角 4px。用于普通标识。
- `tier` 徽标：mono 11px/600，高 19px，圆角 4px；档位色：required 主色系、contextual `--color-info-50`+`-700`、optional 灰系。

### 3.12 可点卡片网格（layer-grid）

三列 grid（`repeat(3, 1fr); gap: 12px`），卡 `padding: 14px 16px` 纵向布局：13px/600 名称 + mono 11px 键名 → 20px/700 计数（tabular，`<small>` 单位）→ 12px 三级色描述。可点卡 `cursor: pointer`，hover 边框 `--main-400`（只变色，不加阴影不位移）。不可用层 `opacity: .4; pointer-events: none`。总览页分层入口、chip 直达目标页皆此配方。先例：`DatasetStatsPanel.vue`。

### 3.13 弹窗与抽屉

| 浮层 | 规格 | 落地 |
| --- | --- | --- |
| modal | 宽 560px（`max-width: 92vw`）上浮 9vh；头 `padding: 14px 20px` 15px/600 标题；脚 `padding: 12px 20px` `--gray-25` 底右对齐；表单行 label 12px/500 + 必填红星 + 12px helper | `a-modal`（宽 620 时含内边距取整） |
| drawer | 右侧 600px（`max-width: 94vw`），scrim `rgba(0,0,0,.45)`；头 `padding: 14px 18px`；体滚动；脚 12px 三级色说明条（如「只读通道」） | `a-drawer`（width 600） |

表单弹窗若从警示行进入，顶部放橙色来源框 `from-unmapped`（`--second-50` 底 + 1px `--second-100` 边框 + 12px `--second-700` 字，暗色边框 `--second-600`）。

### 3.14 提示条与折叠分组

- `note-bar`：`--color-info-50` 底，圆角 6px，`padding: 9px 12px`，12px `--color-info-700` 字，16px 图标上缘对齐首行。用于只读边界、口径说明。
- 折叠组 `ch-row/ch-hd`：头行 `padding: 11px 16px` 13px/600 标题 + 12px 三级色计数 + 右缘 meter；chevron 15°→90° 旋转（transition .15s）；展开体 `padding: 2px 16px 12px 38px`（缩进对齐标题文字）。行间 `border-top: 1px dashed var(--gray-100)`。

### 3.15 微进度条（meter）

5px 高 × 64px 宽，圆角 3px，`--gray-100` 底 + `--main-500` 填充；低于阈值换 `--second-500`。仅在折叠头、列表项等紧凑场景使用，不做大进度条。

## 4. 交互与排版纪律

- 所有 hover/选中反馈 transition `.15s`（表格行 `.12s`），**只变颜色（底/边框/文字）**，禁止位移、放大、阴影变化。
- focus 可见：输入类用主色 2px 浅 ring；按钮复用 AntD 默认。
- 数字（计数、指标、百分比）一律 `font-variant-numeric: tabular-nums`。
- mono 字体只用于技术标识：slot 路径、字段名、章节键、contract id；正文中文永不 mono。
- 正常态保持安静（正文色、无标记），只给异常/待办着色（橙点、橙底行、告警数值）。
- 图标 16px、stroke 2、`stroke: currentColor` 继承文字色；lucide 优先。
- 主操作每屏一个（主按钮），其余降级为次/文本按钮；破坏性操作红色 + 确认弹窗。
- 只读与可编辑必须视觉可分：只读区配 note-bar 说明或 ro-tag 角标，不靠灰色暗示。

## 5. 暗色模式映射

base.dark.css 已按 `:root.dark` 翻转同名 token，配方内的浅底色按下面三条互换即可：

| 浅色 | 暗色 | 场景 |
| --- | --- | --- |
| `--main-50` 底 | `--main-100` 底 | 选中底、badge 底、chip on、pill 主色 |
| `--main-600` 字 | `--main-400` 字 | 主色文字、图标 |
| `--main-color` 实底 + 白字 | 同底 + `#0a0a0a` 字 | 主按钮 |
| `--second-50` 底 / `--second-100` 边框 | `--second-100` 底 / `--second-600` 边框 | 警示行、来源框 |
| expr-block 深底 | 不变 | 表达式块 |

交付前按 design.md §2 暗色清单过一遍：无白底穿帮、hover/focus/选中态可辨。

## 6. Vue 落地映射

原型是静态 HTML 配方，实现按项目栈换算：

- **表格**：简单只读表用配方 CSS 自绘（先例 `DatasetStatsPanel.vue` `ds-*`）；需要排序/分页/滚动用 `a-table` + `#bodyCell` 定制（先例 `FormulasPanel.vue` inputs 表），列宽、字号按 §3.6 对齐。
- **chip / pill / seg**：纯 CSS 自绘（先例 `DatasetStatsPanel.vue` chip 直达与总览 LAYER_LINKS）；带状态语义的可换 `a-tag` 覆盖圆角与配色。
- **浮层**：`a-modal` / `a-drawer`，宽度与头脚 padding 按 §3.13；脚部说明条放 `#footer` 或 body 尾部 note-bar。
- **布局**：page-head / split / layer-grid / metric-strip 均为 grid+flex 纯 CSS，不引第三方。
- **API**：接口一律封装进 `web/src/apis/*`（数据工厂先例 `eia_data_api.js` 族）。
- **组件归置**：页面级放 `web/src/views/`，可复用面板放 `web/src/components/eia-data/`（后续领域仿此建目录）。

## 7. 实现检查清单

- [ ] 颜色全部来自 base.css 正名 token（对照 §1 映射表，无原型别名残留）。
- [ ] 浅/暗两套截图核对，§5 映射三条已覆盖。
- [ ] 数字 tabular-nums；mono 仅技术标识。
- [ ] hover 只变色；focus ring 可见；主操作唯一。
- [ ] 待办/异常态有着色表达且不单靠颜色（dot/pill/文字）。
- [ ] 空态有说明与下一步指引；只读区有 note-bar 或角标。
- [ ] 真实数据下检查长名称截断（省略号 + tooltip）与计数溢出。
