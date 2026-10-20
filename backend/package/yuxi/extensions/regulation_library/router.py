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
    except enrichment_service.StandardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
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


async def _set_verification(payload: dict[str, Any], verified: bool, username: str) -> dict[str, Any]:
    doc_code = str(payload.get("doc_code") or "").strip()
    unit_no = str(payload.get("unit_no") or "").strip()
    if not doc_code or not unit_no:
        raise HTTPException(status_code=400, detail="doc_code/unit_no 必填")
    try:
        updated = await enrichment_service.set_unit_verification(doc_code, unit_no, verified, username)
        return {"updated": updated}
    except HTTPException:
        raise
    except Exception as e:
        action = "核验" if verified else "撤销核验"
        logger.error(f"指标{action}失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{action}失败: {str(e)}")


@regulation_library.post("/indicators/verify")
async def verify_indicators(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """核验指定表单元（doc_code+unit_no）的全部指标行（enrich 重跑会重置核验态）"""
    return await _set_verification(payload, verified=True, username=current_user.username)


@regulation_library.post("/indicators/unverify")
async def unverify_indicators(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """撤销指定表单元的核验态"""
    return await _set_verification(payload, verified=False, username=current_user.username)


def _manual_meta_and_rows(payload: dict[str, Any]) -> tuple[str, str | None, list[Any]]:
    """手工标准载荷解析：返回 (doc_code, doc_name, rows)，越界即 400。

    doc_type 接收即忽略：无消费场景（YAGNI），不持久化。
    """
    doc_code = str(payload.get("doc_code") or "").strip()
    doc_name = str(payload.get("doc_name") or "").strip() or None
    rows = payload.get("rows")
    if not doc_code or not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="doc_code 与非空 rows 必填")
    return doc_code, doc_name, rows


@regulation_library.post("/manual-standards")
async def create_manual_standard(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """专家手工新建标准（行 born-verified 直入权威表，保存即核验生效）"""
    doc_code, doc_name, rows = _manual_meta_and_rows(payload)
    try:
        inserted = await enrichment_service.create_manual_standard(doc_code, doc_name, rows, current_user.username)
        return {"success": True, "doc_code": doc_code, "inserted": inserted}
    except enrichment_service.StandardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"手工标准创建失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@regulation_library.put("/manual-standards/{doc_code:path}")
async def update_manual_standard(
    doc_code: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """整标准替换手工行（事务内删旧插新，重插行 born-verified；仅 expert 行可替换）"""
    _, doc_name, rows = _manual_meta_and_rows(payload)
    try:
        inserted = await enrichment_service.replace_manual_standard(doc_code, doc_name, rows, current_user.username)
        return {"success": True, "doc_code": doc_code, "inserted": inserted}
    except enrichment_service.StandardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"手工标准替换失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"替换失败: {str(e)}")


@regulation_library.delete("/manual-standards/{doc_code:path}")
async def delete_manual_standard(
    doc_code: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除该标准全部手工行（enrich 行拒删；删除后 lookup 立即失效且不可撤销）"""
    try:
        deleted = await enrichment_service.delete_manual_standard(doc_code)
        return {"success": True, "doc_code": doc_code, "deleted": deleted}
    except enrichment_service.StandardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"手工标准删除失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
