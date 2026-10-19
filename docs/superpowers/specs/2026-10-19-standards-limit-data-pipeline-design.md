# 标准与限值库 · 限值数据管线设计（2026-10-19）

> brainstorming 产出。目标：把标准与限值库从「通道建成、0 数据」推到「62 条核实 + 7 张表常用档位覆盖 + 新表候选入册 + 标准原文 ground truth 通道试跑」，为后续达标判定能力备好数据底座。

## 一、背景与现状

- 62 条在册标准（standards_index.json v1.0，2026-09-06）来自 33 份语料 `standards_cited` 聚合，其中 41 条 `needs_verification`、17 条 `pending`；
- `limit_tables` 7 张表 `rows: []` 全空——写作侧纪律规定未录入档一律「需人工对照」禁断言，达标结论现全靠人工；
- 标准与限值库页已交付（P1 限值行录入 / P2 门 1 体检卡 / P3 核实裁决 + 两个导出物化，commit c0656671..250d8bb6），但 `eia_standard_limit_rows` / `eia_standard_reviews` 两表均 0 行——通道通了没人走；
- 项目内另有 regulation-library 扩展骨架（`/api/regulation-library/enrich` 条款解析+指标提取+建图，452 行），`standard_indicators` 表 0 行，从未实战验证。

## 二、决策记录（2026-10-19 用户拍板）

| 决策点 | 结论 |
|---|---|
| 来源策略 | **甲+乙组合**：语料提取打底 + 标准原文通道做 ground truth 与档位补全 |
| 提取范围 | **7 张表 + 新表发现**：映射外标准的限值区块聚合成「新表候选」，人工确认后表级入册（roadmap ⑤ 最小切片） |
| 数据流 | **草稿暂存层 + 逐行核实**：提取产物进暂存表，人工确认后才写正式表；导出物化零改动 |
| 乙输入 | **混合收集 + 试跑门**：先联网获取、缺口用户补充；GB 3838-2002 单标准试跑通过后才批量 |

**非目标（本期不做）**：达标判定引擎/限值选取器（写作侧消费 standards_index 的方式不变）；标准条目本体（62 条数组）的新增/修改/删除；compliance_checklist 结构化。

## 三、四大工作块

| 块 | 内容 | 复用 |
|---|---|---|
| W1 62 条核实辅助 | 每条标准透出语料引用清单 + KB 片段查询入口 + 联网线索提示；人工判定版本时效后 confirm+note | P3 review 通道，只加辅助信息展示 |
| W2 语料提取管线 | 扫 33 份语料 md → 执行标准区块定位 → 限值解析 → 聚合置信 → 落暂存表；映射外标准聚成新表候选 | corpus_meta report_id 体系、标准号归一、unit_parser |
| W3 核实工作台 | 暂存行逐行确认/改值/丢弃 + 佐证展示；新表候选「立表」入册 | 现有 StandardsPanel 扩展 |
| W4 标准原文通道 | 混合收集标准文件 → 试跑门 → 批量 enrich → 与限值行 ground truth 比对 | regulation-library 扩展激活 |

执行顺序：W2+W3 先行，W1 并行（纯 UI 扩展），W4 试跑门独立推进。

## 四、核心数据流

```
33 份语料 md ──W2 提取──▶ eia_limit_extract_rows（暂存，带佐证）
                              │ 人工逐行：确认/改值/丢弃
                              ▼
                    eia_standard_limit_rows（正式表，P1 现有，不动）
                              │ 全表核实完 → 导出物化（现有，零改动）
                              ▼
                    standards_index.json（写作侧消费，不变）
```

## 五、暂存表 `eia_limit_extract_rows`

| 列 | 类型 | 说明 |
|---|---|---|
| id | PK | 自增 |
| table_key | String(64) | 已知 7 表之一；候选行用 `__candidate__:` 前缀 + 标准号 |
| code | String(50) | 归一标准号（如 `GB 3838-2002`） |
| row_json | JSON | 行数据（因子/时段/档位/限值/单位），异构同正式表 |
| confidence | String(16) | `multi`（≥2 份一致）/ `single`（单源）/ `conflict`（不一致，`conflict_values` 附于 row_json） |
| sources | JSON | `[{report_id, md_anchor}]` 溯源到语料 |
| status | String(16) | `pending / confirmed / edited / discarded` |
| decided_by / decided_at / note | | 核实留档（note 仅 DB 留档不物化） |
| created_at / updated_at | | |

**幂等**：按 `(code, table_key, 因子, 时段, 档位)` 去重；重跑只补新行/刷新佐证，不覆盖 `status≠pending` 行。

**新表入册（表级新增通道）**：候选核实完 → 人工「立表」（table_key/desc/行结构 schema/code_ref）→ 写入 limit_tables 注册元数据 → 候选行转正。标准条目本体仍只读。

## 六、提取管线五步（W2）

1. **区块定位**：标准号正则扫描（复用 corpus_meta 归一逻辑），命中后截取关联窗口（紧邻 GFM 表格 ≤30 行（实现期可调常量）/ 行内列举段落）；
2. **限值解析**（纯函数，重点单测）：表格形态逐行解析 + 行内模式；档位识别（二级/III 类/2 类功能区…）；单位归一（复用 `unit_parser.py`）；因子别名映射（SO₂/SO2/二氧化硫、PM₁₀/PM10…）；
3. **table_key 映射**：静态映射（GB 3095→gb3095_concentration_limits 等 7 表）；映射外 → `__candidate__:` 聚合；
4. **聚合置信**：`(code, table_key, 因子, 时段, 档位)` 聚合 → multi/single/conflict；
5. **落库**：幂等写暂存表。

**试跑验收**：先跑出「提取报告」（每表行数/置信分布/候选清单），人工抽检每表 ≥10 行、精度 ≥90% 后开放核实工作台。

## 七、UI 与 API（W3）

**页面**（现有标准与限值库页扩展，base.css 变量 + lucide 图标）：
- **提取草稿**：按 table_key 分组；置信徽标；行展开佐证（report_id + md 锚点摘录）；行操作确认/改值/丢弃；conflict 行强制裁决；
- **新表候选**：按标准号聚合（引用份数/因子数）+「立表」对话框；
- **62 条总览增强**：行展开引用报告清单 + KB 查询弹层（现有 KB 检索 API）+ 联网线索提示（强调 web_search 不可直接引用——现有纪律）。

**新增 API**（admin 门槛同现有）：

```
POST /eia/standards/extract                      # 启动提取任务（后台）
GET  /eia/standards/extract/rows                 # 暂存行（table_key/status/confidence 过滤）
PUT  /eia/standards/extract/rows/{row_id}        # 确认/改值/丢弃
GET  /eia/standards/extract/candidates           # 新表候选清单
POST /eia/standards/extract/candidates/register  # 立表入册
GET  /eia/standards/{code}/citations             # W1 引用报告清单
```

导出物化、review、门 1 体检卡零改动。

## 八、乙通道试跑门（W4）

1. 联网获取标准原文（GB 3095-2012 / GB 3838-2002 / GB/T 14848-2017 / GB 3096-2008 / GB 12348-2008 + 高频候选如 GB 20426-2006），拿不到的出清单给用户补充；
2. 建「标准规范库」KB（若无）→ 上传 GB 3838-2002 → `POST /api/regulation-library/enrich` → 核对 `standard_indicators` 与已知限值；
3. **人工判定精度**：通过 → 批量铺开；不通过 → fallback（标准原文改作核实工作台「原文阅读」辅助，enrich 留作后续迭代）；
4. 通过后：enrich 指标 vs 暂存/正式行自动比对 → ground truth 校验报告（一致/偏差/缺档），偏差行打回人工裁决。

## 九、验收标准

- 62 条：每条有裁决（confirm+note 或明确「待定+原因」）；
- 7 张表：语料多源印证档位全部 confirmed 并导出物化；抽检精度 ≥90%；conflict 行清零；
- 新表候选：逐个立表或明确丢弃，无悬置；
- W4：试跑门有结论（通过或 fallback 生效）；
- 工程：解析纯函数单测（别名/单位/档位边界）+ API 集成测试（权限/校验/幂等）+ `make format` + changelog；提交等用户明确指令。

## 十、约束与风险

- **互证非 ground truth**：多源一致可高置信但不排除系统性抄错/旧版本标准；版本时效只能靠 W1 联网线索人工判定 + W4 原文比对兜底；
- **档位覆盖**：语料并集盖不住冷门档位（I 类水、一类区），留空不硬凑；
- **enrich 未验证**：0 数据骨架，精度风险由试跑门 + fallback 化解；
- **测试纪律**：新测试放 backend/test；严禁对运行栈跑清表类测试；
- 提取源用 samples_bank 语料 md（与 corpus_meta 同源，report_id 一致），不用 MinIO 库文件副本。
