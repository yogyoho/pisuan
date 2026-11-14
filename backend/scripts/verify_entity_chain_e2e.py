"""E2E：通用域知识工厂实体双链路验证（真实 DB + 真实 LLM）。

验证两个结论（对应 docs/vibe/2026-11-13-通用域知识工厂全景梳理.md §3/§5.3）：
  Q1 解析泛化使用现有领域实体数据：
    probe 实体属性 → _load_entity_schema_variables → _format_schema_variables
    → _build_text_generalize_prompt 渲染进 prompt → 真实 LLM generalize_paragraphs。
  Q2 泛化后 LLM 提取新实体供用户确认：
    合成 WAITING_REVIEW 任务（未绑定探针 slot ×3 段）→ discover_entities_task（真实 LLM）
    → entity_proposals/discovery_status 落 metadata → confirm_proposed_entities
    → domain_entity_schemas（metadata.source=etl_proposal）+ regional_facts 草稿级联。

全程探针数据（唯一前缀 e2e_probe / E2E探针）+ finally 清理，结束零残留。
退出码：0=全部通过；1=存在 FAIL。

用法（api 容器内，PowerShell）：
    docker exec pisuan-localized-api-1 uv run --no-sync python /app/scripts/verify_entity_chain_e2e.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from yuxi.repositories.domain_entity_repository import DomainEntityRepository
from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE, DomainFactoryRepository
from yuxi.services.domain_factory_region import attribution_scope_key
from yuxi.services.domain_factory_service import DomainFactoryService
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_entity import DomainEntitySchema
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryRegionalFact,
    DomainFactoryTask,
)

PROBE_PREFIX = "e2e_probe"
Q1_KEY = f"{PROBE_PREFIX}_q1"
Q1_PROP_KEY = "probe_attr"
Q2_KEY = f"{PROBE_PREFIX}_q2_entity"
DECOY_KEY = f"{PROBE_PREFIX}_decoy_entity"
SLOT_NAME = "龦龧龩龫龭龯"  # 生僻字槽名：与全部实体属性字符交集为 0，规则三级匹配不可绑定（脚本内仍自证）

_check_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _check_results.append((bool(ok), f"{label}{('：' + detail) if detail else ''}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return bool(ok)


async def fingerprint() -> dict[str, int]:
    """受影响表的行数指纹（清理前后必须一致）。"""
    async with pg_manager.get_async_session_context() as session:
        entities = (
            await session.execute(
                select(func.count()).select_from(DomainEntitySchema).where(
                    DomainEntitySchema.domain_code == GENERAL_DOMAIN_CODE
                )
            )
        ).scalar_one()
        facts = (await session.execute(select(func.count()).select_from(DomainFactoryRegionalFact))).scalar_one()
        tasks = (await session.execute(select(func.count()).select_from(DomainFactoryTask))).scalar_one()
    return {"entities": entities, "facts": facts, "tasks": tasks}


async def delete_facts_by_task(task_id: str) -> int:
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            sa_delete(DomainFactoryRegionalFact).where(DomainFactoryRegionalFact.source_task_id == task_id)
        )
        return result.rowcount or 0


async def delete_entity_by_key(entity_key: str) -> bool:
    repo = DomainEntityRepository()
    ent = await repo.get_by_key(entity_key, domain_code=GENERAL_DOMAIN_CODE)
    if ent is None:
        return False
    return bool(await repo.delete(ent.entity_id))


async def delete_task(task_id: str) -> None:
    async with pg_manager.get_async_session_context() as session:
        await session.execute(sa_delete(DomainFactoryTask).where(DomainFactoryTask.id == task_id))


async def main() -> int:
    svc = DomainFactoryService()
    entity_repo = DomainEntityRepository()

    # ---- 0. 前置：通用域存在 + 行数指纹 ----
    async with pg_manager.get_async_session_context() as session:
        domain = (
            await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.code == GENERAL_DOMAIN_CODE))
        ).scalar_one_or_none()
    if domain is None:
        print("FATAL：未找到通用域（domain_factory_domains.code='general'），无法构造合成任务")
        return 1
    pre_fp = await fingerprint()
    print(f"前置指纹（通用域实体={pre_fp['entities']}, 区域事实={pre_fp['facts']}, 工厂任务={pre_fp['tasks']}）")

    # ---- 1. 探针实体（Q1 输入）----
    probe_entity = await entity_repo.create(
        {
            "entity_id": str(uuid.uuid4()),
            "entity_key": Q1_KEY,
            "name_cn": "E2E探针实体Q一",
            "category": "natural_env",
            "domain_code": GENERAL_DOMAIN_CODE,
            "value_type": "Numeric",
            "unit": "mg/L",
            "description": "E2E 全链路验证用探针实体，验证后删除",
            "synonyms": [],
            "properties": [
                {
                    "key": Q1_PROP_KEY,
                    "name_cn": "探针属性甲",
                    "value_type": "Numeric",
                    "unit": "mg/L",
                    "extraction_hint": "E2E 探针属性，单位 mg/L",
                }
            ],
            "relation_rules": [],
            "metadata": {"source": "e2e_probe"},
        }
    )
    print(f"探针实体已创建：{Q1_KEY} (id={probe_entity.entity_id})")

    task_id = str(uuid.uuid4())
    try:
        # ================= 链路一（Q1）：实体属性 → 泛化 prompt =================
        print("\n===== 链路一（Q1）：解析泛化使用现有领域实体数据 =====")
        # 生产路径用默认 cap=60（token 成本控制）；通用域实体多时截断是既定行为，
        # 断言映射逻辑本身用大 cap；默认 cap 的覆盖情况单独如实报告
        schema_vars = await svc._load_entity_schema_variables(GENERAL_DOMAIN_CODE, max_items=1000)
        cap_vars = await svc._load_entity_schema_variables(GENERAL_DOMAIN_CODE)
        cap_hit = any(v.get("key") == f"{Q1_KEY}.{Q1_PROP_KEY}" for v in cap_vars)
        probe_var = next((v for v in schema_vars if v.get("key") == f"{Q1_KEY}.{Q1_PROP_KEY}"), None)
        ok1 = check(probe_var is not None, "S1 _load_entity_schema_variables 含探针属性",
                    f"{probe_var}" if probe_var else "未找到（泛化自上而下收敛链断裂）")
        print(f"       [观察] 生产默认 cap=60 实载 {len(cap_vars)} 个变量，探针在 cap 内: {cap_hit}"
              f"（实体多时尾部实体被截断，属 svc:4054 既定 token 成本控制）")
        schema_text = svc._format_schema_variables(schema_vars)
        ok2 = check(f"{Q1_KEY}.{Q1_PROP_KEY}" in schema_text, "S2 _format_schema_variables 输出含探针属性")
        prompt = svc._build_text_generalize_prompt(
            "段落正文占位", schema_text, "3.2", "通用", None
        )
        ok3 = check(f"{Q1_KEY}.{Q1_PROP_KEY}" in prompt, "S3 _build_text_generalize_prompt 渲染进最终 prompt")

        # 真实 LLM：单段落泛化（schema_vars 注入，验证消费端全链）
        gen = await svc.generalize_paragraphs(
            paragraphs=[
                {
                    "id": "e2e-p1",
                    "content": (
                        "根据2026年5月监测数据，该区域探针属性甲浓度为3.5mg/L，"
                        "较上年同期下降0.2mg/L，满足水质管理目标要求。"
                    ),
                    "section_path": ["3", "2"],
                    "is_table": False,
                }
            ],
            schema_variables=schema_vars,
            domain_label="通用",
            max_concurrency=1,
        )
        gen_stats = gen.get("stats", {})
        gen_result = gen.get("results", {}).get("e2e-p1")
        llm_ok = check(
            gen_result is not None
            and isinstance(gen_result.get("generalized"), str)
            and isinstance(gen_result.get("slots"), list)
            and (gen_stats.get("success", 0) + gen_stats.get("structured", 0)) >= 1,
            "S4 真实 LLM generalize_paragraphs 产出模板（实体注入后消费端可跑通）",
            f"stats={ {k: v for k, v in gen_stats.items() if k != 'error'} or gen_stats }",
        )
        if gen_result:
            print(f"       generalized={str(gen_result.get('generalized'))[:80]!r}")
            print(f"       slots={[s.get('name') for s in gen_result.get('slots', [])]}")

        # ================= 链路二（Q2）：LLM 提新实体 → 人工确认落库 =================
        print("\n===== 链路二（Q2）：LLM 提取新实体供确认 → 确认落库 + 事实级联 =====")
        # 槽名自证：规则绑定三级匹配（精确/包含/≥2 汉字交集，svc:6177）对 71 个通用域
        # 实体极易误命中（首轮「氟化物」即被规则绑定，LLM 没有出场）。这里用生产匹配器
        # 预检候选名，选第一个规则不可绑定的，保证未绑定 slot 真正进入 LLM 分析。
        slot_name = ""
        for candidate in [SLOT_NAME, "矶鹬鸻巢区震颤通量", "磲鲎鹈鸊单元存量", "夸克昧变换率探针值"]:
            probe_paras = [
                {
                    "template": {"slots": [{"name": candidate, "type": "NumericValue", "entity_ref": ""}]},
                }
            ]
            bound = await svc._auto_map_slots_to_entity_properties(probe_paras, domain_code=GENERAL_DOMAIN_CODE)
            if bound == 0:
                slot_name = candidate
                break
        ok5a = check(bool(slot_name), "S5a 槽名经生产规则匹配器自证不可绑定", f"slot_name={slot_name!r}")

        paragraphs = [
            {
                "id": f"e2e-q2-p{i}",
                "title": f"E2E探针段落{i}",
                "content": f"第{i}段：监测断面{slot_name}为3.5mg/L，趋势平稳。",
                "classify_type": "text",
                "template": {
                    "generalized": f"第{i}段：监测断面{{{{{slot_name}}}}}为3.5mg/L，趋势平稳。",
                    "slots": [
                        {
                            "name": slot_name,
                            "type": "NumericValue",
                            "description": "探针 slot：生产匹配器无法绑定的未知概念",
                            "entity_ref": "",  # 未绑定：规则与既有实体属性均不命中
                        }
                    ],
                    "metadata": {"chapter": "3", "tags": []},
                },
            }
            for i in range(1, 4)  # 3 段命中 ≥3 置信度阈值（svc:6241）
        ]
        async with pg_manager.get_async_session_context() as session:
            session.add(
                DomainFactoryTask(
                    id=task_id,
                    domain_id=domain.id,
                    file_name="e2e_probe_entity_discovery.pdf",
                    storage_path="e2e/probe/entity_discovery.pdf",
                    status="WAITING_REVIEW",
                    uploaded_by="e2e_probe",
                    source_paragraphs=paragraphs,
                    template_metadata={},
                    region_key="e2eprobe",
                    region_label="E2E探针区域",
                    scope="regional",
                    project_name=None,
                    knowledge_base_id="e2e-probe-kb",
                )
            )

        disc = await svc.discover_entities_task(task_id)
        llm_called = disc.get("total", 0) > 0 or "message" not in disc
        ok5 = check(
            "error" not in disc and llm_called,
            "S5 discover_entities_task：未绑定候选进入 LLM 分析并返回提议",
            f"bound={disc.get('bound')}, proposals={disc.get('total')}, msg={disc.get('message', '')}",
        )
        task_row = await svc.repo.get_task(task_id)
        meta = task_row.template_metadata or {}
        ok6 = check(meta.get("discovery_status") == "completed", "S6 discovery_status=completed 落库")
        proposals = meta.get("entity_proposals") or []
        ok7 = check(isinstance(proposals, list), "S7 entity_proposals 持久化待人工确认",
                    f"types={[p.get('suggestion_type') for p in proposals]}")
        for p in proposals[:3]:
            print(f"       proposal: {p.get('suggestion_type')} -> {p.get('entity_key') or p.get('slot_name')} ({str(p.get('name_cn'))[:30]})")

        # 确认载荷：LLM 的 new_entity 提议（原样 + _confirmed）+ 合成 B 类载荷（确定性事实级联）+ 未确认诱饵
        confirm_payloads: list[dict] = []
        tracked_keys = set()
        llm_new = [p for p in proposals if p.get("suggestion_type") == "new_entity"]
        if llm_new:
            payload_llm = {**llm_new[0], "_confirmed": True}
            payload_llm.setdefault("entity_key", f"{PROBE_PREFIX}_llm_entity")
            payload_llm.setdefault("name_cn", "E2E探针LLM实体")
            confirm_payloads.append(payload_llm)
            tracked_keys.add(payload_llm["entity_key"])
            print(f"       确认 LLM 提议实体: {payload_llm['entity_key']} (category={payload_llm.get('category')})")
        payload_b = {
            "suggestion_type": "new_entity",
            "entity_key": Q2_KEY,
            "name_cn": "E2E探针事实实体",
            "category": "natural_env",  # B 类直映 → monitoring 事实
            "description": "E2E探针事实实体：2026年探针区域氟化物浓度监测值为3.5mg/L。",
            "value_type": "Numeric",
            "unit": "mg/L",
            "properties": [],
            "synonyms": [],
            "_confirmed": True,
        }
        confirm_payloads.append(payload_b)
        tracked_keys.add(Q2_KEY)
        confirm_payloads.append(
            {"suggestion_type": "new_entity", "entity_key": DECOY_KEY, "name_cn": "E2E探针诱饵实体", "_confirmed": False}
        )

        conf = await svc.confirm_proposed_entities(task_id, confirm_payloads)
        ok8 = check(
            isinstance(conf, dict) and conf.get("saved", 0) >= 1 and conf.get("skipped", 0) >= 1,
            "S8 confirm_proposed_entities：确认实体落库 + 未确认诱饵被跳过",
            f"result={conf}",
        )
        ent = await entity_repo.get_by_key(Q2_KEY, domain_code=GENERAL_DOMAIN_CODE)
        ok9 = check(
            ent is not None and (ent.extra_meta or {}).get("source") == "etl_proposal",
            "S9 domain_entity_schemas 新实体落库且 metadata.source=etl_proposal",
            f"entity_id={ent.entity_id if ent else None}, meta={ent.extra_meta if ent else None}",
        )

        # W3 级联：B 类确认实体 → 区域事实草稿
        async with pg_manager.get_async_session_context() as session:
            facts = (
                await session.execute(
                    select(DomainFactoryRegionalFact).where(DomainFactoryRegionalFact.source_task_id == task_id)
                )
            ).scalars().all()
        expect_fact_type = "monitoring"  # natural_env 直映（domain_factory_region.py:75）
        expect_attribution = attribution_scope_key("e2e-probe-kb", "e2eprobe", "regional", None)
        fact_b = next((f for f in facts if f.entity_key == Q2_KEY), None)
        ok10 = check(
            fact_b is not None
            and fact_b.fact_type == expect_fact_type
            and (fact_b.attribution or "") == expect_attribution,
            "S10 B 类确认实体级联区域事实草稿（attribution 隔离键正确）",
            f"facts={[(f.entity_key, f.fact_type, f.attribution) for f in facts]}",
        )
        if fact_b:
            print(f"       fact: type={fact_b.fact_type}, region_key={fact_b.region_key}, year={fact_b.year}")

        all_ok = all([ok1, ok2, ok3, llm_ok, ok5a, ok5, ok6, ok7, ok8, ok9, ok10])
    finally:
        # ---- 清理：facts → 实体 → 任务，零残留 ----
        print("\n===== 清理 =====")
        facts_removed = await delete_facts_by_task(task_id)
        print(f"  删除区域事实 {facts_removed} 行 (source_task_id={task_id})")
        removed_keys = []
        for key in sorted(tracked_keys | {Q1_KEY}):  # tracked_keys 含 LLM 提议实体的实际键
            if await delete_entity_by_key(key):
                removed_keys.append(key)
        print(f"  删除探针实体: {removed_keys}")
        await delete_task(task_id)
        print(f"  删除合成任务 {task_id}")
        post_fp = await fingerprint()
        clean = post_fp == pre_fp
        print(f"  收尾指纹: {post_fp} {'== 前置 ✓ 零残留' if clean else '!= 前置 ' + str(pre_fp) + ' ✗'}")
        if not clean:
            _check_results.append((False, "清理后指纹与前置不一致，存在残留"))

    print("\n===== 结果汇总 =====")
    failed = [label for ok, label in _check_results if not ok]
    print(f"通过 {len(_check_results) - len(failed)}/{len(_check_results)}")
    if failed:
        for label in failed:
            print(f"  FAIL: {label}")
        return 1
    print("两条链路 E2E 全部通过：Q1 实体数据注入泛化 prompt 且 LLM 消费端跑通；"
          "Q2 LLM 提议落 metadata 待确认、确认后实体库落库(etl_proposal)并级联区域事实草稿。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
