# 大纲模板幂等与缺项修复设计（bug-4167）

- 日期：2026-10-29
- 页面：通用域知识工厂 → 大纲模板（`/domain-factory/general/outline-template`，`OutlineTemplate.vue`）
- 数据域：`coal` / `eia_report`（机制通用，本设计不改语义层单域现状）
- 状态：设计已获用户批准（范围=全链路一次修完；幂等实现=方案A 聚合键重构；测试节点=删子树）

## 1. 背景与实测症状

在 localized 栈（`pisuan-localized-*`）实测，2026-10-29：

| 症状 | 实测证据 |
|---|---|
| 章节重叠 | 图谱 ChapterTemplate 共 571 节点（13 std + 558 ETL）；level=1 有 14 个——标准 13 章之外多出「总  则」（全角空格）；「公众参与」×4 同父兄弟并列 + 1 个错挂「结论与建议」下；「修改/修编」「的问题和不足/问题与不足」等语义变体各自成点 |
| 子章节缺编号 | 同树中「1.1 编制依据」（源标题带号）与「评价时段」（源标题无号）并存；前端仅根节点渲染 `order`（`OutlineTemplate.vue:58`） |
| 结构化数据缺项 | 558 个 ETL 节点 purpose/key_points/content_contract 全 null；`get_chapter_outline` 不返回 `expected_tables/charts/formulas` 但 `update_chapter_template` 允许保存（保存→刷新即丢）；PG `domain_factory_outlines` 1055 行：490 键带编号、expected_* 全 0、regulations 仅 1 行 |
| 附带污染 | 图谱混入测试节点「测试章节标题A」「测试章节ParaKeyB」及其子树 |

## 2. 根因

1. **建点不幂等**：`graph_builder.py:805` ChapterTemplate 身份 = `CH_{domain}_{rt}_{hashstr(section_path_str)}`，section_path 含 doc_id → 同章节 × N 文档 = N 节点。
2. **归一化缺失**：`_derive_canonical_key`（`graph_builder.py:44`）只去前导编号不去内部空白；Bug1 特判（:847）仅覆盖 level=1 精确匹配；level-2 CONTAINS 双向 + `LIMIT 1` 模糊匹配（:940-958）是错挂根源。
3. **读路径不对称**：`get_chapter_outline`（`graph_query_service.py:56`）不返回 expected_*；`update_chapter_template` 限 `level=1 AND id STARTS WITH std_`（编辑非 std 章保存 404）；PG 富字段（overview/entity_bindings/writing_example/content_requirements）从不透出。
4. **PG 侧碎片化**：`_llm_chapter_meta` 失败回退用带编号原始标题做 canonical key（`domain_factory_service.py:5025`）；LLM meta 不回写图谱。

## 3. 目标 / 非目标

**目标**：写入幂等（同章节永远一个节点）；存量收敛（页面树干净）；读写对称（编辑不丢、PG 富字段可见）；编号统一展示。

**非目标**：语义变体自动归并（修改/修编类，留 LLM seed_keys 机制 + 人工编辑）；Section 文档层重构；PG↔Neo4j 双写架构调整（维持现状分工：图谱=模板层主源，PG=富字段与检索）。

## 4. 设计

### 4.1 归一化与身份键

**`normalize_chapter_key(title)`** 新建于 `yuxi/utils`（graph_builder / domain_factory_service / domain_factory_repository 共用）：
1. 去前导多级编号（沿用 `_derive_canonical_key` 逻辑）
2. 去所有内部空白（半角空格、全角 `　`、制表符）→「总  则」→「总则」
3. 纯编号返回空（不变）

**聚合身份键**：ChapterTemplate 身份 = `(domain, report_type, norm_canonical, level, 父节点身份)`。建点时自根逐级解析：
- 每级先按 norm_canonical 匹配 std 子章节 → 命中则**复用 std 节点**（std id 形态 `CH_{domain}_{rt}_std_{order}` / `..._std_{parent}_{sub}` 不变，seed 脚本零改动）
- 未命中 → `CH_{domain}_{rt}_{level}_{hashstr(norm_canonical + '|' + 父解析id)}`
- 同构章节树跨文档解析出相同 id → MERGE 命中 → `frequency+1`、rigidity 按 `(命中数+1)/source_count` 重算，不再建新点

**编号结构化**：节点新增 `chapter_no` 属性（由 section_path 逐级 order 推导，如 `sp=[1,4]` → `"1.4"`）；模板层 `title` 存去编号干净标题。跨文档编号冲突时取首个来源文档的推导值（first-won）。

### 4.2 写入端改造

| 位置 | 改动 |
|---|---|
| `graph_builder._build_skeleton_aggregation` | 换聚合键逐级解析 + MERGE；删除 Bug1 特判块（:847-876）与 level-2 CONTAINS 匹配块（:940-958）；HAS_CHILD / REQUIRES_PARAGRAPH_ROLE 挂解析后节点 |
| `confirm_outline_extract` 元数据回填（:5274-5296） | 已按 `(canonical, level)` 匹配——天然兼容，仅需确保匹配用归一后 key |
| `_produce_outlines_async` | LLM meta 产出后按聚合身份回写图谱节点（purpose/overview/key_points/writing_hints/extraction_regex），治 ETL 节点 meta 全空 |
| `_llm_chapter_meta` 回退 | 回退 key 过 `normalize_chapter_key`，消灭带编号 PG key |
| `repo.upsert_outline` | canonical 写入口统一过归一化（单一收口） |
| `graph_query_service.update_chapter_template` | 去掉 `std_` 前缀 + `level=1` 限制，改按 GET 同款 `(canonical, level)` 身份匹配 |

### 4.3 读路径补齐

- `get_chapter_outline`：补返回 `expected_tables/charts/formulas` 与 `child_chapters[].chapter_no`
- 新增薄装配（service 层）：详情端点 = 图谱 meta + PG 大纲行富字段（overview/content_requirements/entity_bindings/writing_example）合并；router 不再直连 GraphQueryService
- `list_outline_templates`：节点带 `chapter_no`；`(canonical, level)` 去重保留为兜底
- 前端 `OutlineTemplate.vue`：全层级统一渲染 `chapter_no + title`；详情新增「来源数据」只读区展示 PG 富字段

### 4.4 存量治理脚本

新建 `scripts/governance/merge_chapter_templates.py`，幂等可重跑 + `--dry-run`；import 兼容 `yuxi`/`pisuan` 双包名（容器内跑 localized 名）。

**Neo4j 阶段**（按序）：
1. 归一：全量 ChapterTemplate canonical 过 `normalize_chapter_key`
2. 合并：按 `(norm_canonical, level, 父节点)` 分组 → 幸存者优先 std → 入出边（HAS_CHILD / HAS_CHAPTER / REQUIRES_PARAGRAPH_ROLE）重定向 → meta COALESCE 取非空、frequency 取最大 → 删重复节点
3. 纠挂：level-2 节点 canonical 与其他章 std 子章节一致 → 重挂正确 std 父（「公众参与」回 std_12）
4. 编号：标题剥前导编号 → 干净 title + 推导 `chapter_no`
5. 删测试子树：「测试章节标题A」「测试章节ParaKeyB」及其全部后代（用户已确认）
6. meta 回填：PG 行（586 行有 purpose/overview）按 canonical 回写图谱
7. 治理报告：前后节点数、合并明细、剩余重复组（应为 0）

**PG 阶段**：带编号 key 行与对应无编号行归并（字段取非空、source_task_ids 并集）→ 删重复行。

**安全网**：治理前 `neo4j` ChapterTemplate 全量快照 dump 留档；dry-run 报告人工确认后再落写。

### 4.5 兼容性核对清单（实现时逐点过）

- seed 三脚本（`seed_standard_chapters/subchapters/outline_content`）：std id 不变，零改动
- `_merge_cross_report_knowledge`（service:4354）：基于 std id + HAS_CHILD，兼容
- `backfill_canonical_keys`（builder:1464）：按 id 更新，兼容
- `tools.py` 四工具：按 canonical 键控，兼容
- coal-eia-writer `mapping.py`：只读 chapter_id 做对比展示，兼容
- 既有治理脚本 `link_subchapters.py` 的 std_ 前缀过滤：本设计不改前缀，兼容

## 5. 测试与验收

**单测**：`normalize_chapter_key`（空白变体/多级编号/纯编号/空串）；聚合键解析（两文档同树→同 id；std 命中复用；不同父同名单独成点）；`_llm_chapter_meta` 回退归一；GET/PUT expected_* roundtrip。

**集成**（docker 容器内，遵守 testing-guidelines）：同一语料构建两遍 → 节点数不变（幂等断言）；`confirm_outline_extract` 后无重复节点。

**验收清单**：
- [ ] 页面左侧树 13 个根，「总则」不再重影
- [ ] 「公众参与」ch12 下唯一，ch13 下无错挂
- [ ] 子章节编号统一显示（含源标题无编号者，如「1.4 评价时段」）
- [ ] 详情编辑 expected_* 保存后刷新仍在
- [ ] 详情可见 PG 富字段
- [ ] 重新入库同一报告 → 图谱节点数不变
- [ ] 治理脚本重跑 → 报告零动作（幂等）

**风险与回滚**：治理脚本先 dry-run 出报告；图谱快照留档可回滚；写入端改动集中在 `_build_skeleton_aggregation` 单函数 + 两个回填点，影响面可控。
