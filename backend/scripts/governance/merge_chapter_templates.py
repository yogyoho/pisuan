"""存量 ChapterTemplate 治理脚本（bug-4167 spec §4.4）：归一 canonical、合并重复、纠挂、编号结构化、删测试子树、meta 回写。

幂等可重跑：每步先算动作清单再执行，重跑零动作。默认 dry-run 只打印 JSON 报告，--apply 才落写。
import 兼容 yuxi/pisuan 双包名（localized 容器内包名为 pisuan，脚本自动降级）。

治理步骤（Neo4j 阶段按序）:
  1. 全量归一 canonical（normalize_chapter_key，「总  则」→「总则」）
  2. 纠挂：错挂的 level-2 ETL 节点挂回正确父——优先同名 std level-2 子章节之父，
     缺 std 子章节时回退「同名节点最大 std level-1 簇」；先纠挂后合并（簇未收敛，多数信号完整）
  3. 按 (归一canonical, level, 父节点) 分组合并：幸存者优先 std_ 前缀 id，重定向
     HAS_CHILD（入+出）/ HAS_CHAPTER / REQUIRES_PARAGRAPH_ROLE，meta COALESCE 取非空、
     frequency 取最大，DELETE 重复节点（迭代至不动点）
  4. 编号结构化：title 剥前导编号；chapter_no = 标题自带编号或 std 编号（std_1→"1"、
     std_2_3→"2.3"）；仍缺时按 父号.order（源文档位次）推导，无 order/父无号不猜（置 null）
  5. 删「测试」前缀节点及其全部后代（DETACH DELETE，dry-run 列出将删清单）
  6. 从 PG domain_factory_outlines（purpose/overview 非空的行）按归一 canonical 回写图谱 meta
PG 阶段: 带编号 canonical 的行与归一后相同的行归并（字段逐个取非空、source_task_ids 并集、
source_count 取最大），canonical 重命名为归一值，删被合并行。

用法（容器内 backend 工作目录）:
  python -m scripts.governance.merge_chapter_templates                     # dry-run 预览（默认）
  python -m scripts.governance.merge_chapter_templates --apply             # 执行落写
  python -m scripts.governance.merge_chapter_templates --scope graph       # 只治理图谱
  python -m scripts.governance.merge_chapter_templates --apply --snapshot /tmp/snapshot.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    from yuxi.utils import normalize_chapter_key
except ImportError:  # localized 容器内包名为 pisuan
    from pisuan.utils import normalize_chapter_key

# 合并重复节点时 COALESCE 取非空的 meta 字段（图谱节点侧）
GRAPH_META_FIELDS = (
    "purpose", "overview", "key_points", "content_requirements", "regulations",
    "entity_bindings", "writing_example", "writing_hints", "extraction_regex",
)
# ⑥ meta 回填：PG 行 → 图谱节点（extraction_regex 无 PG 列，不在其中）
PG_META_FIELDS = (
    "purpose", "overview", "key_points", "content_requirements", "regulations",
    "entity_bindings", "writing_example", "writing_hints",
)
# PG 归并取非空的字段
PG_MERGE_STR_FIELDS = ("chapter_id", "chapter_title", "purpose", "overview", "writing_example", "writing_hints")
PG_MERGE_LIST_FIELDS = (
    "key_points", "content_requirements", "regulations", "entity_bindings",
    "expected_tables", "expected_charts", "expected_formulas", "expected_figures",
    "content_contract", "dependencies",
)
TEST_PREFIX = "测试"

PG_OUTLINE_QUERY = """
    SELECT id, canonical_chapter_key, chapter_id, chapter_title, purpose, overview, key_points,
           content_requirements, regulations, entity_bindings, writing_example, writing_hints,
           expected_tables, expected_charts, expected_formulas, expected_figures,
           content_contract, dependencies, source_task_ids, source_count
      FROM domain_factory_outlines
     WHERE domain_code = %s AND report_type_code = %s
"""


def split_leading_number(title: str) -> tuple[str, str]:
    """拆分标题的前导多级编号 → (编号, 干净标题)。无编号返回 ("", 原标题)，纯编号返回 (编号, "")。"""
    text = (title or "").strip()
    if not text:
        return "", ""
    if re.fullmatch(r"\d+(?:\.\d+)*", text):
        return text, ""
    m = re.match(r"^(\d+(?:\.\d+)*)\s*(\S.*)$", text)
    if m:
        return m.group(1), m.group(2).strip()
    return "", text


def std_chapter_no(node_id: str, std_prefix: str) -> str | None:
    """std 节点 id 推导编号：..._std_1 → "1"、..._std_2_3 → "2.3"；非 std id 返回 None。"""
    if not node_id or not node_id.startswith(std_prefix):
        return None
    parts = node_id[len(std_prefix):].split("_")
    if parts and all(p.isdigit() for p in parts):
        return ".".join(parts)
    return None


def _nonempty(value) -> bool:
    """字段取非空判定：非 None、字符串非空白、列表/字典非空。"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _coalesce_case(field: str) -> str:
    """图谱 meta 字段的 COALESCE 取非空 CASE 片段（兼容字符串与列表存储）。"""
    return (
        f"keep.{field} = CASE WHEN keep.{field} IS NULL OR keep.{field} = '' OR size(keep.{field}) = 0 "
        f"THEN dup.{field} ELSE keep.{field} END"
    )


_META_SET_CASES = ",\n               ".join(_coalesce_case(f) for f in GRAPH_META_FIELDS)


class GraphState:
    """图谱 ChapterTemplate 子图的内存态：节点属性 + HAS_CHILD 父子索引，供纯函数规划与模拟落写。"""

    def __init__(self, nodes: dict[str, dict], parents_of: dict[str, list[str]], domain: str, report_type: str):
        self.nodes = nodes
        self.parents_of = parents_of
        self.children_of: dict[str, list[str]] = {}
        for cid, parents in parents_of.items():
            for p in parents:
                self.children_of.setdefault(p, []).append(cid)
        self.std_prefix = f"CH_{domain}_{report_type}_std_"

    def group_key(self, nid: str) -> tuple[str, int, str]:
        """聚合身份键 (归一canonical, level, 父节点 id)；level=1 无 ChapterTemplate 父 → 空串。"""
        n = self.nodes[nid]
        parents = sorted(p for p in self.parents_of.get(nid, []) if p in self.nodes)
        return (n["canonical_norm"], n["level"], parents[0] if parents else "")


def state_from_query_rows(rows: list[dict], domain: str, report_type: str) -> GraphState:
    """把 fetch 查询行装配为 GraphState（归一 canonical、父索引）。运行与测试共用同一装配路径。"""
    nodes: dict[str, dict] = {}
    parents_of: dict[str, list[str]] = {}
    for r in rows:
        nid = r["id"]
        raw = r["canonical"] or ""
        nodes[nid] = {
            "id": nid,
            "title": r["title"],
            "canonical": raw,
            "canonical_norm": normalize_chapter_key(raw) or normalize_chapter_key(r["title"] or ""),
            "level": r["level"] if r["level"] is not None else 0,
            "chapter_no": r["chapter_no"],
            "order": r.get("order"),
            "frequency": r["frequency"],
            **{f: r[f] for f in GRAPH_META_FIELDS},
        }
        parents_of[nid] = sorted({p for p in (r["parent_ids"] or []) if p})
    return GraphState(nodes, parents_of, domain, report_type)


# ---------------- 纯函数规划（每步先算动作清单） ----------------


def plan_merges(state: GraphState) -> list[dict]:
    """② 按 (归一canonical, level, 父节点) 分组，>1 的组给出幸存者（std_ 前缀优先）与删除清单。"""
    groups: dict[tuple, list[str]] = {}
    for nid in state.nodes:
        key = state.group_key(nid)
        if not key[0]:
            continue  # 空 canonical（纯编号标题）不参与合并
        groups.setdefault(key, []).append(nid)
    plans = []
    for key in sorted(groups):
        ids = groups[key]
        if len(ids) < 2:
            continue
        ordered = sorted(ids, key=lambda i: (0 if i.startswith(state.std_prefix) else 1, i))
        plans.append({
            "canonical": key[0], "level": key[1], "parent": key[2],
            "survivor": ordered[0], "deletes": ordered[1:],
        })
    return plans


def _majority_std_parent(state: GraphState, canonical: str) -> str | None:
    """回退纠挂目标：同名 (归一canonical, level=2) 节点按 std level-1 父分簇，取最大簇。

    线上图谱仅种子了 13 个 std level-1 根（无 level-2 种子），std_sub_index 恒空，
    无法按「同名 std 子章节之父」纠挂；改以多数簇定位——同名节点最集中的 std 根即
    正确归属（并列取 id 最小，保证确定性）。无任何 std 簇时返回 None（无信号不猜测）。
    """
    clusters: dict[str, int] = {}
    for nid, n in state.nodes.items():
        if n["level"] != 2 or n["canonical_norm"] != canonical:
            continue
        for p in state.parents_of.get(nid, []):
            pn = state.nodes.get(p)
            if pn is not None and pn.get("level") == 1 and p.startswith(state.std_prefix):
                clusters[p] = clusters.get(p, 0) + 1
    if not clusters:
        return None
    return max(sorted(clusters), key=lambda k: clusters[k])


def plan_reparents(state: GraphState, std_sub_index: dict[str, tuple[str, str]]) -> list[dict]:
    """③ level-2 ETL 节点纠挂：优先挂同名 std level-2 子章节之父；图谱缺 std 子章节时
    回退为「同名节点最大 std level-1 簇」之父（_majority_std_parent）。"""
    plans = []
    for nid in sorted(state.nodes):
        n = state.nodes[nid]
        if nid.startswith(state.std_prefix) or n["level"] != 2:
            continue
        sub_id = None
        hit = std_sub_index.get(n["canonical_norm"])
        if hit:
            sub_id, parent_id = hit
        else:
            parent_id = _majority_std_parent(state, n["canonical_norm"])
            if parent_id is None:
                continue
        current = sorted(p for p in state.parents_of.get(nid, []) if p in state.nodes)
        if current == [parent_id]:
            continue  # 已挂正，幂等零动作
        plans.append({
            "id": nid, "canonical": n["canonical_norm"],
            "from": current[0] if current else None, "to": parent_id, "std_sub": sub_id,
        })
    return plans


def _effective_numbers(state: GraphState) -> dict[str, str | None]:
    """步骤④ 辅助：自根逐级推导各节点在本轮改号后的编号。

    取值优先级：std → std 序号；标题带号 → 剥出号；既有 chapter_no 非空 → 保留；
    否则 父号.order（order 为建库时记录的源文档位次，与既有 6.4/6.12 实测一致）。
    父无号或节点无 order 不猜（置 None）。既有编号不重算（fill-empty-only），
    但作为父号传递给后代。跨文档累积的兄弟集合次序 ≠ 任一源文档目录，故不用兄弟序。
    """
    by_level: dict[int, list[str]] = {}
    for nid, n in state.nodes.items():
        by_level.setdefault(n["level"], []).append(nid)

    result: dict[str, str | None] = {}
    for lvl in sorted(by_level):  # 父先于子
        for nid in by_level[lvl]:
            n = state.nodes[nid]
            no, _ = split_leading_number(n.get("title") or "")
            if nid.startswith(state.std_prefix):
                result[nid] = std_chapter_no(nid, state.std_prefix)
            elif no:
                result[nid] = no
            elif n.get("chapter_no"):
                result[nid] = n.get("chapter_no")
            else:
                parents = sorted(p for p in state.parents_of.get(nid, []) if p in state.nodes)
                pno = result.get(parents[0]) if parents else None
                order = n.get("order")
                result[nid] = f"{pno}.{int(order)}" if pno and order else None
    return result


def plan_retitles(state: GraphState) -> list[dict]:
    """④ 编号结构化：title 剥前导编号；chapter_no = 标题自带编号或 std 编号，
    仍缺时按 父号.order（源位次）推导（_effective_numbers），使目录树全层级带编号。"""
    effective = _effective_numbers(state)
    plans = []
    for nid in sorted(state.nodes):
        n = state.nodes[nid]
        title = n.get("title") or ""
        if title.startswith(TEST_PREFIX) or (n.get("canonical_norm") or "").startswith(TEST_PREFIX):
            continue  # 测试节点将在 ⑤ 整树删除，不参与改号
        no, clean = split_leading_number(title)
        if nid.startswith(state.std_prefix):
            target_no = std_chapter_no(nid, state.std_prefix)
        elif no:
            target_no = no
        else:
            # 保留新写入路径的推导值（first-won）；旧节点为空 → 结构化兜底
            target_no = n.get("chapter_no") or effective.get(nid)
        changes: dict = {}
        if clean and clean != title:
            changes["title"] = clean
        if target_no != n.get("chapter_no"):
            changes["chapter_no"] = target_no
        if changes:
            plans.append({"id": nid, **changes})
    return plans


def plan_test_deletions(state: GraphState) -> list[dict]:
    """⑤ 「测试」前缀节点及其全部后代子树（嵌套测试根并入祖先子树，不重复删除）。"""
    roots = [
        nid for nid in sorted(state.nodes)
        if not nid.startswith(state.std_prefix)
        and ((state.nodes[nid].get("title") or "").startswith(TEST_PREFIX)
             or (state.nodes[nid].get("canonical_norm") or "").startswith(TEST_PREFIX))
    ]
    plans = []
    claimed: set[str] = set()
    for rid in roots:
        if rid in claimed:
            continue  # 已被更上层测试根的子树覆盖
        subtree: list[str] = []
        seen: set[str] = set()
        stack = [rid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            subtree.append(cur)
            stack.extend(state.children_of.get(cur, []))
        claimed |= seen  # 嵌套测试根的子树是本子树的子集，整树认领防重复删除
        plans.append({
            "root": rid, "root_title": state.nodes[rid].get("title"),
            "count": len(subtree), "ids": sorted(subtree),
        })
    return plans


def plan_meta_backfill(state: GraphState, pg_rows: list[dict]) -> tuple[list[dict], int]:
    """⑥ PG 行（purpose/overview 非空）按归一 canonical 回填图谱 meta；返回 (计划, 歧义跳过数)。"""
    plans: list[dict] = []
    ambiguous = 0
    for row in pg_rows:
        if not (_nonempty(row.get("purpose")) or _nonempty(row.get("overview"))):
            continue
        key = normalize_chapter_key(row.get("canonical_chapter_key") or "")
        if not key:
            continue
        target = row.get("chapter_id") if row.get("chapter_id") in state.nodes else None
        if target is None:
            candidates = sorted(nid for nid, n in state.nodes.items() if n["canonical_norm"] == key)
            if len(candidates) == 1:
                target = candidates[0]
            elif not candidates:
                continue  # 图谱无对应节点（PG 独有章节），跳过
            else:
                ambiguous += 1  # 同 canonical 多节点（跨层同名），不猜测
                continue
        node = state.nodes[target]
        fields = {f: row[f] for f in PG_META_FIELDS if _nonempty(row.get(f)) and not _nonempty(node.get(f))}
        if fields:
            plans.append({"node": target, "canonical": key, "fields": fields})
    return plans, ambiguous


def plan_pg_merges(rows: list[dict]) -> list[dict]:
    """PG 阶段：带编号 canonical 行与归一后相同的行归并；canonical 重命名为归一值。"""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = normalize_chapter_key(row.get("canonical_chapter_key") or "")
        if not key:
            continue
        groups.setdefault(key, []).append(row)
    plans = []
    for key in sorted(groups):
        members = groups[key]
        ordered = sorted(members, key=lambda r: (0 if r["canonical_chapter_key"] == key else 1, r["id"]))
        survivor, dups = ordered[0], ordered[1:]
        set_fields: dict = {}
        if survivor["canonical_chapter_key"] != key:
            set_fields["canonical_chapter_key"] = key
        for f in PG_MERGE_STR_FIELDS:
            if _nonempty(survivor.get(f)):
                continue
            for dup in dups:
                if _nonempty(dup.get(f)):
                    set_fields[f] = dup[f]
                    break
        for f in PG_MERGE_LIST_FIELDS:
            if _nonempty(survivor.get(f)):
                continue
            for dup in dups:
                if _nonempty(dup.get(f)):
                    set_fields[f] = dup[f]
                    break
        task_ids: list = []
        for r in ordered:
            for t in r.get("source_task_ids") or []:
                if t not in task_ids:
                    task_ids.append(t)
        if task_ids != (survivor.get("source_task_ids") or []):
            set_fields["source_task_ids"] = task_ids
        max_count = max((r.get("source_count") or 0) for r in ordered)
        if max_count != (survivor.get("source_count") or 0):
            set_fields["source_count"] = max_count
        if set_fields or dups:
            plans.append({
                "survivor_id": survivor["id"], "canonical": key,
                "set": set_fields, "delete_ids": [d["id"] for d in dups],
            })
    return plans


# ---------------- 内存态落写（与 Cypher 执行语义一致，dry-run 投影 / apply 推进共用） ----------------


def apply_merge(state: GraphState, plan: dict) -> None:
    keep = plan["survivor"]
    for dup in plan["deletes"]:
        for kid in state.children_of.get(dup, []):
            state.parents_of[kid] = sorted({p for p in state.parents_of.get(kid, []) if p != dup} | {keep})
            state.children_of[keep] = sorted(set(state.children_of.get(keep, [])) | {kid})
        for p in state.parents_of.get(dup, []):
            if p == keep:
                continue
            state.children_of[p] = sorted({c for c in state.children_of.get(p, []) if c != dup} | {keep})
            state.parents_of[keep] = sorted(set(state.parents_of.get(keep, [])) | {p})
        state.children_of.pop(dup, None)
        state.parents_of.pop(dup, None)
        state.nodes.pop(dup, None)


def apply_reparent(state: GraphState, plan: dict) -> None:
    nid, to = plan["id"], plan["to"]
    for p in state.parents_of.get(nid, []):
        if p != to:
            state.children_of[p] = sorted(c for c in state.children_of.get(p, []) if c != nid)
    state.parents_of[nid] = [to]
    state.children_of[to] = sorted(set(state.children_of.get(to, [])) | {nid})


def apply_retitle(state: GraphState, plan: dict) -> None:
    node = state.nodes.get(plan["id"])
    if node is None:
        return
    if "title" in plan:
        node["title"] = plan["title"]
    if "chapter_no" in plan:
        node["chapter_no"] = plan["chapter_no"]


def apply_deletions(state: GraphState, ids: list[str]) -> None:
    for nid in ids:
        state.nodes.pop(nid, None)
        for p in state.parents_of.pop(nid, []):
            state.children_of[p] = [c for c in state.children_of.get(p, []) if c != nid]
        for c in state.children_of.pop(nid, []):
            state.parents_of[c] = [p for p in state.parents_of.get(c, []) if p != nid]


def apply_meta_backfill(state: GraphState, plan: dict) -> None:
    node = state.nodes.get(plan["node"])
    if node is None:
        return
    for f, v in plan["fields"].items():
        if not _nonempty(node.get(f)):
            node[f] = v


# ---------------- Cypher 执行 ----------------


def exec_merge(session, keep_id: str, dup_id: str) -> None:
    """meta COALESCE 取非空、frequency 取最大 → 重定向 HAS_CHILD（入+出）/ HAS_CHAPTER /
    REQUIRES_PARAGRAPH_ROLE → DETACH DELETE 重复节点。"""
    session.run(
        f"""
        MATCH (keep:ChapterTemplate {{id: $keep_id}})
        MATCH (dup:ChapterTemplate {{id: $dup_id}})
        SET {_META_SET_CASES},
            keep.frequency = CASE WHEN coalesce(dup.frequency, 0) > coalesce(keep.frequency, 0)
                                  THEN dup.frequency ELSE keep.frequency END
        """,
        keep_id=keep_id, dup_id=dup_id,
    )
    session.run(
        """
        MATCH (p)-[:HAS_CHILD]->(dup:ChapterTemplate {id: $dup_id})
        MATCH (keep:ChapterTemplate {id: $keep_id})
        MERGE (p)-[:HAS_CHILD]->(keep)
        """,
        keep_id=keep_id, dup_id=dup_id,
    )
    session.run(
        """
        MATCH (dup:ChapterTemplate {id: $dup_id})-[:HAS_CHILD]->(c)
        MATCH (keep:ChapterTemplate {id: $keep_id})
        MERGE (keep)-[:HAS_CHILD]->(c)
        """,
        keep_id=keep_id, dup_id=dup_id,
    )
    session.run(
        """
        MATCH (d)-[:HAS_CHAPTER]->(dup:ChapterTemplate {id: $dup_id})
        MATCH (keep:ChapterTemplate {id: $keep_id})
        MERGE (d)-[:HAS_CHAPTER]->(keep)
        """,
        keep_id=keep_id, dup_id=dup_id,
    )
    session.run(
        """
        MATCH (dup:ChapterTemplate {id: $dup_id})-[:REQUIRES_PARAGRAPH_ROLE]->(pr)
        MATCH (keep:ChapterTemplate {id: $keep_id})
        MERGE (keep)-[:REQUIRES_PARAGRAPH_ROLE]->(pr)
        """,
        keep_id=keep_id, dup_id=dup_id,
    )
    session.run("MATCH (dup:ChapterTemplate {id: $dup_id}) DETACH DELETE dup", dup_id=dup_id)


def exec_reparent(session, node_id: str, to_parent_id: str) -> None:
    """挂正确父节点并删除旧父边。"""
    session.run(
        """
        MATCH (node:ChapterTemplate {id: $node_id})
        MATCH (parent:ChapterTemplate {id: $parent_id})
        MERGE (parent)-[:HAS_CHILD]->(node)
        WITH node, parent
        MATCH (old)-[r:HAS_CHILD]->(node) WHERE old <> parent
        DELETE r
        """,
        node_id=node_id, parent_id=to_parent_id,
    )


def exec_retitle(session, plan: dict) -> None:
    sets, params = [], {"id": plan["id"]}
    if "title" in plan:
        sets.append("ch.title = $title")
        params["title"] = plan["title"]
    if "chapter_no" in plan:
        sets.append("ch.chapter_no = $chapter_no")  # None 时即移除属性（置 null）
        params["chapter_no"] = plan["chapter_no"]
    session.run(f"MATCH (ch:ChapterTemplate {{id: $id}}) SET {', '.join(sets)}", **params)


def exec_delete(session, ids: list[str]) -> None:
    session.run("UNWIND $ids AS id MATCH (n:ChapterTemplate {id: id}) DETACH DELETE n", ids=ids)


def exec_meta_backfill(session, plan: dict) -> None:
    """只填空值（COALESCE 语义），不覆盖图谱已有 meta，保证幂等。"""
    sets, params = [], {"id": plan["node"]}
    for f, v in plan["fields"].items():
        params[f] = v
        if isinstance(v, list):
            sets.append(f"ch.{f} = CASE WHEN ch.{f} IS NULL OR size(ch.{f}) = 0 THEN ${f} ELSE ch.{f} END")
        else:
            sets.append(f"ch.{f} = CASE WHEN ch.{f} IS NULL OR ch.{f} = '' THEN ${f} ELSE ch.{f} END")
    session.run(f"MATCH (ch:ChapterTemplate {{id: $id}}) SET {', '.join(sets)}", **params)


# ---------------- 数据读取 ----------------


def fetch_graph_state(session, domain: str, report_type: str) -> GraphState:
    meta_returns = ", ".join(f"ch.{f} AS {f}" for f in GRAPH_META_FIELDS)
    rows = session.run(
        f"""
        MATCH (ch:ChapterTemplate {{domain: $domain, report_type: $rt}})
        OPTIONAL MATCH (p:ChapterTemplate)-[:HAS_CHILD]->(ch)
        RETURN ch.id AS id, ch.title AS title, ch.canonical_chapter_key AS canonical,
               ch.level AS level, ch.chapter_no AS chapter_no, ch.frequency AS frequency,
               ch.order AS order, {meta_returns}, collect(p.id) AS parent_ids
        """,
        domain=domain, rt=report_type,
    )
    return state_from_query_rows([dict(r) for r in rows], domain, report_type)


def fetch_std_sub_index(session, domain: str, report_type: str) -> dict[str, tuple[str, str]]:
    """std level-2 子章节索引：归一 canonical → (子章节 id, 其 std 父 id)。"""
    prefix = f"CH_{domain}_{report_type}_std_"
    rows = session.run(
        """
        MATCH (s:ChapterTemplate) WHERE s.id STARTS WITH $prefix AND s.level = 2
        OPTIONAL MATCH (p:ChapterTemplate)-[:HAS_CHILD]->(s)
        RETURN s.id AS id, s.canonical_chapter_key AS key, p.id AS parent_id
        ORDER BY id
        """,
        prefix=prefix,
    )
    index: dict[str, tuple[str, str]] = {}
    for r in rows:
        key = normalize_chapter_key(r["key"] or "")
        if key and r["parent_id"] and key not in index:
            index[key] = (r["id"], r["parent_id"])
    return index


def fetch_pg_outline_rows(conn, domain: str, report_type: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(PG_OUTLINE_QUERY, (domain, report_type))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def exec_pg_merge(conn, plan: dict) -> None:
    from psycopg.types.json import Json

    json_cols = set(PG_MERGE_LIST_FIELDS) | {"source_task_ids"}
    if plan["set"]:
        sets, params = [], []
        for col, val in plan["set"].items():
            params.append(Json(val) if col in json_cols else val)
            sets.append(f"{col} = %s")
        params.append(plan["survivor_id"])
        with conn.cursor() as cur:
            cur.execute(f"UPDATE domain_factory_outlines SET {', '.join(sets)} WHERE id = %s", params)
    if plan["delete_ids"]:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM domain_factory_outlines WHERE id = ANY(%s)", (plan["delete_ids"],))


def connect_pg():
    """psycopg3 直连（容器内 POSTGRES_URL 为 SQLAlchemy 方言 URL，剥掉方言后缀）。"""
    import psycopg

    url = os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/yuxi")
    return psycopg.connect(url.replace("+asyncpg", "").replace("+psycopg", ""))


def dump_snapshot(driver, path: str, domain: str, report_type: str) -> None:
    """安全网（spec §4.4）：治理前全量快照落盘（节点属性 + 出边），留档可回滚。"""
    with driver.session() as session:
        nodes = [dict(r["props"]) for r in session.run(
            "MATCH (n:ChapterTemplate {domain: $d, report_type: $rt}) RETURN properties(n) AS props",
            d=domain, rt=report_type,
        )]
        edges = [dict(r) for r in session.run(
            """
            MATCH (a:ChapterTemplate {domain: $d, report_type: $rt})-[r]->(b)
            RETURN a.id AS source, type(r) AS rel_type, b.id AS target
            """,
            d=domain, rt=report_type,
        )]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, ensure_ascii=False, default=str, indent=2)


# ---------------- 治理编排 ----------------


def new_report() -> dict:
    return {
        "graph": {
            "normalized": 0, "normalized_detail": [],
            "merged_groups": 0, "merged_detail": [],
            "reparented": 0, "reparented_detail": [],
            "retitled": 0, "retitled_detail": [],
            "deleted_subtrees": 0, "deleted_detail": [],
            "meta_backfilled": 0, "meta_backfill_detail": [],
        },
        "pg": {"merged_rows": 0, "normalized_rows": 0, "merged_detail": []},
        "projected": {"roots": 0, "remaining_dup_groups": 0},
    }


class ChapterGovernance:
    """存量章节模板治理器。dry_run=True 时只算动作清单不落写。"""

    def __init__(self, domain: str, report_type: str, dry_run: bool):
        self.domain = domain
        self.report_type = report_type
        self.dry_run = dry_run

    def _merge_to_fixpoint(self, session, state: GraphState, g: dict, max_passes: int = 10) -> None:
        """② 分组合并，迭代至不动点（父层合并会解锁子层新组）。"""
        for _ in range(max_passes):
            merges = plan_merges(state)
            if not merges:
                break
            g["merged_groups"] += len(merges)
            g["merged_detail"].extend(merges)
            if not self.dry_run:
                for m in merges:
                    for dup in m["deletes"]:
                        exec_merge(session, m["survivor"], dup)
            for m in merges:
                apply_merge(state, m)

    def run_graph(self, session, pg_conn, report: dict) -> None:
        """Neo4j 阶段 ①-⑥，按序执行；pg_conn 用于 ⑥ meta 回填。"""
        g = report["graph"]
        state = fetch_graph_state(session, self.domain, self.report_type)

        # ① 全量归一 canonical
        for nid in sorted(state.nodes):
            n = state.nodes[nid]
            target = normalize_chapter_key(n["canonical"] or "") or normalize_chapter_key(n.get("title") or "")
            if not target or target == n["canonical"]:
                continue
            g["normalized"] += 1
            g["normalized_detail"].append({"id": nid, "from": n["canonical"], "to": target})
            n["canonical"] = target
            n["canonical_norm"] = target
            if not self.dry_run:
                session.run(
                    "MATCH (ch:ChapterTemplate {id: $id}) SET ch.canonical_chapter_key = $key",
                    id=nid, key=target,
                )

        # ② 纠挂：错挂 level-2 节点先归位——重复簇尚未合并，多数簇信号完整；
        #    若先合并，错挂节点已孤立成单成员组，回退依据消失
        std_sub_index = fetch_std_sub_index(session, self.domain, self.report_type)
        for rp in plan_reparents(state, std_sub_index):
            g["reparented"] += 1
            g["reparented_detail"].append(rp)
            if not self.dry_run:
                exec_reparent(session, rp["id"], rp["to"])
            apply_reparent(state, rp)

        # ③ 分组合并（纠挂归位后同父重复一次收敛至不动点）
        self._merge_to_fixpoint(session, state, g)

        # ④ 编号结构化
        for plan in plan_retitles(state):
            g["retitled"] += 1
            g["retitled_detail"].append(plan)
            if not self.dry_run:
                exec_retitle(session, plan)
            apply_retitle(state, plan)

        # ⑤ 删「测试」前缀子树
        for d in plan_test_deletions(state):
            g["deleted_subtrees"] += 1
            g["deleted_detail"].append(d)
            if not self.dry_run:
                exec_delete(session, d["ids"])
            apply_deletions(state, d["ids"])

        # ⑥ PG → 图谱 meta 回填
        if pg_conn is None:
            g["meta_backfill_error"] = "PG 未连接，跳过 meta 回填"
        else:
            rows = fetch_pg_outline_rows(pg_conn, self.domain, self.report_type)
            plans, ambiguous = plan_meta_backfill(state, rows)
            g["meta_skipped_ambiguous"] = ambiguous
            for plan in plans:
                g["meta_backfilled"] += 1
                g["meta_backfill_detail"].append(plan)
                if not self.dry_run:
                    exec_meta_backfill(session, plan)
                apply_meta_backfill(state, plan)

        # 投影：治理后根数与剩余重复组（验收应为 13 / 0）
        groups: dict[tuple, list[str]] = {}
        for nid in state.nodes:
            key = state.group_key(nid)
            if key[0]:
                groups.setdefault(key, []).append(nid)
        report["projected"]["roots"] = sum(1 for n in state.nodes.values() if n["level"] == 1)
        report["projected"]["remaining_dup_groups"] = sum(1 for ids in groups.values() if len(ids) > 1)

    def run_pg(self, conn, report: dict) -> None:
        """PG 阶段：带编号 canonical 行归并到无编号行，canonical 重命名为归一值。"""
        p = report["pg"]
        rows = fetch_pg_outline_rows(conn, self.domain, self.report_type)
        for plan in plan_pg_merges(rows):
            if plan["delete_ids"]:
                p["merged_rows"] += len(plan["delete_ids"])
            elif plan["set"].get("canonical_chapter_key"):
                p["normalized_rows"] += 1
            p["merged_detail"].append(plan)
            if not self.dry_run:
                exec_pg_merge(conn, plan)
        if not self.dry_run:
            conn.commit()


# ---------------- CLI ----------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="存量 ChapterTemplate 治理：归一并去重、纠挂、编号结构化、删测试子树、meta 回写（bug-4167）",
    )
    parser.add_argument("--apply", action="store_true", help="真正落写（缺省 dry-run 只打印 JSON 报告）")
    parser.add_argument("--domain", default="coal", help="领域编码（默认 coal）")
    parser.add_argument("--report-type", default="eia_report", help="报告类型编码（默认 eia_report）")
    parser.add_argument("--scope", choices=["graph", "pg", "all"], default="all", help="治理范围（默认 all）")
    parser.add_argument("--uri", default="bolt://graph:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j 用户名")
    parser.add_argument("--password", default="0123456789", help="Neo4j 密码")
    parser.add_argument("--snapshot", default=None, help="apply 落写前图谱快照 JSON 存盘路径（安全网，可选）")
    return parser


def _connect_pg_quietly(report: dict):
    """PG 连接（⑥ meta 回填 / PG 阶段共用）；失败记录到报告并返回 None，不中断图谱治理。"""
    try:
        return connect_pg()
    except Exception as e:  # noqa: BLE001 —— 连接失败需降级为报告字段
        report["pg_error"] = str(e)
        print(f"[warn] PG 连接失败: {e}", file=sys.stderr)
        return None


def _print_report(args, report: dict) -> None:
    g, p = report["graph"], report["pg"]
    mode = "apply(落写)" if args.apply else "dry-run(预览)"
    print(f"模式: {mode} | 范围: {args.scope} | 对象: {args.domain}/{args.report_type}")
    print(
        f"图谱: 归一 {g['normalized']} | 合并组 {g['merged_groups']} | 纠挂 {g['reparented']} | "
        f"改号 {g['retitled']} | 删子树 {g['deleted_subtrees']} | meta 回填 {g['meta_backfilled']}"
    )
    print(f"PG: 归并行 {p['normalized_rows']} | 合并行 {p['merged_rows']}")
    print(f"投影: 根数 {report['projected']['roots']} | 剩余重复组 {report['projected']['remaining_dup_groups']}")
    print("=== 治理报告(JSON) ===")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    args = build_parser().parse_args()
    dry_run = not args.apply
    gov = ChapterGovernance(args.domain, args.report_type, dry_run)
    report = new_report()

    if args.scope in ("graph", "all"):
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
        if args.snapshot and not dry_run:
            dump_snapshot(driver, args.snapshot, args.domain, args.report_type)
        pg_conn = _connect_pg_quietly(report)
        try:
            with driver.session() as session:
                gov.run_graph(session, pg_conn, report)
            if args.scope == "all":
                if pg_conn is not None:
                    gov.run_pg(pg_conn, report)
                else:
                    report["pg"]["error"] = "PG 未连接，跳过 PG 归并"
        finally:
            if pg_conn is not None:
                pg_conn.close()
            driver.close()

    if args.scope == "pg":
        pg_conn = connect_pg()
        try:
            gov.run_pg(pg_conn, report)
        finally:
            pg_conn.close()

    _print_report(args, report)


if __name__ == "__main__":
    main()
