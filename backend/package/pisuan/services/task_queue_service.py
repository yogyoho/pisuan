from __future__ import annotations

import asyncio
import os
from functools import partial

from pisuan.repositories.task_repository import TaskRepository
from pisuan.services.run_queue_service import get_arq_pool, get_redis_client
from pisuan.services.task_registry import get_failure_task_definition, get_task_definition
from pisuan.utils.logging_config import logger

TASK_LEASE_SECONDS = 30.0
TASK_HEARTBEAT_SECONDS = 10.0
TASK_CANCEL_POLL_SECONDS = 0.5
TASK_CANCEL_KEY_TTL_SECONDS = int(os.getenv("TASK_CANCEL_KEY_TTL_SECONDS", "1800"))
TASK_RECONCILIATION_SECONDS = 30.0
TASK_RECONCILIATION_HEALTH_KEY = "pisuan:worker:health:durable-task-reconciliation-v1"
TASK_RECONCILIATION_HEALTH_TTL_SECONDS = int(TASK_RECONCILIATION_SECONDS * 2 + 5)


def _task_cancel_key(task_id: str) -> str:
    return f"task:cancel:{task_id}"


async def publish_task(task_id: str) -> None:
    """把已提交的 PG Task 发布为 ARQ 唤醒消息；重复消息由数据库 claim 拒绝。"""
    pool = await get_arq_pool()
    await pool.enqueue_job("process_task", task_id)


async def publish_task_cancel_signal(task_id: str) -> None:
    """在 PostgreSQL 取消事务提交后发布短期 Redis 唤醒信号。"""
    try:
        redis = await get_redis_client()
        await redis.set(_task_cancel_key(task_id), "1", ex=TASK_CANCEL_KEY_TTL_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Failed to publish task cancel signal: task_id=%s: %s", task_id, exc)


async def _read_task_cancel_signal(task_id: str) -> bool:
    redis = await get_redis_client()
    return bool(await redis.get(_task_cancel_key(task_id)))


async def wait_for_task_cancel_signal(
    task_id: str,
    poll_interval_seconds: float = TASK_CANCEL_POLL_SECONDS,
) -> bool:
    """轮询 Redis 取消 key；Redis 故障时保持运行，由 PostgreSQL 心跳兜底。"""
    poll_interval_seconds = max(0.0, float(poll_interval_seconds))
    loop = asyncio.get_running_loop()
    key_failure_logged = False

    while True:
        attempt_started_at = loop.time()
        try:
            if await _read_task_cancel_signal(task_id):
                return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not key_failure_logged:
                logger.warning("Failed to read task cancel signal: task_id=%s: %s", task_id, exc)
                key_failure_logged = True
        else:
            key_failure_logged = False

        remaining = poll_interval_seconds - (loop.time() - attempt_started_at)
        await asyncio.sleep(max(0.0, remaining))


async def clear_task_cancel_signal(task_id: str) -> None:
    """清理已终结 Task 的 Redis 取消信号；失败不影响 PostgreSQL 终态。"""
    try:
        redis = await get_redis_client()
        await redis.delete(_task_cancel_key(task_id))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Failed to clear task cancel signal: task_id=%s: %s", task_id, exc)


async def finalize_task_failure(session, record, error: str) -> None:
    """在 Task 失败事务内执行已注册的领域收敛。"""
    handler_version = 1 if record.handler_version is None else int(record.handler_version)
    try:
        definition = get_failure_task_definition(record.type, handler_version)
    except ValueError:
        logger.error(
            "Cannot finalize unknown durable task: task_id=%s, type=%s, handler_version=%s",
            record.id,
            record.type,
            handler_version,
        )
        return
    handler = definition.load_failure_handler()
    if handler is not None:
        await handler(session, record, error)


async def reconcile_and_publish_tasks() -> list[tuple[str, str, int]]:
    """收敛失联 owner，并发布所有当前 pending Task。"""
    repository = TaskRepository()
    reconciled = await repository.reconcile_expired_leases(
        before_fail=finalize_task_failure,
    )
    await publish_pending_tasks()
    await repository.prune_terminal()
    return reconciled


async def publish_pending_tasks(*, limit: int = 200) -> list[str]:
    """重发 PG 中待执行的任务；重复 ARQ 消息由 task_id/attempt 去重。"""
    published: list[str] = []
    repository = TaskRepository()
    for record in await repository.list_pending(limit=limit):
        try:
            get_task_definition(record.type)
        except ValueError as exc:
            logger.error("Cannot publish unknown durable task: task_id=%s, type=%s", record.id, record.type)
            await repository.fail_pending(record.id, error=str(exc))
            continue
        handler_version = 1 if record.handler_version is None else int(record.handler_version)
        if record.cancel_requested:
            try:
                failure_definition = get_failure_task_definition(record.type, handler_version)
            except ValueError:
                failure_definition = None
            failure_handler = failure_definition.load_failure_handler() if failure_definition is not None else None
            before_cancel = partial(failure_handler, error="任务已取消") if failure_handler is not None else None
            await repository.request_cancel(record.id, before_cancel=before_cancel)
            continue
        try:
            get_task_definition(record.type, handler_version)
        except ValueError as exc:
            error = str(exc)
            logger.error("Cannot rebuild durable task: task_id=%s, type=%s", record.id, record.type)
            try:
                failure_definition = get_failure_task_definition(record.type, handler_version)
            except ValueError:
                failure_definition = None
            failure_handler = failure_definition.load_failure_handler() if failure_definition is not None else None
            before_fail = partial(failure_handler, error=error) if failure_handler is not None else None
            await repository.fail_pending(record.id, error=error, before_fail=before_fail)
            continue
        await publish_task(record.id)
        published.append(record.id)
    return published
