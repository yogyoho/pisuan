# 归一化专项校验（只读）：对通用域全部实体属性做「同义/形态」维度的体检，
# 与 audit_entity_spec（规范规则）互补——本脚本关注归一化缺口：
#   A 属性名形态：括号备注、内嵌单位、数字/字母开头、超长、英文名（翻译缺失）
#   B 跨实体同义属性名聚类：名字互含（norm 后双向包含）聚成组，列类型/单位变体
#   C 跨实体同名不同类型（引用 audit 口径）
#   D 实体级：同名/别名冲突引用（指向 audit_entity_spec / report_merge_candidates 结果）
# 输出 stdout 摘要 + --out 全量 JSON；校验结果供人工决定处理方案（本脚本不写库）。
#
# 用法（api 容器内）：
#   python -m scripts.governance.audit_normalization --out /tmp/normalization-report.json
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

# 内嵌单位片段（拉丁系，出现在中文名里即视为单位混入）
UNIT_RE = re.compile(
    r"(mg/?[a-zA-Zµ]|ug/?[a-zA-Zµ]|kg|t/a|万t|m3|km2|hm2|dB\(?A?\)?|MPa|kV|MW|L/s|cmol|S/m|µs/cm|us/cm|mg/kg|mg/m3|%$)"
)
PAREN_RE = re.compile(r"[（(][^（）()]{1,20}[）)]")
# 二字/三字泛词：作为互含连边的「短名」时不算同义信号（距离/浓度等 bridging 会把无关族串起来）
GENERIC_BRIDGE_WORDS = {
    "距离", "浓度", "深度", "高度", "面积", "时间", "名称", "编号", "位置", "厚度", "长度",
    "宽度", "数值", "数据", "参数", "情况", "内容", "类型", "标准", "结果", "项目", "备注",
    "单位", "范围", "方式", "数量", "比例", "占比", "年限", "序号", "日期", "年份", "频次",
    "周期", "速率", "等级", "类别", "编码", "地址", "总量", "含量", "规模", "投资", "指数",
    "坐标", "高程", "特征", "来源", "去向", "要求", "方法", "说明", "现状", "分布",
}
NUMBERED_RE = re.compile(r"\d+$")
LONG_NAME = 24


def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


async def run(out_path: str | None) -> None:
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE

    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)

    shape: dict[str, list] = defaultdict(list)
    all_names: dict[str, list[dict]] = defaultdict(list)  # norm 名 → 出现点
    for e in entities:
        ek = e["entity_key"]
        ent_name = str(e.get("name_cn") or "")
        for p in e.get("properties") or []:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name_cn") or "").strip()
            pk = str(p.get("key") or "").strip()
            if not name:
                continue
            ref = f"{ek}.{pk}（{ent_name}）"
            item = {
                "ref": ref,
                "name": name,
                "type": p.get("value_type"),
                "unit": p.get("unit") or "",
            }
            if PAREN_RE.search(name):
                shape["A1_paren_note"].append(item)
            if UNIT_RE.search(name):
                shape["A2_unit_in_name"].append(item)
            if re.match(r"^[0-9A-Za-z]", name):
                shape["A3_ascii_start"].append(item)
            if len(name) > LONG_NAME:
                shape["A4_too_long"].append(item)
            if name == pk:
                shape["A5_name_eq_key"].append(item)
            all_names[norm(name)].append(item)

    # ---- B：跨实体同义属性名聚类（互含即连边，union-find）----
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        # textbook 迭代 + 路径压缩：先找根，再整链拍平（上一版手写循环在特定链上死循环）
        root = x
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(x, x) != x:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    keys = list(all_names)
    for k in keys:
        parent.setdefault(k, k)
    # 连边：互含（较短方 ≥3 字）
    for i, a in enumerate(keys):
        if len(a) < 3:
            continue
        for b in keys[i + 1 :]:
            if len(b) < 3:
                continue
            if a in b or b in a:
                shorter = a if len(a) <= len(b) else b
                if shorter in GENERIC_BRIDGE_WORDS:
                    continue  # 泛词桥接：距离/浓度等短名互含不代表同义
                union(a, b)

    clusters: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        clusters[find(k)].append(k)
    # 只关心：跨 ≥2 实体 或 含 ≥2 个不同名字的组
    syn_groups = []
    for root, names in clusters.items():
        occ = [it for n in names for it in all_names[n]]
        ents = {it["ref"].split(".")[0] for it in occ}
        distinct = sorted({it["name"] for it in occ})
        if len(ents) < 2 and len(distinct) < 2:
            continue
        types = sorted({str(it["type"]) for it in occ})
        syn_groups.append(
            {
                "names": distinct,
                "n_props": len(occ),
                "n_entities": len(ents),
                "types": types,
                "units": sorted({str(it["unit"]) for it in occ if it["unit"]})[:6],
                "members": [it["ref"] for it in occ[:40]],
                "multi_type": len(types) > 1,
            }
        )
    syn_groups.sort(key=lambda g: (-(g["n_entities"] * g["n_props"]), -g["n_props"]))

    # ---- ③ 归一候选：内聚同族（共享 ≥2 字非泛词公共片段）+ 单一类型 + 非泛词成员 ----
    def common_fragment(names: list[str]) -> str | None:
        """所有名字共享的 ≥2 字非泛词子串（取最短名的子串探测）。"""
        shortest = min(names, key=len)
        seen = set()
        for i in range(len(shortest) - 1):
            for j in range(i + 2, len(shortest) + 1):
                frag = shortest[i:j]
                if len(frag) < 2 or frag in GENERIC_BRIDGE_WORDS or frag in seen:
                    continue
                seen.add(frag)
                if all(frag in n for n in names):
                    return frag
        return None

    all_entity_names: dict[str, set[str]] = defaultdict(set)
    for e in entities:
        for p in e.get("properties") or []:
            if isinstance(p, dict) and p.get("name_cn"):
                all_entity_names[e["entity_key"]].add(norm(p["name_cn"]))

    proposals = []
    for root, names in clusters.items():
        distinct = sorted(set(names))
        if len(distinct) < 2:
            continue
        occ = [it for n in names for it in all_names[n]]
        ents = {it["ref"].split(".")[0] for it in occ}
        types = {str(it["type"]) for it in occ}
        if len(ents) < 2 or len(types) > 1:
            continue
        if any(n in GENERIC_BRIDGE_WORDS for n in distinct):
            continue
        frag = common_fragment(distinct)
        if frag is None:
            continue  # 内聚性不足：传递闭包杂烩族，不出候选
        name_count = Counter(n for n in names)
        canonical = max(distinct, key=lambda n: (name_count[n], -len(n)))
        members = []
        for it in occ:
            if norm(it["name"]) == norm(canonical):
                continue
            ek = it["ref"].split(".")[0]
            collision = canonical in all_entity_names.get(ek, set())
            members.append(
                {
                    "ref": it["ref"],
                    "from": it["name"],
                    "to": canonical,
                    "action": "rename+synonym" if not collision else "skip",
                    "skip_reason": "同实体已有规范名" if collision else "",
                }
            )
        if any(m["action"] == "rename+synonym" for m in members):
            proposals.append(
                {
                    "fragment": frag,
                    "canonical": canonical,
                    "variants": [n for n in distinct if n != canonical],
                    "n_entities": len(ents),
                    "n_props": len(occ),
                    "type": sorted(types)[0],
                    "members": members,
                }
            )
    proposals.sort(key=lambda pr: (-pr["n_props"], -pr["n_entities"]))

    multi_type_names = [
        {"name": n, "types": sorted({str(it["type"]) for it in occ}), "n": len(occ)}
        for n, occ in all_names.items()
        if len({str(it["type"]) for it in occ}) > 1
    ]
    multi_type_names.sort(key=lambda d: -d["n"])

    # ---- 汇总 ----
    print("=" * 64)
    print(f"实体 {len(entities)}，属性出现点 {sum(len(v) for v in all_names.values())}，"
          f"去重属性名 {len(all_names)}")
    for rule, items in sorted(shape.items()):
        print(f"  {rule}: {len(items)} 条")
    print(f"  B 同义/同名跨实体聚类: {len(syn_groups)} 组"
          f"（其中跨类型组 {sum(1 for g in syn_groups if g['multi_type'])}）")
    print(f"  C 同名不同类型: {len(multi_type_names)} 个名字")

    print("\n-- A1 括号备注样例 --")
    for it in shape["A1_paren_note"][:6]:
        print(f"  {it['name']}  [{it['ref'].split('（')[0]}]")
    print("\n-- A2 内嵌单位样例 --")
    for it in shape["A2_unit_in_name"][:6]:
        print(f"  {it['name']}  [{it['ref'].split('（')[0]}]")
    print("\n-- B 聚类 TOP15（跨实体数×属性数排序）--")
    for g in syn_groups[:15]:
        flag = " ⚠多类型" if g["multi_type"] else ""
        print(f"  [{g['n_entities']}实体/{g['n_props']}条{flag}] {' ≈ '.join(g['names'][:5])}"
              f"  类型:{'/'.join(g['types'][:4])}")
    print("\n-- C 同名不同类型 TOP10 --")
    for d in multi_type_names[:10]:
        print(f"  {d['name']}（{d['n']} 处）: {'/'.join(d['types'])}")

    rename_n = sum(1 for pr in proposals for m in pr["members"] if m["action"] == "rename+synonym")
    print(f"\n-- ③ 归一候选（内聚同族）: {len(proposals)} 组 / 可改属性 {rename_n} 条 --")
    for pr in proposals[:12]:
        print(f"  [{pr['n_entities']}实体/{pr['n_props']}条] 片段「{pr['fragment']}」规范名={pr['canonical']}"
              f" ← {' ≈ '.join(pr['variants'][:4])}")

    if out_path:
        payload = {
            "proposals": proposals,
            "entity_count": len(entities),
            "prop_occurrences": sum(len(v) for v in all_names.values()),
            "distinct_names": len(all_names),
            "shape": {k: v for k, v in shape.items()},
            "synonym_clusters": syn_groups,
            "multi_type_names": multi_type_names,
        }
        Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n全量 JSON 已写入 {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    asyncio.run(run(parser.parse_args().out))
