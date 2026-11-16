# bug-4288 收紧后的槽位→实体属性确定性匹配单测（纯函数，无 DB）。
# 口径：唯一精确 → 唯一包含（较短方 ≥3 字）；歧义/模糊一律 None（宁缺勿错）。
from yuxi.services.domain_factory_service import DomainFactoryService

IDX = {
    "矿井涌水量": [("mine_water_inflow", "inflow_value", {})],
    "设备名称": [
        ("noise_equipment", "equipment_name", {}),
        ("mining_equipment", "equipment_name", {}),
    ],
    "涌水量": [("mine_water_inflow", "inflow_value", {})],
    "最大下沉值": [("land_subsidence", "max_subsidence", {})],
    "最大值数值": [("groundwater_quality", "max_value_numeric", {})],
    "采区层数": [("mining_area_section", "layer_count", {})],
}


def match(name: str):
    return DomainFactoryService._match_slot_to_property(name, IDX)


class TestStrictSlotMatching:
    def test_exact_unique_binds(self):
        assert match("矿井涌水量") == ("mine_water_inflow", "inflow_value")

    def test_exact_ambiguous_returns_none(self):
        # 两实体同名“设备名称”——旧实现先到先得绑 noise_equipment，现必须 None
        assert match("设备名称") is None

    def test_containment_unique_binds(self):
        assert match("沉陷最大下沉值") == ("land_subsidence", "max_subsidence")
        assert match("涌水量") == ("mine_water_inflow", "inflow_value")

    def test_containment_short_side_below_3_chars_rejected(self):
        # 2 字短名“数值”不参与包含匹配（历史 211 条学习模板错绑源头），
        # 但它也不是精确键 → None
        assert match("数值") is None
        # “层数”含于“采区层数”，但较短方 2 字 → 拒绝
        assert match("层数") is None

    def test_no_match_returns_none(self):
        assert match("井田名称") is None
        assert match("") is None
