# 词表注入预算的实体轮转分配单测（纯函数，无 DB）。
# 293 实体规模下旧线性遍历会让排序头部实体独占 60 名额；轮转保证覆盖面。
from pisuan.services.domain_factory_service import DomainFactoryService


def var(tag: str) -> dict:
    return {"key": tag, "data_type": "String", "label": tag, "prompt": ""}


class TestRoundRobinSchemaBudget:
    def test_breadth_first_one_prop_per_entity(self):
        # 三个实体各 3 条属性，预算 3 → 每实体 1 条（旧实现会全给第一个实体）
        per = [[var(f"a{i}") for i in range(3)], [var(f"b{i}") for i in range(3)], [var(f"c{i}") for i in range(3)]]
        out = DomainFactoryService._round_robin_schema_budget(per, 3)
        assert [v["key"] for v in out] == ["a0", "b0", "c0"]

    def test_second_round_fills_after_all_entities_served(self):
        per = [[var("a0"), var("a1")], [var("b0")]]
        out = DomainFactoryService._round_robin_schema_budget(per, 3)
        assert [v["key"] for v in out] == ["a0", "b0", "a1"]

    def test_required_first_within_entity(self):
        # required 优先排序发生在调用方（prop_list.sort），此处验证轮转顺序无关属性内容
        per = [[var("x"), var("y"), var("z")]]
        out = DomainFactoryService._round_robin_schema_budget(per, 5)
        assert [v["key"] for v in out] == ["x", "y", "z"]

    def test_budget_smaller_than_entities(self):
        per = [[var("a")]] * 100
        out = DomainFactoryService._round_robin_schema_budget(per, 60)
        assert len(out) == 60

    def test_empty_and_exhaustion(self):
        assert DomainFactoryService._round_robin_schema_budget([], 10) == []
        assert DomainFactoryService._round_robin_schema_budget([[var("a")]], 10) == [var("a")]
