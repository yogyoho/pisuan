# Route B 批次1：project_eia 语料普查——LLM 逐切片抽取实体/属性候选（只读，可断点续跑）。
#
# 对 samples_bank/project_eia_underground + project_eia_openpit 的每个章节切片：
#   结构感知采样（≤30K 全文；超长取 标题大纲+表格行+正文开头，cap 30K）→ LLM 抽取
#   「数据对象 + 属性(name_cn/type/unit/samples)」→ 逐切片落盘 JSON（重跑跳过已成功切片）
# → 聚合：按 (对象, 属性名) 合并计数、对账现有实体属性（db-exact / new-prop / new-object）。
#
# 用法（api 容器内）：
#   python -m scripts.governance.induce_entities_from_corpus --stride 35   # 试点：每35片取1片
#   python -m scripts.governance.induce_entities_from_corpus               # 全量 212 切片
#   python -m scripts.governance.induce_entities_from_corpus --merge-only  # 仅聚合已有产出
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BANK = Path("/app/skill-sources/shared/coal-eia-writer/references/samples_bank")
SUBS = ("project_eia_underground", "project_eia_openpit")
OUT_DIR = Path("/tmp/route-b")
MODEL_SPEC = "openai2:agnes-3.0-flash"
MAX_CHARS = 30000
CONCURRENCY = 4

SYSTEM_TMPL = """你是环评报告领域的语料普查员。任务：从给定的报告章节切片中，抽取文中实际出现的「领域数据对象」
（描述一类业务事物的名词，如：采空区、风井、矸石山、声环境敏感点、沉陷预测参数）及其属性（对象需要填写的字段）。

规则：
1. 只抽取语料中实际出现、可填写/可度量的对象与属性；属性名尽量沿用报告原文措辞（中文），不要臆造。
2. 数值属性必须给单位（unit 字段，无单位填 null）。
3. 每个属性附最多 3 个语料中的样例值（字符串化，截断到 40 字）。
4. 对象若与下方「现有实体清单」明显对应，existing 填该实体 key；否则 existing 填 null，并给建议英文 key（snake_case）与中文名。
5. type 取值：String/Number/Boolean/Enum/Object/List；枚举属性把候选取值放进 samples。
6. 表格列头是属性的重要来源；同一对象下属性名不要重复。
7. 输出严格 JSON（无 markdown 围栏、无解释文字）：
{"objects":[{"key":"snake_case或null","name_cn":"对象中文名","existing":"实体key或null","properties":[{"name_cn":"属性中文名","type":"String","unit":"...或null","samples":["..."]}]}]}

现有实体清单（通用域）：
{anchor}"""


def sample_slice(text: str, cap: int = MAX_CHARS) -> str:
    """超长切片的结构感知采样：标题大纲 + 表格行优先 + 正文开头。"""
    if len(text) <= cap:
        return text
    lines = text.splitlines()
    headings = [l for l in lines if l.lstrip().startswith("#")]
    tables = [l for l in lines if l.lstrip().startswith("|")]
    out, budget = [], cap * 2 // 3
    for l in headings + tables:
        if sum(len(x) + 1 for x in out) > budget:
            break
        out.append(l)
    prose = text[: cap // 3]
    return (
        "\n".join(out)
        + "\n\n-- 正文开头截选 --\n"
        + prose
        + f"\n\n（原文 {len(text)} 字，以上为标题大纲+表格行+正文开头的截选）"
    )


def slice_key(rel: str) -> str:
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12] + ".json"


def content_text(resp) -> str:
    """兼容多形态返回：纯字符串，或 reasoning/text 块列表（zai/siliconflow）。"""
    c = resp.content
    if isinstance(c, str):
        return c
    parts = []
    for blk in c:
        if isinstance(blk, str):
            parts.append(blk)
        elif isinstance(blk, dict) and blk.get("type") == "text":
            parts.append(str(blk.get("text") or ""))
    return "\n".join(parts)


def parse_objects(content: str) -> list[dict] | None:
    s = content.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        data = json.loads(s[i : j + 1])
    except json.JSONDecodeError:
        return None
    objs = data.get("objects")
    return objs if isinstance(objs, list) else None


async def extract_one(model, rel: str, path: Path, anchor: str) -> dict:
    text = sample_slice(path.read_text(encoding="utf-8", errors="replace"))
    last_err = None
    for attempt in range(3):
        try:
            resp = await model.ainvoke(
                [
                    ("system", SYSTEM_TMPL.replace("{anchor}", anchor)),
                    ("human", f"章节切片：{rel}\n\n{text}"),
                ]
            )
            objs = parse_objects(content_text(resp))
            if objs is not None:
                return {"rel": rel, "status": "ok", "objects": objs}
            last_err = "json parse fail"
        except Exception as e:  # noqa: BLE001 — 逐切片容错，失败记录后继续
            last_err = f"{type(e).__name__}: {e}"
        await asyncio.sleep(2 * (attempt + 1))
    return {"rel": rel, "status": "error", "error": str(last_err)[:200], "objects": []}


async def merge(out_dir: Path) -> None:
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE

    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)
    db_prop_names = {
        (e["entity_key"], str(p.get("name_cn") or "").strip())
        for e in entities
        for p in e.get("properties") or []
        if isinstance(p, dict)
    }
    db_entity_names = {str(e.get("name_cn") or "").strip(): e["entity_key"] for e in entities}
    active_keys = {e["entity_key"] for e in entities}

    def clean(s) -> str:
        v = str(s or "").strip()
        return "" if v.lower() in ("null", "none") else v

    agg: dict[tuple[str, str], dict] = {}
    n_ok = n_err = 0
    for f in sorted((out_dir / "slices").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") != "ok":
            n_err += 1
            continue
        n_ok += 1
        for obj in d.get("objects") or []:
            existing = clean(obj.get("existing"))
            # 模型幻觉 key 防线：existing 必须命中活跃实体库，否则降级为新对象提案
            if existing and existing not in active_keys:
                existing = ""
            ek = existing or clean(obj.get("key")) or f"new::{clean(obj.get('name_cn'))}"
            kind = "existing" if existing else "new"
            if kind == "new" and clean(obj.get("name_cn")) in db_entity_names:
                ek, kind = db_entity_names[clean(obj.get("name_cn"))], "existing"
            for prop in obj.get("properties") or []:
                name = clean(prop.get("name_cn"))
                if not name:
                    continue
                rec = agg.setdefault(
                    (ek, name),
                    {
                        "obj_key": ek,
                        "obj_kind": kind,
                        "obj_name": obj.get("name_cn"),
                        "prop": name,
                        "type": prop.get("type"),
                        "units": [],
                        "samples": [],
                        "n_slices": 0,
                    },
                )
                rec["n_slices"] += 1
                unit = str(prop.get("unit") or "").strip()
                if unit and unit not in rec["units"]:
                    rec["units"].append(unit)
                for s in (prop.get("samples") or [])[:3]:
                    s = str(s)[:40]
                    if s and s not in rec["samples"] and len(rec["samples"]) < 6:
                        rec["samples"].append(s)

    for rec in agg.values():
        if rec["obj_kind"] == "existing" and (rec["obj_key"], rec["prop"]) in db_prop_names:
            rec["status"] = "db-exact"
        elif rec["obj_kind"] == "existing":
            rec["status"] = "new-prop"
        else:
            rec["status"] = "new-object"

    records = sorted(agg.values(), key=lambda r: -r["n_slices"])
    by_status = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print("=" * 60)
    print(f"切片 ok {n_ok} / error {n_err}；属性候选 {len(records)} 条：{by_status}")
    print("\n高频候选 TOP25（跨切片次数）:")
    for r in records[:25]:
        print(
            f"  [{r['n_slices']:3d}] {r['obj_key']}.{r['prop']}  {r['status']:10s}"
            f" type={r['type']} unit={'/'.join(r['units'][:2]) or '-'} 样例={r['samples'][:2]}"
        )
    blob = json.dumps(
        {"slices_ok": n_ok, "slices_error": n_err, "candidates": records},
        ensure_ascii=False,
        indent=2,
    )
    (out_dir / "candidates.json").write_text(blob, encoding="utf-8", newline="\n")
    print(f"\n聚合已写入 {out_dir / 'candidates.json'}")


async def run(args) -> None:
    from pisuan.models.chat import load_chat_model
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from pisuan.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)
    anchor = "\n".join(f"- {e['entity_key']}（{e.get('name_cn')}）" for e in entities)

    files = []
    for sub in SUBS:
        files += sorted((BANK / sub).rglob("*.md"))
    if args.stride > 1:
        files = files[:: args.stride]
    slices_dir = OUT_DIR / "slices"
    slices_dir.mkdir(parents=True, exist_ok=True)

    if not args.merge_only:

        def is_done(rel: str) -> bool:
            f = slices_dir / slice_key(rel)
            if not f.exists():
                return False
            try:
                return json.loads(f.read_text(encoding="utf-8")).get("status") == "ok"
            except Exception:  # noqa: BLE001 — 损坏/失败检查点视为未完成，重抽
                return False

        todo = [(str(p.relative_to(BANK)), p) for p in files if not is_done(str(p.relative_to(BANK)))]
        print(f"切片 {len(files)} 个，待抽取 {len(todo)}（并发 {args.concurrency}，模型 {args.model}）")
        model = load_chat_model(args.model)
        sem = asyncio.Semaphore(args.concurrency)

        async def worker(rel, path):
            async with sem:
                r = await extract_one(model, rel, path, anchor)
                (slices_dir / slice_key(rel)).write_text(
                    json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
                )
                mark = "." if r["status"] == "ok" else "E"
                print(mark, flush=True)
                return r

        results = await asyncio.gather(*(worker(rel, p) for rel, p in todo))
        n_err = sum(1 for r in results if r["status"] != "ok")
        print(f"\n本轮抽取完成：成功 {len(results) - n_err} / 失败 {n_err}")

    await merge(OUT_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stride", type=int, default=1, help="每 N 片取 1 片（试点用）")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--model", default=MODEL_SPEC)
    parser.add_argument("--merge-only", action="store_true", help="跳过抽取，仅聚合")
    asyncio.run(run(parser.parse_args()))
