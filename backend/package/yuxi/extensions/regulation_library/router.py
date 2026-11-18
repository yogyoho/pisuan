"""标准规范库 API - /api/regulation-library/*"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from server.utils.auth_middleware import get_admin_user
from yuxi.extensions.regulation_library import enrichment_service
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

regulation_library = APIRouter(prefix="/regulation-library", tags=["Regulation Library"])


@regulation_library.get("/documents")
async def list_documents(
    kb_id: str | None = Query(None, description="标准规范库知识库 ID；省略时读取全局绑定"),
    keyword: str | None = Query(None),
    process_status: str | None = Query(None),
    run_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """列出规范文档、加工状态与指标分层统计。"""
    bound_kb_id = await enrichment_service.get_bound_kb_id()
    if kb_id and kb_id != bound_kb_id:
        raise HTTPException(status_code=400, detail="kb_id 与当前部署绑定的标准规范库不一致")
    try:
        resolved_kb_id = bound_kb_id
        if not resolved_kb_id:
            return {
                "kb_id": "",
                "bound": False,
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "summary": {
                    "documents": 0,
                    "enriched": 0,
                    "indexed": 0,
                    "empty": 0,
                    "indicators": 0,
                    "verified": 0,
                    "process_status_counts": {},
                    "run_status_counts": {},
                },
            }
        return await enrichment_service.list_regulation_documents(
            resolved_kb_id,
            keyword=keyword,
            process_status=process_status,
            run_status=run_status,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"规范文档列表查询失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"规范文档列表查询失败: {str(e)}")


@regulation_library.get("/kb/binding")
async def get_binding(current_user: User = Depends(get_admin_user)) -> dict[str, Any]:
    """读取当前部署绑定的标准规范库。"""
    return {"kb_id": await enrichment_service.get_bound_kb_id()}


@regulation_library.post("/kb/bind")
async def bind_knowledge_base(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """手动绑定当前部署的标准规范库。"""
    try:
        kb_id = await enrichment_service.bind_kb(payload.get("kb_id") or "", current_user.username)
        return {"success": True, "kb_id": kb_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"规范库绑定失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"规范库绑定失败: {str(e)}")


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
        bound_kb_id = await enrichment_service.get_bound_kb_id()
        if kb_id != bound_kb_id:
            raise HTTPException(status_code=400, detail="kb_id 与当前部署绑定的标准规范库不一致")
        run_id = await enrichment_service.start_enrich_run(
            kb_id,
            file_id,
            doc_code,
            doc_name,
            doc_type,
            current_user.username,
        )
        try:
            result = await enrichment_service.enrich_regulation_file(kb_id, file_id, doc_code, doc_name, doc_type)
        except enrichment_service.StandardConflictError as e:
            await enrichment_service.finish_enrich_run(run_id, "conflict", error_message=str(e))
            raise
        except Exception as e:
            await enrichment_service.finish_enrich_run(run_id, "failed", error_message=str(e))
            raise
        if "error" in result:
            error = str(result["error"])
            await enrichment_service.finish_enrich_run(run_id, "failed", error_message=error)
            raise HTTPException(status_code=400, detail=error)
        await enrichment_service.finish_enrich_run(run_id, "success", result=result)
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except enrichment_service.StandardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except enrichment_service.EnrichRunInProgressError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"规范富化失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"富化失败: {str(e)}")


@regulation_library.get("/documents/{file_id}/detail")
async def get_document_detail(
    kb_id: str = Query(..., description="标准规范库知识库 ID"),
    file_id: str = Path(..., description="规范文档文件 ID"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """返回单份规范的结构单元、表格分类、指标预览与运行历史。"""
    try:
        bound_kb_id = await enrichment_service.get_bound_kb_id()
        if kb_id != bound_kb_id:
            raise HTTPException(status_code=400, detail="kb_id 与当前部署绑定的标准规范库不一致")
        result = await enrichment_service.get_regulation_document_detail(kb_id, file_id)
        if not result:
            raise HTTPException(status_code=404, detail="规范文档不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"规范文档详情查询失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"规范文档详情查询失败: {str(e)}")


@regulation_library.get("/taxonomy/rows")
async def list_taxonomy_rows(
    kb_id: str = Query(...),
    doc_code: str | None = Query(None),
    q: str | None = Query(None, description="按代码或名称精确/子串匹配"),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """分类编码表行查询：写作链路查表校验（如地类代码 011 → 水浇地）"""
    try:
        await enrichment_service.ensure_schema()
        from sqlalchemy import text

        from yuxi.storage.postgres.manager import pg_manager

        conditions = ["1=1"]
        params: dict[str, Any] = {}
        if doc_code:
            conditions.append("doc_code = :doc_code")
            params["doc_code"] = doc_code
        if q:
            conditions.append("(code = :q OR name ILIKE :q_like OR meaning ILIKE :q_like)")
            params["q"] = q
            params["q_like"] = f"%{q}%"
        where = " AND ".join(conditions)
        sql = (
            f"SELECT code, name, meaning, parent_code, doc_code, unit_no FROM eia_taxonomy_rows "
            f"WHERE {where} ORDER BY code LIMIT 500"
        )
        async with pg_manager.get_async_session_context() as session:
            rows = (await session.execute(text(sql), params)).mappings().all()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        logger.error(f"分类表查询失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


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


def _manual_meta_and_rows(payload: dict[str, Any], require_doc_code: bool = True) -> tuple[str, str | None, list[Any]]:
    """手工标准载荷解析：返回 (doc_code, doc_name, rows)，越界即 400。

    doc_type 接收即忽略：无消费场景（YAGNI），不持久化。
    PUT 整标准替换的 doc_code 走路径参数，body 内 doc_code 免填（require_doc_code=False）。
    """
    doc_code = str(payload.get("doc_code") or "").strip()
    doc_name = str(payload.get("doc_name") or "").strip() or None
    rows = payload.get("rows")
    missing_code = require_doc_code and not doc_code
    if missing_code or not isinstance(rows, list) or not rows:
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
    _, doc_name, rows = _manual_meta_and_rows(payload, require_doc_code=False)
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
