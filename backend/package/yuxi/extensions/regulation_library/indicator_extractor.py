"""限值表 → LLM → 结构化指标行（含 category/period）；方法表 → 因子→方法名→标准号 映射。

限值表四要素判据：每行可归约为 {因子（污染物/项目），适用条件，限值（带方向 ≤/</≥
或区间），单位}，数值用于合规判定（允许多高），而非测量记录、方法性能（检出浓度）
或工艺参数。通道：fast_model + with_structured_output（Task 13 判别器同款：能力探测
缓存 + prompt+JSON 降级，见 structured_channel），取代旧的 default_model+自由文本 JSON。
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from yuxi.extensions.regulation_library.structured_channel import call_structured
from yuxi.utils import logger

_PROMPT_TEXT_CAP = 24000  # 表格内容截断上限（对齐 4096-token 分块的上界），超限记日志（doc_code+unit_no+截断量）
_EXTRACT_TIMEOUT_SECONDS = 300.0  # 大表 JSON 行数多（GB 3838 表1 单表 120 行），60s 默认上限会 fail-closed（容器实测）

_PROMPT = """你是环保标准专家。提取标准文档《{doc_code}》中限值表（{unit_no}）的指标限值。

限值表判据：每一行可归约为 {{因子, 适用条件, 限值(带比较方向 ≤/</≥ 或区间), 单位}}，
数值用于合规判定（允许多高）；测量记录、方法性能（最低检出浓度）、工艺参数不是限值。

表格内容:
{table_content}

输出 JSON 对象 {{"rows": [...]}}，每个指标一行:
{{"pollutant": "污染物/指标名", "metric": "指标含义(如 年平均浓度限值)",
  "limit_value": 限值数值, "unit": "单位",
  "condition": "其他适用条件(自由文本)，无则空串",
  "category": "适用档位(如 III类/2类区/现有企业)，无则空串",
  "period": "时间周期(如 年平均/24小时/1小时/昼间)，无则空串"}}

要求:
- limit_value 只输出纯数值（如 0.5），禁止 "≤0.5" 等带符号写法
- 区间取上限，≤/≥ 等方向符号语义在 condition 注明
- 严格 JSON 输出，无注释无代码块标记
"""

_METHOD_PROMPT = """你是环保标准专家。提取标准文档《{doc_code}》中分析方法表（{unit_no}）的
「因子→方法名→方法标准号」映射。

表格内容:
{table_content}

输出 JSON 对象 {{"mappings": [...]}}，每个因子一行:
{{"pollutant": "污染物/因子名", "method_name": "分析方法名",
  "method_code": "方法标准号(如 HJ 828-2017)，无则空串"}}

严格 JSON 输出，无注释无代码块标记。
"""


class IndicatorRow(BaseModel):
    """指标行 schema（结构化通道与 prompt 通道 JSON 契约同形）。

    limit_value schema 层仍宽松接受字符串（"≤0.5"/"0.07~0.09"）——类型过严会让整表
    输出报废（Task 13 I2 教训）；数值归一（提取数字取最大值/解析失败丢行）在
    extract_indicators 出口完成，保证入库 NUMERIC 列类型安全。
    """

    pollutant: str = Field(default="", description="污染物/指标名")
    metric: str = Field(default="", description="指标含义，如 年平均浓度限值")
    limit_value: float | str | None = Field(default=None, description="限值；区间/带符号写法可原样字符串")
    unit: str = Field(default="", description="限值单位")
    condition: str = Field(default="", description="其他适用条件（自由文本），无则空串")
    category: str = Field(default="", description="适用档位(如 III类/2类区/现有企业)，无则空串")
    period: str = Field(default="", description="时间周期(如 年平均/24小时/1小时/昼间)，无则空串")


class IndicatorExtraction(BaseModel):
    """整表抽取结果（单列表字段包装，便于结构化通道与降级通道同形解析）。"""

    rows: list[IndicatorRow] = Field(default_factory=list, description="指标行")


class MethodMapping(BaseModel):
    """方法表映射行：因子 → 方法名 → 方法标准号。"""

    pollutant: str = Field(default="", description="污染物/因子名")
    method_name: str = Field(default="", description="分析方法名")
    method_code: str = Field(default="", description="方法标准号，如 HJ 828-2017，无则空串")


class MethodMappingExtraction(BaseModel):
    mappings: list[MethodMapping] = Field(default_factory=list, description="因子→方法映射")


def _is_complete_indicator_row(r: dict[str, Any]) -> bool:
    """行级过滤口径：pollutant/metric 非空且 limit_value 非空才算指标行。"""
    return (
        bool(str(r.get("pollutant") or "").strip())
        and bool(str(r.get("metric") or "").strip())
        and r.get("limit_value") is not None
    )


# legacy-only：生产路径已由 structured_channel 的 prompt+JSON 降级（内部自解析）取代，
# 当前仅测试消费；保留作降级解析参考，勿在新代码直接调用。
def parse_indicator_response(text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的指标 JSON 数组（降级通道），过滤缺少必填字段的行并补齐新字段默认值"""
    m = re.search(r"\[[\s\S]*\]", text or "")
    if not m:
        return []
    try:
        rows = json.loads(m.group())
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    valid = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = {
            "pollutant": str(r.get("pollutant") or ""),
            "metric": str(r.get("metric") or ""),
            "limit_value": r.get("limit_value"),
            "unit": str(r.get("unit") or ""),
            "condition": str(r.get("condition") or ""),
            "category": str(r.get("category") or ""),
            "period": str(r.get("period") or ""),
        }
        if _is_complete_indicator_row(row):
            valid.append(row)
    return valid


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def normalize_limit_value(value: Any) -> float | None:
    """limit_value 归一为 float（standard_indicators.limit_value 为 NUMERIC 列）。

    enrich 抽取与手工录入两条写路径共用此归一口径。float 原样保留；字符串提取全部数字
    取最大值（房规：区间取上限，≤/≥ 方向语义由 prompt 约定记入 condition）；解析不出
    数字返回 None，调用方丢弃该行。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    found = _NUM_RE.findall(str(value))
    return max((float(x) for x in found), default=None)


def _truncate_table_content(doc_code: str, unit_no: str, table_content: str) -> str:
    content = table_content or ""
    if len(content) > _PROMPT_TEXT_CAP:
        logger.info(f"表内容截断: {doc_code} {unit_no} {len(content)}→{_PROMPT_TEXT_CAP} 字符")
        content = content[:_PROMPT_TEXT_CAP]
    return content


async def extract_indicators(doc_code: str, unit_no: str, table_content: str) -> list[dict[str, Any]]:
    """对单张限值表调用 LLM 提取指标（含 category/period 结构化字段；失败 fail-closed 返回 []）"""
    prompt = _PROMPT.format(
        doc_code=doc_code,
        unit_no=unit_no or "未编号表",
        table_content=_truncate_table_content(doc_code, unit_no, table_content),
    )
    try:
        out = await call_structured(IndicatorExtraction, prompt, timeout=_EXTRACT_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning(f"指标提取失败 {doc_code} {unit_no}: {exc}")
        return []
    rows: list[dict[str, Any]] = []
    for r in out.rows:
        dump = r.model_dump()
        if not _is_complete_indicator_row(dump):
            continue
        value = normalize_limit_value(dump["limit_value"])
        if value is None:
            logger.warning(
                f"指标行 limit_value 无法解析为数值，丢弃该行: {doc_code} {unit_no} "
                f"pollutant={dump['pollutant']!r} limit_value={dump['limit_value']!r}"
            )
            continue
        dump["limit_value"] = value
        rows.append(dump)
    return rows


async def extract_method_mappings(doc_code: str, unit_no: str, table_content: str) -> list[dict[str, Any]]:
    """对方法表抽取 因子→方法名→方法标准号 映射（入 chunk tags，不建新表；失败返回 []）"""
    prompt = _METHOD_PROMPT.format(
        doc_code=doc_code,
        unit_no=unit_no or "未编号表",
        table_content=_truncate_table_content(doc_code, unit_no, table_content),
    )
    try:
        out = await call_structured(MethodMappingExtraction, prompt, timeout=_EXTRACT_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning(f"方法映射提取失败 {doc_code} {unit_no}: {exc}")
        return []
    return [m.model_dump() for m in out.mappings if m.pollutant.strip() and m.method_name.strip()]
