# 归一化全集清单导出（只读）：把 293 实体 / 7873 属性出现点 / 6115 去重属性名的全集，
# 连同归一化候选（属性 205 组 + 实体 22 对）与形态问题清单，打包成一份交给环评工程师
# 人工确认的 Markdown 全集 + 机器可读 JSON。
#
# 输出（容器 /tmp/normalization-inventory/）：
#   归一化全集清单.md   —— 人工确认工作稿（总览/实体全集/属性全集/属性候选/实体候选/形态问题）
#   inventory.json      —— 机器可读全量
#
# 用法（api 容器内）：
#   python -m scripts.governance.export_normalization_inventory
from __future__ import annotations

import asyncio
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT_DIR = Path("/tmp/normalization-inventory")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


async def run() -> None:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)
    by_key = {e["entity_key"]: e for e in entities}

    slot_refs: Counter = Counter()
    for row in await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
        for para in row.get("source_paragraphs") or []:
            t = para.get("template") if isinstance(para, dict) else None
            if not isinstance(t, dict):
                continue
            for s in t.get("slots") or []:
                if isinstance(s, dict) and s.get("entity_ref"):
                    slot_refs[str(s["entity_ref"]).partition(".")[0]] += 1
    pps_refs: Counter = Counter()
    for row in await repo.list_usage_report_pps(GENERAL_DOMAIN_CODE):
        ek = str(row.get("entity_key") or "").strip()
        if ek:
            pps_refs[ek.partition(".")[0]] += 1

    # 候选来源（存在才并入；不存在则该节标注未生成）
    prop_cand = json.loads(Path("/tmp/normalization-report.json").read_text(encoding="utf-8")) if Path(
        "/tmp/normalization-report.json"
    ).exists() else {}
    ent_cand = json.loads(Path("/tmp/merge-candidates.json").read_text(encoding="utf-8")) if Path(
        "/tmp/merge-candidates.json"
    ).exists() else {}

    # ---- 实体全集 ----
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in entities:
        by_cat[str(e.get("category") or "?")].append(e)

    # ---- 属性全集 ----
    prop_names: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "entities": set(), "types": Counter(), "units": Counter(), "props": [], "display": ""}
    )
    for e in entities:
        ek, ename = e["entity_key"], str(e.get("name_cn") or "")
        for p in e.get("properties") or []:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name_cn") or "").strip()
            if not name:
                continue
            rec = prop_names[norm(name)]
            if not rec["display"]:
                rec["display"] = name
            rec["count"] += 1
            rec["entities"].add(f"{ename}({ek})")
            rec["types"][str(p.get("value_type") or "?")] += 1
            unit = str(p.get("unit") or "").strip()
            if unit:
                rec["units"][unit] += 1
            rec["props"].append(f"{ek}.{p.get('key')}")

    # ---- 生成 Markdown ----
    lines: list[str] = []
    lines.append("# 实体与属性全集清单（归一化确认工作稿）")
    lines.append("")
    total_occ = sum(rec["count"] for rec in prop_names.values())
    lines.append(f"- 实体 {len(entities)} 个；属性出现点 {total_occ} 个；"
                 f"去重属性名 {len(prop_names)} 个")
    lines.append(f"- 生成方式：scripts/governance/export_normalization_inventory.py（可随时重跑刷新）")
    lines.append("- 用途：环评工程师逐条确认归一化。属性候选一节里把「确认合并」的变体标 Y；")
    lines.append("  实体候选一节里标 canonical 方向。确认结果可由开发批量应用（改名+挂同义词，引用不悬空）。")
    lines.append("")

    lines.append("## 一、实体全集（按分类）")
    lines.append("")
    for cat in sorted(by_cat):
        lines.append(f"### {cat}（{len(by_cat[cat])} 个）")
        lines.append("")
        lines.append("| 实体 key | 中文名 | 别名 | 属性数 | 槽位引用 | pps 引用 |")
        lines.append("|---|---|---|---|---|---|")
        for e in sorted(by_cat[cat], key=lambda x: str(x.get("name_cn") or "")):
            syns = "、".join(str(s) for s in (e.get("synonyms") or []))
            ek = e["entity_key"]
            lines.append(
                f"| {ek} | {e.get('name_cn')} | {syns or '-'} | {len(e.get('properties') or [])} |"
                f" {slot_refs.get(ek, 0)} | {pps_refs.get(ek, 0)} |"
            )
        lines.append("")

    lines.append("## 二、属性全集（去重名，按出现次数降序）")
    lines.append("")
    lines.append("| 属性名 | 出现 | 实体数 | 类型分布 | 单位样例 | 所在实体（前 6） |")
    lines.append("|---|---|---|---|---|---|")
    for n, rec in sorted(prop_names.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
        ents = sorted(rec["entities"])
        lines.append(
            f"| {rec['display'] or n} | {rec['count']} | {len(rec['entities'])} |"
            f" {'/'.join(f'{t}×{c}' for t, c in rec['types'].most_common(3))} |"
            f" {'、'.join(list(rec['units'])[:3]) or '-'} | {'；'.join(ents[:6])}{'…' if len(ents) > 6 else ''} |"
        )
    lines.append("")

    lines.append("## 三、属性归一化候选（内聚同族，环评师逐组确认）")
    lines.append("")
    proposals = prop_cand.get("proposals") or []
    lines.append(f"共 {len(proposals)} 组。每组：规范名（组内最高频）← 变体；确认合并的组标「合并」，")
    lines.append("不确认的组保持原样。合并动作 = 变体改名 + 原名挂 synonym + 引用改写（引用不悬空）。")
    lines.append("")
    for idx, pr in enumerate(proposals, 1):
        lines.append(f"### 候选 {idx}：规范名「{pr['canonical']}」（{pr.get('type')}，{pr['n_entities']} 实体/{pr['n_props']} 条）")
        lines.append("")
        lines.append(f"变体：{' ≈ '.join(pr['variants'])}")
        lines.append("")
        lines.append("成员：")
        for m in pr["members"]:
            mark = "N（同实体已有规范名，跳过）" if m["action"] == "skip" else " "
            lines.append(f"- [{mark}] `{m['ref']}`：{m['from']} → {m['to']}")
        lines.append("- [ ] 本组确认合并：Y/N")
        lines.append("")

    lines.append("## 四、实体归并候选（环评师确认方向）")
    lines.append("")
    syn_pairs = ent_cand.get("syn_hit_pairs") or []
    ovl_pairs = ent_cand.get("overlap_pairs") or []
    lines.append(f"### 别名=他名（{len(syn_pairs)} 对）——先核对该别名是否脏数据（是→删别名，否→归并）")
    lines.append("")
    for pr in syn_pairs:
        lines.append(f"- {pr['a']} + {pr['b']} → 建议 canonical={pr['suggested_canonical']}（证据：{'；'.join(pr['evidence'][:2])}）- [ ] Y/N")
    lines.append("")
    lines.append(f"### 同分类属性集重合 ≥0.6（{len(ovl_pairs)} 对）")
    lines.append("")
    for pr in ovl_pairs:
        lines.append(f"- {pr['a']} + {pr['b']}（重合 {pr['inter']} 条，{pr['ratio']:.0%}）→ 建议 canonical={pr['suggested_canonical']} - [ ] Y/N")
    lines.append("")

    lines.append("## 五、属性名形态问题（供顺带修订）")
    lines.append("")
    shape = prop_cand.get("shape") or {}
    for rule, label in [("A1_paren_note", "括号备注名"), ("A2_unit_in_name", "名称内嵌单位"),
                        ("A3_ascii_start", "字母数字开头"), ("A5_name_eq_key", "名=键（翻译缺失）")]:
        items = shape.get(rule) or []
        lines.append(f"### {label}（{len(items)} 条）")
        lines.append("")
        for it in items[:40]:
            lines.append(f"- {it['name']}  [{it['ref']}]")
        if len(items) > 40:
            lines.append(f"- …另有 {len(items) - 40} 条见 JSON")
        lines.append("")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "归一化全集清单.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    payload = {
        "overview": {
            "entities": len(entities),
            "prop_occurrences": sum(rec["count"] for rec in prop_names.values()),
            "distinct_names": len(prop_names),
        },
        "entities": [
            {
                "entity_key": e["entity_key"],
                "name_cn": e.get("name_cn"),
                "category": e.get("category"),
                "synonyms": e.get("synonyms") or [],
                "prop_count": len(e.get("properties") or []),
                "slot_refs": slot_refs.get(e["entity_key"], 0),
                "pps_refs": pps_refs.get(e["entity_key"], 0),
                "properties": e.get("properties") or [],
            }
            for e in sorted(entities, key=lambda x: (str(x.get("category")), str(x.get("name_cn"))))
        ],
        "prop_names": {
            n: {
                "name": rec["display"] or n,
                "count": rec["count"],
                "entities": sorted(rec["entities"]),
                "types": dict(rec["types"]),
                "units": dict(rec["units"]),
                "props": rec["props"],
            }
            for n, rec in prop_names.items()
        },
        "prop_proposals": proposals,
        "entity_candidates": ent_cand,
        "shape": shape,
    }
    (OUT_DIR / "inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(f"已生成 {OUT_DIR / '归一化全集清单.md'} 与 inventory.json")
    total_occ = sum(rec["count"] for rec in prop_names.values())
    print(f"实体 {len(entities)} | 属性出现点 {total_occ} | 去重名 {len(prop_names)}"
          f" | 属性候选 {len(proposals)} 组 | 实体候选 {len(syn_pairs)}+{len(ovl_pairs)} 对")


if __name__ == "__main__":
    asyncio.run(run())
