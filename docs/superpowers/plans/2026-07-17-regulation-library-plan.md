# 标准规范库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 零侵入构建标准规范库：KB chunks 后处理富化（条款结构 tags 回填）+ 指标结构化提取 + 确定性 Neo4j 图谱

**Architecture:** 全部新代码在 `backend/package/yuxi/extensions/regulation_library/` 与 `web/src/extensions/regulation-library/`；上游 `knowledge/` 模块零改动；唯一侵入点为 `server/routers/__init__.py` 一行注册。数据流：KB 正常入库 → 人工触发富化 → 解析条款结构写 `knowledge_chunks.tags` → LLM 提取限值表写 `standard_indicators` → 确定性写 Neo4j。

**Tech Stack:** Python 3.13, SQLAlchemy async, neo4j driver, FastAPI, Vue 3 + Ant Design Vue

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/package/yuxi/extensions/__init__.py` | 新建 | 扩展区包标记 |
| `backend/package/yuxi/extensions/regulation_library/__init__.py` | 新建 | 包标记 |
| `backend/package/yuxi/extensions/regulation_library/models.py` | 新建 | StandardIndicator 模型 + ensure_schema DDL |
| `backend/package/yuxi/extensions/regulation_library/unit_parser.py` | 新建 | 按 doc_type 解析结构单元（纯函数，可测） |
| `backend/package/yuxi/extensions/regulation_library/enrichment_service.py` | 新建 | 编排：读 chunks → 解析 → 回填 tags → 提取指标 → 建图 |
| `backend/package/yuxi/extensions/regulation_library/indicator_extractor.py` | 新建 | 限值表 → LLM → 结构化指标行 |
| `backend/package/yuxi/extensions/regulation_library/graph_writer.py` | 新建 | 确定性 Neo4j RegDocument→RegUnit→Indicator |
| `backend/package/yuxi/extensions/regulation_library/router.py` | 新建 | API 端点 |
| `backend/server/routers/__init__.py` | 修改 | +1 行注册（唯一侵入点） |
| `backend/test/unit/extensions/test_unit_parser.py` | 新建 | 单元解析测试 |
| `backend/test/unit/extensions/test_indicator_extractor.py` | 新建 | 指标解析测试 |
| `web/src/extensions/regulation-library/regulation_api.js` | 新建 | 前端 API |
| `web/src/extensions/regulation-library/RegulationEnrichPanel.vue` | 新建 | 加工面板（抽屉式） |
| `web/src/views/DomainFactoryView.vue` | 修改 | header 加"标准规范库"按钮（pisuan 定制文件） |

---

## Task 1: 扩展包骨架 + StandardIndicator 模型

**Files:**
- Create: `backend/package/yuxi/extensions/__init__.py`（空文件）
- Create: `backend/package/yuxi/extensions/regulation_library/__init__.py`（空文件）
- Create: `backend/package/yuxi/extensions/regulation_library/models.py`

- [x] **Step 1: 创建包结构与模型**

`models.py`:

```python
"""标准规范库数据模型 - standard_indicators 表（唯一新表）"""

from __future__ import annotations

from sqlalchemy import text

from yuxi.storage.postgres.manager import pg_manager

# 建表 DDL（扩展自管理，不侵入上游 manager.py）
_DDL = """
CREATE TABLE IF NOT EXISTS standard_indicators (
    id          VARCHAR(64) PRIMARY KEY,
    doc_code    VARCHAR(128) NOT NULL,
    unit_no     VARCHAR(64),
    chunk_id    VARCHAR(128),
    pollutant   VARCHAR(128),
    metric      VARCHAR(128),
    limit_value NUMERIC,
    unit        VARCHAR(32),
    condition   VARCHAR(255)
);
CREATE INDEX IF NOT EXISTS idx_std_ind_doc_code ON standard_indicators(doc_code);
CREATE INDEX IF NOT EXISTS idx_std_ind_pollutant ON standard_indicators(pollutant);
"""

_schema_ready = False


async def ensure_schema() -> None:
    """惰性建表：首次使用时执行 DDL（幂等）"""
    global _schema_ready
    if _schema_ready:
        return
    async with pg_manager.get_async_session_context() as session:
        for stmt in _DDL.strip().split(";"):
            if stmt.strip():
                await session.execute(text(stmt))
    _schema_ready = True
```

- [x] **Step 2: 验证建表**

```bash
docker exec api-dev python -c "
import asyncio
from yuxi.extensions.regulation_library.models import ensure_schema
asyncio.run(ensure_schema())
print('OK')
"
docker exec postgres psql -U postgres -d yuxi_know -c "\d standard_indicators"
```

Expected: 表结构输出，9 列。

- [x] **Step 3: Commit**

```bash
git add backend/package/yuxi/extensions/
git commit -m "feat(extensions): 标准规范库扩展包骨架+standard_indicators表"
```

---

## Task 2: 结构单元解析器（unit_parser）

**Files:**
- Create: `backend/package/yuxi/extensions/regulation_library/unit_parser.py`
- Create: `backend/test/unit/extensions/__init__.py`（空）
- Create: `backend/test/unit/extensions/test_unit_parser.py`

- [x] **Step 1: 写失败测试**

`test_unit_parser.py`:

```python
"""结构单元解析测试：4 类文档格式的 unit_no 识别"""

from yuxi.extensions.regulation_library.unit_parser import parse_chunk_unit


def test_standard_clause():
    """标准条款: 4.2 / 4.2.1"""
    r = parse_chunk_unit("4.2 环境空气功能区分类\n环境空气功能区分为二类...", "technical_standard")
    assert r == {"unit_no": "4.2", "unit_type": "clause", "parent_unit": "4",
                 "title": "环境空气功能区分类"}


def test_law_article():
    """法律法条: 第X条"""
    r = parse_chunk_unit("第十二条 国务院环境保护主管部门...", "law")
    assert r["unit_no"] == "第十二条"
    assert r["unit_type"] == "article"
    assert r["parent_unit"] is None


def test_section_chinese_numbering():
    """规划/规章: 三、(一) 自由编号"""
    r = parse_chunk_unit("三、重点任务\n（一）加强源头防控...", "national_plan")
    assert r["unit_no"] == "三"
    assert r["unit_type"] == "section"


def test_table_chunk():
    """表格 chunk: 含 HTML table 或 markdown 表格 → table 类型"""
    r = parse_chunk_unit("表1 环境空气污染物基本项目浓度限值\n<table><tr>...", "technical_standard")
    assert r["unit_no"] == "表1"
    assert r["unit_type"] == "table"


def test_no_match_returns_none():
    """无结构线索的 chunk 返回 None"""
    assert parse_chunk_unit("这是一段没有编号的叙述文字。", "technical_standard") is None
```

- [x] **Step 2: 验证失败**

```bash
docker exec api-dev sh -c 'cd /app && python -m pytest test/unit/extensions/test_unit_parser.py -v'
```

Expected: FAIL (module not found)

- [x] **Step 3: 实现 unit_parser.py**

```python
"""按 doc_type 从 chunk 文本解析结构单元（条款/法条/章节/表格）。

纯函数模块，供 enrichment_service 调用。
"""

from __future__ import annotations

import re

# 表格标题: 表1 / 表 2-1
_TABLE_RE = re.compile(r"^表\s*(\d[\d\-]*)\s*(.*)$", re.MULTILINE)
# 标准条款: 4.2 标题
_CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$", re.MULTILINE)
# 法条: 第X条
_ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百千零〇]+条)\s*(.*)$", re.MULTILINE)
# 中文章节号: 三、 或 （一）
_CN_SECTION_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.*)$", re.MULTILINE)


def parse_chunk_unit(content: str, doc_type: str) -> dict | None:
    """从 chunk 内容解析结构单元信息。

    Returns:
        {unit_no, unit_type, parent_unit, title} 或 None（无结构线索）
    """
    text = (content or "").strip()
    if not text:
        return None

    # 表格优先（所有 doc_type 通用）
    m = _TABLE_RE.search(text[:200])
    if m and ("<table" in text or "|" in text):
        return {"unit_no": f"表{m.group(1)}", "unit_type": "table",
                "parent_unit": None, "title": m.group(2).strip()}

    if doc_type == "law" or doc_type.endswith("regulation") or doc_type.endswith("rule"):
        m = _ARTICLE_RE.search(text[:100])
        if m:
            return {"unit_no": m.group(1), "unit_type": "article",
                    "parent_unit": None, "title": m.group(2).strip()[:100]}

    if doc_type in ("technical_standard",):
        m = _CLAUSE_RE.search(text[:100])
        if m:
            num = m.group(1)
            parent = ".".join(num.split(".")[:-1]) or None
            return {"unit_no": num, "unit_type": "clause",
                    "parent_unit": parent, "title": m.group(2).strip()[:100]}

    # 规划/政策/项目资料: 中文编号章节
    m = _CN_SECTION_RE.search(text[:100])
    if m:
        return {"unit_no": m.group(1), "unit_type": "section",
                "parent_unit": None, "title": m.group(2).strip()[:100]}

    # fallback: 法律类文档也可能出现条款数字编号
    m = _CLAUSE_RE.search(text[:100])
    if m:
        num = m.group(1)
        parent = ".".join(num.split(".")[:-1]) or None
        return {"unit_no": num, "unit_type": "clause",
                "parent_unit": parent, "title": m.group(2).strip()[:100]}

    return None
```

- [x] **Step 4: 验证通过**

```bash
docker exec api-dev sh -c 'cd /app && python -m pytest test/unit/extensions/test_unit_parser.py -v'
```

Expected: 5 passed

- [x] **Step 5: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/unit_parser.py backend/test/unit/extensions/
git commit -m "feat(extensions): 结构单元解析器(条款/法条/章节/表格)"
```

---

## Task 3: 指标提取器（indicator_extractor）

**Files:**
- Create: `backend/package/yuxi/extensions/regulation_library/indicator_extractor.py`
- Create: `backend/test/unit/extensions/test_indicator_extractor.py`

- [x] **Step 1: 写失败测试**

`test_indicator_extractor.py`:

```python
"""指标提取器测试：LLM 响应解析（LLM 调用 mock）"""

from yuxi.extensions.regulation_library.indicator_extractor import parse_indicator_response


def test_parse_valid_response():
    text = '''[
      {"pollutant": "SO2", "metric": "年平均浓度限值", "limit_value": 60,
       "unit": "μg/m³", "condition": "二类区"},
      {"pollutant": "NO2", "metric": "年平均浓度限值", "limit_value": 40,
       "unit": "μg/m³", "condition": "二类区"}
    ]'''
    rows = parse_indicator_response(text)
    assert len(rows) == 2
    assert rows[0]["pollutant"] == "SO2"
    assert rows[0]["limit_value"] == 60


def test_parse_with_code_fence():
    text = '```json\n[{"pollutant": "TSP", "metric": "日均", "limit_value": 300, "unit": "μg/m³", "condition": ""}]\n```'
    rows = parse_indicator_response(text)
    assert len(rows) == 1


def test_parse_invalid_returns_empty():
    assert parse_indicator_response("没有 JSON") == []
    assert parse_indicator_response("") == []


def test_rows_missing_required_fields_skipped():
    text = '[{"pollutant": "SO2"}, {"pollutant": "NO2", "metric": "年均", "limit_value": 40, "unit": "μg/m³"}]'
    rows = parse_indicator_response(text)
    # 缺 metric/limit_value 的行被跳过
    assert len(rows) == 1
    assert rows[0]["pollutant"] == "NO2"
```

- [x] **Step 2: 验证失败**

```bash
docker exec api-dev sh -c 'cd /app && python -m pytest test/unit/extensions/test_indicator_extractor.py -v'
```

- [x] **Step 3: 实现 indicator_extractor.py**

```python
"""限值表 → LLM → 结构化指标行"""

from __future__ import annotations

import json
import re
from typing import Any

from yuxi.utils import logger

_PROMPT = """你是环保标准专家。以下是标准文档《{doc_code}》中的一张限值表（{unit_no}），请提取所有指标限值。

表格内容:
{table_content}

输出 JSON 数组，每行一个指标:
[{{"pollutant": "污染物/指标名", "metric": "指标含义(如 年平均浓度限值)",
  "limit_value": 数值, "unit": "单位", "condition": "适用条件(如 二类区/一级，无则空串)"}}]

要求:
- limit_value 必须是纯数值（区间取上限并在 condition 注明）
- 严格 JSON 数组输出，无注释无代码块标记
"""


def parse_indicator_response(text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的指标 JSON 数组，过滤缺少必填字段的行"""
    m = re.search(r"\[[\s\S]*\]", text or "")
    if not m:
        return []
    try:
        rows = json.loads(m.group())
    except (json.JSONDecodeError, ValueError):
        return []
    valid = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("pollutant") and r.get("metric") and r.get("limit_value") is not None:
            valid.append(r)
    return valid


async def extract_indicators(doc_code: str, unit_no: str, table_content: str) -> list[dict[str, Any]]:
    """对单张限值表调用 LLM 提取指标"""
    from yuxi.models.chat import select_model

    prompt = _PROMPT.format(doc_code=doc_code, unit_no=unit_no or "未编号表",
                            table_content=table_content[:6000])
    try:
        model = select_model()
        response = await model.call(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        return parse_indicator_response(text)
    except Exception as e:
        logger.warning(f"指标提取失败 {doc_code} {unit_no}: {e}")
        return []
```

- [x] **Step 4: 验证通过**

```bash
docker exec api-dev sh -c 'cd /app && python -m pytest test/unit/extensions/test_indicator_extractor.py -v'
```

Expected: 4 passed

- [x] **Step 5: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/indicator_extractor.py backend/test/unit/extensions/test_indicator_extractor.py
git commit -m "feat(extensions): 限值表指标提取器(LLM+解析)"
```

---

## Task 4: 图谱 writer（graph_writer）

**Files:**
- Create: `backend/package/yuxi/extensions/regulation_library/graph_writer.py`

- [x] **Step 1: 实现（照 graph_builder.py 的驱动模式）**

```python
"""确定性 Neo4j 图谱写入: RegDocument → RegUnit → Indicator"""

from __future__ import annotations

import os
from typing import Any

from neo4j import GraphDatabase as Neo4jDriver

from yuxi.utils import logger


class RegulationGraphWriter:
    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is not None:
            return self._driver
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "0123456789")
        try:
            self._driver = Neo4jDriver.driver(uri, auth=(username, password))
            with self._driver.session() as session:
                session.run("RETURN 1")
            return self._driver
        except Exception as e:
            logger.warning(f"RegulationGraphWriter: Neo4j 连接失败: {e}")
            return None

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def write_document_graph(
        self,
        doc_code: str,
        doc_name: str,
        doc_type: str,
        units: list[dict[str, Any]],       # [{unit_no, unit_type, parent_unit, title, chunk_id}]
        indicators: list[dict[str, Any]],  # [{unit_no, pollutant, metric, limit_value, unit, condition}]
    ) -> dict[str, int]:
        """幂等写入单个规范文档的图谱结构"""
        driver = self._get_driver()
        if driver is None:
            return {"nodes": 0, "relationships": 0}

        stats = {"nodes": 0, "relationships": 0}
        with driver.session() as session:
            # 文档节点
            session.run(
                "MERGE (d:RegDocument {doc_code: $code}) "
                "SET d.name = $name, d.doc_type = $dtype",
                code=doc_code, name=doc_name, dtype=doc_type,
            )
            stats["nodes"] += 1

            # 单元节点 + 层级
            for u in units:
                unit_id = f"{doc_code}#{u['unit_no']}"
                session.run(
                    "MERGE (u:RegUnit {id: $uid}) "
                    "SET u.unit_no = $no, u.unit_type = $utype, u.title = $title, "
                    "    u.chunk_id = $chunk_id, u.doc_code = $code "
                    "WITH u MATCH (d:RegDocument {doc_code: $code}) "
                    "MERGE (d)-[:HAS_UNIT]->(u)",
                    uid=unit_id, no=u["unit_no"], utype=u["unit_type"],
                    title=u.get("title", ""), chunk_id=u.get("chunk_id", ""),
                    code=doc_code,
                )
                stats["nodes"] += 1
                stats["relationships"] += 1
                # 父子层级
                if u.get("parent_unit"):
                    session.run(
                        "MATCH (p:RegUnit {id: $pid}), (c:RegUnit {id: $cid}) "
                        "MERGE (p)-[:HAS_CHILD]->(c)",
                        pid=f"{doc_code}#{u['parent_unit']}", cid=unit_id,
                    )
                    stats["relationships"] += 1

            # 指标节点
            for ind in indicators:
                ind_id = f"{doc_code}#{ind.get('unit_no','')}#{ind['pollutant']}#{ind['metric']}"
                session.run(
                    "MERGE (i:Indicator {id: $iid}) "
                    "SET i.pollutant = $p, i.metric = $m, i.limit_value = $v, "
                    "    i.unit = $u, i.condition = $c "
                    "WITH i MATCH (ru:RegUnit {id: $uid}) "
                    "MERGE (ru)-[:HAS_INDICATOR]->(i)",
                    iid=ind_id, p=ind["pollutant"], m=ind["metric"],
                    v=ind.get("limit_value"), u=ind.get("unit", ""),
                    c=ind.get("condition", ""),
                    uid=f"{doc_code}#{ind.get('unit_no','')}",
                )
                stats["nodes"] += 1
                stats["relationships"] += 1

        return stats
```

- [x] **Step 2: 语法验证**

```bash
docker exec api-dev python -c "import ast; ast.parse(open('/app/package/yuxi/extensions/regulation_library/graph_writer.py', encoding='utf-8').read()); print('OK')"
```

- [x] **Step 3: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/graph_writer.py
git commit -m "feat(extensions): 确定性Neo4j规范文档图谱writer"
```

---

## Task 5: 富化编排服务（enrichment_service）

**Files:**
- Create: `backend/package/yuxi/extensions/regulation_library/enrichment_service.py`

- [x] **Step 1: 实现编排逻辑**

```python
"""规范文档富化编排：读 chunks → 解析结构 → 回填 tags → 提取指标 → 建图"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from yuxi.extensions.regulation_library import indicator_extractor
from yuxi.extensions.regulation_library.graph_writer import RegulationGraphWriter
from yuxi.extensions.regulation_library.models import ensure_schema
from yuxi.extensions.regulation_library.unit_parser import parse_chunk_unit
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk
from yuxi.utils import logger


async def enrich_regulation_file(
    kb_id: str,
    file_id: str,
    doc_code: str,
    doc_name: str,
    doc_type: str,
) -> dict[str, Any]:
    """对已入库的规范文档文件执行富化（幂等，可重跑）。

    Args:
        kb_id/file_id: 知识库与文件标识（上游已入库）
        doc_code: 文档编号，如 "GB 3095-2012"
        doc_name: 文档名称
        doc_type: LEGAL_TYPE_MAP 的 9 类之一
    """
    await ensure_schema()

    # 1. 读取该文件全部 chunks（只读上游数据）
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.kb_id == kb_id, KnowledgeChunk.file_id == file_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        chunks = result.scalars().all()

    if not chunks:
        return {"error": "该文件无 chunks，请先完成知识库索引"}

    # 2. 解析结构单元 → 回填 tags
    units: list[dict] = []
    table_chunks: list[tuple[str, str, str]] = []  # (chunk_id, unit_no, content)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.kb_id == kb_id, KnowledgeChunk.file_id == file_id)
        )
        for chunk in result.scalars().all():
            unit = parse_chunk_unit(chunk.content, doc_type)
            if not unit:
                continue
            chunk.tags = {
                "doc_code": doc_code,
                "doc_type": doc_type,
                **unit,
            }
            units.append({**unit, "chunk_id": chunk.chunk_id})
            if unit["unit_type"] == "table":
                table_chunks.append((chunk.chunk_id, unit["unit_no"], chunk.content))

    logger.info(f"规范富化: {doc_code} 解析出 {len(units)} 个结构单元, {len(table_chunks)} 张表")

    # 3. 限值表 → LLM 提取指标 → standard_indicators
    all_indicators: list[dict] = []
    for chunk_id, unit_no, content in table_chunks:
        rows = await indicator_extractor.extract_indicators(doc_code, unit_no, content)
        for r in rows:
            r["unit_no"] = unit_no
            r["chunk_id"] = chunk_id
        all_indicators.extend(rows)

    if all_indicators:
        from sqlalchemy import text as sql_text
        async with pg_manager.get_async_session_context() as session:
            # 幂等：先删该文档旧指标再插入
            await session.execute(
                sql_text("DELETE FROM standard_indicators WHERE doc_code = :code"),
                {"code": doc_code},
            )
            for ind in all_indicators:
                await session.execute(
                    sql_text(
                        "INSERT INTO standard_indicators "
                        "(id, doc_code, unit_no, chunk_id, pollutant, metric, limit_value, unit, condition) "
                        "VALUES (:id, :code, :uno, :cid, :p, :m, :v, :u, :c)"
                    ),
                    {"id": uuid.uuid4().hex[:32], "code": doc_code,
                     "uno": ind.get("unit_no"), "cid": ind.get("chunk_id"),
                     "p": ind["pollutant"], "m": ind["metric"],
                     "v": ind["limit_value"], "u": ind.get("unit", ""),
                     "c": ind.get("condition", "")},
                )

    # 4. 确定性建图
    writer = RegulationGraphWriter()
    try:
        graph_stats = writer.write_document_graph(doc_code, doc_name, doc_type, units, all_indicators)
    finally:
        writer.close()

    return {
        "doc_code": doc_code,
        "units": len(units),
        "tables": len(table_chunks),
        "indicators": len(all_indicators),
        "graph": graph_stats,
    }


async def query_indicators(doc_code: str | None = None, pollutant: str | None = None) -> list[dict]:
    """精确查询指标（供 API 与 writer 工具使用）"""
    from sqlalchemy import text as sql_text
    await ensure_schema()
    conditions, params = [], {}
    if doc_code:
        conditions.append("doc_code = :code")
        params["code"] = doc_code
    if pollutant:
        conditions.append("pollutant = :p")
        params["p"] = pollutant
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            sql_text(f"SELECT doc_code, unit_no, pollutant, metric, limit_value, unit, condition "
                     f"FROM standard_indicators {where} ORDER BY doc_code, unit_no"),
            params,
        )
        return [dict(r._mapping) for r in result.all()]
```

- [x] **Step 2: 语法验证**

```bash
docker exec api-dev python -c "import ast; ast.parse(open('/app/package/yuxi/extensions/regulation_library/enrichment_service.py', encoding='utf-8').read()); print('OK')"
```

- [x] **Step 3: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/enrichment_service.py
git commit -m "feat(extensions): 规范文档富化编排服务"
```

---

## Task 6: API 路由 + 注册

**Files:**
- Create: `backend/package/yuxi/extensions/regulation_library/router.py`
- Modify: `backend/server/routers/__init__.py`（+1 行，唯一侵入点）

- [x] **Step 1: 实现 router.py**

```python
"""标准规范库 API - /api/regulation-library/*"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from server.utils.auth_middleware import get_admin_user
from yuxi.extensions.regulation_library import enrichment_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

regulation_library = APIRouter(prefix="/regulation-library", tags=["Regulation Library"])


@regulation_library.post("/enrich")
async def enrich_file(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """对已入库的规范文档执行富化（条款解析+指标提取+建图）"""
    try:
        kb_id = payload.get("kb_id", "")
        file_id = payload.get("file_id", "")
        doc_code = payload.get("doc_code", "")
        doc_name = payload.get("doc_name", "")
        doc_type = payload.get("doc_type", "technical_standard")
        if not kb_id or not file_id or not doc_code:
            raise HTTPException(status_code=400, detail="kb_id/file_id/doc_code 必填")
        result = await enrichment_service.enrich_regulation_file(
            kb_id, file_id, doc_code, doc_name, doc_type
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"规范富化失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"富化失败: {str(e)}")


@regulation_library.get("/indicators")
async def list_indicators(
    doc_code: str | None = Query(None),
    pollutant: str | None = Query(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """精确查询标准指标"""
    try:
        rows = await enrichment_service.query_indicators(doc_code, pollutant)
        return {"items": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"指标查询失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
```

- [x] **Step 2: 注册路由（唯一侵入点）**

在 `server/routers/__init__.py` 的 `if not _LITE_MODE:` 块末尾加一行：

```python
    from yuxi.extensions.regulation_library.router import regulation_library
    router.include_router(regulation_library)  # /api/regulation-library/* 标准规范库(pisuan扩展)
```

- [x] **Step 3: 验证 API 注册**

```bash
docker exec api-dev python -c "import ast; ast.parse(open('/app/server/routers/__init__.py', encoding='utf-8').read()); print('OK')"
docker logs api-dev --tail 5
```

- [x] **Step 4: Commit**

```bash
git add backend/package/yuxi/extensions/regulation_library/router.py backend/server/routers/__init__.py
git commit -m "feat(extensions): 标准规范库API路由(唯一侵入点1行注册)"
```

---

## Task 7: 前端面板

**Files:**
- Create: `web/src/extensions/regulation-library/regulation_api.js`
- Create: `web/src/extensions/regulation-library/RegulationEnrichPanel.vue`
- Modify: `web/src/views/DomainFactoryView.vue`（header 加按钮，pisuan 定制文件）

- [x] **Step 1: 前端 API**

`regulation_api.js`:

```javascript
/**
 * 标准规范库 API (pisuan 扩展)
 */
import { apiAdminGet, apiAdminPost } from '@/apis/base'

export const regulationApi = {
  enrichFile: (payload) =>
    apiAdminPost('/api/regulation-library/enrich', payload),

  listIndicators: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null && v !== '')
    ).toString()
    return apiAdminGet('/api/regulation-library/indicators' + (qs ? `?${qs}` : ''))
  },
}
```

- [x] **Step 2: RegulationEnrichPanel.vue（抽屉式面板）**

```vue
<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { regulationApi } from './regulation_api'
import { databaseApi, fileApi } from '@/apis/knowledge_api'

const visible = defineModel('open', { type: Boolean, default: false })

const kbList = ref([])
const fileList = ref([])
const form = ref({ kb_id: '', file_id: '', doc_code: '', doc_name: '', doc_type: 'technical_standard' })
const enriching = ref(false)
const result = ref(null)

const DOC_TYPES = [
  { value: 'technical_standard', label: '技术规范/标准' },
  { value: 'law', label: '法律' },
  { value: 'admin_regulation', label: '行政法规' },
  { value: 'ministry_rule', label: '部门规章' },
  { value: 'local_rule', label: '地方规章' },
  { value: 'national_plan', label: '国家规划' },
  { value: 'local_plan', label: '地方规划' },
  { value: 'project_material', label: '项目资料' },
]

const loadKbs = async () => {
  try {
    const res = await databaseApi.getDatabases()
    kbList.value = (res.databases || []).filter(db => db.kb_type === 'milvus' || db.type === 'milvus')
  } catch { message.error('加载知识库失败') }
}

const loadFiles = async () => {
  if (!form.value.kb_id) return
  try {
    const res = await databaseApi.getDatabaseInfo(form.value.kb_id)
    fileList.value = Object.values(res.files || {})
  } catch { message.error('加载文件列表失败') }
}

const runEnrich = async () => {
  const f = form.value
  if (!f.kb_id || !f.file_id || !f.doc_code) {
    message.warning('请选择知识库、文件并填写文档编号')
    return
  }
  enriching.value = true
  result.value = null
  try {
    const res = await regulationApi.enrichFile(f)
    result.value = res.result
    message.success(`富化完成: ${res.result.units} 个单元, ${res.result.indicators} 条指标`)
  } catch (e) {
    message.error('富化失败: ' + (e.message || e))
  } finally {
    enriching.value = false
  }
}
</script>

<template>
  <a-drawer v-model:open="visible" title="标准规范库加工" width="520" @after-open-change="(o) => o && loadKbs()">
    <a-form layout="vertical">
      <a-form-item label="知识库" required>
        <a-select v-model:value="form.kb_id" placeholder="选择存放规范文档的知识库" @change="loadFiles">
          <a-select-option v-for="kb in kbList" :key="kb.kb_id" :value="kb.kb_id">{{ kb.name }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="文件" required>
        <a-select v-model:value="form.file_id" placeholder="选择已索引完成的规范文档">
          <a-select-option v-for="f in fileList" :key="f.file_id" :value="f.file_id">{{ f.filename }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="文档编号" required>
        <a-input v-model:value="form.doc_code" placeholder="如 GB 3095-2012 / 水保[2013]188号" />
      </a-form-item>
      <a-form-item label="文档名称">
        <a-input v-model:value="form.doc_name" placeholder="如 环境空气质量标准" />
      </a-form-item>
      <a-form-item label="文档类型">
        <a-select v-model:value="form.doc_type">
          <a-select-option v-for="t in DOC_TYPES" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-button type="primary" block :loading="enriching" @click="runEnrich">开始加工</a-button>
    </a-form>

    <a-divider />
    <template v-if="result">
      <a-descriptions title="加工结果" :column="1" size="small">
        <a-descriptions-item label="结构单元">{{ result.units }}</a-descriptions-item>
        <a-descriptions-item label="限值表">{{ result.tables }}</a-descriptions-item>
        <a-descriptions-item label="提取指标">{{ result.indicators }}</a-descriptions-item>
        <a-descriptions-item label="图谱节点">{{ result.graph?.nodes || 0 }}</a-descriptions-item>
      </a-descriptions>
    </template>
  </a-drawer>
</template>
```

- [x] **Step 3: DomainFactoryView 加入口按钮**

在 header 按钮区（"实体构建器"按钮旁）添加：

```html
<a-button @click="regulationPanelOpen = true">标准规范库</a-button>
```

script 中添加：

```javascript
import RegulationEnrichPanel from '@/extensions/regulation-library/RegulationEnrichPanel.vue'
const regulationPanelOpen = ref(false)
```

template 末尾添加：

```html
<RegulationEnrichPanel v-model:open="regulationPanelOpen" />
```

- [x] **Step 4: 验证编译**

```bash
docker logs web-dev --tail 3
```

- [x] **Step 5: Commit**

```bash
git add web/src/extensions/ web/src/views/DomainFactoryView.vue
git commit -m "feat(extensions): 标准规范库前端加工面板"
```

---

## 自审

**Spec coverage:**
- ✅ Spec §4 零侵入架构 → Task 1-6（extensions/ 目录 + 1 行注册）
- ✅ Spec §6.1 条款结构 tags → Task 2+5
- ✅ Spec §6.2 指标表 → Task 1+3
- ✅ Spec §6.3 Neo4j → Task 4
- ✅ Spec §9 渐进式建库（单文件加工）→ Task 7 面板
- ⏸ Spec §7 条款引用匹配（P1）与 §8 writer 工具（P1）→ 后续 plan

**Placeholder scan:** 无 TBD/TODO，所有步骤含完整代码。

**Type consistency:** `parse_chunk_unit` 返回 dict 与 enrichment_service 使用一致；`extract_indicators` 签名与调用一致；`enrich_regulation_file` 参数与 router payload 一致。
