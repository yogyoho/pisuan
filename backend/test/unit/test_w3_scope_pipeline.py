# W3 L2 便车 + L1 并列键 + 任务级归属 patch 单测。容器道同 test_w3_region_rules.py 头注。
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import (  # noqa: E402
    DomainFactoryService,
    GeneralizedTemplate,
)


def make_svc() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


class FakeTaskRow:
    def __init__(self, file_name="某项目环评.docx", document_type="通用", report_type_code="通用",
                 scope=None, region_label=None, region_key=None):
        self.file_name = file_name
        self.document_type = document_type
        self.report_type_code = report_type_code
        self.scope = scope
        self.region_label = region_label
        self.region_key = region_key


class TestGeneralizedTemplateFields:
    def test_defaults_are_none(self):
        gt = GeneralizedTemplate()
        assert gt.scope is None and gt.region is None

    def test_structured_dump_none_means_no_evidence(self):
        # structured 通道 model_dump 物化默认字段——None 即「无证据」，不得物化非 None 默认
        data = GeneralizedTemplate(generalized="x").model_dump()
        assert data["scope"] is None and data["region"] is None


class TestPromptDescribesOptionalFields:
    def test_prompt_mentions_scope_region(self):
        svc = make_svc()
        prompt = svc._build_text_generalize_prompt("测试文本内容超过二十个字符了吧", "", "1.2", "煤矿")
        assert '"scope"' in prompt
        assert '"region"' in prompt


class TestNormalizeCoerces:
    def test_invalid_scope_coerced_to_none(self):
        svc = make_svc()
        out = svc._normalize_template_response({"generalized": "x", "scope": "全世界", "region": "  "})
        assert out["scope"] is None
        assert out["region"] is None

    def test_valid_scope_kept(self):
        svc = make_svc()
        out = svc._normalize_template_response({"generalized": "x", "scope": "regional", "region": "横城矿区"})
        assert out["scope"] == "regional"
        assert out["region"] == "横城矿区"


class TestClassifyParallelKeys:
    def test_prose_parallel_keys_added(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "横城矿区规划范围包括以下区域。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["region_signals"] == [{"region_label": "横城矿区", "region_key": "hengcheng"}]
        assert out[0]["fact_signals"] == []  # 中性文本无 fact 信号

    def test_no_hit_empty_signal(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "矿井正常涌水量为 300 m3/h。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["region_signals"] == []
        assert out[0]["fact_signals"] == []

    def test_skip_branch_untouched_plus_signals(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "横城矿区相关描述。", "classify_type": "table", "classify_tags": ["x"]}]
        out = svc.classify_paragraphs(paras)
        # 钉住行为不变：跳过分支将 classify_tags 重置为空（test_w1_prose_pipeline 同款断言）
        assert out[0]["classify_tags"] == []
        # 并列键照常产出（W3 新键独立于类型分支）
        assert out[0]["region_signals"] == [{"region_label": "横城矿区", "region_key": "hengcheng"}]

    def test_w1_baseline_regression(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "矿井正常涌水量为 300 m3/h，采用集中排水方式。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        # 基线实测：涌水量命中 _SLOT_PATTERNS（水量）追加 reusable，W1 同款 fixture 断言见
        # test_w1_prose_pipeline.py::test_prose_fallback_param_tags（任务书原文漏 reusable，按现场基线修正）
        assert out[0]["classify_tags"] == ["measurable", "reusable"]


class TestCollectL2Suggestions:
    def test_first_non_null_wins(self):
        results = {
            "a": {"generalized": "x"},
            "b": {"generalized": "y", "scope": "regional", "region": "横城矿区"},
            "c": {"generalized": "z", "scope": "project"},
        }
        assert DomainFactoryService._collect_l2_suggestions(results) == {"scope": "regional", "region": "横城矿区"}

    def test_none_when_absent(self):
        assert DomainFactoryService._collect_l2_suggestions({"a": {"generalized": "x"}}) == {}


class TestAttributionPatch:
    def test_l1_wins_over_l2(self):
        svc = make_svc()
        row = FakeTaskRow(file_name="2横城矿区总体规划（修编）环评——报批版2021.1.docx")
        patch = svc._build_attribution_patch(row, {"a": {"scope": "project", "region": "伊敏矿区"}})
        assert patch["scope"] == "regional"
        assert patch["region_key"] == "hengcheng"

    def test_l2_fills_null_only(self):
        svc = make_svc()
        row = FakeTaskRow()
        patch = svc._build_attribution_patch(row, {"a": {"scope": "project", "region": "横城矿区"}})
        assert patch["scope"] == "project"
        assert patch["region_label"] == "横城矿区"
        assert patch["region_key"] == "hengcheng"

    def test_existing_values_untouched(self):
        svc = make_svc()
        row = FakeTaskRow(scope="project", region_label="已有", region_key="x")
        patch = svc._build_attribution_patch(row, {"a": {"scope": "regional", "region": "横城矿区"}})
        assert patch == {}

    def test_no_evidence_no_patch(self):
        svc = make_svc()
        row = FakeTaskRow()
        assert svc._build_attribution_patch(row, {"a": {"generalized": "x"}}) == {}

    def test_l2_unregistered_region_no_key_invented(self):
        # L2 region 为词表外名 → 只落 region_label，不静默造 region_key
        svc = make_svc()
        row = FakeTaskRow()
        patch = svc._build_attribution_patch(row, {"a": {"scope": "regional", "region": "某未知矿区"}})
        assert patch == {"scope": "regional", "region_label": "某未知矿区"}

    def test_l1_hit_existing_key_scope_only(self):
        # L1 命中但 region_key 已有值且无 L2 证据 → 只补 scope
        svc = make_svc()
        row = FakeTaskRow(file_name="2横城矿区总体规划（修编）环评.docx", region_key="hengcheng")
        patch = svc._build_attribution_patch(row, {"a": {"generalized": "x"}})
        assert patch == {"scope": "regional"}
