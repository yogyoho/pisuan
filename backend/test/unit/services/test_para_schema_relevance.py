# 方案 C：段落相关度词表注入单测（纯函数，无 DB）。
# 评分口径：实体名字符在段文的绝对命中数 ≥2 且覆盖率 ≥0.34 视为相关；
# 主排序命中数降序、辅排序覆盖率降序；每实体至多 6 条；基线词表补足预算。
from yuxi.services.domain_factory_service import DomainFactoryService


def var(key: str, label: str) -> dict:
    return {"key": key, "data_type": "String", "label": label, "prompt": ""}


def build_pool():
    return [
        [var("sub.max_depth", "沉陷.max_depth"), var("sub.radius", "沉陷.radius"), var("sub.level", "沉陷.level")],
        [var("aq.type", "含水层.type"), var("aq.depth", "含水层.depth"), var("aq.head", "含水层水头")],
        [var("gen.count", "数据.count")],  # 泛化名「数据」不参与匹配
        [var("lu.type", "土地利用与占地.type")],
    ]


class TestBuildEntityPoolGroups:
    def test_groups_and_stoplist(self):
        groups = DomainFactoryService._build_entity_pool_groups(build_pool())
        names = [g[0] for g in groups]
        assert names == ["沉陷", "含水层", "土地利用与占地"]  # 「数据」被停用表剔除
        assert groups[0][1][0].startswith("- sub.max_depth")


class TestComposeParaSchemaLines:
    def test_relevant_entity_props_first(self):
        groups = DomainFactoryService._build_entity_pool_groups(build_pool())
        base = ["- base.1 (String): 基线一", "- base.2 (String): 基线二"]
        text = "本章预测地表沉陷深度的最大值"
        out = DomainFactoryService._compose_para_schema_lines(text, groups, base, 200)
        lines = out.splitlines()
        # 沉陷 3 条全部优先于基线
        assert lines[0].startswith("- sub.max_depth")
        assert lines[2].startswith("- sub.level")
        assert lines[3].startswith("- base.1")

    def test_more_distinct_char_hits_ranks_first(self):
        groups = DomainFactoryService._build_entity_pool_groups(build_pool())
        base = ["- base.1 (String): 基线一"]
        # 含水层命中 3 字 > 沉陷 2 字 → 含水层先
        text = "含水层渗透：沉陷区导水性评价"
        out = DomainFactoryService._compose_para_schema_lines(text, groups, base, 200)
        assert out.splitlines()[0].startswith("- aq.")

    def test_low_overlap_single_common_char_not_enough(self):
        groups = DomainFactoryService._build_entity_pool_groups(build_pool())
        base = ["- base.1 (String): 基线一"]
        # 土地利用与占地：仅命中 地/与 2 字、覆盖率 2/6 <0.34 → 不入选；沉陷命中入选
        text = "地表沉陷范围的与图圈定"
        out = DomainFactoryService._compose_para_schema_lines(text, groups, base, 200)
        first = out.splitlines()[0]
        assert first.startswith("- sub.")
        assert "土地利用与占地" not in first

    def test_budget_cap(self):
        groups = DomainFactoryService._build_entity_pool_groups(build_pool())
        base = [f"- base.{i} (String): 基线{i}" for i in range(50)]
        text = "沉陷区含水层"
        out = DomainFactoryService._compose_para_schema_lines(text, groups, base, 5)
        assert len(out.splitlines()) == 5

    def test_no_hit_falls_back_to_base(self):
        groups = DomainFactoryService._build_entity_pool_groups(build_pool())
        base = ["- base.1 (String): 基线一"]
        out = DomainFactoryService._compose_para_schema_lines("毫不相关的叙述内容", groups, base, 200)
        assert out.splitlines() == base

    def test_per_entity_cap_six(self):
        pool = [[var(f"s.{i}", f"采区工作面.prop{i}") for i in range(10)]]
        groups = DomainFactoryService._build_entity_pool_groups(pool)
        out = DomainFactoryService._compose_para_schema_lines("采区工作面推进", groups, [], 200)
        assert len(out.splitlines()) == 6  # 每实体至多 6 条
