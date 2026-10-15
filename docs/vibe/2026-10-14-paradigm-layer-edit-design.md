# 写作范式层查询与编辑页（paradigm-layer edit）设计

日期：2026-10-14　|　状态：已实施（2026-10-14）
前置：方向 A 范式库 P0 已入库（[2026-10-07-direction-a-paradigm-library-design.md](2026-10-07-direction-a-paradigm-library-design.md)）；原型 s12/s13 已评审通过（`docs/vibe/prototypes/2026-10-12-eia-p2-ui.html`）

## 1. 背景与定位

方向 A 把行文范式固化为技能 references 层静态资产（`references/paradigms/*.md` 4 角色文件 + `_roles.json` 77 节映射 + `forms_catalog.json` 3 族句式），但三类资产**无任何 API / 写通道**——运营侧既看不到库里有什么，也没法修订。bug-367（写手「说明文腔」复发，occ=3）每次复发都要走「改文件 → 提交 → 回流运行栈」的工程通道，运营无法自助。

本设计给范式层补上**查询 + 编辑**页，沿用数据工厂已两次落地的**导出物化**通道（公式 inputs 覆盖、词表方案乙）：**DB 草稿是编辑的唯一真相，admin 显式导出才回写数据文件；UI 任何情况下不直接改文件**。文件仍是写手运行时读取的唯一来源，导出前写手行为不变。

## 2. 资产盘点与编辑边界

| 资产 | 内容 | 编辑边界 |
|---|---|---|
| `references/paradigms/{opener,baseline,analysis,measures}.md` | 四角色行文范式（适用/结构骨架/范文/节尾收束段/句式模式/反模式） | **整文件 Markdown 草稿**（用户裁决 ①）；写前校验锚点小节在位 |
| `references/paradigms/forms_catalog.json` | 3 族句式（caliber_disambiguation / numeric_citation / table_lead），各含 desc / templates / examples / stats | **仅 desc / templates 两键**（用户裁决 ②）；stats/examples 为 bank_compile 语料统计，只读 |
| `references/paradigms/_roles.json` | 77 节 → 角色映射 | **只读对照表**（用户裁决 ③）；角色错配=整节范式错注入，调整走 git 评审，不设 UI 编辑 |

## 3. 目标与非目标

**目标**
- G1 运营可在数据工厂查看三类资产全貌（角色挂载节数、句式族模板与语料统计）并修订可编辑部分。
- G2 草稿落库即时生效为「编辑真相」；导出前写手仍读文件旧版，重派确定性不受影响。
- G3 导出走「写前校验 → diff 预览 → admin 写入」安全阀（用户裁决 ④）：任一校验不过全批不写；未改动的文件与键保持字节一致（round-trip 纪律，不重排键序）。
- G4 与既有导出物化面板（公式/词表）交互一致：pending pill、导出物化按钮、admin-only。

**非目标**
- 不做 `_roles.json` 的 UI 编辑，不做 stats/examples 编辑。
- 不做草稿版本历史 / 多草稿并行（每资产至多一份活跃草稿）。
- 不自动同步 RESIDUE_RE（见 §8 同步纪律）。
- 不改技能侧读取方式——文件始终是技能运行时真相，skill 零改动。

## 4. 数据模型：单一通用草稿表

复用导出物化先例的「DB 层 + 文件锚点」形态，一张通用表承载两类资产：

```python
# backend/package/yuxi/storage/postgres/models_domain_factory.py 新增
class EiaParadigmDraft(Base):
    __tablename__ = "eia_paradigm_drafts"
    id: int            # PK
    asset_kind: str    # 'paradigm_md' | 'forms_catalog'
    asset_id: str      # 'analysis' 等 4 角色名 | 'table_lead' 等 3 族名
    content: JSONB     # paradigm_md: {"md": "<整文件文本>"}；forms_catalog: {"desc": str, "templates": [str]}
    base_hash: str     # 保存草稿时数据文件 sha256——导出时比对检测文件漂移
    created_by / updated_by: str
    created_at / updated_at: datetime
    # UNIQUE (asset_kind, asset_id) —— 每资产至多一份活跃草稿，保存即 upsert，撤回即删行
```

- `base_hash` 漂移语义：导出时重算文件哈希，≠ 草稿 `base_hash` 即「文件已漂移」（bank_compile 重算整文件重写 / 上游同步）→ 预览页示警并给出「以草稿为准恢复」的完整 diff，admin 确认后导出即恢复草稿为真。**skill 侧零改动**。
- forms_catalog 的漂移场景正是 bank_compile 重算：草稿只存 desc/templates，重算带来的新 stats 在导出时按「仅写两键」保留，互不覆盖。

## 5. API（挂 `server/routers`，薄层 + yuxi services）

前缀沿用数据工厂现有域路由命名（实现时对齐 `eia_formula` 路由形态），共 6 个：

| # | 端点 | 语义 |
|---|---|---|
| 1 | `GET /eia-paradigms` | 概览：4 md + 3 family 的草稿态（有/无、pending、drift）、角色挂载计数（读 `_roles.json`） |
| 2 | `GET /eia-paradigms/{kind}/{asset_id}` | 单资产：md 全文（草稿在则草稿+文件版对照元数据）；family 给 desc/templates（草稿在则草稿值）+ 只读 stats/examples。节角色对照数据（_roles 全映射）随概览返回，供范式页只读表格 |
| 3 | `PUT /eia-paradigms/{kind}/{asset_id}/draft` | 保存草稿（登录用户）：md 整文件 / 仅接受 desc+templates 两键，其余键拒收；upsert |
| 4 | `DELETE /eia-paradigms/{kind}/{asset_id}/draft` | 撤回草稿（删行，文件锚点不受影响） |
| 5 | `POST /eia-paradigms/export/preview` | 写前校验 + difflib 逐行 diff（**不写**）：返回每资产的校验结果与 diff 块 |
| 6 | `POST /eia-paradigms/export` | **admin-only** 物化：validate-all-then-write——任一资产校验不过 → 全批不写 |

服务层落 `yuxi/services`（新增 paradigm 服务模块），文件读写、哈希、diff、校验都在 service；路由只做解析/鉴权/装配。

## 6. 导出管线（validate-all-then-write）

**写前校验（全批与）**
1. paradigm md 锚点小节在位：`## 适用 / ## 结构骨架 / ## 范文 / ## 节尾收束段 / ## 句式模式 / ## 反模式`。
2. forms_catalog 拼装结果 JSON 可解析、templates 非空数组。
3. 专名扫描 0 命中（加固项，承方向 A A1 红线）：复用 P0 扫描规则（sample_entities 24 份黑名单聚合，≥3 份通用词子串豁免）扫草稿 md 文本；扫描器若为一次性脚本则此步先提升为可调用模块（工作量见 checklist）。
4. 漂移检测：文件哈希 ≠ 草稿 base_hash → 不阻断，标记 drift 并在 diff 顶部示警。

**写入（round-trip 字节纪律，与 formulas 导出同规）**
- md：整文件写回（草稿即全文，无拼接）。
- forms_catalog.json：按原文件字节载入（保持键序、不 sort_keys），仅替换有草稿 family 的 desc/templates 两键值，序列化格式（缩进/结尾换行）与原文件一致；**无草稿的 family 与 examples/stats 字节不动**。
- 任一文件写失败 → 已写文件回滚（先写临时文件再整体替换），保持「全批或全不写」。

**导出落点**：与 formulas/lexicon 一致写运行栈技能目录，前端提示「落运行栈，需人工回流 pisuan-custom 走 git 评审」。

## 7. 前端（数据工厂 · EiaDataLayout 新分组两页）

- 路由：`/domain-factory/eia-data/paradigms`（写作范式）、`/domain-factory/eia-data/forms`（句式范式），导航分组「写作范式层」，图标 notebook-pen / message-square-quote。
- 组件 `ParadigmsPanel.vue` / `FormsPanel.vue`：沿用 FormulasPanel/LexiconPanel 配方（`ewp` 命名空间 + factory-ui.less、fam-list 左列、page-head pending pill + 导出物化、admin-only 导出按钮）。
- API 封装 `web/src/apis/eia_paradigm_api.js`。
- **像素基准 = 原型 s12/s13 + exportModal**（评审通过，像素级复刻预期）；导出确认弹窗含 RESIDUE_RE 提示条（见 §8）。

## 8. RESIDUE_RE 同步纪律（人工，不联动）

方向 A §8 已定：反模式表与 `build_output.py` RESIDUE_RE 单一来源同步，「先门表后范式」。本设计**不做自动联动**，而在导出确认弹窗固化提示：「analysis.md 反模式表如有改动，需同步人工修订交付门残留词表（RESIDUE_RE）——先改门表，再同步范式」。原因：门是执法、范式是教学，自动联动会让「教学文本的措辞润色」误触执法词表变更，风险不对称。

## 9. 验收标准

| # | 验收项 | 通过标准 |
|---|---|---|
| A1 | 查询 | 概览/详情两页数据与文件实际内容一致（角色计数 12/17/37/11、3 族模板与 stats 同文件） |
| A2 | 草稿链路 | md 整文件保存/撤回、forms 两键保存/拒收其余键，`eia_paradigm_drafts` 每资产至多一行 |
| A3 | 导出安全阀 | 锚点缺失/JSON 不可解析/专名命中任一 → 全批不写且报错定位到资产；diff 与最终写入逐字节一致 |
| A4 | round-trip | 导出后无草稿文件哈希不变；forms_catalog 无草稿 family 与 examples/stats 键字节不变（git diff 仅两键行） |
| A5 | 漂移 | 人工改文件后导出：drift 标记出现，导出以草稿为准恢复且日志可追溯 |
| A6 | 权限与 UI | 导出仅 admin 可见可调；两页视觉过原型 s12/s13 比对 |

## 10. Checklist（实现分期，single plan）

1. [ ] 数据模型 + 迁移（eia_paradigm_drafts）→ verify: 迁移在 docker 内执行成功，唯一约束生效
2. [ ] service 层：读资产/哈希/校验/diff/splice 写入（含专名扫描器提升为可调用模块）→ verify: 单测覆盖 A3/A4 场景（含「键序不重排」「结尾换行一致」的字节断言）
3. [ ] 6 个路由 + 注册 + 权限 → verify: API 集成测试（草稿 upsert/撤回/拒收、preview 不写盘、非 admin 403）
4. [ ] 前端 apis + 两 Panel + 路由/导航 → verify: pnpm lint；浏览器亮暗双主题对照原型截图
5. [ ] docker 端到端演练：改草稿 → 预览 diff → 导出 → `git diff` 仅预期行 → verify: A1-A6 逐项过
6. [ ] changelog + 本文档状态更新
