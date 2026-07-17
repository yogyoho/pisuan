# 标准规范库与条款级引用分析设计

> 日期: 2026-07-17 | 状态: 待评审
> 前置: [实体对象参与加工流程设计](./2026-07-17-entity-lifecycle-design.md)

## 1. 背景与目标

legal_reference 类型段落已提取标准名称/编号等文档级元数据，但缺少**条款级**信息——段落引用了标准的具体哪个条款、符合哪些指标限值。

部署环境为国内网络或完全离线（Tavily 等国外搜索 API 不可用），因此**自建标准规范库**是必选路径。

三个目标：

| 目标 | 用途 | 依赖 |
|------|------|------|
| A. ETL 元数据丰富 | 段落级条款引用关系入图谱 | 条款结构化 |
| B. 写作合规校验 | AI 写作时校验数值是否超标准限值 | 指标结构化（可计算） |
| C. 审核辅助 | 人工审核时展示条款原文对照 | 条款原文可精确定位 |

## 2. 存储选型结论

**结构化条款库为主体 + 向量/图谱为辅**（否决纯向量 KB 与 PageIndex）：

- 纯向量 KB：条款编号精确查询不可靠，限值无法计算比较
- PageIndex：LLM 多轮推理成本高，指标仍非结构化
- 选定方案：条款结构（PG JSONB）+ 指标表（PG 新表）+ 语义检索（Milvus）+ 关系（Neo4j）

## 3. 引用文档类型覆盖

系统 `LEGAL_TYPE_MAP` 的 9 类文档结构各异，统一泛化为"文档-结构单元-指标"三级模型：

| 文档类型 | 结构单元 unit_type | 示例 | 有指标 |
|---------|-------------------|------|--------|
| 国家/行业/地方标准 | clause + table | GB 3095-2012 `4.2` | ✅ |
| 技术规范/导则 | chapter | HJ 2.1-2016 `5.3` | 少量 |
| 国家法律 | article | 环境保护法 `第十二条` | ❌ |
| 行政法规/部门规章 | article/section | 水保[2013]188号 | ❌ |
| 规划/政策/项目资料 | section | `三、(一)` | ❌ |

结构单元统一字段：`{doc_code, doc_type, unit_no, unit_type, parent_unit, title}`——`parent_unit` 自引用构成目录树，容纳法条号/条款号/自由编号。

## 4. 架构：零侵入扩展（Post-Indexing Enrichment）

**约束**：`knowledge/` 模块来自上游 xerrors/Yuxi（定期 rebase），扩展必须零侵入。

```
┌─────────── 上游知识库模块（零改动） ───────────┐
│  KB 管理页创建"标准规范库" → 上传标准 PDF       │
│  → OCR 解析 → laws preset 切分（已按章/节/条）  │
│  → Milvus + PG knowledge_chunks 正常入库       │
└──────────────────┬───────────────────────────┘
                   │ 入库完成后（人工触发加工）
                   ▼
┌─────────── pisuan 扩展区（全部新文件） ────────┐
│  RegulationEnrichmentService                  │
│  1. 读取 KB chunks（只读）                     │
│  2. 解析条款结构 → 回填 chunks.tags JSONB      │
│     （tags 列上游已预留，写数据≠改代码）        │
│  3. 限值表 → LLM → standard_indicators 表     │
│  4. 确定性图谱 writer → Neo4j Clause 树        │
└──────────────────────────────────────────────┘
```

### 复用与缺口

| 上游能力 | 复用方式 |
|---------|---------|
| 上传/解析/索引管线 + UI | 直接使用 |
| `laws` chunk preset | 已按 章/节/条 切分，chunk 边界基本对齐条款 |
| `knowledge_chunks.tags/extraction_result` JSONB 列 | 休眠管道，扩展侧写入 |
| Neo4j 连接层 + `/api/graph/subgraph` 可视化 | 直接使用 |

| 缺口 | 扩展侧解法 |
|------|-----------|
| 条款号不在 chunk 元数据 | 后处理从 chunk 文本解析 `unit_no` 回填 tags |
| 指标未结构化 | `standard_indicators` 新表 + LLM 表格提取 |
| KB 图谱构建为 LLM 自由抽取 | 不用；写确定性 graph writer（参照 `graph_builder.py` 模式） |

## 5. 文件布局（extensions/ 定制专区）

```
backend/package/yuxi/extensions/              ← 新建
└── regulation_library/
    ├── __init__.py
    ├── enrichment_service.py     # 条款解析 + tags 回填
    ├── indicator_extractor.py    # 限值表 → LLM → 结构化指标
    ├── graph_writer.py           # 确定性 Neo4j Clause 树
    ├── models.py                 # standard_indicators 表
    └── router.py                 # API 端点

web/src/extensions/                           ← 新建
└── regulation-library/
    └── RegulationEnrichPanel.vue # 加工触发/进度/预览

唯一侵入点: server/routers/__init__.py 一行 include_router
```

## 6. 数据模型

### 6.1 条款结构（写入上游 chunks.tags JSONB，零迁移）

```json
{
  "doc_code": "GB 3095-2012",
  "doc_type": "technical_standard",
  "unit_no": "4.2",
  "unit_type": "clause",
  "parent_unit": "4",
  "title": "污染物浓度限值"
}
```

### 6.2 指标表（唯一新表）

```sql
CREATE TABLE standard_indicators (
    id          VARCHAR(64) PRIMARY KEY,
    doc_code    VARCHAR(128) NOT NULL,      -- "GB 3095-2012"
    unit_no     VARCHAR(64),                -- "表1"
    chunk_id    VARCHAR(64),                -- 关联来源 chunk
    pollutant   VARCHAR(128),               -- "SO2"
    metric      VARCHAR(128),               -- "年平均浓度限值"
    limit_value NUMERIC,                    -- 60
    unit        VARCHAR(32),                -- "μg/m³"
    condition   VARCHAR(255)                -- "二类区"
);
```

### 6.3 Neo4j（确定性构建）

```
(:RegDocument {doc_code, doc_type, name})
  -[:HAS_UNIT]-> (:RegUnit {unit_no, unit_type, title})
  -[:HAS_INDICATOR]-> (:Indicator {pollutant, metric, limit_value, unit, condition})
(:ParagraphTemplate)-[:CITES_UNIT]->(:RegUnit)    ← 条款级引用
```

## 7. 条款级引用匹配流程

```
legal_reference 段落
  → Step 1 规则预匹配: 段落已提取 code 定位文档；正则扫描条款线索（第X条/表X/X.X）
  → Step 2 语义检索: 段落文本 → Milvus（file 过滤）→ Top-3 候选条款 chunk
  → Step 3 LLM 判定: 段落原文 + 候选条款原文 → 引用了哪个条款/哪些指标
     输出: {cited_units, cited_indicators, confidence}
  → 写回:
     ├─ 段落 template.legal_references[].cited_units（目标A）
     ├─ Neo4j CITES_UNIT 关系（图谱）
     └─ Tab 1 legal_reference 详情面板展示条款原文对照（目标C）
```

**触发方式**：Tab 1 人工触发按钮"条款引用分析"，后台异步（与"智能识别实体"一致的交互模式），不自动执行。

## 8. 写作合规校验（目标B）

writer agent 新增 buildin 工具 `query_standard_indicators`：

```python
query_standard_indicators(doc_code="GB 16297-1996", pollutant="SO2")
→ [{unit_no: "表2", metric: "最高允许排放浓度", limit_value: 960, unit: "mg/m³", condition: "二级"}]
```

写章节时 agent 可校验生成数值是否超限值。

## 9. 建库策略

- **渐进式**：一次上传一份标准 PDF，加工后人工审核单元树/指标表再确认
- **优先级**：从现有 legal_reference 段落统计引用频次，优先录入高频 20-30 个标准
- **来源**：公司已有/渐进收集的标准 PDF 全文

## 10. 实施路线

| Phase | 内容 | 优先级 |
|-------|------|--------|
| 1 | extensions/ 目录 + standard_indicators 表 + enrichment_service（条款解析回填 tags） | P0 |
| 2 | indicator_extractor（限值表 LLM 提取） + graph_writer（Neo4j Clause 树） | P0 |
| 3 | 前端 RegulationEnrichPanel + 加工触发 API | P0 |
| 4 | 条款引用分析（Tab 1 按钮 + 匹配流程 + 详情面板对照展示） | P1 |
| 5 | `query_standard_indicators` writer 工具 | P1 |

## 11. 自审

- ✅ 9 类引用文档格式统一覆盖（unit_type 泛化）
- ✅ 零侵入约束满足（唯一侵入点 1 行路由注册）
- ✅ 三个目标均有对应数据结构与消费路径
- ✅ 离线环境可用（无外网依赖）
- ✅ 无 TBD/TODO
