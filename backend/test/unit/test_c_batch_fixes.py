# C批修复单测（C-4/C-5 纯函数部分 + C-1 迁移表）。容器内执行：
# docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import DomainFactoryService, GeneralizedTemplate


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
