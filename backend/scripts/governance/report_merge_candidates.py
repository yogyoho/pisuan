# 实体归并候选报告（只读）：找出「A 的同义词 = B 的名字」与「属性集大幅重合」的实体对，
# 供人工裁定归并方向（canonical 吸收 + 引用改写 + 软删 + name_cn 沉淀为 synonym）。
#
# 归并候选两类信号：
#   syn-hit   A.synonyms 归一化后命中 B.name_cn —— 用户定义的语义等价，最强信号
#   overlap   两实体属性名集合重合率 ≥0.6 且同分类 —— Route B 批量归纳的同义拆分残留
# 每对附：双方属性数、槽位引用数、pps 引用数、建议 canonical（引用多者，同数时属性多者）。
#
# 用法（api 容器内）：
#   python -m scripts.governance.report_merge_candidates                 # stdout 摘要
#   python -m scripts.governance.report_merge_candidates --out /tmp/merge-candidates.json
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


async def run(out_path: str | None) -> None:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)
    by_key = {e["entity_key"]: e for e in entities}
    name_to_key = {norm(e.get("name_cn")): e["entity_key"] for e in entities}

    # 引用面：槽位头计数 + pps entity_key 计数
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

    def refs(ek: str) -> int:
        return slot_refs.get(ek, 0) + pps_refs.get(ek, 0)

    def prop_count(ek: str) -> int:
        return len(by_key[ek].get("properties") or [])

    # ---- 信号 1：synonym 命中其他实体名 ----
    syn_pairs: dict[tuple[str, str], list[str]] = {}
    for e in entities:
        for syn in e.get("synonyms") or []:
            target = name_to_key.get(norm(syn))
            if target and target != e["entity_key"]:
                pair = tuple(sorted((e["entity_key"], target)))
                syn_pairs.setdefault(pair, []).append(f"{e['entity_key']} 的别名「{syn}」= {target} 的名字")

    # ---- 信号 2：属性集重合 ≥0.6 且同分类 ----
    def prop_names(e: dict) -> set[str]:
        return {norm(p.get("name_cn")) for p in (e.get("properties") or []) if isinstance(p, dict) and p.get("name_cn")}

    overlap_pairs: list[dict] = []
    for i, a in enumerate(entities):
        na = prop_names(a)
        if len(na) < 4:  # 属性太少时重合率不稳定
            continue
        for b in entities[i + 1 :]:
            if a.get("category") != b.get("category"):
                continue
            nb = prop_names(b)
            if len(nb) < 4:
                continue
            inter = len(na & nb)
            ratio = inter / min(len(na), len(nb))
            if ratio >= 0.6:
                overlap_pairs.append(
                    {
                        "a": a["entity_key"],
                        "b": b["entity_key"],
                        "ratio": round(ratio, 2),
                        "inter": inter,
                    }
                )
    overlap_pairs.sort(key=lambda d: -d["ratio"])

    def suggest(ka: str, kb: str) -> str:
        ra, rb = refs(ka), refs(kb)
        if ra != rb:
            return ka if ra > rb else kb
        return ka if prop_count(ka) >= prop_count(kb) else kb

    print("=" * 60)
    print(f"信号 1（别名=他名，最强）: {len(syn_pairs)} 对")
    for (ka, kb), why in list(syn_pairs.items())[:12]:
        print(f"  {ka} + {kb} → 建议 canonical={suggest(ka, kb)}  [{' | '.join(why[:2])}]")
    print(f"\n信号 2（属性集重合≥0.6 同分类）: {len(overlap_pairs)} 对")
    for d in overlap_pairs[:12]:
        ka, kb = d["a"], d["b"]
        print(
            f"  {ka}({prop_count(ka)}属性/{refs(ka)}引用) + {kb}({prop_count(kb)}属性/{refs(kb)}引用)"
            f" 重合 {d['inter']} 条({d['ratio']:.0%}) → 建议 canonical={suggest(ka, kb)}"
        )

    if out_path:
        payload = {
            "syn_hit_pairs": [
                {"a": ka, "b": kb, "suggested_canonical": suggest(ka, kb), "evidence": why}
                for (ka, kb), why in syn_pairs.items()
            ],
            "overlap_pairs": [
                {**d, "suggested_canonical": suggest(d["a"], d["b"])}
                for d in overlap_pairs
            ],
            "slot_refs": dict(slot_refs),
            "pps_refs": dict(pps_refs),
        }
        Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n全量 JSON 已写入 {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="全量 JSON 输出路径")
    asyncio.run(run(parser.parse_args().out))
