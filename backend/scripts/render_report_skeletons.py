"""条件化报告骨架渲染器（roadmap v2 spec §3.4）。

确定性纯函数，无 LLM。输入 6 维条件 + 三层源文件，输出 stage JSON 兼容骨架 +
applied_rules 留痕。属构建/交付脚本，非运行时组件。

用法:
  python backend/scripts/render_report_skeletons.py --conditions <conditions.json> \
      [--only <docx文件名>] --out <输出目录>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAYER_DIR = Path(__file__).resolve().parent.parent / "templates/coal_mining/report_skeletons"
FAMILIES = ("planning_eia", "project_eia", "post_eia", "tracking_eia")


def _when_match(when: dict, conds: dict) -> bool:
    """when 子句匹配：标量键精确相等；sensitive_targets 支持通配 '*'；policy_flags 支持成员判断。"""
    for key, want in when.items():
        have = conds.get(key)
        if key == "sensitive_targets" and want == "*":
            if not have:
                return False
        elif key == "policy_flags":
            if want not in (have or []):
                return False
        elif have != want:
            return False
    return True


def _resolve_base(family: str, conds: dict, layers: dict, seen: tuple[str, ...] = ()) -> list[str]:
    """R8 base 派生：post_eia 从 project_eia 按 openpit 条件解析后克隆。防环：seen 记录链。"""
    if family in seen:
        raise ValueError(f"base 循环引用: {seen + (family,)}")
    l1 = layers[family]["l1"]
    rules = layers["rules"]
    base_rule = next((r for r in rules if r.get("base") and r["when"].get("report_family") == family), None)
    if base_rule and base_rule["base"] != "self":
        b = base_rule["base"]
        base_conds = {**conds, "report_family": b["family"], "mine_type": b.get("mine_type")}
        order = _resolve_base(b["family"], base_conds, layers, seen + (family,))
        suffix = base_rule.get("rename_suffix", "")
        return [t + suffix if suffix else t for t in order]
    return list(l1["canonical_order"])


def _copy_ch(src: dict) -> dict:
    """layer-1 章定义 → 渲染中间体。sections 为富对象（id/title/elements/uses/slots/role）节级浅拷贝
    （嵌套只读共享），章级 key_elements/writing_patterns（seed_gen 消费面）逐字随迁。"""
    return {
        "slot_id": src.get("slot_id", ""),
        "key_elements": list(src.get("key_elements", [])),
        "writing_patterns": list(src.get("writing_patterns", [])),
        "sections": [dict(sec) for sec in src.get("sections", [])],
    }


def _apply_anchors(chapters: dict, l1: dict) -> None:
    """W2v2 spec §4.1 后置重排：在场章若 l1 optional 词条声明 insert_after，摘出重插到锚章之后。

    同锚多章按处理序稳定；锚章不在场 fail loud（禁静默）；无锚词条维持现位；
    链式锚（锚章自身被锚定）有限轮收敛，不收敛即 ValueError。
    """
    anchors = {
        t: spec_["insert_after"]
        for t, spec_ in l1.get("optional_chapters", {}).items()
        if t in chapters and spec_.get("insert_after")
    }
    if not anchors:
        return
    missing = sorted({a for a in anchors.values() if a not in chapters})
    if missing:
        raise KeyError(f"insert_after 锚章不在渲染集: {missing}")
    for _ in range(len(anchors) + 1):
        keys = list(chapters)
        changed = False
        for a in anchors:
            i = keys.index(a)
            if i != keys.index(anchors[a]) + 1:
                keys.pop(i)
                keys.insert(keys.index(anchors[a]) + 1, a)
                changed = True
        if not changed:
            return
        reordered = {k: chapters[k] for k in keys}
        chapters.clear()
        chapters.update(reordered)
    raise ValueError(f"insert_after 链不收敛: {anchors}")


def render(conds: dict, layers: dict) -> dict:
    """渲染单份骨架。conds=6 维条件；layers={family: {"l1":..., "l3":...}, "rules": [...]}."""
    family = conds["report_family"]
    l1, l3 = layers[family]["l1"], layers[family]["l3"]
    applied: list[str] = []

    order = _resolve_base(family, conds, layers)
    chapters: dict[str, dict] = {}
    for t in order:
        src = l1["chapters"].get(t, {})
        chapters[t] = _copy_ch(src)

    optional = l1.get("optional_chapters", {})
    for rule in layers["rules"]:
        if not _when_match(rule["when"], conds):
            continue
        rid = rule["id"]
        if rid == "R8" or rid == "R9":  # base 已在 _resolve_base 处理；此处仅留痕 add
            applied.append(rid)
        for t in rule.get("add", []):
            src = optional.get(t) or ({t: l1["chapters"][t]} if t in l1["chapters"] else None)
            if src is None:
                raise KeyError(f"{rid}: add 章不在 layer-1 词汇表: {t}")
            if t not in chapters:
                chapters[t] = _copy_ch(optional.get(t) or l1["chapters"][t])
            applied.append(rid)
        for t in rule.get("remove", []):
            chapters.pop(t, None)
            applied.append(rid)
        for t in rule.get("require", []):
            # require=校验性保证在场（缺失才注入）；目标必须用 canonical/optional 词汇，禁止裸名/抽象槽名
            if t not in chapters:
                src = optional.get(t) or l1["chapters"].get(t)
                if src is None:
                    raise KeyError(f"{rid}: require 章无定义: {t}")
                chapters[t] = _copy_ch(src)
            applied.append(rid)
        if "add_section_under" in rule:
            spec_ = rule["add_section_under"]
            host, template = spec_["host"], spec_["template"]
            # v1 host 匹配 = 精确或子串（R5 host 用 planning stage 全称章题规避误命中；sections 级定位留待 v2）
            host_ch = next((c for c in chapters if c == host or host in c), None)
            if host_ch:
                existing = {sec.get("title") for sec in chapters[host_ch]["sections"]}
                for target in conds.get("sensitive_targets", []):
                    sec_title = template.replace("{sensitive_target}", target)
                    if sec_title in existing:
                        continue
                    # 注入节 = 最小合法富对象；elements 留空（无语料要素依据，不臆造），role 留痕
                    chapters[host_ch]["sections"].append(
                        {
                            "id": "",
                            "title": sec_title,
                            "elements": [],
                            "uses": {"slots": [], "formulas": [], "contracts": []},
                            "slots": [],
                            "role": "rule_injected",
                        }
                    )
                    existing.add(sec_title)
            applied.append(rid)

    # layer-3 覆盖：v1 只消费 depth + tables。实测 l3 sections 短词菜单对 layer-1 定稿节题
    # 0 命中（既非 exact 也非子串全覆盖），属早期语料配置遗留——v1 渲染器不消费，
    # 保留在源文件中作为 P2（O2 全量表单作业）参考数据
    for t, cfg in l3.items():
        if t in chapters:
            chapters[t].update({k: v for k, v in cfg.items() if k in ("depth", "tables")})

    # W2v2 spec §4.1：锚点后置重排（optional 章 insert_after）——add/require 落位与规则解耦
    _apply_anchors(chapters, l1)

    # 输出章键 = slot_id 小写（CH3→ch3），与 depth_targets/{stage_id}.json 键同形——
    # 重编号 ch1..chN 会与 depth_targets 的 stage 原编号错位，seed_gen 按
    # 产物章键查表（缺章即 FAIL，禁静默默认地板），必须保持原键
    out_chapters = {}
    for t, body in chapters.items():
        ch_key = body["slot_id"].lower()
        if not ch_key:
            raise ValueError(f"章「{t}」缺 slot_id——渲染输出键必须对齐 depth_targets")
        secs = []
        for j, sec_src in enumerate(body["sections"], 1):
            sec = dict(sec_src)
            sec["id"] = f"{ch_key}_S{j:02d}"  # 节 id 前缀跟随渲染后章键
            secs.append(sec)
        out_chapters[ch_key] = {
            "title": t,
            "slot_id": body["slot_id"],
            "key_elements": body["key_elements"],
            "writing_patterns": body["writing_patterns"],
            "depth": body.get("depth", "normal"),
            "tables": body.get("tables", []),
            "sections": secs,
        }
    return {
        "version": "2.0-rendered",
        "stage_id": family,
        "generated_from": {"conditions": conds, "applied_rules": applied},
        "chapters": out_chapters,
    }


def load_layers() -> dict:
    layers: dict = {"rules": json.loads((LAYER_DIR / "rules.json").read_text(encoding="utf-8"))["rules"]}
    for fam in FAMILIES:
        layers[fam] = {
            "l1": json.loads((LAYER_DIR / f"{fam}.json").read_text(encoding="utf-8")),
            "l3": json.loads((LAYER_DIR / f"{fam}-chapters.json").read_text(encoding="utf-8")),
        }
    return layers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--conditions", required=True)
    ap.add_argument("--only", help="只渲染该 docx 文件名对应的条件")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.conditions).read_text(encoding="utf-8"))
    universe = {args.only: data["universe"][args.only]} if args.only else data["universe"]
    layers = load_layers()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for fname, conds in universe.items():
        rendered = render(conds, layers)
        slug = "".join(c if c.isalnum() else "_" for c in fname)[:60]
        (outdir / f"{slug}.json").write_text(
            json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"RENDERED {fname[:40]} chapters={len(rendered['chapters'])} rules={rendered['generated_from']['applied_rules']}"  # noqa: E501
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
