# 插槽→实体属性绑定质量审计（只读）。
#
# 对 WAITING_REVIEW 任务与学习模板的全部非空 entity_ref，按 _auto_map_slots_to_entity_properties
# 同源的三级匹配口径回溯分级，量化绑定确定性：
#   L1      精确：slot.name == property.name_cn 且该名全库唯一（确定性绑定）
#   L1_AMB  精确歧义：名字精确命中但 ≥2 个实体拥有同名属性（matches[0] 先到先得，实体增删即漂移）
#   L2      包含：slot.name 与属性名互相包含才可解释（中等风险）
#   L3      模糊：仅 ≥2 汉字交集可解释（高风险，同字面大量属性可误绑）
#   ORPHAN  无解释：现库任何属性都无法按三级口径解释该绑定（LLM 建议/历史遗留/错绑）
#   DANGLING 悬空：实体头不在库或属性键不存在
#   BARE    实体级裸引用（规范 §0 合法形态），核查实体在位
# 另统计未绑定插槽（未绑定≠错绑，评审可手工映射）。
#
# 用法（api 容器内）：
#   python -m scripts.governance.audit_slot_binding                # stdout 摘要
#   python -m scripts.governance.audit_slot_binding --out /tmp/slot-binding.json
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def build_prop_index(entities: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """与 _auto_map_slots_to_entity_properties 同源：{name_cn: [(entity_key, prop_key), ...]}"""
    prop_index: dict[str, list[tuple[str, str]]] = {}
    for e in entities:
        ek = str(e.get("entity_key") or "")
        if not ek:
            continue
        for p in e.get("properties") or []:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name_cn") or "").strip()
            pk = str(p.get("key") or "").strip()
            if name and pk:
                prop_index.setdefault(name, []).append((ek, pk))
    return prop_index


def classify_binding(slot_name: str, ref: str, entities_by_key: dict, prop_index: dict) -> str:
    """按三级口径回溯：该绑定能被哪一级解释。"""
    head, sep, suffix = ref.partition(".")
    if head not in entities_by_key:
        return "DANGLING"
    if not sep:
        return "BARE"
    prop = next(
        (
            p
            for p in entities_by_key[head].get("properties") or []
            if isinstance(p, dict) and str(p.get("key") or "") == suffix
        ),
        None,
    )
    if prop is None:
        return "DANGLING"
    prop_name = str(prop.get("name_cn") or "").strip()
    if slot_name == prop_name:
        return "L1" if len(prop_index.get(prop_name, [])) == 1 else "L1_AMB"
    if prop_name and (prop_name in slot_name or slot_name in prop_name):
        return "L2"
    if prop_name and len(set(slot_name) & set(prop_name)) >= 2:
        return "L3"
    return "ORPHAN"


async def run(out_path: str | None) -> None:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)
    entities_by_key = {e["entity_key"]: e for e in entities}
    prop_index = build_prop_index(entities)
    ambiguous_names = {n for n, owners in prop_index.items() if len(owners) > 1}

    async def iter_slots():
        for row in await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
            for para in row.get("source_paragraphs") or []:
                tmpl = para.get("template") if isinstance(para, dict) else None
                if not isinstance(tmpl, dict):
                    continue
                for slot in tmpl.get("slots") or []:
                    if isinstance(slot, dict):
                        yield ("task", row["id"], slot)
        for row in await repo.list_usage_learned_templates(GENERAL_DOMAIN_CODE):
            for slot in row.get("slots") or []:
                if isinstance(slot, dict):
                    yield ("learned", str(row["id"]), slot)

    counter: Counter = Counter()
    unbound = 0
    examples: dict[str, list[str]] = defaultdict(list)
    name_distinct: dict[str, set] = defaultdict(set)

    async for source, owner_id, slot in iter_slots():
        slot_name = str(slot.get("name") or "").strip()
        ref = str(slot.get("entity_ref") or "").strip()
        if not ref:
            unbound += 1
            continue
        label = classify_binding(slot_name, ref, entities_by_key, prop_index)
        counter[f"{source}:{label}"] += 1
        name_distinct[f"{source}:{label}"].add(slot_name)
        if label in ("ORPHAN", "L3", "L1_AMB", "DANGLING") and len(examples[label]) < 12:
            examples[label].append(f"[{source}:{owner_id[:8]}] {slot_name!r} → {ref}")

    print("=" * 60)
    print(f"实体 {len(entities)} 个，同名属性歧义项 {len(ambiguous_names)} 个")
    print(f"未绑定插槽（含实体级留白）：{unbound}")
    total = sum(counter.values())
    print(f"非空绑定共 {total} 条：")
    for label in ("L1", "L1_AMB", "L2", "L3", "ORPHAN", "DANGLING", "BARE"):
        t, n_learned = counter[f"task:{label}"], counter[f"learned:{label}"]
        if t or n_learned:
            print(
                f"  {label:9s} 任务 {t:5d} / 模板 {n_learned:5d}（去重插槽名 "
                f"{len(name_distinct[f'task:{label}'])} / {len(name_distinct[f'learned:{label}'])}）"
            )

    for label in ("ORPHAN", "DANGLING", "L1_AMB", "L3"):
        if examples[label]:
            print(f"\n-- {label} 样例 --")
            for line in examples[label]:
                print(f"  {line}")

    if out_path:
        blob = json.dumps(
            {
                "entity_count": len(entities),
                "ambiguous_prop_names": sorted(ambiguous_names),
                "unbound": unbound,
                "counts": dict(counter),
                "distinct_slot_names": {k: sorted(v) for k, v in name_distinct.items()},
                "examples": examples,
            },
            ensure_ascii=False,
            indent=2,
            default=list,
        )
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(blob)
        print(f"\n全量 JSON 已写入 {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="全量 JSON 输出路径")
    asyncio.run(run(parser.parse_args().out))
