"""Domain Factory API Router - 领域知识工厂路由"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile

from server.utils.auth_middleware import get_admin_user
from yuxi.services.domain_factory_service import get_domain_factory_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

domain_factory = APIRouter(prefix="/domain-factory", tags=["Domain Factory"])


# =============================================================================
# Domain Management
# =============================================================================


@domain_factory.get("/domains")
async def get_domains(
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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


@domain_factory.post("/tasks/{task_id}/commit")
async def commit_task(
    task_id: str,
    payload: dict[str, Any] = Body({}),
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """查询图谱中的法律引用，支持按 scope 过滤"""
    try:
        service = get_domain_factory_service()
        result = await service.query_graph_legal_references(scope, limit)
        return result
    except Exception as e:
        logger.error(f"Failed to query legal references: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"法律引用查询失败: {str(e)}")
