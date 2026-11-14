"""E2E 诊断脚本③：工作台入库链（commit → 5 类产物 → 写手消费端），真实栈。

前置：先运行 verify_source_etl_e2e.py，它会把 WAITING_REVIEW 任务 id 写入
      /tmp/e2e_probe_task_id.txt（本脚本消费并负责最终清理）。

覆盖：
  1) 建探针知识库（milvus + bge-m3），commit_task → worker 入库流水线
  2) 产物断言：
     - 知识库文件记录 + 分块（ragflow_like 切块，含原文/泛化模板）
     - domain_factory_learned_templates（本归属 attribution 隔离）
     - domain_factory_outlines（source_task_ids 含探针任务）
     - domain_factory_kb_attributions（一库一归属绑定）
     - Neo4j 图谱节点（doc_<task_id> 文档簇）
     - 任务终态 COMMITTED（FAIL/ PARTIAL 如实记录原因）
  3) 消费端关联：
     - 工具 get_templates（写手取段落模板）能否读到本库归属下的模板
     - 工具 lookup_regional_fact 的归属隔离（本库无事实时返回空 + hint，不跨区混供）
  4) 零残留清理：新图谱节点全删、被改写的共享 ChapterTemplate 属性回滚、
     learned_templates/outlines/kb_attributions 按探针 attribution 删除、探针库删除、任务删除，
     行数指纹与图谱节点集核对。

用法（api 容器内）：
  docker exec pisuan-localized-api-1 uv run --no-sync python /app/scripts/verify_commit_chain_e2e.py
退出码：0=全部通过；1=存在 FAIL。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from types import SimpleNamespace

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update

from pisuan.knowledge.runtime import knowledge_base as kb_manager
from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from pisuan.services.domain_factory_region import attribution_scope_key
from pisuan.services.domain_factory_service import get_domain_factory_service
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_business import TaskRecord
from pisuan.storage.postgres.models_domain_factory import (
    DomainFactoryKnowledgeBaseAttribution,
    DomainFactoryLearnedTemplate,
    DomainFactoryOutline,
    DomainFactoryRegionalFact,
    DomainFactoryTask,
)
from pisuan.utils import hashstr

TASK_ID_FILE = "/tmp/e2e_probe_task_id.txt"
MATCHCOUNT_FILE = "/tmp/e2e_probe_matchcounts.json"
PROBE_KB_NAME = "E2E探针知识库"
EMBED_MODEL = "ollama:bge-m3:latest"
POLL_INTERVAL = 3
POLL_TIMEOUT = 900

_checks: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _checks.append((bool(ok), f"{label}{('：' + detail) if detail else ''}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return bool(ok)


async def fingerprint() -> dict[str, int]:
    async with pg_manager.get_async_session_context() as session:
        return {
            "tasks": (await session.execute(select(func.count()).select_from(DomainFactoryTask))).scalar_one(),
            "facts": (await session.execute(select(func.count()).select_from(DomainFactoryRegionalFact))).scalar_one(),
            "templates": (
                await session.execute(select(func.count()).select_from(DomainFactoryLearnedTemplate))
            ).scalar_one(),
            "outlines": (await session.execute(select(func.count()).select_from(DomainFactoryOutline))).scalar_one(),
            "kb_bindings": (
                await session.execute(select(func.count()).select_from(DomainFactoryKnowledgeBaseAttribution))
            ).scalar_one(),
        }


GRAPH_PROPS_LABELS = ("ChapterTemplate", "DomainOutline")


def snapshot_graph() -> dict:
    """快照全部节点 id + 可能被 commit 改写的共享节点属性（可回滚）。"""
    from pisuan.services.graph_builder import GraphBuilder

    builder = GraphBuilder()
    driver = builder._get_driver()
    if driver is None:
        raise RuntimeError("Neo4j 不可用，无法做零残留快照")
    snap: dict = {"ids": set(), "props": {}}
    with driver.session() as session:
        for row in session.run("MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id"):
            snap["ids"].add(row["id"])
        for label in GRAPH_PROPS_LABELS:
            rows = session.run(
                f"MATCH (n:{label}) WHERE n.id IS NOT NULL RETURN n.id AS id, properties(n) AS props"
            )
            snap["props"][label] = {r["id"]: dict(r["props"]) for r in rows}
    return snap


def cleanup_graph(snap: dict) -> tuple[int, int]:
    """删除本次新增节点；回滚共享节点被改写的属性。返回 (删除数, 回滚数)。"""
    from pisuan.services.graph_builder import GraphBuilder

    builder = GraphBuilder()
    driver = builder._get_driver()
    deleted = restored = 0
    with driver.session() as session:
        current = {r["id"] for r in session.run("MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id")}
        new_ids = sorted(current - snap["ids"])
        for i in range(0, len(new_ids), 200):
            batch = new_ids[i : i + 200]
            session.run(
                "UNWIND $ids AS id MATCH (n) WHERE n.id = id DETACH DELETE n",
                ids=batch,
            )
            deleted += len(batch)
        for label in GRAPH_PROPS_LABELS:
            now = {
                r["id"]: dict(r["props"])
                for r in session.run(
                    f"MATCH (n:{label}) WHERE n.id IS NOT NULL RETURN n.id AS id, properties(n) AS props"
                )
            }
            for node_id, old_props in snap["props"][label].items():
                if node_id in now and now[node_id] != old_props:
                    session.run(
                        f"MATCH (n:{label} {{id: $id}}) SET n = $props",
                        id=node_id,
                        props=old_props,
                    )
                    restored += 1
    return deleted, restored


async def wait_commit(svc, task_id: str) -> tuple[str, list[str]]:
    """等入库终态。WAITING_REVIEW 只在「从未进入 INGESTING 且超过宽限期」时才算中止。"""
    states: list[str] = []
    started = time.time()
    deadline = started + POLL_TIMEOUT
    while time.time() < deadline:
        task = await svc.repo.get_task(task_id)
        if task is None:
            return "MISSING", states
        if not states or states[-1] != task.status:
            states.append(task.status)
            print(f"       状态 → {task.status}")
        if task.status in ("COMMITTED", "COMMIT_PARTIAL", "COMMIT_FAILED"):
            return task.status, states
        if task.status == "WAITING_REVIEW" and (
            "INGESTING" not in states and time.time() - started > 180
        ):
            return "STALLED_WAITING_REVIEW", states
        await asyncio.sleep(POLL_INTERVAL)
    return "TIMEOUT", states


async def main() -> int:
    svc = get_domain_factory_service()
    try:
        with open(TASK_ID_FILE, encoding="utf-8") as f:
            task_id = f.read().strip()
    except FileNotFoundError:
        print(f"FATAL：未找到 {TASK_ID_FILE}，请先运行 verify_source_etl_e2e.py")
        return 1
    probe_task = await svc.repo.get_task(task_id)
    if probe_task is None:
        print(f"FATAL：任务 {task_id} 不存在（可能已被清理），请重跑 verify_source_etl_e2e.py")
        return 1
    if probe_task.status != "WAITING_REVIEW":
        # 陈旧 id（上轮任务已被复用/提交过）会让 wait_commit 立刻返回，误判成功
        print(f"FATAL：任务 {task_id} 状态为 {probe_task.status}，不是 WAITING_REVIEW；请重跑 verify_source_etl_e2e.py")
        return 1
    print(f"探针任务: {task_id}")

    pre_fp = await fingerprint()
    graph_snap = snapshot_graph()
    print(f"前置指纹: {pre_fp}；图谱节点快照 {len(graph_snap['ids'])} 个")
    kb_id = ""
    try:
        print("\n===== 建探针知识库 =====")
        kb_detail = await kb_manager.create_database(
            database_name=PROBE_KB_NAME,
            description="E2E 探针库（脚本创建，结束后删除）",
            kb_type="milvus",
            embedding_model_spec=EMBED_MODEL,
            created_by="e2e_probe",
        )
        kb_id = kb_detail.kb_id
        check(bool(kb_id), "S1 探针知识库创建", f"kb_id={kb_id}")

        print("\n===== 工作台入库：commit_task → worker 流水线 =====")
        summary = await svc.commit_task(task_id, reviewer="e2e_probe", knowledge_base_id=kb_id)
        check(
            isinstance(summary, dict) and summary.get("ingest_task_id") == f"ingest_{task_id}",
            "S2 commit_task 受理（确定性 ingest_task_id，幂等键）",
            f"{summary.get('ingest_task_id') if isinstance(summary, dict) else summary}",
        )
        final, states = await wait_commit(svc, task_id)
        check(final in ("COMMITTED", "COMMIT_PARTIAL"), "S3 入库流水线到达终态", f"{final} 序列={states}")
        check("INGESTING" in states, "S4 观察到 INGESTING 中间态（状态机真实流转）", f"{states}")
        task_row = await svc.repo.get_task(task_id)
        if final == "COMMIT_PARTIAL":
            print(f"       [观察] 部分入库原因: {task_row.error_message}")

        attribution = attribution_scope_key(kb_id, task_row.region_key, task_row.scope, task_row.project_name)
        print(f"       探针归属 attribution={attribution} (region_key={task_row.region_key}, scope={task_row.scope})")

        print("\n===== 产物①：知识库文件 + 分块 =====")
        file_id = f"df_{hashstr(task_id + '|' + kb_id, 12)}"
        try:
            info = await kb_manager.get_file_info(kb_id, file_id)
        except Exception as e:  # noqa: BLE001
            info = {}
            print(f"       get_file_info 失败: {e}")
        base = info.get("meta") or {}
        chunks = info.get("lines") or []
        check(bool(base), "S5 知识库存在探针文件记录", f"file_id={file_id}")
        check(len(chunks) > 0, "S6 探针文件已切块入库", f"chunks={len(chunks)}")
        if chunks:
            joined = json.dumps(chunks, ensure_ascii=False)
            check("泛化模板" in joined or "探针" in joined, "S7 分块内容来自工厂 Markdown 组装（含原文/泛化模板）")

        print("\n===== 产物②③：learned_templates / outlines =====")
        async with pg_manager.get_async_session_context() as session:
            templates = (
                await session.execute(
                    select(DomainFactoryLearnedTemplate).where(
                        DomainFactoryLearnedTemplate.attribution == attribution
                    )
                )
            ).scalars().all()
            outlines = (
                await session.execute(
                    select(DomainFactoryOutline).where(DomainFactoryOutline.attribution == attribution)
                )
            ).scalars().all()
        check(len(templates) > 0, "S8 learned_templates 按归属落库", f"{len(templates)} 条")
        if templates:
            t0 = templates[0]
            print(f"       template: chapter={t0.chapter!r} scope={t0.scope} contributing_task={t0.extra_meta}")
        check(
            any(task_id in (o.source_task_ids or []) for o in outlines),
            "S9 outlines 落库且 source_task_ids 含探针任务",
            f"{len(outlines)} 条 keys={[o.canonical_chapter_key for o in outlines][:4]}",
        )

        print("\n===== 产物④⑤：KB 归属绑定 / 图谱 =====")
        async with pg_manager.get_async_session_context() as session:
            binding = (
                await session.execute(
                    select(DomainFactoryKnowledgeBaseAttribution).where(
                        DomainFactoryKnowledgeBaseAttribution.kb_id == kb_id
                    )
                )
            ).scalar_one_or_none()
        check(
            binding is not None and binding.attribution == attribution,
            "S10 一库一归属绑定写入（attribution 一致）",
            f"{binding.attribution if binding else None}",
        )
        from pisuan.services.graph_builder import GraphBuilder

        driver = GraphBuilder()._get_driver()
        with driver.session() as session:
            doc = session.run(
                "MATCH (d:Document {id: $id}) RETURN d.id AS id", id=f"doc_{task_id}"
            ).single()
            new_count = len(
                {r["id"] for r in session.run("MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id")} - graph_snap["ids"]
            )
        check(doc is not None, "S11 图谱写入 Document 节点 doc_<task_id>")
        check(new_count > 0, "S12 图谱新增节点（段落/章节/模板/法规/表格等）", f"{new_count} 个")

        print("\n===== 消费端：写手工具链 =====")
        from langgraph.prebuilt.tool_node import ToolRuntime

        from pisuan.agents.toolkits.buildin.tools import get_templates, lookup_regional_fact

        # runtime 必须是真实 ToolRuntime（StructuredTool 的 pydantic 校验不接受 SimpleNamespace）
        runtime = ToolRuntime(
            state=None,
            context=SimpleNamespace(knowledges=[kb_id]),
            config=None,
            stream_writer=None,
            tool_call_id=None,
            store=None,
        )
        report_type = task_row.report_type_code or "通用"
        canonical = outlines[0].canonical_chapter_key if outlines else None
        try:
            # @tool 装饰后是 StructuredTool：必须走 ainvoke（与 test/unit 用法一致）
            tool_templates = await get_templates.ainvoke(
                {
                    "domain": GENERAL_DOMAIN_CODE,
                    "report_type": report_type,
                    "canonical_chapter_key": canonical,
                    "kb_id": kb_id,
                    "runtime": runtime,
                }
            )
        except Exception as e:  # noqa: BLE001
            tool_templates = []
            print(f"       get_templates 调用异常: {type(e).__name__}: {e}")
        check(
            isinstance(tool_templates, list) and len(tool_templates) > 0 and "_source" in tool_templates[0],
            "S13 工具 get_templates 在探针库归属下读到模板（图谱/DB 回退）",
            f"n={len(tool_templates) if isinstance(tool_templates, list) else tool_templates}, "
            f"source={tool_templates[0].get('_source') if tool_templates else None}",
        )
        try:
            fact_res = await lookup_regional_fact.ainvoke(
                {"fact_type": "monitoring", "region_key": "e2e-other-region", "kb_id": kb_id, "runtime": runtime}
            )
        except Exception as e:  # noqa: BLE001
            fact_res = {"error": f"{type(e).__name__}: {e}"}
            print(f"       lookup_regional_fact 调用异常: {fact_res['error']}")
        check(
            isinstance(fact_res, dict) and fact_res.get("total") == 0 and fact_res.get("hint"),
            "S14 lookup_regional_fact 归属隔离：无事实返回空 + 提示（不跨区/跨库混供）",
            f"{fact_res.get('total') if isinstance(fact_res, dict) else fact_res}",
        )
    finally:
        print("\n===== 清理 =====")
        if kb_id:
            try:
                await kb_manager.delete_database(kb_id)
                print(f"  删除探针知识库 {kb_id}")
            except Exception as e:  # noqa: BLE001
                print(f"  删除探针知识库失败（需人工）: {e}")
        async with pg_manager.get_async_session_context() as session:
            attr_rows = (
                await session.execute(
                    select(DomainFactoryTask.knowledge_base_id, DomainFactoryTask.region_key,
                           DomainFactoryTask.scope, DomainFactoryTask.project_name)
                    .where(DomainFactoryTask.id == task_id)
                )
            ).first()
        if attr_rows:
            attribution = attribution_scope_key(kb_id or "", attr_rows.region_key, attr_rows.scope, attr_rows.project_name)

            # 每一步独立事务：任一步失败不得回滚前面已删的行（曾因共用 session 导致全部回滚留下残留）
            async def _delete(label: str, stmt) -> None:
                try:
                    async with pg_manager.get_async_session_context() as session:
                        result = await session.execute(stmt)
                    print(f"  删除 {label} {result.rowcount or 0} 行")
                except Exception as e:  # noqa: BLE001
                    _checks.append((False, f"清理 {label} 失败：{type(e).__name__}: {e}"))

            await _delete(
                f"learned_templates (attribution={attribution})",
                sa_delete(DomainFactoryLearnedTemplate).where(
                    DomainFactoryLearnedTemplate.attribution == attribution
                ),
            )
            await _delete(
                f"outlines (attribution={attribution})",
                sa_delete(DomainFactoryOutline).where(DomainFactoryOutline.attribution == attribution),
            )
            await _delete(
                "区域事实",
                sa_delete(DomainFactoryRegionalFact).where(
                    DomainFactoryRegionalFact.source_task_id == task_id
                ),
            )
            if kb_id:
                await _delete(
                    "KB 归属绑定",
                    sa_delete(DomainFactoryKnowledgeBaseAttribution).where(
                        DomainFactoryKnowledgeBaseAttribution.kb_id == kb_id
                    ),
                )
            # ETL/commit 各注册一行任务中心（表 tasks，无 FK），直接删任务行不会带走
            await _delete(
                "任务中心行",
                sa_delete(TaskRecord).where(
                    TaskRecord.payload["domain_factory_task_id"].as_string() == task_id
                ),
            )
            await _delete("探针任务", sa_delete(DomainFactoryTask).where(DomainFactoryTask.id == task_id))

        # ETL 模板匹配会给共享学习模板 match_count +1（不按 attribution 过滤），按脚本①快照回写差异行
        try:
            with open(MATCHCOUNT_FILE, encoding="utf-8") as f:
                baseline_counts: dict[str, int] = json.load(f)
        except FileNotFoundError:
            baseline_counts = {}
        if baseline_counts:
            async with pg_manager.get_async_session_context() as session:
                now_counts = {
                    r.id: r.match_count
                    for r in (
                        await session.execute(
                            select(DomainFactoryLearnedTemplate.id, DomainFactoryLearnedTemplate.match_count)
                        )
                    ).all()
                }
                drifted = {k: v for k, v in baseline_counts.items() if now_counts.get(k, v) != v}
                for tid, mc in drifted.items():
                    await session.execute(
                        update(DomainFactoryLearnedTemplate)
                        .where(DomainFactoryLearnedTemplate.id == tid)
                        .values(match_count=mc)
                    )
            print(f"  回写学习模板 match_count：{len(drifted)} 行漂移已还原（基线 {len(baseline_counts)} 行）")

        deleted, restored = cleanup_graph(graph_snap)
        print(f"  图谱清理：删除新增节点 {deleted} 个，回滚共享节点属性 {restored} 个")

        post_fp = await fingerprint()
        # 前置指纹含探针任务本身（脚本①留下的 WAITING_REVIEW 任务），清理后应恰好少 1 行
        expected_fp = {**pre_fp, "tasks": pre_fp["tasks"] - 1}
        clean = post_fp == expected_fp
        print(f"  收尾指纹: {post_fp} {'== 前置-探针任务 ✓ 零残留' if clean else '!= ' + str(expected_fp) + ' ✗'}")
        if not clean:
            _checks.append((False, "清理后指纹与前置不一致，存在残留"))
        if pg_manager.async_engine is not None:
            await pg_manager.async_engine.dispose()

    print("\n===== 结果汇总 =====")
    failed = [label for ok, label in _checks if not ok]
    print(f"通过 {len(_checks) - len(failed)}/{len(_checks)}")
    for label in failed:
        print(f"  FAIL: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
