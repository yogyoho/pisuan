"""存量实体属性值类型治理（幂等）。

实体构建器只接受 String/Integer/Float/Boolean/Enum/Object/List 作为属性值类型，
但早期数据把模板 slot 类型（`parameter`）写进了属性 `value_type`。后果是这些实体
在页面上任何一次保存都会 400，导出文件也无法原样回导（导入会整条拒绝）。

本脚本只处理这类**无法由写入路径归一**的标记值：`parameter` 是模板参数标记、不是值类型，
按 key 判定：以「数值」结尾 → Float，其余 → String。历史别名（Numeric/Number/Date/Text）
由 DomainEntityService.normalize_value_type 在写入路径归一，不必改库；既不是别名也不是
标记值的类型视为脏数据，脚本直接报错，交人工确认。

用法（api 容器内）：

    python -m scripts.governance.normalize_property_value_types           # 预览
    python -m scripts.governance.normalize_property_value_types --apply   # 写库
"""

from __future__ import annotations

import argparse
import asyncio

from yuxi.services.domain_entity_service import (
    VALID_VALUE_TYPES,
    DomainEntityService,
)

# 模板 slot 类型被误写进属性值类型的标记值（不是合法的属性值类型）
SLOT_TYPE_MARKERS = {"parameter"}


def slot_marker_type(prop: dict) -> str:
    """把模板 slot 类型标记换算成属性值类型：数值类 → Float，其余 → String。"""
    return "Float" if str(prop.get("key") or "").endswith("数值") else "String"


async def run(dry_run: bool) -> int:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    repo = DomainEntityRepository()
    changed = 0

    try:
        for entity in await repo.list_all():
            props = entity.get("properties") or []
            normalized: list[str] = []
            for index, prop in enumerate(props):
                if not isinstance(prop, dict):
                    continue
                raw = str(prop.get("value_type") or "").strip()
                if raw in VALID_VALUE_TYPES:
                    continue
                if raw not in SLOT_TYPE_MARKERS:
                    # 别名（Numeric/Date…）写入路径会归一；其余是脏数据，不猜
                    DomainEntityService.normalize_value_type(raw)
                    continue
                new_type = slot_marker_type(prop)
                props[index] = {**prop, "value_type": new_type}
                normalized.append(f"{prop.get('key')}: {raw} → {new_type}")

            if not normalized:
                continue
            print(f"{entity['entity_key']}: " + "；".join(normalized))
            if not dry_run:
                await repo.update(entity["entity_id"], {"properties": props})
            changed += 1
    finally:
        # 连接池不关，容器内脚本会挂在退出阶段
        await pg_manager.close()

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="归一实体属性值类型（默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="真正写库；缺省只打印计划")
    args = parser.parse_args()
    count = asyncio.run(run(dry_run=not args.apply))
    mode = "EXECUTED" if args.apply else "dry-run"
    print(f"\n{mode}: {count} entities")


if __name__ == "__main__":
    main()
