"""去领域化 HTTP 契约的 CI 通道单测。

集成套件（test/integration/api/test_domain_factory_api.py）因凭据依赖在 CI 零执行，
这里把两条纯契约用例（upload 无 domain 字段、contexts 单通用域）以直调路由/服务函数
的方式下沉到 test/unit 随 CI 强制执行；另补 import-extracted 默认域兜底（bug-4184）。
"""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from server.routers import domain_factory_router
from server.routers import domain_entity_builder_router as deb_router
from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from yuxi.services.domain_factory_service import DomainFactoryService

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class _FakeUploadService:
    def __init__(self):
        self.create_task_kwargs: dict | None = None

    async def save_uploaded_file(self, file_content: bytes, original_filename: str, domain_code: str):
        return "tid-1", f"/data/{original_filename}"

    async def create_task(self, **kwargs):
        self.create_task_kwargs = kwargs


async def test_upload_without_domain_field_ok(monkeypatch):
    """上传不携带 domain 表单字段即成功，且外键与响应恒为通用域。"""
    fake = _FakeUploadService()
    monkeypatch.setattr(domain_factory_router, "get_domain_factory_service", lambda: fake)
    upload = UploadFile(filename="dedomain-contract.txt", file=io.BytesIO("契约内容".encode()))

    result = await domain_factory_router.upload_file(file=upload, current_user=None)

    assert result["success"] is True
    assert result["domain"] == GENERAL_DOMAIN_CODE
    assert fake.create_task_kwargs["domain_code"] == GENERAL_DOMAIN_CODE


class _FakeContextRepo:
    """历史域行仍在库（冻结保留）的 repo 仿真：验证 contexts 读侧收敛。"""

    async def get_or_create_general_domain(self):
        return object()

    async def list_domains(self):
        return [
            {"code": "coal", "name": "煤炭采掘"},
            {"code": "chem", "name": "石油化工"},
            {"code": "transport", "name": "交通运输"},
            {"code": "general", "name": "通用域"},
        ]

    async def list_report_types(self):
        return [
            {"code": "eia_report", "domain_code": "coal", "name": "环境影响评价报告"},
            {"code": "通用", "domain_code": "general", "name": "通用（全部报告类型）"},
        ]

    async def count_learned_templates(self):
        return 0

    async def count_committed_tasks(self, domain_code: str):
        return 3


async def test_contexts_single_general_domain(monkeypatch):
    """contexts 恒返回通用域单元素，report_types 分组键不含历史域编码。"""
    service = DomainFactoryService()
    service.repo = _FakeContextRepo()

    result = await service.get_contexts()

    assert [d["code"] for d in result["domains"]] == [GENERAL_DOMAIN_CODE]
    assert set(result["report_types"].keys()) == {GENERAL_DOMAIN_CODE}
    # 统计只对通用域执行（锚定后单域循环）
    assert result["stats"]["committed_tasks"] == 3


class _FakeEntityService:
    def __init__(self):
        self.saved: tuple | None = None

    async def save_extracted_entities(self, entities, domain_code: str):
        self.saved = (entities, domain_code)
        return {"inserted": 1, "updated": 0}


async def test_import_extracted_defaults_to_general(monkeypatch):
    """import-extracted 缺省 domain_code 兜底为通用域，不再写回历史域（bug-4184）。"""
    fake = _FakeEntityService()
    monkeypatch.setattr(deb_router, "get_entity_service", lambda: fake)

    result = await deb_router.import_extracted_entities(
        payload={"entities": [{"name_cn": "颗粒物"}]}, current_user=None
    )

    assert result["success"] is True
    assert fake.saved[1] == GENERAL_DOMAIN_CODE
