"""单元测试：模板系统三件套（TemplateLibrary / TemplateMatcher / TemplateGenerator）"""

from __future__ import annotations

import json

import pytest

from yuxi.services.template_library import TemplateLibrary
from yuxi.services.template_matcher import TemplateMatcher


# ------------------------------------------------------------------
# 测试用模板数据
# ------------------------------------------------------------------

SAMPLE_TEMPLATES = [
    {
        "template_id": "TPL_HEADER_WATER_01",
        "name": "水资源承载力分析章节",
        "category": "header",
        "domain": "coal_mining",
        "priority": 10,
        "match_rule": {
            "strategy": "regex_anchor",
            "regex": r"^(?P<chapter_id>\d+(\.\d+)*)\s*(?P<water_topic_text>.*(水资源|供水|用水).*(承载力|分析|评价))$",
            "confidence_threshold": 0.85,
            "fallback_keywords": ["水资源", "承载力", "供水", "用水"],
        },
        "generalized_pattern": "[SECTION] {{chapter_id}} {{water_topic_text}}",
        "slots": [
            {
                "name": "chapter_id",
                "description": "章节编号",
                "type": "String",
                "is_variable": True,
                "is_anchor": False,
                "extraction_pattern": r"\d+(\.\d+)*",
            },
            {
                "name": "water_topic_text",
                "description": "水资源相关主题文本",
                "type": "String",
                "is_variable": True,
                "is_anchor": True,
                "semantic_check": ["水资源", "承载力", "供水"],
                "semantic_category": "water_resource",
            },
        ],
        "semantic_routing": {
            "standard_code": "SEC_WATER_RESOURCE",
            "category": "Environmental_Impact_Prediction",
            "subcategory": "Water_Resource_Analysis",
            "required_skills": ["skill_water_balance_calc"],
        },
    },
    {
        "template_id": "TPL_HEADER_ECOLOGY_01",
        "name": "生态环境影响评价章节",
        "category": "header",
        "domain": "coal_mining",
        "priority": 90,
        "match_rule": {
            "strategy": "regex_anchor",
            "regex": r"^(?P<chapter_id>\d+(\.\d+)*)\s*(?P<eco_text>.*(生态|植被|水土保持).*(影响|评价|防治))$",
            "confidence_threshold": 0.80,
            "fallback_keywords": ["生态", "植被", "水土保持", "荒漠化"],
        },
        "slots": [
            {"name": "chapter_id", "description": "章节编号", "type": "String", "is_variable": True},
            {
                "name": "eco_text",
                "description": "生态相关主题",
                "type": "String",
                "is_variable": True,
                "is_anchor": True,
                "semantic_check": ["生态", "植被", "水土保持"],
            },
        ],
        "semantic_routing": {
            "standard_code": "SEC_ECOLOGY",
            "category": "Environmental_Impact_Prediction",
        },
    },
]


@pytest.fixture
def template_dir(tmp_path):
    """创建临时模板目录"""
    tpl_dir = tmp_path / "templates" / "coal_mining" / "headers"
    tpl_dir.mkdir(parents=True)

    for tpl in SAMPLE_TEMPLATES:
        with open(tpl_dir / f"{tpl['template_id']}.json", "w", encoding="utf-8") as f:
            json.dump(tpl, f, ensure_ascii=False, indent=2)

    return tmp_path / "templates"


@pytest.fixture
def template_library(template_dir):
    """创建已加载的 TemplateLibrary"""
    lib = TemplateLibrary(template_dir / "coal_mining" / "headers")
    lib.load_templates()
    return lib


@pytest.fixture
def matcher():
    """创建 TemplateMatcher"""
    return TemplateMatcher(SAMPLE_TEMPLATES)


# ------------------------------------------------------------------
# TemplateLibrary
# ------------------------------------------------------------------


class TestTemplateLibrary:
    def test_load_from_directory(self, template_dir):
        """从目录加载模板"""
        lib = TemplateLibrary(template_dir / "coal_mining" / "headers")
        result = lib.load_templates()
        assert len(result) == 2
        assert "TPL_HEADER_WATER_01" in result
        assert "TPL_HEADER_ECOLOGY_01" in result

    def test_load_single_file(self, tmp_path):
        """从单个 JSON 文件加载"""
        file_path = tmp_path / "single.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_TEMPLATES[0], f, ensure_ascii=False)

        lib = TemplateLibrary(file_path)
        result = lib.load_templates()
        assert len(result) == 1

    def test_load_wrapped_format(self, tmp_path):
        """加载 {"templates": [...]} 格式"""
        file_path = tmp_path / "wrapped.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"templates": SAMPLE_TEMPLATES}, f, ensure_ascii=False)

        lib = TemplateLibrary(file_path)
        result = lib.load_templates()
        assert len(result) == 2

    def test_caching(self, template_dir):
        """第二次调用返回缓存"""
        lib = TemplateLibrary(template_dir / "coal_mining" / "headers")
        r1 = lib.load_templates()
        r2 = lib.load_templates()
        assert r1 is r2

    def test_get_template(self, template_library):
        tpl = template_library.get_template("TPL_HEADER_WATER_01")
        assert tpl is not None
        assert tpl["name"] == "水资源承载力分析章节"
        assert template_library.get_template("nonexistent") is None

    def test_get_templates_by_domain(self, template_library):
        result = template_library.get_templates_by_domain("coal_mining")
        assert len(result) == 2
        assert len(template_library.get_templates_by_domain("other")) == 0

    def test_add_remove(self, template_dir):
        lib = TemplateLibrary(template_dir / "coal_mining" / "headers")
        lib.load_templates()

        new_tpl = {"template_id": "TPL_TEST", "name": "test", "domain": "test"}
        lib.add_template(new_tpl)
        assert lib.get_template("TPL_TEST") is not None

        assert lib.remove_template("TPL_TEST") is True
        assert lib.get_template("TPL_TEST") is None
        assert lib.remove_template("nonexistent") is False

    def test_statistics(self, template_library):
        stats = template_library.get_statistics()
        assert stats["total_templates"] == 2
        assert "Environmental_Impact_Prediction" in stats["categories"]
        assert "coal_mining" in stats["domains"]

    def test_missing_path(self, tmp_path):
        lib = TemplateLibrary(tmp_path / "nonexistent")
        result = lib.load_templates()
        assert result == {}

    def test_save_and_load(self, template_dir, tmp_path):
        lib = TemplateLibrary(template_dir / "coal_mining" / "headers")
        lib.load_templates()
        output = tmp_path / "output.json"
        lib.save_templates(output)

        lib2 = TemplateLibrary(output)
        lib2.load_templates()
        assert len(lib2.templates) == len(lib.templates)


# ------------------------------------------------------------------
# TemplateMatcher
# ------------------------------------------------------------------


class TestTemplateMatcher:
    def test_match_regex_success(self, matcher):
        """正则匹配成功"""
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "coal_mining"})
        assert result.matched is True
        assert result.template_id == "TPL_HEADER_WATER_01"
        assert result.slots.get("chapter_id") == "7.1"
        assert result.confidence >= 0.85

    def test_match_higher_priority_first(self, matcher):
        """高优先级模板先匹配"""
        # "3.1 矿区生态影响评价" 可能匹配 ecology（优先级90）或 water（优先级10）
        result = matcher.match("3.1 矿区生态环境影响评价", context={"domain": "coal_mining"})
        assert result.matched is True
        # ecology 模板优先级更高
        assert result.template_id == "TPL_HEADER_ECOLOGY_01"

    def test_match_fallback_keywords(self, matcher):
        """正则不匹配时，回退到关键词匹配"""
        result = matcher.match("水资源综合分析报告", context={"domain": "coal_mining"})
        assert result.matched is True
        assert result.confidence == 0.6  # 关键词匹配置信度
        assert "matched_keywords" in result.slots

    def test_match_no_match(self, matcher):
        """不匹配的标题"""
        result = matcher.match("噪声环境影响评价", context={"domain": "coal_mining"})
        assert result.matched is False

    def test_match_domain_filter(self, matcher):
        """领域过滤"""
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "other_domain"})
        assert result.matched is False

    def test_match_empty_title(self, matcher):
        result = matcher.match("")
        assert result.matched is False
        result = matcher.match("   ")
        assert result.matched is False

    def test_match_semantic_anchor_validation(self):
        """语义锚点验证：不包含关键词的值应被拒绝"""
        # 这个正则匹配 "7.1 xxx分析"，但 water_topic_text 需要包含水资源关键词
        templates = [
            {
                "template_id": "TEST",
                "match_rule": {
                    "strategy": "regex_anchor",
                    "regex": r"^(?P<id>\d+)\s*(?P<text>.+分析)$",
                    "confidence_threshold": 0.8,
                    "fallback_keywords": [],
                },
                "slots": [
                    {"name": "id", "type": "String", "is_variable": True},
                    {
                        "name": "text",
                        "type": "String",
                        "is_variable": True,
                        "is_anchor": True,
                        "semantic_check": ["水资源"],
                    },
                ],
            }
        ]
        matcher = TemplateMatcher(templates)

        # 应该匹配（包含关键词）
        r1 = matcher.match("1 水资源综合分析")
        assert r1.matched is True

        # 不应该匹配（不包含关键词）
        r2 = matcher.match("1 大气环境综合分析")
        assert r2.matched is False

    def test_match_routing_included(self, matcher):
        """匹配结果包含 semantic_routing"""
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "coal_mining"})
        assert result.matched is True
        assert result.routing is not None
        assert result.routing.get("standard_code") == "SEC_WATER_RESOURCE"

    def test_match_template_name(self, matcher):
        """匹配结果包含模板名称"""
        result = matcher.match("7.1 矿区水资源承载力分析", context={"domain": "coal_mining"})
        assert result.template_name == "水资源承载力分析章节"

    def test_confidence_scoring(self):
        """置信度评分：匹配更多关键词应获得更高分"""
        templates = [
            {
                "template_id": "TEST",
                "match_rule": {
                    "strategy": "regex_anchor",
                    "regex": r"^(?P<id>\d+)\s*(?P<text>.*(水资源|供水).*(分析|评价))$",
                    "confidence_threshold": 0.8,
                    "fallback_keywords": ["水资源", "供水", "承载力", "评价"],
                },
                "slots": [
                    {"name": "id", "type": "String", "is_variable": True},
                    {"name": "text", "type": "String", "is_variable": True},
                ],
            }
        ]
        matcher = TemplateMatcher(templates)

        # 匹配多个关键词 → 高置信度
        r1 = matcher.match("1 水资源供水承载力分析评价")
        assert r1.matched is True
        assert r1.confidence > 0.8

    def test_invalid_regex(self):
        """无效正则不应崩溃"""
        templates = [
            {
                "template_id": "BAD",
                "match_rule": {
                    "strategy": "regex_anchor",
                    "regex": "[invalid",
                    "confidence_threshold": 0.8,
                    "fallback_keywords": ["test"],
                },
                "slots": [],
            }
        ]
        matcher = TemplateMatcher(templates)
        result = matcher.match("test something")
        # 应该回退到关键词匹配
        assert result.matched is True
        assert result.confidence == 0.6
