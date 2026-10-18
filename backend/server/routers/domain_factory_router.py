"""Domain Factory API Router - 领域知识工厂路由"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from yuxi.services import eia_corpus_task_service as eia_corpus_tasks
from yuxi.services.domain_factory_service import get_domain_factory_service
from yuxi.services.eia_data_service import (
    get_data_expectations,
    get_dataset_view,
    get_sections,
    get_skill_stats,
    get_unmapped,
)
from yuxi.services.eia_entity_service import get_eia_entity_service
from yuxi.services.eia_formula_service import get_eia_formula_service
from yuxi.services.eia_lexicon_service import get_eia_lexicon_service
from yuxi.services.eia_library_service import LibraryFileTooLarge, get_eia_library_service
from yuxi.services.eia_meta_service import get_eia_meta_service
from yuxi.services.eia_paradigm_service import get_eia_paradigm_service
from yuxi.services.eia_stage_service import get_eia_stage_service
from yuxi.services.eia_standard_service import get_eia_standard_service
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

from server.utils.auth_middleware import get_admin_user, get_required_user

domain_factory = APIRouter(prefix="/domain-factory", tags=["Domain Factory"])


# =============================================================================
# Domain Management
# =============================================================================


@domain_factory.get("/domains")
async def get_domains(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取所有领域列表"""
    try:
        service = get_domain_factory_service()
        domains = await service.get_domains()
        return {"items": domains}
    except Exception as e:
        logger.error(f"Failed to get domains: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取领域列表失败: {str(e)}")


@domain_factory.post("/domains")
async def create_domain(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """创建新领域"""
    try:
        code = payload.get("code", "")
        name = payload.get("name", "")
        description = payload.get("description")
        if not code or not name:
            raise HTTPException(status_code=400, detail="code 和 name 不能为空")
        service = get_domain_factory_service()
        domain = await service.create_domain(code, name, description)
        return {"success": True, "domain": domain}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create domain: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建领域失败: {str(e)}")


@domain_factory.put("/domains/{domain_id}")
async def update_domain(
    domain_id: int,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新领域配置"""
    try:
        service = get_domain_factory_service()
        domain = await service.update_domain(domain_id, payload)
        if not domain:
            raise HTTPException(status_code=404, detail="领域不存在")
        return {"success": True, "domain": domain}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update domain {domain_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新领域失败: {str(e)}")


@domain_factory.delete("/domains/{domain_id}")
async def delete_domain(
    domain_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除领域"""
    try:
        service = get_domain_factory_service()
        success = await service.delete_domain(domain_id)
        if not success:
            raise HTTPException(status_code=404, detail="领域不存在")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete domain {domain_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除领域失败: {str(e)}")


# =============================================================================
# Data Sources & Tasks
# =============================================================================


@domain_factory.get("/data-sources")
async def fetch_data_sources(
    domain: str | None = Query(None),
    status: str | None = Query(None),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取待处理数据源列表"""
    try:
        service = get_domain_factory_service()
        tasks = await service.list_pending_tasks(domain)
        return {"pending": tasks}
    except Exception as e:
        logger.error(f"Failed to fetch data sources: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取数据源失败: {str(e)}")


@domain_factory.get("/history")
async def fetch_history(
    domain: str | None = Query(None),
    limit: int = Query(50),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取已提交历史列表"""
    try:
        service = get_domain_factory_service()
        tasks = await service.list_history_tasks(domain, limit)
        return {"items": tasks}
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {str(e)}")


@domain_factory.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取任务详情"""
    try:
        service = get_domain_factory_service()
        detail = await service.get_task_detail(task_id)
        if not detail:
            raise HTTPException(status_code=404, detail="任务不存在")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {str(e)}")


@domain_factory.get("/tasks/{task_id}/markdown")
async def get_task_markdown(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取任务的 Markdown 内容（原始文档解析结果）"""
    try:
        service = get_domain_factory_service()
        detail = await service.get_task_detail(task_id)
        if not detail:
            raise HTTPException(status_code=404, detail="任务不存在")
        markdown = detail.get("raw_markdown", "")
        if not markdown:
            raise HTTPException(status_code=404, detail="该任务暂无 markdown 数据")
        return {"markdown": markdown, "file_name": detail.get("file_name", "")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task markdown {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取 markdown 失败: {str(e)}")


@domain_factory.put("/tasks/{task_id}")
async def save_task_step(
    task_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """保存任务步骤数据"""
    try:
        service = get_domain_factory_service()
        task = await service.save_task_step(task_id, payload)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True, "task": task}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save task step {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存任务失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/validate")
async def validate_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """对任务执行校验（PreCommitValidator + SlotValidationService），返回结构化报告。

    纯只读操作，不修改任务状态。用户可在提交前反复调用以检查和修正问题。
    """
    try:
        service = get_domain_factory_service()
        report = await service.validate_task(task_id)
        if "error" in report:
            raise HTTPException(status_code=404, detail=report["error"])
        return {"success": True, "report": report}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate task {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"校验失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/discover-entities")
async def discover_entities(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """异步触发实体发现：LLM 分析未绑定 slot，建议新实体/属性"""
    try:
        service = get_domain_factory_service()
        result = await service.discover_entities_task(task_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to discover entities for {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"实体发现失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/commit")
async def commit_task(
    task_id: str,
    payload: dict[str, Any] = Body({}),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """提交任务（人工审核后确认入库）"""
    try:
        service = get_domain_factory_service()
        reviewer = current_user.username if current_user else None

        # 支持新的 payload 格式
        form_data = payload.get("form", {})
        structured_data = payload.get("structured", [])
        template_data = payload.get("template", {})
        knowledge_base_id = payload.get("knowledge_base_id")

        # 保存分步骤数据
        if form_data:
            await service.save_task_step(task_id, {"step": "basic", "payload": form_data})
        if structured_data or template_data:
            await service.save_task_step(
                task_id, {"step": "structured", "payload": {"structured_blocks": structured_data}}
            )
        if template_data:
            await service.save_task_step(task_id, {"step": "template", "payload": template_data})

        task = await service.commit_task(task_id, reviewer, knowledge_base_id=knowledge_base_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        return {"success": True, "task": task, "ingest_task_id": task.get("ingest_task_id")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to commit task {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"提交任务失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/reingest")
async def reingest_task(
    task_id: str,
    payload: dict[str, Any] = Body({}),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """再入库：重新处理并入库已提交的任务"""
    try:
        service = get_domain_factory_service()
        knowledge_base_id = payload.get("knowledge_base_id")

        task = await service.reingest_task(task_id, knowledge_base_id=knowledge_base_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        return {"success": True, "task": task, "ingest_task_id": task.get("ingest_task_id")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reingest task {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"再入库失败: {str(e)}")


@domain_factory.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """删除任务"""
    try:
        service = get_domain_factory_service()
        success = await service.delete_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete task {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """重试失败任务"""
    try:
        service = get_domain_factory_service()
        task = await service.retry_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True, "task": task}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry task {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"重试任务失败: {str(e)}")


@domain_factory.get("/tasks/{task_id}/proposed-entities")
async def get_proposed_entities(
    task_id: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取 LLM 整理后的实体建议（从泛化阶段未识别插槽生成）"""
    try:
        service = get_domain_factory_service()
        result = await service.get_proposed_entities(task_id)
        return result
    except Exception as e:
        logger.error(f"Failed to get proposed entities for {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取实体建议失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/confirm-entities")
async def confirm_entities(
    task_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """确认并保存建议的实体到实体库"""
    try:
        entities = payload.get("entities", [])
        if not entities:
            raise HTTPException(status_code=400, detail="entities 不能为空")
        service = get_domain_factory_service()
        result = await service.confirm_proposed_entities(task_id, entities)
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm entities for {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"确认实体失败: {str(e)}")


@domain_factory.post("/tasks/{task_id}/confirm-region")
async def confirm_region(
    task_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W3 L3：归属人工确认——落任务四列并级联（facts 确认 + 归因集模板重算）"""
    try:
        region_label = str(payload.get("region_label", "")).strip()
        if not region_label:
            raise HTTPException(status_code=400, detail="region_label 不能为空")
        service = get_domain_factory_service()
        result = await service.confirm_region(task_id, region_label, payload.get("region_key"), payload.get("scope"))
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm region for {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"归属确认失败: {str(e)}")


@domain_factory.post("/regional-facts/retire")
async def retire_regional_facts(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """[pisuan-custom] W3 泄漏处置：批量退役区域事实（不删行，留审计）"""
    try:
        raw_ids = payload.get("fact_ids", [])
        if not raw_ids:
            raise HTTPException(status_code=400, detail="fact_ids 不能为空")
        service = get_domain_factory_service()
        retired = await service.retire_regional_facts([int(i) for i in raw_ids])
        return {"success": True, "retired": retired}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retire regional facts: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"事实退役失败: {str(e)}")


@domain_factory.get("/tasks")
async def fetch_attribution_tasks(
    scope: str | None = Query(None),
    region_key: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W4：任务归属列表（scope=unassigned → scope IS NULL）。"""
    try:
        service = get_domain_factory_service()
        result = await service.list_tasks_with_attribution(
            scope=scope, region_key=region_key, keyword=keyword, page=page, page_size=page_size
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list attribution tasks: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取任务归属列表失败: {str(e)}")


@domain_factory.get("/regional-facts")
async def fetch_regional_facts(
    region_key: str | None = Query(None),
    fact_type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W4：区域事实列表（region×fact_type×status 过滤）。"""
    try:
        service = get_domain_factory_service()
        result = await service.list_regional_facts(
            region_key=region_key, fact_type=fact_type, status=status, page=page, page_size=page_size
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list regional facts: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取区域事实列表失败: {str(e)}")


@domain_factory.get("/region-board")
async def fetch_region_board(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W4：聚合看板（统计卡 + 模板明细 + 区域树）。"""
    try:
        service = get_domain_factory_service()
        return await service.build_region_board()
    except Exception as e:
        logger.error(f"Failed to build region board: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取聚合看板失败: {str(e)}")


# =============================================================================
# File Upload
# =============================================================================


@domain_factory.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    domain: str = Form(...),
    document_type: str = Form("通用"),
    report_type_code: str = Form("通用"),
    source_report_id: str | None = Form(None),
    chapter_label: str | None = Form(None),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """上传文档文件。支持分章节上传: source_report_id 关联同一报告, chapter_label 标记章节。"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        file_content = await file.read()
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")

        service = get_domain_factory_service()
        task_id, storage_path = await service.save_uploaded_file(file_content, file.filename, domain)

        uploaded_by = current_user.username if current_user else None
        await service.create_task(
            domain_code=domain,
            file_name=file.filename,
            file_path=storage_path,
            uploaded_by=uploaded_by,
            document_type=document_type,
            report_type_code=report_type_code,
            source_report_id=source_report_id,
            chapter_label=chapter_label,
        )

        return {
            "success": True,
            "task_id": task_id,
            "file_name": file.filename,
            "domain": domain,
            "report_type_code": report_type_code,
            "source_report_id": source_report_id,
            "chapter_label": chapter_label,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to upload file: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"上传文件失败: {str(e)}")


# =============================================================================
# Pipeline Config
# =============================================================================


@domain_factory.get("/pipeline-config")
async def get_pipeline_config(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取处理流程配置"""
    try:
        service = get_domain_factory_service()
        config = await service.get_pipeline_config()
        return config
    except Exception as e:
        logger.error(f"Failed to get pipeline config: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取流程配置失败: {str(e)}")


@domain_factory.put("/pipeline-config")
async def update_pipeline_config(
    config: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新处理流程配置"""
    try:
        service = get_domain_factory_service()
        success = await service.save_pipeline_config(config)
        if not success:
            raise HTTPException(status_code=500, detail="保存流程配置失败")
        return {"success": True, "config": config}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update pipeline config: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新流程配置失败: {str(e)}")


# =============================================================================
# Prompt Config
# =============================================================================


@domain_factory.get("/prompt-config")
async def get_prompt_config(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取 Prompt 模板配置"""
    try:
        service = get_domain_factory_service()
        config = await service.get_prompt_config()
        return config
    except Exception as e:
        logger.error(f"Failed to get prompt config: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取 Prompt 配置失败: {str(e)}")


@domain_factory.put("/prompt-config")
async def update_prompt_config(
    config: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新 Prompt 模板配置"""
    try:
        service = get_domain_factory_service()
        success = await service.save_prompt_config(config)
        if not success:
            raise HTTPException(status_code=500, detail="保存 Prompt 配置失败")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update prompt config: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新 Prompt 配置失败: {str(e)}")


# =============================================================================
# Context & Section Routing
# =============================================================================


@domain_factory.get("/contexts")
async def get_contexts(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取所有行业领域与报告类型"""
    try:
        service = get_domain_factory_service()
        contexts = await service.get_contexts()
        return contexts
    except Exception as e:
        logger.error(f"Failed to get contexts: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取上下文配置失败: {str(e)}")


# =============================================================================
# Task Center Integration - 任务中心整合
# =============================================================================


@domain_factory.get("/tasks-center")
async def get_tasks_for_task_center(
    domain: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取知识工厂任务列表（用于任务中心展示）

    直接从任务中心获取 domain_factory 类型任务，并关联知识工厂的详细状态
    """
    try:
        from yuxi.services.task_service import tasker as global_tasker

        # 从任务中心获取所有任务
        all_tasks = await global_tasker.list_tasks(limit=limit)
        tasker_tasks = all_tasks.get("tasks", [])

        # 过滤 domain_factory 类型任务
        df_tasks = [t for t in tasker_tasks if t.get("type") == "domain_factory"]

        # 获取知识工厂任务状态
        service = get_domain_factory_service()

        # 合并知识工厂任务状态
        result_tasks = []
        for task in df_tasks:
            payload = task.get("payload", {})
            df_task_id = payload.get("task_id")

            if df_task_id:
                # 从知识工厂获取最新状态
                df_task = await service.repo.get_task(df_task_id)
                if df_task:
                    # 覆盖任务中心状态为知识工厂的实际状态
                    df_status = df_task.status
                    mapped = DOMAIN_FACTORY_STATUS_MAP.get(df_status, {})
                    task["status"] = mapped.get("status", task.get("status"))
                    task["progress"] = mapped.get("progress", task.get("progress"))
                    task["message"] = mapped.get("message", task.get("message"))

            result_tasks.append(task)

        return {"tasks": result_tasks}
    except Exception as e:
        logger.error(f"Failed to get tasks for task center: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


DOMAIN_FACTORY_STATUS_MAP = {
    "UPLOADED": {"status": "running", "progress": 5, "message": "文件已上传，等待处理..."},
    "PARSING": {"status": "running", "progress": 25, "message": "正在解析文档..."},
    "EXTRACTING": {"status": "running", "progress": 55, "message": "正在提取信息..."},
    "GENERALIZING": {"status": "running", "progress": 80, "message": "正在生成槽位模板..."},
    "WAITING_REVIEW": {"status": "running", "progress": 95, "message": "信息提取完成，等待人工审核..."},
    "COMMITTED": {"status": "success", "progress": 100, "message": "报告已入库完成"},
    "COMMIT_PARTIAL": {
        "status": "success",
        "progress": 100,
        "message": "报告已入库（部分阶段有警告，请查看 partial_errors）",
    },
    "COMMIT_FAILED": {"status": "failed", "progress": 100, "message": "入库失败"},
    "FAILED": {"status": "failed", "progress": 100, "message": "执行失败"},
}


@domain_factory.post("/tasks/{task_id}/sync-task-center")
async def sync_task_to_task_center(
    task_id: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """同步任务状态到任务中心"""
    try:
        service = get_domain_factory_service()
        detail = await service.get_task_detail(task_id)
        if not detail:
            raise HTTPException(status_code=404, detail="任务不存在")

        from yuxi.services.task_service import tasker as global_tasker

        tasks_data = await global_tasker.list_tasks(limit=200)

        # 查找并更新对应任务
        for task in tasks_data.get("tasks", []):
            payload = task.get("payload", {})
            if payload.get("task_id") == task_id:
                df_status = detail.get("status", "UPLOADED")
                await global_tasker._update_task(
                    task["id"],
                    status=_map_df_status_to_tasker(df_status),
                    progress=_calculate_progress(df_status),
                    message=_get_status_message(df_status),
                    result={"domain_factory_task_id": task_id, "detail": detail},
                )
                return {"success": True, "synced_task_id": task["id"]}

        return {"success": False, "message": "未在任务中心找到对应任务"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync task to task center: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


def _get_status_message(df_status: str) -> str:
    """获取状态描述消息"""
    message_map = {
        "UPLOADED": "文件已上传，等待处理...",
        "PARSING": "正在解析文档...",
        "EXTRACTING": "正在提取信息...",
        "WAITING_REVIEW": "信息提取完成，等待人工审核...",
        "COMMITTED": "报告已入库完成",
        "FAILED": "执行失败",
    }
    return message_map.get(df_status, "处理中...")


def _map_df_status_to_tasker(df_status: str) -> str:
    """将领域工厂状态映射到任务中心状态（兼容旧代码）"""
    return DOMAIN_FACTORY_STATUS_MAP.get(df_status, {}).get("status", "pending")


def _calculate_progress(df_status: str) -> float:
    """根据状态计算进度（兼容旧代码）"""
    return DOMAIN_FACTORY_STATUS_MAP.get(df_status, {}).get("progress", 0.0)


# =============================================================================
# Graph Query - 图谱查询
# =============================================================================


@domain_factory.get("/graph/templates")
async def query_graph_templates(
    domain_code: str = Query("", description="领域编码"),
    report_type_code: str = Query("", description="报告类型编码"),
    limit: int = Query(50, description="返回数量限制"),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """按 (domain, report_type) 查询图谱中的模板和骨架数据"""
    try:
        service = get_domain_factory_service()
        result = await service.query_graph_templates(domain_code, report_type_code, limit)
        return result
    except Exception as e:
        logger.error(f"Failed to query graph templates: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"图谱查询失败: {str(e)}")


@domain_factory.get("/graph/legal-references")
async def query_graph_legal_references(
    domain_code: str = Query("", description="领域编码"),
    scope: str = Query("", description="适用范围过滤 (national/regional/project)"),
    limit: int = Query(100, description="返回数量限制"),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """查询图谱中的法律引用，支持按 scope 过滤"""
    try:
        service = get_domain_factory_service()
        result = await service.query_graph_legal_references(scope, limit)
        return result
    except Exception as e:
        logger.error(f"Failed to query legal references: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"法律引用查询失败: {str(e)}")


# ========== 大纲模板管理 ==========


@domain_factory.get("/outline-templates")
async def list_outline_templates(
    domain: str = Query("coal"),
    report_type: str = Query("eia_report"),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """列出13章大纲模板概要"""
    try:
        from yuxi.services.graph_query_service import GraphQueryService

        svc = GraphQueryService()
        try:
            items = await svc.list_outline_templates(domain, report_type)
            return {"items": items, "total": len(items)}
        finally:
            svc.close()
    except Exception as e:
        logger.error(f"Failed to list outline templates: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"大纲模板列表查询失败: {str(e)}")


@domain_factory.get("/outline-templates/{chapter_key}")
async def get_outline_template(
    chapter_key: str,
    domain: str = Query("coal"),
    report_type: str = Query("eia_report"),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """获取单章大纲模板详情"""
    try:
        from yuxi.services.graph_query_service import GraphQueryService

        svc = GraphQueryService()
        try:
            outline = await svc.get_chapter_outline(domain, report_type, chapter_key)
            if outline is None:
                raise HTTPException(status_code=404, detail=f"章节 '{chapter_key}' 不存在")
            return outline
        finally:
            svc.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get outline template: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"大纲模板详情查询失败: {str(e)}")


@domain_factory.put("/outline-templates/{chapter_key}")
async def update_outline_template(
    chapter_key: str,
    body: dict = Body(...),
    domain: str = Query("coal"),
    report_type: str = Query("eia_report"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新单章大纲模板"""
    try:
        from yuxi.services.graph_query_service import GraphQueryService

        svc = GraphQueryService()
        try:
            updated = await svc.update_chapter_template(domain, report_type, chapter_key, body)
            if not updated:
                raise HTTPException(status_code=404, detail=f"章节 '{chapter_key}' 不存在或无可更新字段")
            return {"success": True, "chapter_key": chapter_key}
        finally:
            svc.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update outline template: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"大纲模板更新失败: {str(e)}")


@domain_factory.post("/outline-templates/seed")
async def seed_outline_templates(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """初始化/重建标准 13 章大纲结构（幂等）。

    复用 scripts/ 下三个 seed 脚本的 seed() 函数，按依赖顺序写入 Neo4j：
    标准章节 → 标准子章节 → 大纲内容。图谱为空或需重置标准结构时调用。
    """
    import os

    from neo4j import GraphDatabase

    from scripts.seed_outline_content import seed as seed_content
    from scripts.seed_standard_chapters import seed as seed_chapters
    from scripts.seed_standard_subchapters import seed as seed_subchapters

    uri = os.environ.get("NEO4J_URI", "bolt://graph:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "0123456789")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        chapters = seed_chapters(driver)
        subchapters = seed_subchapters(driver)
        content_chapters = seed_content(driver)
        logger.info(
            f"标准大纲结构初始化完成: chapters={chapters}, subchapters={subchapters}, content={content_chapters}"
        )
        return {
            "success": True,
            "chapters": chapters,
            "subchapters": subchapters,
            "content_chapters": content_chapters,
        }
    except Exception as e:
        logger.error(f"Failed to seed outline templates: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"标准结构初始化失败: {str(e)}")
    finally:
        driver.close()


@domain_factory.post("/outline-templates/extract")
async def extract_outline_preview(
    file: UploadFile = File(...),
    domain: str = Form("coal"),
    report_type: str = Form("eia_report"),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """从上传的报告轻量提取大纲（只解析+章节归一化，跳过泛化），返回预览供确认。

    相比完整 ETL 提速 10-50 倍。预览结果经人工确认后调 /confirm 入库。
    """
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="上传文件为空")
        service = get_domain_factory_service()
        preview = await service.extract_outline_preview(file_bytes, file.filename or "upload.docx", domain, report_type)
        return preview
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract outline: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"大纲提取失败: {str(e)}")


@domain_factory.post("/outline-templates/confirm")
async def confirm_outline_extract(
    body: dict = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """将人工确认的大纲章节入库（PG outline upsert + 图谱标准章节同步）。"""
    try:
        domain = body.get("domain", "coal")
        report_type = body.get("report_type", "eia_report")
        chapters = body.get("chapters") or []
        file_name = body.get("file_name") or ""
        if not chapters:
            raise HTTPException(status_code=400, detail="chapters 不能为空")
        service = get_domain_factory_service()
        result = await service.confirm_outline_extract(domain, report_type, chapters, file_name)
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm outline: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"大纲入库失败: {str(e)}")


@domain_factory.post("/outline-templates/generate-regex")
async def generate_extraction_regex(
    body: dict = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """为指定领域/报告类型的图谱标准章节(std_ level=1)批量生成 extraction_regex。

    seed 的标准章节不走 LLM，没有 extraction_regex。此端点走主进程(driver 正常)，
    对每个 std_ 章节调 _llm_chapter_meta 生成正则并写回图谱。
    """
    try:
        domain = body.get("domain", "coal")
        report_type = body.get("report_type", "eia_report")
        service = get_domain_factory_service()
        result = await service.generate_standard_extraction_regex(domain, report_type)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Failed to generate extraction_regex: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"提取规则生成失败: {str(e)}")


# =============================================================================
# EIA Data Factory (coal-eia-writer 环评域数据工厂)
# =============================================================================


@domain_factory.get("/eia/stats")
async def get_eia_skill_stats(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """环评域数据工厂 · 技能数据集统计总览（只读聚合技能语料文件，无 DB 依赖）"""
    try:
        return await run_in_threadpool(get_skill_stats)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to get eia skill stats: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取环评数据统计失败: {str(e)}")


@domain_factory.get("/eia/expectations/unmapped")
async def list_eia_unmapped(
    stage: str | None = Query(None),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """unmapped 池明细（只读）：per-stage 未归并量词短语，词表口径 label 扩充素材。"""
    try:
        return await run_in_threadpool(get_unmapped, stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list eia unmapped: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取 unmapped 明细失败: {str(e)}")


# =============================================================================
# EIA Lexicon (环评数值护栏词表运营层：DB 覆盖层 + overrides 物化)
# =============================================================================


@domain_factory.get("/eia/lexicon/entries")
async def list_eia_lexicon_entries(
    stage: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """词表条目列表（DB 决策态 + 语料实时计数合并；counts 为全量状态分布）"""
    try:
        return await get_eia_lexicon_service().list_entries(stage=stage, category=category, status=status, q=q)
    except Exception as e:
        logger.error(f"Failed to list eia lexicon entries: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取词表条目失败: {str(e)}")


@domain_factory.patch("/eia/lexicon/entries/{entry_id}")
async def update_eia_lexicon_entry(
    entry_id: int,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """条目确认/驳回/改名/备注（业务人员即可；splitting 仅可经拆分动作入选）"""
    try:
        entry = await get_eia_lexicon_service().update_entry(entry_id, payload, current_user.username)
        return {"success": True, "entry": entry}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update eia lexicon entry {entry_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新词表条目失败: {str(e)}")


@domain_factory.post("/eia/lexicon/entries/{entry_id}/split")
async def split_eia_lexicon_entry(
    entry_id: int,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """拆分值簇语义混叠的口径（如控制效率）：N 条 approved 子条目 + 原条目 rejected"""
    try:
        items = payload.get("items")
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="payload.items 必须是数组")
        result = await get_eia_lexicon_service().split_entry(entry_id, items, current_user.username)
        return {"success": True, **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to split eia lexicon entry {entry_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"拆分词表条目失败: {str(e)}")


@domain_factory.get("/eia/lexicon/entries/{entry_id}/mentions")
async def list_eia_lexicon_mentions(
    entry_id: int,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """条目口径在切片中的原始提及清单（拆分对话框素材）"""
    try:
        return await get_eia_lexicon_service().get_mentions(entry_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list eia lexicon mentions: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取口径提及失败: {str(e)}")


@domain_factory.post("/eia/lexicon/import")
async def import_eia_lexicon(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """重扫语料幂等导入词表候选（existing 一律跳过，绝不覆盖人工决策）"""
    try:
        result = await get_eia_lexicon_service().import_entries()
        return {"success": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to import eia lexicon: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导入词表候选失败: {str(e)}")


@domain_factory.get("/eia/lexicon/suppressions")
async def list_eia_lexicon_suppressions(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """抑制名单（改名自动登记 + 手工登记）：导入按 (stage, caliber, unit) 跳过"""
    try:
        return await get_eia_lexicon_service().list_suppressions()
    except Exception as e:
        logger.error(f"Failed to list eia lexicon suppressions: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取抑制名单失败: {str(e)}")


@domain_factory.post("/eia/lexicon/suppressions")
async def add_eia_lexicon_suppression(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """手工登记抑制（业务人员）：仅限扫描差集内指纹，已抑制幂等刷新"""
    try:
        return await get_eia_lexicon_service().add_suppression(payload, current_user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add eia lexicon suppression: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"登记抑制失败: {str(e)}")


@domain_factory.delete("/eia/lexicon/suppressions/{suppression_id}")
async def withdraw_eia_lexicon_suppression(
    suppression_id: int,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """撤回抑制（硬删行）：重扫可能复活旧指纹，UI 撤回前须明示后果"""
    try:
        row = await get_eia_lexicon_service().withdraw_suppression(suppression_id, current_user.username)
        return {"success": True, "row": row}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to withdraw eia lexicon suppression {suppression_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤回抑制失败: {str(e)}")


@domain_factory.get("/eia/lexicon/scan-candidates")
async def list_eia_lexicon_scan_candidates(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """重扫导入将带进来的候选差集（添加抑制下拉数据源）"""
    try:
        return await get_eia_lexicon_service().scan_candidates()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to list eia lexicon scan candidates: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取扫描候选失败: {str(e)}")


@domain_factory.get("/eia/datasets/switches")
async def list_eia_dataset_switches(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """数据集启停开关列表（含 overrides 物化文件存在态）"""
    try:
        return {"items": await get_eia_lexicon_service().get_switches()}
    except Exception as e:
        logger.error(f"Failed to list eia dataset switches: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取数据集开关失败: {str(e)}")


@domain_factory.put("/eia/datasets/switches/{dataset_key}")
async def set_eia_dataset_switch(
    dataset_key: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """切换数据集开关（admin；关闭即删 overrides 物化文件 → 管线回 builtin）"""
    try:
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=400, detail="payload.enabled 必须是布尔值")
        switch = await get_eia_lexicon_service().set_switch(dataset_key, enabled, current_user.username)
        return {"success": True, "switch": switch}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set eia dataset switch {dataset_key}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"切换数据集开关失败: {str(e)}")


@domain_factory.post("/eia/lexicon/export")
async def export_eia_lexicon(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """物化 approved 条目 → references/overrides/curated_lexicon.json（range 现算）+ 开关置位"""
    try:
        result = await get_eia_lexicon_service().export_overrides(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia lexicon: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出物化失败: {str(e)}")


# =============================================================================
# EIA Meta Annotations (环评语料元数据人工标注：DB 覆盖层 + 人工层文件物化)
# =============================================================================


@domain_factory.get("/eia/meta/reports")
async def list_eia_meta_reports(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """31 份报告元数据总览（自动层只读 + DB 标注合并 + counts 待办汇总）"""
    try:
        return await get_eia_meta_service().list_reports()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to list eia meta reports: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取元数据总览失败: {str(e)}")


@domain_factory.put("/eia/meta/reports/{report_id}/annotation")
async def set_eia_meta_annotation(
    report_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """标注落库（upsert）：{annotations: {year_hint?, scale_mt_a?}, note?}；rid 不在 corpus_meta 404，越界 400"""
    try:
        row = await get_eia_meta_service().set_annotation(report_id, payload, current_user.username)
        return {"success": True, "annotation": row}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set eia meta annotation {report_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存元数据标注失败: {str(e)}")


@domain_factory.post("/eia/meta/import")
async def import_eia_meta_annotations(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """存量人工层文件 → DB（幂等，existing rid 一律跳过，绝不覆盖页面裁决）"""
    try:
        result = await get_eia_meta_service().import_annotations()
        return {"success": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to import eia meta annotations: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导入元数据标注失败: {str(e)}")


@domain_factory.post("/eia/meta/export")
async def export_eia_meta_annotations(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """DB → corpus_meta_annotations.json 全量重写（rid 序确定性；admin）"""
    try:
        result = await get_eia_meta_service().export_annotations(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia meta annotations: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出元数据标注失败: {str(e)}")


# =============================================================================
# EIA Library（环评文件库：P1 进料区；P2 起 canonical md 正源 + KB 推送 + 语料加工）
# =============================================================================


@domain_factory.get("/eia/library/folders")
async def list_eia_library_folders(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """文件夹树（含各夹计数）+ 全库登记总数。"""
    service = get_eia_library_service()
    return {"folders": await service.list_folders(), "total_files": await service.count_files()}


@domain_factory.post("/eia/library/files")
async def upload_eia_library_file(
    file: UploadFile = File(...),
    folder_id: int | None = Form(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """上传即登记：sha1 全库去重（409 携既有位置），超限 413。"""
    try:
        return await get_eia_library_service().upload(file, folder_id, current_user.username if current_user else None)
    except FileExistsError as e:
        # 结构化 detail（base.js extractBusinessErrorDetail 契约）：字符串 detail 会被公共文案覆盖
        raise HTTPException(status_code=409, detail={"code": "eia_library_file_exists", "message": str(e)})
    except LibraryFileTooLarge as e:
        raise HTTPException(status_code=413, detail={"code": "eia_library_file_too_large", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.get("/eia/library/files")
async def list_eia_library_files(
    folder_id: int | None = None,
    q: str | None = None,
    uncategorized: bool = False,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """文件列表：folder_id 定向；uncategorized=未归类；都缺省=全库；q 文件名模糊。"""
    files = await get_eia_library_service().list_files(folder_id=folder_id, q=q, uncategorized=uncategorized)
    return {"files": files}


@domain_factory.get("/eia/library/files/{file_id}/download")
async def download_eia_library_file(
    file_id: int,
    current_user: User = Depends(get_required_user),
):
    """下载（以 original_filename 恢复原名；MinIO 正源行走 bytes，存量本地卷行走 FileResponse）。"""
    try:
        row, payload = await get_eia_library_service().download(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在（或源文件已丢失）")
    headers = {"Content-Disposition": f'attachment; filename="{row.original_filename}"'}
    if isinstance(payload, bytes):
        return Response(content=payload, media_type=row.content_type or "application/octet-stream", headers=headers)
    return FileResponse(
        path=payload, filename=row.original_filename, media_type=row.content_type or "application/octet-stream"
    )


@domain_factory.patch("/eia/library/files/{file_id}")
async def move_eia_library_file(
    file_id: int,
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """移动文件夹（folder_id=null 移出为未归类）。"""
    folder_id = body.get("folder_id")
    if folder_id is not None and not isinstance(folder_id, int):
        raise HTTPException(status_code=400, detail="folder_id 须为整数或 null")
    try:
        return await get_eia_library_service().move(file_id, folder_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.delete("/eia/library/files/{file_id}")
async def delete_eia_library_file(
    file_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除（DB 记录与 MinIO 两对象/存量本地卷文件同删）。"""
    try:
        await get_eia_library_service().delete(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"success": True}


@domain_factory.post("/eia/library/admin/migrate-storage")
async def migrate_eia_library_storage(current_user: User = Depends(get_admin_user)) -> dict[str, Any]:
    """存量本地卷 → MinIO 一次性迁移（幂等；docx 顺带回填 canonical md）。"""
    result = await get_eia_library_service().migrate_storage_to_minio(current_user.username)
    return {"success": True, **result}


@domain_factory.post("/eia/library/files/{file_id}/md")
async def get_eia_library_file_md(
    file_id: int,
    current_user: User = Depends(get_required_user),
) -> Response:
    """canonical md 预览（text/markdown）。"""
    try:
        _, data = await get_eia_library_service().get_canonical_md(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="canonical md 不存在")
    return Response(content=data, media_type="text/markdown; charset=utf-8")


@domain_factory.post("/eia/library/files/{file_id}/regenerate-md")
async def regenerate_eia_library_md(
    file_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """重产 canonical md（failed 行手工修复）。"""
    try:
        return await get_eia_library_service().regenerate_md(file_id, current_user.username)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.patch("/eia/library/files/{file_id}/meta")
async def update_eia_library_file_meta(
    file_id: int,
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """stage/mineral 行内编辑（白名单 + 值域守卫）。"""
    fields = {k: body[k] for k in ("stage", "mineral") if k in body}
    if not fields:
        raise HTTPException(status_code=400, detail="无可更新字段")
    try:
        return await get_eia_library_service().update_meta(file_id, fields)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.get("/eia/library/kb/binding")
async def get_eia_corpus_kb_binding(current_user: User = Depends(get_required_user)) -> dict[str, Any]:
    """当前绑定的环评语料知识库（未绑定为空串）。"""
    return {"kb_id": await eia_corpus_tasks.get_bound_kb_id()}


@domain_factory.post("/eia/library/kb/bind")
async def bind_eia_corpus_kb(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """绑定环评语料目标知识库（存在性校验 → system_options.eia_corpus_kb_id）。"""
    try:
        kb_id = await eia_corpus_tasks.bind_corpus_kb(body.get("kb_id") or "", current_user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "kb_id": kb_id}


@domain_factory.post("/eia/library/push-kb")
async def push_eia_library_to_kb(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """推送 canonical md 到绑定 KB（后台任务；body: {file_ids: [int]}）。"""
    file_ids = body.get("file_ids")
    if not isinstance(file_ids, list) or not file_ids:
        raise HTTPException(status_code=400, detail="file_ids 不能为空")
    task = await tasker.enqueue(
        name="环评语料推送知识库",
        task_type="eia_corpus_push",
        payload={"file_ids": file_ids, "operator_id": current_user.uid},
    )
    return {"status": "queued", "task_id": task.id}


@domain_factory.post("/eia/library/process")
async def process_eia_library(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """P2 语料加工/全库重编译（后台任务；body: {file_ids?: [int], scope?: "all"}）。"""
    payload: dict[str, Any] = {"operator_id": current_user.uid}
    if body.get("scope") == "all":
        payload["scope"] = "all"
    elif isinstance(body.get("file_ids"), list) and body["file_ids"]:
        payload["file_ids"] = body["file_ids"]
    else:
        raise HTTPException(status_code=400, detail="须提供 file_ids 或 scope=all")
    task = await tasker.enqueue(name="环评语料加工", task_type="eia_corpus_process", payload=payload)
    return {"status": "queued", "task_id": task.id}


@domain_factory.post("/eia/library/admin/bootstrap-manifest")
async def bootstrap_eia_library_manifest(
    file: UploadFile = File(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """既有 manifest.json 导入：按 file_name 匹配登记 → 回填 report_id/stage/mineral（D6 人工裁决保留）。"""
    import json as _json

    try:
        manifest = _json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"manifest.json 非法: {e}")
    try:
        result = await get_eia_library_service().bootstrap_from_manifest(manifest, current_user.username)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, **result}


# =============================================================================
# EIA Standard Reviews (环评标准条目人工核实：无 import 初始态即文件态 + 导出翻转)
# =============================================================================


@domain_factory.get("/eia/standards")
async def list_eia_standards(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """62 条标准总览（文件态只读 + DB 裁决合并 + 语料引用数 + counts 汇总）"""
    try:
        return await get_eia_standard_service().list_standards()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to list eia standards: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取标准总览失败: {str(e)}")


@domain_factory.get("/eia/standards/limits")
async def list_eia_standard_limits(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """limit_tables：文件态 + DB 录入行合并（source: db|file）+ 行结构 schemas（供前端渲染编辑表格）"""
    try:
        return await get_eia_standard_service().list_limit_tables()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"coal-eia-writer 技能数据缺失: {e}")
    except Exception as e:
        logger.error(f"Failed to list eia standard limits: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取限值表失败: {str(e)}")


@domain_factory.put("/eia/standards/limits/{table_key}/rows")
async def save_eia_standard_limit_rows(
    table_key: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """限值行整表替换落库（DB 即导出真源）：{rows: [...]}；未知表 404，载荷越界 400"""
    try:
        result = await get_eia_standard_service().save_limit_rows(table_key, payload.get("rows"), current_user.username)
        return {"success": True, **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to save eia limit rows {table_key}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存限值行失败: {str(e)}")


@domain_factory.post("/eia/standards/limits/export")
async def export_eia_standard_limit_rows(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """DB → standards_index.json（已录入表整表替换 rows + 翻转 nv/verified，round-trip 纪律；admin）"""
    try:
        result = await get_eia_standard_service().export_limit_rows(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia limit rows: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出限值行失败: {str(e)}")


@domain_factory.put("/eia/standards/review")
async def set_eia_standard_review(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """核实裁决落库（upsert）：{code, action: 'confirm', note?}；code 走 body——
    注册表 10/62 条编号含 `/`（GB/T、HJ/T 等），uvicorn 路由匹配前解码 %2F，
    路径参数 {code} 段无法跨越内部斜杠，恒 404（对抗评审实证）。code 不在注册表 404，载荷越界 400"""
    code = payload.get("code")
    if not isinstance(code, str) or not code:
        raise HTTPException(status_code=400, detail="code 须为非空字符串")
    body = {k: v for k, v in payload.items() if k != "code"}
    try:
        row = await get_eia_standard_service().set_review(code, body, current_user.username)
        return {"success": True, "review": row}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set eia standard review {code}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存标准核实裁决失败: {str(e)}")


@domain_factory.post("/eia/standards/export")
async def export_eia_standard_reviews(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """DB → standards_index.json（仅翻转被裁决条目两标志，round-trip 字节纪律；admin）"""
    try:
        result = await get_eia_standard_service().export_reviews(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia standard reviews: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出标准核实裁决失败: {str(e)}")


# =============================================================================
# EIA Sections & Stage Forms (环评节级明细只读 + stages forms 口径字段人工裁决)
# =============================================================================


@domain_factory.get("/eia/expectations/sections")
async def list_eia_sections(
    stage: str = Query(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """节级明细只读视图（P2-2）：节键自然序展平 + unmapped 附带。"""
    try:
        return await run_in_threadpool(get_sections, stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list eia sections {stage}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取节级明细失败: {str(e)}")


@domain_factory.get("/eia/expectations/data")
async def get_eia_data_expectations(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """备料清单只读视图（P2-4）：per_chapter 分章数据族 + source_hint 词表。"""
    try:
        return await run_in_threadpool(get_data_expectations)
    except Exception as e:
        logger.error(f"Failed to get eia data expectations: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取备料清单失败: {str(e)}")


@domain_factory.get("/eia/standards/gate1")
async def get_eia_gate1_checks(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """门 1 体检卡（P2-3 只读）：规则规格 + 注册表自检。"""
    try:
        return await get_eia_standard_service().get_gate1_checks()
    except Exception as e:
        logger.error(f"Failed to get eia gate1 checks: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取门 1 体检数据失败: {str(e)}")


@domain_factory.get("/eia/stages/forms")
async def list_eia_stage_forms(
    stage: str | None = Query(None),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """stages forms 口径字段合并态（P2-1）：文件锚点 + DB 裁决（add 追加/amend 覆盖层标注）。"""
    try:
        return await get_eia_stage_service().list_stage_forms(stage)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list eia stage forms: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取口径字段失败: {str(e)}")


@domain_factory.put("/eia/stages/forms/{stage}/{family_key}/fields")
async def save_eia_stage_field(
    stage: str,
    family_key: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """口径字段人工裁决落库（add 新增/amend 改 label、required；name 禁改）。"""
    try:
        result = await get_eia_stage_service().save_stage_field(stage, family_key, payload, current_user.username)
        return {"success": True, **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to save eia stage field {stage}/{family_key}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存口径字段裁决失败: {str(e)}")


@domain_factory.delete("/eia/stages/forms/{stage}/{family_key}/fields/{field_name}")
async def delete_eia_stage_field(
    stage: str,
    family_key: str,
    field_name: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """撤回未物化口径字段裁决行（仅草稿态；文件锚点不受影响）。"""
    try:
        return await get_eia_stage_service().delete_stage_field(stage, family_key, field_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to delete eia stage field {stage}/{family_key}/{field_name}: {e}\n{traceback.format_exc()}"
        )
        raise HTTPException(status_code=500, detail=f"撤回口径字段裁决失败: {str(e)}")


@domain_factory.post("/eia/stages/forms/export")
async def export_eia_stage_forms(
    stage: str | None = Query(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """DB 裁决 → stages/<stage>.json 文本级插接物化（字节纪律；幂等；admin）"""
    try:
        result = await get_eia_stage_service().export_stage_forms(stage, current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia stage forms: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出口径字段裁决失败: {str(e)}")


# =============================================================================
# EIA Formulas (环评公式参数参考值运营层：DB 覆盖层 + 导出物化 formulas.json)
# =============================================================================


@domain_factory.get("/eia/formulas")
async def list_eia_formulas(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """公式参数合并态（P3-1）：文件锚点 + DB 覆盖（value/note/pending）；expr/derived_slots 恒只读。"""
    try:
        return await get_eia_formula_service().list_formulas()
    except Exception as e:
        logger.error(f"Failed to list eia formulas: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取公式参数失败: {str(e)}")


@domain_factory.put("/eia/formulas/{formula_id}/inputs/{input_name}")
async def set_eia_formula_input_value(
    formula_id: str,
    input_name: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """参数参考值裁决落库（仅 user_input；同键覆盖）。"""
    try:
        result = await get_eia_formula_service().set_input_value(
            formula_id,
            input_name,
            payload.get("value"),
            payload.get("note"),
            current_user.username,
        )
        return {"success": True, **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set eia formula value {formula_id}.{input_name}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存参数参考值失败: {str(e)}")


@domain_factory.delete("/eia/formulas/{formula_id}/inputs/{input_name}")
async def clear_eia_formula_input_value(
    formula_id: str,
    input_name: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """撤回参数覆盖行（文件锚点不受影响）。"""
    try:
        cleared = await get_eia_formula_service().clear_input_value(formula_id, input_name)
        return {"success": cleared}
    except Exception as e:
        logger.error(f"Failed to clear eia formula value {formula_id}/{input_name}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤回参数参考值失败: {str(e)}")


@domain_factory.post("/eia/formulas/export")
async def export_eia_formulas(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """DB 覆盖 → formulas.json 行级插接物化（字节纪律；幂等；admin）"""
    try:
        result = await get_eia_formula_service().export_formulas(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia formulas: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出公式参数失败: {str(e)}")


# =============================================================================
# EIA Paradigms (写作范式层：DB 草稿唯一真相 + admin 导出物化回写 references/paradigms/*)
# =============================================================================


@domain_factory.get("/eia/paradigms")
async def list_eia_paradigms(current_user: User = Depends(get_required_user)) -> dict[str, Any]:
    """范式层概览：4 md + 3 family 草稿态/漂移 + 角色挂载计数 + _roles 全映射（只读）"""
    try:
        return {"success": True, **await get_eia_paradigm_service().load_overview()}
    except Exception as e:
        logger.error(f"Failed to list eia paradigms: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取范式层概览失败: {str(e)}")


@domain_factory.get("/eia/paradigms/{kind}/{asset_id}")
async def get_eia_paradigm_asset(
    kind: str, asset_id: str, current_user: User = Depends(get_required_user)
) -> dict[str, Any]:
    """单资产：md 全文（草稿在则附草稿）/ family 四键（草稿值在 draft.content）"""
    try:
        return {"success": True, **await get_eia_paradigm_service().get_asset(kind, asset_id)}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get eia paradigm {kind}/{asset_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取范式资产失败: {str(e)}")


@domain_factory.put("/eia/paradigms/{kind}/{asset_id}/draft")
async def save_eia_paradigm_draft(
    kind: str,
    asset_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """保存草稿（登录用户）：md 整文件 / 仅 desc+templates 两键，其余键拒收；upsert"""
    try:
        return {
            "success": True,
            **await get_eia_paradigm_service().save_draft(kind, asset_id, payload, current_user.username),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to save eia paradigm draft {kind}/{asset_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存草稿失败: {str(e)}")


@domain_factory.delete("/eia/paradigms/{kind}/{asset_id}/draft")
async def withdraw_eia_paradigm_draft(
    kind: str, asset_id: str, current_user: User = Depends(get_required_user)
) -> dict[str, Any]:
    """撤回草稿（删行，文件锚点不受影响）"""
    try:
        ok = await get_eia_paradigm_service().withdraw_draft(kind, asset_id)
        return {"success": True, "withdrawn": ok}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to withdraw eia paradigm draft {kind}/{asset_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤回草稿失败: {str(e)}")


@domain_factory.post("/eia/paradigms/export/preview")
async def preview_eia_paradigm_export(current_user: User = Depends(get_required_user)) -> dict[str, Any]:
    """写前校验 + difflib diff（不写盘）"""
    try:
        return {"success": True, **await get_eia_paradigm_service().preview_export()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to preview eia paradigm export: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出预览失败: {str(e)}")


@domain_factory.post("/eia/paradigms/export")
async def export_eia_paradigms(current_user: User = Depends(get_admin_user)) -> dict[str, Any]:
    """DB 草稿 → references/paradigms/* 物化（validate-all-then-write；字节纪律；admin）"""
    try:
        result = await get_eia_paradigm_service().export_paradigms(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia paradigms: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出范式失败: {str(e)}")


# =============================================================================
# EIA Entities (环评样例实体注册表补充：仅添加 + 导出物化 registry + _index)
# =============================================================================


@domain_factory.get("/eia/entities/samples")
async def list_eia_entity_samples(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """样例清单（P3-2 只读）：_index samples + skipped 透出。"""
    try:
        return await get_eia_entity_service().list_samples()
    except Exception as e:
        logger.error(f"Failed to list eia entity samples: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取样例清单失败: {str(e)}")


@domain_factory.get("/eia/entities/{slug}")
async def get_eia_entity_registry(
    slug: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """单样例注册表合并态（锚点条目 + DB 待导出补充 pending 标注）。"""
    try:
        return await get_eia_entity_service().get_registry(slug)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get eia entity registry {slug}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取实体注册表失败: {str(e)}")


@domain_factory.put("/eia/entities/{slug}/items")
async def add_eia_entity(
    slug: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """实体补充落库（仅添加：etype/name/rid?/note?；锚点与待导出重复即拒）。"""
    try:
        result = await get_eia_entity_service().add_entity(
            slug,
            payload.get("etype"),
            payload.get("name"),
            payload.get("rid"),
            payload.get("note"),
            current_user.username,
        )
        return {"success": True, **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add eia entity {slug}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"补充实体失败: {str(e)}")


@domain_factory.delete("/eia/entities/items/{addition_id}")
async def withdraw_eia_entity(
    addition_id: int,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """撤回 DB 实体补充行（文件锚点不受影响）。"""
    try:
        cleared = await get_eia_entity_service().withdraw_entity(addition_id)
        return {"success": cleared}
    except Exception as e:
        logger.error(f"Failed to withdraw eia entity {addition_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤回实体补充失败: {str(e)}")


@domain_factory.post("/eia/entities/export")
async def export_eia_entities(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """DB 补充 → registry 数组尾追加 + _index counts（字节纪律；幂等；admin）"""
    try:
        result = await get_eia_entity_service().export_entities(current_user.username)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export eia entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出实体补充失败: {str(e)}")


# =============================================================================
# EIA Datasets (环评数据集只读抽屉：attachment_checklist / consistency_contracts / depth_targets)
# =============================================================================


@domain_factory.get("/eia/datasets/{key}/view")
async def view_eia_dataset(
    key: str,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """三数据集只读抽屉数据通道（P3-3）。"""
    try:
        return await run_in_threadpool(get_dataset_view, key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to view eia dataset {key}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取数据集视图失败: {str(e)}")
