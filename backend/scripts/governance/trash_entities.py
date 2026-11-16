# 实体批量入回收站（软删除）+ 引用安全清理（治理工具，可复用）。
#
# 与 repair_entity_spec.py 的 trash 步骤同机制，独立成工具供后续批次使用：
#   1. 校验 keys 均为活跃实体（已回收的警告跳过）
#   2. 统计引用面：待审任务插槽 / 学习模板插槽 / 报告 pps / 区域事实
#   3. --apply：备份受影响行 → 逐个 delete_entity（软删除）
#      → 学习模板指向被删头的引用清空（任务插槽由 remap 步骤 1 失效清理）
#      → pps 裸键/点号键指向被删头的清空
#      → remap_waiting_review_tasks 全量重绑定 → 复核残留必须为 0
# 区域事实（regional_facts）只报告不清理：属历史数据，消费侧按 key 关联缺失即自然失配。
#
# 用法（api 容器内）：
#   python -m scripts.governance.trash_entities --keys npp_model_parameters          # dry-run
#   python -m scripts.governance.trash_entities --keys npp_model_parameters --apply
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def run(keys: list[str], apply: bool) -> int:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        DomainFactoryRepository,
    )
    from yuxi.services.domain_entity_service import DomainEntityService
    from yuxi.services.domain_factory_service import DomainFactoryService
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    repo = DomainEntityRepository()
    entities = {e["entity_key"]: e for e in await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)}
    trashed_set = {e["entity_key"] for e in await repo.list_deleted(None)}
    to_delete, tset = [], set()
    for k in keys:
        if k in entities:
            to_delete.append(k)
            tset.add(k)
        elif k in trashed_set:
            # 已在回收站：不重复删除，但引用清理/重映射/复核照走（补清历史悬空引用）
            print(f"已在回收站（仅清引用）: {k}")
            tset.add(k)
        else:
            print(f"跳过（不存在）: {k}")
    if not tset:
        print("无可清理目标")
        return 1

    # ---- 引用面统计 ----
    task_refs: dict[str, list[str]] = {k: [] for k in tset}
    affected_tasks: dict[str, list] = {}
    for row in await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
        hit = False
        for para in row.get("source_paragraphs") or []:
            tmpl = para.get("template") if isinstance(para, dict) else None
            if not isinstance(tmpl, dict):
                continue
            for slot in tmpl.get("slots") or []:
                ref = str((slot or {}).get("entity_ref") or "").strip()
                head = ref.partition(".")[0]
                if head in tset:
                    task_refs[head].append(f"{row['id']}:{ref}")
                    hit = True
        if hit:
            affected_tasks[row["id"]] = row.get("source_paragraphs") or []

    learned_refs: dict[str, list[str]] = {k: [] for k in tset}
    affected_templates: dict[int, list] = {}
    for row in await repo.list_usage_learned_templates(GENERAL_DOMAIN_CODE):
        hit_refs = []
        for slot in row.get("slots") or []:
            ref = str((slot or {}).get("entity_ref") or "").strip()
            if ref.partition(".")[0] in tset:
                hit_refs.append(ref)
        if hit_refs:
            affected_templates[row["id"]] = row.get("slots") or []
            for r in hit_refs:
                learned_refs[r.partition(".")[0]].append(r)

    pps_refs = []
    for row in await repo.list_usage_report_pps(GENERAL_DOMAIN_CODE):
        if str(row.get("entity_key") or "").strip().partition(".")[0] in tset:
            pps_refs.append(str(row["entity_key"]).strip())
    fact_refs = []
    for row in await repo.list_usage_regional_facts():
        if str(row.get("entity_key") or "").strip().partition(".")[0] in tset:
            fact_refs.append(str(row["entity_key"]).strip())

    print("=" * 60)
    print(f"目标实体 {len(tset)} 个: {sorted(tset)}")
    for k in sorted(tset):
        name = entities[k].get("name_cn") if k in entities else "（已在回收站）"
        print(f"  {k}（{name}）: 任务插槽 {len(task_refs[k])} / 模板插槽 {len(learned_refs[k])}")
    print(f"pps 引用 {len(pps_refs)}，区域事实引用 {len(fact_refs)}（只报告不清理）")
    if not apply:
        print("dry-run 结束，加 --apply 执行")
        return 0

    # ---- 备份 ----
    stamp = date.today().strftime("%Y%m%d-%H%M%S")
    backup = {
        "targets": sorted(tset),
        "tasks": affected_tasks,
        "learned_templates": {str(k): v for k, v in affected_templates.items()},
    }
    backup_path = Path(f"/tmp/trash-entities-backup-{stamp}.json")
    backup_path.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    print(f"备份已写入 {backup_path}")

    # ---- trash ----
    service = DomainEntityService()
    for k in to_delete:
        await service.delete_entity(k)
        print(f"已入回收站: {k}")

    # ---- 学习模板引用清空 ----
    ref_map = {r: "" for refs in learned_refs.values() for r in set(refs)}
    if ref_map:
        n = await DomainFactoryRepository().rewrite_learned_template_slot_refs(ref_map)
        print(f"学习模板引用清空: {n} 个模板")

    # ---- pps 引用清空 ----
    if pps_refs:
        n = await DomainFactoryRepository().clear_report_pps_entity_keys(set(pps_refs))
        print(f"pps 引用清空: {n} 行")

    # ---- 重映射 + 复核 ----
    remapped = await DomainFactoryService().remap_waiting_review_tasks(GENERAL_DOMAIN_CODE)
    print(f"待审任务重映射: {remapped} 个")

    leftovers = 0
    for row in await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
        for para in row.get("source_paragraphs") or []:
            tmpl = para.get("template") if isinstance(para, dict) else None
            if not isinstance(tmpl, dict):
                continue
            for slot in tmpl.get("slots") or []:
                if str((slot or {}).get("entity_ref") or "").strip().partition(".")[0] in tset:
                    leftovers += 1
    for row in await repo.list_usage_learned_templates(GENERAL_DOMAIN_CODE):
        for slot in row.get("slots") or []:
            if str((slot or {}).get("entity_ref") or "").strip().partition(".")[0] in tset:
                leftovers += 1
    if leftovers:
        print(f"!! 复核失败：仍有 {leftovers} 条残留引用")
        return 1
    print("复核通过：被删实体引用残留 0")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", required=True, help="逗号分隔的 entity_key 列表")
    parser.add_argument("--apply", action="store_true", help="实际执行（默认 dry-run）")
    args = parser.parse_args()
    sys.exit(asyncio.run(run([k.strip() for k in args.keys.split(",") if k.strip()], args.apply)))
