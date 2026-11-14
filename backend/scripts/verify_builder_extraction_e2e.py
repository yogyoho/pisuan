"""E2E：实体构建器「AI 提取 → 采纳 → 落库 → remap」链路验证（真实 DB，模型 mock）。

对应 docs/vibe/2026-11-14-实体构建器P0重构实施.md §3「真实栈 E2E 脚本」：
  合成文档 → extract_entities_from_document（mock LLM 响应，其余全是生产代码）
  → 三态比对（matched / partial / new）与 grounded 证据 → save_extracted_entities
  → domain_entity_schemas（新增实体 + 追加属性定义，实例值不入库）
  → 属性改名后 _remap_waiting_review_tasks 清空失效引用并按属性名重新绑定。

模型 mock 只替换 `yuxi.models.chat.select_model`，prompt 构造、解析、比对、
保存、remap 全部走生产实现。

副作用控制：
  - save/update 会 remap 同域全部 WAITING_REVIEW 任务：脚本先快照其 source_paragraphs，
    finally 原样写回。
  - 探针实体/任务清理 + 行数指纹核对，结束零残留。

用法（api 容器内，PowerShell）：
    docker exec pisuan-localized-api-1 uv run --no-sync python /app/scripts/verify_builder_extraction_e2e.py
退出码：0=全部通过；1=存在 FAIL。
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
import uuid
from types import SimpleNamespace

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update

from yuxi.repositories.domain_entity_repository import DomainEntityRepository
from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from yuxi.services.domain_entity_service import get_entity_service
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_entity import DomainEntitySchema
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryRegionalFact,
    DomainFactoryTask,
)

PROBE_KEY = "e2e_builder_probe"
PROBE_EXISTING_PROP = "existing_metric"
PROP_NAME = "龦浊度龧"  # 生僻字属性名：避开通用域既有属性名，remap 匹配可自证
NEW_KEY = "e2e_builder_new"

DOC_CONTENT = (
    "探针文档第一段：监测断面既有指标浓度为 3.5 mg/L，趋势平稳。\n"
    f"探针文档第二段：该断面新增{PROP_NAME}，实测值为 12 NTU。\n"
    f"探针文档第三段：{PROP_NAME}连续三个月稳定，属新识别实体。\n"
)

MATCHED_TEXT = "监测断面既有指标浓度为 3.5 mg/L"
PARTIAL_TEXT = f"该断面新增{PROP_NAME}，实测值为 12 NTU"
NEW_TEXT = f"{PROP_NAME}连续三个月稳定"
FAKE_TEXT = "这段文字并不存在于文档中"

FAKE_LLM_ITEMS = [
    {
        "schema_ref": PROBE_KEY,
        "name_cn": "既有指标",
        "values": {PROBE_EXISTING_PROP: "3.5 mg/L"},
        "extracted_text": MATCHED_TEXT,
        "confidence": 0.92,
    },
    {
        "schema_ref": PROBE_KEY,
        "name_cn": PROP_NAME,
        "values": {PROBE_EXISTING_PROP: "12 NTU", PROP_NAME: "12 NTU"},
        "extracted_text": PARTIAL_TEXT,
        "confidence": 0.88,
    },
    {
        "schema_ref": "__proposal__",
        "entity_key": "E2E-Builder New",
        "name_cn": "E2E探针新实体",
        "category": "natural_env",
        # 属性名与探针实体不同，避免 remap 精确匹配时产生歧义
        "values": {"龦岸线龧": "8.6 km"},
        "extracted_text": NEW_TEXT,
        "confidence": 0.81,
    },
    {
        "schema_ref": PROBE_KEY,
        "name_cn": "既有指标",
        "values": {PROBE_EXISTING_PROP: "9.9 mg/L"},
        "extracted_text": FAKE_TEXT,
        "confidence": 0.95,
    },
]

_checks: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _checks.append((bool(ok), f"{label}{('：' + detail) if detail else ''}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return bool(ok)


class _FakeModel:
    """最小 LLM 替身：返回预置 JSON，验证 prompt→解析→比对→保存链路。"""

    def __init__(self, items: list[dict]):
        self.items = items

    async def call(self, prompt: str):  # noqa: ARG002 - 仅作链路占位
        return SimpleNamespace(content=json.dumps(self.items, ensure_ascii=False))


async def fingerprint() -> dict[str, int]:
    async with pg_manager.get_async_session_context() as session:
        entities = (
            await session.execute(
                select(func.count())
                .select_from(DomainEntitySchema)
                .where(DomainEntitySchema.domain_code == GENERAL_DOMAIN_CODE)
            )
        ).scalar_one()
        facts = (await session.execute(select(func.count()).select_from(DomainFactoryRegionalFact))).scalar_one()
        tasks = (await session.execute(select(func.count()).select_from(DomainFactoryTask))).scalar_one()
    return {"entities": entities, "facts": facts, "tasks": tasks}


async def snapshot_pending_tasks() -> dict[str, list]:
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.execute(
                select(DomainFactoryTask.id, DomainFactoryTask.source_paragraphs).where(
                    DomainFactoryTask.status == "WAITING_REVIEW"
                )
            )
        ).all()
    return {r.id: copy.deepcopy(r.source_paragraphs or []) for r in rows}


async def restore_pending_tasks(snapshot: dict[str, list], skip_task_id: str) -> int:
    restored = 0
    async with pg_manager.get_async_session_context() as session:
        for task_id, paragraphs in snapshot.items():
            if task_id == skip_task_id:
                continue
            await session.execute(
                update(DomainFactoryTask).where(DomainFactoryTask.id == task_id).values(source_paragraphs=paragraphs)
            )
            restored += 1
    return restored


async def slot_ref(task_id: str) -> str:
    async with pg_manager.get_async_session_context() as session:
        paragraphs = (
            await session.execute(
                select(DomainFactoryTask.source_paragraphs).where(DomainFactoryTask.id == task_id)
            )
        ).scalar_one_or_none()
    try:
        return paragraphs[0]["template"]["slots"][0].get("entity_ref", "")
    except (IndexError, KeyError, TypeError):
        return "<missing>"


async def main() -> int:
    entity_service = get_entity_service()
    entity_repo = DomainEntityRepository()
    task_id = str(uuid.uuid4())

    async with pg_manager.get_async_session_context() as session:
        domain = (
            await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.code == GENERAL_DOMAIN_CODE))
        ).scalar_one_or_none()
    if domain is None:
        print("FATAL：未找到通用域，无法执行 E2E")
        return 1

    pre_fp = await fingerprint()
    pending_snapshot = await snapshot_pending_tasks()
    print(f"前置指纹: {pre_fp}；快照同域 WAITING_REVIEW 任务 {len(pending_snapshot)} 个")

    await entity_service.create_entity(
        {
            "entity_key": PROBE_KEY,
            "name_cn": "E2E提取探针实体",
            "category": "natural_env",
            "value_type": "String",
            "description": "E2E 提取链路探针，验证后删除",
            "properties": [
                {
                    "key": PROBE_EXISTING_PROP,
                    "name_cn": "既有指标",
                    "value_type": "String",
                }
            ],
        }
    )

    paragraphs = [
        {
            "id": "e2e-builder-p1",
            "title": "E2E探针段落",
            "content": f"监测断面{PROP_NAME}为12NTU。",
            "classify_type": "text",
            "template": {
                "generalized": f"监测断面{{{{{PROP_NAME}}}}}为12NTU。",
                "slots": [
                    {"name": PROP_NAME, "type": "NumericValue", "entity_ref": ""},
                ],
                "metadata": {"chapter": "3", "tags": []},
            },
        }
    ]
    async with pg_manager.get_async_session_context() as session:
        session.add(
            DomainFactoryTask(
                id=task_id,
                domain_id=domain.id,
                file_name="e2e_probe_builder_extract.pdf",
                storage_path="e2e/probe/builder_extract.pdf",
                status="WAITING_REVIEW",
                uploaded_by="e2e_probe",
                source_paragraphs=paragraphs,
                template_metadata={},
                region_key=None,
                region_label=None,
                scope=None,
                project_name=None,
                knowledge_base_id=None,
            )
        )
    print(f"合成待审核任务: {task_id}")

    try:
        # mock 只替换模型选择，其余全部生产代码
        import yuxi.models.chat as chat_module

        chat_module.select_model = lambda model_spec=None: _FakeModel(FAKE_LLM_ITEMS)  # noqa: ARG005

        print("\n===== 提取：三态比对 + 证据校验 =====")
        extraction = await entity_service.extract_entities_from_document(DOC_CONTENT, GENERAL_DOMAIN_CODE)
        comparison = extraction["comparison"]
        statuses = [item.get("_status") for item in comparison]
        check(
            statuses == ["matched", "partial", "new", "matched"],
            "S1 三态比对（matched / partial / new / matched）",
            f"{statuses}",
        )
        check(
            [item.get("grounded") for item in comparison] == [True, True, True, False],
            "S2 grounded 证据校验：文档外的片段判为无证据",
            f"{[item.get('grounded') for item in comparison]}",
        )
        partial = comparison[1]
        added_keys = [p["key"] for p in partial["_diff"]["add_properties"]]
        check(
            added_keys == [PROP_NAME],
            "S3 partial 只补充未定义属性（既有属性不重复计入）",
            f"{added_keys}",
        )
        proposal = comparison[2]["_proposed_entity"]
        check(
            proposal["entity_key"] == NEW_KEY and not proposal["problems"],
            "S4 new 提案：entity_key 归一化且无阻断问题",
            f"{proposal['entity_key']} problems={proposal['problems']}",
        )
        coverage = extraction["coverage"]
        check(
            coverage["content_chars"] == len(DOC_CONTENT)
            and coverage["scanned_chars"] == len(DOC_CONTENT)
            and coverage["truncated"] is False,
            "S5 coverage 如实报告字符数与截断状态",
            f"{coverage}",
        )

        print("\n===== 采纳落库：实例值不入 schema =====")
        saved = await entity_service.save_extracted_entities(comparison, GENERAL_DOMAIN_CODE)
        check(
            saved["inserted"] == 1
            and saved["updated_entities"] == 1
            and saved["properties_added"] == 1
            and saved["unchanged"] == 1
            and len(saved["rejected"]) == 1,
            "S6 保存结果：新增 1 实体 / 补 1 属性 / 不变 1 / 拒绝 1（无证据）",
            f"{saved}",
        )
        check(
            "原文未找到" in saved["rejected"][0]["reason"],
            "S7 拒绝原因写明无原文证据",
            saved["rejected"][0]["reason"],
        )

        probe = await entity_repo.get_by_key(PROBE_KEY, domain_code=GENERAL_DOMAIN_CODE)
        appended = next((p for p in (probe.properties if probe else []) if p.get("key") == PROP_NAME), None)
        check(
            probe is not None and appended is not None and "sample_value" not in appended,
            "S8 追加的是属性定义，实例值（sample_value）未写入 schema",
            f"{appended}",
        )

        new_entity = await entity_repo.get_by_key(NEW_KEY, domain_code=GENERAL_DOMAIN_CODE)
        check(
            new_entity is not None and (new_entity.extra_meta or {}).get("source") == "ai_extract",
            "S9 新实体落库且来源标记 ai_extract",
            f"entity_id={new_entity.entity_id if new_entity else None}",
        )

        print("\n===== remap：属性定义 → 待审核任务 entity_ref =====")
        ref_bound = await slot_ref(task_id)
        check(
            ref_bound == f"{PROBE_KEY}.{PROP_NAME}",
            "S10 保存后 remap 绑定属性 key（不再用 name_cn 作第二段）",
            f"{ref_bound!r}",
        )

        print("\n===== remap：属性改名后失效引用清空并重新绑定 =====")
        renamed_props = [
            ({**p, "key": "turbidity"} if p.get("key") == PROP_NAME else p)
            for p in ((probe.properties if probe else []) or [])
        ]
        await entity_service.update_entity(PROBE_KEY, {"properties": renamed_props})
        ref_renamed = await slot_ref(task_id)
        check(
            ref_renamed == f"{PROBE_KEY}.turbidity",
            "S11 属性改名后 remap 清空旧 key 并按 name_cn 重新绑定新 key",
            f"{ref_renamed!r}",
        )
    finally:
        print("\n===== 清理 =====")
        restored = await restore_pending_tasks(pending_snapshot, skip_task_id=task_id)
        print(f"  还原其它 pending 任务段落 {restored} 行")
        async with pg_manager.get_async_session_context() as session:
            await session.execute(sa_delete(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
        print(f"  删除合成任务 {task_id}")
        for key in (PROBE_KEY, NEW_KEY):
            ent = await entity_repo.get_by_key(key, domain_code=GENERAL_DOMAIN_CODE) or await entity_repo.get_by_key(key)
            if ent is not None:
                await entity_repo.delete(ent.entity_id)
                print(f"  删除探针实体 {key}")
        post_fp = await fingerprint()
        clean = post_fp == pre_fp
        print(f"  收尾指纹: {post_fp} {'== 前置 ✓ 零残留' if clean else '!= 前置 ' + str(pre_fp) + ' ✗'}")
        if not clean:
            _checks.append((False, "清理后指纹与前置不一致，存在残留"))
        if pg_manager.async_engine is not None:
            await pg_manager.async_engine.dispose()

    print("\n===== 结果汇总 =====")
    failed = [label for ok, label in _checks if not ok]
    print(f"通过 {len(_checks) - len(failed)}/{len(_checks)}")
    for label in failed:
        print(f"  FAIL: {label}")
    if failed:
        return 1
    print("实体构建器提取链路 E2E 全部通过：三态比对 + 证据校验 → 采纳落库（实例值不入库）→ remap 绑定/改名刷新。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
