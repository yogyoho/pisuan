"""实体分类字典（v23）单元测试。

覆盖：taxonomy 按字典 sort_order 渲染（含空分类）、停用分类规则、
字典外历史分类兜底可见、实体 category 校验走字典、删除分类的实体保护、
调序、泛化 prompt 按分类 sort_order 截断。
"""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

from pisuan.services.domain_entity_service import DomainEntityService
from pisuan.services.domain_factory_service import DomainFactoryService

pytestmark = pytest.mark.asyncio


DEFAULT_ROWS = [
    {"code": "project_basic", "name_cn": "基础工程实体", "description": "d1", "sort_order": 10, "is_active": True},
    {"code": "natural_env", "name_cn": "自然环境实体", "description": "d2", "sort_order": 20, "is_active": True},
    {
        "code": "env_quality",
        "name_cn": "环境质量与污染源实体",
        "description": "d3",
        "sort_order": 30,
        "is_active": True,
    },
]


class _FakeCategoryRepo:
    def __init__(self, rows=DEFAULT_ROWS):
        self.rows = [dict(row) for row in rows]

    async def list_categories(self, include_inactive: bool = True):
        rows = sorted(self.rows, key=lambda row: (row["sort_order"], row["code"]))
        return [dict(row) for row in rows if include_inactive or row["is_active"]]

    async def get(self, code: str):
        return next((dict(row) for row in self.rows if row["code"] == code), None)

    async def create(self, data: dict):
        row = {
            "code": data["code"],
            "name_cn": data["name_cn"],
            "description": data.get("description", ""),
            "sort_order": data.get("sort_order", 0),
            "is_active": data.get("is_active", True),
        }
        self.rows.append(row)
        return dict(row)

    async def update(self, code: str, data: dict):
        row = next(row for row in self.rows if row["code"] == code)
        row.update(
            {key: value for key, value in data.items() if key in {"name_cn", "description", "sort_order", "is_active"}}
        )
        return dict(row)

    async def delete(self, code: str):
        self.rows = [row for row in self.rows if row["code"] != code]

    async def reorder(self, codes: list[str]):
        for index, code in enumerate(codes, start=1):
            next(row for row in self.rows if row["code"] == code)["sort_order"] = index * 10
        return await self.list_categories()

    async def rank_map(self):
        return {row["code"]: row["sort_order"] for row in self.rows}


class _FakeEntityRepo:
    def __init__(self, entities=()):
        self.entities = [dict(entity) for entity in entities]

    async def counts_by_category(self, domain_code=None):
        return dict(Counter(entity["category"] for entity in self.entities))

    async def count_by_category(self, category: str, domain_code=None):
        return sum(1 for entity in self.entities if entity["category"] == category)

    async def get_by_key(self, entity_key: str, domain_code=None):
        return None

    async def create(self, data: dict):
        self.entities.append(dict(data))
        return SimpleNamespace(to_dict=lambda: dict(data))

    async def list_all(self, category=None, domain_code=None):
        return [dict(entity) for entity in self.entities]


def _service(entities=(), rows=DEFAULT_ROWS) -> DomainEntityService:
    service = DomainEntityService()
    service.repo = _FakeEntityRepo(entities)
    service.category_repo = _FakeCategoryRepo(rows)
    return service


def _entity(category: str, name: str, **overrides) -> dict:
    data = {
        "entity_id": f"id-{name}",
        "entity_key": f"key_{name}",
        "name_cn": name,
        "category": category,
        "properties": [],
    }
    data.update(overrides)
    return data


# ========== Taxonomy ==========


async def test_taxonomy_follows_dictionary_order_and_includes_empty_categories():
    service = _service([_entity("env_quality", "噪声")])
    taxonomy = await service.get_taxonomy()

    codes = [domain["domain_id"] for domain in taxonomy["domains"]]
    # 字典顺序（10/20/30），不是字母序（env_quality 在前）
    assert codes == ["project_basic", "natural_env", "env_quality"]
    assert [domain["entity_count"] for domain in taxonomy["domains"]] == [0, 0, 1]
    assert taxonomy["domains"][0]["domain_name"] == "基础工程实体"
    assert taxonomy["domains"][0]["categories"][0]["category_name"] == "project_basic"
    assert taxonomy["domains"][0]["categories"][0]["category_label"] == "基础工程实体"
    assert taxonomy["domains"][0]["is_active"] is True


async def test_taxonomy_keeps_inactive_category_only_when_it_has_entities():
    rows = [dict(row) for row in DEFAULT_ROWS]
    rows[1]["is_active"] = False  # natural_env 停用且为空 → 不渲染
    rows[2]["is_active"] = False  # env_quality 停用但有实体 → 保留
    service = _service([_entity("env_quality", "噪声")], rows)

    codes = [domain["domain_id"] for domain in (await service.get_taxonomy())["domains"]]
    assert codes == ["project_basic", "env_quality"]


async def test_taxonomy_appends_unknown_categories_from_data():
    service = _service([_entity("legacy_cat", "历史实体")])

    domains = (await service.get_taxonomy())["domains"]
    assert [domain["domain_id"] for domain in domains] == [
        "project_basic",
        "natural_env",
        "env_quality",
        "legacy_cat",
    ]
    assert domains[-1]["domain_name"] == "legacy_cat"
    assert domains[-1]["entity_count"] == 1


# ========== 实体 category 校验 ==========


async def test_create_entity_accepts_dictionary_category():
    service = _service()
    created = await service.create_entity({"entity_key": "probe", "name_cn": "探针", "category": "natural_env"})
    assert created["category"] == "natural_env"


async def test_create_entity_rejects_unknown_category():
    service = _service()
    with pytest.raises(ValueError, match="不在分类字典中"):
        await service.create_entity({"entity_key": "probe", "name_cn": "探针", "category": "no_such"})


# ========== 分类 CRUD / 调序 / 删除保护 ==========


async def test_delete_category_rejects_when_entities_exist():
    service = _service([_entity("env_quality", "噪声")])
    with pytest.raises(ValueError, match="还有 1 个实体"):
        await service.delete_category("env_quality")


async def test_delete_empty_category_succeeds():
    service = _service()
    await service.delete_category("natural_env")
    assert [row["code"] for row in await service.category_repo.list_categories()] == [
        "project_basic",
        "env_quality",
    ]


async def test_reorder_categories_rewrites_sort_order():
    service = _service()
    rows = await service.reorder_categories(["env_quality", "project_basic", "natural_env"])
    assert [row["code"] for row in rows] == ["env_quality", "project_basic", "natural_env"]
    assert [row["sort_order"] for row in rows] == [10, 20, 30]


async def test_list_categories_carries_entity_count():
    service = _service([_entity("env_quality", "噪声"), _entity("env_quality", "废水")])
    rows = await service.list_categories()
    assert {row["code"]: row["entity_count"] for row in rows} == {
        "project_basic": 0,
        "natural_env": 0,
        "env_quality": 2,
    }


# ========== 泛化 prompt 截断顺序 ==========


async def test_schema_variables_follow_category_sort_order(monkeypatch):
    """字典序 project_basic(10) < natural_env(20) 决定了谁先进入 60 个名额。"""
    from pisuan.repositories import domain_entity_category_repository as category_repo_module
    from pisuan.repositories import domain_entity_repository as entity_repo_module

    entities = [
        _entity(
            "natural_env",
            "B实体",
            entity_key="b_entity",
            properties=[{"key": "b1", "name_cn": "B属性", "value_type": "String"}],
        ),
        _entity(
            "project_basic",
            "A实体",
            entity_key="a_entity",
            properties=[
                {"key": "a1", "name_cn": "A属性", "value_type": "String"},
                {"key": "a2", "name_cn": "A属性2", "value_type": "String"},
            ],
        ),
    ]

    class _Repo(entity_repo_module.DomainEntityRepository):
        async def list_all(self, category=None, domain_code=None):
            return [dict(entity) for entity in entities]

    class _CategoryRepo(category_repo_module.DomainEntityCategoryRepository):
        async def rank_map(self):
            return {"project_basic": 10, "natural_env": 20}

    monkeypatch.setattr(entity_repo_module, "DomainEntityRepository", _Repo)
    monkeypatch.setattr(category_repo_module, "DomainEntityCategoryRepository", _CategoryRepo)

    variables = await DomainFactoryService._load_entity_schema_variables(SimpleNamespace(), "general", max_items=2)
    # 只取前 2 个：project_basic 的 a1/a2 全部命中，natural_env 被挤出
    assert [item["key"] for item in variables] == ["a_entity.a1", "a_entity.a2"]
