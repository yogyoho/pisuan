# 青云素雅主题换肤 — 设计文档

- 日期：2026-09-29
- 状态：设计已确认（对话决策：方向 D + 浅色侧栏 + 范围 C）
- 关联：`docs/vibe/2026-09-27-ui-retheme-tech-blue.md`（上一轮科技蓝换肤，本次为其同构迭代）
- 可视化规范：`.superpowers/brainstorm/90-1790660812/content/token-spec.html`（视觉伴侣会话存档）

## 1. 背景与目标

平台现有「科技蓝」主题（Tailwind blue `#2563eb` + shadcn zinc 中性色）需整体更换为「青云素雅」方向：靛蓝主色 + 纯白浮面 + 极浅灰背景 + 大圆角 + 微阴影描边（Linear/Notion 式现代 SaaS 工具感）。侧栏保持浅色。

除换肤外，本次同时偿还两类风格债务：残留的第二图标库（`@ant-design/icons-vue`）与散落在组件中的硬编码色值——二者是「克制精致」观感的主要破坏点。

**不做的事**（明确排除）：字体更换（沿用 Inter Variable + Noto Sans SC）、头像套图更换（thumbs 不动）、深色模式三底色调整（zinc-950 系保持现状）、后端任何改动、多主题运行时切换（本次仍为单一静态主题）。

## 2. Token 规范（唯一色值依据）

### 2.1 主色阶（--main-*，Tailwind indigo 映射）

| 档 | 值 | 档 | 值 |
|---|---|---|---|
| 50 | `#eef2ff` | 500 | `#6366f1` ★深色主色 |
| 100 | `#e0e7ff` | 600 | `#4f46e5` ★浅色主色 |
| 200 | `#c7d2fe` | 700 | `#4338ca` |
| 300 | `#a5b4fc` | 800 | `#3730a3` |
| 400 | `#818cf8` | 900 | `#312e81` |

- `theme.js`：浅色 `colorPrimary: #4f46e5`，深色提亮 `colorPrimary: #6366f1`（与现有 blue 双主色机制同构，暗色由 darkAlgorithm + 显式覆盖实现）
- `colorLink/colorLinkHover/colorLinkActive` 指向 `var(--main-*)` 的接线保持现有模式

### 2.2 中性色与背景层次（zinc 系）

| 角色 | 浅色 | 深色 |
|---|---|---|
| 页面底 `--page-bg` | `#fafafa`（zinc-50，由现值调整） | `#0a0a0a`（保持） |
| 浮面/卡片 | `#ffffff` | `#18181b`（保持） |
| 次级浮面 | `#f4f4f5`（zinc-100） | `#262626`（保持） |
| 描边 | `#e4e4e7`（zinc-200） | `#2a2a2e` |
| 正文/标题 | `#18181b`（zinc-900） | `#f4f4f5` |
| 次级文本 | `#71717a`（zinc-500） | `#a1a1aa` |

### 2.3 形制

- **阴影**：整体减淡，卡片从扩散投影改为 `0 1px 2px rgba(0,0,0,.05)` + 1px `#e4e4e7` 描边；弹窗/浮层保留大投影（6 档 shadow 变量逐档复核）
- **圆角**：AntD `borderRadius` token 8 → **10**；CSS 卡片圆角 12；图标容器 16
- **侧栏**：浅色白底 + 右侧 1px 描边，无投影（现状描边色跟随 `--line` 更新）

### 2.4 图表 10 色（--chart-1..10，靛蓝锚点）

`#4f46e5` indigo / `#0ea5e9` sky / `#8b5cf6` violet / `#14b8a6` teal / `#f59e0b` amber / `#f43f5e` rose / `#06b6d4` cyan / `#10b981` emerald / `#d946ef` fuchsia / `#64748b` slate

### 2.5 语义色与点缀

- 语义色保持不变：success `#16a34a` / error `#dc2626` / warning `#d97706`
- 新增点缀橙 `#f97316`（徽标/强调场景；对应现有 second/辅助色变量的值替换）

### 2.6 不变项

字体（Inter Variable + Noto Sans SC 及其加载方式）、lucide `stroke-width 2`、thumbs 头像套图、深色模式三底色。

## 3. 实施架构（五步提交，每步独立可验证可回滚）

| 步 | 内容 | 触碰 | 验证 |
|---|---|---|---|
| ① | 硬编码色值收编：24 文件裸 hex → `var(--*)`（**值不变纯重构**） | ~24 文件 | 视觉零变化（改前改后截图对比）+ `pnpm lint` |
| ② | 换肤：`base.css` / `base.dark.css` 变量值 + `theme.js` token（色板/圆角/阴影） | 3 文件 | 7 关键页 × 明暗截图巡检 |
| ③ | 图标迁移：16 文件 `@ant-design/icons-vue` → `@lucide/vue` | 16 文件 | 每文件 lint + 图标视觉核对 |
| ④ | 品牌页对齐：`HomeViewV2.vue` / `HomeView.vue` / `LoginView.vue` 主题色引用跟随新主色 | 3 文件 | Landing/登录页截图 |
| ⑤ | 双端同步 + changelog + `[pisuan-custom]` 标记补全 | — | sync-dev 收敛 + 官方链镜像 |

顺序理由：先还债（①）再换值（②），换肤时不存在漏网旧色值；③ 独立于配色放最后，随时可做可回滚。

### 3.1 图标迁移方案（步骤③细则）

- 逐文件枚举 antd 图标 → lucide 语义映射（如 `PlusOutlined`→`Plus`、`SearchOutlined`→`Search`、`DeleteOutlined`→`Trash2`）；无一一对应的取最接近语义者并在行内注明
- 尺寸核对：antd 图标为字体图标（`font-size` 控制），lucide 为 SVG（`size` prop / `width`/`height`）——迁移时逐一核对容器尺寸，避免视觉大小跳变
- 迁移后 `package.json` 移除 `@ant-design/icons-vue` 依赖（若归零）

### 3.2 色值收编原则（步骤①细则）

- 有语义的色值 → 收编到 `var(--*)`（如品牌蓝、灰阶、语义色）
- 无语义的一次性装饰色（如特殊渐变端点）→ 保留，行内注释说明原因
- 白名单：`base.css` / `base.dark.css` 本身（变量定义处允许裸值）

## 4. 约束

- `base.css` / `base.dark.css` 为上游保护文件：改动行全部带 `[pisuan-custom]` 行内标记；变量名不变、只改值，上游 rebase 冲突按同步指南既有套路解决
- `backend/package/yuxi/config/static/info.template.yaml`（华宇页脚）不碰
- 上次科技蓝换肤在 `theme.js` 留有 `// [pisuan-custom]` 注释锚点，本次在原锚点上更新值，保持注释的同步提示语义

## 5. 验收标准

1. **机检**：`web/src` 内裸 hex 计数（`base.css`/`base.dark.css` 白名单外）= 0；`@ant-design/icons-vue` 引用 = 0；`git grep -c '\[pisuan-custom\]'` 计数不减
2. **视觉**：Landing / 登录 / 工作台 / 对话 / 知识库 / 领域工厂 / 管理后台 共 7 页 × 明暗两态截图巡检
3. **回归**：`pnpm lint` 通过；后端零改动（无测试影响）
4. **同步**：sync-dev 收敛轮零写入；官方链镜像重建后 `[pisuan-custom]` 标记文件数与 pisuan 一致

## 6. 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 方向 | D · 青云素雅 | 用户从 4 候选中选定（对照 A 墨青商务 / B 曙光暖橙 / C 暗夜科技） |
| 侧栏 | 浅色 | 用户明确指定 |
| 范围 | C（配色+形制+图标+收编） | D 方向卖点「克制精致」依赖形制统一；两笔债务机械性强风险低 |
| 字体 | 沿用 | 中文切片加载成本最低，方向卡片已注明默认 |
