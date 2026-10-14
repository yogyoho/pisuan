# 知识工厂首页重设计：Landing 化 + 通用域模块化

日期：2026-10-14 ｜ 状态：已确认（brainstorming 闭环，会话 .superpowers/brainstorm/793-1791972344）

## 目标

将 `/domain-factory`（知识工厂首页）从「工作台形态」（hero + 三 tab）重设计为**纯 Landing 页**，
视觉语言对齐站内新 Landing `HomeViewV2.vue`（5173 实况，白底极简 + 拟真窗 hero + 橙色点睛 + 深靛蓝 CTA）。
原有工作台内容独立为与环评域平级的**通用域**模块。

## 已确认决策

1. **通用域独立模块**：数据源管理 / ETL 清洗工作台 / 归属管理 三块升级为「通用域」，与环评域平级、不交叉（不嵌入 EiaDataLayout）。
2. **统计移入通用域**：已入库任务 / 实体 / 学习模板三卡不再出现在首页，移入通用域「数据统计」屏。
3. **工具移入通用域**：Prompt 管理 / 大纲模板 / 实体构建器（admin）+ 规范库加工（全员）入口移入通用域侧栏。
4. **首页 = Landing**：HomeViewV2 配方 + B 叙事结构（hero → 机制指标带 → 四步工作流 → 领域入口 → CTA）。
5. **通用域壳 = EiaDataLayout 同款 chrome**（216px 侧栏 + 分组导航 + 返回知识工厂），路由 `/domain-factory/general/*`。
6. 通用域内部领域选择器保留（后端管线必填属性，不影响模块定位）。

## Landing 页内容定稿

- **Hero**（lp-hero 左文右窗）：橙 pill badge「DOMAIN KNOWLEDGE FACTORY」+ H1「领域知识工厂」+ 副标 + 双 CTA（进入通用域 / 了解加工流程锚点）+ ✓ 三特性点 + 右侧「知识加工工作台」拟真窗（加工队列状态点 + 文档骨架 + 入库 pill）+ 两浮动徽章。
- **机制指标带**（lp-metrics）：5 步加工流水线 / 双屏人机校验 / 3 层入库沉淀 / 模板实体复用（纯机制口径，不放运营统计）。
- **工作流**（lp-steps，id=workflow，tint 底）：kicker「工作流程」+「四步，从语料到资产」；四卡可点直达对应屏：上传语料→数据源管理、ETL 清洗→工作台、归属沉淀→归属管理、写手消费→环评域。
- **领域入口**：kicker「领域入口」+ 三大卡（通用域 5 chips / 环评域 8 chips / 矿井域虚线占位），chips 屏级直达，平台工具 chip 带 admin 徽标。
- **CTA 大块**（lp-cta）：深靛蓝渐变，白按钮进通用域 + 描边浏览环评域。
- **Footer**：一行 copyright（infoStore）。

## 路由与文件改动

```
/domain-factory                → DomainFactoryView.vue（重写为 Landing）
/domain-factory/general        → GeneralLayout.vue（新壳，components/factory-core/）
  ├─ ''                        → GeneralDataView.vue（数据源管理 = DataSourceDashboard 容器）
  ├─ workbench                 → GeneralWorkbenchView.vue（EtlWorkbench 容器；query.task 下钻）
  ├─ attribution               → GeneralAttributionView.vue（RegionAttributionPanel 容器）
  ├─ stats                     → GeneralStatsView.vue（新屏：三统计卡，P2 metric-strip）
  ├─ prompt-config             → PromptConfigView.vue（admin，原路由迁入）
  ├─ outline-template          → DomainOutlineTemplateView.vue（admin，迁入）
  └─ entity-builder            → DomainEntityBuilderView.vue（admin，迁入）
/domain-factory/eia-data/**    → 不动
旧路径 redirect：/domain-factory/prompt-config|outline-template|entity-builder → /general/* 同名
规范库加工：RegulationEnrichPanel 保持抽屉形态，入口提升至 GeneralLayout 侧栏（不建屏）
组件迁移（实现期修订）：三个 tab 组件不搬目录——`components/domain-factory/` 目录名本就通用，搬移只有 churn 没有收益；
GeneralLayout 新建于 `components/factory-core/`，四个容器/新屏 view 落 `views/`
```

## 验收标准（checklist）

- [ ] `/domain-factory` 渲染 Landing 五区，无统计卡、无工具按钮、无 tabs
- [ ] Landing 各 CTA/chip/步骤卡路由正确（含 admin 可见性：平台工具 chip 与侧栏 admin 组仅 admin 可见）
- [ ] 通用域四屏（数据源/工作台/归属/统计）功能等价迁移，任务下钻链路可用
- [ ] 旧路由 redirect 生效；eia-data 子应用不受影响
- [ ] 浅/暗两主题核对（token 翻转，无白底穿帮）；`prefers-reduced-motion` 禁动效
- [ ] `pnpm run lint` 通过；changelog 已更新

## 明确不做

- 不改 API 与后端；不改 eia-data 各屏；不做「应用中心」；统计/工具不加回首页

## 修订 [2026-10-14]：布局差异化 → A 立式流水线（已实现）

用户验收首版反馈：「效果还行，但与本系统首页太相似」。经可视化伴侣出三方案（A 立式流水线 / B 分屏双域 / C 蓝图图纸，原型存 `.superpowers/brainstorm/4341-1791977035/content/proto{A,B,C}-landing.html`），用户选定 **A 方案**：无营销 hero / 拟真窗 / 三列卡组 / 深色 CTA，页面骨架即装配线——

1. 顶部紧凑工作台横带（左品牌 + 右双 CTA，非居中 hero）
2. 装配线主轴：虚线传送带 + 流动件（reduced-motion 禁）+ 四工位卡上下交错（`STATION 01-04` 即四大屏入口，窄屏退化为常规网格）
3. 设备铭牌带：机制口径四格（PIPELINE/REVIEW/STORAGE/REUSE 双刻线铭牌样式）
4. 工位名录：三横带 + 屏级 chips（与首版权利映射一致）
5. 收工带（流水线已就绪 + 双按钮）+ footer

五区路由映射、admin 可见性、通用域四屏均不变。token 勘误：`--main-*` 实为青云靛蓝（main-600 #4f46e5）、`--second-*` 为点缀橙（#f97316），原型稿近似色已全部正名映射。

## 修订 2 [2026-10-14]：二轮精修（用户反馈「太单调」）

结构与路由不变，纯视觉/交互增强：

1. 传送带实体化：2px 虚线轨 → 6px 带体（灰阶 token）+ 滚动刻度内层 + 进料口箭头 + 靛蓝投影；流动件由 8px 圆点升级为发光胶囊
2. 工位卡：新增 Lucide 图标块（Inbox/Workflow/Database/PenLine）、卡角大序号水印、hover 顶部靛蓝→橙流光条 + 呼吸工位节点灯（错峰 0.7s）
3. 顶部横带：背景对齐系统首页 hero 同款配方（右上 main-100 光晕 + 左下 second-50 光晕 + 32px 方格网，HomeViewV2 .lp-hero 原样）+ 「管线运转中」呼吸灯 + 机制速览
4. 铭牌金属化：渐变面 + 内高光 + 双铆钉；p-value 换 main-700 提色
5. 收工带：顶部斜纹加工带 + 右侧橙色氛围 + 「PIPELINE READY」大水印 + 旋转「入库即精品」印章
6. 交互：主按钮 hover 流光扫过、工位卡/名录横带补 tabindex+enter 键盘可达（role=link）、chip hover 上浮

全部新动效（带体刻度/呼吸灯/流光）纳入 `prefers-reduced-motion` 禁用清单；色仅用 base.css token（靛蓝 rgba 走 `--main-color-rgb`（明暗双档已定义）、橙无 rgb 档走实体 token/`color-mix`），无裸 hex 语义色。
