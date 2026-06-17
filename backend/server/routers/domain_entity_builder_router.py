"""Domain Entity Builder API Router - 领域实体构建器路由"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile

from server.utils.auth_middleware import get_admin_user
from yuxi.services.domain_entity_service import get_entity_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

domain_entity_builder = APIRouter(
    prefix="/domain-entity-builder", tags=["Domain Entity Builder"]
)


# ========== Taxonomy ==========

@domain_entity_builder.get("/taxonomy")
async def get_taxonomy(
    domain_code: str | None = Query(None, description="行业代码，如 coal/chem/transport"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取分类体系结构（4大领域 + 实体分类），可按行业过滤"""
    try:
        service = get_entity_service()
        taxonomy = await service.get_taxonomy(domain_code)
        return {"success": True, "data": taxonomy}
    except Exception as e:
        logger.error(f"Failed to get taxonomy: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取分类体系失败: {e}")


# ========== Domains ==========

@domain_entity_builder.get("/domains")
async def list_domains(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """列出已被实体引用的行业代码"""
    try:
        service = get_entity_service()
        domains = await service.get_domains_in_use()
        return {"success": True, "data": domains}
    except Exception as e:
        logger.error(f"Failed to list domains: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取行业列表失败: {e}")


# ========== Report Types ==========

@domain_entity_builder.get("/report-types")
async def list_report_types(
    domain_code: str | None = Query(None, description="按行业代码过滤"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取报告类型字典列表"""
    try:
        service = get_entity_service()
        report_types = await service.list_report_types(domain_code)
        return {"success": True, "data": report_types}
    except Exception as e:
        logger.error(f"Failed to list report types: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取报告类型失败: {e}")


# ========== Entity CRUD ==========

@domain_entity_builder.get("/entities")
async def list_entities(
    category: str | None = Query(None, description="按分类过滤"),
    domain_code: str | None = Query(None, description="按行业代码过滤"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取实体 Schema 列表，可按分类/行业过滤"""
    try:
        service = get_entity_service()
        result = await service.list_entities(category, domain_code)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Failed to list entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取实体列表失败: {e}")


@domain_entity_builder.get("/entities/{identifier}")
async def get_entity(
    identifier: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取单个实体 Schema 详情（支持 entity_id 或 entity_key）"""
    try:
        service = get_entity_service()
        entity = await service.get_entity(identifier)
        if not entity:
            raise HTTPException(status_code=404, detail=f"实体 {identifier} 不存在")
        return {"success": True, "data": entity}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取实体失败: {e}")


@domain_entity_builder.post("/entities")
async def create_entity(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """创建新的实体 Schema"""
    try:
        service = get_entity_service()
        entity = await service.create_entity(payload)
        return {"success": True, "message": "实体创建成功", "data": entity}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create entity: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建实体失败: {e}")


@domain_entity_builder.put("/entities/{identifier}")
async def update_entity(
    identifier: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新实体 Schema"""
    try:
        service = get_entity_service()
        entity = await service.update_entity(identifier, payload)
        return {"success": True, "message": "实体更新成功", "data": entity}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新实体失败: {e}")


@domain_entity_builder.delete("/entities/{identifier}")
async def delete_entity(
    identifier: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除实体 Schema"""
    try:
        service = get_entity_service()
        success = await service.delete_entity(identifier)
        if not success:
            raise HTTPException(status_code=404, detail=f"实体 {identifier} 不存在")
        return {"success": True, "message": "实体删除成功"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除实体失败: {e}")


@domain_entity_builder.post("/entities/batch-delete")
async def batch_delete_entities(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """批量删除实体 Schema"""
    try:
        identifiers = payload.get("identifiers", [])
        if not identifiers:
            raise HTTPException(status_code=400, detail="请提供要删除的实体标识列表")
        service = get_entity_service()
        count = await service.delete_entities_batch(identifiers)
        return {"success": True, "message": f"批量删除成功，共 {count} 个实体", "count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch delete entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"批量删除失败: {e}")


@domain_entity_builder.post("/entities/{identifier}/clone")
async def clone_entity(
    identifier: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """克隆实体 Schema"""
    try:
        new_key = payload.get("entity_key")
        new_name = payload.get("name_cn")
        if not new_key or not new_name:
            raise HTTPException(status_code=400, detail="entity_key 和 name_cn 不能为空")
        service = get_entity_service()
        entity = await service.clone_entity(identifier, new_key, new_name)
        return {"success": True, "message": "实体克隆成功", "data": entity}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to clone entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"克隆实体失败: {e}")


@domain_entity_builder.post("/entities/import-extracted")
async def import_extracted_entities(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """保存用户确认的 AI 提取实体"""
    try:
        entities = payload.get("entities", [])
        domain_code = payload.get("domain_code", "coal")
        if not entities:
            raise HTTPException(status_code=400, detail="请提供要导入的实体列表")
        service = get_entity_service()
        result = await service.save_extracted_entities(entities, domain_code)
        return {
            "success": True,
            "message": f"导入完成：新增 {result['inserted']} 个，更新 {result['updated']} 个",
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import extracted entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导入提取实体失败: {e}")


# ========== Import / Export ==========

@domain_entity_builder.get("/export")
async def export_config(
    domain_code: str | None = Query(None, description="按行业导出，为空则导出全部"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """导出完整配置"""
    try:
        service = get_entity_service()
        config = await service.export_all(domain_code)
        return {"success": True, "data": config}
    except Exception as e:
        logger.error(f"Failed to export config: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出配置失败: {e}")


@domain_entity_builder.post("/import")
async def import_config(
    config_data: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """导入配置"""
    try:
        if "entity_schemas" not in config_data:
            raise HTTPException(status_code=400, detail="配置格式不正确，缺少 entity_schemas")
        service = get_entity_service()
        count = await service.import_all(config_data)
        return {"success": True, "message": f"配置导入成功，共 {count} 个实体", "count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import config: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导入配置失败: {e}")


# ========== AI Extraction ==========

@domain_entity_builder.post("/extract")
async def extract_entities(
    file: UploadFile = File(...),
    domain_code: str = Form(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """上传报告文档，AI 自动提取领域实体对象"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        file_content = await file.read()
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")

        try:
            text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = file_content.decode("gbk")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400, detail="无法解析文件编码，请使用 UTF-8 或 GBK 编码的文件"
                )

        service = get_entity_service()
        result = await service.extract_entities_from_document(
            content=text, domain_code=domain_code
        )

        return {
            "success": True,
            "data": result,
            "file_name": file.filename,
            "domain_code": domain_code,
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to extract entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"实体提取失败: {e}")
