"""表类型打标：快路径标题关键词规则 + 慢路径 LLM 判别（fail-closed → other）。

限值表四要素判据（工单定义基准）：一张表是限值表，当且仅当其每一行可归约为
{因子（污染物/项目），适用条件（类别/功能区/时段），限值（带比较方向 ≤/</≥ 或区间），
单位}，且数值用于合规判定（允许多高），而非测量记录、方法性能（检出浓度）或工艺参数。

分流宁可漏抽不可错抽——错抽是污染，漏抽可后人审补：判别失败/拿不准一律标 other，
不进指标抽取。慢路径复用 Task 13 判别器模式（fast_model + with_structured_output +
能力探测缓存 + prompt+JSON 降级），通道实现在 structured_channel。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from yuxi.extensions.regulation_library.structured_channel import call_structured
from yuxi.utils import logger

TableRole = Literal["limit", "method", "criteria", "param", "other"]

# 快路径规则：按工单顺序先到先得（limit 优先与真实标准表相符：限值表常附测定方法列）
_TITLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("limit", ("限值", "标准值", "最高允许")),
    ("method", ("分析方法", "测定方法", "检出")),
    ("criteria", ("判据", "等级", "分级")),
    ("param", ("参数", "系数")),
)

_EXCERPT_CAP = 1500

_PROMPT = """你是标准规范库的表类型判别器。判断标准文档《{doc_code}》中表格（{unit_no}）的类型。

表标题：{title}
表格内容（截选）：
{content_excerpt}

类型定义：
- limit（限值表）：每行可归约为 {{因子, 适用条件, 限值(带比较方向 ≤/</≥ 或区间), 单位}}，
  数值用于合规判定（允许多高），而非测量记录、方法性能（检出浓度）或工艺参数。
- method（方法表）：分析/测定方法及检出限，因子→方法名→方法标准号。
- criteria（判据表）：评价等级/级别划分判据。
- param（参数表）：工艺/计算参数或系数。
- other：以上都不是或无法确定。

反信号：数值列语义为检出浓度/回收率/效率/系数，或标题含采样/布点/分析方法的，不是 limit。
拿不准时选 other（宁可漏判不可错判）。严格按 schema 输出一个 JSON 对象，不要输出任何其他文本。"""


class TableRoleVerdict(BaseModel):
    """判别结构化输出 schema；枚举外取值过不了校验（fail-closed）。"""

    table_role: TableRole = Field(description="表类型：limit/method/criteria/param/other")


def classify_table_role_by_title(title: str) -> TableRole | None:
    """标题关键词快路径；返回 None 表示标题缺失/歧义，交 LLM 慢路径。"""
    t = (title or "").strip()
    if not t:
        return None
    for role, keywords in _TITLE_RULES:
        if any(k in t for k in keywords):
            return role
    return None


class TableRoleClassifier:
    """慢路径 LLM 判别器；classify 永不抛错，任何失败返回 other（不抽取，fail-closed）。"""

    def __init__(self, model: Any | None = None, model_spec: str | None = None, timeout: float | None = None):
        self._model = model
        self._model_spec = model_spec
        self._timeout = timeout

    async def classify(self, doc_code: str, unit_no: str, title: str, content_excerpt: str) -> TableRole:
        try:
            verdict = await call_structured(
                TableRoleVerdict,
                self._build_prompt(doc_code, unit_no, title, content_excerpt),
                model=self._model,
                model_spec=self._model_spec,
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning(f"[table-role] 判别失败（{doc_code} {unit_no}），fail-closed → other: {exc}")
            return "other"
        return verdict.table_role

    def _build_prompt(self, doc_code: str, unit_no: str, title: str, content_excerpt: str) -> str:
        return _PROMPT.format(
            doc_code=doc_code,
            unit_no=unit_no or "未编号表",
            title=(title or "").strip() or "（无标题）",
            content_excerpt=(content_excerpt or "")[:_EXCERPT_CAP],
        )
