"""结构化 LLM 输出通道（regulation_library 内共用）。

指标抽取与方法映射、表类型判别共用一套模式（Task 13 判别器同款，平台先例 ETL
spec-W1 P1-1a）：每模型一次能力探测缓存，探测仅包调用本身——通道级失败（调用异常/
超时）拉黑该模型的结构化通道并降级 prompt+JSON；输出校验失败属本次无效，抛
StructuredOutputInvalid 由调用方 fail-closed，不写探测缓存（一次坏响应不应永久
关闭该模型的结构化通道）。降级不等于放行：prompt 通道解析/校验失败同样抛
StructuredOutputInvalid。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, get_origin

from pydantic import BaseModel, ValidationError

from pisuan.config.options import system_options
from pisuan.models.chat import select_model
from pisuan.utils import logger

_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")
_JSON_ARR_RE = re.compile(r"\[[\s\S]*\]")

CALL_TIMEOUT_SECONDS: float = 60.0

_structured_support: dict[str, bool] = {}  # model_name -> 结构化通道可用（每模型一次探测）
_adapter_cache: dict[str, Any] = {}  # model_spec -> adapter（进程内复用，避免逐表重建客户端）


class StructuredOutputInvalid(Exception):
    """结构化/降级通道输出无法通过 schema 校验：本次调用 fail-closed，不写探测缓存。"""


def reset_channel_caches() -> None:
    """清空探测缓存与适配器缓存（测试用）。"""
    _structured_support.clear()
    _adapter_cache.clear()


async def _resolve_adapter(model: Any | None = None, model_spec: str | None = None) -> Any:
    """显式 model 注入 > 显式 model_spec > 系统配置 fast_model；均不可用则抛错。"""
    if model is not None:
        return model
    spec = model_spec or (await system_options.get()).get("fast_model")
    if not spec:
        raise ValueError("fast_model 未配置且未显式指定模型")
    if spec not in _adapter_cache:
        _adapter_cache[spec] = select_model(spec)
    return _adapter_cache[spec]


def _wrap_single_list_field(schema_type: type[BaseModel], data: Any) -> Any:
    """prompt 通道吐裸数组时，包装进 schema 的唯一列表字段（如 {"rows": [...]}）。"""
    if not isinstance(data, list):
        return data
    list_fields = [name for name, f in schema_type.model_fields.items() if get_origin(f.annotation) is list]
    if len(list_fields) == 1:
        return {list_fields[0]: data}
    return data


def _extract_json(schema_type: type[BaseModel], text: str) -> Any:
    stripped = (text or "").strip()
    # 按首字符定匹配顺序：裸数组先于对象（否则 \{...\} 会截走数组内的单个对象）
    patterns = (_JSON_ARR_RE, _JSON_OBJ_RE) if stripped.startswith("[") else (_JSON_OBJ_RE, _JSON_ARR_RE)
    for pat in patterns:
        m = pat.search(stripped)
        if not m:
            continue
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            continue
        return _wrap_single_list_field(schema_type, data)
    raise StructuredOutputInvalid("输出中未找到 JSON")


async def call_structured(
    schema_type: type[BaseModel],
    prompt: str,
    *,
    model: Any | None = None,
    model_spec: str | None = None,
    timeout: float | None = None,
) -> BaseModel:
    """schema 结构化调用：with_structured_output 优先，prompt+JSON 降级；输出必过 schema 校验。"""
    adapter = await _resolve_adapter(model, model_spec)
    t = timeout if timeout is not None else CALL_TIMEOUT_SECONDS
    if _structured_support.get(adapter.model_name, True):
        try:
            async with asyncio.timeout(t):
                raw = await adapter.model.with_structured_output(schema_type).ainvoke(prompt)
        except Exception as exc:
            _structured_support[adapter.model_name] = False
            logger.warning(
                f"[structured-channel] 结构化通道不可用（model={adapter.model_name}），降级 prompt 通道: {exc}"
            )
        else:
            if isinstance(raw, schema_type):
                return raw
            try:
                # provider 可能返回缺字段裸 dict，一律过 pydantic 校验
                return schema_type.model_validate(raw)
            except ValidationError as exc:
                raise StructuredOutputInvalid(str(exc)) from exc
    try:
        async with asyncio.timeout(t):
            resp = await adapter.call(prompt)
        text = getattr(resp, "content", None) or str(resp)
        return schema_type.model_validate(_extract_json(schema_type, text))
    except StructuredOutputInvalid:
        raise
    except ValidationError as exc:
        raise StructuredOutputInvalid(str(exc)) from exc
    except Exception as exc:
        logger.warning(f"[structured-channel] prompt 通道失败（model={adapter.model_name}），fail-closed: {exc}")
        raise StructuredOutputInvalid(f"prompt 通道失败: {exc}") from exc
