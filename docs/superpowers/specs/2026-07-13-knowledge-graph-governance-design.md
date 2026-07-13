# 知识图谱治理与环评写作助手增强设计文档

> 日期: 2026-07-13 | 状态: 待评审
> 前置: [环评写作助手 v2 设计](./2026-07-13-coal-eia-writer-v2-design.md)

## 1. 背景与动机

### 1.1 问题发现

调研发现知识工厂数据存在严重的"图谱-DB 双写不同步"问题:

- Neo4j 图谱有完整的层级结构(90 ChapterTemplate / 819 ParagraphTemplate / 3810 Slot / 18 LegalReference)
- PostgreSQL 的 `domain_factory_outlines` / `learned_templates` 表是图谱的失真投影
- 工具只查 DB,拿不到图谱的丰富关系(段落模板/插槽/法规引用)

### 1.2 图谱数据质量问题

| 问题 | 根因 | 影响 |
|------|------|------|
| `canonical_chapter_key` 全 NULL | `graph_builder.py:805` MERGE 从不设置 | 工具无法按 key 查询 |
| `report_type="通用"` | 全链路默认值,ETL 不归一化 | 41/90 章挂错分支 |
| 只有 coal domain | 仅上传 coal 文档 + "通用"碎片化 | 其他矿种不可用 |
| 双编号 "1.1.1 3.1.1" | MinerU 加层级号,去重正则漏 numbered-line 路径 | title 混乱 |
| 图谱与 DB 不同步 | Neo4j(Stage 2.5)和 DB(Stage 2.8/2.9)独立写入 | canonical_key 只进 DB 不回写图谱 |

### 1.3 对标 fire-protection-report-v2 的差距

coal-eia-writer 相比消防技能缺少:content_contract 内容契约、路由关卡、写盘铁律、工具白名单、参考文件分层、脚本化合规检查、循环上限。

## 2. 治理目标与数据流重构 (Section 1)

### 2.1 目标状态:图谱作为单一数据源

```
ETL Pipeline (报告样例 → 图谱)
  Stage 1: 解析 → 清洗 title (修复双编号)
  Stage 2: 归一化 domain/report_type (修复"通用"污染)
  Stage 3: 构建 ChapterTemplate 时写入 canonical_key + content_contract
  Stage 4: 段落模板/插槽/法规/表格 (现有,质量已OK)
         │
         ▼ (单一数据源)
Neo4j 图谱 (治理后)
  DomainOutline(domain, report_type)
    └─HAS_CHAPTER→ ChapterTemplate
         ├─ canonical_chapter_key ✅
         ├─ content_contract ✅ (新增)
         ├─ title (清洗后) ✅
         ├─ domain ✅ / report_type ✅
         ├─ REQUIRES_PARAGRAPH_ROLE → ParagraphRole
         └─ HAS_CHILD → ChapterTemplate (子章节)
  ParagraphTemplate
    ├─ canonical_chapter_key ✅
    ├─ HAS_SLOT → Slot → CONSTRAINS → EntitySchema
    └─ CITES → LegalReference
         │
         ▼ (工具直查)
Agent Tools (改造)
  get_chapter_outline(key) → Cypher 查图谱
  get_templates(key)       → Cypher 查图谱
  list_chapter_keys()      → Cypher 查图谱
  废弃: domain_factory_outlines 表 (读取)
  废弃: domain_factory_learned_templates 表 (读取)
```

### 2.2 DB 表的命运

| 表 | 处理 | 理由 |
|---|------|------|
| `domain_factory_outlines` | 读取废弃,写入保留(过渡期降级) | 工具改查图谱 |
| `domain_factory_learned_templates` | 读取废弃 | 段落模板全从图谱查 |
| `domain_factory_reports*` | 保留 | 报告运行时数据,与图谱无关 |
| `report_types` / `domain_factory_domains` | 保留 | 字典表,图谱不覆盖 |

## 3. 治理步骤 (Section 2)

### 3.1 存量数据治理脚本 (一次性)

文件: `scripts/governance/fix_graph_data.py`

```
Step 1: 合并 DomainOutline 分支
  coal/通用 的 41 个 ChapterTemplate → report_type 改为 eia_report
  合并到 coal/eia_report 分支

Step 2: 清洗 ChapterTemplate.title
  "1.1.1 3.1.1 地形地貌" → "3.1.1 地形地貌"
  "1.3.4.1七号井田..."   → "七号井田..."
  "2" (纯编号)           → 删除或合并到父节点

Step 3: 回填 canonical_chapter_key
  用 clean_title 后的纯标题作为 key
  子章节继承父级前缀: "自然环境概况.地形地貌"

Step 4: 回填 ParagraphTemplate.canonical_chapter_key
  通过 COMPOSED_OF 关系反查所属 ChapterTemplate

Step 5: 回填 content_contract (从 key_points/expected_tables 推导)

Step 6: 校验
  0 个 canonical_chapter_key 为 NULL
  0 个 report_type='通用'
  0 个 title 含双编号
  DomainOutline 只剩 coal/eia_report 一个分支
```

### 3.2 ETL 源头治理 (防新污染)

**修复点 1: 归一化 report_type/domain** (`domain_factory_service.py:4028`)

```python
from yuxi.repositories.domain_factory_repository import (
    _normalize_domain, _normalize_report_type
)
domain_code = _normalize_domain(task_detail.get("domain") or "")
report_type_code = _normalize_report_type(task_detail.get("report_type_code") or "")
```

**修复点 2: title 清洗覆盖全路径** (`domain_factory_service.py:1077-1088`)

numbered-line 路径补充双编号去重正则。

**修复点 3: canonical_chapter_key 写入图谱** (`graph_builder.py:805-832`)

ChapterTemplate MERGE 增加 `ch.canonical_chapter_key = $canonical_chapter_key`。

**修复点 4: Stage 2.9 回写图谱** (`domain_factory_service.py:4051` 之后)

`_produce_outlines_async` 算出 canonical_key 后,新增 `GraphBuilder.backfill_canonical_keys()` 批量 UPDATE Cypher。

## 4. 工具改造直查图谱 (Section 3)

### 4.1 新增图谱查询服务

文件: `backend/package/yuxi/services/graph_query_service.py`

```python
class GraphQueryService:
    async def get_chapter_outline(domain, report_type, canonical_key) -> dict | None
    async def list_chapter_keys(domain, report_type) -> list[str]
    async def get_templates(canonical_key) -> list[dict]
    async def lookup_chapter_order(domain, report_type, canonical_key) -> int
```

### 4.2 工具改造

| 工具 | 当前 | 改造后 |
|------|------|--------|
| `get_chapter_outline` | DB repository | GraphQueryService |
| `get_templates` | DB repository | GraphQueryService |
| `list_chapter_keys` | DB repository | GraphQueryService |
| `save_chapter` (lookup_chapter_order) | DB repository | GraphQueryService |
| `list_report_types` | DB (不变) | 保留(字典表) |

### 4.3 返回数据增强

图谱查询返回比 DB 更丰富的信息:paragraph_roles / child_chapters / templates_preview / legal_references / entity_schema。

### 4.4 回滚安全

过渡期保留 DB 降级:图谱查询 miss 时回退 DB,1-2 版本后彻底废弃。

## 5. A 类静态大纲 MD + 测试验证 (Section 4)

### 5.1 MD 静态骨架

```
coal-eia-writer/outlines/
├── README.md
└── ch01~ch13.md  (导则规定的13章静态知识)
```

每章 MD 含:章节定位/写作要求/法规依据/写作骨架/数据需求清单。

**静态 vs 动态边界**: MD 放导则静态知识(13章标准结构/法规清单/写作骨架),图谱放 ETL 抽取的动态细化(章节模板/段落模式/插槽)。

### 5.2 测试验证策略

```
阶段1: 存量治理脚本 (TDD)
  治理前记录 NULL/双编号/"通用"数量
  运行治理脚本
  断言: 0 个 NULL key / 0 个"通用" / 0 个双编号

阶段2: 图谱查询服务 (TDD)
  get_chapter_outline('地形地貌') 返回完整结构
  list_chapter_keys('coal','eia_report') ≥ 38
  get_templates('地形地貌') 返回含 slots+refs

阶段3: 工具集成 (端到端)
  get_chapter_outline 工具返回图谱数据
  AI 对话调用链路正常
  不再读 domain_factory_outlines 表
```

## 6. 对标消防技能提升 (Section 5)

### 6.1 参考文件目录

```
coal-eia-writer/
├── SKILL.md
├── references/                  (新建,对标消防技能)
│   ├── terminology.md           (环评专业术语)
│   ├── content_guidelines.md    (各章编写规范)
│   ├── report_structure.md      (13章结构,fallback)
│   └── chapter_examples/
│       └── sample_coal_eia.md   (横城矿区样例片段)
└── outlines/                    (A类静态大纲)
```

分层加载:图谱查询 > references/report_structure.md > outlines/。

### 6.2 路由关卡 + 写盘铁律

新增到 SKILL.md 顶部:

- **路由关卡**: 上传完整报告书→文档解析;单章请求→直接写作
- **写盘铁律**: save_chapter 单章一次写入,禁止反复 append 修补;连续失败 2 次停止
- **工具白名单**: 各 writer 严格限定工具集,禁止跨角色调用
- **输出语言**: 全中文包括框架标签

### 6.3 content_contract 内容契约

ChapterTemplate 新增 `content_contract` 属性:

```json
{
  "key_elements": ["气候类型","气温","降水","风向风速","静风频率"],
  "min_word_count": 800,
  "forbidden_phrases": ["大约","可能","暂定","估计"],
  "structure_type": "narrative_text"
}
```

治理脚本从 key_points/expected_tables 推导初始值;get_chapter_outline 返回时附带;save_chapter 可选校验覆盖率(P1)。

### 6.4 脚本化合规检查

新增 `scripts/compliance_check.py`,检查项(PASS/WARN/FAIL):

1. 标准引用完整性(必引导则)
2. 标准编号格式(GB/HJ + 版本)
3. 必填要素覆盖(key_elements)
4. 数值占位符残留({{MISSING}}/[XX])
5. 禁止用语检测(forbidden_phrases)
6. 章节字数下限(min_word_count)
7. 交叉引用完整性({{REF}} 解析)
8. 表格编号连续性

compliance-checker 技能调用此脚本产出结构化报告。

### 6.5 循环上限

每章写作循环最多 2 轮修正,第 3 轮停止并报告用户。

## 7. 实施路线图

| Phase | 内容 | 优先级 |
|-------|------|--------|
| Phase 1 | 存量数据治理脚本 + ETL 源头修复 | P0 |
| Phase 2 | 图谱查询服务 + 工具改造直查图谱 | P0 |
| Phase 3 | 参考文件目录 + 路由关卡 + 写盘铁律 | P1 |
| Phase 4 | content_contract 回填 + 校验 | P1 |
| Phase 5 | 脚本化合规检查 | P2 |
| Phase 6 | A 类静态大纲 MD (13章) | P2 |

## 8. 不变量

1. 图谱是章节大纲/模板/插槽的单一读取源(过渡期 DB 降级)
2. canonical_chapter_key 是全局归一化章节标识,ETL 必填
3. domain/report_type 必须用 code,ETL 入图谱前归一化
4. title 清洗后不得含双编号
5. content_contract 由图谱提供,工具不得本地硬编码
6. 合规检查脚本化,不依赖 LLM 主观判断硬规则
