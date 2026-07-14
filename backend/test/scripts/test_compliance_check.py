"""compliance_check.py 单元测试:8 项合规检查 + 整体 check。"""

from scripts.compliance_check import ComplianceChecker


# ---------------------------------------------------------------------------
# 1. 标准引用完整性
# ---------------------------------------------------------------------------


def test_standard_reference_complete():
    """markdown 含必引导则标准编号 → PASS"""
    checker = ComplianceChecker()
    md = "本项目执行 GB 3095 环境空气质量标准及 HJ 2.2 大气环境影响评价技术导则。"
    result = checker.check_standard_reference(md)
    assert result["status"] == "PASS"


def test_standard_reference_missing_required():
    """markdown 缺少必引导则(HJ/T 130) → WARN"""
    checker = ComplianceChecker()
    md = "本项目执行 GB 3095 环境空气质量标准。"
    result = checker.check_standard_reference(md)
    assert result["status"] == "WARN"
    assert "HJ/T 130" in result["detail"] or "HJ 130" in result["detail"]


# ---------------------------------------------------------------------------
# 2. 标准编号格式
# ---------------------------------------------------------------------------


def test_standard_format_valid():
    """正确格式标准编号 → PASS"""
    checker = ComplianceChecker()
    md = "执行 GB 3095、GB/T 14848、HJ 2.2 标准。"
    result = checker.check_standard_format(md)
    assert result["status"] == "PASS"


def test_standard_format_invalid():
    """格式错误标准编号(如 GB3095 无空格分隔) → WARN"""
    checker = ComplianceChecker()
    md = "执行 GB3095 标准。"
    result = checker.check_standard_format(md)
    assert result["status"] == "WARN"


def test_standard_format_no_standards():
    """无标准编号 → PASS(不适用)"""
    checker = ComplianceChecker()
    md = "本区气候温和。"
    result = checker.check_standard_format(md)
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# 3. 必填要素覆盖
# ---------------------------------------------------------------------------


def test_key_elements_all_covered():
    """所有 key_elements 出现 → PASS"""
    checker = ComplianceChecker()
    cc = {"key_elements": ["气候类型", "气温", "降水"]}
    md = "本区气候类型为温带季风,气温12℃,降水600mm。"
    result = checker.check_key_elements(md, cc)
    assert result["status"] == "PASS"


def test_key_elements_missing():
    """部分 key_elements 缺失 → FAIL"""
    checker = ComplianceChecker()
    cc = {"key_elements": ["气候类型", "气温", "降水", "风向风速"]}
    md = "本区气候类型为温带季风,气温12℃。"
    result = checker.check_key_elements(md, cc)
    assert result["status"] == "FAIL"
    assert "风向风速" in result["detail"]


def test_key_elements_no_contract():
    """无 content_contract → PASS(跳过)"""
    checker = ComplianceChecker()
    result = checker.check_key_elements("内容", None)
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# 4. 数值占位符残留
# ---------------------------------------------------------------------------


def test_placeholder_no_residual():
    """无占位符残留 → PASS"""
    checker = ComplianceChecker()
    md = "本区年平均气温12.5℃,年降水量600mm。"
    result = checker.check_placeholder(md)
    assert result["status"] == "PASS"


def test_placeholder_missing_residual():
    """检测到 {{MISSING:...}} 残留 → FAIL"""
    checker = ComplianceChecker()
    md = "本区年平均气温{{MISSING:气温数据}},年降水量600mm。"
    result = checker.check_placeholder(md)
    assert result["status"] == "FAIL"
    assert "{{MISSING" in result["detail"]


def test_placeholder_xx_residual():
    """检测到 [XX] 残留 → FAIL"""
    checker = ComplianceChecker()
    md = "本区年平均气温[XX]℃,年降水量600mm。"
    result = checker.check_placeholder(md)
    assert result["status"] == "FAIL"


def test_placeholder_待补充_residual():
    """检测到 [待补充] 残留 → FAIL"""
    checker = ComplianceChecker()
    md = "本区年平均气温[待补充]。"
    result = checker.check_placeholder(md)
    assert result["status"] == "FAIL"


# ---------------------------------------------------------------------------
# 5. 禁止用语检测
# ---------------------------------------------------------------------------


def test_forbidden_phrases_none():
    """无禁止用语 → PASS"""
    checker = ComplianceChecker()
    cc = {"forbidden_phrases": ["大约", "可能", "暂定"]}
    md = "本区年平均气温12.5℃,年降水量600mm。"
    result = checker.check_forbidden_phrases(md, cc)
    assert result["status"] == "PASS"


def test_forbidden_phrases_detected():
    """检测到禁止用语 → WARN"""
    checker = ComplianceChecker()
    cc = {"forbidden_phrases": ["大约", "可能", "暂定"]}
    md = "本区年平均气温大约12.5℃,年降水量可能600mm。"
    result = checker.check_forbidden_phrases(md, cc)
    assert result["status"] == "WARN"
    assert "大约" in result["detail"]


def test_forbidden_phrases_no_contract():
    """无 content_contract → PASS(跳过)"""
    checker = ComplianceChecker()
    result = checker.check_forbidden_phrases("内容", None)
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# 6. 章节字数下限
# ---------------------------------------------------------------------------


def test_word_count_sufficient():
    """字数达标 → PASS"""
    checker = ComplianceChecker()
    cc = {"min_word_count": 10}
    md = "本区气候类型为温带季风气候,年平均气温12.5℃,年降水量600mm,主导风向西北风。"
    result = checker.check_word_count(md, cc)
    assert result["status"] == "PASS"


def test_word_count_insufficient():
    """字数不足 → WARN"""
    checker = ComplianceChecker()
    cc = {"min_word_count": 1000}
    md = "本区气候温和。"
    result = checker.check_word_count(md, cc)
    assert result["status"] == "WARN"


def test_word_count_no_contract():
    """无 content_contract → PASS(跳过)"""
    checker = ComplianceChecker()
    result = checker.check_word_count("短", None)
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# 7. 交叉引用完整性
# ---------------------------------------------------------------------------


def test_cross_reference_no_residual():
    """无 {{REF:...}} 残留 → PASS"""
    checker = ComplianceChecker()
    md = "详见本章表3-1及第5章相关内容。"
    result = checker.check_cross_reference(md)
    assert result["status"] == "PASS"


def test_cross_reference_residual():
    """检测到 {{REF:...}} 未解析残留 → WARN"""
    checker = ComplianceChecker()
    md = "详见{{REF:表3-1}}及第5章相关内容。"
    result = checker.check_cross_reference(md)
    assert result["status"] == "WARN"
    assert "{{REF" in result["detail"]


# ---------------------------------------------------------------------------
# 8. 表格编号连续性
# ---------------------------------------------------------------------------


def test_table_numbering_continuous():
    """表格编号连续(表3-1, 表3-2, 表3-3) → PASS"""
    checker = ComplianceChecker()
    md = "见表3-1、表3-2和表3-3。"
    result = checker.check_table_numbering(md)
    assert result["status"] == "PASS"


def test_table_numbering_gap():
    """表格编号不连续(表3-1, 表3-3 缺 表3-2) → WARN"""
    checker = ComplianceChecker()
    md = "见表3-1和表3-3。"
    result = checker.check_table_numbering(md)
    assert result["status"] == "WARN"


def test_table_numbering_none():
    """无表格编号 → PASS(不适用)"""
    checker = ComplianceChecker()
    md = "本区气候温和。"
    result = checker.check_table_numbering(md)
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# 整体 check
# ---------------------------------------------------------------------------


def test_check_all_pass():
    """全部检查通过 → passed=True"""
    checker = ComplianceChecker()
    md = (
        "本区气候类型为温带季风气候,年平均气温12.5℃,年降水量600mm,"
        "主导风向西北风,静风频率15%。"
        "执行 GB 3095 环境空气质量标准及 HJ 2.2 大气环境影响评价技术导则,"
        "并参照 HJ/T 130 规划环评技术导则。"
        "详见本章表3-1和表3-2。"
    )
    cc = {
        "key_elements": ["气候类型", "气温", "降水", "风向", "静风频率"],
        "min_word_count": 10,
        "forbidden_phrases": ["大约", "可能"],
    }
    result = checker.check(md, cc)
    assert result["passed"] is True
    assert len(result["checks"]) == 8


def test_check_with_failures():
    """有 FAIL 项 → passed=False"""
    checker = ComplianceChecker()
    md = "本区气温{{MISSING:数据}}大约12.5℃。"
    cc = {
        "key_elements": ["气候类型", "降水"],
        "forbidden_phrases": ["大约"],
    }
    result = checker.check(md, cc)
    assert result["passed"] is False
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["数值占位符残留"] == "FAIL"


def test_check_no_content_contract():
    """无 content_contract → 跳过相关检查,只跑通用检查"""
    checker = ComplianceChecker()
    md = "执行 GB 3095 标准,详见{{REF:表3-1}}。"
    result = checker.check(md, None)
    assert "checks" in result
    assert len(result["checks"]) == 8
