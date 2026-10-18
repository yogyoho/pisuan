"""eia_corpus_task_service.py — 环评文件库 P2 后台任务（KB 推送 / 语料加工 / 绑定）。

KB 推送走既有公开链（spec 2026-10-18 D5 直通）：add_file_record（MinIO URL +
content_hashes + source_path 显示名 `<原名>.md`）→ parse_file（.md 原生直读）→
index_file。对照样板：knowledge_task_service.run_knowledge_ingest。
重推语义：已推送且 md 未变（md_sha1 相同）→ no-op；md 已重产 → 删旧 KB 文档后
重新登记（一对一镜像）；从未推送 → 首推。
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from yuxi.config.options import invalidate_option_cache, system_options, update_option_value
from yuxi.knowledge.runtime import knowledge_base
from yuxi.knowledge.utils.kb_utils import calculate_content_hash
from yuxi.repositories.eia_library_repository import EiaLibraryRepository
from yuxi.services.eia_canonical_md import split_canonical_md
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.services.eia_library_service import MINIO_BUCKET
from yuxi.services.task_service import TaskContext
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger

_repo = EiaLibraryRepository()
_SKILL_REFS = _SKILL_ROOT / "references"  # 模块级便于单测打桩


async def _ensure_kb_exists(kb_id: str) -> None:
    if await knowledge_base.get_database_info(kb_id) is None:
        raise ValueError(f"绑定的知识库不存在: {kb_id}")


async def bind_corpus_kb(kb_id: str, operator: str | None) -> str:
    """绑定目标 KB（存在性校验）→ system_options.eia_corpus_kb_id 持久化。"""
    kb_id = (kb_id or "").strip()
    if not kb_id:
        raise ValueError("kb_id 不能为空")
    await _ensure_kb_exists(kb_id)
    async with pg_manager.get_async_session_context() as session:
        await update_option_value(session, system_options.key, {"eia_corpus_kb_id": kb_id}, operator or "")
        await session.commit()
    await invalidate_option_cache(system_options.key)  # Option.get 走 Redis 缓存，写后必须失效
    return kb_id


async def get_bound_kb_id() -> str:
    config = await system_options.get()
    return (config.get("eia_corpus_kb_id") or "").strip()


async def _resolve_kb_id() -> str:
    kb_id = await get_bound_kb_id()
    if not kb_id:
        raise ValueError("未绑定环评语料知识库：请先在文件库「绑定语料知识库」中设置")
    await _ensure_kb_exists(kb_id)
    return kb_id


def _md_minio_url(object_key: str) -> str:
    return f"http://{get_minio_client().public_endpoint}/{MINIO_BUCKET}/{object_key}"


async def _push_one(row, kb_id: str, operator_id: str | None) -> str:
    """单文件推送；返回终态 kb_status（indexed）。no-op 直接返回现态。"""
    if row.md_status != "ready" or not row.md_object_key:
        raise ValueError(f"md 不可推送（md_status={row.md_status}）")
    client = get_minio_client()
    md_bytes = await client.adownload_file(MINIO_BUCKET, row.md_object_key)
    md_sha1_now = hashlib.sha1(md_bytes).hexdigest()
    if row.kb_file_id and row.kb_status == "indexed" and md_sha1_now == row.md_sha1:
        return row.kb_status  # 已推送且 md 未变 → no-op

    item = _md_minio_url(row.md_object_key)
    params = {
        "content_type": "file",
        "content_hashes": {item: await calculate_content_hash(md_bytes)},
        "file_sizes": {item: len(md_bytes)},
        "source_path": f"{Path(row.original_filename).stem}.md",  # KB 显示名
    }
    if row.kb_file_id:
        # 有旧 KB 登记一律替换（indexed+md 已变 → 删旧登新；failed 半途 → 清半途登记防重复）
        await knowledge_base.delete_file(kb_id, row.kb_file_id)

    await _repo.update_file(row.id, {"kb_id": kb_id, "kb_status": "pushed", "push_error": None})
    file_meta = await knowledge_base.add_file_record(kb_id, item, params=params, operator_id=operator_id)
    file_id = file_meta["file_id"]
    await _repo.update_file(row.id, {"kb_file_id": file_id, "kb_status": "parsing"})
    await knowledge_base.parse_file(kb_id, file_id, operator_id=operator_id)
    await _repo.update_file(row.id, {"kb_status": "indexing"})
    await knowledge_base.index_file(kb_id, file_id, operator_id=operator_id)
    await _repo.update_file(row.id, {"kb_status": "indexed", "md_sha1": md_sha1_now})
    return "indexed"


async def run_eia_corpus_push(context: TaskContext) -> dict:
    """按 file_ids 推送 canonical md 到绑定 KB（逐文件容错，进度/结果入任务中心）。"""
    payload = context.payload
    file_ids: list[int] = payload["file_ids"]
    operator_id = payload.get("operator_id")
    kb_id = await _resolve_kb_id()
    items: list[dict] = []
    failed = 0
    for i, fid in enumerate(file_ids, 1):
        await context.raise_if_cancelled()
        await context.set_progress(5.0 + (i / len(file_ids)) * 90.0, f"推送 {i}/{len(file_ids)}")
        row = await _repo.get_file(fid)
        if row is None:
            items.append({"file_id": fid, "status": "failed", "error": "文件不存在"})
            failed += 1
            continue
        try:
            status = await _push_one(row, kb_id, operator_id)
            items.append({"file_id": fid, "status": status})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[eia-push] {row.original_filename} 推送失败: {exc}")
            await _repo.update_file(fid, {"kb_status": "failed", "push_error": str(exc)[:1000]})
            items.append({"file_id": fid, "status": "failed", "error": str(exc)})
            failed += 1
    summary = {"kb_id": kb_id, "submitted": len(file_ids), "failed": failed, "items": items}
    await context.set_result(summary)
    await context.set_progress(100.0, f"推送完成，失败 {failed} 个" if failed else "推送完成")
    return summary


# ---------------------------------------------------------------- 语料加工（P2）


def _load_bank_compile():
    """importlib 动态加载技能脚本（先例：eia_data_service._load_quantity_re）。"""
    spec = importlib.util.spec_from_file_location("eia_p2_bank_compile", _SKILL_ROOT / "scripts" / "bank_compile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _materialize_workdir(tmp: Path, client, rows: list[dict]) -> list[dict]:
    """DB manifest → temp workdir（<rid>/source.md + manifest.json）。"""
    entries = []
    for row in rows:
        md_bytes = await client.adownload_file(MINIO_BUCKET, row["md_object_key"])
        _, body = split_canonical_md(md_bytes.decode("utf-8"))
        d = tmp / row["report_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "source.md").write_text(body, encoding="utf-8", newline="\n")
        entries.append(
            {
                "report_id": row["report_id"],
                "stage": row["stage"],
                "mineral": row["mineral"] or "coal",
                "file_name": row["original_filename"],
            }
        )
    (tmp / "manifest.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return entries


def _merge_corpus_meta(entries: list[dict], front_by_rid: dict[str, dict]) -> None:
    """DB 封面元数据 → 技能 corpus_meta.json reports 合并（新 rid 增量；既有条目不动）。

    eia_meta_service 以 corpus_meta.reports 为 rid 全集权威（import_annotations 已知
    rid 校验），新报告不合并即被 meta 面跳过——此步是加工闭环的必需动作。
    """
    meta_path = _SKILL_REFS / "samples_bank" / "corpus_meta.json"
    doc = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {"reports": {}}
    reports = doc.setdefault("reports", {})
    for e in entries:
        rid = e["report_id"]
        if rid in reports:
            continue
        f = front_by_rid.get(rid, {})
        reports[rid] = {
            "report_title": f.get("report_title"),
            "report_title_basis": "cover",
            "eia_org": f.get("eia_org"),
            "eia_org_basis": "cover",
            "project_no": f.get("project_no"),
            "province": f.get("province"),
            "province_basis": "cover",
            "year": f.get("year"),
            "cover_scale_mt_a": f.get("cover_scale_mt_a"),
            "scale_basis": "needs_review",
            "scale_candidates": [],
            "stage": e["stage"],
            "mineral": e["mineral"],
        }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


async def run_eia_corpus_process(context: TaskContext) -> dict:
    """P2 加工：前置校验 → 全库重编译（bank_compile --prune）→ corpus_meta 合并 → 台账。

    payload: {file_ids?: [int], scope?: "all", operator_id}
    校验失败（md 非 ready / stage 未填）→ fail fast 列缺项清单（绝不静默跳过）；
    bank_compile 零可编译报告 rc=1 → 任务失败、产物保留原状（拒绝空 bank_index）。
    """
    payload = context.payload
    operator_id = payload.get("operator_id")
    if payload.get("scope") == "all":
        targets = [r for r in await _repo.list_files() if r["md_status"] == "ready"]
    else:
        targets = []
        for fid in payload["file_ids"]:
            row = await _repo.get_file(fid)
            if row is not None:
                targets.append(row.to_dict())

    missing = [
        f"id={r['id']} {r['original_filename']}: md_status={r['md_status']}" + ("" if r["stage"] else "，stage 未填")
        for r in targets
        if r["md_status"] != "ready" or not r["stage"]
    ]
    if missing:
        raise ValueError("加工前置不满足：" + "；".join(missing))

    await context.set_progress(10.0, "物化临时 workdir")
    # 全库重编译语义：以全库可编译集为输入重建全局衍生物（非仅本次触发子集）
    compile_rows = [r for r in await _repo.list_files() if r["md_status"] == "ready" and r["report_id"] and r["stage"]]
    bank = _load_bank_compile()
    with tempfile.TemporaryDirectory(prefix="eia_compile_") as td:
        tmp = Path(td)
        client = get_minio_client()
        entries = await _materialize_workdir(tmp, client, compile_rows)
        await context.set_progress(40.0, f"bank_compile（{len(entries)} 份，--prune）")
        rc = await asyncio.to_thread(
            bank.main_with_args,
            ["--workdir", str(tmp), "--references", str(_SKILL_REFS), "--prune"],
        )
        if rc != 0:
            raise RuntimeError(f"bank_compile 失败（rc={rc}）：产物保留原状，详见 worker 日志")

    _merge_corpus_meta(entries, {r["report_id"]: (r["front_meta"] or {}) for r in compile_rows})
    now = utc_now_naive()
    for r in targets:
        await _repo.update_file(r["id"], {"processed_at": now})
    await _repo_log(
        action="recompile",
        detail={"reports": len(entries), "rids": [e["report_id"] for e in entries]},
        operator=operator_id,
    )
    summary = {"compiled": len(entries)}
    await context.set_result(summary)
    await context.set_progress(100.0, f"加工完成（{len(entries)} 份入编）")
    return summary


async def _repo_log(*, action: str, detail: dict | None, operator: str | None) -> None:
    await _repo.insert_process_log(file_id=None, content_sha1=None, action=action, detail=detail, operator=operator)
