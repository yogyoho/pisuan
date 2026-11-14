# 通用域知识工厂 UI 对齐环评域设计系统

状态：implemented
类型：feature
Owner：web/src/components/factory-core/factory-ui.less（共享配方真源）；web/src/components/domain-factory/*（通用域页面形状）；docs/develop-guides/data-factory-ui.md（配方语义）

## 问题

通用域知识工厂（`/domain-factory/general/*`）各页面（数据源管理、ETL 清洗工作台、归属管理、Prompt 管理、大纲模板、实体构建器）沿用了各自的视觉语言：带阴影的面板、圆角胶囊按钮、AntD 默认色 tag 与自造的筛选控件，与环评域知识工厂已评审定稿的数据工厂设计语言（`factory-ui.less`：page-head 点阵页头、三档按钮、pill/dot、扁平卡片、seg 分段器）不一致，双域并存时观感割裂。

## 决策

`factory-ui.less` 从 `web/src/components/eia-data/` 上移至 `web/src/components/factory-core/`，作为环评域与通用域共用的唯一配方真源；环评域 11 个面板仅更新 `<style src>` 引用路径，配方内容不变。通用域各功能页以 `.ewp` 为根容器，页头统一为 `.page-head`（点阵底纹 + 34px 图标位 + ph-actions），区块统一为 `.card/.card-hd/.toolbar`，筛选控件收敛到 `.seg`，状态表达收敛到 `.pill/.dot`，破坏性操作使用 `.btn-danger`（红底 + 确认弹窗）。需要排序/分页/行选择的 `a-table` 由 factory-ui.less 新增的 `.ewp .ant-table-wrapper` 观感对齐段统一贴齐 §3.6 表格配方；简单只读列表继续走自绘 `.tbl`。GeneralLayout 画布改为零内边距，由各页面 `.ewp` 自带 20/24/40 边距（与 EiaDataLayout 同构）；总览 Landing 保持全幅直出，不纳入本次数据面板对齐范围。

### 实现方案

- 共享层：`factory-core/factory-ui.less` 同时被环评域面板（`../factory-core/factory-ui.less`）与通用域页面/子组件引入；非 scoped 注入靠 `.ewp` 命名空间防泄漏。
- 通用域页面：`DataSourceDashboard`（自绘表格 + 卡片头）、`RegionAttributionPanel` 及四个子表（page-head + seg + card + pill）、`PromptConfigView`（seg 四分段 + card 编辑器 + slot-chip 变量钮）、`DomainOutlineTemplateView`/`DomainEntityBuilderView`（page-head + 面板边框化 + flex 撑满）、`EtlWorkbench`（page-head 同款头部 + a-card/a-button 深度覆写到三档按钮配方）。
- 视觉契约不变式：hover 只变色（0.15s，表格行 0.12s）、数字 tabular-nums、mono 仅技术标识、暗色按 §5 三条映射换档。

## 替代方案

- 各通用域页面继续维护独立样式：拒绝——双域视觉契约漂移，成本随页面数线性增长，且违背「数据工厂 UI 规范适用于后续领域」的既定约定。
- 复制一份 factory-ui.less 到 domain-factory 目录：拒绝——两份配方必然漂移，无单一语义 Owner。
- 把 AntD 组件全部替换为自绘控件以像素级复刻环评面板：拒绝——超出外观对齐的验收范围，破坏 a-table 的排序/分页/行选择语义；采用观感对齐配方（规范 §6 的既有映射）。

## 后果

`.ewp` 内的 `a-table` 观感由共享配方统一（含环评域未来新增表格），改动表头样式需回归两条主链路；子组件独立引入 factory-ui.less 是有意为之（子组件可脱离父容器独立复用），代价是同一页面多次注入同一全局样式（构建去重，运行时无重复规则）。`.btn-danger` 成为破坏性操作的唯一样式出口。总览 Landing 与 OutlineTemplate 组件内部旧样式保持原状，是本次显式非目标。

## 验证

- `docker compose exec web pnpm run lint:check`（改动文件单测 eslint 通过；全量失败源自容器内 dist-prod 产物，为既有环境问题，与本变更无关）。
- `docker compose exec web pnpm run build` 构建成功。
- 11 个环评面板 diff 经字节级比对均为单行引用路径变化；`factory-ui.less` 上移无内容漂移（仅新增 a-table 对齐段）。
- 真实页面浅/暗色截图验证尚未执行，列为未验证范围；合并前需按 web/AGENTS.md 补齐 7 条路由的可视验证。
