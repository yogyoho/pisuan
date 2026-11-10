# C批修复单测（C-4/C-5 纯函数部分 + C-1 迁移表）。容器内执行：
# docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from pisuan.services.domain_factory_service import DomainFactoryService, GeneralizedTemplate


def make_svc() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


class TestChineseToArabic:
    def test_eleven(self):
        assert make_svc()._chinese_to_arabic("十一") == "11"

    def test_twenty_three(self):
        assert make_svc()._chinese_to_arabic("二十三") == "23"

    def test_one_hundred_three(self):
        assert make_svc()._chinese_to_arabic("一百零三") == "103"

    def test_liang(self):
        assert make_svc()._chinese_to_arabic("两") == "2"

    def test_ten(self):
        assert make_svc()._chinese_to_arabic("十") == "10"

    def test_ten_thousand_section(self):
        assert make_svc()._chinese_to_arabic("十二万三千") == "123000"

    def test_ten_thousand_with_zero(self):
        assert make_svc()._chinese_to_arabic("一万零一") == "10001"

    def test_yi_section(self):
        assert make_svc()._chinese_to_arabic("三亿") == "300000000"

    def test_twenty(self):
        assert make_svc()._chinese_to_arabic("二十") == "20"

    def test_arabic_passthrough(self):
        assert make_svc()._chinese_to_arabic("1.2") == "1.2"

    def test_mixed_passthrough(self):
        assert make_svc()._chinese_to_arabic("第3章") == "第3章"


class TestNarrativeCleanupTombstones:
    def test_no_narrative_placeholders_field(self):
        assert "narrative_placeholders" not in GeneralizedTemplate.model_fields


class TestGeneralizeInput:
    def test_table_whole_never_truncated(self):
        long_table = "| a | b |\n|---|---|\n" + "\n".join(f"| x{i} | y{i} |" for i in range(500))
        out, body, truncated = make_svc()._build_generalize_input(long_table, True, "3.2")
        assert truncated is False
        assert out == long_table
        assert body == long_table  # 表格整块：正文同样不切碎

    def test_prose_under_budget_with_prefix(self):
        out, body, truncated = make_svc()._build_generalize_input("短段落。", False, "1.2")
        assert truncated is False
        assert out == "【章节】1.2\n短段落。"
        assert body == "短段落。"  # 正文不带前缀（兜底路径语义）

    def test_prose_over_budget_drops_tail_at_boundary(self):
        body = "首句内容。" + "后续句子。" * 2000
        out, _, truncated = make_svc()._build_generalize_input(body, False, "")
        assert truncated is True
        assert len(out) <= make_svc().GENERALIZE_PROSE_BUDGET
        assert out.endswith("。")
        assert body.startswith(out)
        assert "【章节】" not in out

    def test_no_chapter_no_prefix(self):
        out, body, _ = make_svc()._build_generalize_input("内容", False, "")
        assert out == "内容"
        assert body == "内容"

    def test_exactly_at_budget_passthrough(self):
        text = "字" * 4000
        out, body, truncated = make_svc()._build_generalize_input(text, False, "1.2")
        assert truncated is False
        assert out == "【章节】1.2\n" + text
        assert body == text

    def test_no_boundary_hard_head(self):
        text = "x" * 5000  # 前 4000 字符内无 。；\n
        out, _, truncated = make_svc()._build_generalize_input(text, False, "")
        assert truncated is True
        assert len(out) == 4000

    def test_boundary_at_index_zero(self):
        text = "。" + "x" * 5000  # rfind=0 不满足 cut>0，应硬切头部而非产出单字符 body
        out, _, truncated = make_svc()._build_generalize_input(text, False, "")
        assert truncated is True
        assert len(out) == 4000
        assert out == text[:4000]
