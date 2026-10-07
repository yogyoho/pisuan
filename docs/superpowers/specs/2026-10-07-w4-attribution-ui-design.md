# W4 归属管理 UI 设计

> **日期**: 2026-10-07 ｜ **状态**: 已评审（六项分叉经用户裁决，见 §8）
> **依据**: W3 spec §4.2 L3（UI 归 W4）、roadmap v2 §4.2「WAITING_REVIEW 界面确认，可批量改判」/§4.3「泄漏处置=批量退役」；本日文档驱动词表提取（4 文档 53 候选）
> **前窗**: W3 scope×region 事实维度落库（bef9d9d0 收口，confirm-region/retire API 已就位）

## 1. 背景与目标

W3 已落库归属判定全链（Task+4 列、regional_facts 表、confirm-region 级联、retire API），但**无任何界面**：任务归属不可见、改判靠脚本、区域事实不可浏览、泄漏退役无人工通道、min-permissive 聚合结果不可观察。

**目标**：知识工厂新增「归属管理」tab——任务归属可视可改、区域事实可筛可退、聚合看板可读（含区域下钻），并补齐行政区辅助词表（W3 终审挂账②）。

**本窗 checklist（简要）**：
- [ ] 后端读接口三件套：任务归属列表 / 区域事实列表 / 聚合看板（3 个薄 GET，零 DDL）
- [ ] 行政区辅助词表：3+6 条落 `domain_factory_region.py` + L1 二级查找 + 单测
- [ ] 前端面板：RegionAttributionPanel 三子页（任务归属/区域事实/模板聚合）+ API 封装 5 方法
- [ ] 挂载：DomainFactoryView 第三 tab（纯增量 2 行）
- [ ] lint/format + 运行栈端到端冒烟 + changelog/勾账/终审

## 2. 范围

**In**：`backend/server/routers/domain_factory_router.py`（+3 GET）、`backend/package/yuxi/services/domain_factory_service.py`（+3 读 service 函数）、`backend/package/yuxi/repositories/domain_factory_repository.py`（+分页/聚合查询）、`backend/package/yuxi/services/domain_factory_region.py`（+ADMIN_REGION_VOCAB 及 L1 二级查找）、前端 5 新组件 + `domain_factory_api.js`（+5 方法）+ `DomainFactoryView.vue`（挂载）。

**Out**：批量改判（逐行打底，批量入口真用上再加，§8-3）；批量退役已有 API 但 UI 仅单批操作；roadmap §11 消费通道 W4（get_slot_registry/导出端点，另一条线不混窗）；词表管理 UI（常量人工维护）；learned_templates 历史回填。

**不变量**：**现有知识工厂功能零行为改动**（用户硬约束）——EtlWorkbench/DataSourceDashboard/confirm-entities 流不动；`DomainFactoryView.vue` 仅新增 1 个 a-tab-pane + 1 行 import；classify_tags 与 W3 归属主词表（REGION_VOCAB 17 条）语义零变动；本窗**零 DDL**（读接口无 schema 变更）；禁碰文件（HomeView/LoginView/base.css/base.dark.css/info.template.yaml）零卷入。

## 3. 设计输入（探索结论，行号为 2026-10-07 快照）

- **前端现状**：`DomainFactoryView.vue` hero 折叠 + a-tabs 双页（key=data→DataSourceDashboard / key=workbench→EtlWorkbench，#tab 具名插槽带 lucide 图标）；`domain_factory_api.js` 单例 `domainFactoryApi`（:114）~30 方法，`confirmProposedEntities`→POST confirm-entities（:252）
- **W3 端点响应键**（改判/退役 toast 数据源）：confirm-region → `{success, region_key, facts_confirmed, templates_recalculated}`（router:373-395，service:6478 返回键实测）；retire → `{success, retired}`（router:397+）；confirm-region 鉴权 get_required_user，retire get_admin_user
- **词表提取**（4 份总规环评全文，Workflow 4 代理，53 候选带原文证据）：横城归属链=宁夏→银川→灵武市→临河镇/宁东镇（两种乡镇表述并存均收）；伊宁北区归属链=新疆→伊犁州→伊宁县（主体）+伊宁市（紧邻北郊）+霍城县（保护区/水源地紧邻）；乡镇级强信号：喀拉亚尕奇乡/英也尔乡/曲鲁海乡。陷阱实录：「横城」地名本身属银川市兴庆区掌政乡，不在灵武市境（故不收横城村）；「灵武市」与灵武矿区同域（歧义交 L3 纠正）

## 4. 设计

### 4.1 前端组件树与挂载

```
DomainFactoryView.vue                仅 +1 a-tab-pane(key="region" tab="归属管理") + 1 行 import
└─ components/domain-factory/
   ├─ RegionAttributionPanel.vue     容器：a-tabs 三子页，默认选中「任务归属」
   ├─ AttributionTaskTable.vue       子页1：筛选 chips（全部/regional/project/universal/未归属）+ 关键词搜索
   │                                 + 表格（任务/领域/scope 徽标/region_label/region_key/任务状态/操作）；操作列文案：
   │                                 已归属→「改判」/ 未归属→「归属确认」（同一弹窗）
   ├─ AttributionEditModal.vue       改判弹窗：region_label(必填)/region_key(select 允许自定义
   │                                 + slug 校验 ^[a-z0-9-]+$)/scope(radio 三选+一句解释) + 级联后果提示
   ├─ RegionalFactsTable.vue         子页2：region×fact_type×status 三重筛选 + 表格
   │                                 + admin 勾选列与底部批量退役操作条（非 admin 纯浏览）
   └─ RegionBoard.vue                子页3：统计卡×3 + 聚合明细表 + 区域下钻树（T1 横排卡片+展开块）
web/src/apis/domain_factory_api.js   +5 方法：fetchAttributionTasks/confirmRegion/
                                     fetchRegionalFacts/retireRegionalFacts/fetchRegionBoard
```

- 样式用 `base.css` 颜色变量，图标 lucide-vue-next（tab 图标选 MapPinned 类，尺寸对齐既有两 tab）
- region_key 下拉候选 = `REGION_VOCAB` 全部键 + 任务表已用键去重并集，允许输入新 slug
- 空态文案：聚合明细（「新任务回写后出现」——211 存量模板 scope=NULL 为 W3 Q3 预期行为）

### 4.2 子页交互要点

- **任务归属**：改判成功 → toast「已归属 {region_key}：级联确认事实 {facts_confirmed} 条，重算模板 {templates_recalculated} 个」→ 原位刷新该行；失败 toast 后端 detail 原文（无静默兜底）
- **区域事实**：勾选 ≥1 且 admin → 底部操作条「批量退役」；确认后 toast「已退役 {retired} 条」→ 刷新列表；retired 状态行置灰可切换查看
- **模板聚合**（只读）：统计卡（模板×scope / 任务×region / 事实×状态）；明细表列=模板(章族/变体)/scope/region/归因集任务数/更新时间，倒序；下钻树 region 卡片（计数徽标：任务 N·事实 N·模板 N）点击展开摘要块，摘要块内「任务 N/事实 N」可点击并跳转对应子页且带上该 region 过滤

### 4.3 后端读接口三件套（router → service → repository，W3 分层）

| 端点 | 参数 | 返回 |
|---|---|---|
| `GET /domain-factory/tasks` | `scope`（universal/regional/project/unassigned）、`region_key`、`keyword`（file_name 模糊）、`page`/`page_size`（默认 1/20，上限 100） | `{items:[{id,file_name,domain,domain_label,status,project_name,region_label,region_key,scope,created_at}], total}`；`scope=unassigned` → `scope IS NULL` |
| `GET /domain-factory/regional-facts` | `region_key`、`fact_type`、`status`、`page`/`page_size` | `{items:[{id,fact_type,region_key,content,status,year,source_task_id,source_task_file_name,source_ref,created_at,updated_at}], total}`（service 层拼来源任务 file_name） |
| `GET /domain-factory/region-board` | 无 | `{stats:{templates_by_scope:{universal,regional,project,unassigned}, tasks_by_region:[{region_key,region_label,count}], facts_by_status:{draft,confirmed,retired}}, region_tree:[{region_key(null=未归属伪节点),region_label,task_count,fact_count,fact_counts_by_type:{monitoring,sensitive_target,measure,constraint},template_count}]}` |

- **模板 region 派生规则**（LearnedTemplate 无 region 列，W3 只加 scope）：明细表/树中模板的 region 由归因集派生——`extra_meta.contributing_task_ids` 对应任务的 `region_key` 去重后恰一个 → 该值；多个 → `"mixed"`；空集 → `null`（显示「未归属」）

- 三个 GET 均为 get_required_user；router 仿 W3 confirm-region 同款 try/except 骨架（400 参数/500 兜底，原文 detail）
- service：`list_tasks_with_attribution` / `list_regional_facts` / `build_region_board`（放 domain_factory_service.py，读路径不碰写状态）；repository：对应分页查询与 GROUP BY 聚合（数据量小：8 任务/211 模板，board 单响应一次返回，不做缓存）

### 4.4 权限模型（与 W3 API 严格对齐）

tab 与三子页可见=已登录；改判=已登录（API get_required_user）；**勾选列+批量退役仅 `userStore.isAdmin` 渲染**（API get_admin_user，前端只做展示层收敛，不做重复鉴权假设）。

### 4.5 C 行政区辅助词表（3+6 条，文档驱动提取已确认）

```python
# domain_factory_region.py —— [pisuan-custom] W4：行政区辅助词表（县/乡镇级）
# 来源：4 份总规环评全文提取（2026-10-07），证据与排除清单见 spec §3/§8-6
ADMIN_REGION_VOCAB = {
    "灵武市": "hengcheng",      # 强：归属链核心县级市（歧义：灵武矿区同域，L3 纠）
    "临河镇": "hengcheng",      # 强：「属灵武市临河镇管辖」
    "宁东镇": "hengcheng",      # 强：「矿区位于灵武市宁东镇」多语境
    "伊宁县": "yining-beiqu",       # 强：矿区主体所在县
    "伊宁市": "yining-beiqu",       # 中：紧邻北郊，部分设施在伊宁市界内
    "霍城县": "yining-beiqu",       # 中：保护区/水源地紧邻
    "喀拉亚尕奇乡": "yining-beiqu",  # 强：伊宁县辖
    "英也尔乡": "yining-beiqu",      # 中：伊宁市辖，井田相关
    "曲鲁海乡": "yining-beiqu",      # 中：伊宁县辖，水源地
}
```

- **L1 二级查找**：任务级归属判定函数中，`REGION_VOCAB`（矿区名，主命中）优先；无主命中时查 `ADMIN_REGION_VOCAB`，命中 → 同通道写三列 + scope=regional。既有主命中行为零改动；backfill 脚本复用同函数（只填 NULL，幂等不受影响）
- 单测：9 条收录词逐一命中断言；排除代表词不命中断言（定边县/博乐市/宁夏/萨尔布拉克镇）；二级查找触发与主命中优先断言

## 5. 执行序

| 任务 | 内容 | 验证 |
|---|---|---|
| T1 | 读接口三件套（repository+service+router） | 容器集成：分页/筛选/unassigned 语义/board 聚合值断言 |
| T2 | ADMIN_REGION_VOCAB + L1 二级查找 | 单测：9 命中+4 排除+主优先；backfill 幂等复跑 |
| T3 | API 封装 5 方法 + Panel 容器 + 任务归属子页 + 挂载 | pnpm lint + 运行栈冒烟（列表/筛选/改判级联 toast） |
| T4 | 区域事实子页（筛选+退役 admin） | 冒烟：非 admin 不可见操作列；admin 退役计数 toast |
| T5 | 看板子页（统计卡+明细+T1 下钻树） | 冒烟：空态文案；下钻跳转过过滤 |
| T6 | lint/format + changelog + 勾账 + 终审 | fresh-eyes 复验 |

T1→(T2∥T3)→T4→T5→T6；T2 纯后端常量与 T3 前端可并行。

## 6. 验收标准（DoD）

1. 三 GET 容器集成全绿：筛选/分页/unassigned 语义/board 计数与运行栈 DB 实况一致
2. 词表：9 命中+4 排除+主命中优先单测全绿；backfill 幂等复跑结果不变（8/8 regional）
3. 前端：`pnpm run lint` + `pnpm run format` 零错误；现有两 tab（数据源/ETL 工作台）回归冒烟无任何行为变化
4. 改判级联：改判一条任务 → toast 计数与 DB 一致（facts_confirmed/templates_recalculated 抽查）；slug 校验拒绝非法输入
5. 权限：admin 可见退役操作、非 admin 不可见；retire 调用仅 admin 触发
6. 看板：统计卡数值=DB 聚合实况；空态文案正确；下钻跳转带过滤
7. 不变量：零 DDL；禁碰文件零卷入；DomainFactoryView diff 仅 2 行增量；中文 Conventional 提交 + 明确 `git add`

## 7. 风险与挂账

- **灵武市歧义**（灵武矿区同域）→ 词表单层设计接受误判，改判 UI 兜底（本窗交付物本身）；若误判率显著，后续可加「强/弱信号分层」
- **region 增多后 T1 布局**→ >6 个 region 时组件内重排为左树右详情（T2 形态），接口不变
- **批量改判**→ 挂账，真需求出现时优先做「同区域归拢」形态（多选行+一弹窗，前端循环调单任务 API）
- **前端无单测惯例**→ 本窗沿用 lint+运行栈冒烟+E2E 手工清单；若引入 vitest 另立专项
- **roadmap §11 消费通道 W4**（get_slot_registry/导出）→ 不在本窗，独立排期

## 8. 裁决记录

| # | 分叉 | 裁决 | 理由 |
|---|---|---|---|
| Q1 | 窗口范围 | A+B+C+D 全做（任务归属面板/事实管理/行政区词表/聚合看板） | 用户拍板 |
| Q2 | UI 对接方式 | DomainFactoryView 第三 tab「归属管理」（自包含组件，纯增量） | 用户提议+编排方论证：触点最小、导航不分散；独立路由反而多 AppLayout/router 两触点 |
| Q3 | 批量改判 | 逐行打底，批量挂起 | 存量仅 8 任务且 L1 已全归属，批量真低频；API 循环可覆盖 |
| Q4 | C 词表内容来源 | 文档驱动：扫 4 份源文档提取→候选确认 | 用户选②（可复核）；产出 3+6 条已确认 |
| Q5 | 看板深度 | 统计卡+明细+区域下钻树（T1 横排卡片布局） | 用户选②；T1 因当前仅 2 region |
| Q6 | 架构形态 | 前端单面板组件 α + 后端三薄 GET α | 组件内聚、接口职责单一 |
