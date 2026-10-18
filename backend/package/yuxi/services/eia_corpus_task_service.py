"""eia_corpus_task_service.py — 环评文件库 P2 后台任务（KB 推送 / 语料加工 / 绑定）。

KB 推送走既有公开链（spec 2026-10-18 D5 直通）：add_file_record（MinIO URL +
content_hashes + source_path 显示名 `<原名>.md`）→ parse_file（.md 原生直读）→
index_file。对照样板：knowledge_task_service.run_knowledge_ingest。
重推语义：已推送且 md 未变（md_sha1 相同）→ no-op；md 已重产 → 删旧 KB 文档后
重新登记（一对一镜像）；从未推送 → 首推。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from yuxi.config.options import system_options, update_option_value
from yuxi.knowledge.runtime import knowledge_base
from yuxi.knowledge.utils.kb_utils import calculate_content_hash
from yuxi.repositories.eia_library_repository import EiaLibraryRepository
from yuxi.services.eia_library_service import MINIO_BUCKET
from yuxi.services.task_service import TaskContext
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.logging_config import logger

_repo = EiaLibraryRepository()


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
    if row.kb_file_id and row.kb_status == "indexed" and md_sha1_now != row.md_sha1:
        await knowledge_base.delete_file(kb_id, row.kb_file_id)  # md 已重产 → 替换（删旧登新）

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
