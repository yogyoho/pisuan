"""[pisuan-custom] W3：存量任务 L1 归属回填（幂等：只填 NULL 列；learned_templates 零改动）

用法（api 容器内）: python /app/scripts/backfill_task_scope.py
打印逐任务对照表；文档身份词表命中才写（region_label/region_key/scope='regional'）。
yuxi/pisuan 双轨 import：worktree 语境为 yuxi.*，pisuan-localized 运行栈为 pisuan.*。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "package"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

try:
    from yuxi.services.domain_factory_region import l1_task_attribution
except ModuleNotFoundError:  # pisuan-localized 改名层运行栈
    from pisuan.services.domain_factory_region import l1_task_attribution


async def main() -> None:
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        async with engine.begin() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id, file_name, document_type, report_type_code, "
                            "region_label, region_key, scope FROM domain_factory_tasks ORDER BY created_at"
                        )
                    )
                )
                .mappings()
                .all()
            )
            patched = 0
            for row in rows:
                hit = l1_task_attribution(dict(row))
                display = hit["region_label"] if hit else "（无命中，不回填）"
                print(f"{row['file_name'][:44]:46s} -> {display}")
                if not hit:
                    continue
                sets = []
                params: dict = {"id": row["id"], "region_label": hit["region_label"], "region_key": hit["region_key"]}
                if not row["region_label"]:
                    sets.append("region_label = :region_label")
                if not row["region_key"]:
                    sets.append("region_key = :region_key")
                if not row["scope"]:
                    sets.append("scope = 'regional'")
                if sets:
                    await conn.execute(
                        text(f"UPDATE domain_factory_tasks SET {', '.join(sets)} WHERE id = :id"), params
                    )
                    patched += 1
            print(f"\n回填完成: {patched}/{len(rows)} 任务落列（learned_templates 零改动）")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
