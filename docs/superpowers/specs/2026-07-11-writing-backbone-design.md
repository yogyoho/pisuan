# 写作侧确定性骨架（Sub-project 2）— design

> 子项目 2 of「让 AI Agent 写出高质量 700 页煤炭环评报告」。依赖子项目 1（入库→写作的桥,已完成）。本 spec 覆盖写作侧的**确定性骨架**;合规引擎(子项目3)、成稿导出(子项目4)另行立项。

## 1. 背景与动机

子项目 1 打通了入库→写作的桥:writer 现在能从 KB 取到结构化章节大纲(`get_chapter_outline`)与模板(`get_templates`)。但写作侧的**项目参数表(PPS)、章节注册表、`{{REF}}` 交叉引用、章节装配**仍全交给 LLM 在沙箱 markdown 里"自觉维护":

- PPS / 注册表是自由 markdown → 跨章一致性无代码保证。
- `{{REF:chXX/表X-Y}}` 占位符由 LLM 写入,装配时"解析替换"是 prompt 指令,**无确定性解析代码**。
- 章节装配(合并 + 解析)是 LLM 指令,**无确定逻辑**。

叠加环评报告的实际使用特征:**700 页、单 agent 上下文装不下、需跨多会话点状累积**(每次请求可能只做一个点,而非从头写到尾)。

**本子项目目标**:把写作侧状态升级为 **DB 持久化 + 确定性装配 + 子 agent 编排**,支撑跨会话点状写作。

## 2. 范围

| | 内容 |
|---|---|
| **本版(开发)** | report 对象 + 3 张表 + 5 个工具 + `{{REF}}` resolver + 确定性装配 + chapter-writer 子 agent + coal-eia-writer 改为编排者 |
| **不在本子项目** | 成稿 docx/pdf 导出(子项目 4);合规数值规则引擎(子项目 3);section 级粒度工具(YAGNI,章内编辑由章节子 agent load/edit/save 整章);stable-id 引用体系(本版用位置编号起步) |

## 3. 核心决策

1. **DB-backed report 对象**(3 张新表)。状态跨会话持久——这是支撑"点状跨会话累积"的基础。
2. **Tools-driven agent**:不再写 PPS/registry markdown;agent 调结构化工具操作报告状态。
3. **PPS = 项目级实体值**:`entity_key` 链子项目 1 的 `entity_bindings`(schema 来自 outline 实体并集 + 用户基础项)。
4. **章节懒加载**:写哪章建哪章;装配按 outline 的 canonical 章节序合并。
5. **`{{REF}}` 位置编号**(`{{REF:chXX/表X-Y}}`),resolver 在 `assemble_report` 时**扫描各章 content_md 现算**引用目标(不存 ref_index 表)。
6. **`report_id` 主句柄**(跨会话续接);`thread_id` 仅作创建溯源。
7. **coal-eia-writer 升级为编排者(orchestrator)**;每章派**临时 chapter-writer 子 agent**(状态全在 DB,实例完成即终)。

## 4. 数据模型(3 张新表)

沿项目惯例:`models_domain_factory.py` 加模型 + `manager.py` DDL(`CREATE TABLE IF NOT EXISTS`,无 Alembic)。

```
domain_factory_reports                     ← 报告根对象
├─ id, title
├─ domain_code, report_type_code, kb_id(源知识库)
├─ thread_id(创建会话溯源;非主键)
├─ status: draft|writing|assembled
├─ created_by(uid), created_at, updated_at

domain_factory_report_chapters             ← 章节注册表(确定性)
├─ id, report_id
├─ canonical_chapter_key(链 outline), chapter_order(取自 outline 序)
├─ title, status: pending|writing|done|skipped
├─ content_md(写好的 markdown 正文)
├─ summary(一句话,供交叉引用/注册表)
├─ created_at, updated_at
└─ UNIQUE(report_id, canonical_chapter_key)

domain_factory_report_pps                  ← PPS 项目级参数值
├─ id, report_id
├─ entity_key(链 outline entity_bindings), name
├─ value, value_type(number|string|enum), unit
├─ source/provenance, confidence
├─ created_at, updated_at
└─ UNIQUE(report_id, entity_key)
```

**无 ref_index 表**——`{{REF}}` 目标映射在 assemble 时扫 content_md 现算。

**关系**:report 通过 `report_type_code` + 每章 `canonical_chapter_key` 链子项目 1 的 `domain_factory_outlines`;PPS 的 `entity_key` 链 outline 的 `entity_bindings`。

## 5. 工具 API(5 个新 buildin + 复用)

新工具(`agents/toolkits/buildin/tools.py`,`category="buildin"`,常驻):

| 工具 | 签名 | 作用 |
|---|---|---|
| `create_report` | `(thread_id, title, domain, report_type, kb_id)` → `report_id` | 建报告根对象(绑会话溯源) |
| `get_report` | `(report_id)` → `{status, pps: [...], registry: [{chapter_key,title,summary}], pending: [...]}` | 全景快照(PPS + 已完成章注册表一次取齐) |
| `set_pps_param` | `(report_id, entity_key, name, value, value_type, unit, source)` | upsert PPS 参数 |
| `save_chapter` | `(report_id, canonical_chapter_key, title, content_md, summary, status)` | 懒建/更新章节;`status` 可直接置 `done`(合并 mark_done) |
| `assemble_report` | `(report_id)` → `{markdown, unresolved_refs: [...], artifact_path}` | 按 outline 序合并 + 解析 `{{REF}` → 写沙箱 + 返回交付路径 |

**复用**:`get_chapter_outline` / `get_templates`(子项目 1)、`present_artifacts`(交付)、`subagent_start`/`task`(派 chapter-writer)。

## 6. chapter-writer 子 agent

- 注册一个**专用 subagent backend**(Agent 表,`SubAgentBackend`),预装报告工具(`get_chapter_outline`/`get_report`/`get_templates`/`set_pps_param`/`save_chapter`),聚焦单章写作。
- **临时实例**:编排者派发"写第 X 章"→ 实例取该章大纲 + PPS + 模板 → 填充 → `save_chapter(status=done)` → 终结。状态全在 DB,实例不持有跨请求状态。
- **点状编辑**:用户请求"改 5.2 章的表 5-3"→ 编排者按 `report_id` + 章 key 派发该章 chapter-writer → 实例 `get_report`/读该章 `content_md` → 改那一处 → `save_chapter` 整章回写。
- 系统已有子 agent 机制(`subagent_start`/`task`/`SubAgentBackend`),复用,不另造。

## 7. `{{REF}}` 解析(位置编号 + assemble 现算)

- **格式**:`{{REF:chXX/表X-Y}}`、`{{REF:chXX/图X-Y}}`、`{{REF:chXX/N.N节 标题}}`。
- **resolver(纯代码,assemble 时跑)**:
  1. 扫各 done 章节 `content_md`,按章号 `chXX` 建 `{表X-Y / 图X-Y / N.N节}` 目标映射(从 markdown 表格标题、图片标题、标题行抽取)。
  2. 扫全报告 `{{REF:...}}` 占位符,按映射替换为实际引用文(如"见表 5-3")。
  3. **未解析的**(`{{REF}}` 目标章未写 / 表不存在)→ 收进 `unresolved_refs` 返回,**不静默产出坏引用**。
- **位置编号的局限**:章节重排/重编号会断(700 页可能发生);本版接受,后续可升级 stable-id。

## 8. coal-eia-writer 编排工作流(SKILL.md 改写)

```
全量写作:
1. create_report(thread_id, title, domain, report_type, kb_id) → report_id
2. 逐章(按 outline 序,并发派 chapter-writer 子 agent):
   每章子 agent: get_chapter_outline → get_report(PPS+注册表) → get_templates
                 → 填插槽(缺参数 → set_pps_param 或 ask_user) → save_chapter(done)
3. assemble_report(report_id) → 解析 {{REF}} → present_artifacts 交付

点状请求(任意会话):
- report_id + 目标章 → 派该章 chapter-writer → get 当前 content → edit → save_chapter
- 或:set_pps_param(改一个参数)/ assemble_report(基于当前状态重新成稿)
```

## 9. 错误处理

- `assemble_report` 遇**未解析 `{{REF}}`** → **不静默丢弃/替换**:产出的 markdown 里保留可见 `{{REF:...}}` 占位符,同时返回 `unresolved_refs` 列表(占位符 + 所属章 + 原因),agent 修或用户确认后重 assemble。即"可见不静默",非硬阻断、不藏坏引用。
- `save_chapter(status=done)` 但 `content_md` 空 → 拒绝(返回 error)。
- PPS 缺关键 `entity_key` → 非阻断(写作时 slot-filler 走 `ask_user_question`);`assemble_report` 对未填关键参数给 warning 列表。
- chapter-writer 子 agent 失败 → 该章 `status` 留 `writing`/回 `pending`,编排者可重派;不影响他章。

## 10. 前置依赖

- 子项目 1(桥)已完成 ✓:`get_chapter_outline` / `get_templates` / `domain_factory_outlines` / `entity_bindings`。
- 子 agent 机制已有 ✓(`subagent_start`/`task`/`SubAgentBackend`)。
- coal-eia-writer skill 已存在 ✓(改为编排者,注入 chapter-writer 派发指令)。

## 11. 测试

- **工具单测**(mock repo):`create_report` / `get_report` / `set_pps_param` / `save_chapter` / `assemble_report`。
- **`{{REF}}` resolver 单测**(核心确定性):给若干章 `content_md`(含表/图/标题)+ `{{REF}}` 占位 → 断言正确解析 + `unresolved_refs` 标记。
- **装配集成**:章节乱序入库 → assemble 按 outline 序合并。
- **子 agent 派发**:mock `subagent_start`/`task`,断言编排者按章派发 + 收集结果。
- SKILL.md 驱动的端到端靠 manual 验证(prompt 难单测)。

## 12. 验收标准

1. `create_report` → reports 表行;**不同会话用 `report_id` 能续接同一报告**。
2. `set_pps_param` → PPS 填值;`get_report` 快照含 PPS + 已完成章注册表。
3. `save_chapter`(懒建)→ chapter 行;`status=done` + 空 content 被拒。
4. `{{REF}}` resolver:正确解析 `{{REF:chXX/表X-Y}}`;未解析进 `unresolved_refs`。
5. `assemble_report`:按 outline 序合并 + 解析 `{{REF}}` + 写沙箱 + 返回交付路径。
6. chapter-writer 子 agent:编排者派发"写第 X 章"→ 实例完成 → `save_chapter(done)`。
7. **点状编辑**:`report_id` + 目标章 → 派 chapter-writer → load/edit/save 整章。
8. 跨会话:报告状态在 DB 累积,新会话 `get_report(report_id)` 看到全部历史进度。
