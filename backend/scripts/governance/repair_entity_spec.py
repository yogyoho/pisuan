# 《实体对象构建规范》存量数据治理脚本（配套 audit_entity_spec.py 使用）。
#
# 按预置映射一次性修复审计出的全部违规；默认 dry-run 只打印计划，--apply 落库：
#   1) 备份 export_all → /tmp/entity-spec-backup-<时间戳>.json
#   2) 逐实体更新（属性删除/改名/类型/单位/枚举/提示 + 实体级 Object/分类/名称/别名）
#      改名保留 name_cn → 每次保存自动触发 WAITING_REVIEW 任务插槽按名归一
#   3) trash 实体头的任务插槽引用显式改写/清空（必须在更新之后：更新触发的
#      重映射会按静态表回填空槽，trash 实体未删除前过滤不生效）
#   4) trash 前扫描引用面，确认无残留后软删除冗余实体 → 全量自动重绑定 → 复核
#
# 用法（api 容器内）：
#   python -m scripts.governance.repair_entity_spec            # dry-run
#   python -m scripts.governance.repair_entity_spec --apply
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------- 属性改名（保留 name_cn，引用由保存后的重映射按名归一） ----------
RENAMES: dict[str, dict[str, str]] = {
    "ecological_function_zoning": {
        "全国生态功能区划图号": "national_zoning_map_number",
        "区域生态功能区划图号": "regional_zoning_map_number",
    },
    "soil_erosion": {
        "重点治理区名称": "key_control_area_name",
        "主要侵蚀类型": "main_erosion_type",
        "侵蚀子类型1": "erosion_subtype_1",
        "侵蚀子类型2": "erosion_subtype_2",
        "主要侵蚀强度类型": "main_erosion_intensity_type",
        "主要侵蚀面积占比": "main_erosion_area_ratio",
        "次要侵蚀强度类型": "secondary_erosion_strength_type",
        "次要侵蚀面积占比": "secondary_erosion_area_ratio",
        "主要侵蚀分布区域": "main_erosion_distribution_area",
        "水蚀原因描述": "water_erosion_cause_desc",
        "水土保持分区类型": "soil_conservation_zoning_type",
    },
    "soil_environment": {
        "土壤类型": "soil_type",
        "有机质含量下限": "organic_matter_min",
        "有机质含量上限": "organic_matter_max",
    },
    "groundwater_quality": {
        "监测时间": "monitoring_time",
        "监测点总数": "total_monitoring_points",
        "水质指标名称": "quality_indicator_name",
        "最大值数值": "max_value",
        "最小值数值": "min_value",
    },
    "topography": {
        "矿区名称": "mining_area_name",
        "所在区域": "located_region",
        "地势特征": "terrain_characteristic",
        "地表起伏情况": "surface_undulation",
        "地貌类型": "geomorphic_type",
        "海拔最小值": "elevation_min",
        "海拔最大值": "elevation_max",
        "相对高差最小值": "relative_height_diff_min",
        "相对高差最大值": "max_relative_height_diff",
        "主要地貌类型名称": "main_geomorphic_type_name",
        "地貌部位": "geomorphic_position",
        "地貌描述": "geomorphology_description",
        "地势描述": "terrain_description",
        "地貌类型一名称": "geomorphic_type_1_name",
        "地貌类型一面积数值": "geomorphic_type_1_area_value",
        "地貌类型一面积占比数值": "geomorphic_type_1_area_ratio",
        "地貌类型二名称": "geomorphic_type_2_name",
        "地貌类型二面积数值": "geomorphic_type_2_area_value",
        "地貌类型二面积占比数值": "geomorphic_type_2_area_ratio",
        "地貌类型三名称": "geomorphic_type_3_name",
        "地貌类型三面积数值": "geomorphic_type_3_area_value",
        "地貌类型三面积占比数值": "geomorphic_type_3_area_ratio",
    },
    "noise_quality": {
        "监测点位位置": "monitoring_point_location",
        "监测点数量": "monitoring_point_count",
    },
    "air_quality_status": {
        "规划环评名称": "planning_eia_source",
        "采样时间": "sampling_time",
        "监测点位信息": "monitoring_points_info",
        "污染物名称": "pollutant_name",
        "平均时段": "averaging_period",
        "浓度最小值": "concentration_min",
        "浓度最大值": "concentration_max",
        "最大占标率数值": "max_ratio",
    },
    "vegetation_quadrat_survey": {"样方调查表编号": "quadrat_survey_table_id"},
    "climate": {
        "区域名称": "region_name",
        "所属区域": "belonging_region",
        "地理位置": "geographic_location",
        "年平均气温": "annual_mean_temp",
        "年均温度下限": "annual_temp_min",
        "年均温度上限": "annual_temp_max",
        "极端最高气温": "extreme_max_temp",
        "极端最低气温": "extreme_min_temp",
        "年均无霜期下限": "frost_free_period_min",
        "年均无霜期上限": "frost_free_period_max",
        "降水量下限": "annual_precipitation_min",
        "降水量上限": "annual_precipitation_max",
    },
    "hydrogeology": {
        "含水层名称": "aquifer_name",
        "含水层类型": "aquifer_type",
        "含水层性质": "aquifer_property",
        "水位埋深数值": "groundwater_level_depth",
        "埋深范围": "depth_range",
        "压力水头最小值": "pressure_head_min",
        "压力水头最大值": "pressure_head_max",
        "径流条件": "runoff_condition",
        "主要补给方式": "main_recharge_mode",
        "主要排泄方式": "main_discharge_mode",
        "人工开采情况": "artificial_exploitation",
        "隔水层名称": "aquifuge_name",
    },
    "river": {
        "河流类型描述": "river_type_description",
        "国际河流描述": "international_river_desc",
        "河流长度数值": "river_length_km",
        "注入河流名称": "inflow_river_name",
        "汇入河流名称": "confluence_river_name",
        "河流位置描述": "river_position_description",
        "河流性质": "river_nature",
        "河流发源地": "river_source_location",
        "参考河流方位": "reference_river_aspect",
        "河流级别": "river_grade",
        "汇入河流": "confluence_river",
        "上级河流": "parent_river",
        "河流等级": "river_class",
        "河流名称1": "river_name_1",
        "河流名称2": "river_name_2",
        "河流名称3": "river_name_3",
        "边界河流名称": "boundary_river_name",
    },
    "eco_protection_targets": {
        "保护目标列表": "protection_target_list",
        "保护目标名称": "protection_target_name",
    },
    "eco_assessment_scope": {"生态评价范围面积数值": "eco_scope_area_value"},
    "socio_economy": {
        "行政区域名称": "admin_region_name",
        "总面积数值": "total_area_value",
        "总人口数值": "total_population_value",
        "数据年份": "data_year",
        "生产总值数值": "gdp_value",
        "生产总值同比增长": "gdp_growth_rate",
        "工业增加值数值": "industrial_added_value",
        "社会消费品零售总额数值": "retail_sales_total_value",
        "民族构成": "ethnic_composition",
        "居首位矿种列表": "leading_energy_mineral",
        "排名位置1": "ranking_position_1",
    },
    "ecological_quality": {
        "评价范围面积": "evaluation_area_value",
        "样方网格边长数值": "quadrat_grid_side_value",
        "高优势度景观类型": "dominant_landscape_type",
        "优势度数值": "dominance_value",
        "连通度Rd": "connectivity_rd",
        "连通度Rf": "connectivity_rf",
        "其他景观类型及优势度": "other_landscape_dominance",
        "净第一性生产力数值": "npp_value",
        "生产力等级": "productivity_grade",
        "Shannon-Weaver多样性指数H": "shannon_weaver_index",
        "最大多样性指数": "max_diversity_index",
        "多样性程度描述": "diversity_description",
        "群落类型数": "community_type_count",
        "计算公式名称": "calculation_formula_name",
        "结果表格编号": "result_table_id",
    },
    "protected_target": {
        "保护目标列表": "protection_target_list",
        "evaluation_range_expand_distance": "expand_distance_value",
    },
    "remote_sensing_data": {"遥感影像年份": "imagery_year"},
}

# ---------- 直接删除的属性（重名孪生 / “单位”拆分属性 / 语义重复的旧键） ----------
DELETES: dict[str, list[str]] = {
    "soil_erosion": [
        "水土保持规划名称",
        "规划年份",
        "水土流失重点治理区级别",
        "建议措施",
        "main_erosion_intensity_area_ratio",
        "secondary_erosion_area_ratio",
        "secondary_erosion_distribution_area",
    ],
    "soil_environment": ["母质类型", "钙积层深度起点", "钙积层深度终点"],
    "topography": [
        "东北部地势特征",
        "地貌类型一面积单位",
        "地貌类型二面积单位",
        "地貌类型三面积单位",
        "northeast_elevation_feature",
        "max_relative_height_diff",
        "elevation_unit",
        "relative_height_unit",
    ],
    "surface_water_quality": ["断面位置表格编号", "断面位置图编号", "section_position_table_id"],
    "noise_quality": ["报告名称"],
    "air_quality_status": ["concentration_unit"],
    "climate": [
        "夏季气温下限",
        "夏季气温上限",
        "冬季平均气温",
        "最大温差",
        "温度日较差",
        "积雪天数下限",
        "积雪天数上限",
        "年降水量最大值",
        "蒸发量下限",
        "蒸发量上限",
        "相对湿度下限",
        "相对湿度上限",
        "主导风向",
        "平均风速下限",
        "平均风速上限",
        "最大风速",
        "开始冻结时间",
        "完全解冻时间",
        "最大冻结深度",
        "逆温带海拔下限",
        "逆温带海拔上限",
        "逆温带温差下限",
        "逆温带温差上限",
        "temperature_daily_range",
        "maximum_frozen_depth",
        "dominant_wind_direction",
    ],
    "hydrogeology": [
        "含水层岩性",
        "地层时代",
        "径流方向",
        "水力坡度最小值",
        "水力坡度最大值",
        "富水性等级",
        "recharge_mode",
        "discharge_mode",
    ],
    "river": ["河流长度单位", "basin_coordinate_range"],
    "eco_assessment_scope": ["expansion_distance_unit"],
    "ecological_quality": ["样方网格边长单位", "生产力单位"],
    "protected_target": [
        "evaluation_area_area_unit",
        "mining_area_area_unit",
        "expend_distance_unit",
    ],
    "npp_model_parameters": ["radiation_unit"],
    "ecological_integrity_assessment": ["radiation_unit"],
    "biodiversity_assessment": ["h_max", "h_value"],
    # 指标完全相同的“数值”双份：英文名即幸存属性名，引用由重映射按名归一
    "socio_economy": [
        "第一产业增加值数值",
        "第二产业增加值数值",
        "第三产业增加值数值",
        "固定资产投资数值",
        "一般公共预算收入数值",
        "人均生产总值数值",
        "城镇居民人均可支配收入数值",
        "矿种总数",
    ],
}

# ---------- 幸存属性的类型/单位/枚举/提示修正（key 用改名后的最终键） ----------
DIMLESS = "无量纲"
PROTECTED_TARGET_ENUM = ["人居类保护目标", "文物类保护目标", "水资源类保护目标", "生态红线类保护目标"]
PROP_OPS: dict[str, dict[str, dict]] = {
    "groundwater_quality": {
        "total_monitoring_points": {"value_type": "Integer", "unit": DIMLESS},
        "max_value_numeric": {"unit": "mg/L"},
        "min_value_numeric": {"unit": "mg/L"},
        "monitoring_year": {"unit": DIMLESS},
        "monitoring_month": {"unit": DIMLESS},
        "coincident_point_count": {"unit": DIMLESS},
        "new_point_count": {"unit": DIMLESS},
        "groundwater_level_buried_depth": {"value_type": "Float", "unit": "m"},
    },
    "topography": {
        "geomorphic_type_1_area_value": {"unit": "km²"},
        "geomorphic_type_1_area_ratio": {"unit": "%"},
        "geomorphic_type_2_area_value": {"unit": "km²"},
        "geomorphic_type_2_area_ratio": {"unit": "%"},
        "geomorphic_type_3_area_value": {"unit": "km²"},
        "geomorphic_type_3_area_ratio": {"unit": "%"},
    },
    "noise_quality": {"monitoring_point_count": {"value_type": "Integer", "unit": DIMLESS}},
    "river": {
        "river_length_km": {"unit": "km"},
        "historical_max_flood_year": {"unit": DIMLESS},
        "historical_max_flood_month": {"unit": DIMLESS},
    },
    "vegetation_quadrat_survey": {"total_quadrat_count": {"value_type": "Integer", "unit": DIMLESS}},
    "air_quality_status": {
        "hourly_avg_concentration_min": {"value_type": "Float", "unit": "μg/m³"},
        "hourly_avg_concentration_max": {"unit": "μg/m³"},
        "daily_avg_concentration_min": {"unit": "μg/m³"},
        "daily_avg_concentration_max": {"unit": "μg/m³"},
    },
    "socio_economy": {
        "data_year": {"value_type": "Integer", "unit": DIMLESS},
        "town_count": {"value_type": "Integer", "unit": DIMLESS},
        "farm_count": {"value_type": "Integer", "unit": DIMLESS},
        "subdistrict_office_count": {"value_type": "Integer", "unit": DIMLESS},
        "ethnic_total_count": {"value_type": "Integer", "unit": DIMLESS},
        "mineral_types_count": {"value_type": "Integer", "unit": DIMLESS},
        "township_count": {"unit": DIMLESS},
    },
    "wildlife_survey": {
        "survey_year": {"unit": DIMLESS},
        "transect_count": {"unit": DIMLESS},
        "protected_animals_level1_count": {"unit": DIMLESS},
        "protected_animals_level2_count": {"unit": DIMLESS},
    },
    "remote_sensing_data": {"imagery_year": {"value_type": "Integer", "unit": DIMLESS}},
    "eco_assessment_scope": {
        "eco_scope_area_value": {"unit": "km²"},
        "expansion_distance_value": {"unit": "m"},
    },
    "protected_target": {
        "type": {"value_type": "Enum", "enum_options": PROTECTED_TARGET_ENUM},
        "evaluation_area_area_value": {"unit": "km²"},
        "mining_area_area_value": {"unit": "km²"},
        "expand_distance_value": {"unit": "m"},
    },
    "eco_protection_targets": {
        "target_type": {"value_type": "Enum", "enum_options": PROTECTED_TARGET_ENUM},
    },
    "ecological_quality": {
        "evaluation_area_value": {"unit": "km²"},
        "quadrat_grid_side_value": {"unit": "m"},
        "dominance_value": {"unit": DIMLESS},
        "connectivity_rd": {"unit": DIMLESS},
        "connectivity_rf": {"unit": DIMLESS},
        "npp_value": {"unit": "g/(m²·a)"},
        "shannon_weaver_index": {"unit": DIMLESS},
        "max_diversity_index": {"unit": DIMLESS},
        "community_type_count": {"value_type": "Integer", "unit": DIMLESS},
    },
    "npp_model_parameters": {"max_lue": {"unit": DIMLESS}},
    "ecological_integrity_assessment": {
        "max_light_use_efficiency": {"value_type": "Float", "unit": DIMLESS},
    },
    "biodiversity_assessment": {
        "community_type_count": {"value_type": "Integer", "unit": DIMLESS},
        "h_ratio": {"unit": "%"},
        "shannon_theoretical_max": {"unit": DIMLESS},
        "shannon_actual_value": {"unit": DIMLESS},
    },
    "landscape_ecology_assessment": {
        "quadrat_count": {"unit": DIMLESS},
        "dominant_degree": {"unit": DIMLESS},
        "rd_value": {"unit": DIMLESS},
        "rf_value": {"unit": DIMLESS},
    },
}

# ---------- 超长提示重写（≤30 字，语义保留） ----------
HINT_REWRITES: dict[tuple[str, str], str] = {
    ("wastewater_sources", "generation_volume"): "优先提取正常涌水量，单位统一为m³/d",
    ("environmental_quality_baseline", "monitor_factors"): "例：PM10、SO2、pH、COD、氨氮",
    ("environmental_quality_baseline", "compliance_status"): "关键词：满足标准要求、超标、Pi值大于1",
    ("planning_compliance", "policy_name"): "如产业结构调整指导目录、三线一单文件",
    ("land_subsidence", "subsidence_area"): "关键词沉陷影响范围/塌陷面积，统一换算为公顷",
    ("land_occupation", "area"): "单位换算：1公顷=15亩=0.01km²",
    ("land_occupation", "original_land_type"): "如耕地、林地等，重点识别基本农田",
    ("engineering_basic_info", "project_name"): "封面或第一章取全称，去除修编版等后缀",
    ("engineering_basic_info", "production_capacity"): "找生产能力/规模，万吨/年÷100即Mt/a",
}

# ---------- 实体级修改 ----------
OBJECT_ENTITIES = [
    "npp_model_parameters",
    "wildlife_survey",
    "soil_erosion",
    "soil_environment",
    "groundwater_quality",
    "topography",
    "surface_water_quality",
    "noise_quality",
    "air_quality_status",
    "climate",
    "hydrogeology",
    "socio_economy",
    "ecological_quality",
]
CATEGORY_REMAPS: dict[str, str] = {
    "climate": "natural_env",
    "topography": "natural_env",
    "hydrogeology": "natural_env",
    "river": "natural_env",
    "soil_erosion": "natural_env",
    "vegetation_type": "natural_env",
    "vegetation_quadrat_survey": "natural_env",
    "remote_sensing_data": "natural_env",
    "air_quality_status": "env_quality",
    "noise_quality": "env_quality",
    "surface_water_quality": "env_quality",
    "groundwater_quality": "env_quality",
    "soil_environment": "env_quality",
    "ecological_quality": "env_quality",
    "land_subsidence": "impact_assessment",
    "landscape_ecology_assessment": "impact_assessment",
    "biodiversity_assessment": "impact_assessment",
    "ecological_integrity_assessment": "impact_assessment",
    "eco_assessment_scope": "impact_assessment",
    "eco_protection_targets": "sensitive_target",
}
# E6：去括号注记，注记内容转别名
NAME_FIXES: dict[str, dict] = {
    "solid_waste_gangue": {"name_cn": "固体废物", "synonyms_add": ["煤矸石", "生活垃圾"]},
    "carbon_footprint": {"name_cn": "碳排放与减排", "synonyms_add": ["双碳"]},
    "public_works": {"name_cn": "公用工程", "synonyms_add": ["供水", "供电", "供热"]},
    "sensitive_villages": {"name_cn": "环境敏感目标", "synonyms_add": ["居民点"]},
}

# ---------- 合并宿主的新增属性 ----------
# soil_erosion.secondary_erosion_area_ratio / topography.max_relative_height_diff
# 曾因“删除键与改名目标同名”的幂等缺陷被误删，这里按最终形态自愈补回
NEW_PROPS: dict[str, list[dict]] = {
    "wildlife_survey": [{"key": "bird_habitat", "name_cn": "鸟类栖息区域", "value_type": "String"}],
    "environmental_measures": [
        {
            "key": "efficiency",
            "name_cn": "处理效率",
            "value_type": "String",
            "extraction_hint": "例如：脱硫效率90%、除尘效率99%",
        }
    ],
    "engineering_basic_info": [
        {"key": "project_owner", "name_cn": "项目主体", "value_type": "String"},
        {"key": "construction_nature", "name_cn": "建设性质", "value_type": "String"},
    ],
    "soil_erosion": [
        {
            "key": "secondary_erosion_area_ratio",
            "name_cn": "次要侵蚀面积占比",
            "value_type": "Float",
            "unit": "%",
        }
    ],
    "topography": [
        {
            "key": "max_relative_height_diff",
            "name_cn": "最大相对高差",
            "value_type": "Float",
            "unit": "m",
        }
    ],
}

# ---------- trash 实体头的引用显式改写（remap 机制跳过未知头，须在 trash 前执行） ----------
REF_HEAD_REMAPS: dict[str, str] = {
    "wildlife_transect_survey": "wildlife_survey",
    "protection_measures": "environmental_measures",
}
REF_SUFFIX_REMAPS: dict[tuple[str, str], str] = {
    ("protection_measures", "category"): "target_element",
}

# ---------- 学习模板插槽引用改写（学习模板不参与自动重映射，需显式改写） ----------
LEARNED_REF_REWRITES: dict[str, str] = {
    "groundwater_quality.最大值数值": "groundwater_quality.max_value_numeric",
}

# ---------- 与他实体名冲突的别名移除 ----------
SYNONYM_REMOVALS: dict[str, list[str]] = {
    # “保护目标”是 protected_target 的实体名，从 eco_protection_targets 别名中退位
    "eco_protection_targets": ["保护目标"],
}

# ---------- 软删除（回收站可恢复） ----------
TRASH = [
    # 零属性标量（规范 §4 之外的空壳概念；regulation/spatial_boundary 保留）
    "residential",
    "cultural_relic",
    "water_resource",
    "ecological_redline",
    "pollutant",
    "environmental_element",
    "judgment",
    "impact_behavior",
    "prevention_measure",
    "shallow_groundwater",
    "engineering_params",
    "project_main",
    "construction_nature",
    "lifecycle",
    "mining_technology",
    "linear_engineering",
    # 合并被并方
    "project_basic_info",
    "wildlife_transect_survey",
    "protection_measures",
]

# 已在回收站的 trash 键（重跑幂等：不存在于活跃列表视为已完成，不算错误）
TRASHED_OK: set[str] = set()


def rebuild_properties(entity: dict, errors: list[str]) -> tuple[list[dict] | None, bool]:
    """对单实体执行 删除→改名→属性级修正→新增，返回 (新属性表, 是否有变化)。"""
    key = entity["entity_key"]
    props = [dict(p) for p in entity.get("properties") or []]
    by_key = {str(p.get("key")): p for p in props}
    renames = RENAMES.get(key, {})
    deletes = set(DELETES.get(key, []))
    ops = PROP_OPS.get(key, {})
    new_props = NEW_PROPS.get(key, [])
    for np in new_props:  # 自愈补回的键在改名/删除校验中视同已存在
        by_key.setdefault(str(np.get("key")), np)

    changed = False
    survivors: dict[str, str] = {}  # casefold(old) → new
    for old, new in renames.items():
        if old not in by_key:
            if new in by_key:  # 已应用过（重跑幂等）
                continue
            errors.append(f"{key}.{old}: 待改名属性不存在")
            return None, False
        if new in by_key and new not in renames.values():
            errors.append(f"{key}: 改名目标 {new} 与既有属性冲突")
            return None, False
        survivors[old.casefold()] = new
    # 已完成改名的源键不在了 → 其目标键是幸存者，不得再被 DELETES 误删
    protected = {tgt for src, tgt in renames.items() if src not in by_key}
    for old in deletes:
        if old not in by_key or old in protected:
            continue  # 已删除（重跑幂等）/ 是改名幸存者

    # 1) 删除（受改名幸存者保护） 2) 改名（保序） 3) 属性级修正 4) 新增
    effective_deletes = deletes - protected
    result: list[dict] = []
    for p in props:
        pk = str(p.get("key"))
        if pk in effective_deletes:
            changed = True
            continue
        if pk in renames:
            p["key"] = renames[pk]
            changed = True
        final_ops = ops.get(p["key"])
        if final_ops:
            for field, value in final_ops.items():
                if p.get(field) != value:
                    p[field] = value
                    changed = True
        hint = HINT_REWRITES.get((key, p["key"]))
        if hint and str(p.get("extraction_hint") or "") != hint:
            p["extraction_hint"] = hint
            changed = True
        result.append(p)
    for np in new_props:
        if np["key"] not in {str(p.get("key")) for p in result}:
            result.append(dict(np))
            changed = True

    # 幂等性：重复执行时 alias 归一由 service 完成，这里只校验 key 唯一
    folded_seen: set[str] = set()
    for p in result:
        folded = str(p.get("key")).casefold()
        if folded in folded_seen:
            errors.append(f"{key}: 修正后属性键重复 {p.get('key')}")
            return None, False
        folded_seen.add(folded)
    return result, changed


async def rewrite_trash_head_refs(errors: list[str]) -> tuple[int, int]:
    """清理待 trash 实体头的任务插槽引用：有宿主映射的改写到宿主，
    实体级裸引用与无映射引用清空（后续由自动重绑定按名/上下文回填）。
    返回 (处理 ref 数, 任务数)。"""
    from yuxi.repositories.domain_factory_repository import (
        GENERAL_DOMAIN_CODE,
        DomainFactoryRepository,
    )

    repo = DomainFactoryRepository()
    ref_count, task_count = 0, 0
    for task_summary in await repo.list_pending_tasks_by_domain(GENERAL_DOMAIN_CODE):
        task = await repo.get_task(task_summary["id"])
        if not task or not task.source_paragraphs:
            continue
        changed = False
        for para in task.source_paragraphs:
            template = para.get("template", {}) if isinstance(para, dict) else {}
            if not isinstance(template, dict):
                continue
            for slot in template.get("slots", []) or []:
                ref = str((slot or {}).get("entity_ref") or "")
                head, sep, suffix = ref.partition(".")
                if not ref or head not in TRASH:
                    continue
                if sep and head in REF_HEAD_REMAPS:
                    new_head = REF_HEAD_REMAPS[head]
                    new_suffix = REF_SUFFIX_REMAPS.get((head, suffix), suffix)
                    slot["entity_ref"] = f"{new_head}.{new_suffix}"
                else:
                    # 实体级裸引用或无宿主映射的带属性引用：清空，交自动重绑定
                    slot["entity_ref"] = ""
                ref_count += 1
                changed = True
        if changed:
            await repo.update_task(task.id, {"source_paragraphs": task.source_paragraphs})
            task_count += 1
    return ref_count, task_count


async def scan_trash_refs() -> list[str]:
    """扫描学习模板插槽 / 待审任务插槽 / 报告 pps 中仍指向 trash 实体的引用。"""
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE

    repo = DomainEntityRepository()
    leftover: list[str] = []
    for row in await repo.list_usage_learned_templates(GENERAL_DOMAIN_CODE):
        for slot in row.get("slots") or []:
            head = str((slot or {}).get("entity_ref") or "").partition(".")[0]
            if head in TRASH:
                leftover.append(f"learned_template[{row.get('id')}] {head}")
    for row in await repo.list_usage_pending_tasks(GENERAL_DOMAIN_CODE):
        for para in row.get("source_paragraphs") or []:
            template = para.get("template", {}) if isinstance(para, dict) else {}
            if not isinstance(template, dict):
                continue
            for slot in template.get("slots", []) or []:
                head = str((slot or {}).get("entity_ref") or "").partition(".")[0]
                if head in TRASH:
                    leftover.append(f"task[{row.get('id')}] {head}")
    for row in await repo.list_usage_report_pps(GENERAL_DOMAIN_CODE):
        if str(row.get("entity_key") or "") in TRASH:
            leftover.append(f"pps[{row.get('report_id')}] {row.get('entity_key')}")
    return leftover


def hint_entities() -> set[str]:
    return {ek for (ek, _pk) in HINT_REWRITES}


def plan_summary(entities: dict[str, dict]) -> dict:
    errors: list[str] = []
    plans: dict[str, dict] = {}
    for key in sorted(
        set(RENAMES)
        | set(DELETES)
        | set(PROP_OPS)
        | set(OBJECT_ENTITIES)
        | set(CATEGORY_REMAPS)
        | set(NAME_FIXES)
        | set(NEW_PROPS)
        | hint_entities()
    ):
        entity = entities.get(key)
        if not entity:
            errors.append(f"{key}: 实体不存在")
            continue
        new_props, prop_changed = rebuild_properties(entity, errors)
        entity_changed = prop_changed or key in OBJECT_ENTITIES or key in CATEGORY_REMAPS or key in NAME_FIXES
        plans[key] = {
            "renames": len(RENAMES.get(key, {})),
            "deletes": len(DELETES.get(key, {})),
            "prop_ops": len(PROP_OPS.get(key, {})),
            "new_props": len(NEW_PROPS.get(key, {})),
            "object": key in OBJECT_ENTITIES,
            "category": CATEGORY_REMAPS.get(key),
            "name_fix": key in NAME_FIXES,
            "changed": bool(entity_changed),
        }
    for ek, pk in HINT_REWRITES:
        entity = entities.get(ek)
        if not entity or not any(str(p.get("key")) == pk for p in entity.get("properties") or []):
            errors.append(f"{ek}.{pk}: 待重写提示的属性不存在")
    for key in TRASH:
        if key not in entities and key not in TRASHED_OK:
            errors.append(f"{key}: 待 trash 实体不存在")
    return {"plans": plans, "errors": errors}


async def run(apply: bool) -> int:
    from yuxi.repositories.domain_entity_repository import DomainEntityRepository
    from yuxi.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from yuxi.services.domain_entity_service import get_entity_service
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    service = get_entity_service()
    repo = DomainEntityRepository()

    entities = {e["entity_key"]: e for e in await repo.list_all()}
    # 重跑幂等：已在回收站的 trash 键不再要求存在于活跃列表
    TRASHED_OK.update(e["entity_key"] for e in await repo.list_deleted())
    errors: list[str] = []
    summary = plan_summary(entities)
    errors.extend(summary["errors"])
    if errors:
        print("!! 映射校验失败，未执行任何修改：")
        for e in errors:
            print(f"   {e}")
        return 1

    total = {
        "renames": sum(p["renames"] for p in summary["plans"].values()),
        "deletes": sum(p["deletes"] for p in summary["plans"].values()),
        "prop_ops": sum(p["prop_ops"] for p in summary["plans"].values()),
        "new_props": sum(p["new_props"] for p in summary["plans"].values()),
    }
    print(
        f"计划：属性改名 {total['renames']} / 删除 {total['deletes']} / "
        f"类型单位枚举修正 {total['prop_ops']} / 新增 {total['new_props']}；"
        f"实体级修改 {sum(1 for p in summary['plans'].values() if p['changed'])}；"
        f"提示重写 {len(HINT_REWRITES)}；trash {len(TRASH)}"
    )

    if not apply:
        for key, p in summary["plans"].items():
            if p["changed"]:
                flags = [
                    f"rename×{p['renames']}",
                    f"del×{p['deletes']}",
                    f"op×{p['prop_ops']}",
                    f"new×{p['new_props']}",
                ]
                if p["object"]:
                    flags.append("→Object")
                if p["category"]:
                    flags.append(f"cat→{p['category']}")
                if p["name_fix"]:
                    flags.append("name_fix")
                print(f"  {key}: {' '.join(flags)}")
        print("dry-run 完成（--apply 落库）")
        return 0

    # 1) 备份
    backup = await service.export_all()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"/tmp/entity-spec-backup-{stamp}.json"
    with open(backup_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(backup, f, ensure_ascii=False)
    print(f"备份已写入 {backup_path}")

    # 2) 逐实体更新（每次保存自动触发 WAITING_REVIEW 插槽按名归一；
    #    此时插槽引用保持非空，静态表回填不会介入空槽）
    updated_entities = 0
    for key, plan in summary["plans"].items():
        if not plan["changed"]:
            continue
        entity = entities[key]
        new_props, _ = rebuild_properties(entity, [])
        data: dict = {"properties": new_props}
        if key in OBJECT_ENTITIES:
            data["value_type"] = "Object"
        if key in CATEGORY_REMAPS:
            data["category"] = CATEGORY_REMAPS[key]
        if key in NAME_FIXES:
            fix = NAME_FIXES[key]
            data["name_cn"] = fix["name_cn"]
            merged = list(entity.get("synonyms") or [])
            merged += [s for s in fix["synonyms_add"] if s not in merged]
            data["synonyms"] = merged
        await service.update_entity(key, data)
        updated_entities += 1
    print(f"实体更新完成：{updated_entities} 个")

    for key, drop in SYNONYM_REMOVALS.items():
        entity = entities[key]
        merged = [s for s in (entity.get("synonyms") or []) if s not in drop]
        if len(merged) != len(entity.get("synonyms") or []):
            await service.update_entity(key, {"synonyms": merged})
            print(f"别名清理：{key} 移除 {'、'.join(drop)}")

    # 3) 清理 trash 实体头的插槽引用（必须在更新之后：更新触发的重映射
    #    会按静态表回填空槽，trash 实体未删除前过滤不生效，先清会被再填上）
    ref_n, task_n = await rewrite_trash_head_refs(errors)
    print(f"引用改写：{ref_n} 个 ref / {task_n} 个任务")

    if LEARNED_REF_REWRITES:
        from yuxi.repositories.domain_factory_repository import DomainFactoryRepository

        n_learned = await DomainFactoryRepository().rewrite_learned_template_slot_refs(LEARNED_REF_REWRITES)
        print(f"学习模板引用改写：{n_learned} 个模板")

    # 4) trash 前引用面终检，无残留后软删除（delete_entity 不触发重映射）
    leftover = await scan_trash_refs()
    if leftover:
        print("!! trash 终检发现残留引用，已中止：")
        for item in leftover[:20]:
            print(f"   {item}")
        return 1

    active_keys = {e["entity_key"] for e in await repo.list_all()}
    trashed = 0
    for key in TRASH:
        try:
            if await service.delete_entity(key):
                trashed += 1
        except ValueError:
            pass  # 已在回收站（重跑幂等）
    print(f"trash 完成：{trashed} 个（活跃 {len(active_keys) - trashed}，回收站 {trashed}）")

    # 5) 清空的引用触发一次全量自动重绑定（按属性名/上下文回填）
    from yuxi.services.domain_factory_service import get_domain_factory_service

    remapped = await get_domain_factory_service().remap_waiting_review_tasks(GENERAL_DOMAIN_CODE)
    print(f"trash 后自动重绑定：{remapped} 个任务")

    # 6) 复核：trash 实体已删除，任何残留引用都说明清理链路有缺口
    leftover = await scan_trash_refs()
    if leftover:
        print(f"!! trash 后仍有 {len(leftover)} 处残留引用，需人工排查：")
        for item in leftover[:20]:
            print(f"   {item}")
        return 1
    print("请复审：python -m scripts.governance.audit_entity_spec")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正落库（默认 dry-run）")
    raise SystemExit(asyncio.run(run(parser.parse_args().apply)))
