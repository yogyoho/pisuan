# 入库→写作的桥：领域知识工厂结构化大纲产出（design）

> 子项目 1 of「让 AI Agent 写出高质量 700 页煤炭环评报告」。本 spec 只覆盖**入库→写作的桥**。写作侧确定性骨架、合规引擎、成稿导出分别是后续子项目。

## 1. 背景与动机

写作侧 `coal-eia-writer` / `compliance-checker` / `template-recommender` / `slot-filler` 四个 skill 的主数据源——每章 `[OUTLINE]` 结构化大纲（`overview` / `key_points` / `content_requirements` / `regulations` / `entity_bindings`）——其唯一生产者 `ingest_outline_collection()` 是 **LightRAG 专属死代码**。v0.7.0 移除 LightRAG 后（`knowledge/__init__.py` 只注册 milvus/dify/notion），它连同 `[OUTLINE]` 产出一起失效。

此前修复（commit `b548167c`）只让 **commit→Milvus 入库** 跑通，产出的是普通 chunk + `learned_templates` + 图谱，**不是 writer 要消费的结构化章节大纲**。skill 里硬约束"大纲以知识库 `[OUTLINE]` 查询结果为准"，但 KB 里根本没有 `[OUTLINE]`——writer 只能退化到 LLM mindmap 兜底，对 700 页强结构报告不可靠。

**本子项目目标**：在 commit 阶段产出 writer 真正能消费的「章节大纲 + 结构化模板」，打通入库→写作的桥。

## 2. 范围

| | 内容 |
|---|---|
| **本版（Tier 1，开发）** | 单报告章节大纲产出（OutlineProducer）+ 结构化模板工具（`get_templates`）+ 大纲工具（`get_chapter_outline`）+ 4 个消费 skill 改指向新工具 |
| **设计但开发后置** | 多报告聚合（`content_contract` / `rigidity` / 合并语义 / LLM 散文 lazy 刷新） |
| **不在本子项目** | 写作侧确定性骨架（PPS/章节注册表/{{REF}} 解析，子项目 2）；合规数值规则引擎（子项目 3）；成稿 docx/pdf 导出（子项目 4）；headers/routing_config 的物理删除（可能影响 ETL 内部） |

## 3. 核心决策

1. **桥在 commit 阶段一次性产出**（非查询时实时组装）。产物持久化、可审核、写作时零延迟；代价是入库多一个 OutlineProducer 阶段。
2. **混合产出**：结构化部分（`regulations` / `entity_bindings` / `content_requirements` / `expected_*` / `writing_example`）从 ETL 已抽资产**确定性组装**；散文部分（`purpose` / `overview` / `key_points` / `writing_hints`）+ 章节归一化由 **LLM** 生成。
3. **章节身份走 LLM 归一化**（`canonical_chapter_key`），**不依赖**静态 headers / SEC_* codes / template_matcher / routing_config。LLM 在生成散文的同一次调用里产出规范章节名，优先复用库里已有 key（seed 机制），找不到才新建。分类从样例自生长、自适应任何章（含煤炭特有的沉陷/复垦/煤矸石，无需预写 header）。
4. **分仓**：`domain_factory_outlines` 表（Postgres，精确取）+ `learned_templates`（Postgres，已存在）+ Milvus KB **回归纯自由检索**。不走 LightRAG 死代码、**不镜像模板到 Milvus**（Tier 1 检索主轴是章节=精确查询，语义跨章检索留后续）。
5. **废弃 routing_config**；**不补煤炭缺章 header**（LLM 自适应解决）。headers/template_matcher 可能仍服务于 ETL 内部章节分类，但**桥不依赖它们**。

## 4. 数据流

```
commit 流水线（在 b548167c 修复的基础上）：
  现有:  index_file(→Milvus 普通 chunk) → save_learned_templates(→Postgres) → GraphBuilder(→Neo4j)
  +新增: OutlineProducer（非阻断）
           ├─ 逐章: 对齐 canonical_chapter_key(LLM 归一,seed 已有 key)
           ├─ 确定性组装 7 字段(从 source_paragraphs/learned_templates/法规/表格/公式/图/图谱实体)
           ├─ LLM 一次调用产 4 散文字段 + canonical_chapter_key
           └─ upsert domain_factory_outlines (Tier1: insert, source_count=1)
```

OutlineProducer 触发于 `_commit_pipeline_async` 末尾（`_save_learned_templates_from_task` 之后），**非阻断**（失败不挡 commit，核心入库已完成）。

## 5. 存储 Schema

### 5.1 新表 `domain_factory_outlines`

沿项目惯例：`models_domain_factory.py` 加模型 + `manager.py` DDL 列表加 `CREATE TABLE IF NOT EXISTS`（无 Alembic）。

```
domain_factory_outlines
├─ id SERIAL PK
├─ domain_code        VARCHAR(64)  NOT NULL        ── 聚合键①
├─ report_type_code   VARCHAR(64)  NOT NULL        ── 聚合键②
├─ canonical_chapter_key TEXT NOT NULL             ── 聚合键③（LLM 归一化名，如"地下水环境影响预测"）
├─ chapter_id         VARCHAR(128)                 ── 原始章节号（如"3.1"，可读标签）
├─ chapter_title      TEXT
├─ ── Tier1 文字 ──
│  ├─ purpose             TEXT        （编写目的, LLM）
│  ├─ overview            TEXT        （概述, LLM）
│  ├─ key_points          JSONB '[]'  （要点[], LLM）
│  ├─ content_requirements JSONB '[]' （文字变量/段落角色[], 确定性）
│  ├─ regulations         JSONB '[]'  （[{code,title,effective_date,scope,standard_code}], 确定性）
│  ├─ entity_bindings     JSONB '[]'  （[{entity_id,entity_key,role,value_type,unit}], 确定性）
│  ├─ writing_example     TEXT         （sample_original, 确定性选最优）
│  └─ writing_hints       TEXT         （编写提示词, LLM）
├─ ── Tier1 artifact ──
│  ├─ expected_tables   JSONB '[]'  （[{table_type,purpose,columns:[{name,role,unit}],standard_code}]）
│  ├─ expected_charts   JSONB '[]'  （[{chart_type,purpose,data_source}]）
│  ├─ expected_formulas JSONB '[]'  （[{formula_template,variables:[{name,symbol,unit}],purpose}]）
│  └─ expected_figures  JSONB '[]'  （[{figure_type,purpose,generation_hint}]）
├─ ── Tier2 占位（随聚合开发填充）──
│  ├─ content_contract  JSONB '[]'  （多报告刚性内容契约[]）
│  └─ dependencies      JSONB '[]'  （前置章节[{chapter_key,reason}]）
├─ ── 聚合/来源 ──
│  ├─ source_task_ids   JSONB '[]'
│  ├─ source_count      INTEGER NOT NULL DEFAULT 1
│  ├─ prose_based_on_source_count INTEGER  （散文生成时的源数，lazy 刷新用）
│  └─ rigidity          VARCHAR(16) （rigid/flexible/conditional，≥2源时算）
├─ created_at / updated_at TIMESTAMP
└─ UNIQUE(domain_code, report_type_code, canonical_chapter_key)
   + Index(domain_code, report_type_code)
```

**命名约束**：字段一律用 `canonical_chapter_key`，**不复用** header 里那个误导的 `standard_code`（它实际存的是章节码）。`regulations[].standard_code` 才是真正的法规编号（GB/HJ/MT）。

### 5.2 `learned_templates` 不改结构

已有字段够用（`generalized` / `slots` / `chapter` / `slot_signature` / `source_count` / `sample_original`）。新增的只是读工具 `get_templates`。

### 5.3 Milvus KB 不动

`kb_cgsguljhor` 等继续做报告全文自由检索。桥不碰它，也不往里写 `[OUTLINE]` / `[TEMPLATE]` chunk。

## 6. 组件

### 6.1 OutlineProducer（`domain_factory_service.py` 内新增方法）

```
async def _produce_outlines_async(self, task_id, domain_code, report_type_code):
    detail = await self.get_task_detail(task_id)
    # 1. 按 chapter 分组 ETL 资产（source_paragraphs 带 chapter 上下文）
    chapters = group_assets_by_chapter(detail)  # {chapter_title: {templates, regs, tables, formulas, figures, entities}}
    # 2. 取已有 canonical_chapter_key 作 seed（同 domain+report_type）
    seed_keys = await self.repo.list_chapter_keys(domain_code, report_type_code)
    # 3. 逐章
    for ch_title, assets in chapters.items():
        deterministic = {
            "content_requirements": union_slots(assets.templates) + roles(assets.paragraphs),
            "regulations":          assets.legal_refs,        # [{code,...,standard_code}]
            "entity_bindings":      assets.entities,
            "expected_tables":      assets.table_schemas,
            "expected_formulas":    assets.formulas,
            "expected_charts":      assets.charts,            # docling 图表分类
            "expected_figures":     assets.figures,           # VLM 分类
            "writing_example":      pick_best(assets.templates.sample_original),
        }
        llm = await self._llm_chapter_meta(ch_title, deterministic, seed_keys)
        # llm → {canonical_chapter_key, purpose, overview, key_points, writing_hints}
        await self.repo.upsert_outline(domain_code, report_type_code,
            canonical_chapter_key=llm["canonical_chapter_key"],
            chapter_id=ch_title.chapter_id, chapter_title=ch_title,
            **deterministic, **{k: llm[k] for k in ("purpose","overview","key_points","writing_hints")},
            source_task_ids=[task_id], source_count=1,
            prose_based_on_source_count=1)
```

- `_llm_chapter_meta` 单次 LLM 调用同时产 canonical_chapter_key + 4 散文字段（省调用）。prompt 给 seed_keys，要求"优先复用已有 key，找不到再新建"。
- 每章一次 LLM 调用；一份报告约 30~50 章 = 30~50 次（commit 时一次性，可 `max_concurrency=10` 并发，复用 ETL 既有的并发模式）。

### 6.2 新增 2 个 buildin 工具（`agents/toolkits/buildin/tools.py`）

```python
@tool(category="domain_factory")
async def get_chapter_outline(domain: str, report_type: str, canonical_chapter_key: str) -> dict:
    """取某章的结构化大纲（purpose/overview/content_requirements/regulations/
    entity_bindings/expected_tables/charts/formulas/figures/writing_example/hints）"""

@tool(category="domain_factory")
async def get_templates(domain: str, report_type: str, canonical_chapter_key: str | None = None) -> list[dict]:
    """取某章（或全部）的结构化段落模板（generalized/slots/chapter/sample_original/standard_code）"""
```

常驻可用（不按 skill 门控），通过 `DomainFactoryRepository` 读 Postgres。

### 6.3 query_kb 职责纯化

`query_kb`（Milvus 语义检索）**不再背结构化大纲/模板**，回归报告全文自由检索（writer 查具体事实/段落）。结构化走 `get_chapter_outline` / `get_templates`，自由文本走 `query_kb`。

## 7. Skill 改动（4 个 SKILL.md，prompt 编辑无代码）

| skill | 原（坏的） | 改为 |
|---|---|---|
| `coal-eia-writer` | `query_kb` 过滤 `[OUTLINE]`（KB 里没有） | 写每章前先 `get_chapter_outline(report_type, chapter_key)` → 按其 `content_requirements` + `expected_*` 组织本章 |
| `compliance-checker` | `query_kb` 过滤 `[OUTLINE].regulations` | `get_chapter_outline(...).regulations` 拿法规清单逐条校验 |
| `template-recommender` | `query_kb`/`read_file` 找 `generalized_pattern`（结构对不上） | `get_templates(chapter_key)` 直接拿结构化模板 |
| `slot-filler` | `read_file` 读插槽 | `get_templates(...).slots`（已结构化） |

## 8. 错误处理（非阻断 soft，沿用 ETL 既有模式）

- OutlineProducer 整体异常 → 不挡 commit（核心入库已完成），记 error。
- LLM 散文/归一失败 → 确定性字段照存；散文留空标"待补充"；`canonical_chapter_key` 退化为 `chapter_title`（不聚合但不丢）。
- 某 extraction 源缺失（如无图） → 对应字段空数组。
- 工具调用查不到大纲 → 返回空 + 提示"该章尚未入库"，writer 走 mindmap 兜底。

## 9. 前置依赖（写进 plan）

- **`mcp-server-chart` 启用**（默认 disabled）——否则 `expected_charts` 给了 writer 也画不出。部署前置，非设计问题。
- **docling `image_refs` bug 修复**——docling 2.111 在 docx 上报 `name 'image_refs' is not defined` 回退到 python-docx（只给文本），表格/图表/VLM 抽取喂不饱。需先定位（docling 自身 or `unified.py` 包装层）。
- ~~coal_mining headers 挂载容器~~（已随静态 codes 砍掉而取消）。

## 10. 测试

- **单元**：`group_assets_by_chapter` / `union_slots` / `pick_best` 等纯函数；`_llm_chapter_meta` 的 prompt 组装与 JSON 解析（mock LLM）。
- **集成**：commit 一个真实煤矿章节 → 断言 `domain_factory_outlines` 有行 + 各字段非空 → 调 `get_chapter_outline` / `get_templates` 断言结构正确。
- **回归**：commit 仍产出 `learned_templates` / 图谱 / Milvus chunk（b548167c 的行为不退化）。
- 复用 `backend/test/test_pipeline.py` harness 扩展（它已驱动 parse→commit 零件）。

## 11. 多报告聚合设计（开发后置，schema 已预留）

**两层模型**：per-report ETL 产物（每份独立，保留可重算） vs 跨报告聚合视图（`domain_factory_outlines` 章节级 + `learned_templates` 模板级，后者本就跨报告按 `slot_signature` 累加 `source_count`）。

**触发**：第 N 份同 `(domain, report_type)` 报告 commit 时，OutlineProducer 改 insert 为 upsert，按 `canonical_chapter_key` 合并。

**逐字段合并语义**：
- `regulations` / `entity_bindings` / `content_requirements` / `expected_*`：按编码/ID 取**并集**，累计 prevalence。
- `writing_example`：多源选最优（或多个标来源）。
- `purpose` / `overview` / `key_points` / `writing_hints`：**lazy 重生成**——存 `prose_based_on_source_count`，查询时若 `source_count` 增长则标 stale、首次被取用时重生成。

**`content_contract` 计算**（聚合核心产出）：对每个内容元素（slot / 表类型 / 段落角色 / 法规）按 prevalence 计数； prevalence ≥ 阈值 → 刚性必覆盖；低于 → 可选/柔性。

**`rigidity` 评分**：刚性元素占比 → `rigid`（必照模板）/ `conditional` / `flexible`（可发挥）。对接既有骨架聚合设计。

**阈值待定**：`≥⌈N×0.7⌉` 还是"全部出现才算刚性"——聚合开发时定。

## 12. 已砍项（不再属于本子项目）

- 静态 headers（30 个 JSON）维护、SEC_* codes、template_matcher 正则匹配——LLM 归一化替代。
- 煤炭缺章（沉陷/复垦/煤矸石/清洁生产/总量控制）header + 码补全——LLM 自适应解决。
- routing_config.json 重建（已废弃，桥不读它）。
- 模板镜像到 Milvus（`[TEMPLATE]` chunk）——Tier 1 走 Postgres 工具，语义跨章检索留后续。
- headers/routing_config 物理删除——可能影响 ETL 内部，不在桥的 scope。

## 13. 验收标准（Tier 1）

1. commit 一份真实煤矿报告 → `domain_factory_outlines` 出现每章一行，确定性字段（regulations/entity_bindings/content_requirements/expected_*）非空（前提：ETL 抽取有产出）。
2. `canonical_chapter_key` 由 LLM 归一化产出，同报告内不重复、可读。
3. `get_chapter_outline(domain, report_type, chapter_key)` 返回完整结构化大纲。
4. `get_templates(domain, report_type, chapter_key)` 返回该章结构化模板列表。
5. coal-eia-writer 能用 `get_chapter_outline` 拿到本章大纲（而非 query_kb 空结果），写作不再盲写。
6. commit 失败时 OutlineProducer 非阻断（核心入库不退化）。
