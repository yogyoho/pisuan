# 属性级 synonyms：归一化 + 严格匹配器同义词索引 + 相关度字符集并入（纯函数，无 DB）。
from pisuan.services.domain_entity_service import DomainEntityService
from pisuan.services.domain_factory_service import DomainFactoryService


class TestNormalizeSynonyms:
    def test_strip_dedupe_and_own_name_removal(self):
        out = DomainEntityService.normalize_synonyms(
            [" 行政区 ", "行政区", "行政区", "", None, "行政区划"], own_name_cn="行政区"
        )
        assert out == ["行政区划"]

    def test_string_input_and_cap(self):
        out = DomainEntityService.normalize_synonyms("a,b", own_name_cn="x")  # 整串视作一条
        assert out == ["a,b"]
        out2 = DomainEntityService.normalize_synonyms([str(i) for i in range(20)])
        assert len(out2) == 8

    def test_empty(self):
        assert DomainEntityService.normalize_synonyms(None) == []
        assert DomainEntityService.normalize_synonyms([]) == []

    def test_normalize_property_passthrough(self):
        p = DomainEntityService.normalize_property(
            {"key": "admin_region", "name_cn": "行政区", "value_type": "String", "synonyms": ["行政区域", "行政区"]}
        )
        assert p["synonyms"] == ["行政区域"]


def _entities():
    return [
        {
            "entity_key": "eco_control",
            "name_cn": "环境管控单元",
            "properties": [
                {"key": "admin_region", "name_cn": "行政区", "synonyms": ["行政区域"], "value_type": "String"},
                {"key": "code", "name_cn": "管控单元编号", "synonyms": [], "value_type": "String"},
            ],
        },
        {
            "entity_key": "eco_other",
            "name_cn": "另一实体",
            "properties": [
                {"key": "admin_region2", "name_cn": "行政区", "synonyms": ["行政区域"], "value_type": "String"},
            ],
        },
    ]


def build_index():
    idx: dict[str, list[tuple[str, str, dict]]] = {}
    for e in _entities():
        for p in e["properties"]:
            idx.setdefault(p["name_cn"], []).append((e["entity_key"], p["key"], p))
            for syn in p["synonyms"]:
                idx.setdefault(syn, []).append((e["entity_key"], p["key"], p))
    return idx


class TestMatcherSynonymIndex:
    def test_synonym_exact_unique_binds(self):
        idx = {
            "行政区": [("eco_control", "admin_region", {})],
            "行政区域": [("eco_control", "admin_region", {})],
        }
        assert DomainFactoryService._match_slot_to_property("行政区域", idx) == ("eco_control", "admin_region")

    def test_synonym_ambiguous_returns_none(self):
        # 同义词在两个实体上同名 → 精确歧义，不猜
        assert DomainFactoryService._match_slot_to_property("行政区域", build_index()) is None

    def test_name_cn_ambiguous_unaffected(self):
        assert DomainFactoryService._match_slot_to_property("行政区", build_index()) is None


class TestGroupsSynonymChars:
    def test_entity_synonyms_join_char_set(self):
        pool = [[var("sub.d", "生态影响与沉陷.max_depth")]]
        groups = DomainFactoryService._build_entity_pool_groups(pool, {"生态影响与沉陷": ["沉陷"]})
        chars = groups[0][2]
        assert "沉" in chars and "陷" in chars
        # 别名「沉陷」两字即可让该组过阈值（此前复合名只靠部分字符，排序易被压头）
        text = "4.2 地表沉陷预测与沉陷深度。"
        out = DomainFactoryService._compose_para_schema_lines(text, groups, [], 200)
        assert out.splitlines()[0].startswith("- sub.")


def var(key: str, label: str) -> dict:
    return {"key": key, "data_type": "String", "label": label, "prompt": ""}
