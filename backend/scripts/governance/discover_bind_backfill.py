# 空槽绑定回填：复用 discover 流语义（LLM 语义绑定建议直接应用），按批量驱动覆盖全部空槽。
#
# 内建 discover_entities_task 的三道闸（≥3 段落置信度 / candidates[:50] / entities[:40]）
# 在 293 实体、3319 空槽规模下只覆盖 ~24%；本脚本保留其提示词结构与建议类型，
# 改为：全局按插槽名去重 → 50 名/批 → 全量实体目录（每实体至多 6 属性）入 prompt →
#   bind_slot   校验 (entity_key, prop_key) 真实存在后应用
#   add_property 目标实体按属性名实际已存在 → 自动转为绑定；否则记待确认（不自动建属性）
#   new_entity  记待确认（不自动建实体）
# 结果写回各任务的空槽（entity_ref 为空才写），待确认建议并入 template_metadata.entity_proposals。
# LLM 输出逐批落盘 /tmp/discover-backfill-raw.json，断点续跑。
#
# 用法（api 容器内）：
#   python -m scripts.governance.discover_bind_backfill            # dry-run：只跑 LLM 出建议报告
#   python -m scripts.governance.discover_bind_backfill --apply    # 应用绑定
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RAW_PATH = Path("/tmp/discover-backfill-raw.json")
BATCH = 50
MODEL = "openai2:agnes-2.5-flash"

CATEGORIES = """entity categories (6):
- project_basic: 基础工程实体 / natural_env: 自然环境实体 / env_quality: 环境质量与污染源实体
- sensitive_target: 敏感目标与空间实体 / measures_regulation: 措施与法规实体 / impact_assessment: 环境影响评价实体"""


def content_text(resp) -> str:
    c = resp.content
    if isinstance(c, str):
        return c
    return "\n".join(
        str(b.get("text") or "") for b in c if isinstance(b, dict) and b.get("type") == "text"
    )


def build_prompt(batch: list[dict], catalog: str) -> str:
    cand = "\n".join(
        f"- {c['name']} (类型={c['type']}, 出现{c['count']}次, 描述={c.get('description', '')[:40]}, 段落样例={'/'.join(c['titles'][:2])})"
        for c in batch
    )
    return f"""你是煤矿环评领域专家。以下是段落模板中未绑定实体的 slot 变量，需要把它们语义绑定到实体体系。

{CATEGORIES}

已有实体目录（格式：entity_key(中文名)[分类] 属性: prop_key(属性名)，每实体至多展示 6 条）:
{catalog}

候选 slot:
{cand}

请输出 JSON 数组，每个元素是以下三种之一：
1. bind_slot: slot 语义匹配到某实体的已有属性（优先；entity_ref 必须取自上面目录中出现过的 entity_key.prop_key；若该实体的正确属性未在目录中展示，用 add_property 而不是编造 prop_key）
{{"suggestion_type":"bind_slot","slot_name":"候选slot名称","entity_ref":"entity_key.prop_key","confidence":0.9}}
2. add_property: slot 属于某已有实体但目录中没展示对应属性
{{"suggestion_type":"add_property","target_entity_key":"实体key","slot_name":"候选slot名称","proposed_property":{{"key":"prop_key","name_cn":"属性名","value_type":"number|string","unit":"单位"}},"confidence":0.8}}
3. new_entity: 无可归属实体才用（慎用）
{{"suggestion_type":"new_entity","entity_key":"snake_key","name_cn":"中文名","category":"6分类之一","properties":[{{"key":"prop_key","name_cn":"属性中文","value_type":"number|string"}}],"confidence":0.8}}

要求：
- 优先 bind_slot，其次 add_property，最后 new_entity
- 每个候选 slot 必须恰好出现在一条建议中
- 严格 JSON 数组输出，无注释无围栏
"""


async def run(apply: bool, model_spec: str) -> None:
    from yuxi.models.chat import load_chat_model
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        DomainFactoryRepository,
    )
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)
    valid_props: dict[str, dict[str, str]] = {}  # ek -> {pk: name_cn}
    catalog_lines: list[str] = []
    for e in entities:
        ek = e["entity_key"]
        props = e.get("properties") or []
        pk_map = {}
        for p in props:
            if isinstance(p, dict) and p.get("key"):
                pk_map[str(p["key"])] = str(p.get("name_cn") or "")
        valid_props[ek] = pk_map
        shown = list(pk_map.items())[:10]
        prop_text = " ".join(f"{k}({v})" for k, v in shown)
        rest = f" …共{len(pk_map)}属性" if len(pk_map) > 10 else ""
        catalog_lines.append(f"- {ek}({e.get('name_cn')})[{e.get('category')}]{(' 属性: ' + prop_text + rest) if prop_text else ''}")
    catalog = "\n".join(catalog_lines)

    # 收集全部空槽（全局按名去重）
    tasks = await DomainEntityRepository().list_usage_pending_tasks(GENERAL_DOMAIN_CODE)
    slot_info: dict[str, dict] = {}
    for row in tasks:
        for para in row.get("source_paragraphs") or []:
            tmpl = para.get("template") if isinstance(para, dict) else None
            if not isinstance(tmpl, dict):
                continue
            for slot in tmpl.get("slots") or []:
                if not (isinstance(slot, dict) and not slot.get("entity_ref")):
                    continue
                name = (slot.get("name") or "").strip()
                if not name:
                    continue
                info = slot_info.setdefault(
                    name, {"name": name, "type": str(slot.get("type") or ""), "description": str(slot.get("description") or ""), "count": 0, "titles": []}
                )
                info["count"] += 1
                t = str(para.get("title") or "")[:30]
                if t and t not in info["titles"]:
                    info["titles"].append(t)
    names = sorted(slot_info.values(), key=lambda c: -c["count"])
    print(f"空槽 {sum(c['count'] for c in slot_info.values())} 个 / 去重 {len(names)} 名；实体 {len(entities)}")

    done: dict[str, dict] = {}
    if RAW_PATH.exists():
        done = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    pending_batches = [names[i : i + BATCH] for i in range(0, len(names), BATCH) if any(c["name"] not in done for c in names[i : i + BATCH])]
    print(f"LLM 批次 {len(pending_batches)} 个（模型 {model_spec}，批大小 {BATCH}）")

    model = load_chat_model(model_spec)
    stats: Counter = Counter()
    for bi, batch in enumerate(pending_batches):
        todo = [c for c in batch if c["name"] not in done]
        for attempt in range(3):
            try:
                resp = await model.ainvoke([("human", build_prompt(todo, catalog))])
                arr = json.loads(re.search(r"\[[\s\S]*\]", content_text(resp)).group())
                for item in arr:
                    n = str(item.get("slot_name") or "").strip()
                    if n and n not in done:
                        done[n] = item
                print(f"  batch {bi+1}: +{sum(1 for c in todo if c['name'] in done)}/{len(todo)}")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  batch {bi+1} attempt {attempt+1} failed: {str(e)[:90]}")
                await asyncio.sleep(3 * (attempt + 1))
        await asyncio.sleep(1.5)  # 批间缓速，降低限流概率
        RAW_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")

    # 校验建议 → 全局绑定映射
    def norm(s: str) -> str:
        return re.sub(r"\s+", "", s or "")

    def resolve_in_entity(ek: str, slot_name: str, want_exact: bool) -> str | None:
        """在指定实体属性内找回绑定：精确名 → 唯一包含（较短方≥3字）。"""
        props = valid_props.get(ek) or {}
        rev = {norm(cn): pk for pk, cn in props.items()}
        hit = rev.get(norm(slot_name))
        if hit:
            return hit
        if want_exact:
            return None
        cands = {
            pk
            for pk, cn in props.items()
            if (norm(cn) in norm(slot_name) or norm(slot_name) in norm(cn)) and min(len(norm(cn)), len(norm(slot_name))) >= 3
        }
        return next(iter(cands)) if len(cands) == 1 else None

    bind_map: dict[str, str] = {}
    pendings: list[dict] = []
    for name, item in done.items():
        st = str(item.get("suggestion_type") or "")
        if st == "bind_slot":
            ref = str(item.get("entity_ref") or "")
            ek, _, pk = ref.partition(".")
            if pk and pk in valid_props.get(ek, {}):
                bind_map[name] = ref
                stats["bind"] += 1
            else:
                # LLM 幻觉 prop_key 挽回：实体键有效时在该实体内做唯一匹配
                rec = resolve_in_entity(ek, name, want_exact=False) if ek in valid_props else None
                if rec:
                    bind_map[name] = f"{ek}.{rec}"
                    stats["bind_recovered_in_entity"] += 1
                else:
                    stats["bind_invalid_ref"] += 1
                    pendings.append({"slot_name": name, "reason": f"bind_ref 不存在: {ref}"})
        elif st == "add_property":
            ek = str(item.get("target_entity_key") or "")
            prop = item.get("proposed_property") or {}
            name_cn = str(prop.get("name_cn") or "").strip()
            hit = next((pk for pk, cn in valid_props.get(ek, {}).items() if cn.strip() == name_cn), None)
            if hit is None:
                # 精确名未命中 → 唯一包含挽回（目录只展示 6 属性，多数真已存在）
                hit = resolve_in_entity(ek, name_cn or name, want_exact=True) or resolve_in_entity(ek, name_cn or name, want_exact=False)
            if hit:
                bind_map[name] = f"{ek}.{hit}"
                stats["add_resolved_to_existing"] += 1
            else:
                pendings.append({**item, "slot_name": name})
                stats["add_pending"] += 1
        else:
            pendings.append({**item, "slot_name": name})
            stats["new_entity_pending"] += 1
    covered = sum(slot_info[n]["count"] for n in bind_map if n in slot_info)
    print("=" * 60)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"  建议可绑定槽位: {covered} / 3319；待确认建议 {len(pendings)} 条")

    if not apply:
        sample = list(bind_map.items())[:10]
        print("\n绑定样例（dry-run 不写库）:")
        for n, r in sample:
            print(f"  {n!r} → {r}")
        print(f"\n[dry-run] --apply 写回 {len(bind_map)} 个插槽名对应的空槽")
        return

    changed = 0
    for row in tasks:
        paragraphs = row.get("source_paragraphs") or []
        touched = False
        for para in paragraphs:
            tmpl = para.get("template") if isinstance(para, dict) else None
            if not isinstance(tmpl, dict):
                continue
            for slot in tmpl.get("slots") or []:
                if not (isinstance(slot, dict) and not slot.get("entity_ref")):
                    continue
                ref = bind_map.get((slot.get("name") or "").strip())
                if ref:
                    slot["entity_ref"] = ref
                    touched = True
        if touched:
            await DomainFactoryRepository().update_task(row["id"], {"source_paragraphs": paragraphs})
            changed += 1
    print(f"已写回 {changed} 个任务")

    if pendings:
        for row in tasks:
            detail = await DomainFactoryRepository().get_task(row["id"])
            d = detail.to_dict() if hasattr(detail, "to_dict") else detail
            meta = d.get("template_metadata") or {} if isinstance(d, dict) else {}
            old = meta.get("entity_proposals") or []
            await DomainFactoryRepository().update_task(
                row["id"], {"template_metadata": {**meta, "entity_proposals": old + pendings, "discovery_status": "completed"}}
            )
        print(f"待确认建议 {len(pendings)} 条已并入各任务 template_metadata.entity_proposals")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写回绑定（默认 dry-run）")
    parser.add_argument("--model", default=MODEL)
    asyncio.run(run(parser.parse_args().apply, parser.parse_args().model))
