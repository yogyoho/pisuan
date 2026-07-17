"""标准规范库 API - /api/regulation-library/*"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from server.utils.auth_middleware import get_admin_user
from yuxi.extensions.regulation_library import enrichment_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

regulation_library = APIRouter(prefix="/regulation-library", tags=["Regulation Library"])


@regulation_library.post("/enrich")
async def enrich_file(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """对已入库的规范文档执行富化（条款解析+指标提取+建图）"""
    try:
        kb_id = payload.get("kb_id", "")
        file_id = payload.get("file_id", "")
        doc_code = payload.get("doc_code", "")
        doc_name = payload.get("doc_name", "")
        doc_type = payload.get("doc_type", "technical_standard")
        if not kb_id or not file_id or not doc_code:
            raise HTTPException(status_code=400, detail="kb_id/file_id/doc_code 必填")
        result = await enrichment_service.enrich_regulation_file(kb_id, file_id, doc_code, doc_name, doc_type)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"规范富化失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"富化失败: {str(e)}")


@regulation_library.get("/indicators")
async def list_indicators(
    doc_code: str | None = Query(None),
    pollutant: str | None = Query(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """精确查询标准指标"""
    try:
        rows = await enrichment_service.query_indicators(doc_code, pollutant)
        return {"items": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"指标查询失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
