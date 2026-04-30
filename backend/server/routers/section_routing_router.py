"""Section Routing API Router - 章节路由配置"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from server.utils.auth_middleware import get_admin_user
from yuxi.services.domain_factory_service import get_domain_factory_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

section_routing = APIRouter(prefix="/section-routing", tags=["Section Routing"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SectionCreate(BaseModel):
    """创建章节请求模型"""
    code: str = Field(..., description="章节唯一标识码", min_length=1, max_length=128)
    title: str = Field(..., description="章节标题", min_length=1, max_length=500)
    section_path: str = Field(..., description="章节路径（如1.1）", min_length=1, max_length=50)
    level: int | None = Field(None, description="章节层级（1-5）", ge=1, le=5)
    domain: str = Field(..., description="领域代码", min_length=1, max_length=64)
    report_type: str = Field(..., description="报告类型", min_length=1, max_length=64)
    parent_id: int | None = Field(None, description="父章节ID")
    standard_code: str | None = Field(None, description="绑定的StandardCode", max_length=128)
    match_confidence: int | None = Field(None, description="匹配置信度（0-100）", ge=0, le=100)
    sort_order: int = Field(0, description="同级排序序号")
    template_data: dict[str, Any] | None = Field(None, description="模板相关配置")
    context_routing: dict[str, Any] | None = Field(None, description="上下文路由配置")
    writing_guidance: dict[str, Any] | None = Field(None, description="章节编写要点")
    entity_bindings: list[dict[str, Any]] | None = Field(None, description="领域实体绑定列表")


class SectionUpdate(BaseModel):
    """更新章节请求模型"""
    title: str | None = Field(None, description="章节标题", min_length=1, max_length=500)
    section_path: str | None = Field(None, description="章节路径", min_length=1, max_length=50)
    level: int | None = Field(None, description="章节层级", ge=1, le=5)
    parent_id: int | None = Field(None, description="父章节ID")
    standard_code: str | None = Field(None, description="绑定的StandardCode", max_length=128)
    match_confidence: int | None = Field(None, description="匹配置信度", ge=0, le=100)
    sort_order: int | None = Field(None, description="同级排序序号")
    template_data: dict[str, Any] | None = Field(None, description="模板相关配置")
    context_routing: dict[str, Any] | None = Field(None, description="上下文路由配置")
    writing_guidance: dict[str, Any] | None = Field(None, description="章节编写要点")
    entity_bindings: list[dict[str, Any]] | None = Field(None, description="领域实体绑定列表")


class StandardCodeBinding(BaseModel):
    """StandardCode 绑定请求"""
    standard_code: str = Field(..., description="StandardCode")
    mount_type: str = Field("direct", description="挂载类型: direct/inherit")


class MatchStandardCodeRequest(BaseModel):
    """匹配 StandardCode 请求"""
    title: str = Field(..., description="章节标题")
    section_path: str = Field(..., description="章节路径")
    level: int = Field(..., description="章节层级", ge=1, le=5)
    content_sample: str | None = Field(None, description="内容样本")


class BatchGetSectionsRequest(BaseModel):
    """批量获取章节请求"""
    section_ids: list[int] = Field(..., description="章节ID列表", min_length=1, max_length=100)


# =============================================================================
# Section Tree Endpoints
# =============================================================================


@section_routing.get("/sections/tree")
async def get_section_tree(
    domain: str | None = Query(None, description="领域代码"),
    report_type: str | None = Query(None, description="报告类型"),
    is_template: bool = Query(True, description="是否为模板库配置"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取章节树"""
    try:
        service = get_domain_factory_service()
        # 如果没有提供 domain 和 report_type，使用默认值
        if not domain:
            domain = "coal"
        if not report_type:
            report_type = "eia_report"
        sections = await service.get_context_sections_tree(domain, report_type, is_template)
        return {"sections": sections}
    except Exception as e:
        logger.error(f"Failed to get section tree: {e}")
        raise HTTPException(status_code=500, detail=f"获取章节树失败: {str(e)}")


@section_routing.get("/sections/{section_id}")
async def get_section_detail(
    section_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取章节详情"""
    try:
        service = get_domain_factory_service()
        section = await service.get_section_detail(section_id)
        if not section:
            raise HTTPException(status_code=404, detail="章节不存在")
        return section
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get section detail: {e}")
        raise HTTPException(status_code=500, detail=f"获取章节详情失败: {str(e)}")


# =============================================================================
# Section CRUD Endpoints
# =============================================================================


@section_routing.post("/sections")
async def create_section(
    section_data: SectionCreate,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """创建章节"""
    try:
        service = get_domain_factory_service()
        section = await service.create_section(
            code=section_data.code,
            title=section_data.title,
            section_path=section_data.section_path,
            level=section_data.level,
            domain=section_data.domain,
            report_type=section_data.report_type,
            parent_id=section_data.parent_id,
            standard_code=section_data.standard_code,
            match_confidence=section_data.match_confidence,
            sort_order=section_data.sort_order,
            template_data=section_data.template_data,
            context_routing=section_data.context_routing,
            writing_guidance=section_data.writing_guidance,
            entity_bindings=section_data.entity_bindings,
            user=current_user.username if current_user else None,
        )
        return {"success": True, "section": section}
    except Exception as e:
        logger.error(f"Failed to create section: {e}")
        raise HTTPException(status_code=500, detail=f"创建章节失败: {str(e)}")


@section_routing.put("/sections/{section_id}")
async def update_section(
    section_id: int,
    section_data: SectionUpdate,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新章节"""
    try:
        service = get_domain_factory_service()
        section = await service.update_section(
            section_id=section_id,
            title=section_data.title,
            section_path=section_data.section_path,
            level=section_data.level,
            parent_id=section_data.parent_id,
            standard_code=section_data.standard_code,
            match_confidence=section_data.match_confidence,
            sort_order=section_data.sort_order,
            template_data=section_data.template_data,
            context_routing=section_data.context_routing,
            writing_guidance=section_data.writing_guidance,
            entity_bindings=section_data.entity_bindings,
        )
        if not section:
            raise HTTPException(status_code=404, detail="章节不存在")
        return {"success": True, "section": section}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update section: {e}")
        raise HTTPException(status_code=500, detail=f"更新章节失败: {str(e)}")


@section_routing.delete("/sections/{section_id}")
async def delete_section(
    section_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除章节"""
    try:
        service = get_domain_factory_service()
        success = await service.delete_section(section_id)
        if not success:
            raise HTTPException(status_code=404, detail="章节不存在")
        return {"success": True, "message": "章节已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete section: {e}")
        raise HTTPException(status_code=500, detail=f"删除章节失败: {str(e)}")


# =============================================================================
# Batch Operations
# =============================================================================


@section_routing.post("/sections/batch")
async def batch_get_sections(
    batch_request: BatchGetSectionsRequest,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """批量获取章节"""
    try:
        service = get_domain_factory_service()
        sections = await service.batch_get_sections(batch_request.section_ids)
        return {
            "sections": sections,
            "total": len(sections),
            "found": len(sections),
        }
    except Exception as e:
        logger.error(f"Failed to batch get sections: {e}")
        raise HTTPException(status_code=500, detail=f"批量获取章节失败: {str(e)}")


# =============================================================================
# Section Context Endpoints
# =============================================================================


@section_routing.put("/contexts/{domain}/{report_type}/sections")
async def update_context_sections(
    domain: str,
    report_type: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新上下文章节结构"""
    try:
        service = get_domain_factory_service()
        sections = payload.get("sections", [])
        result = await service.update_context_sections(domain, report_type, sections)
        return {"success": True, "sections": result.get("sections", [])}
    except Exception as e:
        logger.error(f"Failed to update context sections: {e}")
        raise HTTPException(status_code=500, detail=f"更新章节失败: {str(e)}")


# =============================================================================
# StandardCode Binding Endpoints
# =============================================================================


@section_routing.get("/sections/{section_id}/standard-codes")
async def get_section_standard_codes(
    section_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取章节绑定的 StandardCodes"""
    try:
        service = get_domain_factory_service()
        codes = await service.get_section_standard_codes(section_id)
        return {"codes": codes}
    except Exception as e:
        logger.error(f"Failed to get section standard codes: {e}")
        raise HTTPException(status_code=500, detail=f"获取StandardCode失败: {str(e)}")


@section_routing.post("/sections/{section_id}/standard-codes")
async def bind_standard_code(
    section_id: int,
    binding: StandardCodeBinding,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """绑定 StandardCode 到章节"""
    try:
        service = get_domain_factory_service()
        success = await service.bind_section_standard_code(
            section_id, binding.standard_code, binding.mount_type
        )
        return {"success": success, "message": "绑定成功"}
    except Exception as e:
        logger.error(f"Failed to bind standard code: {e}")
        raise HTTPException(status_code=500, detail=f"绑定StandardCode失败: {str(e)}")


@section_routing.delete("/sections/{section_id}/standard-codes/{standard_code}")
async def unbind_standard_code(
    section_id: int,
    standard_code: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """解绑 StandardCode"""
    try:
        service = get_domain_factory_service()
        success = await service.unbind_section_standard_code(section_id, standard_code)
        return {"success": success, "message": "解绑成功"}
    except Exception as e:
        logger.error(f"Failed to unbind standard code: {e}")
        raise HTTPException(status_code=500, detail=f"解绑StandardCode失败: {str(e)}")


# =============================================================================
# StandardCode Matching
# =============================================================================


@section_routing.post("/standard-codes/match")
async def match_standard_codes(
    request: MatchStandardCodeRequest,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """匹配 StandardCodes"""
    try:
        service = get_domain_factory_service()
        matches = await service.match_standard_codes(
            title=request.title,
            section_path=request.section_path,
            level=request.level,
            content_sample=request.content_sample,
        )
        return {"matches": matches}
    except Exception as e:
        logger.error(f"Failed to match standard codes: {e}")
        raise HTTPException(status_code=500, detail=f"匹配StandardCode失败: {str(e)}")


# =============================================================================
# Export/Import
# =============================================================================


@section_routing.get("/export")
async def export_sections(
    domain: str = Query(..., description="领域代码"),
    report_type: str = Query(..., description="报告类型"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """导出章节配置"""
    try:
        service = get_domain_factory_service()
        export_data = await service.export_sections(domain, report_type)
        return export_data
    except Exception as e:
        logger.error(f"Failed to export sections: {e}")
        raise HTTPException(status_code=500, detail=f"导出章节失败: {str(e)}")


@section_routing.post("/import")
async def import_sections(
    domain: str = Query(..., description="领域代码"),
    report_type: str = Query(..., description="报告类型"),
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """导入章节配置"""
    try:
        service = get_domain_factory_service()
        sections = payload.get("sections", [])
        result = await service.import_sections(domain, report_type, sections)
        return result
    except Exception as e:
        logger.error(f"Failed to import sections: {e}")
        raise HTTPException(status_code=500, detail=f"导入章节失败: {str(e)}")
