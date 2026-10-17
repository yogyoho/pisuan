"""eia_data_service 单元测试：统计结构完整性 + 词表候选清洗/三分类规则。

结构断言依赖仓库内置的 coal-eia-writer 技能语料（docker 内 /app/package/ 路径），
宿主环境无技能目录时自动跳过。
"""

import pytest

from pisuan.services.eia_data_service import (
    STAGES,
    _classify_caliber,
    _clean_caliber,
    _skill_root_exists,
    get_skill_stats,
    get_unmapped,
)


def test_clean_caliber_stops_tail():
    """尾噪声迭代剥离：STOP_TAIL 尾字剥到稳定，不得破坏正常口径。"""
    assert _clean_caliber("除尘效率可") == "除尘效率"
    assert _clean_caliber("矸石综合利用率") == "矸石综合利用率"
    assert _clean_caliber("废水回用率") == "废水回用率"


def test_classify_caliber_three_way():
    """三分类：A 措施效率 / B 现状监测 / C 非护栏杂项（截断与非目标口径）。"""
    assert _classify_caliber("抑尘效率") == "measure"
    assert _classify_caliber("废水回用率") == "measure"
    assert _classify_caliber("超标率") == "site"
    assert _classify_caliber("林草盖度") == "site"
    assert _classify_caliber("占地面积") == "junk"


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_get_skill_stats_structure():
    """真实语料聚合：顶层结构 + 核心计数与语料普查一致。"""
    stats = get_skill_stats()
    assert set(stats) >= {"skill", "stages", "corpus", "layers", "candidates", "expectations", "quality"}
    assert stats["skill"] == "coal-eia-writer"

    corpus = stats["corpus"]
    assert corpus["reports_total"] == 31
    assert corpus["slices_total"] == corpus["samples_total"] == 477
    assert sum(v["reports"] for v in corpus["per_stage"].values()) == 31
    assert sum(corpus["by_province"].values()) == 31

    # 词表候选：口径与语料普查对齐（单位白名单 + n≥2 报告门槛 + 强清洗，
    # 比普查 99 少的 7 项为平均值/分别等整词垃圾）
    # P2 拉丁前缀窗后：裸「控制效率」（splitting 不计数）三分成三子口径 +3、「产生量」精化
    # 为「TSP产生量」（切片源未达 n≥2 门槛未成键）-1，total 90→92；控制效率入 measure 枚举
    cand = stats["candidates"]
    assert cand["total"] == 92
    assert cand["measure"] + cand["site"] + cand["junk"] == cand["total"]
    assert cand["measure"] == 34
    assert cand["per_stage"]["planning_eia"]["measure"] == 13
    assert cand["range_ready"] == 9

    # 事实槽位：5 阶段齐全，planning unmapped 池触顶 200 cap
    assert set(stats["expectations"]) == set(STAGES)
    assert stats["expectations"]["planning_eia"]["unmapped"] == 200

    # 五层价值模型：预留位存在
    planned = [i for layer in stats["layers"] for i in layer["items"] if i.get("status") == "planned"]
    assert {i["key"] for i in planned} == {"question_bank", "deep_annotations", "eval_cases", "regulation_library"}

    # 体检项：标准待核实 41（standards_index 既有存量）
    quality = {i["key"]: i for i in stats["quality"]}
    assert quality["standards_verify"]["count"] == 41


def test_get_unmapped_invalid_stage():
    """非法 stage 拒绝（ValueError，路由层翻 400）。"""
    with pytest.raises(ValueError):
        get_unmapped(stage="nonexistent")


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_get_unmapped_all_stages():
    """全阶段明细：5 阶段齐全，planning 触顶 200 cap，total 为各阶段之和，条目字段齐全。"""
    out = get_unmapped()
    assert set(out["stages"]) == set(STAGES)
    assert out["total"] == sum(v["total"] for v in out["stages"].values())
    for v in out["stages"].values():
        assert v["total"] == len(v["items"])
    planning = out["stages"]["planning_eia"]
    assert planning["total"] == 200
    assert planning["items"], "planning unmapped 池不应为空"
    for item in planning["items"][:5]:
        assert set(item) >= {"caliber", "sample", "section", "unit", "value"}


@pytest.mark.skipif(not _skill_root_exists(), reason="coal-eia-writer 技能目录不存在（宿主环境）")
def test_get_unmapped_stage_filter():
    """按 stage 过滤：只含该阶段，计数与全量视图一致。"""
    full = get_unmapped()
    single = get_unmapped(stage="tracking_eia")
    assert set(single["stages"]) == {"tracking_eia"}
    assert single["stages"]["tracking_eia"]["total"] == full["stages"]["tracking_eia"]["total"]
    assert single["total"] == single["stages"]["tracking_eia"]["total"]
