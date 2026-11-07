"""eia 服务层流测试的共享运行库隔离助手。

api 容器连接的 Postgres 是共享运行库：流测试若 delete 全表，会把运营数据当
测试数据抹掉（bug-4198：词表 8 条 approved 与开关系被清空，页面报"无 approved
条目可导出"）。本助手做行级快照/恢复——测试前把目标表整表存为列字典，
测试清理后原样回灌（显式主键，不动序列），文件侧沿用字节级快照。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert, select


async def snapshot_rows(model: Any) -> list[dict[str, Any]]:
    """整表行级快照（列名 → 值，含主键与 JSON 列）。"""
    from pisuan.storage.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as session:
        rows = (await session.execute(select(model))).scalars().all()
        return [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in rows]


async def restore_rows(model: Any, saved: list[dict[str, Any]]) -> None:
    """清表后回灌快照行（显式主键直插，autoincrement 序列不受影响）。"""
    from pisuan.storage.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as session:
        await session.execute(delete(model))
        if saved:
            await session.execute(insert(model).values(saved))
