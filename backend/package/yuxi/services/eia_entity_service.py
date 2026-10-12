"""环评 sample_entities 实体补充服务（P3-2：DB 补充唯一真相 + 显式导出物化注册表 + _index）。

方案乙同构。编辑边界：仅添加（name/etype/rid/note）；文件锚点条目禁删禁改
（生成时实体泄漏检测清单依赖其稳定）。导出走文本级插接：registry 实体为纯字符串数组，
仅在目标 etype 数组尾追加条目（空数组 [] 与非空数组两种形态分别处理），并同步
_index.json 该样例 counts.<etype> 数字；CRLF 字面量保形，文件其余字节不动
（stages bug-417 同款教训）。已物化条目跳过（同状态重复导出 byte-identical，幂等）。
rid 为 DB 侧溯源字段（来源报告），不物化——registry schema 是纯字符串数组，保持稳定。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_entity_repository import EiaEntityRepository
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.utils import logger

SAMPLE_ENTITIES_DIR = _SKILL_ROOT / "references" / "sample_entities"
ENTITY_INDEX_PATH = SAMPLE_ENTITIES_DIR / "_index.json"

# registry entities 白名单（生成时实体泄漏检测清单的五个清单位）
ENTITY_TYPES = ("projects", "mines", "orgs", "places", "sensitive")


def _load_registry_text(slug: str) -> str:
    p = SAMPLE_ENTITIES_DIR / f"{slug}.json"
    if not p.exists():
        raise KeyError(f"未知样例注册表: {slug}")
    return p.read_text(encoding="utf-8", newline="")


def _load_index() -> dict[str, Any]:
    if not ENTITY_INDEX_PATH.exists():
        raise KeyError(f"sample_entities/_index.json 未找到: {ENTITY_INDEX_PATH}")
    return json.loads(ENTITY_INDEX_PATH.read_text(encoding="utf-8"))


def _find_array_span(text: str, etype: str) -> tuple[int, int]:
    """定位 entities.<etype> 数组（开括号位，匹配闭括号后一位）；字符串感知括号计数。"""
    marker = f'"{etype}": ['
    i = text.find(marker)
    if i < 0:
        raise KeyError(f"实体清单未找到: {etype}")
    open_pos = i + len(marker) - 1
    depth = 0
    in_str = False
    esc = False
    for j in range(open_pos, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return open_pos, j + 1
    raise KeyError(f"实体清单括号不闭合: {etype}")


def _append_item(text: str, etype: str, name: str) -> str:
    """数组尾追加条目：空数组 [] → 多行形态；非空数组在末项后插 `,\r\n      "x"`。"""
    open_pos, close_end = _find_array_span(text, etype)
    inner = text[open_pos + 1 : close_end - 1]
    item = json.dumps(name, ensure_ascii=False)
    if not inner.strip():
        return text[:open_pos] + f"[\r\n      {item}\r\n    ]" + text[close_end:]
    close_pos = close_end - 1
    rstrip_pos = len(text[:close_pos].rstrip())
    return text[:rstrip_pos] + f",\r\n      {item}" + text[rstrip_pos:]


def _bump_index_count(text: str, slug: str, etype: str, delta: int) -> str:
    """_index.json 文本级更新指定样例 counts.<etype> 数字。"""
    marker = f'"slug": "{slug}"'
    i = text.find(marker)
    if i < 0:
        raise KeyError(f"_index 缺样例: {slug}")
    obj_end = text.find('"slug": "', i + len(marker))
    if obj_end < 0:
        obj_end = len(text)
    seg = text[i:obj_end]
    m = re.search(rf'"{etype}": (\d+)', seg)
    if m is None:
        raise KeyError(f"_index counts 缺键: {slug}.{etype}")
    old = m.group(1)
    new_seg = seg[: m.start(1)] + str(int(old) + delta) + seg[m.end(1) :]
    return text[:i] + new_seg + text[obj_end:]


class EiaEntityService:
    """sample_entities 补充：list_samples / get_registry / add / withdraw / export。"""

    def __init__(self, repo: EiaEntityRepository | None = None):
        self.repo = repo or EiaEntityRepository()

    async def list_samples(self) -> dict[str, Any]:
        """_index 透出（样例清单 + counts + skipped），只读。"""
        idx = _load_index()
        return {"samples": idx.get("samples", []), "skipped": idx.get("skipped", [])}

    async def get_registry(self, slug: str) -> dict[str, Any]:
        """registry 锚点 + DB 待导出补充合并视图（pending=尚未物化到文件）。"""
        idx = _load_index()
        if not any(s["slug"] == slug for s in idx.get("samples", [])):
            raise KeyError(f"未知样例: {slug}")
        doc = json.loads(_load_registry_text(slug))
        additions = await self.repo.list_additions(slug)
        by_type: dict[str, list[dict[str, Any]]] = {t: [] for t in ENTITY_TYPES}
        for t in ENTITY_TYPES:
            by_type[t] = [{"name": n, "pending": False, "id": None} for n in doc.get("entities", {}).get(t, [])]
        for r in additions:
            by_type[r.etype].append(
                {
                    "name": r.name,
                    "pending": r.name not in [e["name"] for e in by_type[r.etype] if not e["pending"]],
                    "id": r.id,
                    "rid": r.rid,
                    "note": r.note,
                    "decided_by": r.decided_by,
                }
            )
        pending_count = sum(1 for items in by_type.values() for e in items if e["pending"])
        return {
            "sample_slug": slug,
            "source": doc.get("source"),
            "entities": by_type,
            "generic_terms": doc.get("generic_terms", []),
            "aux": doc.get("aux", {}),
            "notes": doc.get("notes", []),
            "pending_count": pending_count,
        }

    async def add_entity(
        self, sample_slug: str, etype: str, name: str, rid: str | None, note: str | None, username: str
    ) -> dict[str, Any]:
        """仅添加：锚点/待导出重复即拒；skipped 样例不可补充。"""
        idx = _load_index()
        if not any(s["slug"] == sample_slug for s in idx.get("samples", [])):
            raise KeyError(f"未知样例: {sample_slug}")
        if any(s["slug"] == sample_slug for s in idx.get("skipped", [])):
            raise ValueError(f"skipped 样例不可补充实体: {sample_slug}")
        if etype not in ENTITY_TYPES:
            raise ValueError(f"非法 etype: {etype}")
        if not name or not name.strip():
            raise ValueError("实体名称不能为空")
        name = name.strip()
        doc = json.loads(_load_registry_text(sample_slug))
        if name in doc.get("entities", {}).get(etype, []):
            raise ValueError(f"实体已存在（锚点）: {etype}.{name}")
        existing = await self.repo.list_additions(sample_slug)
        if any(r.etype == etype and r.name == name for r in existing):
            raise ValueError(f"实体已存在（待导出）: {etype}.{name}")

        row = await self.repo.insert_addition(sample_slug, etype, name, rid, note, username)
        logger.info(f"[eia-entity] 实体补充 {sample_slug}.{etype} + {name!r}（by {username}）")
        return {
            "id": row.id,
            "sample_slug": row.sample_slug,
            "etype": row.etype,
            "name": row.name,
            "rid": row.rid,
            "note": row.note,
            "decided_by": row.decided_by,
            "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else row.updated_at,
        }

    async def withdraw_entity(self, addition_id: int) -> bool:
        """撤回 DB 补充行（文件锚点不受影响）。"""
        return await self.repo.delete_addition(addition_id)

    async def export_entities(self, username: str) -> dict[str, Any]:
        """DB 补充 → registry 数组尾追加 + _index counts；幂等（已物化跳过，字节不动）。"""
        additions = await self.repo.list_additions()
        if not additions:
            raise ValueError("无待导出的实体补充")

        def _export_one() -> tuple[dict[str, dict[str, int]], list[str], str]:
            results: dict[str, dict[str, int]] = {}
            changed_paths: list[str] = []
            index_text = ENTITY_INDEX_PATH.read_text(encoding="utf-8", newline="")
            index_original = index_text
            deltas: dict[tuple[str, str], int] = {}
            for r in additions:
                stat = results.setdefault(r.sample_slug, {"materialized": 0, "skipped": 0})
                path = SAMPLE_ENTITIES_DIR / f"{r.sample_slug}.json"
                text = _load_registry_text(r.sample_slug)
                doc = json.loads(text)
                if r.name in doc.get("entities", {}).get(r.etype, []):
                    stat["skipped"] += 1  # 已物化（幂等）
                    continue
                new_text = _append_item(text, r.etype, r.name)
                if new_text != text:
                    path.write_text(new_text, encoding="utf-8", newline="")
                    if f"sample_entities/{r.sample_slug}.json" not in changed_paths:
                        changed_paths.append(f"sample_entities/{r.sample_slug}.json")
                    stat["materialized"] += 1
                    key = (r.sample_slug, r.etype)
                    deltas[key] = deltas.get(key, 0) + 1
            for (slug, etype), delta in deltas.items():
                index_text = _bump_index_count(index_text, slug, etype, delta)
            if index_text != index_original:
                ENTITY_INDEX_PATH.write_text(index_text, encoding="utf-8", newline="")
                changed_paths.append("sample_entities/_index.json")
            return results, changed_paths, index_text

        results, changed_paths, _ = await run_in_threadpool(_export_one)
        total = sum(s["materialized"] for s in results.values())
        skipped = sum(s["skipped"] for s in results.values())
        logger.info(f"[eia-entity] 导出物化实体补充 +{total}（跳过已物化 {skipped}）→ {changed_paths}（by {username}）")
        return {
            "results": results,
            "paths": changed_paths,
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


_service: EiaEntityService | None = None


def get_eia_entity_service() -> EiaEntityService:
    global _service
    if _service is None:
        _service = EiaEntityService()
    return _service
