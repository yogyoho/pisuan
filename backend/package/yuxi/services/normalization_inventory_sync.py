"""归一化全集清单自动同步（Gitea）。

实体库变更（创建/更新/删除/恢复/归并）后，防抖合并连续操作，后台依次跑：
  1. audit_normalization        —— 重算同义聚类与归一候选 → /tmp/normalization-report.json
  2. report_merge_candidates    —— 重算实体归并候选 → /tmp/merge-candidates.json
  3. export_normalization_inventory —— 生成全集 md/json
  4. publish_inventory_to_gitea —— 发布 refsadmin/normalization-inventory

失败隔离：同步链任何一步失败只告警，不影响实体保存本身；期间又有变更则自动重跑一轮。
单测环境（PYTEST_CURRENT_TEST 存在）自动禁用。
"""

import asyncio
import os

from yuxi.utils import logger

SYNC_DEBOUNCE_SECONDS = 20
SYNC_STEP_TIMEOUT_SECONDS = 600

_state = {"task": None, "dirty": False}


def _enabled() -> bool:
    return not os.environ.get("PYTEST_CURRENT_TEST")


def schedule_sync() -> None:
    """实体变更后调用：标记脏并确保有一个防抖任务在跑（幂等，fire-and-forget）。"""
    if not _enabled():
        return
    _state["dirty"] = True
    if _state["task"] is None or _state["task"].done():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("[norm-sync] 无运行中事件循环，跳过调度")
            return
        _state["task"] = loop.create_task(_run_delayed())


async def _run_steps() -> None:
    steps = [
        (["python", "-m", "scripts.governance.audit_normalization", "--out", "/tmp/normalization-report.json"],),
        (["python", "-m", "scripts.governance.report_merge_candidates", "--out", "/tmp/merge-candidates.json"],),
        (["python", "-m", "scripts.governance.export_normalization_inventory"],),
        (["python", "-m", "scripts.governance.publish_inventory_to_gitea"],),
    ]
    for (cmd,) in steps:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd="/app",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=SYNC_STEP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"步骤超时: {' '.join(cmd)}")
        if proc.returncode != 0:
            raise RuntimeError(f"步骤失败（exit {proc.returncode}）: {' '.join(cmd)}")
        logger.info(f"[norm-sync] 步骤完成: {' '.join(cmd)}")


async def _run_delayed(delay: int | None = None) -> None:
    await asyncio.sleep(SYNC_DEBOUNCE_SECONDS if delay is None else delay)
    while _state["dirty"]:
        _state["dirty"] = False
        try:
            await _run_steps()
            logger.info("[norm-sync] 归一化全集已重新生成并发布 Gitea")
        except Exception as e:  # noqa: BLE001 — 失败只告警，下一轮实体变更会自动重试
            logger.warning(f"[norm-sync] 同步链失败（不影响实体保存，后续变更将自动重试）: {e}")
            return  # 失败即退出；下次实体变更重新调度
