"""E2E 诊断脚本②：工作台写入语义 + 「确认实体 remap 被旧内存覆盖」缺陷复现。

背景（docs/vibe 诊断，EtlWorkbench.vue）：
  - 工作台不持有草稿副本：source_paragraphs 是 taskDetail 的别名（EtlWorkbench.vue:338）。
  - 保存 = 全量替换，无 version/ETag：save_task_step('structured') 直接覆写两列
    （domain_factory_service.py:4270-4277）。
  - 确认实体后后端会 remap 同域全部 WAITING_REVIEW 任务，给空 entity_ref 补绑
    （domain_factory_service.py:6554-6613）。
  - 前端确认成功后不刷新 taskDetail，内存里仍是 remap 前的快照；
    下一次保存/入库会把 remap 结果覆盖回去。

本脚本同时验证两件事（真实服务层代码路径，不需要浏览器）：
  A. remap 的匹配源是静态文件 server/coal_eia_entity_types.json（17 个旧实体类型，
     EntityMetaLoader），与「实体构建」页维护的 domain_entity_schemas 不是同一份数据。
     因此确认通用域实体不会产生任何 remap（remapped=0）。
  B. 一旦 entity_ref 被填上（若 remap 对齐了实体库），前端用旧快照全量保存会把它覆盖回空。
     S4 用直写 DB 模拟「remap 生效」后的服务端状态，再重放前端保存请求复现该缺陷。

副作用控制：
  - confirm 会 remap 同域其他 WAITING_REVIEW 任务：脚本先快照所有 pending 任务的
    source_paragraphs，finally 原样写回。
  - 探针实体/事实/任务清理 + 行数指纹核对，结束零残留。

用法（api 容器内）：
  docker exec pisuan-localized-api-1 uv run --no-sync python /app/scripts/verify_workbench_remap_e2e.py
退出码：0=全部通过；1=存在 FAIL。
"""

from __future__ import annotations

import asyncio
import copy
import sys
import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update

from pisuan.repositories.domain_entity_repository import DomainEntityRepository
from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from pisuan.services.domain_factory_service import get_domain_factory_service
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_entity import DomainEntitySchema
from pisuan.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryRegionalFact,
    DomainFactoryTask,
)

PROBE_PREFIX = "e2e_probe"
ENTITY_KEY = f"{PROBE_PREFIX}_remap_entity"
SLOT_NAME = "龦龧龩龫龭龯"  # 生僻字槽名：不会与既有实体/插槽同名（同一自证策略见 verify_entity_chain_e2e.py）

_checks: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _checks.append((bool(ok), f"{label}{('：' + detail) if detail else ''}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return bool(ok)


async def fingerprint() -> dict[str, int]:
    async with pg_manager.get_async_session_context() as session:
        entities = (
            await session.execute(
                select(func.count())
                .select_from(DomainEntitySchema)
                .where(DomainEntitySchema.domain_code == GENERAL_DOMAIN_CODE)
            )
        ).scalar_one()
        facts = (await session.execute(select(func.count()).select_from(DomainFactoryRegionalFact))).scalar_one()
        tasks = (await session.execute(select(func.count()).select_from(DomainFactoryTask))).scalar_one()
    return {"entities": entities, "facts": facts, "tasks": tasks}


async def snapshot_pending_tasks() -> dict[str, list]:
    """快照同域全部 WAITING_REVIEW 任务段落（confirm 会跨任务 remap）。"""
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.execute(
                select(DomainFactoryTask.id, DomainFactoryTask.source_paragraphs).where(
                    DomainFactoryTask.status == "WAITING_REVIEW"
                )
            )
        ).all()
    return {r.id: copy.deepcopy(r.source_paragraphs or []) for r in rows}


async def restore_pending_tasks(snapshot: dict[str, list], skip_task_id: str) -> int:
    restored = 0
    async with pg_manager.get_async_session_context() as session:
        for task_id, paragraphs in snapshot.items():
            if task_id == skip_task_id:
                continue
            await session.execute(
                update(DomainFactoryTask).where(DomainFactoryTask.id == task_id).values(source_paragraphs=paragraphs)
            )
            restored += 1
    return restored


async def get_paragraphs(task_id: str) -> list:
    async with pg_manager.get_async_session_context() as session:
        row = (
            await session.execute(
                select(DomainFactoryTask.source_paragraphs, DomainFactoryTask.structured_blocks).where(
                    DomainFactoryTask.id == task_id
                )
            )
        ).first()
    return list(row) if row else [None, None]


def slot_ref(paragraphs: list) -> str:
    try:
        return paragraphs[0]["template"]["slots"][0].get("entity_ref", "")
    except (IndexError, KeyError, TypeError):
        return "<missing>"


async def main() -> int:
    svc = get_domain_factory_service()
    entity_repo = DomainEntityRepository()
    task_id = str(uuid.uuid4())

    async with pg_manager.get_async_session_context() as session:
        domain = (
            await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.code == GENERAL_DOMAIN_CODE))
        ).scalar_one_or_none()
    if domain is None:
        print("FATAL：未找到通用域，无法构造合成任务")
        return 1

    pre_fp = await fingerprint()
    print(f"前置指纹: {pre_fp}")
    pending_snapshot = await snapshot_pending_tasks()
    print(f"快照同域 WAITING_REVIEW 任务 {len(pending_snapshot)} 个（confirm 会跨任务 remap，finally 原样写回）")

    paragraphs = [
        {
            "id": "e2e-remap-p1",
            "title": "E2E探针段落",
            "content": f"监测断面{SLOT_NAME}为3.5mg/L，趋势平稳。",
            "classify_type": "text",
            "template": {
                "generalized": f"监测断面{{{{{SLOT_NAME}}}}}为3.5mg/L，趋势平稳。",
                "slots": [
                    {
                        "name": SLOT_NAME,
                        "type": "NumericValue",
                        "description": "E2E remap 验证 slot",
                        "entity_ref": "",
                    }
                ],
                "metadata": {"chapter": "3", "tags": []},
            },
        }
    ]
    async with pg_manager.get_async_session_context() as session:
        session.add(
            DomainFactoryTask(
                id=task_id,
                domain_id=domain.id,
                file_name="e2e_probe_remap.docx",
                storage_path="e2e/probe/remap.docx",
                status="WAITING_REVIEW",
                uploaded_by="e2e_probe",
                source_paragraphs=paragraphs,
                structured_blocks=[{"id": "t1", "type": "table", "headers": ["a"], "rows": [["1"]]}],
                template_metadata={},
                region_key=None,
                region_label=None,
                scope=None,
                project_name=None,
                knowledge_base_id=None,
            )
        )
    print(f"合成任务: {task_id}")

    try:
        print("\n===== 工作台读链：详情快照（前端内存） =====")
        detail = await svc.get_task_detail(task_id)
        memory = copy.deepcopy((detail or {}).get("source_paragraphs") or [])
        check(
            len(memory) == 1 and slot_ref(memory) == "",
            "S1 详情快照可取，且 slot.entity_ref 初始为空",
            f"ref={slot_ref(memory)!r}",
        )

        print("\n===== remap 匹配源：静态 17 类型文件（非实体构建页数据） =====")
        from pisuan.services.entity_meta_service import EntityMetaLoader, SlotEntityMapper

        legacy = EntityMetaLoader().load()
        legacy_id, legacy_entity = next(iter(legacy.items()))
        legacy_name = legacy_entity.get("name") or ""
        probe_mapped = SlotEntityMapper().map_slots([{"name": legacy_name, "entity_ref": ""}])
        check(
            probe_mapped[0].get("entity_ref") == legacy_id,
            "S2a SlotEntityMapper 对 legacy 实体类型名可精确绑定（机制本身是活的）",
            f"{legacy_id}",
        )

        print("\n===== 确认通用域实体 → 后端 remap =====")
        conf = await svc.confirm_proposed_entities(
            task_id,
            [
                {
                    "suggestion_type": "new_entity",
                    "entity_key": ENTITY_KEY,
                    "name_cn": SLOT_NAME,
                    "category": "其他",  # 非 B 类：不级联区域事实，保持本脚本单一变量
                    "description": "E2E remap 验证实体，验证后删除",
                    "value_type": "Numeric",
                    "properties": [],
                    "synonyms": [],
                    "_confirmed": True,
                }
            ],
        )
        check(isinstance(conf, dict) and conf.get("saved", 0) == 1, "S2 确认实体落库", f"result={conf}")

        db_paras, db_blocks = await get_paragraphs(task_id)
        check(
            conf.get("remapped", 0) == 0 and slot_ref(db_paras) == "",
            "S3 remap 不认实体构建页的实体（匹配源是 17 类型静态文件）：确认后 entity_ref 仍为空",
            f"remapped={conf.get('remapped')}, entity_ref={slot_ref(db_paras)!r}",
        )

        print("\n===== S4：模拟 remap 生效后，前端旧快照全量保存 =====")
        simulated = copy.deepcopy(memory)
        simulated[0]["template"]["slots"][0]["entity_ref"] = f"{ENTITY_KEY}.probe_metric"
        await svc.save_task_step(task_id, {"step": "structured", "payload": {"source_paragraphs": simulated}})
        ref_after_remap = slot_ref((await get_paragraphs(task_id))[0])
        check(bool(ref_after_remap), "S4a 服务端存在已绑定 entity_ref（remap 生效后的状态）", f"{ref_after_remap!r}")

        await svc.save_task_step(task_id, {"step": "structured", "payload": {"source_paragraphs": memory}})
        ref_after_stale = slot_ref((await get_paragraphs(task_id))[0])
        check(
            ref_after_stale == "" and bool(ref_after_remap),
            "S4b【缺陷复现】旧快照保存后 entity_ref 被覆盖回空（前端不刷新 → 下次保存即回退）",
            f"{ref_after_remap!r} → {ref_after_stale!r}",
        )

        print("\n===== 保存语义：structured_blocks 全量替换 =====")
        _, blocks_before = await get_paragraphs(task_id)
        await svc.save_task_step(task_id, {"step": "structured", "payload": {"structured_blocks": []}})
        _, blocks_after = await get_paragraphs(task_id)
        check(
            len(blocks_before) == 1 and blocks_after == [],
            "S5 save_task_step 对 structured_blocks 是全量替换（空数组即清空，无字段级合并/版本校验）",
            f"{len(blocks_before)} → {len(blocks_after)}",
        )

        # 顺带记录跨任务 remap 的真实影响面（不改动其它任务，finally 还原）
        print(f"\n[观察] 本次 confirm 的跨任务 remap={conf.get('remapped')}（同域 WAITING_REVIEW 任务数={len(pending_snapshot)}）")
    finally:
        print("\n===== 清理 =====")
        restored = await restore_pending_tasks(pending_snapshot, skip_task_id=task_id)
        print(f"  还原其它 pending 任务段落 {restored} 行")
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                sa_delete(DomainFactoryRegionalFact).where(DomainFactoryRegionalFact.source_task_id == task_id)
            )
            await session.execute(sa_delete(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
        print(f"  删除合成任务 {task_id}")
        ent = await entity_repo.get_by_key(ENTITY_KEY, domain_code=GENERAL_DOMAIN_CODE)
        if ent is not None:
            await entity_repo.delete(ent.entity_id)
            print(f"  删除探针实体 {ENTITY_KEY}")
        post_fp = await fingerprint()
        clean = post_fp == pre_fp
        print(f"  收尾指纹: {post_fp} {'== 前置 ✓ 零残留' if clean else '!= 前置 ' + str(pre_fp) + ' ✗'}")
        if not clean:
            _checks.append((False, "清理后指纹与前置不一致，存在残留"))
        if pg_manager.async_engine is not None:
            await pg_manager.async_engine.dispose()

    print("\n===== 结果汇总 =====")
    failed = [label for ok, label in _checks if not ok]
    print(f"通过 {len(_checks) - len(failed)}/{len(_checks)}")
    for label in failed:
        print(f"  FAIL: {label}")
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
