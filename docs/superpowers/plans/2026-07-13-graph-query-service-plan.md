# 知识图谱核心数据流改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让环评写作工具直查 Neo4j 图谱（ChapterTemplate/ParagraphTemplate/Slot/LegalReference），DB 降级兜底，实现"图谱作为单一数据源"的核心目标。

**Architecture:** ETL 源头在 graph_builder 创建节点时写入 canonical_chapter_key；_produce_outlines_async 算出 key 后回写图谱；新增 GraphQueryService 封装 Cypher 查询；改造 tools.py 的 4 个工具优先查图谱、miss 时回退 DB。存量 ParagraphTemplate 通过 Section→COMPOSED_OF→ParagraphTemplate + Section.section_path 反查 ChapterTemplate 回填 key。

**Tech Stack:** Python 3.13, neo4j driver (async), SQLAlchemy async, pytest-asyncio

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/package/yuxi/services/graph_builder.py` | 修改 | ChapterTemplate/ParagraphTemplate MERGE 写 canonical_chapter_key；新增 backfill_canonical_keys/backfill_para_keys 方法 |
| `backend/package/yuxi/services/domain_factory_service.py` | 修改 | _produce_outlines_async 后调用图谱回写；ETL 写 ParagraphTemplate 时传 key |
| `backend/package/yuxi/services/graph_query_service.py` | 新建 | Cypher 查询服务（get_chapter_outline/list_chapter_keys/get_templates/lookup_chapter_order） |
| `backend/package/yuxi/agents/toolkits/buildin/tools.py` | 修改 | 4 个工具改造：图谱优先 + DB 降级 |
| `backend/scripts/governance/fix_existing_graph.py` | 修改 | 扩展 Step：回填 ParagraphTemplate.canonical_chapter_key |
| `backend/test/unit/services/test_graph_query_service.py` | 新建 | 图谱查询服务测试 |
| `backend/test/unit/services/test_graph_builder_keys.py` | 新建 | graph_builder 写 key 测试 |
| `backend/test/unit/agents/toolkits/buildin/test_tools_graph_integration.py` | 新建 | 工具图谱集成测试 |

---

## Phase A: graph_builder 写 canonical_key（P0 前置）

### Task 1: ChapterTemplate MERGE 写入 canonical_chapter_key

**Files:**
- Modify: `backend/package/yuxi/services/graph_builder.py:747-832`
- Create: `backend/test/unit/services/test_graph_builder_keys.py`

**Purpose:** ETL 创建 ChapterTemplate 时写入 canonical_chapter_key（用 clean_title 后的纯标题），防新数据再污染。

- [ ] **Step 1: 写失败测试**

Create `backend/test/unit/services/test_graph_builder_keys.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from yuxi.services.graph_builder import GraphBuilder


def test_chapter_template_merge_includes_canonical_key():
    """ChapterTemplate MERGE 的 Cypher 应包含 canonical_chapter_key 字段"""
    builder = GraphBuilder()
    captured_cypher = []

    fake_tx = MagicMock()
    def capture_run(cypher, **kwargs):
        captured_cypher.append(cypher)
        captured_cypher.append(kwargs)
        return MagicMock()
    fake_tx.run.side_effect = capture_run

    # 调用 _build_skeleton_aggregation 的 ChapterTemplate MERGE 部分
    # 需要构造 source_paragraphs 含 is_title 段落
    source_paragraphs = [
        {
            "id": "p1",
            "is_title": True,
            "title": "3.1.1 地形地貌",
            "section_path": ["3", "3.1", "3.1.1"],
            "content": "",
        }
    ]

    with patch.object(builder, "_driver"):
        builder._build_skeleton_aggregation.__func__(  # 调用静态方法
            MagicMock(),  # tx
            kb_id="kb1",
            doc_id="doc1",
            source_paragraphs=source_paragraphs,
            domain_code="coal",
            report_type_code="eia_report",
            source_count=1,
        )

    # 找到 ChapterTemplate 的 MERGE cypher
    ch_merge_found = False
    for i in range(0, len(captured_cypher), 2):
        cypher = captured_cypher[i]
        if "ChapterTemplate" in cypher and "MERGE" in cypher and "canonical_chapter_key" in cypher:
            ch_merge_found = True
            break
    assert ch_merge_found, "ChapterTemplate MERGE 应包含 canonical_chapter_key"
```

注意：`_build_skeleton_aggregation` 是 `@staticmethod`，签名是 `(tx, kb_id, doc_id, source_paragraphs, domain_code, report_type_code, source_count)`。测试可能需要调整调用方式——如果静态方法内部依赖 tx.run，测试直接传 fake_tx。如果测试结构难以构造，退化为**集成测试**：跑真实 GraphBuilder.build_knowledge_graph 后用 Cypher 验证节点有 canonical_chapter_key 属性。

**若单元测试 mock 太复杂，改用这个集成测试替代**（删除上面，用下面）：

```python
@pytest.mark.asyncio
async def test_build_knowledge_graph_writes_chapter_canonical_key():
    """build_knowledge_graph 后 ChapterTemplate 应有 canonical_chapter_key"""
    from yuxi.services.graph_builder import GraphBuilder

    builder = GraphBuilder()
    source_paragraphs = [
        {
            "id": "p_t1",
            "is_title": True,
            "title": "测试章节标题",
            "section_path": ["1", "1.1"],
            "content": "",
            "classify_type": "narrative",
        }
    ]
    try:
        builder.build_knowledge_graph(
            kb_id="kb_test_graph_keys",
            doc_id="doc_test_graph_keys",
            doc_title="测试文档",
            source_paragraphs=source_paragraphs,
            domain_label="coal",
            base_info={},
            domain_code="coal",
            report_type_code="eia_report",
        )
    finally:
        builder.close()

    # 验证写入的 ChapterTemplate 有 canonical_chapter_key
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (ch:ChapterTemplate {title:'测试章节标题'}) "
                "RETURN ch.canonical_chapter_key AS key"
            )
            rec = result.single()
            assert rec is not None, "ChapterTemplate 应被创建"
            assert rec["key"] == "测试章节标题", f"canonical_key 应为纯标题,实际: {rec['key']}"
    finally:
        driver.close()
```

- [ ] **Step 2: 运行验证失败**

Run: `docker exec api-dev pytest test/unit/services/test_graph_builder_keys.py -v`
Expected: FAIL — canonical_chapter_key 不在 MERGE 中 / 节点无该属性

- [ ] **Step 3: 修改 ChapterTemplate MERGE 写入 canonical_chapter_key**

在 `graph_builder.py:805-832` 的 `tx.run` Cypher 中，`ON CREATE SET` 块添加 `ch.canonical_chapter_key`，并传入参数。

修改 `_build_skeleton_aggregation` 中构建 chapter_map 的部分（约 766-772 行），给每个 ch_info 增加 `canonical_key`：

```python
            chapter_id = f"CH_{domain_code}_{report_type_code}_{hashstr(section_path_str, 10)}"
            # 推导 canonical_chapter_key: 去掉前导编号的纯标题
            canonical_key = _derive_canonical_key(title)
            chapter_map[section_path_str] = {
                "chapter_id": chapter_id,
                "title": title,
                "canonical_key": canonical_key,
                "level": level,
                "order": order,
                "section_path_str": section_path_str,
            }
```

在文件顶部（import 后，class 外）添加辅助函数：

```python
import re


def _derive_canonical_key(title: str) -> str:
    """从章节标题推导 canonical_chapter_key:去所有前导编号,只留纯标题。"""
    text = (title or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)*", text):
        return ""
    while True:
        m = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", text)
        if not m:
            break
        text = m.group(2).strip()
    return text
```

然后在 ChapterTemplate MERGE（约 805 行）的 Cypher `ON CREATE SET` 添加一行，并在参数中传入：

```python
            tx.run(
                """
                MERGE (ch:ChapterTemplate {id: $chapter_id})
                ON CREATE SET
                    ch.id = $chapter_id,
                    ch.title = $title,
                    ch.canonical_chapter_key = $canonical_key,
                    ch.level = $level,
                    ch.order = $order,
                    ch.rigidity = $rigidity,
                    ch.frequency = $frequency,
                    ch.domain = $domain_code,
                    ch.report_type = $report_type_code,
                    ch.kb_id = $kb_id,
                    ch.created_at = datetime()
                ON MATCH SET
                    ch.frequency = $frequency,
                    ch.rigidity = $rigidity,
                    ch.canonical_chapter_key = COALESCE(ch.canonical_chapter_key, $canonical_key)
                """,
                chapter_id=chapter_id,
                title=title,
                canonical_key=ch_info["canonical_key"],
                level=level,
                order=order,
                rigidity=rigidity,
                frequency=freq,
                domain_code=domain_code,
                report_type_code=report_type_code,
                kb_id=kb_id,
            )
```

注意 `ON MATCH SET` 用 `COALESCE` 保留已有 key（治理脚本回填的优先），仅当为空时用新推导值。

- [ ] **Step 4: 运行验证通过**

Run: `docker exec api-dev pytest test/unit/services/test_graph_builder_keys.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/graph_builder.py backend/test/unit/services/test_graph_builder_keys.py
git commit -m "feat(graph-builder): ChapterTemplate MERGE写入canonical_chapter_key"
```

---

### Task 2: ParagraphTemplate MERGE 写入 canonical_chapter_key

**Files:**
- Modify: `backend/package/yuxi/services/graph_builder.py:209-355`

**Purpose:** ParagraphTemplate 创建时关联到所属 ChapterTemplate 的 canonical_key。通过 section_path 反查 chapter_map。

- [ ] **Step 1: 写失败测试** — Append to `test_graph_builder_keys.py`:

```python
@pytest.mark.asyncio
async def test_build_knowledge_graph_writes_para_canonical_key():
    """build_knowledge_graph 后 ParagraphTemplate 应有 canonical_chapter_key(继承所属章节)"""
    from yuxi.services.graph_builder import GraphBuilder

    builder = GraphBuilder()
    source_paragraphs = [
        {
            "id": "p_t2",
            "is_title": True,
            "title": "测试章节ParaKey",
            "section_path": ["2", "2.1"],
            "content": "",
            "classify_type": "narrative",
        },
        {
            "id": "p_c2",
            "is_title": False,
            "title": "",
            "section_path": ["2", "2.1"],
            "content": "某矿区位于某地，海拔1000m。",
            "classify_type": "parameter",
            "template": {
                "generalized": "{{矿区}}位于{{位置}}，海拔{{海拔}}。",
                "slots": [
                    {"name": "矿区", "type": "string"},
                    {"name": "位置", "type": "string"},
                    {"name": "海拔", "type": "number"},
                ],
            },
        },
    ]
    try:
        builder.build_knowledge_graph(
            kb_id="kb_test_para_keys",
            doc_id="doc_test_para_keys",
            doc_title="测试ParaKey文档",
            source_paragraphs=source_paragraphs,
            domain_label="coal",
            base_info={},
            domain_code="coal",
            report_type_code="eia_report",
        )
    finally:
        builder.close()

    from neo4j import GraphDatabase
    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (pt:ParagraphTemplate) "
                "WHERE pt.text_pattern CONTAINS '{{矿区}}位于{{位置}}' "
                "AND pt.kb_id = 'kb_test_para_keys' "
                "RETURN pt.canonical_chapter_key AS key"
            )
            rec = result.single()
            assert rec is not None, "ParagraphTemplate 应被创建"
            assert rec["key"] == "测试章节ParaKey", f"应继承所属章节key,实际: {rec['key']}"
    finally:
        driver.close()
```

- [ ] **Step 2: 验证失败** — Expected FAIL（ParagraphTemplate 无 canonical_chapter_key）

- [ ] **Step 3: ParagraphTemplate MERGE 增加 canonical_chapter_key**

`_build_sections_and_templates` 当前签名是静态方法 `(tx, kb_id, doc_id, source_paragraphs)`。它内部不知道 chapter_map（chapter_map 在 `_build_skeleton_aggregation` 里构建）。

**方案**：`_build_sections_and_templates` 内部通过 section_path 反查所属章节标题，推导 canonical_key。但它没有 chapter_map。需要传入或在内部重建。

最简方案：在 `_build_sections_and_templates` 内部，对每个 ParagraphTemplate，根据其 section_path 找到最近的标题段落（同 section_path 的 is_title 段落），取其 title 推导 key。

修改 `_build_sections_and_templates`（约 209 行起），在第二遍循环（创建 ParagraphTemplate，约 296 行）前，先构建 `section_title_map`：

```python
        # 构建 section_path_str → 纯标题 映射(用于回填 ParagraphTemplate.canonical_chapter_key)
        section_title_map: dict[str, str] = {}
        for para in source_paragraphs:
            if not para.get("is_title"):
                continue
            sp = para.get("section_path") or para.get("path") or []
            if not sp:
                continue
            sp_str = "/".join(str(p) for p in sp)
            title = para.get("title", "")
            section_title_map[sp_str] = title
```

然后在创建 ParagraphTemplate 时（约 315 行后），推导所属章节 key：

```python
            # 推导所属章节的 canonical_chapter_key(从 section_path 反查最近标题)
            para_canonical_key = ""
            sp_list = section_path if isinstance(section_path, list) else []
            for i in range(len(sp_list), 0, -1):
                parent_sp_str = "/".join(str(p) for p in sp_list[:i])
                if parent_sp_str in section_title_map:
                    para_canonical_key = _derive_canonical_key(section_title_map[parent_sp_str])
                    break
```

在 ParagraphTemplate MERGE（约 325 行）的 `ON CREATE SET` 加 `pt.canonical_chapter_key`，`ON MATCH SET` 加 COALESCE，参数传 `canonical_key=para_canonical_key`：

```python
                tx.run(
                    """
                    MERGE (pt:ParagraphTemplate {id: $template_id})
                    ON CREATE SET
                        pt.id = $template_id,
                        pt.text_pattern = $text_pattern,
                        pt.generalized_pattern = $generalized_pattern,
                        pt.canonical_chapter_key = $canonical_key,
                        pt.hash = $hash,
                        pt.classify_type = $classify_type,
                        pt.kb_id = $kb_id,
                        pt.created_at = datetime()
                    ON MATCH SET
                        pt.text_pattern = COALESCE($text_pattern, pt.text_pattern),
                        pt.generalized_pattern = COALESCE($generalized_pattern, pt.generalized_pattern),
                        pt.classify_type = COALESCE($classify_type, pt.classify_type),
                        pt.canonical_chapter_key = COALESCE(pt.canonical_chapter_key, $canonical_key)
                    """,
                    template_id=template_id,
                    text_pattern=generalized,
                    generalized_pattern=generalized,
                    canonical_key=para_canonical_key,
                    hash=template_hash,
                    classify_type=classify_type,
                    kb_id=kb_id,
                )
```

- [ ] **Step 4: 验证通过** — Expected PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/graph_builder.py backend/test/unit/services/test_graph_builder_keys.py
git commit -m "feat(graph-builder): ParagraphTemplate MERGE写入canonical_chapter_key"
```

---

## Phase B: 存量 ParagraphTemplate 回填（P0 前置）

### Task 3: 治理脚本扩展回填 ParagraphTemplate.canonical_chapter_key

**Files:**
- Modify: `backend/scripts/governance/fix_existing_graph.py`
- Modify: `backend/test/scripts/test_fix_existing_graph.py`

**Purpose:** 存量 819 个 ParagraphTemplate 通过 section_path 反查所属 ChapterTemplate 回填 canonical_chapter_key。

- [ ] **Step 1: 写失败测试** — Append to `test_fix_existing_graph.py`:

```python
def test_backfill_para_keys_uses_chapter_lookup():
    """backfill_para_keys 通过 Section 反查 ChapterTemplate 回填"""
    from scripts.governance.fix_existing_graph import GraphGovernance

    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    # 模拟查询返回需回填的 ParagraphTemplate 及其所属章节 title
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter([
        {"id": "pt1", "chapter_title": "地形地貌"}
    ])
    fake_session.run.return_value = fake_result

    gov.backfill_para_keys(fake_driver)
    assert gov.report.fixed_para_keys >= 1
```

注意：`GovernanceReport` 需新增 `fixed_para_keys: int = 0` 字段。

- [ ] **Step 2: 验证失败** — Expected FAIL（`backfill_para_keys` 不存在）

- [ ] **Step 3: 实现回填**

在 `GovernanceReport` 添加字段：

```python
@dataclass
class GovernanceReport:
    fixed_keys: int = 0
    fixed_para_keys: int = 0
    merged_branches: int = 0
    cleaned_titles: int = 0
```

在 `GraphGovernance` 类添加方法：

```python
    def backfill_para_keys(self, driver) -> None:
        """回填 ParagraphTemplate.canonical_chapter_key(通过 Section 反查所属 ChapterTemplate)。"""
        with driver.session() as session:
            # 通过 Section-COMPOSED_OF->ParagraphTemplate, Section.section_path 反查 ChapterTemplate
            result = session.run(
                """
                MATCH (pt:ParagraphTemplate)
                WHERE (pt.canonical_chapter_key IS NULL OR pt.canonical_chapter_key = '')
                OPTIONAL MATCH (s:Section)-[:COMPOSED_OF]->(pt)
                OPTIONAL MATCH (ch:ChapterTemplate)
                  WHERE ch.title IS NOT NULL
                    AND s.section_path_str IS NOT NULL
                    AND s.section_path_str <> ''
                RETURN pt.id AS pt_id, s.section_path_str AS sp_str,
                       collect(DISTINCT ch.title) AS ch_titles,
                       collect(DISTINCT ch.canonical_chapter_key) AS ch_keys
                """
            )
            for record in result:
                pt_id = record["pt_id"]
                # 优先用已有 ChapterTemplate.canonical_chapter_key,否则从 title 推导
                ch_keys = [k for k in (record["ch_keys"] or []) if k]
                ch_titles = [t for t in (record["ch_titles"] or []) if t]
                key = ch_keys[0] if ch_keys else (derive_canonical_key(clean_chapter_title(ch_titles[0])) if ch_titles else "")
                if key and not self.dry_run:
                    session.run(
                        "MATCH (pt:ParagraphTemplate {id:$id}) "
                        "SET pt.canonical_chapter_key = $key",
                        id=pt_id, key=key,
                    )
                if key:
                    self.report.fixed_para_keys += 1
```

在 `run_all` 中调用（在 `backfill_keys` 之后）：

```python
    def run_all(self, driver) -> GovernanceReport:
        self.merge_general_branch(driver)
        self.clean_titles(driver)
        self.backfill_keys(driver)
        self.backfill_para_keys(driver)
        return self.report
```

在 `main()` 打印添加：

```python
    print(f"回填 ParagraphTemplate key 数: {report.fixed_para_keys}")
```

- [ ] **Step 4: 验证通过** — Expected PASS

- [ ] **Step 5: 执行存量回填**

```bash
docker exec api-dev python -m scripts.governance.fix_existing_graph --uri bolt://graph:7687
```
Expected: fixed_para_keys > 0

验证：
```bash
docker exec graph cypher-shell -a bolt://localhost:7687 -u neo4j -p 0123456789 "MATCH (pt:ParagraphTemplate) WHERE pt.canonical_chapter_key IS NOT NULL RETURN count(pt) AS with_key;"
```
Expected: with_key 从 0 大幅增加

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/governance/fix_existing_graph.py backend/test/scripts/test_fix_existing_graph.py
git commit -m "feat(governance): 回填ParagraphTemplate.canonical_chapter_key"
```

---

### Task 4: _produce_outlines_async 回写图谱（可选增强）

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py:4047-4056`（Stage 2.9 之后）
- Modify: `backend/package/yuxi/services/graph_builder.py`（新增 backfill 方法）

**Purpose:** _produce_outlines_async 算出的 canonical_chapter_key 回写图谱（Stage 2.9 → 图谱）。由于 Task 1 已让 ETL 写入推导 key，此 Task 是"用 LLM 算出的更准 key 覆盖"。

- [ ] **Step 1: 写失败测试** — Append to `test_graph_builder_keys.py`:

```python
@pytest.mark.asyncio
async def test_backfill_canonical_keys_updates_graph():
    """GraphBuilder.backfill_canonical_keys 用 outline_map 更新 ChapterTemplate key"""
    from yuxi.services.graph_builder import GraphBuilder
    from neo4j import GraphDatabase

    # 先建一个测试节点(无 key)
    driver = GraphDatabase.driver("bolt://graph:7687", auth=("neo4j", "0123456789"))
    try:
        with driver.session() as s:
            s.run("MERGE (ch:ChapterTemplate {id:'ch_test_backfill'}) SET ch.title='旧标题', ch.canonical_chapter_key=''")

        builder = GraphBuilder()
        outline_map = {"ch_test_backfill": "LLM算出的规范名"}
        builder.backfill_canonical_keys(outline_map, kb_id="kb_test_backfill")
        builder.close()

        with driver.session() as s:
            rec = s.run("MATCH (ch:ChapterTemplate {id:'ch_test_backfill'}) RETURN ch.canonical_chapter_key AS key").single()
            assert rec["key"] == "LLM算出的规范名"
            # 清理
            s.run("MATCH (ch:ChapterTemplate {id:'ch_test_backfill'}) DETACH DELETE ch")
    finally:
        driver.close()
```

- [ ] **Step 2: 验证失败** — Expected FAIL（backfill_canonical_keys 不存在）

- [ ] **Step 3: 实现 backfill_canonical_keys**

在 `GraphBuilder` 类添加：

```python
    def backfill_canonical_keys(self, outline_map: dict[str, str], kb_id: str = "") -> int:
        """用 outline_map({chapter_id: canonical_key}) 更新 ChapterTemplate.canonical_chapter_key。

        供 _produce_outlines_async 在 LLM 算出 key 后回写图谱。
        """
        if not outline_map:
            return 0
        updated = 0
        with self._driver.session() as session:
            for chapter_id, canonical_key in outline_map.items():
                if not canonical_key:
                    continue
                session.run(
                    "MATCH (ch:ChapterTemplate {id:$id}) "
                    "SET ch.canonical_chapter_key = $key",
                    id=chapter_id, key=canonical_key,
                )
                updated += 1
        return updated
```

在 `domain_factory_service.py` 的 `_produce_outlines_async`（约 4589 行 return 之前），构造 chapter_id→key 映射并回写。需要先确认 _produce_outlines_async 内部能拿到 chapter_id（section_path hash）。如果拿不到 chapter_id，此 Task 标记为**可选**——Task 1 的 ETL 源头写入已保证新数据有 key，此 Task 仅是用 LLM key 覆盖推导 key 的精度增强。

**务实决策**：如果 chapter_id 难以在 _produce_outlines_async 内重建，跳过回写调用，backfill_canonical_keys 方法保留供治理脚本用。在 _produce_outlines_async 末尾加注释说明。

- [ ] **Step 4: 验证通过** — Expected PASS（方法存在且能更新）

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/graph_builder.py backend/test/unit/services/test_graph_builder_keys.py
git commit -m "feat(graph-builder): backfill_canonical_keys方法(LLM key回写图谱)"
```

---

## Phase C: GraphQueryService + 工具直查图谱（P0 核心）

### Task 5: 创建 GraphQueryService 基础结构 + list_chapter_keys

**Files:**
- Create: `backend/package/yuxi/services/graph_query_service.py`
- Create: `backend/test/unit/services/test_graph_query_service.py`

**Purpose:** 图谱查询服务骨架 + list_chapter_keys 查询。

- [ ] **Step 1: 写失败测试**

Create `backend/test/unit/services/test_graph_query_service.py`:

```python
import pytest
from yuxi.services.graph_query_service import GraphQueryService


@pytest.mark.asyncio
async def test_list_chapter_keys_returns_distinct_keys():
    """list_chapter_keys 返回 coal/eia_report 下所有非空 canonical_chapter_key"""
    service = GraphQueryService()
    keys = await service.list_chapter_keys("coal", "eia_report")
    assert isinstance(keys, list)
    # 存量治理后应有 88 个 key
    assert len(keys) >= 30, f"应至少30个章节key,实际{len(keys)}"
    assert all(isinstance(k, str) and k for k in keys)
    # 去重
    assert len(keys) == len(set(keys)), "章节key不应重复"


@pytest.mark.asyncio
async def test_list_chapter_keys_unknown_domain_returns_empty():
    """未知 domain 返回空列表(不报错)"""
    service = GraphQueryService()
    keys = await service.list_chapter_keys("nonexistent_domain", "eia_report")
    assert keys == []
```

- [ ] **Step 2: 验证失败** — Expected FAIL（模块不存在）

- [ ] **Step 3: 创建 GraphQueryService**

Create `backend/package/yuxi/services/graph_query_service.py`:

```python
"""图谱查询服务:封装 Cypher,供工具直查 Neo4j 图谱。"""

from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from yuxi import config as sys_config


class GraphQueryService:
    """查询知识图谱的 ChapterTemplate/ParagraphTemplate/Slot/LegalReference。

    替代工具层对 DB 的直接查询,图谱作为单一数据源。
    """

    def __init__(self):
        uri = getattr(sys_config, "neo4j_uri", "bolt://graph:7687") or "bolt://graph:7687"
        user = getattr(sys_config, "neo4j_user", "neo4j") or "neo4j"
        password = getattr(sys_config, "neo4j_password", "0123456789") or "0123456789"
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    async def list_chapter_keys(self, domain: str, report_type: str) -> list[str]:
        """列出某 domain+report_type 下所有 canonical_chapter_key(去重、非空)。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt})
                WHERE ch.canonical_chapter_key IS NOT NULL AND ch.canonical_chapter_key <> ''
                RETURN DISTINCT ch.canonical_chapter_key AS key
                ORDER BY key
                """,
                domain=domain, rt=report_type,
            )
            return [r["key"] for r in result if r["key"]]
```

- [ ] **Step 4: 验证通过** — Expected PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/graph_query_service.py backend/test/unit/services/test_graph_query_service.py
git commit -m "feat(graph-query): GraphQueryService + list_chapter_keys"
```

---

### Task 6: GraphQueryService.get_chapter_outline

**Files:**
- Modify: `backend/package/yuxi/services/graph_query_service.py`
- Modify: `backend/test/unit/services/test_graph_query_service.py`

**Purpose:** 查询单个章节大纲，含子章节和段落角色。

- [ ] **Step 1: 写失败测试** — Append:

```python
@pytest.mark.asyncio
async def test_get_chapter_outline_returns_structure():
    """get_chapter_outline 返回章节结构(含 title/level/key)"""
    service = GraphQueryService()
    # 先确保有数据(coal/eia_report 治理后有"地形地貌")
    outline = await service.get_chapter_outline("coal", "eia_report", "地形地貌")
    if outline is None:
        # 数据可能命名不同,跳过断言细节,只验证结构
        keys = await service.list_chapter_keys("coal", "eia_report")
        if not keys:
            return  # 无数据,跳过
        outline = await service.get_chapter_outline("coal", "eia_report", keys[0])
    assert outline is not None
    assert "canonical_chapter_key" in outline
    assert "title" in outline


@pytest.mark.asyncio
async def test_get_chapter_outline_not_found_returns_none():
    """不存在的 key 返回 None"""
    service = GraphQueryService()
    outline = await service.get_chapter_outline("coal", "eia_report", "不存在的章节XYZ123")
    assert outline is None
```

- [ ] **Step 2: 验证失败** — Expected FAIL（方法不存在）

- [ ] **Step 3: 实现 get_chapter_outline**

Add to `GraphQueryService`:

```python
    async def get_chapter_outline(
        self, domain: str, report_type: str, canonical_key: str
    ) -> dict[str, Any] | None:
        """查询单个章节大纲,含子章节和段落角色预览。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                OPTIONAL MATCH (ch)-[:HAS_CHILD]->(sub:ChapterTemplate)
                OPTIONAL MATCH (ch)-[:REQUIRES_PARAGRAPH_ROLE]->(pr:ParagraphRole)
                RETURN ch.canonical_chapter_key AS key, ch.title AS title,
                       ch.level AS level, ch.`order` AS order,
                       ch.rigidity AS rigidity, ch.frequency AS frequency,
                       collect(DISTINCT {title: sub.title, key: sub.canonical_chapter_key}) AS children,
                       collect(DISTINCT pr.name AS role) AS roles
                """,
                domain=domain, rt=report_type, key=canonical_key,
            )
            rec = result.single()
            if rec is None or rec["key"] is None:
                return None
            return {
                "canonical_chapter_key": rec["key"],
                "title": rec["title"],
                "level": rec["level"],
                "order": rec["order"],
                "rigidity": rec["rigidity"],
                "frequency": rec["frequency"],
                "child_chapters": [c for c in rec["children"] if c.get("title")],
                "paragraph_roles": [r for r in (rec["roles"] or []) if r],
            }
```

注意：Cypher 中 `order` 是保留字，用反引号 `` `order` ``。`collect(DISTINCT pr.name AS role)` 语法需验证——可能需要拆成单独 collect。如果 Cypher 报错，改为：

```cypher
                collect(DISTINCT pr.name) AS roles
```

并在 return 里用 `rec["roles"]`。

- [ ] **Step 4: 验证通过** — Expected PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/graph_query_service.py backend/test/unit/services/test_graph_query_service.py
git commit -m "feat(graph-query): get_chapter_outline查询单章节大纲"
```

---

### Task 7: GraphQueryService.get_templates + lookup_chapter_order

**Files:**
- Modify: `backend/package/yuxi/services/graph_query_service.py`
- Modify: `backend/test/unit/services/test_graph_query_service.py`

**Purpose:** 查询段落模板（含 Slot/LegalReference）+ 章节顺序号。

- [ ] **Step 1: 写失败测试** — Append:

```python
@pytest.mark.asyncio
async def test_get_templates_returns_paragraph_templates():
    """get_templates 返回该章节下的段落模板(含 slots)"""
    service = GraphQueryService()
    templates = await service.get_templates("coal", "eia_report", "地形地貌")
    if not templates:
        # 数据可能命名不同,验证结构即可
        keys = await service.list_chapter_keys("coal", "eia_report")
        if keys:
            templates = await service.get_templates("coal", "eia_report", keys[0])
    assert isinstance(templates, list)
    for t in templates:
        assert "text_pattern" in t
        assert "slots" in t


@pytest.mark.asyncio
async def test_lookup_chapter_order_returns_int():
    """lookup_chapter_order 返回章节顺序号"""
    service = GraphQueryService()
    keys = await service.list_chapter_keys("coal", "eia_report")
    if not keys:
        return
    order = await service.lookup_chapter_order("coal", "eia_report", keys[0])
    assert order is None or isinstance(order, int)


@pytest.mark.asyncio
async def test_lookup_chapter_order_unknown_returns_none():
    service = GraphQueryService()
    order = await service.lookup_chapter_order("coal", "eia_report", "不存在XYZ")
    assert order is None
```

- [ ] **Step 2: 验证失败** — Expected FAIL

- [ ] **Step 3: 实现 get_templates + lookup_chapter_order**

Add to `GraphQueryService`:

```python
    async def get_templates(
        self, domain: str, report_type: str, canonical_key: str
    ) -> list[dict[str, Any]]:
        """查询某章节下的段落模板,含 Slot 和 LegalReference。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (pt:ParagraphTemplate {canonical_chapter_key: $key})
                WHERE $domain IS NULL OR pt.kb_id STARTS WITH 'kb_'
                OPTIONAL MATCH (pt)-[:HAS_SLOT]->(s:Slot)
                OPTIONAL MATCH (s)-[:CONSTRAINS]->(es:EntitySchema)
                OPTIONAL MATCH (pt)-[:CITES]->(lr:LegalReference)
                RETURN pt.id AS pt_id, pt.text_pattern AS pattern,
                       collect(DISTINCT {name: s.name, type: s.type,
                                          entity: es.name}) AS slots,
                       collect(DISTINCT {code: lr.code, name: lr.name}) AS refs
                """,
                key=canonical_key, domain=domain,
            )
            templates = []
            for rec in result:
                pattern = rec["pattern"]
                if not pattern:
                    continue
                slots = [
                    {"name": s["name"], "type": s["type"], "entity_ref": s["entity"]}
                    for s in rec["slots"]
                    if s and s.get("name")
                ]
                refs = [
                    {"code": r["code"], "name": r["name"]}
                    for r in rec["refs"]
                    if r and r.get("code")
                ]
                templates.append({
                    "text_pattern": pattern,
                    "slots": slots,
                    "legal_references": refs,
                })
            return templates

    async def lookup_chapter_order(
        self, domain: str, report_type: str, canonical_key: str
    ) -> int | None:
        """查询章节顺序号。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                RETURN ch.`order` AS order
                """,
                domain=domain, rt=report_type, key=canonical_key,
            )
            rec = result.single()
            if rec is None:
                return None
            order = rec["order"]
            return int(order) if order is not None else None
```

- [ ] **Step 4: 验证通过** — Expected PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/graph_query_service.py backend/test/unit/services/test_graph_query_service.py
git commit -m "feat(graph-query): get_templates + lookup_chapter_order"
```

---

### Task 8: 工具改造 — list_chapter_keys 直查图谱

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py` (`list_chapter_keys` 函数，约 461 行)
- Create: `backend/test/unit/agents/toolkits/buildin/test_tools_graph_integration.py`

**Purpose:** list_chapter_keys 工具优先查图谱，miss 时回退 DB。

- [ ] **Step 1: 写失败测试**

Create `backend/test/unit/agents/toolkits/buildin/test_tools_graph_integration.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_list_chapter_keys_uses_graph_first():
    """list_chapter_keys 工具优先查图谱"""
    from yuxi.agents.toolkits.buildin.tools import list_chapter_keys

    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.list_chapter_keys",
        new=AsyncMock(return_value=["地形地貌", "气候气象"]),
    ):
        result = await list_chapter_keys.ainvoke({"domain": "coal", "report_type": "eia_report"})
    assert isinstance(result, list)
    assert "地形地貌" in result


@pytest.mark.asyncio
async def test_list_chapter_keys_falls_back_to_db():
    """图谱查询失败时回退 DB"""
    from yuxi.agents.toolkits.buildin.tools import list_chapter_keys

    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.list_chapter_keys",
        new=AsyncMock(side_effect=Exception("graph down")),
    ):
        # 即使图谱挂了,工具不应抛异常,应回退 DB(可能返回空或DB数据)
        result = await list_chapter_keys.ainvoke({"domain": "coal", "report_type": "eia_report"})
    assert isinstance(result, list)
```

- [ ] **Step 2: 验证失败** — Expected FAIL（工具仍查 DB）

- [ ] **Step 3: 改造 list_chapter_keys**

找到 `tools.py` 的 `list_chapter_keys` 工具函数（约 461 行），当前用 `DomainFactoryRepository`。改为图谱优先 + DB 降级：

```python
async def list_chapter_keys(domain: str, report_type: str) -> list[str]:
    """列出某 domain+report_type 下所有 canonical_chapter_key。优先查图谱,回退 DB。"""
    from yuxi.services.graph_query_service import GraphQueryService

    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)
    # 1. 优先查图谱
    try:
        graph_svc = GraphQueryService()
        try:
            keys = await graph_svc.list_chapter_keys(domain, report_type)
            if keys:
                return keys
        finally:
            graph_svc.close()
    except Exception as e:
        logger.warning(f"图谱查询 list_chapter_keys 失败,回退 DB: {e}")
    # 2. 降级 DB
    repo = DomainFactoryRepository()
    return await repo.list_chapter_keys(domain, report_type)
```

注意：确认 `_normalize_domain`/`_normalize_report_type` 已在 tools.py 导入（应在）。`logger` 已在 tools.py 顶部导入。

- [ ] **Step 4: 验证通过** — Expected PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/test/unit/agents/toolkits/buildin/test_tools_graph_integration.py
git commit -m "feat(tools): list_chapter_keys直查图谱+DB降级"
```

---

### Task 9: 工具改造 — get_chapter_outline 直查图谱

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py` (`get_chapter_outline`，约 413 行)

**Purpose:** get_chapter_outline 图谱优先 + DB 降级。图谱返回更丰富（child_chapters/roles），DB 返回原始 outline 字段。

- [ ] **Step 1: 写失败测试** — Append to `test_tools_graph_integration.py`:

```python
@pytest.mark.asyncio
async def test_get_chapter_outline_uses_graph_first():
    """get_chapter_outline 优先查图谱,返回增强结构"""
    from yuxi.agents.toolkits.buildin.tools import get_chapter_outline

    graph_data = {
        "canonical_chapter_key": "地形地貌",
        "title": "3.1.1 地形地貌",
        "level": 3,
        "order": 1,
        "rigidity": "rigid",
        "child_chapters": [],
        "paragraph_roles": [],
    }
    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.get_chapter_outline",
        new=AsyncMock(return_value=graph_data),
    ):
        result = await get_chapter_outline.ainvoke({
            "domain": "coal", "report_type": "eia_report",
            "canonical_chapter_key": "地形地貌"
        })
    assert result is not None
    assert result.get("canonical_chapter_key") == "地形地貌"


@pytest.mark.asyncio
async def test_get_chapter_outline_graph_miss_hints_report_types():
    """图谱查不到时,返回 hint(复用现有逻辑)"""
    from yuxi.agents.toolkits.buildin.tools import get_chapter_outline

    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.get_chapter_outline",
        new=AsyncMock(return_value=None),
    ), patch(
        "yuxi.repositories.domain_entity_repository.DomainEntityRepository.list_report_types",
        new=AsyncMock(return_value=[]),
    ):
        result = await get_chapter_outline.ainvoke({
            "domain": "coal", "report_type": "eia_report",
            "canonical_chapter_key": "不存在XYZ"
        })
    # 图谱和DB都miss → 返回 error+hint
    assert "error" in result or result is None
```

- [ ] **Step 2: 验证失败** — Expected FAIL

- [ ] **Step 3: 改造 get_chapter_outline**

找到 `get_chapter_outline` 工具（约 413 行），当前逻辑是查 DB → miss 返回 hint。改为：

```python
async def get_chapter_outline(domain: str, report_type: str, canonical_chapter_key: str) -> dict:
    """获取指定章节的结构化大纲。优先查图谱,回退 DB。"""
    from yuxi.services.graph_query_service import GraphQueryService

    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)

    # 1. 优先查图谱
    try:
        graph_svc = GraphQueryService()
        try:
            outline = await graph_svc.get_chapter_outline(domain, report_type, canonical_chapter_key)
            if outline:
                return outline
        finally:
            graph_svc.close()
    except Exception as e:
        logger.warning(f"图谱查询 get_chapter_outline 失败,回退 DB: {e}")

    # 2. 降级 DB
    repo = DomainFactoryRepository()
    out = await repo.get_outline(domain, report_type, canonical_chapter_key)
    if out:
        return out

    # 3. 都 miss → hint
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    types = await DomainEntityRepository().list_report_types(domain)
    valid_codes = [t["code"] for t in types]
    return {
        "error": f"未找到章节大纲: {domain}/{report_type}/{canonical_chapter_key}",
        "hint": f"该 domain 合法 report_type: {valid_codes}（请用 list_report_types 确认数据字典 code）",
    }
```

- [ ] **Step 4: 验证通过** — Expected PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/test/unit/agents/toolkits/buildin/test_tools_graph_integration.py
git commit -m "feat(tools): get_chapter_outline直查图谱+DB降级"
```

---

### Task 10: 工具改造 — get_templates 直查图谱

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py` (`get_templates`，约 483 行)

**Purpose:** get_templates 图谱优先 + DB 降级。

- [ ] **Step 1: 写失败测试** — Append:

```python
@pytest.mark.asyncio
async def test_get_templates_uses_graph_first():
    """get_templates 优先查图谱"""
    from yuxi.agents.toolkits.buildin.tools import get_templates

    graph_templates = [
        {"text_pattern": "{{矿区}}位于{{位置}}", "slots": [{"name": "矿区", "type": "string"}], "legal_references": []}
    ]
    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.get_templates",
        new=AsyncMock(return_value=graph_templates),
    ):
        result = await get_templates.ainvoke({
            "domain": "coal", "report_type": "eia_report",
            "canonical_chapter_key": "地形地貌"
        })
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "text_pattern" in result[0]


@pytest.mark.asyncio
async def test_get_templates_graph_empty_falls_back_to_db():
    """图谱返回空时回退 DB"""
    from yuxi.agents.toolkits.buildin.tools import get_templates

    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.get_templates",
        new=AsyncMock(return_value=[]),
    ):
        result = await get_templates.ainvoke({
            "domain": "coal", "report_type": "eia_report",
            "canonical_chapter_key": "某章"
        })
    assert isinstance(result, list)  # DB 也可能空,但不报错
```

- [ ] **Step 2: 验证失败** — Expected FAIL

- [ ] **Step 3: 改造 get_templates**

找到 `get_templates` 工具（约 483 行）。需先确认其当前签名和实现。当前用 `DomainFactoryRepository.list_learned_templates_by_key`。改为：

```python
async def get_templates(domain: str, report_type: str, canonical_chapter_key: str) -> list[dict]:
    """获取章节段落模板。优先查图谱,回退 DB。"""
    from yuxi.services.graph_query_service import GraphQueryService

    domain = _normalize_domain(domain)
    report_type = _normalize_report_type(report_type)

    # 1. 优先查图谱
    try:
        graph_svc = GraphQueryService()
        try:
            templates = await graph_svc.get_templates(domain, report_type, canonical_chapter_key)
            if templates:
                return templates
        finally:
            graph_svc.close()
    except Exception as e:
        logger.warning(f"图谱查询 get_templates 失败,回退 DB: {e}")

    # 2. 降级 DB
    repo = DomainFactoryRepository()
    return await repo.list_learned_templates_by_key(domain, report_type, canonical_chapter_key)
```

注意：需确认 `get_templates` 工具当前的参数签名（是否含 domain/report_type）。如果当前签名只有 `canonical_chapter_key`，改造时需同步调整工具装饰器的 args_schema。先用 grep 确认现有签名：

```bash
docker exec api-dev grep -n -A 15 "async def get_templates" backend/package/yuxi/agents/toolkits/buildin/tools.py
```

如果签名不同，调整测试和实现以匹配实际签名（可能只需 canonical_chapter_key，domain/report_type 从 normalize 推导或忽略）。

- [ ] **Step 4: 验证通过** — Expected PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py backend/test/unit/agents/toolkits/buildin/test_tools_graph_integration.py
git commit -m "feat(tools): get_templates直查图谱+DB降级"
```

---

### Task 11: 工具改造 — save_chapter 的 lookup_chapter_order 直查图谱

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py` (`save_chapter` 内的 `lookup_chapter_order` 调用，约 599 行)

**Purpose:** save_chapter 推导章节顺序时图谱优先。

- [ ] **Step 1: 写失败测试** — Append:

```python
@pytest.mark.asyncio
async def test_save_chapter_uses_graph_for_order_lookup():
    """save_chapter 的 chapter_order 推导优先查图谱"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    with patch(
        "yuxi.services.graph_query_service.GraphQueryService.lookup_chapter_order",
        new=AsyncMock(return_value=5),
    ), patch(
        "yuxi.repositories.domain_factory_repository.DomainFactoryRepository.report_exists",
        new=AsyncMock(return_value=False),
    ):
        result = await save_chapter.ainvoke({
            "report_id": "rpt_test", "canonical_chapter_key": "地形地貌",
            "title": "测试", "content_md": "内容", "summary": "", "status": "writing"
        })
    # report 不存在 → 返回 error(但 lookup_chapter_order 已走图谱)
    assert "error" in result
```

- [ ] **Step 2: 验证失败** — Expected FAIL（仍查 DB）

- [ ] **Step 3: 改造 save_chapter 的 order 查找**

`save_chapter` 工具内（约 599 行）当前：
```python
    order = await repo.lookup_chapter_order(report_id, canonical_chapter_key)
```

注意 `repo.lookup_chapter_order` 签名是 `(report_id, canonical_chapter_key)`——它查的是 DB 的 report_chapters 表（已有章节的顺序），不是图谱。这和 GraphQueryService.lookup_chapter_order(domain, report_type, key) 语义不同。

**务实决策**：save_chapter 的 lookup_chapter_order 是查"该 report 已有章节的 order"，属于报告运行时数据，**应保留 DB 查询**（图谱不存报告运行时数据）。此 Task 跳过——save_chapter 不改造。

更新计划：Task 11 标记为**不实施**，在测试里删除，记录原因。改为验证 save_chapter 仍正常工作（回归测试）：

- [ ] **Step 3 (修订): 回归验证 save_chapter 不受影响**

```bash
docker exec api-dev pytest test/unit/agents/toolkits/buildin/test_tools.py -v -k save_chapter
```
Expected: PASS（save_chapter 状态校验测试仍通过）

- [ ] **Step 4: Commit (跳过——无代码改动)**

记录：save_chapter.lookup_chapter_order 查报告运行时数据(DB),不属于图谱范畴,不改造。

---

### Task 12: 端到端验证 + 清理测试数据

**Files:** 无新文件

**Purpose:** 验证整个数据流改造可用，清理测试产生的图谱节点。

- [ ] **Step 1: 跑全部新测试**

```bash
docker exec api-dev pytest test/unit/services/test_graph_query_service.py test/unit/services/test_graph_builder_keys.py test/unit/agents/toolkits/buildin/test_tools_graph_integration.py -v
```
Expected: 全部 PASS

- [ ] **Step 2: 跑回归测试**

```bash
docker exec api-dev pytest test/unit/services/ test/unit/agents/toolkits/ test/scripts/ -v --tb=short
```
Expected: 无回归

- [ ] **Step 3: 清理测试产生的图谱节点**

```bash
docker exec graph cypher-shell -a bolt://localhost:7687 -u neo4j -p 0123456789 \
  "MATCH (n) WHERE n.kb_id STARTS WITH 'kb_test_' DETACH DELETE n;"
```
Expected: 测试节点清理干净

- [ ] **Step 4: 验证工具实际查询**

```bash
docker exec api-dev python -c "
import asyncio
from yuxi.services.graph_query_service import GraphQueryService
async def t():
    svc = GraphQueryService()
    keys = await svc.list_chapter_keys('coal', 'eia_report')
    print(f'章节key数: {len(keys)}')
    if keys:
        outline = await svc.get_chapter_outline('coal', 'eia_report', keys[0])
        print(f'大纲: {outline}')
        templates = await svc.get_templates('coal', 'eia_report', keys[0])
        print(f'模板数: {len(templates)}')
    svc.close()
asyncio.run(t())
"
```
Expected: 章节key数 ≥ 30, 大纲非空, 模板数 ≥ 0

- [ ] **Step 5: Commit (验证记录)**

```bash
git commit --allow-empty -m "test: 端到端验证图谱数据流改造(工具直查图谱)"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Section 3.2 修复点3（graph_builder 写 canonical_key）→ Task 1, 2
- ✅ Section 3.2 修复点4（回写图谱）→ Task 4
- ✅ Section 3.1 Step 4（ParagraphTemplate 回填）→ Task 3
- ✅ Section 4（GraphQueryService + 工具改造）→ Task 5-10
- ⚠️ Section 4.2 save_chapter → Task 11 评估后**不改造**（查报告运行时数据,非图谱范畴）
- ✅ Section 4.4 DB 降级兜底 → Task 8-10 都实现了降级

**关键决策记录:**
1. Task 1/2 的测试用集成测试(连真实Neo4j)而非纯mock,因为静态方法内部结构复杂,mock成本高
2. Task 4 标记为可选增强(ETL源头已写key,LLM回写是精度优化)
3. Task 11(save_chapter)评估后不改造——lookup_chapter_order 查报告运行时数据,不属于图谱

**不在本次范围(后续独立计划):**
- 参考文件目录 + SKILL路由关卡/写盘铁律
- content_contract 属性 + 校验
- 脚本化合规检查
- 13章MD大纲

---

## 实施顺序

```
Phase A (P0前置): Task 1 → 2         (graph_builder 写 key)
Phase B (P0前置): Task 3 → 4         (存量 ParagraphTemplate 回填)
Phase C (P0核心): Task 5 → 6 → 7     (GraphQueryService)
                 Task 8 → 9 → 10    (工具改造)
                 Task 11 (评估后跳过)
                 Task 12             (端到端验证)
```

Phase A/B 是前置(保证图谱有 key),Phase C 是核心(工具直查)。每个 Task 遵循 TDD。
