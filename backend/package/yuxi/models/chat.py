from langchain_core.messages import convert_to_messages

from yuxi.agents.models import load_chat_model
from yuxi.models.providers.cache import model_cache
from yuxi.utils import logger


class GeneralResponse:
    def __init__(self, content):
        self.content = content
        self.is_full = False


class LangChainChatAdapter:
    def __init__(self, model, *, model_name: str, base_url: str | None = None, info: dict | None = None):
        self.model = model
        self.model_name = model_name
        self.base_url = base_url
        self.info = info or {}

    @staticmethod
    def _normalize_messages(message):
        if isinstance(message, str):
            return message
        return convert_to_messages(message)

    async def call(self, message, stream=False):
        messages = self._normalize_messages(message)
        try:
            if stream:
                return self._stream_response(messages)
            response = await self.model.ainvoke(messages)
            return GeneralResponse(response.text)
        except Exception as e:
            err = f"Error calling model: {e}, URL: {self.base_url}, Model: {self.model_name}"
            logger.error(err)
            raise Exception(err)

    async def _stream_response(self, messages):
        async for chunk in self.model.astream(messages):
            if chunk.text:
                yield GeneralResponse(chunk.text)


def _langchain_kwargs(provider_type: str, kwargs: dict) -> dict:
    langchain_kwargs = dict(kwargs.pop("model_params", {}) or {})
    langchain_kwargs.update(kwargs)
    if provider_type == "anthropic" and "max_completion_tokens" in langchain_kwargs:
        langchain_kwargs.setdefault("max_tokens", langchain_kwargs.pop("max_completion_tokens"))
    return langchain_kwargs


def select_model(model_spec: str, **kwargs) -> LangChainChatAdapter:
    if not model_spec:
        raise ValueError("model_spec 不能为空")

    info = model_cache.get_model_info(model_spec)
    if not info:
        available = model_cache.get_all_specs("chat")
        available_ids = [item.spec for item in available[:10]]
        raise ValueError(f"未找到模型: '{model_spec}'。可用聊天模型 ({len(available)}): {available_ids}")

    if info.model_type != "chat":
        raise ValueError(f"Model {model_spec} is not a chat model (type={info.model_type})")

    logger.info(f"Selecting model: {model_spec} (provider_type={info.provider_type})")

    model = load_chat_model(
        model_spec,
        **_langchain_kwargs(info.provider_type, kwargs),
    )
    return LangChainChatAdapter(
        model,
        model_name=info.model_id,
        base_url=info.base_url,
        info={"provider_type": info.provider_type, "provider_id": info.provider_id},
    )


def select_model(model_provider=None, model_name=None, model_spec=None):
    """根据模型提供者选择模型"""
    if model_spec and is_v2_spec_format(model_spec):
        from yuxi.services.model_cache import model_cache

        if model_cache.is_v2_spec(model_spec):
            return select_model_v2(model_spec)

        available = model_cache.get_all_specs("chat")
        available_ids = [s.spec for s in available[:10]]
        raise ValueError(f"未找到 V2 模型: '{model_spec}'。可用聊天模型 ({len(available)}): {available_ids}")

    # 无参调用时，检查默认模型是否 v2 格式，是则走 v2 路径
    if model_spec is None and model_provider is None and model_name is None:
        default_spec = getattr(config, "default_model", "")
        if is_v2_spec_format(default_spec):
            from yuxi.services.model_cache import model_cache
            if model_cache.is_v2_spec(default_spec):
                return select_model_v2(default_spec)

    logger.warning(
        f"旧版本的模型选择逻辑已废弃，建议尽快迁移至新的模型配置；"
        f"当前模型选择参数: provider={model_provider}, model_name={model_name}, spec={model_spec}"
    )

    if model_spec:
        spec_provider, spec_model_name = split_model_spec(model_spec)
        model_provider = model_provider or spec_provider
        model_name = model_name or spec_model_name

    if model_provider is None or not model_name:
        default_provider, default_model = split_model_spec(getattr(config, "default_model", ""))
        model_provider = model_provider or default_provider
        model_name = model_name or default_model

    assert model_provider, "Model provider not specified"

    model_info = config.model_names.get(model_provider)
    if not model_info:
        raise ValueError(f"Unknown model provider: {model_provider}")

    model_name = model_name or model_info.default

    if not model_name:
        raise ValueError(f"Model name not specified for provider {model_provider}")

    logger.info(f"Selecting model from `{model_provider}` with `{model_name}`")

    if model_provider == "openai":
        return OpenModel(model_name)

    # 其他模型，默认使用OpenAIBase
    try:
        extra_body = getattr(model_info, "extra_body", None)
        model = OpenAIBase(
            api_key=os.environ.get(model_info.env, model_info.env),
            base_url=model_info.base_url,
            model_name=model_name,
            extra_body=extra_body,
        )
        return model
    except Exception as e:
        raise ValueError(f"Model provider {model_provider} load failed, {e} \n {traceback.format_exc()}")


async def test_chat_model_status_by_spec(spec: str) -> dict:
    try:
        logger.debug(f"Testing model status by spec: {spec}")
        model = select_model(model_spec=spec)

        test_messages = [{"role": "user", "content": "Say 1"}]
        response = await model.call(test_messages, stream=False)

        if response and response.content:
            return {"spec": spec, "status": "available", "message": "连接正常"}
        return {"spec": spec, "status": "unavailable", "message": "响应无效"}

    except Exception as e:
        logger.error(f"测试模型状态失败 {spec}: {e}")
        return {"spec": spec, "status": "error", "message": str(e)}


if __name__ == "__main__":
    pass
