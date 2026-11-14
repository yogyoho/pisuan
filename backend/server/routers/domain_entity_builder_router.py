"""Domain Entity Builder API Router - 领域实体构建器路由"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile

from server.utils.auth_middleware import get_admin_user
from yuxi.repositories.domain_entity_repository import EntityVersionConflict
from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from yuxi.services.domain_entity_service import get_entity_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

domain_entity_builder = APIRouter(prefix="/domain-entity-builder", tags=["Domain Entity Builder"])


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


@domain_entity_builder.get("/entities/trash")
async def list_trash_entities(
    domain_code: str | None = Query(None, description="按行业代码过滤"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """回收站：已软删实体列表（声明必须在 /entities/{identifier} 之前）"""
    try:
        service = get_entity_service()
        result = await service.list_trash(domain_code)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Failed to list trash entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取回收站失败: {e}")


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


@domain_entity_builder.get("/entities/{identifier}/usage")
async def get_entity_usage(
    identifier: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """实体引用影响面：模板/待审核任务/报告参数/区域事实的引用计数与明细"""
    try:
        service = get_entity_service()
        usage = await service.get_entity_usage(identifier)
        return {"success": True, "data": usage}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get entity usage {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取实体引用情况失败: {e}")


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
    """更新实体 Schema；expected_updated_at 用于乐观锁，force=True 表示确认覆盖"""
    try:
        service = get_entity_service()
        payload = dict(payload)
        expected_updated_at = payload.pop("expected_updated_at", None)
        force = bool(payload.pop("force", False))
        entity = await service.update_entity(identifier, payload, expected_updated_at=expected_updated_at, force=force)
        return {"success": True, "message": "实体更新成功", "data": entity}
    except EntityVersionConflict as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "ENTITY_VERSION_CONFLICT", "message": str(e)},
        )
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
    """删除实体 Schema（移入回收站，可恢复）"""
    try:
        service = get_entity_service()
        success = await service.delete_entity(identifier)
        if not success:
            raise HTTPException(status_code=404, detail=f"实体 {identifier} 不存在")
        return {"success": True, "message": "实体已移入回收站"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除实体失败: {e}")


@domain_entity_builder.post("/entities/{identifier}/restore")
async def restore_entity(
    identifier: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """从回收站恢复实体"""
    try:
        service = get_entity_service()
        entity = await service.restore_entity(identifier)
        return {"success": True, "message": "实体已恢复", "data": entity}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restore entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"恢复实体失败: {e}")


@domain_entity_builder.delete("/entities/{identifier}/purge")
async def purge_entity(
    identifier: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """彻底删除回收站实体（不可恢复）"""
    try:
        service = get_entity_service()
        success = await service.purge_entity(identifier)
        if not success:
            raise HTTPException(status_code=404, detail=f"实体 {identifier} 不存在")
        return {"success": True, "message": "实体已彻底删除"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to purge entity {identifier}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"彻底删除实体失败: {e}")


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
        domain_code = payload.get("domain_code", GENERAL_DOMAIN_CODE)
        if not entities:
            raise HTTPException(status_code=400, detail="请提供要导入的实体列表")
        service = get_entity_service()
        result = await service.save_extracted_entities(entities, domain_code)
        rejected = len(result["rejected"])
        message = f"导入完成：新增 {result['inserted']} 个实体，补充 {result['properties_added']} 个属性"
        if rejected:
            message += f"，{rejected} 条被拒绝"
        return {"success": True, "message": message, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import extracted entities: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导入提取实体失败: {e}")


# ========== Category Dictionary ==========


@domain_entity_builder.get("/categories")
async def list_categories(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """分类字典（含实体数与启用状态），按 sort_order 排序"""
    try:
        service = get_entity_service()
        return {"success": True, "data": await service.list_categories()}
    except Exception as e:
        logger.error(f"Failed to list categories: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取分类字典失败: {e}")


@domain_entity_builder.post("/categories")
async def create_category(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """新增分类（code 为实体 category 的存储值，只能小写 snake_case）"""
    try:
        service = get_entity_service()
        return {"success": True, "data": await service.create_category(payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create category: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"新增分类失败: {e}")


@domain_entity_builder.post("/categories/reorder")
async def reorder_categories(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """按给定 code 顺序重排分类（sort_order 记为 10/20/30…）"""
    try:
        codes = payload.get("codes") or []
        if not isinstance(codes, list) or not codes:
            raise HTTPException(status_code=400, detail="codes 不能为空")
        service = get_entity_service()
        return {"success": True, "data": await service.reorder_categories(codes)}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to reorder categories: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"分类排序失败: {e}")


@domain_entity_builder.put("/categories/{code}")
async def update_category(
    code: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新分类名称/描述/启用（code 不可改）"""
    try:
        service = get_entity_service()
        return {"success": True, "data": await service.update_category(code, payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update category {code}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新分类失败: {e}")


@domain_entity_builder.delete("/categories/{code}")
async def delete_category(
    code: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除分类（仅允许空分类，有实体时 400）"""
    try:
        service = get_entity_service()
        await service.delete_category(code)
        return {"success": True, "message": "分类已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete category {code}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除分类失败: {e}")


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
    dry_run: bool = Query(False, description="只计算新增/更新/拒绝，不写库"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """导入配置；dry_run 返回影响面供前端确认后再落库"""
    try:
        if "entity_schemas" not in config_data:
            raise HTTPException(status_code=400, detail="配置格式不正确，缺少 entity_schemas")
        service = get_entity_service()
        result = await service.import_all(config_data, dry_run=dry_run)
        message = f"新增 {result['created']} 个，更新 {result['updated']} 个"
        if result["rejected"]:
            message += f"，拒绝 {len(result['rejected'])} 个"
        if result["remapped_tasks"]:
            message += f"，重映射待审核任务 {result['remapped_tasks']} 个"
        return {
            "success": True,
            "message": f"{'预检' if dry_run else '导入'}完成：{message}",
            **result,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
                raise HTTPException(status_code=400, detail="无法解析文件编码，请使用 UTF-8 或 GBK 编码的文件")

        service = get_entity_service()
        result = await service.extract_entities_from_document(content=text, domain_code=domain_code)

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
