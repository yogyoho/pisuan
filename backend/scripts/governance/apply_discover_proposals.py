# discover 待确认建议采纳：按用户最大保留口径，把 add_property/new_entity 提案落进实体库。
#
# 数据源：/tmp/discover-backfill-raw.json（回填 LLM 建议全集），按回填脚本同口径校验后：
#   add_property  去重 (target_entity, 属性名) → 属性并入目标实体（key 取提案或确定性兜底，
#                 实体内唯一化带后缀；value_type: number→Float/string→String/boolean→Boolean）
#   new_entity    按 name_cn 对账活跃实体：命中 → 其属性提案折入该实体的 add_property；
#                 未命中 → 按提案建实体（分类非法兜底 project_basic）
#   invalid_bind  保持 pending（写入 metadata，人工处理）
# 流程：重算校验 → 建实体 → 并属性（走 DomainEntityService 正常编辑流）→ 残余 pending 写回
#       各任务 metadata → 供 discover_bind_backfill --apply 复跑解析新属性完成绑定。
#
# 用法（api 容器内）：
#   python -m scripts.governance.apply_discover_proposals           # dry-run 摘要
#   python -m scripts.governance.apply_discover_proposals --apply
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RAW_PATH = Path("/tmp/discover-backfill-raw.json")
KEY_OK = re.compile(r"^[a-z][a-z0-9_]*$")
VALID_CATS = {"project_basic", "natural_env", "env_quality", "sensitive_target", "measures_regulation", "impact_assessment"}
VT_MAP = {"number": "Float", "integer": "Integer", "string": "String", "boolean": "Boolean", "float": "Float"}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def fallback_key(seed: str) -> str:
    return "f_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


async def run(apply: bool) -> None:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        DomainFactoryRepository,
    )
    from yuxi.services.domain_entity_service import DomainEntityService
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)
    svc = DomainEntityService()

    valid: dict[str, dict[str, str]] = {}
    names_idx: dict[str, str] = {}
    for e in entities:
        ek = e["entity_key"]
        valid[ek] = {str(p.get("key")): norm(p.get("name_cn")) for p in (e.get("properties") or []) if isinstance(p, dict) and p.get("key")}
        names_idx[norm(e.get("name_cn"))] = ek

    adds: dict[tuple[str, str], dict] = {}
    new_entities: dict[str, dict] = {}
    pendings: list[dict] = []
    stats: dict[str, int] = defaultdict(int)

    for slot_name, item in raw.items():
        st = str(item.get("suggestion_type") or "")
        if st == "bind_slot":
            ek, _, pk = str(item.get("entity_ref") or "").partition(".")
            if pk in valid.get(ek, {}):
                stats["bind_ok_untouched"] += 1
            else:
                pendings.append({"slot_name": slot_name, "reason": f"bind_ref 不存在: {item.get('entity_ref')}"})
                stats["invalid_bind_pending"] += 1
        elif st == "add_property":
            ek = str(item.get("target_entity_key") or "")
            prop = item.get("proposed_property") or {}
            name_cn = norm(prop.get("name_cn"))
            if not name_cn:
                stats["add_prop_empty_name"] += 1
                continue
            if ek not in valid:
                stats["add_target_missing"] += 1
                pendings.append({**item, "slot_name": slot_name, "reason": f"目标实体不存在: {ek}"})
                continue
            if name_cn in set(valid[ek].values()):
                stats["add_prop_already_exists"] += 1  # 校验漏网（norm 口径），无需加
                continue
            k = (ek, name_cn)
            rec = adds.setdefault(
                k, {"ek": ek, "name_cn": str(prop.get("name_cn") or "").strip(), "key": norm(prop.get("key")), "vt": VT_MAP.get(str(prop.get("value_type") or "string").lower(), "String"), "unit": str(prop.get("unit") or ""), "support": 0}
            )
            rec["support"] += 1
            stats["add_prop_accepted"] += 1
        elif st == "new_entity":
            ne_key = norm(item.get("entity_key"))
            ne_name = norm(item.get("name_cn"))
            target = names_idx.get(ne_name) or (ne_key if ne_key in valid else None)
            if target:
                # 已有同名/同键实体 → 属性提案折入该实体
                for p in item.get("properties") or []:
                    pn = norm(p.get("name_cn"))
                    if pn and pn not in set(valid[target].values()):
                        k = (target, pn)
                        rec = adds.setdefault(k, {"ek": target, "name_cn": str(p.get("name_cn") or "").strip(), "key": norm(p.get("key")), "vt": VT_MAP.get(str(p.get("value_type") or "string").lower(), "String"), "unit": str(p.get("unit") or ""), "support": 0})
                        rec["support"] += 1
                stats["new_entity_folded"] += 1
            else:
                new_entities.setdefault(ne_key or fallback_key(ne_name), {"name_cn": str(item.get("name_cn") or "").strip(), "category": str(item.get("category") or "") if str(item.get("category") or "") in VALID_CATS else "project_basic", "props": item.get("properties") or [], "slots": [slot_name]})
                stats["new_entity_create"] += 1

    print("=" * 60)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"  待并属性: {len(adds)} 条，跨 {len({v['ek'] for v in adds.values()})} 实体；拟建实体: {len(new_entities)}")

    if not apply:
        for (ek, n), rec in sorted(adds.items(), key=lambda kv: -kv[1]["support"])[:8]:
            print(f"  [dry] {ek} += {rec['name_cn']}({rec['vt']}, x{rec['support']})")
        return

    # 1) 建实体
    n_created = 0
    for ek, ne in new_entities.items():
        props = []
        for p in ne["props"]:
            pn = str(p.get("name_cn") or "").strip()
            if not pn:
                continue
            pk = norm(p.get("key"))
            if not KEY_OK.match(pk):
                pk = fallback_key(ek + pn)
            props.append({"key": pk, "name_cn": pn, "value_type": VT_MAP.get(str(p.get("value_type") or "string").lower(), "String"), "unit": str(p.get("unit") or ""), "required": False})
        try:
            await svc.create_entity({"entity_key": ek, "name_cn": ne["name_cn"], "category": ne["category"], "value_type": "Object", "description": "discover 流 new_entity 提案采纳（2026-11-16）", "properties": props})
            n_created += 1
            valid[ek] = {p["key"]: norm(p["name_cn"]) for p in props}
        except Exception as e:  # noqa: BLE001
            ek2 = ek + "_b"
            try:
                await svc.create_entity({"entity_key": ek2, "name_cn": ne["name_cn"], "category": ne["category"], "value_type": "Object", "description": "discover 流 new_entity 提案采纳（2026-11-16，key 占用改 _b）", "properties": props})
                n_created += 1
                valid[ek2] = {p["key"]: norm(p["name_cn"]) for p in props}
            except Exception:  # noqa: BLE001
                print(f"  FAIL create {ek}: {str(e)[:100]}")
    print(f"新建实体 {n_created}")

    # 2) 并属性（每实体一次 update）
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for (ek, _), rec in adds.items():
        by_entity[ek].append(rec)
    n_added = 0
    for ek, recs in by_entity.items():
        ent = await DomainEntityRepository().get_by_id_or_key(ek)
        if ent is None:
            print(f"  FAIL add {ek}: 实体不存在")
            continue
        current = ent.to_dict().get("properties") or []
        cur_names = {norm(p.get("name_cn")) for p in current if isinstance(p, dict)}
        cur_keys = {str(p.get("key") or "").casefold() for p in current if isinstance(p, dict)}
        fresh = []
        for rec in recs:
            if norm(rec["name_cn"]) in cur_names:
                continue
            pk = rec["key"] if KEY_OK.match(rec["key"]) else fallback_key(ek + rec["name_cn"])
            while pk.casefold() in cur_keys:
                pk = pk + "_2"
            cur_keys.add(pk.casefold())
            cur_names.add(norm(rec["name_cn"]))
            fresh.append({"key": pk, "name_cn": rec["name_cn"], "value_type": rec["vt"], "unit": rec["unit"], "required": False})
        if fresh:
            await svc.update_entity(ek, {"properties": current + fresh}, force=True)
            n_added += len(fresh)
    print(f"并入属性 {n_added} 条（跨 {len(by_entity)} 实体）")

    # 3) 残余 pending 写回各任务 metadata
    tasks = await DomainEntityRepository().list_usage_pending_tasks(GENERAL_DOMAIN_CODE)
    for row in tasks:
        detail = await DomainFactoryRepository().get_task(row["id"])
        d = detail.to_dict() if hasattr(detail, "to_dict") else detail
        meta = d.get("template_metadata") or {} if isinstance(d, dict) else {}
        await DomainFactoryRepository().update_task(row["id"], {"template_metadata": {**meta, "entity_proposals": pendings, "discovery_status": "completed"}})
    print(f"残余 pending {len(pendings)} 条写回 metadata")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="落库（默认 dry-run）")
    asyncio.run(run(parser.parse_args().apply))
