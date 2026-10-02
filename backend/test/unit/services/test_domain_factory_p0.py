"""知识工厂 ETL P0 改造单元测试（[pisuan-custom]）

覆盖：
- P0-1 错误分类（_classify_llm_error）、退避重试（_call_llm_with_retry）、
  StepOutcome 台账与熔断（generalize_paragraphs）
- P0-2 兜底标记（_generalize_fallback.metadata.fallback）
- P0-4 list 分类停机（classify_paragraphs 不再产出 list）
"""

from __future__ import annotations

import pytest
import yuxi.services.domain_factory_service as dfs_mod
from yuxi.services.domain_factory_service import DomainFactoryService


# ------------------------------------------------------------------
# 测试替身
# ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeModel:
    """按脚本依序回放：元素为 str（正常响应）或 Exception（抛错）"""

    model_name = "fake-model"

    def __init__(self, script: list):
        self._script = list(script)
        self.calls = 0

    async def call(self, prompt: str):
        self.calls += 1
        item = self._script.pop(0) if self._script else AssertionError("no more script")
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


class FakeSystemOptions:
    async def get(self):
        return {"default_model": "fake-model"}


def _make_service(monkeypatch, model: FakeModel) -> DomainFactoryService:
    monkeypatch.setattr(dfs_mod, "system_options", FakeSystemOptions())
    monkeypatch.setattr("yuxi.models.chat.select_model", lambda model_spec: model)
    return DomainFactoryService()


RATE_LIMIT_EXC = Exception("Error code: 429 - Too Many Requests, rate limit exceeded")
QUOTA_EXC = Exception("Error code: 402 - Insufficient balance, quota exhausted")
TIMEOUT_EXC = Exception("Request timed out after 30s (connect error)")
API_EXC = Exception("Error code: 500 - Internal Server Error")
AUTH_EXC = Exception("Error code: 401 - Invalid API key")


# ------------------------------------------------------------------
# P0-1 错误分类
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_llm_error_categories(monkeypatch):
    service = _make_service(monkeypatch, FakeModel([]))
    classify = service._classify_llm_error
    assert classify(RATE_LIMIT_EXC) == "rate_limit"
    assert classify(QUOTA_EXC) == "quota"
    assert classify(TIMEOUT_EXC) == "timeout"
    assert classify(API_EXC) == "api_error"
    assert classify(AUTH_EXC) == "other"
    assert classify(ValueError("bad request")) == "other"


# ------------------------------------------------------------------
# P0-1 退避重试
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_rate_limit(monkeypatch):
    monkeypatch.setattr(DomainFactoryService, "RETRY_BACKOFF_BASE_SECONDS", 0.0)
    model = FakeModel([RATE_LIMIT_EXC, RATE_LIMIT_EXC, '{"ok": 1}'])
    service = _make_service(monkeypatch, model)

    text, meta = await service._call_llm_with_retry(model, "prompt")
    assert text == '{"ok": 1}'
    assert meta == {"error_type": None, "attempts": 3}
    assert model.calls == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_reports_error_type(monkeypatch):
    monkeypatch.setattr(DomainFactoryService, "RETRY_BACKOFF_BASE_SECONDS", 0.0)
    model = FakeModel([RATE_LIMIT_EXC] * 10)
    service = _make_service(monkeypatch, model)

    text, meta = await service._call_llm_with_retry(model, "prompt")
    assert text is None
    assert meta["error_type"] == "rate_limit"
    assert meta["attempts"] == 1 + service.PROVIDER_RETRY_MAX
    assert model.calls == 1 + service.PROVIDER_RETRY_MAX


@pytest.mark.asyncio
async def test_no_retry_for_auth_error(monkeypatch):
    monkeypatch.setattr(DomainFactoryService, "RETRY_BACKOFF_BASE_SECONDS", 0.0)
    model = FakeModel([AUTH_EXC])
    service = _make_service(monkeypatch, model)

    text, meta = await service._call_llm_with_retry(model, "prompt")
    assert text is None
    assert meta["error_type"] == "other"
    assert model.calls == 1  # 非 provider 类错误不重试


# ------------------------------------------------------------------
# P0-1 台账版单段泛化
# ------------------------------------------------------------------


GOOD_JSON = (
    '{"generalized": "{{项目名称}}设计产能{{产能数值}}{{产能单位}}", '
    '"slots": [{"name": "项目名称", "type": "descriptive", "description": "项目名"}], '
    '"metadata": {"chapter": "3.1", "tags": []}}'
)


@pytest.mark.asyncio
async def test_tracked_success_normalizes_result(monkeypatch):
    model = FakeModel([GOOD_JSON])
    service = _make_service(monkeypatch, model)

    resp, outcome = await service._generalize_text_tracked("某矿井设计产能6.0Mt/a", "3.1")
    assert outcome["status"] == "success"
    assert outcome["attempts"] == 1
    assert resp is not None
    assert "项目名称" in resp["generalized"]


@pytest.mark.asyncio
async def test_tracked_fallback_after_json_failures(monkeypatch):
    model = FakeModel(["这不是JSON", "还不是JSON"])
    service = _make_service(monkeypatch, model)

    resp, outcome = await service._generalize_text_tracked("某矿井设计产能6.0Mt/a", "3.1")
    assert outcome["status"] == "fallback"
    assert outcome["error_type"] == "json_parse"
    assert outcome["attempts"] == 2  # 首次 + JSON 重试 1 次
    assert resp is not None
    assert resp["metadata"]["fallback"] is True  # P0-2/断点续跑判据


# ------------------------------------------------------------------
# P0-1 熔断与台账聚合
# ------------------------------------------------------------------


def _para(i: int) -> dict:
    return {
        "id": f"p{i}",
        "content": f"第{i}号矿井设计产能6.0Mt/a，服务年限50年，配套建设选煤厂一座。" * 2,
        "section_path": ["3", "3.1"],
    }


@pytest.mark.asyncio
async def test_breaker_trips_after_consecutive_provider_errors(monkeypatch):
    service = _make_service(monkeypatch, FakeModel([]))

    async def fake_tracked(text, chapter_hint="", prompt=None):
        return None, {"status": "error", "error_type": "rate_limit", "attempts": 1}

    async def fake_templates():
        return {}

    service._generalize_text_tracked = fake_tracked
    service._load_prompt_templates = fake_templates

    out = await service.generalize_paragraphs([_para(i) for i in range(20)], [])
    stats = out["stats"]
    assert stats["breaker_tripped"] is True
    assert stats["breaker_position"]  # 含断供位置
    assert stats["success"] == 0 and stats["fallback"] == 0
    assert stats["error"]["rate_limit"] >= service.CIRCUIT_BREAKER_THRESHOLD
    assert stats["skipped"] > 0
    assert out["results"] == {}


@pytest.mark.asyncio
async def test_ledger_counts_all_success(monkeypatch):
    service = _make_service(monkeypatch, FakeModel([]))

    async def fake_tracked(text, chapter_hint="", prompt=None):
        return {"generalized": "x", "slots": [], "metadata": {}}, {
            "status": "success",
            "error_type": None,
            "attempts": 1,
        }

    async def fake_templates():
        return {}

    service._generalize_text_tracked = fake_tracked
    service._load_prompt_templates = fake_templates

    out = await service.generalize_paragraphs([_para(i) for i in range(3)], [])
    stats = out["stats"]
    assert stats["success"] == 3
    assert stats["attempts"] == 3
    assert stats["breaker_tripped"] is False
    assert stats["skipped"] == 0
    assert len(out["results"]) == 3


# ------------------------------------------------------------------
# P0-2 兜底标记 / P0-4 list 停机
# ------------------------------------------------------------------


def test_fallback_result_carries_marker():
    service = DomainFactoryService()
    fb = service._generalize_fallback("矿井产能6.0Mt/a", "采矿业")
    assert fb["metadata"]["fallback"] is True


def test_list_classification_shutdown():
    """多行编号段落不再判为 list（恒 0 产出的死分类已停机）"""
    service = DomainFactoryService()
    paras = [
        {
            "id": "t1",
            "title": "",
            "is_title": False,
            "content": "（1）第一项要求\n（2）第二项要求\n（3）第三项要求\n（4）第四项要求",
        }
    ]
    out = service.classify_paragraphs(paras)
    assert out[0]["classify_type"] != "list"
