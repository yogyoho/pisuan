# Route A：stages 字段清单 → 属性候选 → 与通用域实体库对账（只读）。
#
# stages/*.json 的 forms.fields 形态 {name: 英文key, label: 中文名, type, required, note}
# 与实体属性 {key, name_cn, value_type} 同构。本脚本把字段映射为属性候选后按
# name_cn 精确 → 包含 两级与 52 实体对账，输出三清单：
#   covered   字段已被现有实体属性覆盖（对账锚点，附实体归属）
#   gaps      字段无实体属性承接（缺口候选，按表单族分组；表单族 label 亦尝试映射实体）
#   unanchored 实体库中零字段锚定的实体（清理/降级候选，供人工裁定）
#
# 用法（api 容器内；stages 文件经 SKILLS_DIR 挂载）：
#   python -m scripts.governance.reconcile_corpus_fields --out /tmp/route-a.json
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# stages 文件相对技能 references 根的定位：容器走 skill-sources 挂载（shared 布局），
# 宿主走仓库相对路径，两处择一可用。
CANDIDATE_ROOTS = [
    Path("/app/skill-sources/shared/coal-eia-writer/references/stages"),
    Path(__file__).resolve().parents[2] / "package/yuxi/agents/skills/buildin/coal-eia-writer/references/stages",
]

TYPE_MAP = {
    "string": ("String", None),
    "bool": ("Boolean", None),
    "int": ("Integer", None),
    "number": ("Float", None),
    "object": ("Object", None),
    "array<object>": ("Object", None),
    "array<string>": ("List", None),
}


def map_value_type(t: str) -> tuple[str, list[str]]:
    """stages 字段 type → (value_type, enum_options)。"""
    t = (t or "").strip()
    if t.startswith("enum:"):
        options = [x.strip() for x in t[5:].split("|") if x.strip()]
        return ("Enum", options)
    if t in TYPE_MAP:
        return TYPE_MAP[t]
    return ("String", None)


def find_stage_files() -> list[Path]:
    for root in CANDIDATE_ROOTS:
        if root.is_dir():
            return sorted(root.glob("*.json"))
    raise FileNotFoundError(f"stages 目录未找到，尝试过: {[str(p) for p in CANDIDATE_ROOTS]}")


def load_field_candidates() -> list[dict]:
    """展开全部 forms.fields 为属性候选，携带表单族与阶段上下文。"""
    out: list[dict] = []
    for path in find_stage_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        stage_id = str(data.get("stage_id") or path.stem)
        for fam_key, fam in (data.get("forms") or {}).items():
            fam_label = str(fam.get("label") or fam_key)
            for fl in fam.get("fields") or []:
                label = str(fl.get("label") or "").strip()
                if not label:
                    continue
                vt, options = map_value_type(str(fl.get("type") or ""))
                out.append(
                    {
                        "stage": stage_id,
                        "family_key": fam_key,
                        "family_label": fam_label,
                        "key": str(fl.get("name") or "").strip(),
                        "name_cn": label,
                        "value_type": vt,
                        "enum_options": options,
                        "required": bool(fl.get("required")),
                    }
                )
    return out


async def run(out_path: str | None) -> None:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)

    # 属性索引：name_cn → [(entity_key, prop)]
    prop_index: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    entity_by_name: dict[str, dict] = {}
    for e in entities:
        entity_by_name[str(e.get("name_cn") or "").strip()] = e
        for p in e.get("properties") or []:
            if isinstance(p, dict) and p.get("name_cn"):
                prop_index[str(p["name_cn"]).strip()].append((e["entity_key"], p))

    covered, gaps = [], []
    anchored_entities: set[str] = set()
    for cand in load_field_candidates():
        name = cand["name_cn"]
        hits = prop_index.get(name)
        level = None
        if hits:
            level = "exact"
        else:
            # 包含匹配（双向），唯一归属才收，多归属标记歧义
            contains = [
                (ek, p)
                for pn, lst in prop_index.items()
                for ek, p in lst
                if (pn in name or name in pn) and min(len(pn), len(name)) >= 3
            ]
            if contains:
                hits = contains
                level = "contains"
        if hits and level:
            owners = sorted({ek for ek, _ in hits})
            anchored_entities.update(owners)
            covered.append({**cand, "match": level, "owners": owners, "ambiguous": len(owners) > 1})
        else:
            gaps.append(cand)

    unanchored = [
        {
            "entity_key": e["entity_key"],
            "name_cn": e.get("name_cn"),
            "category": e.get("category"),
            "prop_count": len(e.get("properties") or []),
        }
        for e in entities
        if e["entity_key"] not in anchored_entities
    ]

    # 缺口按 表单族×阶段 分组，族本身尝试映射实体（label 与实体名互含）
    gap_groups: dict[str, dict] = {}
    for g in gaps:
        gk = f"{g['stage']}::{g['family_label']}"
        grp = gap_groups.setdefault(gk, {"family_label": g["family_label"], "suggested_entity": None, "fields": []})
        grp["fields"].append({k: g[k] for k in ("key", "name_cn", "value_type", "enum_options", "required")})
    for grp in gap_groups.values():
        fam = grp["family_label"]
        for ename, e in entity_by_name.items():
            if ename and (ename in fam or fam in ename) and min(len(ename), len(fam)) >= 3:
                grp["suggested_entity"] = e["entity_key"]
                break

    # 摘要
    n_fields = len(covered) + len(gaps)
    amb = [c for c in covered if c["ambiguous"]]
    print("=" * 60)
    print(f"stages 字段候选 {n_fields} 个（covered {len(covered)} / gaps {len(gaps)}）")
    print(f"covered 中多实体归属歧义 {len(amb)} 个")
    print(f"锚定实体 {len(anchored_entities)} / {len(entities)}；零锚定实体 {len(unanchored)} 个:")
    for u in unanchored:
        print(f"  {u['entity_key']}（{u['name_cn']}）cat={u['category']} props={u['prop_count']}")
    print(f"\n缺口分组 {len(gap_groups)} 组（组内字段数 TOP10）:")
    for gk, grp in sorted(gap_groups.items(), key=lambda kv: -len(kv[1]["fields"]))[:10]:
        hint = grp["suggested_entity"] or "（无实体映射）"
        print(f"  [{len(grp['fields']):3d}] {gk} → {hint}")

    if out_path:
        blob = json.dumps(
            {
                "field_candidates": len(covered) + len(gaps),
                "covered": covered,
                "gap_groups": gap_groups,
                "unanchored_entities": unanchored,
            },
            ensure_ascii=False,
            indent=2,
        )
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(blob)
        print(f"\n全量 JSON 已写入 {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="全量 JSON 输出路径")
    asyncio.run(run(parser.parse_args().out))
