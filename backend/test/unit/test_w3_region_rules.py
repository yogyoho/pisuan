# W3 归属判定纯函数单测：词表/L1 任务归因/min-permissive 聚合/fact 映射。
# 验证走容器道：
# MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" \
#   pisuan-api:0.7.3 pytest /app/test/unit/test_w3_region_rules.py --noconftest -q
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_region import (  # noqa: E402
    REGION_VOCAB,
    apply_min_permissive,
    extract_fact_signal,
    extract_region_signal,
    extract_year,
    fact_type_for_category,
    l1_task_attribution,
    min_permissive_scope,
)


class TestVocab:
    def test_slug_format(self):
        for name, key in REGION_VOCAB.items():
            assert re.fullmatch(r"[a-z0-9-]+", key), f"{name} -> {key} 不合 slug 格式"

    def test_vocab_only_region_identity(self):
        # 项目名不入词表：防项目报告正文引用矿区名被误判 regional（Q2 语义）
        for banned in ("伊泰煤矿", "活鸡兔煤矿", "柠条塔矿井", "月儿湾矿井", "九龙川矿井"):
            assert banned not in REGION_VOCAB


class TestRegionSignal:
    def test_hit(self):
        assert extract_region_signal("横城矿区总体规划（修编）环评") == {
            "region_label": "横城矿区",
            "region_key": "hengcheng",
        }

    def test_longest_name_wins(self):
        sig = extract_region_signal("伊宁矿区北区总体规划环评报告书")
        assert sig is not None and sig["region_key"] == "yining-beiqu"

    def test_miss(self):
        assert extract_region_signal("活鸡兔煤矿改扩建项目环境影响报告书") is None


class TestTaskAttribution:
    def test_plan_report_regional(self):
        out = l1_task_attribution(
            {
                "file_name": "2横城矿区总体规划（修编）环评——报告书报批版2021.1.docx",
                "document_type": "通用",
                "report_type_code": "通用",
            }
        )
        assert out == {"region_label": "横城矿区", "region_key": "hengcheng", "scope": "regional"}

    def test_project_report_no_attribution(self):
        # 项目报告文件名无矿区词 → None（scope 留 NULL，交 L2/兜底 project）
        out = l1_task_attribution(
            {
                "file_name": "活鸡兔煤矿改扩建项目环评报告-2023.9.docx",
                "document_type": "通用",
                "report_type_code": "通用",
            }
        )
        assert out is None

    def test_none_fields_tolerated(self):
        assert l1_task_attribution({"file_name": None, "document_type": None, "report_type_code": None}) is None


class TestMinPermissive:
    def test_empty_evidence_returns_none(self):
        assert min_permissive_scope([]) is None
        assert min_permissive_scope([None, None]) is None

    def test_uniform(self):
        assert min_permissive_scope(["project", "project"]) == "project"
        assert min_permissive_scope(["regional", "regional"]) == "regional"
        assert min_permissive_scope(["universal"]) == "universal"

    def test_mixed_takes_narrowest(self):
        assert min_permissive_scope(["universal", "regional"]) == "regional"
        assert min_permissive_scope(["regional", "project"]) == "project"
        assert min_permissive_scope(["universal", "project", "regional"]) == "project"

    def test_null_evidence_not_participating(self):
        assert min_permissive_scope([None, "regional"]) == "regional"

    def test_apply_degrades_universal_only(self):
        assert apply_min_permissive("universal", ["regional"]) == "regional"
        assert apply_min_permissive("universal", ["project"]) == "project"

    def test_apply_never_upgrades(self):
        assert apply_min_permissive("project", ["universal"]) == "project"
        assert apply_min_permissive("regional", ["universal"]) == "regional"

    def test_apply_empty_keeps_current(self):
        assert apply_min_permissive("universal", [None]) == "universal"
        assert apply_min_permissive(None, [None]) is None

    def test_apply_null_current_takes_target(self):
        assert apply_min_permissive(None, ["project"]) == "project"


class TestFactMapping:
    def test_direct_mapping(self):
        assert fact_type_for_category("natural_env", "地形地貌") == "monitoring"
        assert fact_type_for_category("env_quality", "空气质量现状") == "monitoring"
        assert fact_type_for_category("sensitive_target", "某居民点") == "sensitive_target"
        assert fact_type_for_category("impact_assessment", "沉陷预测结论") == "constraint"

    def test_measures_regulation_split(self):
        assert fact_type_for_category("measures_regulation", "执行标准 GB20426") == "constraint"
        assert fact_type_for_category("measures_regulation", "沉陷区治理工程措施") == "measure"

    def test_c_class_rejected(self):
        assert fact_type_for_category("project_basic", "产能 500 万吨") is None
        assert fact_type_for_category("其他", "任意") is None


class TestYearAndFactSignal:
    def test_year(self):
        assert extract_year("2021年1月报批版") == 2021
        assert extract_year("无年份文本") is None

    def test_fact_signal(self):
        assert extract_fact_signal("排放浓度执行标准限值") == "constraint"
        assert extract_fact_signal("制定沉陷区治理措施") == "measure"
        assert extract_fact_signal("无关键词中性文本") is None
