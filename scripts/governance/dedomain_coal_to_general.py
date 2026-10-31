"""去领域化存量迁移：domain_code 'coal' 等历史域值 → 'general'（设计 docs/vibe/2026-10-29-etl-pipeline-dedomain-design.md §4.1）。

幂等可重跑。默认 dry-run 只统计；--apply 才写库。
用法（宿主仓库根执行，脚本经 stdin 进容器；localized 栈容器包名为 pisuan 时先做 yuxi→pisuan 替换再入）：
    MSYS_NO_PATHCONV=1 docker exec -i api-dev python - --apply < scripts/governance/dedomain_coal_to_general.py
（不带 --apply 即 dry-run）

两类目标表：
- PLAIN_TARGETS：无含 domain 的唯一约束，直接 UPDATE。
- MERGE_TARGETS：learned_templates/outlines/prompt_configs 有 UNIQUE(domain_code, 业务键…) 约束；
  report_types 实为主键 code 单列（翻 domain_code 不会撞键），走同一合并路径时 promote 即退化为直更、
  删重为空操作，行为安全。
  逐业务键处理：无 general 行时 promote 一行（coal 行优先），有 general 行或已有同名键行时删除重复
  （general 行为准；learned/outlines 重复行本就是去域后的同一实体）。
  注意不能整表一条 UPDATE：同一语句内多行翻到同一 (domain,键) 会互相撞唯一键。

dry-run 严格只读：不执行 get_or_create_general_domain（其含 INSERT），仅对各目标表做 SELECT 统计；
通用域行只在其不存在且 --apply 时创建。
"""
import argparse
import asyncio

from sqlalchemy import text

from yuxi.repositories.domain_factory_repository import (
    GENERAL_DOMAIN_CODE,
    GENERAL_DOMAIN_NAME,
    DomainFactoryRepository,
)
from yuxi.storage.postgres.manager import pg_manager

# (表, 域列)。表名列名已对照 models_domain_factory.py / models_domain_entity.py 核实（2026-10-30）。
PLAIN_TARGETS = [
    ("domain_factory_reports", "domain_code"),
    ("domain_factory_tool_usage", "domain"),
    ("domain_entity_schemas", "domain_code"),
]

# (表, 业务键列)。UNIQUE 约束含 domain_code，须合并而非直改。
MERGE_TARGETS = [
    ("domain_factory_learned_templates", ("report_type_code", "chapter", "slot_signature")),
    ("domain_factory_outlines", ("report_type_code", "canonical_chapter_key")),
    ("domain_factory_prompt_configs", ("report_type_code", "prompt_type")),
    ("report_types", ("code",)),
]


async def main(apply: bool) -> None:
    repo = DomainFactoryRepository()
    tag = "apply" if apply else "dry-run"
    # dry-run 严格只读：get_or_create_general_domain 含 INSERT，仅在 --apply 下执行
    general_id = None
    if apply:
        general = await repo.get_or_create_general_domain()
        general_id = general.id
        print(f"通用域行: id={general.id} code={general.code}")

    async with pg_manager.get_async_session_context() as session:
        for table, col in PLAIN_TARGETS:
            rows = (
                await session.execute(
                    text(f"SELECT {col}, count(*) FROM {table} WHERE {col} <> :c GROUP BY {col}"),
                    {"c": GENERAL_DOMAIN_CODE},
                )
            ).all()
            print(f"[{tag}] {table}.{col} 待迁移: {rows}")
            if apply and rows:
                result = await session.execute(
                    text(f"UPDATE {table} SET {col} = :c WHERE {col} <> :c"),
                    {"c": GENERAL_DOMAIN_CODE},
                )
                print(f"[apply] {table} 直更 {result.rowcount} 行")

        for table, keys in MERGE_TARGETS:
            rows = (
                await session.execute(
                    text(f"SELECT domain_code, count(*) FROM {table} WHERE domain_code <> :c GROUP BY domain_code"),
                    {"c": GENERAL_DOMAIN_CODE},
                )
            ).all()
            print(f"[{tag}] {table} 待合并: {rows}")
            if not apply or not rows:
                continue
            groups = (
                await session.execute(
                    text(
                        f"SELECT {', '.join(keys)} FROM {table} "
                        f"WHERE domain_code <> :c GROUP BY {', '.join(keys)}"
                    ),
                    {"c": GENERAL_DOMAIN_CODE},
                )
            ).all()
            # 逐业务键处理：同一 UPDATE 语句内多行翻到同一 (domain,键) 会互相撞唯一键
            # （语句快照不读自身改动，NOT EXISTS 守卫拦不住），必须每键单独 promote 一行
            # （coal 行优先），再删同键其余域行。
            g_check = " AND ".join(f"g.{k} IS NOT DISTINCT FROM :k{i}" for i, k in enumerate(keys))
            t_match = " AND ".join(f"{k} IS NOT DISTINCT FROM :k{i}" for i, k in enumerate(keys))
            upd_cnt = del_cnt = 0
            for group in groups:
                params = {"c": GENERAL_DOMAIN_CODE, "coal": "coal", **{f"k{i}": v for i, v in enumerate(group)}}
                upd = await session.execute(
                    text(
                        f"""UPDATE {table} SET domain_code = :c
                        WHERE ctid = (
                            SELECT ctid FROM {table} WHERE domain_code <> :c AND {t_match}
                            ORDER BY (domain_code = :coal) DESC LIMIT 1
                        ) AND NOT EXISTS (
                            SELECT 1 FROM {table} g WHERE g.domain_code = :c AND {g_check}
                        )"""
                    ),
                    params,
                )
                dele = await session.execute(
                    text(
                        f"""DELETE FROM {table}
                        WHERE domain_code <> :c AND {t_match} AND EXISTS (
                            SELECT 1 FROM {table} g WHERE g.domain_code = :c AND {g_check}
                        )"""
                    ),
                    params,
                )
                upd_cnt += upd.rowcount
                del_cnt += dele.rowcount
            print(f"[apply] {table} 合并: promote {upd_cnt} 行, 删重复 {del_cnt} 行 (业务键 {len(groups)} 组)")

        task_rows = (
            await session.execute(
                text(
                    "SELECT count(*) FROM domain_factory_tasks t "
                    "JOIN domain_factory_domains d ON t.domain_id = d.id "
                    "WHERE d.code <> :c"
                ),
                {"c": GENERAL_DOMAIN_CODE},
            )
        ).scalar()
        print(f"[{tag}] domain_factory_tasks 待重指向: {task_rows}")
        if apply and task_rows:
            result = await session.execute(
                text(
                    "UPDATE domain_factory_tasks t SET domain_id = :gid "
                    "FROM domain_factory_domains d WHERE t.domain_id = d.id AND d.code <> :c"
                ),
                {"gid": general_id, "c": GENERAL_DOMAIN_CODE},
            )
            print(f"[apply] domain_factory_tasks 重指向 {result.rowcount} 行")
    print("完成（general 行名为 " + GENERAL_DOMAIN_NAME + "；domains 表其他历史行冻结保留）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    asyncio.run(main(parser.parse_args().apply))
