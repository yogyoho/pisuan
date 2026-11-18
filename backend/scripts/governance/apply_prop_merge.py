# 属性归并执行工具：按确认清单做「重复属性合并 + 改名 + synonym 沉淀 + 引用改写」。
#
# spec JSON 结构（.tmp/prop-merge-spec.json）：
# {
#   "ops": [
#     {"entity_key": "land_occupation",
#      "canonical_key": "land_occupation_type",        # 保留的规范属性 key
#      "add_synonyms": ["主要占地类型", "项目占地类型"],  # 沉淀到规范属性的同义词
#      "remove": ["main_land_occupation_type", "project_land_occipation_types"]},  # 删除的重复属性 key
#     {"entity_key": "engineering_site_scheme",
#      "rename": [{"key": "main_land_occupation_type", "name_cn": "占地类型",
#                  "add_synonyms": ["主要占地类型"]}]}
#   ]
# }
#
# 流程：备份受影响实体属性 → 引用改写（旧引用→规范引用：待审任务槽位/学习模板/pps）
#       → 删重复属性并给规范属性挂同义词 → 属性改名（key 不动，仅 name_cn+synonyms）
#       → remap → 复核旧引用残留（非 0 即 exit 1）
# 用法（api 容器内）：
#   python -m scripts.governance.apply_prop_merge --spec /tmp/prop-merge-spec.json            # dry-run
#   python -m scripts.governance.apply_prop_merge --spec /tmp/prop-merge-spec.json --apply
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def run(spec_path: str, apply: bool) -> None:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        DomainFactoryRepository,
    )
    from yuxi.services.domain_entity_service import DomainEntityService
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    ops = spec.get("ops") or []
    svc = DomainEntityService()
    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)
    by_key = {e["entity_key"]: e for e in entities}

    # 备份
    backup = {op["entity_key"]: by_key[op["entity_key"]].get("properties") for op in ops if op["entity_key"] in by_key}
    ts = time.strftime("%Y%m%d-%H%M%S")
    Path(f"/tmp/prop-merge-backup-{ts}.json").write_text(
        json.dumps(backup, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"备份 {len(backup)} 实体属性 → /tmp/prop-merge-backup-{ts}.json")

    # 引用改写映射：{旧完整引用: 新完整引用}
    ref_map: dict[str, str] = {}
    for op in ops:
        ek = op["entity_key"]
        ck = op.get("canonical_key")
        if not ck:
            continue  # rename 型 op 无引用改写（key 不动）
        for old_key in op.get("remove") or []:
            ref_map[f"{ek}.{old_key}"] = f"{ek}.{ck}"

    if apply and ref_map:
        # 1) 待审任务槽位
        tasks = await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE)
        n_tasks = 0
        for row in tasks:
            paragraphs = row.get("source_paragraphs") or []
            touched = False
            for para in paragraphs:
                t = para.get("template") if isinstance(para, dict) else None
                if not isinstance(t, dict):
                    continue
                for s in t.get("slots") or []:
                    if isinstance(s, dict) and s.get("entity_ref") in ref_map:
                        s["entity_ref"] = ref_map[s["entity_ref"]]
                        touched = True
            if touched:
                await DomainFactoryRepository().update_task(row["id"], {"source_paragraphs": paragraphs})
                n_tasks += 1
        print(f"任务槽位引用改写：{n_tasks} 个任务")
        # 2) 学习模板
        from yuxi.services.domain_factory_service import get_domain_factory_service

        n_lt = await get_domain_factory_service().repo.rewrite_learned_template_slot_refs(ref_map)
        print(f"学习模板引用改写：{n_lt} 条")
        # 3) pps
        from sqlalchemy import select
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryReportPps

        n_pps = 0
        from yuxi.storage.postgres.manager import pg_manager as _pg

        async with _pg.get_async_session_context() as session:
            rows = (await session.execute(select(DomainFactoryReportPps))).scalars().all()
            for row in rows:
                ek = str(row.entity_key or "")
                if ek in ref_map:
                    row.entity_key = ref_map[ek]
                    n_pps += 1
            await session.commit()
        print(f"pps 引用改写：{n_pps} 条")

    # 属性结构变更
    from sqlalchemy import select as _select
    from yuxi.storage.postgres.models_domain_factory import DomainFactoryReportPps as _Pps

    for op in ops:
        ek = op["entity_key"]
        ent = await repo.get_by_id_or_key(ek)
        if ent is None:
            print(f"  FAIL {ek}: 实体不存在")
            continue
        d = ent.to_dict()
        props = d.get("properties") or []
        canonical_key = op.get("canonical_key")

        if apply and op.get("remove"):
            removed = [p["key"] for p in props if p.get("key") in op["remove"]]
            props = [p for p in props if p.get("key") not in op["remove"]]
            for p in props:
                if p.get("key") == canonical_key:
                    syns = p.get("synonyms") or []
                    for s in op.get("add_synonyms") or []:
                        if s not in syns:
                            syns.append(s)
                    p["synonyms"] = syns
            await svc.update_entity(ek, {"properties": props}, force=True)
            print(f"  {ek}: 合并删除 {removed}，规范属性 {canonical_key} 挂同义词 {op.get('add_synonyms')}")

        for rn in op.get("rename") or []:
            hit = next((p for p in props if p.get("key") == rn["key"]), None)
            if hit is None:
                print(f"  FAIL rename {ek}.{rn['key']}: 属性不存在")
                continue
            hit["name_cn"] = rn["name_cn"]
            syns = hit.get("synonyms") or []
            for s in rn.get("add_synonyms") or []:
                if s not in syns:
                    syns.append(s)
            hit["synonyms"] = syns
            await svc.update_entity(ek, {"properties": props}, force=True)
            print(f"  {ek}.{rn['key']}: 改名 → {rn['name_cn']}，同义词 +{rn.get('add_synonyms')}")

    # 复核旧引用残留
    leftovers = 0
    async with pg_manager.get_async_session_context() as session:
        rows = (await session.execute(_select(_Pps))).scalars().all()
        leftovers += sum(1 for row in rows if str(row.entity_key or "") in ref_map)
    for row in await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
        for para in row.get("source_paragraphs") or []:
            t = para.get("template") if isinstance(para, dict) else None
            if not isinstance(t, dict):
                continue
            for s in t.get("slots") or []:
                if isinstance(s, dict) and s.get("entity_ref") in ref_map:
                    leftovers += 1
    print(f"旧引用残留: {leftovers}")
    if leftovers and apply:
        print("!! 存在残留，请排查")
        sys.exit(1)
    if not apply:
        print("[dry-run] 未写库；复核基于当前库态")

    if apply:
        from yuxi.services.domain_factory_service import get_domain_factory_service

        n = await get_domain_factory_service().remap_waiting_review_tasks(GENERAL_DOMAIN_CODE)
        print(f"remap 刷新 {n} 个任务")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().spec, parser.parse_args().apply))
