"""Prompt 配置键归一化单元测试（bug-4244 回归）。

前端 API 键带 _prompt 后缀（extract_prompt 等），DB 与消费端
（_load_prompt_templates → 泛化管线 templates.get("template")）使用裸 prompt_type。
save_prompt_config 必须剥后缀落库，否则保存的提示词回显丢失且永不生效。
"""

from __future__ import annotations

import pytest

from yuxi.services.domain_factory_service import DomainFactoryService


class FakePromptRepo:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.upserts: list[tuple] = []

    async def upsert_prompt_config(self, domain_code, prompt_type, template):
        self.upserts.append((domain_code, prompt_type, template))
        return True

    async def list_prompt_configs(self):
        return self.rows


def _make_service(repo: FakePromptRepo) -> DomainFactoryService:
    svc = DomainFactoryService()
    svc.repo = repo
    return svc


@pytest.mark.asyncio
async def test_save_strips_prompt_suffix_and_is_idempotent():
    """PUT 提交 {type}_prompt 键落库为裸 type；已裸键幂等不变。"""
    repo = FakePromptRepo()
    svc = _make_service(repo)
    ok = await svc.save_prompt_config(
        {
            "template_prompt": "T",
            "extract_prompt": "E",
            "schema_generation_prompt": "S",
            "section_generalization_prompt": "G",
            "template": "bare",
        }
    )
    assert ok is True
    assert [key for _, key, _ in repo.upserts] == [
        "template",
        "extract",
        "schema_generation",
        "section_generalization",
        "template",
    ]


@pytest.mark.asyncio
async def test_get_returns_single_prompt_suffix():
    """GET 对裸 prompt_type 恰好包一层 _prompt 后缀（前端契约键）。"""
    repo = FakePromptRepo([{"prompt_type": "template", "template": "自定义"}])
    svc = _make_service(repo)
    data = await svc.get_prompt_config()
    assert data["config"] == {"template_prompt": "自定义"}


@pytest.mark.asyncio
async def test_db_override_lands_on_consumer_key(monkeypatch):
    """DB 行按裸键覆盖文件默认，泛化管线 templates.get("template") 命中自定义值。"""
    repo = FakePromptRepo([{"prompt_type": "template", "template": "自定义泛化"}])
    svc = _make_service(repo)
    monkeypatch.setattr(DomainFactoryService, "_load_prompts_from_file", lambda self: {"template": "文件默认"})
    templates = await svc._load_prompt_templates()
    assert templates["template"] == "自定义泛化"
