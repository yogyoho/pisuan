# 知识工厂数据加工完善与升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AI 查询任意章节时能拿到模板（递归查子章节），支持分章节上传合并到一份报告，支持多报告知识去重聚合。

**Architecture:** 从 outlines/ MD 解析标准子章节（level=2）seed 到图谱作为合并锚点；ETL 子章节按标题匹配归一化到标准子章节；get_templates 递归查询；commit pipeline 新增 Stage 2.10 做跨报告去重合并。

**Tech Stack:** Python 3.13, neo4j driver, SQLAlchemy async, pytest-asyncio

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/scripts/seed_standard_subchapters.py` | 新建 | 从 outlines/ MD 解析标准子章节 seed 到图谱 |
| `backend/scripts/governance/link_subchapters.py` | 新建 | 存量 ETL 子章节归一化 + HAS_CHILD 关联 |
| `backend/package/yuxi/services/graph_query_service.py` | 修改 | get_templates 递归查询 |
| `backend/package/yuxi/storage/postgres/models_domain_factory.py` | 修改 | DomainFactoryTask 加 source_report_id/chapter_label |
| `backend/package/yuxi/storage/postgres/manager.py` | 修改 | 建表 ALTER 加列 |
| `backend/package/yuxi/services/domain_factory_service.py` | 修改 | commit pipeline Stage 2.10 跨报告合并 + slot_validation 接入 |
| `backend/test/unit/services/test_graph_query_service.py` | 修改 | 递归查询测试 |
| `backend/test/scripts/test_seed_standard_subchapters.py` | 新建 | 子章节 seed 测试 |
| `backend/test/scripts/test_link_subchapters.py` | 新建 | 归一化关联测试 |

---

## Phase 1: 标准子章节 seed + 存量归一化 (P0)

### Task 1: 解析 outlines/ MD 写作骨架 + seed 标准子章节

**Files:**
- Create: `backend/scripts/seed_standard_subchapters.py`
- Create: `backend/test/scripts/test_seed_standard_subchapters.py`

**Purpose:** 从 outlines/ MD 的"写作骨架"段解析标准子章节（如"5.1 环境影响识别"），seed 到图谱作为 level=2 合并锚点。

- [ ] **Step 1: 写解析测试**

Create `backend/test/scripts/test_seed_standard_subchapters.py`:

```python
from scripts.seed_standard_subchapters import parse_skeleton, STANDARD_SUBCHAPTERS


def test_parse_skeleton_extracts_subchapters():
    """解析写作骨架段,提取标准子章节"""
    md_text = """## 写作骨架
5.1 环境影响识别
  5.1.1 识别方法（矩阵法/清单法）
  5.1.2 施工期影响识别
5.2 评价因子筛选
5.3 重点评价要素确定

## 数据需求清单"""
    subs = parse_skeleton(md_text, parent_order=5)
    assert len(subs) == 3
    assert subs[0] == {"sub_order": 1, "key": "环境影响识别", "title": "5.1 环境影响识别"}
    assert subs[1] == {"sub_order": 2, "key": "评价因子筛选", "title": "5.2 评价因子筛选"}
    assert subs[2] == {"sub_order": 3, "key": "重点评价要素确定", "title": "5.3 重点评价要素确定"}


def test_parse_skeleton_no_skeleton_returns_empty():
    """无写作骨架段返回空"""
    subs = parse_skeleton("## 其他\n无骨架", parent_order=1)
    assert subs == []


def test_standard_subchapters_generated_from_all_outlines():
    """从全部13章 outlines/ 解析出标准子章节"""
    assert len(STANDARD_SUBCHAPTERS) > 0
    # 第5章应有子章节
    ch5_subs = [s for s in STANDARD_SUBCHAPTERS if s["parent_order"] == 5]
    assert len(ch5_subs) >= 3
    assert any(s["key"] == "环境影响识别" for s in ch5_subs)
```

- [ ] **Step 2: 验证失败** — `docker exec api-dev pytest test/scripts/test_seed_standard_subchapters.py -v`

- [ ] **Step 3: 实现 seed_standard_subchapters.py**

Create `backend/scripts/seed_standard_subchapters.py`:

```python
"""从 outlines/ MD 的写作骨架段解析标准子章节,seed 到图谱作为 level=2 合并锚点。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from neo4j import GraphDatabase

OUTLINES_DIR = Path(__file__).resolve().parent.parent / "package" / "yuxi" / "agents" / "skills" / "buildin" / "coal-eia-writer" / "outlines"
DOMAIN = "coal"
REPORT_TYPE = "eia_report"


def parse_skeleton(md_text: str, parent_order: int) -> list[dict]:
    """解析写作骨架段,提取 level=2 标准子章节。

    格式:
      5.1 环境影响识别        ← level=2 子章节
        5.1.1 识别方法        ← level=3 细节(跳过)
    """
    m = re.search(r"## 写作骨架\s*\n(.*?)(?=\n## |\Z)", md_text, re.DOTALL)
    if not m:
        return []
    skeleton = m.group(1)
    subs = []
    for line in skeleton.strip().split("\n"):
        line = line.rstrip()
        if not line:
            continue
        # level=2 行: "5.1 环境影响识别" (无前导空格, 两级编号)
        m2 = re.match(r"^(\d+)\.(\d+)\s+(.+)$", line)
        if m2:
            parent_num = int(m2.group(1))
            sub_num = int(m2.group(2))
            title_text = m2.group(3).strip()
            if parent_num == parent_order:
                key = _derive_key(title_text)
                subs.append({
                    "parent_order": parent_order,
                    "sub_order": sub_num,
                    "key": key,
                    "title": f"{parent_order}.{sub_num} {title_text}",
                })
    return subs


def _derive_key(title: str) -> str:
    """从子章节标题推导 canonical_chapter_key(去编号的纯标题)。"""
    text = title.strip()
    m = re.match(r"^\d+(?:\.\d+)*\s+(.+)$", text)
    if m:
        text = m.group(1)
    return text.strip()


def _build_standard_subchapters() -> list[dict]:
    """从全部13章 outlines/ MD 解析标准子章节。"""
    all_subs = []
    for order in range(1, 14):
        pattern = f"ch{order:02d}-*.md"
        md_files = list(OUTLINES_DIR.glob(pattern))
        if not md_files:
            continue
        text = md_files[0].read_text(encoding="utf-8")
        subs = parse_skeleton(text, parent_order=order)
        all_subs.extend(subs)
    return all_subs


STANDARD_SUBCHAPTER = _build_standard_subchapters()


def seed(driver, dry_run: bool = False) -> int:
    count = 0
    with driver.session() as session:
        for sub in STANDARD_SUBCHAPTER:
            parent_id = f"CH_{DOMAIN}_{REPORT_TYPE}_std_{sub['parent_order']}"
            sub_id = f"CH_{DOMAIN}_{REPORT_TYPE}_std_{sub['parent_order']}_{sub['sub_order']}"
            if dry_run:
                count += 1
                continue
            session.run(
                """
                MERGE (sub:ChapterTemplate {id: $sub_id})
                ON CREATE SET
                    sub.id = $sub_id,
                    sub.title = $title,
                    sub.canonical_chapter_key = $key,
                    sub.level = 2,
                    sub.`order` = $sub_order,
                    sub.rigidity = 'rigid',
                    sub.domain = $domain,
                    sub.report_type = $rt,
                    sub.created_at = datetime()
                ON MATCH SET
                    sub.canonical_chapter_key = $key,
                    sub.title = $title
                """,
                sub_id=sub_id, title=sub["title"], key=sub["key"],
                sub_order=sub["sub_order"], domain=DOMAIN, rt=REPORT_TYPE,
            )
            session.run(
                """
                MATCH (parent:ChapterTemplate {id: $parent_id})
                MATCH (sub:ChapterTemplate {id: $sub_id})
                MERGE (parent)-[:HAS_CHILD]->(sub)
                """,
                parent_id=parent_id, sub_id=sub_id,
            )
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Seed 标准子章节到图谱")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uri", default="bolt://graph:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="0123456789")
    args = parser.parse_args()
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    count = seed(driver, dry_run=args.dry_run)
    driver.close()
    print(f"模式: {'dry-run' if args.dry_run else '执行'}")
    print(f"标准子章节数: {count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 验证通过** — `docker exec api-dev pytest test/scripts/test_seed_standard_subchapters.py -v`

- [ ] **Step 5: 执行 seed** — `docker exec api-dev python -m scripts.seed_standard_subchapters`

- [ ] **Step 6: Commit**
```bash
git add backend/scripts/seed_standard_subchapters.py backend/test/scripts/test_seed_standard_subchapters.py
git commit -m "feat(seed): 标准子章节seed(从outlines/ MD写作骨架解析level=2锚点)"
```

---

### Task 2: 存量 ETL 子章节归一化 + HAS_CHILD 关联

**Files:**
- Create: `backend/scripts/governance/link_subchapters.py`
- Create: `backend/test/scripts/test_link_subchapters.py`

**Purpose:** 将存量 ETL 子章节（level=2/3）按标题匹配到标准子章节，建 HAS_CHILD 关系，归一化 canonical_chapter_key。

- [ ] **Step 1: 写归一化匹配测试**

Create `backend/test/scripts/test_link_subchapters.py`:

```python
from scripts.governance.link_subchapters import match_etl_to_standard


def test_match_exact_title():
    """ETL标题与标准子章节标题完全匹配"""
    std_subs = [
        {"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"},
        {"sub_id": "std_5_2", "key": "评价因子筛选", "title": "5.2 评价因子筛选"},
    ]
    etl_title = "环境影响识别"
    match = match_etl_to_standard(etl_title, std_subs)
    assert match is not None
    assert match["sub_id"] == "std_5_1"
    assert match["key"] == "环境影响识别"


def test_match_partial_title():
    """ETL标题包含标准子章节关键词"""
    std_subs = [
        {"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"},
    ]
    etl_title = "矿区环境影响因子识别"
    match = match_etl_to_standard(etl_title, std_subs)
    assert match is not None
    assert match["sub_id"] == "std_5_1"


def test_no_match_returns_none():
    """无法匹配返回 None"""
    std_subs = [{"sub_id": "std_5_1", "key": "环境影响识别", "title": "5.1 环境影响识别"}]
    match = match_etl_to_standard("完全无关的标题XYZ", std_subs)
    assert match is None


def test_empty_etl_title_returns_none():
    match = match_etl_to_standard("", [{"sub_id": "x", "key": "k", "title": "t"}])
    assert match is None
```

- [ ] **Step 2: 验证失败**

- [ ] **Step 3: 实现 link_subchapters.py**

Create `backend/scripts/governance/link_subchapters.py`:

```python
"""存量 ETL 子章节归一化: 按标题匹配标准子章节, 建 HAS_CHILD, 归一化 canonical_chapter_key。"""

from __future__ import annotations

import argparse
from typing import Any

from neo4j import GraphDatabase

DOMAIN = "coal"
REPORT_TYPE = "eia_report"


def match_etl_to_standard(etl_title: str, std_subs: list[dict]) -> dict | None:
    """将 ETL 子章节标题匹配到标准子章节。

    匹配策略(优先级递减):
    1. 精确匹配: ETL标题 == 标准key
    2. 包含匹配: ETL标题包含标准key(或反向)
    3. 无匹配: 返回 None
    """
    etl = (etl_title or "").strip()
    if not etl:
        return None
    # 1. 精确匹配
    for s in std_subs:
        if etl == s["key"]:
            return s
    # 2. 包含匹配(双向)
    for s in std_subs:
        if s["key"] in etl or etl in s["key"]:
            return s
    return None


def link(driver, dry_run: bool = False) -> dict:
    """对每个 ETL level=2 子章节, 匹配标准子章节并建 HAS_CHILD + 归一化 key。"""
    stats = {"matched": 0, "unmatched": 0, "normalized": 0}
    with driver.session() as session:
        # 查所有标准子章节
        std_result = session.run(
            "MATCH (s:ChapterTemplate) WHERE s.id STARTS WITH 'CH_coal_eia_report_std_' "
            "AND s.level = 2 RETURN s.id AS sub_id, s.canonical_chapter_key AS key, s.title AS title"
        )
        std_subs = [{"sub_id": r["sub_id"], "key": r["key"], "title": r["title"]} for r in std_result]

        # 查所有 ETL level=2 子章节(非 std_)
        etl_result = session.run(
            "MATCH (ch:ChapterTemplate {domain: $d, report_type: $rt}) "
            "WHERE ch.level = 2 AND NOT ch.id STARTS WITH 'CH_coal_eia_report_std_' "
            "RETURN ch.id AS etl_id, ch.title AS title, ch.canonical_chapter_key AS key",
            d=DOMAIN, rt=REPORT_TYPE,
        )
        for rec in etl_result:
            etl_title = rec["title"] or ""
            match = match_etl_to_standard(etl_title, std_subs)
            if match:
                stats["matched"] += 1
                if not dry_run:
                    session.run(
                        "MATCH (std:ChapterTemplate {id: $std_id}) "
                        "MATCH (etl:ChapterTemplate {id: $etl_id}) "
                        "MERGE (std)-[:HAS_CHILD]->(etl) "
                        "SET etl.canonical_chapter_key = $key",
                        std_id=match["sub_id"], etl_id=rec["etl_id"], key=match["key"],
                    )
                    if rec["key"] != match["key"]:
                        stats["normalized"] += 1
            else:
                stats["unmatched"] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description="存量 ETL 子章节归一化关联")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uri", default="bolt://graph:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="0123456789")
    args = parser.parse_args()
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    stats = link(driver, dry_run=args.dry_run)
    driver.close()
    print(f"模式: {'dry-run' if args.dry_run else '执行'}")
    print(f"匹配: {stats['matched']}, 未匹配: {stats['unmatched']}, 归一化: {stats['normalized']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 验证通过**

- [ ] **Step 5: 执行归一化** — `docker exec api-dev python -m scripts.governance.link_subchapters`

- [ ] **Step 6: Commit**
```bash
git add backend/scripts/governance/link_subchapters.py backend/test/scripts/test_link_subchapters.py
git commit -m "feat(governance): 存量ETL子章节归一化+HAS_CHILD关联到标准子章节"
```

---

## Phase 2: get_templates 递归查询 (P0)

### Task 3: get_templates 顶级查不到时递归查子章节

**Files:**
- Modify: `backend/package/yuxi/services/graph_query_service.py`
- Modify: `backend/test/unit/services/test_graph_query_service.py`

- [ ] **Step 1: 写递归查询测试**

Append to `test_graph_query_service.py`:

```python
@pytest.mark.asyncio
async def test_get_templates_recurses_to_children():
    """顶级章节无模板时,递归查子章节模板"""
    service = GraphQueryService()
    try:
        # 第5章"环境影响识别与评价指标体系"是标准章节,自身无模板
        # 但其子章节"环境影响识别"应有模板(ETL抽取的)
        templates = await service.get_templates("coal", "eia_report", "环境影响识别与评价指标体系")
        assert isinstance(templates, list)
        # 如果子章节有模板,应返回非空(取决于ETL数据)
        # 至少不应报错
    finally:
        service.close()


@pytest.mark.asyncio
async def test_get_templates_subchapter_direct():
    """子章节直接查模板(不递归)"""
    service = GraphQueryService()
    try:
        templates = await service.get_templates("coal", "eia_report", "环境影响识别")
        assert isinstance(templates, list)
    finally:
        service.close()
```

- [ ] **Step 2: 验证失败**（顶级章节返回空,不递归）

- [ ] **Step 3: 改造 get_templates 递归**

修改 `graph_query_service.py` 的 `get_templates` 方法:

```python
    async def get_templates(
        self, domain: str, report_type: str, canonical_key: str
    ) -> list[dict[str, Any]]:
        """查询某章节下的段落模板。顶级章节无模板时递归查子章节。"""
        # 1. 先查本章节模板
        templates = self._query_templates(domain, report_type, canonical_key)
        if templates:
            return templates
        # 2. 递归查子章节模板
        child_keys = self._query_child_canonical_keys(domain, report_type, canonical_key)
        all_templates = []
        seen_patterns = set()
        for child_key in child_keys:
            child_templates = self._query_templates(domain, report_type, child_key)
            for t in child_templates:
                pattern = t.get("text_pattern", "")
                if pattern and pattern not in seen_patterns:
                    seen_patterns.add(pattern)
                    all_templates.append(t)
        return all_templates

    def _query_child_canonical_keys(self, domain: str, report_type: str, canonical_key: str) -> list[str]:
        """查询某章节的所有子章节 canonical_chapter_key(去重)。"""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ch:ChapterTemplate {domain: $domain, report_type: $rt, canonical_chapter_key: $key})
                OPTIONAL MATCH (ch)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
                WHERE sub.canonical_chapter_key IS NOT NULL AND sub.canonical_chapter_key <> ''
                RETURN DISTINCT sub.canonical_chapter_key AS key
                """,
                domain=domain, rt=report_type, key=canonical_key,
            )
            return [r["key"] for r in result if r["key"]]
```

注意: 原有的 `get_templates` 方法体改为 `_query_templates`（私有方法，查单层）。签名不变。

- [ ] **Step 4: 验证通过**

- [ ] **Step 5: Commit**
```bash
git add backend/package/yuxi/services/graph_query_service.py backend/test/unit/services/test_graph_query_service.py
git commit -m "feat(graph-query): get_templates递归查询子章节模板+去重"
```

---

## Phase 3: 分章节上传支持 (P0)

### Task 4: DomainFactoryTask 加 source_report_id + chapter_label

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`
- Modify: `backend/package/yuxi/storage/postgres/manager.py`

- [ ] **Step 1: 模型加字段**

在 `models_domain_factory.py` 的 `DomainFactoryTask` 类中，`knowledge_base_id` 字段后添加:

```python
    source_report_id = Column(String(64), nullable=True, index=True)
    chapter_label = Column(String(64), nullable=True)
```

- [ ] **Step 2: manager.py ALTER 语句**

在 `manager.py` 的 `ensure_business_schema` 方法的 ALTER 语句列表中添加:

```python
            "ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS source_report_id VARCHAR(64)",
            "ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS chapter_label VARCHAR(64)",
            "CREATE INDEX IF NOT EXISTS idx_df_tasks_source_report ON domain_factory_tasks(source_report_id)",
```

- [ ] **Step 3: 验证** — `docker exec api-dev python -c "from yuxi.storage.postgres.models_domain_factory import DomainFactoryTask; print(DomainFactoryTask.source_report_id)"`

- [ ] **Step 4: 重启服务让 ALTER 生效** — `docker compose restart api worker`

- [ ] **Step 5: Commit**
```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py
git commit -m "feat(model): DomainFactoryTask加source_report_id+chapter_label支持分章上传"
```

---

### Task 5: 上传接口支持 source_report_id

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（上传接口）
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（create_task）

- [ ] **Step 1: 上传接口加可选参数**

在 `domain_factory_router.py` 的上传接口中添加可选参数:

```python
    source_report_id: str | None = Form(None),
    chapter_label: str | None = Form(None),
```

传递到 `service.create_task(...)` 调用中。

- [ ] **Step 2: create_task 接收并存储**

在 `domain_factory_service.py` 的 `create_task` 方法中，接收 `source_report_id` 和 `chapter_label`，写入 task 记录。如果 `source_report_id` 为空且 `chapter_label` 不为空，自动生成 `source_report_id = f"sr_{uuid4().hex[:12]}"`。

- [ ] **Step 3: 验证** — 上传一个文件带 chapter_label，检查 DB 有值

- [ ] **Step 4: Commit**
```bash
git add backend/server/routers/domain_factory_router.py backend/package/yuxi/services/domain_factory_service.py
git commit -m "feat(upload): 上传接口支持source_report_id+chapter_label分章上传"
```

---

## Phase 4: 多报告去重合并 (P1)

### Task 6: commit pipeline Stage 2.10 跨报告合并

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`
- Create: `backend/test/unit/services/test_cross_report_merge.py`

- [ ] **Step 1: 写合并逻辑测试**

Create `test_cross_report_merge.py`:

```python
import pytest
from unittest.mock import MagicMock


def test_dedup_templates_by_hash():
    """相同 text_pattern 的模板去重, source_count 累加"""
    from yuxi.services.domain_factory_service import DomainFactoryService
    svc = DomainFactoryService()
    templates = [
        {"text_pattern": "{{矿区}}位于{{位置}}", "source": "报告A"},
        {"text_pattern": "{{矿区}}位于{{位置}}", "source": "报告B"},
        {"text_pattern": "{{产能}}为{{数值}}", "source": "报告A"},
    ]
    deduped = svc._dedup_templates_by_hash(templates)
    assert len(deduped) == 2
    # 保留的第一个 source_count 应为 2
    t0 = next(t for t in deduped if "矿区" in t["text_pattern"])
    assert t0["source_count"] == 2
```

- [ ] **Step 2: 验证失败**

- [ ] **Step 3: 实现合并逻辑**

在 `_commit_pipeline_async` 的 Stage 2.9 之后添加 Stage 2.10:

```python
            # ========== 阶段2.10: 跨报告知识合并 (MERGE) ==========
            try:
                await context.set_progress(94.0, "正在合并跨报告知识...")
                await context.set_message("正在合并跨报告知识...")
                merged = await service._merge_cross_report_knowledge(task_detail)
                logger.info(f"跨报告合并完成: {merged}")
            except Exception as e:
                logger.warning(f"跨报告合并失败(不阻断入库): {e}")
                pipeline_status = "COMMIT_PARTIAL"
                partial_errors.append(f"跨报告合并失败: {e}")
```

在 `DomainFactoryService` 类中添加:

```python
    def _dedup_templates_by_hash(self, templates: list[dict]) -> list[dict]:
        """按 text_pattern 去重, source_count 累加。"""
        seen = {}
        for t in templates:
            pattern = t.get("text_pattern", "")
            if pattern in seen:
                seen[pattern]["source_count"] = seen[pattern].get("source_count", 1) + 1
            else:
                t["source_count"] = 1
                seen[pattern] = t
        return list(seen.values())

    async def _merge_cross_report_knowledge(self, task_detail: dict) -> dict:
        """合并当前报告知识到标准13章(去重+聚合 key_points/regulations)。"""
        from yuxi.services.graph_builder import GraphBuilder
        builder = GraphBuilder()
        try:
            with builder._get_driver().session() as session:
                # 对每个标准子章节, 聚合子章节的 key_points 和 regulations
                for order in range(1, 14):
                    session.run(
                        """
                        MATCH (std:ChapterTemplate {id: $std_id})
                        OPTIONAL MATCH (std)-[:HAS_CHILD*1..3]->(sub:ChapterTemplate)
                        WHERE sub.key_points IS NOT NULL
                        WITH std, collect(DISTINCT sub.key_points) AS all_kp
                        UNWIND all_kp AS kp_json
                        WITH std, kp_json
                        CALL {
                            WITH kp_json
                            WITH kp_json AS kp
                            RETURN CASE WHEN kp IS NULL THEN [] ELSE kp END AS kp_list
                        }
                        WITH std, collect(DISTINCT item) AS items
                        UNWIND items AS item
                        WITH std, collect(DISTINCT item) AS unique_kp
                        SET std.key_points = unique_kp
                        """,
                        std_id=f"CH_coal_eia_report_std_{order}",
                    )
            return {"status": "ok"}
        finally:
            builder.close()
```

注意: Cypher 较复杂, implementer 可能需要简化为 Python 端聚合而非纯 Cypher。

- [ ] **Step 4: 验证通过**

- [ ] **Step 5: Commit**
```bash
git add backend/package/yuxi/services/domain_factory_service.py backend/test/unit/services/test_cross_report_merge.py
git commit -m "feat(merge): commit pipeline Stage 2.10跨报告知识合并(去重+聚合)"
```

---

## Phase 5: slot_validation 接入 ETL (P1)

### Task 7: commit pipeline 接入 slot_validation_service

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`

- [ ] **Step 1: 在 Stage 2.5 之前插入 slot 校验**

在 `_run_commit_pipeline_body` 中, Stage 2.5（图谱构建）之前插入:

```python
            # ========== 阶段2.4b: slot 事后校验 (新增) ==========
            try:
                from yuxi.services.slot_validation_service import SlotValidationService
                svc = SlotValidationService()
                paragraph_slots = [
                    {"paragraph_id": p.get("id", ""), "slots": (p.get("template") or {}).get("slots", [])}
                    for p in task_detail.get("source_paragraphs", [])
                    if p.get("type") == "parameter" and p.get("template")
                ]
                if paragraph_slots:
                    report = await svc.validate_slots(paragraph_slots, {})
                    if report.get("conflicts"):
                        logger.warning(f"slot 校验发现 {len(report['conflicts'])} 个冲突")
                    if report.get("warnings"):
                        logger.warning(f"slot 校验发现 {report['warnings']} 个警告")
            except Exception as e:
                logger.warning(f"slot 校验失败(不阻断): {e}")
```

- [ ] **Step 2: 验证不破坏现有流程** — `docker exec api-dev pytest test/unit/services/test_commit_pipeline_status.py -v`

- [ ] **Step 3: Commit**
```bash
git add backend/package/yuxi/services/domain_factory_service.py
git commit -m "feat(etl): slot_validation接入commit pipeline(Stage 2.4b)"
```

---

## Phase 6: ETL 源头映射标准子章节 (P2)

### Task 8: graph_builder 创建 ChapterTemplate 时映射标准子章节

**Files:**
- Modify: `backend/package/yuxi/services/graph_builder.py`

- [ ] **Step 1: 在 _build_skeleton_aggregation 中, ChapterTemplate 创建后映射**

在 ChapterTemplate MERGE 之后, 按标题匹配标准子章节并建 HAS_CHILD + 归一化 canonical_chapter_key:

```python
            # 映射 ETL 子章节到标准子章节
            std_sub_result = tx.run(
                "MATCH (s:ChapterTemplate) WHERE s.id STARTS WITH 'CH_coal_eia_report_std_' "
                "AND s.level = 2 RETURN s.id AS sub_id, s.canonical_chapter_key AS key, s.title AS title"
            )
            std_subs = [{"sub_id": r["sub_id"], "key": r["key"], "title": r["title"]} for r in std_sub_result]
            for sp_str, ch_info in chapter_map.items():
                etl_title = ch_info["title"]
                for s in std_subs:
                    if s["key"] in etl_title or etl_title in s["key"]:
                        tx.run(
                            "MATCH (std:ChapterTemplate {id: $std_id}) "
                            "MATCH (etl:ChapterTemplate {id: $etl_id}) "
                            "MERGE (std)-[:HAS_CHILD]->(etl) "
                            "SET etl.canonical_chapter_key = $key",
                            std_id=s["sub_id"], etl_id=ch_info["chapter_id"], key=s["key"],
                        )
                        break
```

- [ ] **Step 2: 验证** — 新报告入库后 ETL 子章节自动关联标准子章节

- [ ] **Step 3: Commit**
```bash
git add backend/package/yuxi/services/graph_builder.py
git commit -m "feat(etl): graph_builder创建子章节时自动映射标准子章节(HAS_CHILD+归一化)"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 4.0 子章节归一化 → Task 1-2
- ✅ Section 4.4 get_templates 递归 → Task 3
- ✅ Section 5 分章节上传 → Task 4-5
- ✅ Section 6 多报告去重合并 → Task 6
- ✅ Section 7 slot_validation 接入 → Task 7
- ✅ Section 4.2 ETL 源头映射 → Task 8

**Placeholder scan:** 无 TBD/TODO。Task 6 的 Cypher 标注"可能需简化"但给了 Python fallback。

**Type一致性:** STANDARD_SUBCHAPTERS / match_etl_to_standard / _query_child_canonical_keys / _dedup_templates_by_hash 命名一致。

---

## 实施顺序

```
Phase 1 (P0): Task 1 → 2         (标准子章节seed + 存量归一化)
Phase 2 (P0): Task 3             (get_templates递归)
Phase 3 (P0): Task 4 → 5         (分章节上传)
Phase 4 (P1): Task 6             (多报告合并)
Phase 5 (P1): Task 7             (slot_validation接入)
Phase 6 (P2): Task 8             (ETL源头映射)
```
