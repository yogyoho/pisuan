# 存量实体定义《实体对象构建规范》符合性审计（只读）。
#
# 逐条对照 web/src/assets/docs/entity-construction-spec.md 的规则，输出机器可读的
# 违规清单（JSON）与引用面统计，作为治理脚本的输入。不改任何数据。
#
# 用法（api 容器内）：
#   python -m scripts.governance.audit_entity_spec                # 摘要 + 全量 JSON 打到 stdout
#   python -m scripts.governance.audit_entity_spec --out /tmp/audit.json
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
VALID_VALUE_TYPES = {"String", "Integer", "Float", "Boolean", "Enum", "Object", "List"}
LEGACY_ALIASES = {"Numeric": "Float", "Number": "Float", "Date": "String", "Text": "String"}
DIMENSIONLESS_HINTS = ("数量", "个数", "条数", "人数", "户数", "比例", "率", "指数", "序号", "年份", "年")

# 引用面来源与 learned_templates/report_pps/regional_facts 的读取口径一致（见
# DomainEntityService.get_entity_usage），审计同样只看通用域。


def norm_ref_head(ref: str) -> str:
    return ref.partition(".")[0].strip()


def audit_entity(entity: dict, categories: set[str]) -> dict:
    """单实体审计，返回 {rule: [违规明细]}。"""
    key = str(entity.get("entity_key") or "")
    props = [p for p in (entity.get("properties") or []) if isinstance(p, dict)]
    issues: dict[str, list] = defaultdict(list)

    if not KEY_RE.match(key) or len(key) > 64:
        issues["E1_entity_key_format"].append(key)
    value_type = str(entity.get("value_type") or "")
    if props and value_type != "Object":
        issues["E2_object_required"].append(value_type)
    if not props and value_type == "Object":
        issues["E3_object_without_props"].append(value_type)
    if props and str(entity.get("unit") or "").strip():
        issues["E4_unit_on_object"].append(entity.get("unit"))
    if entity.get("category") not in categories:
        issues["E5_category_unknown"].append(entity.get("category"))
    name_cn = str(entity.get("name_cn") or "").strip()
    if re.search(r"[（(].+[)）]", name_cn):
        issues["E6_name_paren_note"].append(name_cn)

    seen_keys: dict[str, str] = {}
    seen_names: dict[str, str] = {}
    for prop in props:
        pkey = str(prop.get("key") or "")
        pname = str(prop.get("name_cn") or "").strip()
        ptype = str(prop.get("value_type") or "")
        if not KEY_RE.match(pkey) or len(pkey) > 64:
            issues["P1_prop_key_format"].append(f"{pkey}({pname})")
        folded = pkey.casefold()
        if folded in seen_keys:
            issues["P2_prop_key_dup"].append(f"{pkey}≡{seen_keys[folded]}")
        else:
            seen_keys[folded] = pkey
        if ptype not in VALID_VALUE_TYPES:
            fix = LEGACY_ALIASES.get(ptype, "非法值" if ptype else "空")
            issues["P3_prop_type_invalid"].append(f"{pkey}: {ptype!r}→{fix}")
        if ptype in ("Integer", "Float") and not str(prop.get("unit") or "").strip():
            issues["P4_numeric_no_unit"].append(f"{pkey}({pname})")
        if ptype == "Enum" and not (prop.get("enum_options") or []):
            issues["P5_enum_no_options"].append(f"{pkey}({pname})")
        if ptype != "Enum" and (prop.get("enum_options") or []):
            issues["P6_options_on_non_enum"].append(f"{pkey}:{ptype}")
        if pname and pname in seen_names:
            issues["P7_dup_name_in_entity"].append(f"{pname}({pkey}≡{seen_names[pname]})")
        else:
            seen_names[pname] = pkey
        hint = str(prop.get("extraction_hint") or "").strip()
        if len(hint) > 30:
            issues["P9_hint_too_long"].append(f"{pkey}:{len(hint)}字")
        if pname.endswith("单位"):
            issues["P8_unit_split_prop"].append(f"{pkey}({pname})")
    return issues


def property_set_overlap(a: dict, b: dict) -> float:
    names_a = {str(p.get("name_cn") or "").strip() for p in a.get("properties") or [] if isinstance(p, dict)}
    names_a.discard("")
    names_b = {str(p.get("name_cn") or "").strip() for p in b.get("properties") or [] if isinstance(p, dict)}
    names_b.discard("")
    if not names_a or not names_b:
        return 0.0
    return len(names_a & names_b) / min(len(names_a), len(names_b))


async def run(out_path: str | None) -> None:
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from pisuan.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    repo = DomainEntityRepository()

    entities = await repo.list_all()
    from pisuan.repositories.domain_entity_category_repository import DomainEntityCategoryRepository

    categories = {row["code"] for row in await DomainEntityCategoryRepository().list_categories()}
    trash = await repo.list_deleted(None)

    report: dict = {
        "entity_count": len(entities),
        "trash_count": len(trash),
        "categories": sorted(categories),
        "violations": defaultdict(dict),
        "entity_level": defaultdict(list),
        "global": {},
        "references": {},
    }

    # ---- 逐实体规则 ----
    synonyms_owner: dict[str, str] = {}
    name_owner: dict[str, str] = {}
    for entity in entities:
        key = entity["entity_key"]
        issues = audit_entity(entity, categories)
        for rule, items in issues.items():
            report["violations"][rule][key] = items
        name = str(entity.get("name_cn") or "").strip()
        if name in name_owner:
            report["entity_level"]["name_dup"].append(f"{name}: {name_owner[name]} ≡ {key}")
        else:
            name_owner[name] = key
        for syn in entity.get("synonyms") or []:
            syn = str(syn).strip()
            if not syn:
                continue
            if syn in synonyms_owner:
                report["entity_level"]["synonym_conflict"].append(f"{syn}: {synonyms_owner[syn]} ≡ {key}")
            else:
                synonyms_owner[syn] = key
            if syn in name_owner and name_owner[syn] != key:
                report["entity_level"]["synonym_hits_other_name"].append(
                    f"{syn}: 实体名={name_owner[syn]}, 别名于={key}"
                )

    # ---- 属性集大幅重合（重复实体探测，阈值 0.6）----
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for entity in entities:
        by_cat[entity["category"]].append(entity)
    overlap_pairs = []
    for cat, group in by_cat.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                ratio = property_set_overlap(group[i], group[j])
                if ratio >= 0.6:
                    a, b = group[i], group[j]
                    overlap_pairs.append(
                        f"{cat}: {a['entity_key']}({a['name_cn']}) ≈ "
                        f"{b['entity_key']}({b['name_cn']}) overlap={ratio:.2f}"
                    )
    report["entity_level"]["prop_set_overlap"] = overlap_pairs

    # ---- 跨实体同名属性类型不一致 ----
    prop_type_by_name: dict[str, dict[str, int]] = defaultdict(Counter)
    for entity in entities:
        for prop in entity.get("properties") or []:
            if isinstance(prop, dict) and prop.get("key") and prop.get("name_cn"):
                prop_type_by_name[str(prop["name_cn"]).strip()][str(prop["value_type"])] += 1
    inconsistent = {name: dict(types) for name, types in prop_type_by_name.items() if len(types) > 1}
    report["global"]["prop_type_inconsistent_by_name"] = inconsistent

    # ---- 引用面（与 get_entity_usage 同源：learned_templates / pending_tasks / report_pps / regional_facts）----
    known_keys = {e["entity_key"] for e in entities}
    key_by_name = {str(e.get("name_cn") or "").strip(): e["entity_key"] for e in entities}
    prop_name_by_full: dict[str, set[str]] = defaultdict(set)
    for e in entities:
        for p in e.get("properties") or []:
            if isinstance(p, dict) and p.get("name_cn"):
                prop_name_by_full[e["entity_key"]].add(str(p["name_cn"]).strip())

    all_refs: list[str] = []
    for row in await repo.list_usage_learned_templates(GENERAL_DOMAIN_CODE):
        for slot in row.get("slots") or []:
            ref = str((slot or {}).get("entity_ref") or "").strip()
            if ref:
                all_refs.append(ref)
    pps_refs, fact_refs = [], []
    for row in await repo.list_usage_report_pps(GENERAL_DOMAIN_CODE):
        if str(row.get("entity_key") or "").strip():
            pps_refs.append(str(row["entity_key"]).strip())
    for row in await repo.list_usage_regional_facts():
        if str(row.get("entity_key") or "").strip():
            fact_refs.append(str(row["entity_key"]).strip())
    all_entity_refs = [norm_ref_head(r) for r in all_refs] + pps_refs + fact_refs

    unknown_heads = sorted({h for h in all_entity_refs if h not in known_keys})
    chinese_heads = sorted({h for h in all_entity_refs if h in key_by_name})
    # 引用后缀仍用中文名的（改名后靠 name_cn 兜底归一，不受影响，但计入规模）
    chinese_suffix = []
    for ref in all_refs:
        head, sep, suffix = ref.partition(".")
        if sep and head in known_keys and suffix and suffix in prop_name_by_full.get(head, ()):
            chinese_suffix.append(ref)

    report["references"] = {
        "slot_refs": len(all_refs),
        "pps_refs": len(pps_refs),
        "fact_refs": len(fact_refs),
        "unknown_heads": unknown_heads,
        "chinese_heads_in_refs": chinese_heads,
        "chinese_suffix_refs": sorted(set(chinese_suffix)),
        "chinese_suffix_count": len(set(chinese_suffix)),
    }

    # ---- 汇总 ----
    violations = {k: v for k, v in report["violations"].items()}
    report["violations"] = violations
    data = dict(report)
    data["violations"] = violations
    blob = json.dumps(report, ensure_ascii=False, default=lambda o: dict(o) if isinstance(o, defaultdict) else str(o))

    print("=" * 60)
    print(f"实体 {len(entities)} 个（回收站 {len(trash)}），分类字典 {len(categories)} 项")
    for rule in sorted(violations):
        n = len(violations[rule])
        total = sum(len(v) for v in violations[rule].values())
        print(f"  {rule}: {n} 实体 / {total} 处")
    el = report["entity_level"]
    for rule in ("name_dup", "synonym_conflict", "synonym_hits_other_name", "prop_set_overlap"):
        print(f"  {rule}: {len(el[rule])}")
    print(f"  prop_type_inconsistent_by_name: {len(inconsistent)}")
    refs = report["references"]
    print(f"引用面: slot={refs['slot_refs']} pps={refs['pps_refs']} facts={refs['fact_refs']}")
    print(f"  引用了未知实体头的 ref: {len(refs['unknown_heads'])}")
    print(f"  引用头是中文名的实体数: {len(refs['chinese_heads_in_refs'])}")
    print(f"  引用后缀为中文名的 ref 数: {refs['chinese_suffix_count']}")

    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(blob)
        print(f"全量 JSON 已写入 {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="全量 JSON 输出路径")
    asyncio.run(run(parser.parse_args().out))
