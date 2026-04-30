"""Entity Type API Router - 实体类型管理路由"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from server.utils.auth_middleware import get_admin_user
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

entity_types = APIRouter(prefix="/entity-types", tags=["Entity Types"])

# 内存中的实体类型存储（生产环境应使用数据库）
_entity_types_store = {
    "基础工程实体": [
        {"id": "e1", "name": "煤矿", "description": "煤矿开采相关设施", "keywords": ["矿井", "采煤"]},
        {"id": "e2", "name": "道路", "description": "交通道路设施", "keywords": ["公路", "铁路"]},
    ],
    "敏感目标与空间实体": [
        {"id": "s1", "name": "学校", "description": "教育设施", "keywords": ["小学", "中学"]},
        {"id": "s2", "name": "医院", "description": "医疗机构", "keywords": ["医院", "诊所"]},
    ],
    "环境要素与影响实体": [
        {"id": "env1", "name": "地表水", "description": "地表水体", "keywords": ["河流", "湖泊"]},
        {"id": "env2", "name": "空气", "description": "大气环境", "keywords": ["PM2.5", "空气质量"]},
    ],
    "措施与法规实体": [
        {"id": "m1", "name": "环评法", "description": "环境影响评价相关法规", "keywords": ["环境保护法"]},
    ],
    "其他": []
}


@entity_types.get("/categories")
async def list_categories(
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取所有实体分类"""
    return {"categories": list(_entity_types_store.keys())}


@entity_types.get("")
async def list_entity_types(
    category: str | None = Query(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取实体类型列表"""
    if category:
        if category not in _entity_types_store:
            return {"items": []}
        return {"items": _entity_types_store.get(category, [])}
    
    # 返回所有分类下的实体
    all_items = []
    for cat, items in _entity_types_store.items():
        for item in items:
            item_copy = item.copy()
            item_copy["category"] = cat
            all_items.append(item_copy)
    return {"items": all_items}


@entity_types.get("/{entity_id}")
async def get_entity_type(
    entity_id: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """获取实体类型详情"""
    for category, items in _entity_types_store.items():
        for item in items:
            if item.get("id") == entity_id:
                result = item.copy()
                result["category"] = category
                return result
    raise HTTPException(status_code=404, detail="实体类型不存在")


@entity_types.post("")
async def create_entity_type(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """创建实体类型"""
    name = payload.get("name")
    category = payload.get("category", "其他")
    description = payload.get("description", "")
    keywords = payload.get("keywords", [])
    examples = payload.get("examples", [])
    metadata = payload.get("metadata", {})

    if not name:
        raise HTTPException(status_code=400, detail="实体名称不能为空")

    # 确保分类存在
    if category not in _entity_types_store:
        _entity_types_store[category] = []

    # 生成 ID
    import uuid
    entity_id = str(uuid.uuid4())[:8]

    entity = {
        "id": entity_id,
        "name": name,
        "description": description,
        "keywords": keywords if isinstance(keywords, list) else [],
        "examples": examples if isinstance(examples, list) else [name],
        "metadata": metadata,
    }

    _entity_types_store[category].append(entity)
    logger.info(f"创建实体类型: {name} (分类: {category})")

    result = entity.copy()
    result["category"] = category
    return result


@entity_types.put("/{entity_id}")
async def update_entity_type(
    entity_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """更新实体类型"""
    for category, items in _entity_types_store.items():
        for i, item in enumerate(items):
            if item.get("id") == entity_id:
                # 更新字段
                if "name" in payload:
                    item["name"] = payload["name"]
                if "description" in payload:
                    item["description"] = payload["description"]
                if "keywords" in payload:
                    item["keywords"] = payload["keywords"]
                if "examples" in payload:
                    item["examples"] = payload["examples"]
                if "metadata" in payload:
                    item["metadata"] = payload["metadata"]

                result = item.copy()
                result["category"] = category
                return result

    raise HTTPException(status_code=404, detail="实体类型不存在")


@entity_types.delete("/{entity_id}")
async def delete_entity_type(
    entity_id: str,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除实体类型"""
    for category, items in _entity_types_store.items():
        for i, item in enumerate(items):
            if item.get("id") == entity_id:
                items.pop(i)
                logger.info(f"删除实体类型: {entity_id}")
                return {"success": True, "message": "删除成功"}

    raise HTTPException(status_code=404, detail="实体类型不存在")


@entity_types.post("/batch")
async def batch_import_entity_types(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """批量导入实体类型"""
    entities = payload.get("entities", [])
    imported = 0
    skipped = 0

    for entity_data in entities:
        name = entity_data.get("name")
        category = entity_data.get("category", "其他")

        if not name:
            skipped += 1
            continue

        if category not in _entity_types_store:
            _entity_types_store[category] = []

        import uuid
        entity = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "description": entity_data.get("description", ""),
            "keywords": entity_data.get("keywords", []),
            "examples": entity_data.get("examples", [name]),
            "metadata": entity_data.get("metadata", {}),
        }
        _entity_types_store[category].append(entity)
        imported += 1

    return {
        "success": True,
        "imported_count": imported,
        "skipped_count": skipped,
    }
