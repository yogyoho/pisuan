# spec-W1 分类器收敛/双产物/词表单测；依赖 yuxi 服务模块，宿主缺依赖不可 import——验证走容器道：MSYS_NO_PATHCONV=1 docker run --rm -v "C:\workspace\pisuan\backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import DomainFactoryService


def make_svc() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


class TestClassifyConvergence:
    def test_heading_route(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "施工期环境影响", "is_title": True}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "heading"

    def test_table_route_keeps_subtype(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "| 污染物 | 浓度 |\n|---|---|\n| SS | 50 |", "is_table": True}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "table"
        assert out[0]["classify_tags"]  # 子类型标签仍在

    def test_figure_formula_legal_routes(self):
        svc = make_svc()
        paras = [
            {"id": "f1", "content": "![图4-1](media/fig41.png)"},
            {"id": "f2", "content": "L = 3.5 × K × Q / (C - C0) = 100"},
            {"id": "f3", "content": "依据《中华人民共和国水污染防治法》相关规定"},
        ]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "figure"
        assert out[1]["classify_type"] == "formula"
        assert out[2]["classify_type"] == "legal_reference"

    def test_prose_fallback_param_tags(self):
        svc = make_svc()
        # 注：_UNIT_RE 单位分支为 m3/[dha]（ASCII），不含上标 m³/h，故 fixture 用 m3/h 真实触发 measurable
        paras = [{"id": "p1", "content": "矿井正常涌水量为 300 m3/h，采用集中排水方式。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert "measurable" in out[0]["classify_tags"]

    def test_prose_fallback_descriptive_tag(self):
        svc = make_svc()
        # 已验证（容器内实测真实常量）：has_unit=False、不命中 _SLOT_PATTERNS
        paras = [{"id": "p1", "content": "矿区范围内共有废弃井筒 12 处，均已完成封闭。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        # spec-W1 放宽语义：descriptive = 有数值且无单位无槽名（旧 verb 路由信号随双轨废弃）
        assert out[0]["classify_tags"] == ["descriptive"]

    def test_prose_fallback_plain_no_tags(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "该区域历史上曾发生多次洪水事件，对矿山生产构成威胁。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert out[0]["classify_tags"] == []

    def test_narrative_subtype_machinery_extinct(self):
        svc = make_svc()
        assert not hasattr(svc, "_match_narrative_subtype")
        # 行为墓碑：旧叙述子类型（"综上所述"→conclusion 等）不再作为类型/标签产出
        paras = [{"id": "p1", "content": "综上所述，矿区范围内共有 3 处废弃井筒需治理。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert not ({"conclusion", "methodology", "summary", "background"} & set(out[0]["classify_tags"]))

    def test_preclassified_skip(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "任意", "classify_type": "table", "classify_tags": ["x"]}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "table"
        # 现行为：跳过分支将 classify_tags 重置为空列表（不保留入参 tags）
        assert out[0]["classify_tags"] == []

    def test_prose_types_triple(self):
        assert DomainFactoryService._PROSE_TYPES == ("prose", "parameter", "narrative")
        assert DomainFactoryService.VALID_SLOT_TYPES == ("parameter", "enum", "descriptive", "reference")


class TestDualProductAndVocab:
    def test_prompt_v2_contains_vocab_and_summary_fields(self):
        svc = make_svc()
        prompt = svc._build_text_generalize_prompt("测试文本内容超过二十个字符了吧", "", "1.2", "煤矿")
        assert "parameter|enum|descriptive|reference" in prompt
        assert '"summary"' in prompt
        assert '"key_points"' in prompt

    def test_normalize_coerces_invalid_type_and_counts(self):
        svc = make_svc()
        resp = {
            "generalized": "涌水量为 {{涌水量}}",
            "slots": [
                {"name": "涌水量", "type": "数值", "value": "300"},   # 非法 → 强转+计数
                {"name": "方式", "value": "集中排水"},                  # 缺 type → 补 parameter 不计数
                {"name": "口径", "type": "enum", "value": "x"},        # 合法保留
            ],
        }
        out = svc._normalize_template_response(resp)
        types = [s["type"] for s in out["slots"]]
        assert types == ["parameter", "parameter", "enum"]
        assert out["metadata"]["slot_type_coerced"] == 1

    def test_normalize_defaults_dual_product_fields(self):
        svc = make_svc()
        out = svc._normalize_template_response({"generalized": "x", "slots": []})
        assert out["summary"] == ""
        assert out["key_points"] == []

    def test_prose_coverage_denominator(self):
        paras = [
            {"classify_type": "prose", "template": {"generalized": "x"}},
            {"classify_type": "prose"},                                    # 无模板
            {"classify_type": "parameter", "template": {"generalized": "y"}},  # legacy 计入
            {"classify_type": "narrative"},                                # legacy 计入分母
            {"classify_type": "heading"},
            {"classify_type": "table", "template": {"generalized": "z"}},  # 结构类不计
        ]
        generalized, total = DomainFactoryService.compute_prose_coverage(paras)
        # 任务书原文误写 (2, 3)：按其自身口径（分母=prose/parameter/narrative 三值段落，
        # 与 _PROSE_TYPES 及上方四行注释一致）应为 (2, 4)，实测亦为 (2, 4)
        assert (generalized, total) == (2, 4)


class FakeStructuredRunnable:
    def __init__(self, data, err=None):
        self.data, self.err = data, err

    async def ainvoke(self, prompt):
        if self.err:
            raise self.err
        return self.data


class FakeLCModel:
    def __init__(self, data=None, err=None):
        self.data, self.err = data, err
        self.bind_calls = 0

    def with_structured_output(self, schema):
        self.bind_calls += 1
        return FakeStructuredRunnable(self.data, self.err)


class FakeAdapter:
    def __init__(self, lc):
        self.model, self.model_name = lc, "fake-model"


class TestStructuredChannel:
    def setup_method(self):
        # _structured_support 是进程级 ClassVar 缓存，跨用例清零避免用例顺序耦合
        DomainFactoryService._structured_support.clear()

    def _make_svc(self, monkeypatch, lc):
        import yuxi.models.chat as chat_mod
        svc = make_svc()
        monkeypatch.setattr(chat_mod, "select_model", lambda **kw: FakeAdapter(lc))
        # 裸容器无 Redis/Postgres：system_options.get() 在模型初始化 try 块内即抛
        # 'NoneType' object is not callable（pg_manager 未初始化），须一并 stub（仅测试侧）。
        # Option 是 frozen+slots dataclass，实例/类属性不可 setattr——改为替换服务模块的绑定
        import yuxi.services.domain_factory_service as svc_mod
        class _FakeSystemOptions:
            async def get(self):
                return {"default_model": "fake-model"}
        monkeypatch.setattr(svc_mod, "system_options", _FakeSystemOptions())
        # 降级通道 stub：返回合法模板 JSON
        async def fake_call(model, prompt):
            return '{"generalized": "x {{A}}", "slots": []}', {"error_type": None, "attempts": 1}
        monkeypatch.setattr(svc, "_call_llm_with_retry", fake_call)
        return svc

    def test_structured_success(self, monkeypatch):
        from yuxi.services.domain_factory_service import GeneralizedTemplate
        lc = FakeLCModel(data=GeneralizedTemplate(generalized="x {{A}}", slots=[], summary="s", key_points=["k"]))
        svc = self._make_svc(monkeypatch, lc)
        import asyncio
        resp, outcome = asyncio.run(svc._generalize_text_tracked("内容超过二十个字符了吧啊", "1.1"))
        assert outcome["status"] == "success" and outcome["channel"] == "structured"
        assert outcome["attempts"] == 1 and lc.bind_calls == 1
        assert resp["summary"] == "s" and resp["generalized"] == "x {{A}}"

    def test_structured_unsupported_downgrades_then_caches(self, monkeypatch):
        lc = FakeLCModel(err=RuntimeError("tools not supported"))
        svc = self._make_svc(monkeypatch, lc)
        import asyncio
        _, outcome = asyncio.run(svc._generalize_text_tracked("内容超过二十个字符了吧啊", "1.1"))
        assert outcome["channel"] == "prompt" and svc._structured_support.get("fake-model") is False
        _, outcome2 = asyncio.run(svc._generalize_text_tracked("再来一段超过二十个字符的内容啊", "1.2"))
        assert outcome2["channel"] == "prompt" and lc.bind_calls == 1  # 缓存生效，不再试探

    def test_record_outcome_counts_channel(self, monkeypatch):
        """集成验证 _record_outcome 的通道计数：fake tracked 返回带 channel 的 outcome"""
        import asyncio
        svc = make_svc()
        outcomes = iter([
            ({"generalized": "a", "slots": []}, {"status": "success", "error_type": None, "attempts": 1, "channel": "structured"}),
            ({"generalized": "b", "slots": []}, {"status": "success", "error_type": None, "attempts": 1, "channel": "prompt"}),
        ])
        async def fake_tracked(text, chapter_hint, prompt=None):
            return next(outcomes)
        monkeypatch.setattr(svc, "_generalize_text_tracked", fake_tracked)
        async def fake_templates():
            return {"template": None}
        monkeypatch.setattr(svc, "_load_prompt_templates", fake_templates)
        # 内容 >=20 字符：低于阈值会在 _run_for_paragraph 直接跳过（不进 tracked、不计数）
        paras = [{"id": f"p{i}", "content": f"第{i}段内容足够长可以被处理到了吧，补充更多文字"} for i in range(2)]
        gen = asyncio.run(svc.generalize_paragraphs(paragraphs=paras, schema_variables=[], domain_label="煤矿", max_concurrency=1))
        assert gen["stats"]["structured"] == 1
        assert gen["stats"]["success"] == 2
