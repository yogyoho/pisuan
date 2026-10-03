"""TDD tests for v2 calculation tools and save_chapter state extension."""

import pytest

# ========== calculate_a_value ==========


def test_calculate_a_value_computes_basic_case():
    """A=3.5, Ci=0.07, Si=100 → capacity = 3.5*0.07*100/10000 = 0.00245"""
    # Import the underlying function (before @tool wraps it)
    import asyncio

    from yuxi.agents.toolkits.buildin.tools import calculate_a_value

    result = asyncio.run(calculate_a_value.ainvoke({"A": 3.5, "Ci": 0.07, "Si": 100.0}))
    assert result["capacity"] == 0.0025  # round(0.00245, 4) = 0.0025
    assert result["unit"] == "10⁴ t/a"
    assert "C = A × Ci × Si" in result["formula"]


def test_calculate_a_value_handles_zero_area():
    """Si=0 时应返回 capacity=0（不应崩溃）"""
    import asyncio

    from yuxi.agents.toolkits.buildin.tools import calculate_a_value

    result = asyncio.run(calculate_a_value.ainvoke({"A": 3.5, "Ci": 0.07, "Si": 0.0}))
    assert result["capacity"] == 0.0


def test_calculate_a_value_handles_large_values():
    """大面积矿区应返回合理的大容量值"""
    import asyncio

    from yuxi.agents.toolkits.buildin.tools import calculate_a_value

    result = asyncio.run(calculate_a_value.ainvoke({"A": 4.0, "Ci": 0.15, "Si": 500.0}))
    assert result["capacity"] > 0
    assert result["unit"] == "10⁴ t/a"
    assert len(result["steps"]) == 2


# ========== calculate_water_capacity ==========


def test_calculate_water_capacity_basic():
    """C0=10, K=0.15, x=1000, u=0.5 → 浓度应衰减"""
    import asyncio

    from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity

    result = asyncio.run(calculate_water_capacity.ainvoke({"C0": 10.0, "K": 0.15, "x": 1000.0, "u": 0.5}))
    assert 0 < result["Cx"] < 10.0  # 浓度应小于初始值
    assert result["unit"] == "mg/L"
    assert len(result["steps"]) == 3


def test_calculate_water_capacity_fast_flow_no_decay():
    """快速流动（u极大）时几乎不衰减"""
    import asyncio

    from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity

    result = asyncio.run(calculate_water_capacity.ainvoke({"C0": 10.0, "K": 0.01, "x": 10.0, "u": 100.0}))
    # 流速极快 → 几乎无降解 → Cx 接近 C0
    assert abs(result["Cx"] - 10.0) < 0.1


def test_calculate_water_capacity_stagnant_full_decay():
    """静止水体（u极小）长时间后几乎完全降解"""
    import asyncio

    from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity

    result = asyncio.run(calculate_water_capacity.ainvoke({"C0": 10.0, "K": 1.0, "x": 50000.0, "u": 0.001}))
    assert result["Cx"] < 1.0  # 几乎完全降解


# ========== lookup_subsidence_params ==========


@pytest.mark.asyncio
async def test_lookup_subsidence_params_no_kb_available():
    """无 Milvus KB 时应返回 hint 而不是崩溃"""
    from yuxi.agents.toolkits.buildin.tools import lookup_subsidence_params

    result = await lookup_subsidence_params.ainvoke({"depth": "300-500m", "coal_seam": "2-5m", "angle": "0-15°"})
    assert "matched" in result
    assert result.get("matched") is None or isinstance(result["matched"], list)


# ========== save_chapter status validation ==========


@pytest.mark.asyncio
async def test_save_chapter_rejects_invalid_status():
    """非法 status 应返回 error 消息"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    result = await save_chapter.ainvoke(
        {
            "report_id": "nonexistent",
            "canonical_chapter_key": "测试章",
            "title": "测试",
            "content_md": "正文",
            "summary": "摘要",
            "status": "invalid_status",
            "runtime": None,  # C3: 拒绝路径不触达 runtime
        }
    )
    assert "error" in result
    assert "无效 status" in result["error"]


@pytest.mark.asyncio
async def test_save_chapter_rejects_empty_content_on_done_and_review():
    """status=done/review 且 content_md 为空 → error"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    for status in ("done", "review"):
        result = await save_chapter.ainvoke(
            {
                "report_id": "nonexistent",
                "canonical_chapter_key": f"test_{status}",
                "title": "测试",
                "content_md": "",
                "summary": "",
                "status": status,
                "runtime": None,  # C3: 拒绝路径不触达 runtime
            }
        )
        assert "error" in result, f"status={status} should reject empty content"
        assert status in result["error"]


@pytest.mark.asyncio
async def test_save_chapter_accepts_all_valid_statuses():
    """所有合法 status 都不应因 status 字段本身报错"""
    from yuxi.agents.toolkits.buildin.tools import save_chapter

    valid = ["writing", "skipped", "pending_data"]
    for status in valid:
        result = await save_chapter.ainvoke(
            {
                "report_id": "nonexistent-rpt",
                "canonical_chapter_key": f"test_{status}_{id(status)}",
                "title": "Test",
                "content_md": "正文内容",
                "summary": "摘要",
                "status": status,
                "runtime": None,  # C3: report 不存在即返回，不触达 runtime
            }
        )
        if "error" in result:
            assert "无效 status" not in result["error"], f"status={status} should be valid, got: {result['error']}"


# ========== check_content_contract ==========


def test_check_content_contract_all_covered():
    """所有 key_elements 都在 content_md 中出现 → 返回空 warnings"""
    from yuxi.agents.toolkits.buildin.tools import check_content_contract

    cc = {"key_elements": ["气候类型", "气温", "降水"]}
    md = "本区气候类型为温带季风气候,年平均气温12.5℃,年降水量600mm。"
    warnings = check_content_contract(md, cc)
    assert warnings == []


def test_check_content_contract_missing_elements():
    """部分 key_elements 未出现 → 返回 warning 列出缺失项"""
    from yuxi.agents.toolkits.buildin.tools import check_content_contract

    cc = {"key_elements": ["气候类型", "气温", "降水", "风向风速"]}
    md = "本区气候类型为温带季风气候,年平均气温12.5℃。"
    warnings = check_content_contract(md, cc)
    assert len(warnings) == 1
    assert "降水" in warnings[0]
    assert "风向风速" in warnings[0]


def test_check_content_contract_none_contract():
    """content_contract 为 None → 返回空列表(无校验依据)"""
    from yuxi.agents.toolkits.buildin.tools import check_content_contract

    assert check_content_contract("任意内容", None) == []


def test_check_content_contract_no_key_elements():
    """content_contract 无 key_elements → 返回空列表"""
    from yuxi.agents.toolkits.buildin.tools import check_content_contract

    cc = {"min_word_count": 800}
    assert check_content_contract("内容", cc) == []


def test_check_content_contract_empty_key_elements():
    """key_elements 为空列表 → 返回空列表"""
    from yuxi.agents.toolkits.buildin.tools import check_content_contract

    cc = {"key_elements": []}
    assert check_content_contract("内容", cc) == []


# ========== D1: lookup_subsidence_params 真实 API 重写 ==========


@pytest.mark.asyncio
async def test_lookup_subsidence_params_no_milvus_kb(monkeypatch):
    """无 milvus 库 → 返回 hint,不崩溃"""
    from datetime import datetime

    from yuxi.agents.toolkits.buildin.tools import lookup_subsidence_params
    from yuxi.knowledge.read_models import KnowledgeBaseSummary

    async def fake_get_databases():
        return [
            KnowledgeBaseSummary(
                kb_id="kb_x",
                name="dify库",
                description=None,
                kb_type="dify",
                embedding_model_spec=None,
                llm_model_spec=None,
                query_params={},
                additional_params={},
                share_config={},
                created_by=None,
                created_at=datetime.now(),
            )
        ]

    import yuxi.knowledge.runtime as rt

    monkeypatch.setattr(rt.knowledge_base, "get_databases", fake_get_databases)

    result = await lookup_subsidence_params.ainvoke({"depth": "300-500m", "coal_seam": "2-5m", "angle": "0-15°"})
    assert result["matched"] is None
    assert "milvus" in result["hint"]


@pytest.mark.asyncio
async def test_lookup_subsidence_params_merges_milvus_hits(monkeypatch):
    """多 milvus 库逐库 retrieve 并合并命中,带来源标注"""
    from datetime import datetime

    from yuxi.agents.toolkits.buildin.tools import lookup_subsidence_params
    from yuxi.knowledge.read_models import KnowledgeBaseSummary

    def _summary(kb_id, name):
        return KnowledgeBaseSummary(
            kb_id=kb_id,
            name=name,
            description=None,
            kb_type="milvus",
            embedding_model_spec=None,
            llm_model_spec=None,
            query_params={},
            additional_params={},
            share_config={},
            created_by=None,
            created_at=datetime.now(),
        )

    async def fake_get_databases():
        return [_summary("kb_a", "规范库"), _summary("kb_b", "模板库")]

    async def fake_retrieve(kb_id, query, **options):
        assert options.get("limit") == 3
        if kb_id == "kb_a":
            return {
                "kb_id": kb_id,
                "results": [{"id": "1", "kb_id": kb_id, "file_id": "f1", "content": "下沉系数 0.65", "metadata": {}}],
            }
        return {"kb_id": kb_id, "results": []}

    import yuxi.knowledge.runtime as rt

    monkeypatch.setattr(rt.knowledge_base, "get_databases", fake_get_databases)
    monkeypatch.setattr(rt.knowledge_base, "retrieve", fake_retrieve)

    result = await lookup_subsidence_params.ainvoke({"depth": "300-500m", "coal_seam": "2-5m", "angle": "0-15°"})
    assert isinstance(result["matched"], list) and len(result["matched"]) == 1
    assert "规范库" in result["matched"][0]["source"]
    assert "下沉系数" in result["matched"][0]["content"]


# ========== D5: get_templates 兜底标注 ==========


@pytest.mark.asyncio
async def test_get_templates_marks_db_fallback_on_graph_error(monkeypatch):
    """图谱查询异常 → DB 兜底条目带 _source=db_fallback + _degraded_note"""
    from yuxi.agents.toolkits.buildin import tools as tools_mod

    class _Boom:
        async def get_templates(self, *a, **k):
            raise RuntimeError("neo4j down")

        def close(self):
            pass

    monkeypatch.setattr("yuxi.services.graph_query_service.GraphQueryService", _Boom)

    rows = [{"generalized": "模板文本", "slots": []}]

    class _FakeRepo:
        async def list_learned_templates_by_key(self, *a, **k):
            return rows

    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", _FakeRepo)

    result = await tools_mod.get_templates.ainvoke(
        {"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "章1"}
    )
    assert result[0]["_source"] == "db_fallback"
    assert "_degraded_note" in result[0]
    assert result[0]["generalized"] == "模板文本"


@pytest.mark.asyncio
async def test_get_templates_marks_graph_source(monkeypatch):
    """图谱命中 → 条目 _source=graph,不查 DB"""
    from yuxi.agents.toolkits.buildin import tools as tools_mod

    graph_rows = [{"generalized": "图谱模板", "slots": []}]

    class _FakeGraphSvc:
        async def get_templates(self, *a, **k):
            return [dict(r) for r in graph_rows]

        def close(self):
            pass

    monkeypatch.setattr("yuxi.services.graph_query_service.GraphQueryService", _FakeGraphSvc)

    def _no_repo(*a, **k):
        raise AssertionError("图谱命中时不应回退 DB")

    monkeypatch.setattr(tools_mod, "DomainFactoryRepository", _no_repo)

    result = await tools_mod.get_templates.ainvoke(
        {"domain": "coal", "report_type": "eia_report", "canonical_chapter_key": "章1"}
    )
    assert result[0]["_source"] == "graph"
