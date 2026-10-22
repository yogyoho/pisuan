"""限值行形 ↔ standard_indicators 扁平指标双向映射（P1 合流；spec 2026-10-22 §4）。

LIMIT_TABLE_SCHEMAS 七表异构行形是页面编辑/校验契约；落库统一拍平为扁平指标行。
day/night 拆两行共享 page_row_id（页面重组键）；page_row_id 由行形业务键确定性派生，
转正幂等删除以它为键。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _page_row_id(table_key: str, page_row: dict[str, Any]) -> str:
    """行形业务键确定性派生 32 位重组键（同输入同键——转正幂等删除依赖）。"""
    biz = json.dumps(page_row, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(f"{table_key}|{biz}".encode()).hexdigest()


def flatten_limit_row(table_key: str, page_row: dict[str, Any]) -> list[dict[str, Any]]:
    """页面行形 → 扁平指标行列表（共享同一 page_row_id；DB 行 id 由调用方补）。"""
    prid = _page_row_id(table_key, page_row)

    def _row(**kw: Any) -> dict[str, Any]:
        return {
            "page_row_id": prid,
            "pollutant": kw.get("pollutant", ""),
            "metric": kw.get("metric", ""),
            "limit_value": kw["limit_value"],
            "unit": kw.get("unit", ""),
            "condition": "",
            "category": kw.get("category", ""),
            "period": kw.get("period", ""),
        }

    if "day" in page_row or "night" in page_row:  # 噪声行形：拆昼/夜两行
        return [
            _row(
                category=page_row.get("category", ""), metric="昼间", limit_value=page_row["day"], unit=page_row["unit"]
            ),
            _row(
                category=page_row.get("category", ""),
                metric="夜间",
                limit_value=page_row["night"],
                unit=page_row["unit"],
            ),
        ]
    if "a_value" in page_row:  # GB/T 13201 A 值
        return [
            _row(
                category=page_row.get("region_type", ""),
                metric="A值",
                limit_value=page_row["a_value"],
                unit=page_row["unit"],
            )
        ]
    return [
        _row(
            pollutant=page_row.get("pollutant", ""),
            limit_value=page_row["limit_value"],
            unit=page_row.get("unit", ""),
            category=page_row.get("category", page_row.get("grade", "")),
            period=page_row.get("period", page_row.get("phase", "")),
        )
    ]


def regroup_limit_rows(table_key: str, flat_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """扁平指标行 → 页面行形（按 page_row_id 分组；组内昼间在前还原 day/night）。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in flat_rows:
        groups.setdefault(r["page_row_id"], []).append(r)
    out: list[dict[str, Any]] = []
    for prid in groups:  # dict 保序：按 flat_rows 首现序（= 调用方 DB id 序）还原页面行序
        rows = sorted(groups[prid], key=lambda r: 0 if r["metric"] == "昼间" else 1)
        head = rows[0]
        if head["metric"] == "昼间":  # 噪声行形重组
            out.append(
                {
                    "category": head["category"],
                    "day": head["limit_value"],
                    "night": rows[1]["limit_value"],
                    "unit": head["unit"],
                }
            )
        elif head["metric"] == "A值":
            out.append({"region_type": head["category"], "a_value": head["limit_value"], "unit": head["unit"]})
        else:
            page: dict[str, Any] = {"pollutant": head["pollutant"]}
            if head["period"]:
                page["phase" if table_key == "gb20426_emission_limits" else "period"] = head["period"]
            if head["category"]:
                page["grade" if table_key == "gb3095_concentration_limits" else "category"] = head["category"]
            page["limit_value"] = head["limit_value"]
            page["unit"] = head["unit"]
            out.append(page)
    return out
