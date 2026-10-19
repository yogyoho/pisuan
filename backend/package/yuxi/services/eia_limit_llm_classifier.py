"""语料限值提取 LLM 语义判别层（Task 13 B 通道，spec 2026-10-19 计划修订 B）。

真实语料试跑实证正则内核的结构性不足：监测值/水质值当限值（噪声表取到实测声级、
空气表混入水质因子）、散文碎片成行。本层在 locate 与 parse_block 之间加语义门：
区块先经 LLM 判别是否为「标准限值陈述」，仅通过者进入既有 parse_block/聚合/去重链路；
监测陈述与判别失败一律不产出行。

fail-closed 契约：模型不可用/超时/输出解析失败 → 该区块按「未通过」处理并计入
stats.failed，绝不回退为无条件放行。判别模型默认取系统配置「快速响应模型」
（fast_model，沿用既有模型选择机制，不新增配置面）。结构化输出通道遵循平台先例
（ETL 泛化 spec-W1 P1-1a）：每模型一次能力探测缓存，不支持则显式降级 prompt+JSON 通道，
降级不等于放行——prompt 通道解析失败同样 fail-closed。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from yuxi.config.options import system_options
from yuxi.models.chat import select_model
from yuxi.utils import logger

_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")
_PROMPT_TEXT_CAP = 4000  # 区块窗口已被 locate 限至 30 行，此处再设字符上限双保险

_JUDGE_PROMPT = """你是环评报告限值提取管线中的语义判别器。判断下面的文本区块是否为「污染物标准限值陈述」。

引用标准号：{code}
目标限值表：{table_key}
区块原文：
{block_text}

判定规则：
- is_limit_statement=true：标准/法规对污染物浓度、排放或声级规定的允许限值，包括限值表格
  （表头含 限值/标准值/浓度 等列）与行内限值句，如「SO₂ 日均 0.15 mg/m³」「III类 1.0 mg/L」「昼间 60 dB(A)」。
- is_limit_statement=false：监测/实测结果陈述（如「实测 45 dB(A)」「监测结果见下表」）、达标情况分析、
  采样记录、方法检出限、仅引用标准号而不含限值的一般性文字。
- 注意：噪声限值表的昼/夜声级（dB(A)）是限值；同一区块混入的水质/空气实测值不是限值。
严格按 schema 输出一个 JSON 对象，不要输出任何其他文本；evidence_span 摘录支撑判定的原文片段。"""


class LimitBlockVerdict(BaseModel):
    """判别结构化输出 schema（结构化通道与 prompt 通道 JSON 契约同形）。

    is_limit_statement 必填：缺裁决位的输出视为无效判定（fail-closed），
    不允许「没说清就默认拒绝」混入 rejected 计数。
    """

    is_limit_statement: bool = Field(description="区块是否为标准限值陈述（限值表/限值行/行内限值句）")
    pollutant: str = Field(default="", description="限值对应的污染物/因子名；无法判断留空")
    grade: str = Field(default="", description="限值适用等级/档位（如 二级标准、III类、2类）；无法判断留空")
    limit_value: float | None = Field(default=None, description="限值数值；无法判断留空")
    unit: str = Field(default="", description="限值单位；无法判断留空")
    evidence_span: str = Field(default="", description="支撑判定的原文片段")
    reason: str = Field(default="", description="一句话判定理由")


@dataclass
class GateStats:
    """判别计数器（单次试跑报告口径；failed 含模型不可用/超时/解析失败）。"""

    blocks: int = 0
    passed: int = 0
    rejected: int = 0
    failed: int = 0


@dataclass
class JudgeResult:
    """单区块判别结论：passed 仅在「模型明确判定为限值陈述」时为 True。"""

    passed: bool
    status: str  # passed / rejected / failed
    verdict: dict[str, Any]
    error: str | None = None


class EiaLimitLLMClassifier:
    """限值区块 LLM 语义判别器（服务层逐区块调用 judge）。

    model / model_spec 可注入便于测试；默认路径 = system_options.fast_model → select_model
    （首个判别时惰性初始化并复用）。_structured_support 为进程级每模型探测缓存。
    """

    CALL_TIMEOUT_SECONDS: ClassVar[float] = 60.0
    _structured_support: ClassVar[dict[str, bool]] = {}  # model_name -> 结构化通道可用（每模型一次探测）

    def __init__(self, model_spec: str | None = None, model: Any | None = None, timeout: float | None = None):
        self._model_spec = model_spec
        self._model = model
        self._timeout = timeout if timeout is not None else self.CALL_TIMEOUT_SECONDS
        self.stats = GateStats()

    async def judge(self, code: str, text: str, table_key: str | None = None) -> JudgeResult:
        """判别一个标准引用区块；任何失败路径都 fail-closed（passed=False + stats.failed）。"""
        self.stats.blocks += 1
        try:
            model = await self._resolve_model()
        except Exception as exc:
            self.stats.failed += 1
            logger.warning(f"[eia-limit-llm] 判别模型初始化失败，fail-closed: {exc}")
            return JudgeResult(False, "failed", {}, f"模型初始化失败: {exc}")
        prompt = self._build_prompt(code, text, table_key)
        data = None
        if self._structured_support.get(model.model_name, True):
            data = await self._try_structured(model, prompt)
        if data is None:
            data = await self._try_prompt_channel(model, prompt)
        if data is None:
            self.stats.failed += 1
            return JudgeResult(False, "failed", {}, "结构化与 prompt 通道均失败（fail-closed）")
        passed = bool(data["is_limit_statement"])
        if passed:
            self.stats.passed += 1
        else:
            self.stats.rejected += 1
        return JudgeResult(passed, "passed" if passed else "rejected", data)

    async def _resolve_model(self) -> Any:
        """显式 model 注入 > 显式 model_spec > 系统配置 fast_model；均不可用则抛错（fail-closed）。"""
        if self._model is not None:
            return self._model
        spec = self._model_spec or (await system_options.get()).get("fast_model")
        if not spec:
            raise ValueError("fast_model 未配置且未显式指定判别模型")
        self._model = select_model(spec)
        return self._model

    def _build_prompt(self, code: str, text: str, table_key: str | None) -> str:
        return _JUDGE_PROMPT.format(
            code=code,
            table_key=table_key or "（未知，按引用标准判断）",
            block_text=text[:_PROMPT_TEXT_CAP],
        )

    async def _try_structured(self, model, prompt: str) -> dict[str, Any] | None:
        """结构化输出通道（一次尝试）；不可用记探测缓存并交 prompt 通道（先例 spec-W1 P1-1a）。"""
        try:
            async with asyncio.timeout(self._timeout):
                data = await model.model.with_structured_output(LimitBlockVerdict).ainvoke(prompt)
            # provider 可能返回模型实例或缺字段裸 dict，一律过 pydantic 校验——无效判定交 fail-closed
            verdict = data if isinstance(data, LimitBlockVerdict) else LimitBlockVerdict.model_validate(data)
            return verdict.model_dump()
        except Exception as exc:
            self._structured_support[model.model_name] = False
            logger.warning(f"[eia-limit-llm] 结构化判别通道不可用（model={model.model_name}），降级 prompt 通道: {exc}")
            return None

    async def _try_prompt_channel(self, model, prompt: str) -> dict[str, Any] | None:
        """prompt+JSON 解析通道；解析失败返回 None（fail-closed，不重试）。"""
        try:
            async with asyncio.timeout(self._timeout):
                resp = await model.call(prompt)
            data = LimitBlockVerdict.model_validate(json.loads(_JSON_OBJ_RE.search(resp.content).group()))
            return data.model_dump()
        except Exception as exc:
            logger.warning(f"[eia-limit-llm] prompt 通道判别失败（model={model.model_name}），fail-closed: {exc}")
            return None


def gate_report(stats: GateStats) -> dict[str, int]:
    """试跑报告的 gate 字段口径。"""
    return asdict(stats)
