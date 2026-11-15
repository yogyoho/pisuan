"""Domain Factory 数据访问层 - Repository"""

from typing import Any

from sqlalchemy import func, select, text, update

from yuxi.services.domain_factory_region import (
    attribution_scope_key,
    normalize_attribution,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import (
    DomainFactoryDomain,
    DomainFactoryKnowledgeBaseAttribution,
    DomainFactoryLearnedTemplate,
    DomainFactoryOutline,
    DomainFactoryPromptConfig,
    DomainFactoryRegionalFact,
    DomainFactoryReport,
    DomainFactoryReportChapter,
    DomainFactoryReportPps,
    DomainFactoryTask,
    DomainFactoryToolUsage,
)
from yuxi.utils import hashstr, normalize_chapter_key
from yuxi.utils.datetime_utils import utc_now_naive

# 去领域化（2026-10-29）：通用域唯一常量。领域维度废弃后，所有写入与查询固定使用此值；
# domains 表冻结保留（历史外键兼容），不再暴露增删改接口。
GENERAL_DOMAIN_CODE = "general"
GENERAL_DOMAIN_NAME = "通用域"

# 中文别名 → DB code 映射（agent 可能传中文名，这里统一归一化）
_DOMAIN_ALIASES: dict[str, str] = {
    "煤矿": "coal",
    "煤炭": "coal",
    "煤炭采掘": "coal",
    "煤矿采掘": "coal",
    "化工": "chem",
    "石油化工": "chem",
    "精细化工": "chem",
    "矿产": "mineral",
    "矿物": "mineral",
    "固体矿物": "mineral",
    "交通": "transport",
    "交通运输": "transport",
    "交通工程": "transport",
}
_REPORT_TYPE_ALIASES: dict[str, str] = {
    "通用": "eia_report",
    "eia": "eia_report",
    "环境影响评价报告": "eia_report",
    "环境影响评价报告书": "eia_report",
    "环评报告": "eia_report",
    "环评": "eia_report",
    "feasibility": "feasibility_report",
    "可行性研究报告": "feasibility_report",
    "可研报告": "feasibility_report",
    "geological": "geological_exploration",
    "地质勘查报告": "geological_exploration",
    "reclamation": "land_reclamation",
    "土地复垦方案": "land_reclamation",
    "土地复垦": "land_reclamation",
    "mine_design": "mine_design",
    "矿井设计报告": "mine_design",
    "矿井设计": "mine_design",
    "safety": "safety_assessment",
    "安全评价报告": "safety_assessment",
    "安全评价": "safety_assessment",
    "water_soil": "water_soil_conservation",
    "水土保持方案": "water_soil_conservation",
    "水土保持": "water_soil_conservation",
}


def _normalize_domain(domain: str) -> str:
    """归一化 domain：中文别名 → DB code。"""
    return _DOMAIN_ALIASES.get(domain.strip(), domain.strip())


def _normalize_report_type(report_type: str) -> str:
    """归一化 report_type：中文别名 → DB code。"""
    return _REPORT_TYPE_ALIASES.get(report_type.strip(), report_type.strip())


# ---------------------------------------------------------------------------
# C-1 状态机：合法迁移表。键=当前状态，值=允许迁移到的目标集合。
# 同值重写不计为迁移；非法迁移 raise ValueError（fail-loud，不用静默兜底掩盖）。
# 已知写盘点普查（2026-11-11，FAILED_PROVIDER 已砍除——失败统一落 FAILED）：
#   service create_task/retry_task/_etl_pipeline_async(:856 GENERALIZING, 终态 WAITING_REVIEW/
#   FAILED)、commit 管线(:4563/:4580 begin_ingest/:4655/:4740/:4796/:4825
#   except 终态守卫)、reingest 管线(:5712/:5821/:5845 except 终态守卫)、repo.commit_task(:313)、
#   fail_domain_factory_etl(:6909 直写)、
#   fail_domain_factory_ingest（INGESTING→COMMIT_FAILED 直写，durable 收敛豁免）、
#   save_task_step 通用分支（service :4313 附近 update_task 透传客户端可控 status，
#   PUT /tasks/{task_id} 路由；非法值 ValueError→500，fail-loud 符合设计）。
# worker 侧误用 ValueError（非法迁移）由管线 except 终态守卫/任务中心 durable 层按失败收敛。
# 死代码豁免：update_task_form_data 的 UPLOADED→EXTRACTING 写点无调用方，未计入。
# ---------------------------------------------------------------------------
TASK_STATUS_EDGES: dict[str, set[str]] = {
    # UPLOADED→各终态/等待态：retry_task 入队失败恢复原状态（C-3）；
    # UPLOADED→GENERALIZING：断点续跑跳过解析直达泛化（retry 先重置 UPLOADED，管线跳过解析阶段）
    "UPLOADED": {
        "PARSING",
        "GENERALIZING",
        "FAILED",
        "WAITING_REVIEW",
        "COMMITTED",
        "COMMIT_FAILED",
        "COMMIT_PARTIAL",
    },
    "PARSING": {"GENERALIZING", "FAILED"},
    "GENERALIZING": {"WAITING_REVIEW", "FAILED"},
    # WAITING_REVIEW→COMMIT_FAILED：提交前校验中止（:4493 既有行为）
    "WAITING_REVIEW": {"INGESTING", "COMMIT_FAILED", "UPLOADED"},
    "INGESTING": {"COMMITTED", "COMMIT_PARTIAL", "COMMIT_FAILED"},
    "FAILED": {"UPLOADED"},
    # COMMITTED/PARTIAL/FAILED→UPLOADED：retry 现守卫允许；→INGESTING：reingest 入口
    "COMMITTED": {"UPLOADED", "INGESTING", "COMMITTED"},
    "COMMIT_PARTIAL": {"UPLOADED", "INGESTING", "COMMITTED"},
    "COMMIT_FAILED": {"UPLOADED", "INGESTING", "COMMITTED"},
}


def _validate_status_transition(current: str | None, target: str) -> None:
    """校验任务状态迁移合法性；同值重写放行，非法迁移 raise ValueError。"""
    if current == target:
        return
    allowed = TASK_STATUS_EDGES.get(current or "", set())
    if target not in allowed:
        raise ValueError(f"非法状态迁移: {current or '<None>'} → {target}")


class DomainFactoryRepository:
    """领域知识工厂数据访问层"""

    # ========== Domain ==========

    async def count_committed_tasks(self, domain_code: str) -> int:
        """统计指定领域已 COMMIT 的任务数量"""
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryDomain, DomainFactoryTask

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(DomainFactoryTask.id))
                .join(DomainFactoryDomain, DomainFactoryTask.domain_id == DomainFactoryDomain.id)
                .where(
                    DomainFactoryDomain.code == domain_code,
                    DomainFactoryTask.status == "COMMITTED",
                )
            )
            return result.scalar() or 0

    async def get_domain_by_code(self, code: str) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.code == code))
            return result.scalar_one_or_none()

    async def get_domain_by_id(self, id: int) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.id == id))
            return result.scalar_one_or_none()

    async def list_domains(self) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).order_by(DomainFactoryDomain.created_at.desc()))
            domains = result.scalars().all()
            return [d.to_dict() for d in domains]

    async def create_domain(self, code: str, name: str, description: str | None = None) -> DomainFactoryDomain:
        async with pg_manager.get_async_session_context() as session:
            domain = DomainFactoryDomain(code=code, name=name, description=description)
            session.add(domain)
        return domain

    async def get_or_create_general_domain(self) -> DomainFactoryDomain:
        """通用域行不存在则建（幂等）。去域后任务外键统一指向它。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryDomain).where(DomainFactoryDomain.code == GENERAL_DOMAIN_CODE)
            )
            domain = result.scalar_one_or_none()
            if domain is None:
                domain = DomainFactoryDomain(
                    code=GENERAL_DOMAIN_CODE,
                    name=GENERAL_DOMAIN_NAME,
                    description="去领域化后的唯一通用域",
                )
                session.add(domain)
        return domain

    async def update_domain(self, id: int, data: dict[str, Any]) -> DomainFactoryDomain | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.id == id))
            domain = result.scalar_one_or_none()
            if domain is None:
                return None
            for key, value in data.items():
                if key not in ("id",):
                    setattr(domain, key, value)
        return domain

    async def delete_domain(self, id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryDomain).where(DomainFactoryDomain.id == id))
            domain = result.scalar_one_or_none()
            if domain is None:
                return False
            await session.delete(domain)
        return True

    # ========== Report Types ==========

    async def list_report_types(self) -> list[dict[str, Any]]:
        """查询所有报告类型"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                text(
                    "SELECT code, name, domain_code, sort_order FROM report_types WHERE is_active = true ORDER BY sort_order"
                )
            )
            return [
                {"code": row.code, "name": row.name, "domain_code": row.domain_code, "sort_order": row.sort_order}
                for row in result.fetchall()
            ]

    # ========== Task ==========

    async def get_task(self, task_id: str) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
            return result.scalar_one_or_none()

    async def get_task_with_domain(self, task_id: str) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            return result.unique().scalar_one_or_none()

    async def list_pending_tasks(self, domain_id: int | None = None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            query = (
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(
                    DomainFactoryTask.status.in_(
                        ["UPLOADED", "PENDING", "PARSING", "EXTRACTING", "GENERALIZING", "WAITING_REVIEW", "FAILED"]
                    )
                )
                .order_by(DomainFactoryTask.created_at.desc())
            )
            if domain_id is not None:
                query = query.where(DomainFactoryTask.domain_id == domain_id)
            result = await session.execute(query)
            tasks = result.unique().scalars().all()
            return [t.to_summary_dict() for t in tasks]

    async def list_history_tasks(self, domain_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            query = (
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.status.in_(["COMMITTED", "REJECTED"]))
                .order_by(DomainFactoryTask.committed_at.desc().nullslast())
                .limit(limit)
            )
            if domain_id is not None:
                query = query.where(DomainFactoryTask.domain_id == domain_id)
            result = await session.execute(query)
            tasks = result.unique().scalars().all()
            return [t.to_history_dict() for t in tasks]

    async def create_task(
        self,
        task_id: str,
        domain_id: int,
        file_name: str,
        storage_path: str,
        uploaded_by: str | None = None,
    ) -> DomainFactoryTask:
        async with pg_manager.get_async_session_context() as session:
            task = DomainFactoryTask(
                id=task_id,
                domain_id=domain_id,
                file_name=file_name,
                storage_path=storage_path,
                status="UPLOADED",
                uploaded_by=uploaded_by,
            )
            session.add(task)
        return task

    async def update_task(self, task_id: str, data: dict[str, Any]) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            target_status = data.get("status")
            if target_status is not None:
                _validate_status_transition(task.status, target_status)
            for key, value in data.items():
                if key not in ("id",):
                    setattr(task, key, value)
        return task

    async def commit_task(
        self, task_id: str, reviewer: str | None = None, ingest_task_id: str | None = None
    ) -> DomainFactoryTask | None:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            _validate_status_transition(task.status, "COMMITTED")
            task.status = "COMMITTED"
            task.committed_at = utc_now_naive()
            # [pisuan-custom] W3 兜底：提交时仍无归属判定 → project（最保守；已有值不动）
            if task.scope is None:
                task.scope = "project"
            if reviewer:
                task.reviewer = reviewer
            if ingest_task_id:
                task.ingest_task_id = ingest_task_id
        return task

    async def begin_ingest(
        self,
        task_id: str,
        reviewer: str | None = None,
        ingest_task_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> DomainFactoryTask | None:
        """C-1：入库链入口，落 INGESTING 中间态并锁定目标库归属。"""
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(DomainFactoryTask.id == task_id)
            )
            task = result.unique().scalar_one_or_none()
            if task is None:
                return None
            _validate_status_transition(task.status, "INGESTING")
            if knowledge_base_id:
                await self._assert_kb_attribution_compatible_in_session(
                    session,
                    kb_id=knowledge_base_id,
                    task_id=task_id,
                    region_key=task.region_key,
                    scope=task.scope,
                    project_name=task.project_name,
                )
            task.status = "INGESTING"
            if reviewer:
                task.reviewer = reviewer
            if ingest_task_id:
                task.ingest_task_id = ingest_task_id
            if knowledge_base_id:
                task.knowledge_base_id = knowledge_base_id
            # [pisuan-custom] W3 兜底：入库时仍无归属判定 → project（最保守；已有值不动）
            if task.scope is None:
                task.scope = "project"
            if knowledge_base_id:
                await self._bind_regional_facts_for_task_in_session(session, task)
        return task

    async def assert_kb_attribution_compatible(
        self,
        kb_id: str,
        *,
        task_id: str,
        region_key: str | None,
        scope: str | None,
        project_name: str | None,
    ) -> None:
        """提交入口的早失败检查；权威检查仍在 begin_ingest 的事务内。"""
        if not kb_id:
            return
        async with pg_manager.get_async_session_context() as session:
            await self._assert_kb_attribution_compatible_in_session(
                session,
                kb_id=kb_id,
                task_id=task_id,
                region_key=region_key,
                scope=scope,
                project_name=project_name,
            )

    async def get_kb_attribution(self, kb_id: str) -> dict[str, Any]:
        """返回知识库的入库归属；未绑定返回空串，混合归属标记 mixed 供调用方降级。"""
        result: dict[str, Any] = {
            "kb_id": kb_id,
            "attribution": "",
            "bound": False,
            "mixed": False,
            "region_key": None,
            "scope": None,
            "project_name": None,
        }
        if not kb_id:
            return result
        async with pg_manager.get_async_session_context() as session:
            binding = (
                await session.execute(
                    select(DomainFactoryKnowledgeBaseAttribution).where(
                        DomainFactoryKnowledgeBaseAttribution.kb_id == kb_id
                    )
                )
            ).scalar_one_or_none()
            rows = await session.execute(
                select(
                    DomainFactoryTask.region_key,
                    DomainFactoryTask.scope,
                    DomainFactoryTask.project_name,
                )
                .where(DomainFactoryTask.knowledge_base_id == kb_id)
                .distinct()
            )
            attributions = {
                normalize_attribution(row.region_key, row.scope or "project", row.project_name) for row in rows
            }
        if binding is not None:
            binding_tuple = normalize_attribution(binding.region_key, binding.scope, binding.project_name)
            if len(attributions) > 1 or (attributions and next(iter(attributions)) != binding_tuple):
                result["mixed"] = True
                return result
            result.update(
                {
                    "bound": True,
                    "attribution": binding.attribution,
                    "region_key": binding.region_key,
                    "scope": binding.scope,
                    "project_name": binding.project_name,
                }
            )
            return result
        if not attributions:
            return result
        result["bound"] = True
        if len(attributions) > 1:
            result["mixed"] = True
            return result
        region_key, scope, project_name = next(iter(attributions))
        result.update(
            {
                "attribution": attribution_scope_key(kb_id, region_key, scope, project_name),
                "region_key": region_key,
                "scope": scope,
                "project_name": project_name,
            }
        )
        return result

    async def list_kb_attributions(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """返回一库一归属诊断列表；任务已删除的绑定标记 retained，防止误判为可复用。"""
        async with pg_manager.get_async_session_context() as session:
            bindings = (
                (
                    await session.execute(
                        select(DomainFactoryKnowledgeBaseAttribution).order_by(
                            DomainFactoryKnowledgeBaseAttribution.kb_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            task_rows = (
                await session.execute(
                    select(
                        DomainFactoryTask.knowledge_base_id,
                        DomainFactoryTask.region_key,
                        DomainFactoryTask.scope,
                        DomainFactoryTask.project_name,
                        func.count(DomainFactoryTask.id),
                    )
                    .where(DomainFactoryTask.knowledge_base_id != "")
                    .group_by(
                        DomainFactoryTask.knowledge_base_id,
                        DomainFactoryTask.region_key,
                        DomainFactoryTask.scope,
                        DomainFactoryTask.project_name,
                    )
                )
            ).all()

        by_kb: dict[str, dict[str, Any]] = {}
        for binding in bindings:
            by_kb[binding.kb_id] = {
                "kb_id": binding.kb_id,
                "attribution": binding.attribution,
                "binding_region_key": binding.region_key,
                "binding_scope": binding.scope,
                "binding_project_name": binding.project_name,
                "created_at": binding.created_at.isoformat() if binding.created_at else None,
                "updated_at": binding.updated_at.isoformat() if binding.updated_at else None,
                "task_count": 0,
                "task_attribution_count": 0,
            }
        task_groups: dict[str, set[tuple[str | None, str | None, str | None]]] = {}
        for kb_id, region_key, scope, project_name, count in task_rows:
            key = str(kb_id)
            item = by_kb.setdefault(
                key,
                {
                    "kb_id": key,
                    "attribution": attribution_scope_key(key, region_key, scope or "project", project_name),
                    "binding_region_key": None,
                    "binding_scope": None,
                    "binding_project_name": None,
                    "created_at": None,
                    "updated_at": None,
                    "task_count": 0,
                    "task_attribution_count": 0,
                },
            )
            item["task_count"] += int(count)
            task_groups.setdefault(key, set()).add(normalize_attribution(region_key, scope or "project", project_name))

        binding_tuples: dict[str, tuple[str | None, str | None, str | None]] = {
            key: normalize_attribution(item["binding_region_key"], item["binding_scope"], item["binding_project_name"])
            for key, item in by_kb.items()
            if item["binding_region_key"] is not None or item["binding_scope"] is not None
        }
        for key, item in by_kb.items():
            attrs = task_groups.get(key, set())
            item["task_attribution_count"] = len(attrs)
            binding_tuple = binding_tuples.get(key)
            if binding_tuple is None:
                item["status"] = "mixed" if len(attrs) > 1 else "legacy"
                item["status_reason"] = "知识库存在任务归属但没有持久绑定" if attrs else ""
            elif not attrs:
                item["status"] = "retained"
                item["status_reason"] = "来源任务已删除；绑定仍阻止知识库复用"
            elif len(attrs) > 1 or next(iter(attrs)) != binding_tuple:
                item["status"] = "mixed"
                item["status_reason"] = "任务归属与持久绑定不一致，或同一库包含多种归属"
            else:
                item["status"] = "bound"
                item["status_reason"] = ""

        keyword_value = (keyword or "").strip().lower()
        items = list(by_kb.values())
        if keyword_value:
            items = [
                item
                for item in items
                if keyword_value
                in " ".join(
                    [
                        item["kb_id"],
                        item["attribution"],
                        item["binding_region_key"] or "",
                        item["binding_project_name"] or "",
                    ]
                ).lower()
            ]
        if status:
            items = [item for item in items if item["status"] == status]
        items.sort(key=lambda item: (item["status"] != "mixed", item["kb_id"]))
        total = len(items)
        start = (max(1, page) - 1) * page_size
        return items[start : start + page_size], total

    async def _assert_kb_attribution_compatible_in_session(
        self,
        session,
        *,
        kb_id: str,
        task_id: str,
        region_key: str | None,
        scope: str | None,
        project_name: str | None,
    ) -> None:
        """一个知识库只允许写入一种归属；用 advisory lock 串行化并发首写。"""
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"domain-factory-kb:{kb_id}"))))
        binding_result = await session.execute(
            select(DomainFactoryKnowledgeBaseAttribution).where(DomainFactoryKnowledgeBaseAttribution.kb_id == kb_id)
        )
        binding = binding_result.scalar_one_or_none()
        current = normalize_attribution(region_key, scope or "project", project_name)
        if binding is not None:
            existing = normalize_attribution(binding.region_key, binding.scope, binding.project_name)
            if existing != current:
                raise ValueError(
                    "目标知识库已被其他归属占用："
                    f"库={kb_id} 已绑定 {existing}，当前任务归属 {current}。"
                    "请选择对应归属的知识库，或新建知识库后再入库。"
                )
        result = await session.execute(
            select(
                DomainFactoryTask.region_key,
                DomainFactoryTask.scope,
                DomainFactoryTask.project_name,
            )
            .where(
                DomainFactoryTask.knowledge_base_id == kb_id,
                DomainFactoryTask.id != task_id,
            )
            .distinct()
        )
        for row in result:
            existing = normalize_attribution(row.region_key, row.scope or "project", row.project_name)
            if existing != current:
                raise ValueError(
                    "目标知识库已被其他归属占用："
                    f"库={kb_id} 已绑定 {existing}，当前任务归属 {current}。"
                    "请选择对应归属的知识库，或新建知识库后再入库。"
                )
        if binding is None:
            session.add(
                DomainFactoryKnowledgeBaseAttribution(
                    kb_id=kb_id,
                    region_key=current[0],
                    scope=current[1] or "project",
                    project_name=current[2],
                    attribution=attribution_scope_key(kb_id, current[0], current[1] or "project", current[2]),
                )
            )

    async def delete_task(self, task_id: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                return False
            await session.delete(task)
        return True

    async def list_pending_tasks_by_domain(self, domain_code: str) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .join(DomainFactoryDomain, DomainFactoryTask.domain_id == DomainFactoryDomain.id)
                .where(
                    DomainFactoryDomain.code == domain_code,
                    DomainFactoryTask.status == "WAITING_REVIEW",
                )
            )
            tasks = result.unique().scalars().all()
            return [t.to_summary_dict() for t in tasks]

    # ========== Learned Templates ==========

    async def upsert_learned_template(
        self,
        domain_code: str,
        chapter: str,
        generalized: str,
        slots: list,
        slot_signature: str,
        sample_original: str | None = None,
        extra_meta: dict | None = None,
        report_type_code: str | None = None,
        attribution: str = "",
    ) -> int | None:
        async with pg_manager.get_async_session_context() as session:
            conditions = [
                DomainFactoryLearnedTemplate.domain_code == domain_code,
                DomainFactoryLearnedTemplate.chapter == chapter,
                DomainFactoryLearnedTemplate.slot_signature == slot_signature,
                DomainFactoryLearnedTemplate.attribution == attribution,
            ]
            if report_type_code:
                conditions.append(DomainFactoryLearnedTemplate.report_type_code == report_type_code)
            result = await session.execute(select(DomainFactoryLearnedTemplate).where(*conditions))
            existing = result.scalar_one_or_none()

            if existing is None:
                template = DomainFactoryLearnedTemplate(
                    domain_code=domain_code,
                    report_type_code=report_type_code or "通用",
                    chapter=chapter,
                    generalized=generalized,
                    slots=slots,
                    slot_signature=slot_signature,
                    sample_original=sample_original,
                    extra_meta=extra_meta,
                    attribution=attribution,
                )
                session.add(template)
                await session.flush()  # W3：聚合需要自增 id（session 内取出，避免 expire 后取值）
                template_id: int | None = template.id
            else:
                template_id = existing.id
                existing.source_count += 1
                if len(generalized) > len(existing.generalized or ""):
                    existing.generalized = generalized
                if sample_original and len(sample_original) > len(existing.sample_original or ""):
                    existing.sample_original = sample_original
                if extra_meta:
                    existing.extra_meta = extra_meta
        return existing.id if existing else template_id

    async def increment_learned_template_match_counts(self, template_ids: list[int]) -> int:
        """批量自增学习模板 match_count（ETL 标题命中留痕，bug-353）。"""
        if not template_ids:
            return 0
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                update(DomainFactoryLearnedTemplate)
                .where(DomainFactoryLearnedTemplate.id.in_(template_ids))
                .values(match_count=DomainFactoryLearnedTemplate.match_count + 1)
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def record_tool_usage(
        self,
        tool_name: str,
        *,
        domain: str | None = None,
        report_type: str | None = None,
        args_summary: dict | None = None,
        result_count: int = 0,
        source: str | None = None,
    ) -> None:
        """记一条工具取用台账（W0 埋点）。失败上抛，由调用方决定是否吞。"""
        async with pg_manager.get_async_session_context() as session:
            session.add(
                DomainFactoryToolUsage(
                    tool_name=tool_name,
                    domain=domain,
                    report_type=report_type,
                    args_summary=args_summary or {},
                    result_count=result_count,
                    source=source,
                )
            )

    # ========== Outline ==========

    async def upsert_outline(
        self,
        *,
        domain_code,
        report_type_code,
        canonical_chapter_key,
        chapter_id=None,
        chapter_title=None,
        purpose=None,
        overview=None,
        key_points=None,
        content_requirements=None,
        regulations=None,
        entity_bindings=None,
        writing_example=None,
        writing_hints=None,
        expected_tables=None,
        expected_charts=None,
        expected_formulas=None,
        expected_figures=None,
        source_task_ids=None,
        source_count=1,
        prose_based_on_source_count=None,
        attribution="",
    ) -> DomainFactoryOutline:
        # canonical 归一化单一收口：带编号/含空白 key 统一归一后入库（bug-4167）
        canonical_chapter_key = normalize_chapter_key(canonical_chapter_key) or canonical_chapter_key
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryOutline).where(
                    DomainFactoryOutline.domain_code == domain_code,
                    DomainFactoryOutline.report_type_code == report_type_code,
                    DomainFactoryOutline.canonical_chapter_key == canonical_chapter_key,
                    DomainFactoryOutline.attribution == attribution,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = DomainFactoryOutline(
                    domain_code=domain_code,
                    report_type_code=report_type_code or "通用",
                    canonical_chapter_key=canonical_chapter_key,
                    chapter_id=chapter_id,
                    chapter_title=chapter_title,
                    purpose=purpose,
                    overview=overview,
                    key_points=key_points or [],
                    content_requirements=content_requirements or [],
                    regulations=regulations or [],
                    entity_bindings=entity_bindings or [],
                    writing_example=writing_example,
                    writing_hints=writing_hints,
                    expected_tables=expected_tables or [],
                    expected_charts=expected_charts or [],
                    expected_formulas=expected_formulas or [],
                    expected_figures=expected_figures or [],
                    source_task_ids=source_task_ids or [],
                    source_count=source_count,
                    prose_based_on_source_count=prose_based_on_source_count,
                    attribution=attribution,
                )
                session.add(row)
            else:
                # Tier1 单报告：直接覆盖确定性字段；聚合合并在后续版本
                row.chapter_id = chapter_id or row.chapter_id
                row.chapter_title = chapter_title or row.chapter_title
                row.purpose = purpose or row.purpose
                row.overview = overview or row.overview
                row.key_points = key_points or row.key_points
                row.content_requirements = content_requirements or row.content_requirements
                row.regulations = regulations or row.regulations
                row.entity_bindings = entity_bindings or row.entity_bindings
                row.writing_example = writing_example or row.writing_example
                row.writing_hints = writing_hints or row.writing_hints
                row.expected_tables = expected_tables or row.expected_tables
                row.expected_charts = expected_charts or row.expected_charts
                row.expected_formulas = expected_formulas or row.expected_formulas
                row.expected_figures = expected_figures or row.expected_figures
                row.prose_based_on_source_count = prose_based_on_source_count
            await session.commit()
            return row

    async def get_outline(
        self, domain_code, report_type_code, canonical_chapter_key, *, attribution: str | None = None
    ) -> dict[str, Any] | None:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline

        async with pg_manager.get_async_session_context() as session:
            conditions = [
                DomainFactoryOutline.domain_code == domain_code,
                DomainFactoryOutline.report_type_code == report_type_code,
                DomainFactoryOutline.canonical_chapter_key == canonical_chapter_key,
            ]
            if attribution is not None:
                conditions.append(DomainFactoryOutline.attribution == attribution)
            stmt = select(DomainFactoryOutline).where(*conditions)
            if attribution is None:
                # 未指定归属的历史调用按最早行兜底，避免多归属并存后 scalar_one_or_none 抛错。
                stmt = stmt.order_by(DomainFactoryOutline.id).limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row.to_dict() if row else None

    async def list_chapter_keys(self, domain_code, report_type_code, *, attribution: str | None = None) -> list[str]:
        from yuxi.storage.postgres.models_domain_factory import DomainFactoryOutline

        async with pg_manager.get_async_session_context() as session:
            conditions = [
                DomainFactoryOutline.domain_code == domain_code,
                DomainFactoryOutline.report_type_code == report_type_code,
            ]
            if attribution is not None:
                conditions.append(DomainFactoryOutline.attribution == attribution)
            result = await session.execute(select(DomainFactoryOutline.canonical_chapter_key).where(*conditions))
            return [r[0] for r in result.all() if r[0]]

    async def backfill_template_chapter_key(
        self,
        domain_code,
        report_type_code,
        chapter_identifiers: list[str],
        canonical_chapter_key,
        *,
        attribution: str = "",
    ) -> int:
        from sqlalchemy import update

        from yuxi.storage.postgres.models_domain_factory import DomainFactoryLearnedTemplate

        if not chapter_identifiers:
            return 0
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                update(DomainFactoryLearnedTemplate)
                .where(
                    DomainFactoryLearnedTemplate.domain_code == domain_code,
                    DomainFactoryLearnedTemplate.report_type_code == report_type_code,
                    DomainFactoryLearnedTemplate.chapter.in_(chapter_identifiers),
                    DomainFactoryLearnedTemplate.attribution == attribution,
                )
                .values(canonical_chapter_key=canonical_chapter_key)
            )
            await session.commit()
            return result.rowcount or 0

    # ========== Report (writing-backbone) ==========

    async def report_exists(self, report_id) -> bool:
        """检查 report_id 是否存在于 domain_factory_reports 表。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(DomainFactoryReport.id)).where(DomainFactoryReport.id == report_id)
            )
            return (result.scalar() or 0) > 0

    async def create_report(self, *, thread_id, title, domain_code, report_type_code, kb_id, created_by) -> dict:
        import uuid

        rid = f"rpt_{hashstr(thread_id + title + str(uuid.uuid4()), 10)}"
        kb_info = await self.get_kb_attribution(str(kb_id or ""))
        if kb_info.get("mixed") or not kb_info.get("bound"):
            raise ValueError(f"报告知识库必须绑定唯一入库归属: {kb_id}")
        async with pg_manager.get_async_session_context() as session:
            row = DomainFactoryReport(
                id=rid,
                title=title,
                domain_code=domain_code,
                report_type_code=report_type_code or "通用",
                kb_id=kb_id,
                thread_id=thread_id,
                status="draft",
                created_by=created_by,
            )
            session.add(row)
            await session.commit()
        return {"id": rid, "title": title, "status": "draft"}

    async def get_report_snapshot(self, report_id) -> dict | None:
        async with pg_manager.get_async_session_context() as session:
            r = (
                await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))
            ).scalar_one_or_none()
            if not r:
                return None
            chs = (
                (
                    await session.execute(
                        select(DomainFactoryReportChapter)
                        .where(DomainFactoryReportChapter.report_id == report_id)
                        .order_by(DomainFactoryReportChapter.chapter_order)
                    )
                )
                .scalars()
                .all()
            )
            pps = (
                (
                    await session.execute(
                        select(DomainFactoryReportPps).where(DomainFactoryReportPps.report_id == report_id)
                    )
                )
                .scalars()
                .all()
            )
            return {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "report_type_code": r.report_type_code,
                "domain_code": r.domain_code,
                "kb_id": r.kb_id,
                "pps": [p.to_dict() for p in pps],
                "chapters": [c.to_dict() for c in chs],
                "registry": [
                    {"canonical_chapter_key": c.canonical_chapter_key, "title": c.title, "summary": c.summary}
                    for c in chs
                    if c.status == "done"
                ],
            }

    async def upsert_pps_param(
        self, *, report_id, entity_key, name, value, value_type, unit, source, confidence=None
    ) -> dict:
        async with pg_manager.get_async_session_context() as session:
            row = (
                await session.execute(
                    select(DomainFactoryReportPps).where(
                        DomainFactoryReportPps.report_id == report_id,
                        DomainFactoryReportPps.entity_key == entity_key,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = DomainFactoryReportPps(
                    report_id=report_id,
                    entity_key=entity_key,
                    name=name,
                    value=value,
                    value_type=value_type,
                    unit=unit,
                    source=source,
                    confidence=confidence,
                )
                session.add(row)
            else:
                row.name, row.value, row.value_type, row.unit, row.source = (
                    name,
                    value,
                    value_type,
                    unit,
                    source,
                )
                if confidence:
                    row.confidence = confidence
            await session.commit()
            return row.to_dict()

    async def upsert_chapter(
        self,
        *,
        report_id,
        canonical_chapter_key,
        chapter_order=None,
        title=None,
        content_md=None,
        summary=None,
        status="writing",
    ) -> dict:
        async with pg_manager.get_async_session_context() as session:
            row = (
                await session.execute(
                    select(DomainFactoryReportChapter).where(
                        DomainFactoryReportChapter.report_id == report_id,
                        DomainFactoryReportChapter.canonical_chapter_key == canonical_chapter_key,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = DomainFactoryReportChapter(
                    report_id=report_id,
                    canonical_chapter_key=canonical_chapter_key,
                    chapter_order=chapter_order,
                    title=title,
                    content_md=content_md,
                    summary=summary,
                    status=status,
                )
                session.add(row)
            else:
                if chapter_order is not None:
                    row.chapter_order = chapter_order
                if title is not None:
                    row.title = title
                if content_md is not None:
                    row.content_md = content_md
                if summary is not None:
                    row.summary = summary
                row.status = status
            # 报告状态推进
            rpt = (
                await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))
            ).scalar_one_or_none()
            if rpt and rpt.status == "draft":
                rpt.status = "writing"
            await session.commit()
            return row.to_dict()

    async def lookup_chapter_order(
        self, report_id, canonical_chapter_key, *, attribution: str | None = None
    ) -> int | None:
        """从 domain_factory_outlines 推导章节序：查同 domain+report_type 的 outlines，
        按 id 顺序取 canonical_chapter_key 的出现排名（1-based）；查不到则 None。"""
        async with pg_manager.get_async_session_context() as session:
            rpt = (
                await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))
            ).scalar_one_or_none()
            if not rpt:
                return None
            if attribution is None:
                attribution_info = await self.get_kb_attribution(str(rpt.kb_id or ""))
                if attribution_info.get("mixed") or not attribution_info.get("bound"):
                    return None
                attribution = str(attribution_info["attribution"])
            rows = (
                await session.execute(
                    select(DomainFactoryOutline.canonical_chapter_key)
                    .where(
                        DomainFactoryOutline.domain_code == rpt.domain_code,
                        DomainFactoryOutline.report_type_code == rpt.report_type_code,
                        DomainFactoryOutline.attribution == attribution,
                    )
                    .order_by(DomainFactoryOutline.id)
                )
            ).all()
            keys = [r[0] for r in rows]
            return (keys.index(canonical_chapter_key) + 1) if canonical_chapter_key in keys else None

    async def list_chapters(self, report_id, status_only=None) -> list[dict]:
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                select(DomainFactoryReportChapter)
                .where(DomainFactoryReportChapter.report_id == report_id)
                .order_by(DomainFactoryReportChapter.chapter_order)
            )
            if status_only:
                if isinstance(status_only, (list, tuple, set)):
                    stmt = stmt.where(DomainFactoryReportChapter.status.in_(status_only))
                else:
                    stmt = stmt.where(DomainFactoryReportChapter.status == status_only)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "canonical_chapter_key": r.canonical_chapter_key,
                    "chapter_order": r.chapter_order,
                    "title": r.title,
                    "status": r.status,
                    "content_md": r.content_md,
                    "summary": r.summary,
                }
                for r in rows
            ]

    async def mark_assembled(self, report_id):
        """将报告 status 推进为 assembled。"""
        async with pg_manager.get_async_session_context() as session:
            rpt = (
                await session.execute(select(DomainFactoryReport).where(DomainFactoryReport.id == report_id))
            ).scalar_one_or_none()
            if rpt:
                rpt.status = "assembled"
            await session.commit()

    async def list_learned_templates(self, domain_code: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = (
                select(DomainFactoryLearnedTemplate)
                .order_by(DomainFactoryLearnedTemplate.source_count.desc())
                .limit(limit)
            )
            if domain_code:
                query = query.where(DomainFactoryLearnedTemplate.domain_code == domain_code)
            result = await session.execute(query)
            templates = result.scalars().all()
            return [t.to_dict() for t in templates]

    async def list_learned_templates_by_key(
        self, domain_code, report_type_code, canonical_chapter_key=None, *, attribution: str | None = None
    ) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            stmt = select(DomainFactoryLearnedTemplate).where(
                DomainFactoryLearnedTemplate.domain_code == domain_code,
                DomainFactoryLearnedTemplate.report_type_code == report_type_code,
            )
            if canonical_chapter_key:
                stmt = stmt.where(DomainFactoryLearnedTemplate.canonical_chapter_key == canonical_chapter_key)
            if attribution is not None:
                stmt = stmt.where(DomainFactoryLearnedTemplate.attribution == attribution)
            result = await session.execute(stmt)
            return [r.to_dict() for r in result.scalars().all()]

    async def delete_learned_template(self, template_id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryLearnedTemplate).where(DomainFactoryLearnedTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()
            if template is None:
                return False
            await session.delete(template)
        return True

    async def count_learned_templates(self, domain_code: str | None = None) -> int:
        async with pg_manager.get_async_session_context() as session:
            query = select(func.count(DomainFactoryLearnedTemplate.id))
            if domain_code:
                query = query.where(DomainFactoryLearnedTemplate.domain_code == domain_code)
            result = await session.execute(query)
            return result.scalar() or 0

    # ========== Prompt Config ==========

    async def get_prompt_config(self, domain_code: str | None, prompt_type: str) -> DomainFactoryPromptConfig | None:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainFactoryPromptConfig).where(DomainFactoryPromptConfig.prompt_type == prompt_type)
            if domain_code:
                query = query.where(DomainFactoryPromptConfig.domain_code == domain_code)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def upsert_prompt_config(
        self, domain_code: str | None, prompt_type: str, template: str
    ) -> DomainFactoryPromptConfig:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryPromptConfig).where(
                    DomainFactoryPromptConfig.domain_code == domain_code,
                    DomainFactoryPromptConfig.prompt_type == prompt_type,
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                config = DomainFactoryPromptConfig(domain_code=domain_code, prompt_type=prompt_type, template=template)
                session.add(config)
            else:
                config.template = template
        return config

    async def list_prompt_configs(self, domain_code: str | None = None) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainFactoryPromptConfig)
            if domain_code:
                query = query.where(DomainFactoryPromptConfig.domain_code == domain_code)
            result = await session.execute(query)
            configs = result.scalars().all()
            return [c.to_dict() for c in configs]

    # ========== Regional Facts & Template Scope (W3) ==========

    async def insert_regional_fact(
        self,
        *,
        fact_type: str,
        content: str,
        source_task_id: str,
        entity_key: str,
        region_key: str | None,
        year: int | None,
        source_ref: str,
        kb_id: str = "",
        attribution: str = "",
    ) -> str:
        """B 类确认实体 → 事实草稿；(source_task_id, entity_key) 去重。返回 created|skipped。"""
        async with pg_manager.get_async_session_context() as session:
            existing = await session.execute(
                select(DomainFactoryRegionalFact).where(
                    DomainFactoryRegionalFact.source_task_id == source_task_id,
                    DomainFactoryRegionalFact.entity_key == entity_key,
                )
            )
            if existing.scalar_one_or_none() is not None:
                return "skipped"
            session.add(
                DomainFactoryRegionalFact(
                    fact_type=fact_type,
                    content=content,
                    source_task_id=source_task_id,
                    entity_key=entity_key,
                    region_key=region_key,
                    kb_id=kb_id,
                    attribution=attribution,
                    year=year,
                    source_ref=source_ref or None,
                )
            )
        return "created"

    async def confirm_facts_for_task(self, task_id: str, region_key: str | None) -> int:
        """confirm-region 级联：同任务未退役事实覆盖式回填 region_key 并转 confirmed（纠偏含已确认行）。"""
        async with pg_manager.get_async_session_context() as session:
            task = (
                await session.execute(select(DomainFactoryTask).where(DomainFactoryTask.id == task_id))
            ).scalar_one_or_none()
            current = normalize_attribution(task.region_key, task.scope or "project", task.project_name)
            kb_id = str(task.knowledge_base_id or "") if task else ""
            attribution = attribution_scope_key(kb_id, *current)
            result = await session.execute(
                update(DomainFactoryRegionalFact)
                .where(
                    DomainFactoryRegionalFact.source_task_id == task_id,
                    DomainFactoryRegionalFact.status.in_(["draft", "confirmed"]),
                )
                .values(
                    region_key=region_key,
                    kb_id=kb_id,
                    attribution=attribution,
                    status="confirmed",
                    updated_at=utc_now_naive(),
                )
            )
        return result.rowcount or 0

    async def _bind_regional_facts_for_task_in_session(self, session, task: DomainFactoryTask) -> None:
        """入库绑定事务内同步事实归属；避免事实在任务提交后仍停留在空归属。"""
        current = normalize_attribution(task.region_key, task.scope or "project", task.project_name)
        kb_id = str(task.knowledge_base_id or "")
        await session.execute(
            update(DomainFactoryRegionalFact)
            .where(DomainFactoryRegionalFact.source_task_id == task.id)
            .values(
                kb_id=kb_id,
                attribution=attribution_scope_key(kb_id, *current),
                updated_at=utc_now_naive(),
            )
        )

    async def retire_regional_facts(self, fact_ids: list[int]) -> int:
        """泄漏处置：批量 status→retired（不删行，留审计）；幂等。"""
        if not fact_ids:
            return 0
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                update(DomainFactoryRegionalFact)
                .where(DomainFactoryRegionalFact.id.in_(fact_ids))
                .values(status="retired", updated_at=utc_now_naive())
            )
        return result.rowcount or 0

    async def get_learned_templates_by_ids(self, template_ids: list[int]) -> list[dict[str, Any]]:
        if not template_ids:
            return []
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(
                    DomainFactoryLearnedTemplate.id,
                    DomainFactoryLearnedTemplate.scope,
                    DomainFactoryLearnedTemplate.extra_meta,
                ).where(DomainFactoryLearnedTemplate.id.in_(template_ids))
            )
            return [{"id": r.id, "scope": r.scope, "extra_meta": r.extra_meta or {}} for r in result]

    async def get_learned_templates_by_contributing_task(self, task_id: str) -> list[dict[str, Any]]:
        """归因集定位：extra_meta.contributing_task_ids 含 task_id 的模板（JSONB 包含查询）。"""
        import json as _json

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                text(
                    "SELECT id, scope, extra_meta FROM domain_factory_learned_templates "
                    "WHERE extra_meta::jsonb->'contributing_task_ids' @> CAST(:needle AS jsonb)"
                ),
                {"needle": _json.dumps([task_id])},
            )
            return [{"id": r.id, "scope": r.scope, "extra_meta": r.extra_meta or {}} for r in result]

    async def update_learned_template_scope(
        self, template_id: int, scope: str | None, extra_meta: dict[str, Any]
    ) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(DomainFactoryLearnedTemplate)
                .where(DomainFactoryLearnedTemplate.id == template_id)
                .values(scope=scope, extra_meta=extra_meta, updated_at=utc_now_naive())
            )

    async def rewrite_learned_template_slot_refs(self, ref_map: dict[str, str]) -> int:
        """按映射批量改写学习模板插槽引用（存量治理：中文后缀/旧键归一为新键）。
        学习模板不参与 _remap_waiting_review_tasks 的自动归一，需显式改写。
        ref_map: {旧完整 ref: 新完整 ref}；返回改写的模板数。"""
        if not ref_map:
            return 0
        rewritten = 0
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainFactoryLearnedTemplate))
            for template in result.scalars():
                slots = template.slots or []
                new_slots = []
                changed = False
                for slot in slots:
                    ref = str((slot or {}).get("entity_ref") or "")
                    if ref in ref_map:
                        slot = {**slot, "entity_ref": ref_map[ref]}
                        changed = True
                    new_slots.append(slot)
                if changed:
                    # JSON 列需整体换新对象才能被 ORM 判定变更
                    template.slots = new_slots
                    template.updated_at = utc_now_naive()
                    rewritten += 1
        return rewritten

    async def get_task_scopes(self, task_ids: list[str]) -> dict[str, str | None]:
        if not task_ids:
            return {}
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryTask.id, DomainFactoryTask.scope).where(DomainFactoryTask.id.in_(task_ids))
            )
            return {r.id: r.scope for r in result}

    # [pisuan-custom] W4 归属管理读接口（只读，零 DDL）

    async def list_tasks_with_attribution(
        self,
        scope: str | None = None,
        region_key: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """任务归属列表。scope='unassigned' 解释为 scope IS NULL，其余等值过滤；
        keyword 对 file_name 大小写不敏感模糊；created_at 倒序分页。"""
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy.orm import joinedload

            conditions = []
            if scope == "unassigned":
                conditions.append(DomainFactoryTask.scope.is_(None))
            elif scope:
                conditions.append(DomainFactoryTask.scope == scope)
            if region_key:
                conditions.append(DomainFactoryTask.region_key == region_key)
            if keyword:
                conditions.append(DomainFactoryTask.file_name.ilike(f"%{keyword}%"))

            total = (await session.execute(select(func.count(DomainFactoryTask.id)).where(*conditions))).scalar() or 0

            result = await session.execute(
                select(DomainFactoryTask)
                .options(joinedload(DomainFactoryTask.domain))
                .where(*conditions)
                .order_by(DomainFactoryTask.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            tasks = result.unique().scalars().all()
            items = [
                {
                    "id": t.id,
                    "file_name": t.file_name,
                    "domain": t.domain.code if t.domain else None,
                    "domain_label": t.domain.name if t.domain else None,
                    "status": t.status,
                    "project_name": t.project_name,
                    "region_label": t.region_label,
                    "region_key": t.region_key,
                    "scope": t.scope,
                    "knowledge_base_id": t.knowledge_base_id,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ]
            return items, total

    async def list_regional_facts(
        self,
        region_key: str | None = None,
        fact_type: str | None = None,
        status: str | None = None,
        kb_id: str | None = None,
        attribution: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """区域事实分页列表（created_at 倒序）；来源任务 file_name 就地批量拼接。"""
        async with pg_manager.get_async_session_context() as session:
            conditions = []
            if region_key:
                conditions.append(DomainFactoryRegionalFact.region_key == region_key)
            if fact_type:
                conditions.append(DomainFactoryRegionalFact.fact_type == fact_type)
            if status:
                conditions.append(DomainFactoryRegionalFact.status == status)
            if kb_id:
                conditions.append(DomainFactoryRegionalFact.kb_id == kb_id)
            if attribution is not None:
                conditions.append(DomainFactoryRegionalFact.attribution == attribution)

            total = (
                await session.execute(select(func.count(DomainFactoryRegionalFact.id)).where(*conditions))
            ).scalar() or 0

            result = await session.execute(
                select(DomainFactoryRegionalFact)
                .where(*conditions)
                .order_by(DomainFactoryRegionalFact.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            facts = result.scalars().all()

            task_ids = {f.source_task_id for f in facts if f.source_task_id}
            file_map: dict[str, str] = {}
            if task_ids:
                rows = await session.execute(
                    select(DomainFactoryTask.id, DomainFactoryTask.file_name).where(DomainFactoryTask.id.in_(task_ids))
                )
                file_map = dict(rows.all())

            items = [
                {
                    "id": f.id,
                    "fact_type": f.fact_type,
                    "region_key": f.region_key,
                    "kb_id": f.kb_id or "",
                    "attribution": f.attribution or "",
                    "content": f.content,
                    "status": f.status,
                    "year": f.year,
                    "source_task_id": f.source_task_id,
                    "source_task_file_name": file_map.get(f.source_task_id),
                    "source_ref": f.source_ref,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                }
                for f in facts
            ]
            return items, total

    async def get_region_board_raw(self) -> dict[str, Any]:
        """看板聚合原始数据（数据量小：任务 8 / 模板 211，单响应一次取全，不做缓存）。"""
        async with pg_manager.get_async_session_context() as session:
            task_rows = (
                await session.execute(
                    select(
                        DomainFactoryTask.region_key,
                        DomainFactoryTask.region_label,
                        func.count(DomainFactoryTask.id),
                    ).group_by(DomainFactoryTask.region_key, DomainFactoryTask.region_label)
                )
            ).all()
            fact_rows = (
                await session.execute(
                    select(
                        DomainFactoryRegionalFact.region_key,
                        DomainFactoryRegionalFact.kb_id,
                        DomainFactoryRegionalFact.attribution,
                        DomainFactoryRegionalFact.fact_type,
                        DomainFactoryRegionalFact.status,
                        func.count(DomainFactoryRegionalFact.id),
                    ).group_by(
                        DomainFactoryRegionalFact.region_key,
                        DomainFactoryRegionalFact.kb_id,
                        DomainFactoryRegionalFact.attribution,
                        DomainFactoryRegionalFact.fact_type,
                        DomainFactoryRegionalFact.status,
                    )
                )
            ).all()
            scope_rows = (
                await session.execute(
                    select(
                        DomainFactoryLearnedTemplate.scope,
                        func.count(DomainFactoryLearnedTemplate.id),
                    ).group_by(DomainFactoryLearnedTemplate.scope)
                )
            ).all()
            task_region_rows = (
                await session.execute(
                    select(DomainFactoryTask.id, DomainFactoryTask.region_key).where(
                        DomainFactoryTask.region_key.is_not(None)
                    )
                )
            ).all()
            attribution_bindings = (
                await session.execute(
                    select(
                        DomainFactoryKnowledgeBaseAttribution.kb_id,
                        DomainFactoryKnowledgeBaseAttribution.attribution,
                        DomainFactoryKnowledgeBaseAttribution.region_key,
                        DomainFactoryKnowledgeBaseAttribution.scope,
                        DomainFactoryKnowledgeBaseAttribution.project_name,
                    ).order_by(DomainFactoryKnowledgeBaseAttribution.kb_id)
                )
            ).all()
            template_rows = (
                await session.execute(
                    select(
                        DomainFactoryLearnedTemplate.id,
                        DomainFactoryLearnedTemplate.chapter,
                        DomainFactoryLearnedTemplate.domain_code,
                        DomainFactoryLearnedTemplate.report_type_code,
                        DomainFactoryLearnedTemplate.scope,
                        DomainFactoryLearnedTemplate.attribution,
                        DomainFactoryLearnedTemplate.extra_meta,
                        DomainFactoryLearnedTemplate.updated_at,
                    )
                )
            ).all()

        return {
            "tasks_by_region": [{"region_key": rk, "region_label": rl, "count": cnt} for rk, rl, cnt in task_rows],
            "facts_by_region_type_status": [
                {
                    "region_key": rk,
                    "kb_id": kbid,
                    "attribution": attr,
                    "fact_type": ft,
                    "status": st,
                    "count": cnt,
                }
                for rk, kbid, attr, ft, st, cnt in fact_rows
            ],
            "kb_attributions": [
                {
                    "kb_id": kbid,
                    "attribution": attr,
                    "region_key": rk,
                    "scope": sc,
                    "project_name": pn,
                }
                for kbid, attr, rk, sc, pn in attribution_bindings
            ],
            # scope 可能是 NULL → 键用 ""（service 层映射为 unassigned）
            "templates_by_scope": {(scope or ""): cnt for scope, cnt in scope_rows},
            "task_regions": dict(task_region_rows),
            "templates": [
                {
                    "id": tid,
                    "chapter": ch,
                    "domain_code": dc,
                    "report_type_code": rtc,
                    "scope": sc,
                    "attribution": attr,
                    "contributing_task_ids": (em or {}).get("contributing_task_ids") or [],
                    "updated_at": ua.isoformat() if ua else None,
                }
                for tid, ch, dc, rtc, sc, attr, em, ua in template_rows
            ],
        }
