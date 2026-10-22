# W4 行政区辅助词表单测：9 收录命中 / 4+2 排除不命中 / 主命中优先 / 段落级回归钉。
# 验证走容器道：
# MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" \
#   pisuan-api:0.7.3 pytest /app/test/unit/test_w4_admin_vocab.py --noconftest -q
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from pisuan.services.domain_factory_region import (  # noqa: E402
    ADMIN_REGION_VOCAB,
    extract_region_signal,
    l1_task_attribution,
)


def _doc(word: str) -> dict:
    return {"file_name": f"{word}相关规划环评报告书.docx", "document_type": "通用", "report_type_code": "通用"}


class TestAdminVocab:
    def test_slug_format_and_size(self):
        assert len(ADMIN_REGION_VOCAB) == 9
        for name, key in ADMIN_REGION_VOCAB.items():
            assert re.fullmatch(r"[a-z0-9-]+", key), f"{name} -> {key} 不合 slug 格式"

    def test_nine_entries_hit_regional(self):
        for word, expected_key in ADMIN_REGION_VOCAB.items():
            out = l1_task_attribution(_doc(word))
            assert out is not None, word
            assert out["scope"] == "regional", word
            assert out["region_key"] == expected_key, word

    def test_canonical_label_from_primary_vocab(self):
        # 行政区命中 hengcheng 时，region_label 反查主词表展示名「横城矿区」而非「灵武市」
        out = l1_task_attribution(_doc("灵武市"))
        assert out == {"region_label": "横城矿区", "region_key": "hengcheng", "scope": "regional"}

    def test_excluded_words_do_not_hit(self):
        # 排除代表词：邻区参照 / 省市级过宽 / 陷阱词「横城村」（属兴庆区，且不构成「横城矿区」子串命中）
        for word in ("定边县", "博乐市", "萨尔布拉克镇", "横城村", "宁夏", "伊犁州"):
            assert l1_task_attribution(_doc(word)) is None, word

    def test_primary_hit_wins_over_admin(self):
        # 同时含主词表名与行政区词 → 主词表胜（同通道最长名优先）
        doc = {
            "file_name": "伊宁矿区北区总体规划（伊宁县境内）环评.docx",
            "document_type": "通用",
            "report_type_code": "通用",
        }
        out = l1_task_attribution(doc)
        assert out == {"region_label": "伊宁矿区北区", "region_key": "yining-beiqu", "scope": "regional"}

    def test_extract_region_signal_untouched(self):
        # 回归钉：段落级信号函数不查行政区词表（classify region_signals 行为零变动的根基）
        assert extract_region_signal("灵武市临河镇") is None
        assert extract_region_signal("评价范围为横城矿区") == {
            "region_label": "横城矿区",
            "region_key": "hengcheng",
        }
