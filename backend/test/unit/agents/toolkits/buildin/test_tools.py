"""TDD tests for v2 calculation tools and save_chapter state extension."""

import pytest

# ========== calculate_a_value ==========

def test_calculate_a_value_computes_basic_case():
    """A=3.5, Ci=0.07, Si=100 → capacity = 3.5*0.07*100/10000 = 0.00245"""
    # Import the underlying function (before @tool wraps it)
    from yuxi.agents.toolkits.buildin.tools import calculate_a_value
    import asyncio

    result = asyncio.run(calculate_a_value.ainvoke({"A": 3.5, "Ci": 0.07, "Si": 100.0}))
    assert result["capacity"] == 0.0025  # round(0.00245, 4) = 0.0025
    assert result["unit"] == "10⁴ t/a"
    assert "C = A × Ci × Si" in result["formula"]


def test_calculate_a_value_handles_zero_area():
    """Si=0 时应返回 capacity=0（不应崩溃）"""
    from yuxi.agents.toolkits.buildin.tools import calculate_a_value
    import asyncio

    result = asyncio.run(calculate_a_value.ainvoke({"A": 3.5, "Ci": 0.07, "Si": 0.0}))
    assert result["capacity"] == 0.0


def test_calculate_a_value_handles_large_values():
    """大面积矿区应返回合理的大容量值"""
    from yuxi.agents.toolkits.buildin.tools import calculate_a_value
    import asyncio

    result = asyncio.run(calculate_a_value.ainvoke({"A": 4.0, "Ci": 0.15, "Si": 500.0}))
    assert result["capacity"] > 0
    assert result["unit"] == "10⁴ t/a"
    assert len(result["steps"]) == 2


# ========== calculate_water_capacity ==========

def test_calculate_water_capacity_basic():
    """C0=10, K=0.15, x=1000, u=0.5 → 浓度应衰减"""
    from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity
    import asyncio

    result = asyncio.run(
        calculate_water_capacity.ainvoke({"C0": 10.0, "K": 0.15, "x": 1000.0, "u": 0.5})
    )
    assert 0 < result["Cx"] < 10.0  # 浓度应小于初始值
    assert result["unit"] == "mg/L"
    assert len(result["steps"]) == 3


def test_calculate_water_capacity_fast_flow_no_decay():
    """快速流动（u极大）时几乎不衰减"""
    from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity
    import asyncio

    result = asyncio.run(
        calculate_water_capacity.ainvoke({"C0": 10.0, "K": 0.01, "x": 10.0, "u": 100.0})
    )
    # 流速极快 → 几乎无降解 → Cx 接近 C0
    assert abs(result["Cx"] - 10.0) < 0.1


def test_calculate_water_capacity_stagnant_full_decay():
    """静止水体（u极小）长时间后几乎完全降解"""
    from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity
    import asyncio

    result = asyncio.run(
        calculate_water_capacity.ainvoke({"C0": 10.0, "K": 1.0, "x": 50000.0, "u": 0.001})
    )
    assert result["Cx"] < 1.0  # 几乎完全降解


# ========== lookup_subsidence_params ==========

@pytest.mark.asyncio
async def test_lookup_subsidence_params_no_kb_available():
    """无 Milvus KB 时应返回 hint 而不是崩溃"""
    from yuxi.agents.toolkits.buildin.tools import lookup_subsidence_params

    result = await lookup_subsidence_params.ainvoke(
        {"depth": "300-500m", "coal_seam": "2-5m", "angle": "0-15°"}
    )
    assert "matched" in result
    assert result.get("matched") is None or isinstance(result["matched"], list)


# ========== save_chapter status validation ==========


@pytest.mark.asyncio
async def test_save_chapter_rejects_invalid_status():
    """非法 status 应返回 error 消息"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    result = await save_chapter.ainvoke({
        "report_id": "nonexistent",
        "canonical_chapter_key": "测试章",
        "title": "测试",
        "content_md": "正文",
        "summary": "摘要",
        "status": "invalid_status",
    })
    assert "error" in result
    assert "无效 status" in result["error"]


@pytest.mark.asyncio
async def test_save_chapter_rejects_empty_content_on_done_and_review():
    """status=done/review 且 content_md 为空 → error"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    for status in ("done", "review"):
        result = await save_chapter.ainvoke({
            "report_id": "nonexistent",
            "canonical_chapter_key": f"test_{status}",
            "title": "测试",
            "content_md": "",
            "summary": "",
            "status": status,
        })
        assert "error" in result, f"status={status} should reject empty content"
        assert status in result["error"]


@pytest.mark.asyncio
async def test_save_chapter_accepts_all_valid_statuses():
    """所有合法 status 都不应因 status 字段本身报错"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    valid = ["writing", "skipped", "pending_data"]
    for status in valid:
        result = await save_chapter.ainvoke({
            "report_id": "nonexistent-rpt",
            "canonical_chapter_key": f"test_{status}_{id(status)}",
            "title": "Test",
            "content_md": "正文内容",
            "summary": "摘要",
            "status": status,
        })
        if "error" in result:
            assert "无效 status" not in result["error"], (
                f"status={status} should be valid, got: {result['error']}"
            )

