"""Domain Entity Builder 分类字典 - Repository

分类字典是实体树顺序与泛化 prompt 截断顺序的唯一来源。code 是实体表
`category` 列的存储值（对外契约），只增不改；可管理的是 name_cn / sort_order /
description / is_active。
"""

import re
from typing import Any

from sqlalchemy import func, select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_entity import DomainEntityCategory

_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_category_code(value: Any) -> str:
    code = str(value or "").strip()
    if not _CODE_PATTERN.fullmatch(code):
        raise ValueError("分类 code 只能是小写字母开头的 snake_case（a-z0-9_，≤64 字符）")
    return code


class DomainEntityCategoryRepository:
    """实体分类字典数据访问层"""

    async def list_categories(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            query = select(DomainEntityCategory).order_by(DomainEntityCategory.sort_order, DomainEntityCategory.code)
            if not include_inactive:
                query = query.where(DomainEntityCategory.is_active.is_(True))
            result = await session.execute(query)
            return [row.to_dict() for row in result.scalars().all()]

    async def get(self, code: str) -> dict[str, Any] | None:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(DomainEntityCategory, code)
            return row.to_dict() if row else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        code = validate_category_code(data.get("code"))
        name_cn = str(data.get("name_cn") or "").strip()
        if not name_cn:
            raise ValueError("分类名称不能为空")
        async with pg_manager.get_async_session_context() as session:
            if await session.get(DomainEntityCategory, code):
                raise ValueError(f"分类 `{code}` 已存在")
            sort_order = data.get("sort_order")
            if sort_order is None:
                # 未指定顺序时排在字典末尾：新分类不该抢到树首与 prompt 名额
                max_order = await session.scalar(select(func.max(DomainEntityCategory.sort_order)))
                sort_order = (max_order or 0) + 10
            row = DomainEntityCategory(
                code=code,
                name_cn=name_cn,
                description=str(data.get("description") or ""),
                sort_order=int(sort_order),
                is_active=bool(data.get("is_active", True)),
            )
            session.add(row)
        return row.to_dict()

    async def update(self, code: str, data: dict[str, Any]) -> dict[str, Any]:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(DomainEntityCategory, code)
            if row is None:
                raise ValueError(f"分类 `{code}` 不存在")
            if "name_cn" in data:
                name_cn = str(data["name_cn"] or "").strip()
                if not name_cn:
                    raise ValueError("分类名称不能为空")
                row.name_cn = name_cn
            if "description" in data:
                row.description = str(data["description"] or "")
            if "sort_order" in data:
                row.sort_order = int(data["sort_order"])
            if "is_active" in data:
                row.is_active = bool(data["is_active"])
        return row.to_dict()

    async def delete(self, code: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(DomainEntityCategory, code)
            if row is None:
                raise ValueError(f"分类 `{code}` 不存在")
            await session.delete(row)

    async def reorder(self, codes: list[str]) -> list[dict[str, Any]]:
        """按给定顺序重排：sort_order 记为 10/20/30…，未列出的分类保持原位次。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(DomainEntityCategory))
            by_code = {row.code: row for row in result.scalars().all()}
            missing = [code for code in codes if code not in by_code]
            if missing:
                raise ValueError(f"分类不存在：{', '.join(missing)}")
            seen: set[str] = set()
            for index, code in enumerate(codes, start=1):
                if code in seen:
                    raise ValueError(f"分类 `{code}` 在排序列表里重复")
                seen.add(code)
                by_code[code].sort_order = index * 10
        return await self.list_categories()

    async def rank_map(self) -> dict[str, int]:
        """code → sort_order，供热点路径（prompt 截断）排序使用。"""
        return {row["code"]: row["sort_order"] for row in await self.list_categories()}
