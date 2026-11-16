# Route B 归纳落库：把语料普查候选按「明显错误才剔除、其余全保留」口径写入通用域实体库。
#
# 四阶段（均在 api 容器内执行）：
#   --plan       候选 → 落库计划 /tmp/induction-plan.json（合并同义簇、路由现有实体、过滤重复属性）
#   --translate  LLM 批量生成 snake_case 键（新实体缺 key + 属性名全量），断点续跑
#   --classify   LLM 给新实体分配六分类，断点续跑
#   --apply      按计划走 DomainEntityService 正常编辑流落库（create_entity/update_entity）
#
# 剔除口径（只剔明显错误）：
#   1) 新实体候选 key 与活跃实体 key 冲突 → 属性并入该现有实体（不新建）
#   2) 同义拆分簇（下方 MERGE_CLUSTERS，人工梳理的明显同概念分家）→ 合并、属性并集
#   3) 归一化 name_cn 完全相同的新对象 → 自动并入跨切片次数最高者
#   4) 现有实体属性新增：目标实体已有同名属性跳过；与其他实体现有属性精确同名的跳过
#      （避免扩大精确名歧义面——槽位自动映射对同名属性是先到先得）
#   5) 沉陷族/矸石等按 EXISTING_ROUTES 并入现有实体
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CANDIDATES_PATH = Path("/tmp/route-b/candidates.json")
PLAN_PATH = Path("/tmp/induction-plan.json")
KEYS_PATH = Path("/tmp/induction-keys.json")
CLS_PATH = Path("/tmp/induction-classes.json")
TRANSLATE_MODEL = "openai2:agnes-2.5-flash"

# 人工梳理的同义拆分簇：canonical = (english_key, name_cn)，members 按候选 obj_key 列出。
MERGE_CLUSTERS = [
    ("coal_quality", "煤质特征", ["coal_quality", "coal_properties", "coal_quality_params", "coal_quality_param", "coal_quality_parameter", "coal", "coal_characteristics", "new::煤质分析指标", "coal_seam_characteristics", "new::商品煤质量指标", "coal_quality_params"]),
    ("coal_seam", "煤层", ["coal_seam", "new::煤层特征", "new::可采煤层", "coalmill_field"]),
    ("coal_resource_reserve", "资源储量", ["coal_resource_reserve", "mine_reserve", "new::资源储量平衡表", "new::地质资源与储量", "new::矿产资源", "ore_block_reserve_by_tonnage", "reclaimed_resource"]),
    ("clean_production_indicators", "清洁生产", ["clean_production_indicators", "cleaning_production_indicator", "cleaner_production_assessment", "clear_production_assessment", "cleaner_production_indicator", "clean_production_index", "cleaner_production_index", "cleaning_production_evaluation", "coal_mining_cleaning_process_indicator", "coal_mining_resource_energy_indicator", "coal_mining_ecological_indicator", "coal_mining_resource_reuse_indicator", "coal_mine_reclaim_rate", "environmental_management_requirement", "mining_mechanization"]),
    ("external_waste_dump", "外排土场", ["external_waste_dump", "new::外排土场", "spill_ground", "waste_dump_site"]),
    ("gangue_disposal_site", "排矸场（矸石周转场）", ["gangue_disposal_site", "temporary_gangue_storage_site", "temporary_discharge_yard", "solid_waste_gangue_pile"]),
    ("hazardous_waste", "危险废物", ["hazardous_waste", "solid_waste_hazardous", "hazardous_waste_detail"]),
    ("hazardous_substance", "危险物质", ["hazardous_substance", "new::危险物质", "hazardous_material", "hazardous_substance_assessment"]),
    ("hazardous_waste_storage", "危险废物暂存设施", ["hazardous_waste_storage", "dangerous_waste_storage", "waste_storage_facility"]),
    ("domestic_sewage_treatment_facility", "生活污水处理站", ["domestic_sewage_treatment_facility", "domestic_wastewater_treatment_station", "domestic_sewage_treatment_station"]),
    ("mine_water_treatment_facility", "矿井水处理设施", ["mine_water_treatment_facility", "water_treatment_facility", "minewater_treatment_facility", "wastewater_treatment_station", "mining_water_treatment", "mine_water_treatment", "treatment_structures"]),
    ("mine_water_reuse", "矿井水综合利用", ["mine_water_recycle", "mine_pit_water_utilization", "mine_water_resources_utilization", "mine_water_utilization", "mine_water_reuse", "mine_water_management"]),
    ("domestic_sewage_recycle", "生活污水综合利用", ["domestic_sewage_recycle", "domestic_wastewater_utilization", "domestic_waste_utilization"]),
    ("coal_preparation_plant", "选煤厂", ["coal_preparation_plant", "coal_washing_plant", "new::选煤厂", "plant"]),
    ("boiler_emissions", "锅炉烟气治理", ["boiler_emissions", "boiler_emission_control"]),
    ("environmental_management_institution", "环境管理机构", ["environmental_management_institution", "environmental_management_organization", "environmental_management_structure", "environment_management_agency"]),
    ("seismic_parameter", "地震参数", ["seismic_parameter", "seismic_parameters", "geo_seismic", "seismicity", "recent_earthquake_event"]),
    ("blasting_parameters", "爆破参数", ["blasting_operation_parameters", "blasting_parameters"]),
    ("eco_impact_factor", "生态影响评价因子", ["eco_impact_factor", "ecological_impact_factors", "ecological_impact_factor"]),
    ("soil_monitoring_point", "土壤监测点", ["soil_monitoring_point", "soil_mon_point", "soil_tracking_monitoring_point", "soil_monitoring_plan"]),
    ("groundwater_monitoring_point", "地下水监测点", ["monitoring_point", "groundwater_monitoring_point", "groundwater_monitoring_well", "groundwater_monitoring_borehole", "groundwater_well", "water_quality_station", "groundwater_level_monitoring_point", "tracking_monitoring_well", "piezometric_observation", "groundwater_level_observation", "water_level_time_series"]),
    ("estimation_model_params", "大气估算模型参数", ["estimation_model_params", "air_emission_model_params", "calculation_model_parameters", "air_dispersion_parameter", "air_assessment_params", "air_dispersion_prediction_params"]),
    ("first_mining_area_scheme", "首采区方案", ["first_mining_area_scheme", "initial_bench_scheme", "initial_cut_scheme", "new::首采区方案", "new::初始拉沟", "new::拉沟技术指标"]),
    ("engineering_site_scheme", "工业场地选址方案", ["engineering_site_scheme", "industrial_site_selection_scheme", "site_selection_analysis"]),
    ("industrial_site", "工业场地", ["industrial_site", "industrial_plant", "industrial_site_surface_coal"]),
    ("pollutant_emission_inventory", "污染物排放清单", ["pollutant_emission_item", "pollutant_emission_inventory", "pollutant_emission", "new::污染源排放参数"]),
    ("solid_waste_monitoring", "矸石浸出液监测", ["solid_waste_monitoring", "gangu_lix_solution_monitoring", "gangue_leachate_monitoring", "gangue_leachate_test", "leaching_toxicity_monitoring", "leaching_toxicity_result", "leaching_toxicity_test", "solid_waste_testing"]),
    ("plant_species", "植物物种", ["plant_species", "new::植物物种", "wild_plant_species", "plant_resource", "plant_resource_species", "dominant_plant_species"]),
    ("animal_species", "动物物种", ["animal_species", "new::动物物种名录", "wildlife_species"]),
    ("environment_sensitivity", "环境敏感程度", ["environment_sensitivity", "environmental_sensitivity", "new::环境敏感程度"]),
    ("environmental_control_unit", "环境管控单元", ["environmental_control_unit", "new::环境管控单元"]),
    ("stratigraphy", "地层", ["stratigraphic_layer", "stratigraphy", "new::地层信息"]),
    ("protective_coal_pillar", "保护煤柱", ["protective_coal_pillar", "protection_coal_pillar", "coal_pillar", "river_protection_zone"]),
    ("mine_area", "矿区井田基本信息", ["mine_area", "mining_district", "mine_field", "new::矿区井田规划"]),
    ("mining_area_section", "采区", ["mining_area_section", "mining_operation_area"]),
    ("surface_water_monitoring_station", "地表水监测断面", ["surface_water_monitoring_station", "new::地表水监测断面", "river_water_quality_monitoring"]),
    ("noise_prediction_point", "噪声预测点", ["noise_prediction_point", "noise_prediction", "factory_boundary_noise_prediction"]),
    ("water_quality_monitoring_data", "水质监测数据", ["water_quality_monitoring_data", "water_quality_result", "water_quality_indicators", "water_quality_parameter", "groundwater_quality_indicator", "analysis_item", "monitoring_data_hourly", "monitoring_data_daily"]),
    ("soil_pollution_source", "土壤污染源", ["soil_pollution_source", "pollution_source"]),
    ("ecosystem_type", "生态系统类型", ["ecosystem_type", "ecosystem_structure", "new::生态系统类型"]),
    ("dust_control_equipment", "除尘设施", ["dust_control_equipment", "new::除尘器设备", "pulse_bag_dust_collector", "wet_filter_dust_remover", "ultrasonic_misting_dust_suppression_device"]),
    ("mine_shaft", "矿井井筒", ["mine_shaft", "new::矿井井筒", "mine_shaft_layout", "shaft_tunnel_engineering"]),
    ("road_infrastructure", "厂外运输道路", ["road_infrastructure", "road", "new::场外道路"]),
    ("transmission_line", "输电线路", ["transmission_line", "power_line_protection"]),
    ("reservoir", "水库/淤地坝", ["reservoir", "check_dam"]),
    ("environmental_cost_benefit_analysis", "环境经济损益", ["environmental_cost_benefit_analysis", "environmental_economic_benefit_analysis", "env_economic_summary", "new::环境经济指标", "env_economic_loss_item", "new::环境损失费用", "new::年环境损失费用", "new::吨煤环境代价", "environmental_cost_indicator"]),
    ("environmental_protection_investment", "环保投资", ["environmental_protection_investment", "env_protection_investment_item", "new::环保投资明细", "new::环境保护费用", "total_investment_and_ratio"]),
    ("risk_source", "环境风险源", ["risk_source", "environmental_risk_source", "risk_source_facility"]),
    ("drainage_outlet", "排污口", ["drainage_outlet", "new::排污口", "discharge_outlet_signage"]),
    ("sludge", "污泥", ["sludge", "sludge_waste", "sewage_treatment_sludge", "sludge_disposal"]),
    ("protected_heritage", "文物古迹", ["protected_heritage", "heritage_site", "new::文物保护单位", "new::古墓葬"]),
    ("assessment_scope", "评价范围及等级", ["assessment_scope", "evaluation_parameters", "survey_scope"]),
    ("surface_water_self_review", "地表水环境影响评价自查表", ["new::地表水环境影响评价自查表", "new::地表水评价自查表"]),
    ("construction_waste_balance", "建设期土石方平衡", ["construction_waste_balance", "earthwork_balance"]),
    ("aquifer_pumping_test", "含水层抽水试验", ["aquifer_pumping_test", "drilling_test", "pumping_test_well", "drill_hole"]),
    ("aquifer_zone", "含水层（段）", ["aquifer_zone", "aquifer_parameter", "water_bearing_unit"]),
    ("hydrochemical_analysis", "地下水水化学分析", ["hydrochemical_analysis", "groundwater_chemistry_type", "water_quality_analysis"]),
    ("air_impact_prediction", "大气环境影响预测结果", ["air_impact_prediction", "air_pollution_impact_prediction", "air_dispersion_prediction_result", "new::环境空气预测结果"]),
    ("soil_heavy_metals_monitoring", "土壤污染监测结果", ["soil_heavy_metals_monitoring", "soil_pollutant_concentration", "soil_quality_status"]),
    ("gravel_layer_survey", "砾幕层样地调查", ["gravel_layer_survey", "habitat_quadrat_survey", "new::砾幕层样方调查"]),
    ("workface_param", "综采工作面参数", ["workface_param", "new::回采工作面", "mine_working_face"]),
    ("openpit_working_area", "采掘场", ["openpit_working_area", "mining_area_overburden"]),
    ("mining_equipment", "采矿装备", ["mining_equipment", "hydraulic_support", "hydraulic_power_station", "end_hydraulic_support", "scraper_conveyor", "coal_mining_machine", "transfer_machine", "belt_conveyor"]),
    ("blasting_vibration_safety", "爆破振动安全", ["blasting_vibration_safety", "blast_vibration_parameters"]),
    ("blasting_shockwave_safety", "爆破冲击波安全", ["blasting_shockwave_safety", "blast_shockwave_parameters"]),
    ("blasting_gas_emission", "爆破有害气体排放", ["blasting_gas_emission", "explosive_gas_generation"]),
    ("construction_boundary_noise", "施工边界噪声", ["construction_boundary_noise", "construction_period_noise_impact"]),
    ("desulfurization_process", "脱硫脱硝除尘工艺", ["desulfurization_denitrification_dust_removal_process", "de_sulfur_denitrification_dust_removing_efficiency"]),
    ("groundwater_parameter_prediction", "地下水预测参数", ["groundwater_parameter_prediction", "new::地下水评价参数"]),
    ("burned_rock_zone", "火烧区（烧变岩）", ["burned_rock_zone", "fire_area"]),
    ("village_relocation", "村庄搬迁", ["new::搬迁村庄", "village_relocation_plan"]),
    ("radioactive_element", "放射性核素", ["radioactive_element", "new::核素含量"]),
    ("radioactivity_detection", "放射性检测", ["radioactivity_detection", "radiation_monitoring", "radiation_safety_param"]),
]

# 应并入现有实体的候选（沉陷族归沉陷实体、通用污染源归既有实体等明显归属）。
EXISTING_ROUTES = {
    "subsidence_prediction_parameters": "land_subsidence",
    "subsidence_prediction_parameter": "land_subsidence",
    "subsidence_prediction_params": "land_subsidence",
    "land_subsidence_prediction_params": "land_subsidence",
    "subsidence_parameter": "land_subsidence",
    "subsidence_prediction_scheme": "land_subsidence",
    "subsidence_scenario": "land_subsidence",
    "subsidence_prediction_phase": "land_subsidence",
    "subsidence_deformation": "land_subsidence",
    "surface_deformation_prediction": "land_subsidence",
    "surface_deformation_prediction_result": "land_subsidence",
    "surface_deformation_result": "land_subsidence",
    "subsidence_result": "land_subsidence",
    "coal_layer_deformation": "land_subsidence",
    "coal_seam_deformation": "land_subsidence",
    "coal_seam_subsidence": "land_subsidence",
    "surface_crack": "land_subsidence",
    "rock_movement_observation": "land_subsidence",
    "subsidence_observation": "land_subsidence",
    "subsidence_observation_station": "land_subsidence",
    "ground_surface_mining_subsidence_monitoring_station": "land_subsidence",
    "building_damage_grade": "land_subsidence",
    "building_damage_assessment": "land_subsidence",
    "building_damage_standard": "land_subsidence",
    "cultural_relic_subsidence_impact": "land_subsidence",
    "power_line_subsidence_impact": "land_subsidence",
    "road_subsidence_impact": "land_subsidence",
    "water_facility_subsidence_impact": "land_subsidence",
    "new::矸石": "solid_waste_gangue",
    "air_pollutants": "air_pollutants",
    "project_emission_source": "air_pollutants",
    "surface_boundary_coord": "spatial_boundary",
}

TYPE_MAP = {"String": "String", "Number": "Float", "Integer": "Integer", "Float": "Float", "Boolean": "Boolean", "Enum": "Enum", "Object": "Object", "List": "List"}
KEY_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def norm_name(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


async def build_plan() -> None:
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE

    entities = await DomainEntityRepository().list_all(domain_code=GENERAL_DOMAIN_CODE)
    active_keys = {e["entity_key"] for e in entities}
    # 现有属性名索引：归一化名 → [(ek, prop)]
    existing_props: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    entity_by_key = {e["entity_key"]: e for e in entities}
    for e in entities:
        for p in e.get("properties") or []:
            if isinstance(p, dict) and p.get("name_cn"):
                existing_props[norm_name(p["name_cn"])].append((e["entity_key"], p))

    data = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    recs = data["candidates"]

    new_objs: dict[str, dict] = {}
    for r in recs:
        if r["status"] != "new-object":
            continue
        o = new_objs.setdefault(r["obj_key"], {"key": r["obj_key"], "name": r["obj_name"], "props": [], "n": 0})
        o["props"].append(r)
        o["n"] += r["n_slices"]

    # 1) 人工簇合并
    cluster_of: dict[str, tuple[str, str]] = {}
    for ck, cname, members in MERGE_CLUSTERS:
        for m in members:
            cluster_of[m] = (ck, cname)
    routed: dict[str, list[dict]] = defaultdict(list)
    canonical: dict[str, dict] = {}
    for k, o in new_objs.items():
        if k in EXISTING_ROUTES:
            routed[EXISTING_ROUTES[k]].extend(o["props"])
            continue
        if k in cluster_of:
            ck, cname = cluster_of[k]
            c = canonical.setdefault(ck, {"key": ck, "name": cname, "props": [], "n": 0})
            c["props"].extend(o["props"])
            c["n"] += o["n"]
            continue
        canonical[k] = {**o}

    # 2) name_cn 归一后完全相同的自动合并（并入跨切片次数最高者）
    by_norm: dict[str, list[str]] = defaultdict(list)
    for k, o in canonical.items():
        by_norm[norm_name(o["name"])].append(k)
    merged_away = set()
    for _, keys in by_norm.items():
        if len(keys) < 2:
            continue
        keys.sort(key=lambda k: -canonical[k]["n"])
        keep = keys[0]
        for k in keys[1:]:
            canonical[keep]["props"].extend(canonical[k]["props"])
            canonical[keep]["n"] += canonical[k]["n"]
            merged_away.add(k)
    for k in merged_away:
        canonical.pop(k)

    # 3) key 冲突路由（候选 key 撞活跃实体 → 并入该实体）
    for k in list(canonical):
        if k in active_keys:
            routed[k].extend(canonical.pop(k)["props"])

    # 4) 新实体属性去重（组内按归一名）+ key 占位
    for c in canonical.values():
        seen: dict[str, dict] = {}
        for p in c["props"]:
            nm = norm_name(p["prop"])
            if nm not in seen:
                seen[nm] = {
                    "name_cn": p["prop"],
                    "value_type": TYPE_MAP.get(p.get("type") or "String", "String"),
                    "unit": (p.get("units") or [""])[0] if p.get("units") else "",
                    "samples": p.get("samples") or [],
                    "n_slices": p["n_slices"],
                    "key": "",
                }
            else:
                seen[nm]["n_slices"] += p["n_slices"]
                for s in p.get("samples") or []:
                    if len(seen[nm]["samples"]) < 6:
                        seen[nm]["samples"].append(s)
        c["props"] = sorted(seen.values(), key=lambda p: -p["n_slices"])

    # 5) 现有实体属性新增过滤：目标已有同名跳过；与其他实体现有属性同名跳过（歧义面控制）
    def pass_filter(ek: str, own: set[str], p: dict) -> dict | None:
        nm = norm_name(p["prop"])
        if nm in own:
            return None
        if [x for x in existing_props.get(nm, []) if x[0] != ek]:
            return None
        return {
            "name_cn": p["prop"],
            "value_type": TYPE_MAP.get(p.get("type") or "String", "String"),
            "unit": (p.get("units") or [""])[0] if p.get("units") else "",
            "samples": p.get("samples") or [],
            "n_slices": p["n_slices"],
            "key": "",
        }

    adds: dict[str, list[dict]] = {}
    skipped_dup = skipped_ambig = 0
    for ek, props in routed.items():
        tgt = entity_by_key.get(ek)
        if tgt is None:
            continue
        own = {norm_name(p.get("name_cn")) for p in tgt.get("properties") or []}
        out = []
        for p in props:
            kept = pass_filter(ek, own, p)
            if kept is None:
                if norm_name(p["prop"]) not in own:
                    skipped_ambig += 1
                else:
                    skipped_dup += 1
                continue
            own.add(norm_name(p["prop"]))
            out.append(kept)
        if out:
            adds[ek] = out

    # 5b) 主载荷：直接挂在现有实体上的 new-prop 候选（同口径过滤）
    for r in recs:
        if r["status"] != "new-prop":
            continue
        ek = r["obj_key"]
        if ek not in entity_by_key:
            continue
        adds.setdefault(ek, [])
        tgt = entity_by_key[ek]
        own = {norm_name(p.get("name_cn")) for p in tgt.get("properties") or []} | {
            norm_name(x["name_cn"]) for x in adds[ek]
        }
        kept = pass_filter(ek, own, r)
        if kept is None:
            if norm_name(r["prop"]) in own:
                skipped_dup += 1
            else:
                skipped_ambig += 1
            continue
        adds[ek].append(kept)

    plan = {
        "new_entities": [
            {"key": c["key"], "name_cn": c["name"], "n_slices": c["n"], "props": c["props"]}
            for c in canonical.values()
        ],
        "prop_adds": adds,
        "stats": {
            "new_entity_count": len(canonical),
            "existing_entity_touched": len(adds),
            "props_new_entities": sum(len(c["props"]) for c in canonical.values()),
            "props_added_existing": sum(len(v) for v in adds.values()),
            "skipped_dup_in_entity": skipped_dup,
            "skipped_cross_entity_ambig": skipped_ambig,
            "routed_props_to_existing": sum(len(v) for v in routed.values()),
        },
    }
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print("plan written:", PLAN_PATH)
    for k, v in plan["stats"].items():
        print(f"  {k}: {v}")
    need_key_entities = [c["key"] for c in plan["new_entities"] if not KEY_OK.match(c["key"])]
    print(f"  新实体缺合法 key: {len(need_key_entities)}")


async def translate() -> None:
    """LLM 批量生成 snake_case 键：新实体名 + 属性名（全局唯一名集合）。断点续跑。"""
    from pisuan.models.chat import load_chat_model
    from pisuan.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    todo_entities = {norm_name(c["name_cn"]): c["name_cn"] for c in plan["new_entities"] if not KEY_OK.match(c["key"])}
    todo_props: dict[str, str] = {}
    for c in plan["new_entities"]:
        for p in c["props"]:
            todo_props.setdefault(norm_name(p["name_cn"]), p["name_cn"])
    for props in plan["prop_adds"].values():
        for p in props:
            todo_props.setdefault(norm_name(p["name_cn"]), p["name_cn"])

    done: dict[str, str] = {}
    if KEYS_PATH.exists():
        done = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
    names = sorted({*todo_entities.values(), *todo_props.values()})
    pending = [n for n in names if norm_name(n) not in done]
    print(f"待翻译 {len(pending)} / {len(names)} 个名称 → snake_case")
    if not pending:
        return
    model = load_chat_model(TRANSLATE_MODEL)
    BATCH = 80
    for i in range(0, len(pending), BATCH):
        batch = pending[i : i + BATCH]
        numbered = "\n".join(f"{j+1}. {n}" for j, n in enumerate(batch))
        prompt = (
            "把下列中文领域名词分别翻译成 snake_case 英文标识符（用于实体 key / 属性 key）。\n"
            "规则：全小写、下划线分隔、不含点号/空格/中文、不超过 40 字符、语义准确、简短；\n"
            "环境专业术语用通用英文（如 沉陷=subsidence、矸石=gangue、矿井水=mine_water）。\n"
            "只输出 JSON：{\"1\":\"key1\",\"2\":\"key2\",...}，编号对应。\n\n" + numbered
        )
        for attempt in range(3):
            try:
                resp = await model.ainvoke([("human", prompt)])
                txt = resp.content
                if isinstance(txt, list):
                    txt = "\n".join(str(b.get("text") or "") for b in txt if isinstance(b, dict) and b.get("type") == "text")
                m = re.search(r"\{.*\}", str(txt), re.S)
                mapping = json.loads(m.group(0))
                ok = 0
                for j, n in enumerate(batch):
                    v = str(mapping.get(str(j + 1)) or "").strip()
                    if KEY_OK.match(v):
                        done[norm_name(n)] = v
                        ok += 1
                print(f"  batch {i//BATCH+1}: {ok}/{len(batch)}")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  batch {i//BATCH+1} attempt {attempt+1} failed: {str(e)[:100]}")
                await asyncio.sleep(3 * (attempt + 1))
        KEYS_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"翻译完成，共 {len(done)} 条 → {KEYS_PATH}")


async def classify() -> None:
    """LLM 给新实体分配六分类。断点续跑。"""
    from pisuan.models.chat import load_chat_model
    from pisuan.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    cats = "project_basic(基础工程实体) / natural_env(自然环境实体) / env_quality(环境质量与污染源实体) / sensitive_target(敏感目标与空间实体) / measures_regulation(措施与法规实体) / impact_assessment(环境影响评价实体)"
    done: dict[str, str] = {}
    if CLS_PATH.exists():
        done = json.loads(CLS_PATH.read_text(encoding="utf-8"))
    pending = [c for c in plan["new_entities"] if c["key"] not in done]
    print(f"待分类 {len(pending)} / {len(plan['new_entities'])} 个新实体")
    if not pending:
        return
    model = load_chat_model(TRANSLATE_MODEL)
    BATCH = 60
    for i in range(0, len(pending), BATCH):
        batch = pending[i : i + BATCH]
        numbered = "\n".join(f"{j+1}. {c['name_cn']}（{c['key']}）" for j, c in enumerate(batch))
        prompt = (
            f"把下列环评领域实体分到六个分类之一：{cats}。\n"
            "判定要点：工程/矿建/装备/资源地质→project_basic；气象水文地质生态物种→natural_env；"
            "质量监测/污染源/排放→env_quality；敏感点保护目标红线管控单元→sensitive_target；"
            "措施设施投资机构预案法规→measures_regulation；评价等级预测自查损益→impact_assessment。\n"
            "只输出 JSON：{\"1\":\"code\",...}。\n\n" + numbered
        )
        valid = {"project_basic", "natural_env", "env_quality", "sensitive_target", "measures_regulation", "impact_assessment"}
        for attempt in range(3):
            try:
                resp = await model.ainvoke([("human", prompt)])
                txt = resp.content
                if isinstance(txt, list):
                    txt = "\n".join(str(b.get("text") or "") for b in txt if isinstance(b, dict) and b.get("type") == "text")
                mapping = json.loads(re.search(r"\{.*\}", str(txt), re.S).group(0))
                ok = 0
                for j, c in enumerate(batch):
                    v = str(mapping.get(str(j + 1)) or "").strip()
                    if v in valid:
                        done[c["key"]] = v
                        ok += 1
                print(f"  batch {i//BATCH+1}: {ok}/{len(batch)}")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  batch {i//BATCH+1} attempt {attempt+1} failed: {str(e)[:100]}")
                await asyncio.sleep(3 * (attempt + 1))
        CLS_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"分类完成，共 {len(done)} 条 → {CLS_PATH}")


async def apply_plan(dry: bool) -> None:
    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from pisuan.services.domain_entity_service import DomainEntityService

    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    keys = json.loads(KEYS_PATH.read_text(encoding="utf-8")) if KEYS_PATH.exists() else {}
    classes = json.loads(CLS_PATH.read_text(encoding="utf-8")) if CLS_PATH.exists() else {}
    svc = DomainEntityService()

    def prop_key(p: dict, entity_name: str) -> str:
        k = keys.get(norm_name(p["name_cn"])) or ""
        if not KEY_OK.match(k):
            k = "f_" + hashlib.sha1((entity_name + p["name_cn"]).encode("utf-8")).hexdigest()[:10]
        return k[:64]

    def build_props(props: list[dict], entity_name: str) -> list[dict]:
        out, seen = [], set()
        for p in props:
            k = prop_key(p, entity_name)
            if k.casefold() in seen:
                k = k + "_2"
            while k.casefold() in seen:
                k = k + "_2"
            seen.add(k.casefold())
            hint = f"单位 {p['unit']}" if p.get("unit") else ""
            out.append(
                {
                    "key": k,
                    "name_cn": p["name_cn"],
                    "value_type": p["value_type"],
                    "unit": p.get("unit") or "",
                    "required": False,
                    "extraction_hint": hint,
                }
            )
        return out

    repo = DomainEntityRepository()
    n_created = n_failed = n_updated = 0
    created_keys: set[str] = set()
    for c in plan["new_entities"]:
        ek = c["key"] if KEY_OK.match(c["key"]) else (keys.get(norm_name(c["name_cn"])) or "")
        if not KEY_OK.match(ek):
            ek = "ent_" + hashlib.sha1(c["name_cn"].encode("utf-8")).hexdigest()[:10]
        # 幂等续跑：key 或 name_cn 已在库即跳过（上次中断可能已建）
        existing = await repo.get_by_id_or_key(ek) if not dry else None
        if existing is not None:
            created_keys.add(ek)
            continue
        cat = classes.get(c["key"], "project_basic")
        data = {
            "entity_key": ek,
            "name_cn": c["name_cn"],
            "category": cat,
            "value_type": "Object",
            "description": f"Route B 语料归纳（2026-11-16，project_eia 普查，跨切片 {c['n_slices']} 次）",
            "properties": build_props(c["props"], c["name_cn"]),
        }
        if dry:
            print(f"[dry] create {ek}（{c['name_cn']}）props={len(data['properties'])} cat={cat}")
            n_created += 1
            continue
        try:
            await svc.create_entity(data)
            n_created += 1
        except Exception as e:  # noqa: BLE001 — key 占用等单条失败不阻断批次
            msg = str(e)
            if "已存在" in msg or "占用" in msg:
                ek2 = ek + "_b"
                data["entity_key"] = ek2
                try:
                    await svc.create_entity(data)
                    n_created += 1
                    print(f"  retry ok: {ek} → {ek2}")
                    continue
                except Exception as e2:  # noqa: BLE001
                    msg = str(e2)
            n_failed += 1
            print(f"  FAIL create {ek}（{c['name_cn']}）: {msg[:120]}")

    for ek, props in plan["prop_adds"].items():
        if dry:
            print(f"[dry] add {len(build_props(props, ek))} props → {ek}")
            n_updated += 1
            continue
        try:
            ent = await repo.get_by_id_or_key(ek)
            if ent is None:
                print(f"  FAIL add {ek}: 实体不存在")
                n_failed += 1
                continue
            current = ent.to_dict().get("properties") or []
            cur_names = {norm_name(p.get("name_cn")) for p in current if isinstance(p, dict)}
            cur_keys = {str(p.get("key") or "").casefold() for p in current if isinstance(p, dict)}
            # 幂等 + key 撞既有属性加后缀（normalize_properties 拒绝实体内重复 key）
            fresh = []
            for p in build_props(props, ek):
                if norm_name(p["name_cn"]) in cur_names:
                    continue
                while p["key"].casefold() in cur_keys:
                    p["key"] = p["key"] + "_2"
                cur_keys.add(p["key"].casefold())
                cur_names.add(norm_name(p["name_cn"]))
                fresh.append(p)
            if not fresh:
                continue
            await svc.update_entity(ek, {"properties": current + fresh}, force=True)
            n_updated += 1
            print(f"  add {len(fresh)} props → {ek}")
        except Exception as e:  # noqa: BLE001
            n_failed += 1
            print(f"  FAIL add {ek}: {str(e)[:120]}")

    mode = "DRY-RUN" if dry else "APPLY"
    print(f"[{mode}] 新建实体 {n_created} / 更新实体 {n_updated} / 失败 {n_failed}")


async def conform() -> None:
    """落库后规范收敛：键小写化、无选项 Enum 降级 String、超长 hint 截断（幂等）。"""
    import re

    from pisuan.repositories.domain_entity_repository import DomainEntityRepository
    from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
    from pisuan.services.domain_entity_service import DomainEntityService

    pat = re.compile(r"^[a-z][a-z0-9_]*$")
    svc = DomainEntityService()
    repo = DomainEntityRepository()
    entities = await repo.list_all(domain_code=GENERAL_DOMAIN_CODE)
    n_fixed = 0
    for e in entities:
        props = e.get("properties") or []
        if not props:
            continue
        changed = False
        seen: set[str] = set()
        for p in props:
            if not isinstance(p, dict):
                continue
            k = str(p.get("key") or "")
            if not pat.match(k):
                nk = k.lower()
                if not pat.match(nk):
                    nk = "n_" + nk
                while nk in seen:
                    nk = nk + "_2"
                p["key"] = nk
                changed = True
            seen.add(p["key"].casefold())
            if p.get("value_type") == "Enum" and not (p.get("enum_options") or []):
                p["value_type"] = "String"
                changed = True
            hint = str(p.get("extraction_hint") or "")
            if len(hint) > 80:
                p["extraction_hint"] = hint[:80]
                changed = True
        if changed:
            await svc.update_entity(e["entity_key"], {"properties": props}, force=True)
            n_fixed += 1
    print(f"[conform] 规范化实体 {n_fixed} 个")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="生成落库计划")
    parser.add_argument("--translate", action="store_true", help="LLM 生成 snake_case 键")
    parser.add_argument("--classify", action="store_true", help="LLM 分配六分类")
    parser.add_argument("--apply", action="store_true", help="落库")
    parser.add_argument("--dry-run", action="store_true", help="apply 只打印不写库")
    parser.add_argument("--conform", action="store_true", help="落库后规范收敛")
    args = parser.parse_args()
    if args.plan:
        asyncio.run(build_plan())
    elif args.translate:
        asyncio.run(translate())
    elif args.classify:
        asyncio.run(classify())
    elif args.apply:
        asyncio.run(apply_plan(args.dry_run))
    elif args.conform:
        asyncio.run(conform())
    else:
        parser.print_help()
