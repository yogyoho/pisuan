# 存量重绑：按收紧后的确定性匹配口径（bug-4288）重算 WAITING_REVIEW 任务插槽的 entity_ref。
#
# 对每个非空 ref：
#   keep     实体级 BARE 引用，或新口径重算结果 == 现值（唯一精确/唯一包含）
#   correct  新口径给出不同 ref（罕见校正）
#   clear    新口径给 None（≥2 字模糊已废/精确歧义/包含多候选/悬空）→ 置空，
#            留给人工审核或 LLM discover 流，宁缺勿错
# 只动任务插槽；已学习模板是评审产物不回改。
# 流程：备份 /tmp/rebind-strict-backup-<ts>.json → 逐任务更新 → 显式 remap 一次
# （legacy 静态表仅对空槽且头在活跃实体库时回填）→ 复核统计。
#
# 用法（api 容器内）：
#   python -m scripts.governance.rebind_slots_strict            # dry-run 摘要
#   python -m scripts.governance.rebind_slots_strict --apply
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def run(apply: bool) -> None:
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        DomainFactoryRepository,
    )
    from pisuan.services.domain_factory_service import DomainFactoryService
    from pisuan.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)
    entity_keys = {e["entity_key"] for e in entities}
    prop_index: dict[str, list[tuple[str, str, dict]]] = {}
    for e in entities:
        for p in e.get("properties") or []:
            if isinstance(p, dict) and p.get("name_cn") and p.get("key"):
                prop_index.setdefault(str(p["name_cn"]).strip(), []).append(
                    (e["entity_key"], str(p["key"]), p)
                )

    repo = DomainFactoryRepository()
    tasks = await DomainEntityRepository().list_usage_pending_tasks(GENERAL_DOMAIN_CODE)
    stats: Counter = Counter()
    backup: list[dict] = []
    changed_tasks: dict[str, list] = {}
    samples: dict[str, list[str]] = {"correct": [], "clear_strict": [], "keep": []}

    for row in tasks:
        paragraphs = row.get("source_paragraphs") or []
        task_changed = False
        for para in paragraphs:
            tmpl = para.get("template") if isinstance(para, dict) else None
            if not isinstance(tmpl, dict):
                continue
            for slot in tmpl.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                ref = str(slot.get("entity_ref") or "").strip()
                if not ref:
                    stats["unbound_before"] += 1
                    continue
                head, sep, prop = ref.partition(".")
                if not sep:  # BARE 实体级引用
                    if head not in entity_keys:
                        stats["clear_bare_dangling"] += 1
                        slot["entity_ref"] = ""
                        task_changed = True
                        backup.append({"task": row["id"], "slot": slot.get("name"), "old": ref, "why": "bare_dangling"})
                    else:
                        stats["keep_bare"] += 1
                    continue
                new = DomainFactoryService._match_slot_to_property(str(slot.get("name") or "").strip(), prop_index)
                if head not in entity_keys or not any(
                    p.get("key") == prop
                    for p in (next((e for e in entities if e["entity_key"] == head), {}) or {}).get("properties") or []
                    if isinstance(p, dict)
                ):
                    stats["clear_dangling"] += 1
                    slot["entity_ref"] = ""
                    task_changed = True
                    backup.append({"task": row["id"], "slot": slot.get("name"), "old": ref, "why": "dangling"})
                elif new == (head, prop):
                    stats["keep"] += 1
                    if len(samples["keep"]) < 6:
                        samples["keep"].append(f"{slot.get('name')!r} → {ref}")
                elif new is None:
                    stats["clear_strict"] += 1
                    if len(samples["clear_strict"]) < 8:
                        samples["clear_strict"].append(f"{slot.get('name')!r} → {ref}")
                    slot["entity_ref"] = ""
                    task_changed = True
                    backup.append({"task": row["id"], "slot": slot.get("name"), "old": ref, "why": "strict_none"})
                else:
                    stats["correct"] += 1
                    if len(samples["correct"]) < 8:
                        samples["correct"].append(f"{slot.get('name')!r}: {ref} ⇒ {new[0]}.{new[1]}")
                    slot["entity_ref"] = f"{new[0]}.{new[1]}"
                    task_changed = True
                    backup.append({"task": row["id"], "slot": slot.get("name"), "old": ref, "new": slot["entity_ref"], "why": "corrected"})
        if task_changed:
            changed_tasks[row["id"]] = paragraphs

    print("=" * 60)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    for label, items in samples.items():
        if items:
            print(f"\n-- {label} 样例 --")
            for line in items:
                print(f"  {line}")

    if not apply:
        print(f"\n[dry-run] 将改动 {len(changed_tasks)} 个任务，备份+写库未执行")
        return

    if changed_tasks:
        ts = time.strftime("%Y%m%d-%H%M%S")
        Path(f"/tmp/rebind-strict-backup-{ts}.json").write_text(
            json.dumps(backup, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        for tid, paragraphs in changed_tasks.items():
            await repo.update_task(tid, {"source_paragraphs": paragraphs})
        print(f"已更新 {len(changed_tasks)} 个任务，备份 {len(backup)} 条 → /tmp/rebind-strict-backup-{ts}.json")

    from pisuan.services.domain_factory_service import get_domain_factory_service

    n = await get_domain_factory_service().remap_waiting_review_tasks(GENERAL_DOMAIN_CODE)
    print(f"remap 完成，刷新 {n} 个任务")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="落库（默认 dry-run）")
    asyncio.run(run(parser.parse_args().apply))
