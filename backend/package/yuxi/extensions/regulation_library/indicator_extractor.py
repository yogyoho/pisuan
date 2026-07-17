"""限值表 → LLM → 结构化指标行"""

from __future__ import annotations

import json
import re
from typing import Any

from yuxi.utils import logger

_PROMPT = """你是环保标准专家。以下是标准文档《{doc_code}》中的一张限值表（{unit_no}），请提取所有指标限值。

表格内容:
{table_content}

输出 JSON 数组，每行一个指标:
[{{"pollutant": "污染物/指标名", "metric": "指标含义(如 年平均浓度限值)",
  "limit_value": 数值, "unit": "单位", "condition": "适用条件(如 二类区/一级，无则空串)"}}]

要求:
- limit_value 必须是纯数值（区间取上限并在 condition 注明）
- 严格 JSON 数组输出，无注释无代码块标记
"""


def parse_indicator_response(text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的指标 JSON 数组，过滤缺少必填字段的行"""
    m = re.search(r"\[[\s\S]*\]", text or "")
    if not m:
        return []
    try:
        rows = json.loads(m.group())
    except (json.JSONDecodeError, ValueError):
        return []
    valid = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("pollutant") and r.get("metric") and r.get("limit_value") is not None:
            valid.append(r)
    return valid


async def extract_indicators(doc_code: str, unit_no: str, table_content: str) -> list[dict[str, Any]]:
    """对单张限值表调用 LLM 提取指标"""
    from yuxi.models.chat import select_model

    prompt = _PROMPT.format(doc_code=doc_code, unit_no=unit_no or "未编号表", table_content=table_content[:6000])
    try:
        model = select_model()
        response = await model.call(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        return parse_indicator_response(text)
    except Exception as e:
        logger.warning(f"指标提取失败 {doc_code} {unit_no}: {e}")
        return []
