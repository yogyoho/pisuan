"""存量实体分类迁移：7 分类 → 6 分类（对齐环评导则）

Usage:
  docker exec api-dev python -m scripts.migrate_entity_categories --dry-run
  docker exec api-dev python -m scripts.migrate_entity_categories --execute
"""

from __future__ import annotations

import argparse
import asyncio

CATEGORY_MAP = {
    "基础工程实体": "project_basic",
    "环境要素与影响实体": None,  # 需精确映射（走 ENTITY_OVERRIDES）
    "敏感目标与空间实体": "sensitive_target",
    "敏感目标实体": "sensitive_target",
    "措施与法规实体": "measures_regulation",
    "生态完整性评价": "natural_env",
    "生态调查": "natural_env",
}

# 精确映射：从"环境要素与影响实体"拆分到 env_quality / natural_env / impact_assessment
ENTITY_OVERRIDES = {
    "pollutant": "env_quality",
    "noise_equipment": "env_quality",
    "risk_assessment": "impact_assessment",
    "soil_water_conservation": "natural_env",
    "carbon_footprint": "env_quality",
    "environmental_element": "natural_env",
    "impact_behavior": "impact_assessment",
    "judgment": "impact_assessment",
    "shallow_groundwater": "natural_env",
    "wastewater_sources": "env_quality",
    "solid_waste_gangue": "env_quality",
    "environmental_quality_baseline": "env_quality",
    "assessment_conclusion": "impact_assessment",
    "air_pollutants": "env_quality",
    "land_subsidence": "natural_env",
}


async def migrate(dry_run: bool = True) -> int:
    """Return count of entities that would be / were migrated."""
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository

    pg_manager.initialize()
    repo = DomainEntityRepository()
    entities = await repo.list_all()
    updated = 0

    for entity in entities:
        ek = entity.get("entity_key", "")
        old_cat = entity.get("category", "")

        if ek in ENTITY_OVERRIDES:
            new_cat = ENTITY_OVERRIDES[ek]
        else:
            new_cat = CATEGORY_MAP.get(old_cat)

        if new_cat is None:
            print(f"  SKIP {entity['name_cn']} ({ek}): 环境要素与影响实体 未在 overrides 中定义")
            continue

        if new_cat != old_cat:
            print(f"  {entity['name_cn']} ({ek}): {old_cat} -> {new_cat}")
            if not dry_run:
                await repo.update(entity["entity_id"], {"category": new_cat})
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description="Entity category migration: 7 → 6")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", dest="dry_run", action="store_false")
    args = parser.parse_args()
    count = asyncio.run(migrate(dry_run=args.dry_run))
    mode = "dry-run" if args.dry_run else "EXECUTED"
    print(f"\n{mode}: {count} entities would be/are migrated")


if __name__ == "__main__":
    main()
