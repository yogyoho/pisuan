"""单元测试：entity_meta_service.py 的四个核心类"""

from __future__ import annotations

import json

import pytest

from yuxi.services.entity_meta_service import (
    EntityMetaAdapter,
    EntityMetaLoader,
    EntityMetaMatcher,
    SlotEntityMapper,
)


# ------------------------------------------------------------------
# 测试用实体数据
# ------------------------------------------------------------------

SAMPLE_ENTITIES = {
    "project_main": {
        "id": "project_main",
        "name": "项目主体",
        "category": "基础工程实体",
        "description": "建设项目的基本信息",
        "examples": ["煤矿", "选煤厂", "矿井"],
        "keywords": ["项目", "工程", "主体"],
    },
    "water_resource": {
        "id": "water_resource",
        "name": "水资源",
        "category": "环境要素与影响实体",
        "description": "水资源及水环境相关要素",
        "examples": ["地下水", "地表水", "河流"],
        "keywords": ["水", "水资源", "水环境"],
    },
}


@pytest.fixture
def entity_json_file(tmp_path):
    """创建临时实体类型 JSON 文件"""
    file_path = tmp_path / "entity_types.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_ENTITIES, f, ensure_ascii=False)
    return file_path


# ------------------------------------------------------------------
# EntityMetaLoader
# ------------------------------------------------------------------


class TestEntityMetaLoader:
    def test_load_dict_format(self, entity_json_file):
        """加载 dict 格式的实体类型文件"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        result = loader.load()
        assert len(result) == 2
        assert "project_main" in result
        assert result["project_main"]["name"] == "项目主体"

    def test_load_list_format(self, tmp_path):
        """加载 list 格式的实体类型文件"""
        file_path = tmp_path / "entities_list.json"
        entities_list = list(SAMPLE_ENTITIES.values())
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(entities_list, f, ensure_ascii=False)

        loader = EntityMetaLoader(entity_types_path=file_path)
        result = loader.load()
        assert len(result) == 2

    def test_load_caching(self, entity_json_file):
        """第二次调用应返回缓存"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        r1 = loader.load()
        r2 = loader.load()
        assert r1 is r2

    def test_load_missing_file(self, tmp_path):
        """文件不存在时返回空字典"""
        loader = EntityMetaLoader(entity_types_path=tmp_path / "nonexistent.json")
        result = loader.load()
        assert result == {}

    def test_clear_cache(self, entity_json_file):
        """清除缓存后重新加载"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        r1 = loader.load()
        loader.clear_cache()
        r2 = loader.load()
        assert r1 is not r2
        assert len(r1) == len(r2)

    def test_get_entity(self, entity_json_file):
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        entity = loader.get_entity("project_main")
        assert entity is not None
        assert entity["name"] == "项目主体"
        assert loader.get_entity("nonexistent") is None

    def test_get_entities_by_category(self, entity_json_file):
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        result = loader.get_entities_by_category("基础工程实体")
        assert len(result) == 1
        assert result[0]["id"] == "project_main"

    def test_get_all_categories(self, entity_json_file):
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        cats = loader.get_all_categories()
        assert "基础工程实体" in cats
        assert "环境要素与影响实体" in cats


# ------------------------------------------------------------------
# EntityMetaAdapter
# ------------------------------------------------------------------


class TestEntityMetaAdapter:
    def test_enhance_schema_variables_basic(self):
        """增强已有变量并追加缺失的实体变量"""
        adapter = EntityMetaAdapter()
        existing_vars = [
            {"key": "项目名称", "label": "项目名称", "data_type": "string", "widget": "Input"},
            {"key": "产能", "label": "设计产能", "data_type": "float", "widget": "InputNumber"},
        ]
        enhanced = adapter.enhance_schema_variables(existing_vars, SAMPLE_ENTITIES)

        # 应包含原始变量
        keys = [v["key"] for v in enhanced]
        assert "项目名称" in keys
        assert "产能" in keys

        # 实体"project_main"应通过关键词匹配到"项目名称"变量
        project_var = next(v for v in enhanced if v["key"] == "项目名称")
        assert project_var.get("_entity_id") == "project_main"

        # 缺失的实体应被追加
        assert "water_resource" in keys

    def test_enhance_empty_entities(self):
        """无实体时返回原始变量"""
        adapter = EntityMetaAdapter()
        variables = [{"key": "test", "label": "test"}]
        result = adapter.enhance_schema_variables(variables, {})
        assert result == variables

    def test_enhance_preserves_existing_fields(self):
        """增强不覆盖已有字段"""
        adapter = EntityMetaAdapter()
        variables = [
            {"key": "project_main", "label": "项目", "prompt": "自定义提示", "data_type": "string"},
        ]
        enhanced = adapter.enhance_schema_variables(variables, SAMPLE_ENTITIES)
        project_var = next(v for v in enhanced if v["key"] == "project_main")
        # 已有 prompt 不应被覆盖
        assert project_var["prompt"] == "自定义提示"


# ------------------------------------------------------------------
# EntityMetaMatcher
# ------------------------------------------------------------------


class TestEntityMetaMatcher:
    def test_match_paragraph(self, entity_json_file):
        """匹配段落中出现的实体"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        matcher = EntityMetaMatcher(loader)
        results = matcher.match_paragraph("项目概况", "本项目为煤矿工程，水资源丰富")
        # 应匹配到 project_main 和 water_resource
        ids = [e["id"] for e in results]
        assert "project_main" in ids
        assert "water_resource" in ids

    def test_match_no_match(self, entity_json_file):
        """不匹配无关内容"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        matcher = EntityMetaMatcher(loader)
        results = matcher.match_paragraph("噪声", "声环境质量标准 GB 3096-2008")
        # 不应匹配到任何实体
        assert len(results) == 0

    def test_match_empty_entities(self, tmp_path):
        """空实体库返回空结果"""
        file_path = tmp_path / "empty.json"
        with open(file_path, "w") as f:
            json.dump({}, f)
        loader = EntityMetaLoader(entity_types_path=file_path)
        matcher = EntityMetaMatcher(loader)
        results = matcher.match_paragraph("项目", "煤矿")
        assert results == []


# ------------------------------------------------------------------
# SlotEntityMapper
# ------------------------------------------------------------------


class TestSlotEntityMapper:
    def test_map_slots_direct_match(self, entity_json_file):
        """直接匹配插槽名称到实体"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        mapper = SlotEntityMapper(loader)
        slots = [
            {"name": "project_main", "type": "string"},
            {"name": "water_resource", "type": "string"},
        ]
        mapped = mapper.map_slots(slots)
        assert mapped[0]["entity_ref"] == "project_main"
        assert mapped[1]["entity_ref"] == "water_resource"

    def test_map_slots_keyword_match(self, entity_json_file):
        """通过关键词匹配"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        mapper = SlotEntityMapper(loader)
        slots = [{"name": "项目", "type": "string"}]
        mapped = mapper.map_slots(slots)
        assert mapped[0]["entity_ref"] == "project_main"

    def test_map_slots_no_match(self, entity_json_file):
        """不匹配的插槽不变"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        mapper = SlotEntityMapper(loader)
        slots = [{"name": "噪声等级", "type": "string"}]
        mapped = mapper.map_slots(slots)
        assert "entity_ref" not in mapped[0]

    def test_map_slots_preserves_existing_entity_ref(self, entity_json_file):
        """已有的 entity_ref 不被覆盖"""
        loader = EntityMetaLoader(entity_types_path=entity_json_file)
        mapper = SlotEntityMapper(loader)
        slots = [{"name": "project_main", "entity_ref": "custom_ref"}]
        mapped = mapper.map_slots(slots)
        assert mapped[0]["entity_ref"] == "custom_ref"

    def test_map_slots_empty_entities(self, tmp_path):
        """空实体库返回原始插槽"""
        file_path = tmp_path / "empty.json"
        with open(file_path, "w") as f:
            json.dump({}, f)
        loader = EntityMetaLoader(entity_types_path=file_path)
        mapper = SlotEntityMapper(loader)
        slots = [{"name": "test"}]
        mapped = mapper.map_slots(slots)
        assert mapped == slots
