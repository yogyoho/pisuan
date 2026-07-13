from unittest.mock import MagicMock

from scripts.governance.fix_existing_graph import GraphGovernance, GovernanceReport


def test_dry_run_does_not_modify_graph():
    """dry-run 模式不执行任何写操作"""
    gov = GraphGovernance(dry_run=True)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_session.run.return_value = MagicMock()

    gov.merge_general_branch(fake_driver)

    write_calls = [
        c for c in fake_session.run.call_args_list
        if "SET" in str(c) or "MERGE" in str(c) or "DELETE" in str(c)
    ]
    assert len(write_calls) == 0


def test_report_initialization():
    report = GovernanceReport()
    assert report.fixed_keys == 0
    assert report.merged_branches == 0
    assert report.cleaned_titles == 0
    assert report.errors == []


def test_clean_title_dual_numbering():
    """清洗双编号 title"""
    from scripts.governance.fix_existing_graph import clean_chapter_title

    assert clean_chapter_title("1.1.1 3.1.1 地形地貌") == "地形地貌"
    assert clean_chapter_title("3.1.1 地形地貌") == "地形地貌"
    assert clean_chapter_title("2") == ""
    assert clean_chapter_title("地形地貌") == "地形地貌"


def test_derive_canonical_key_from_clean_title():
    """从清洗后 title 推导 canonical_chapter_key"""
    from scripts.governance.fix_existing_graph import derive_canonical_key

    assert derive_canonical_key("地形地貌") == "地形地貌"
    assert derive_canonical_key("") == ""
    assert derive_canonical_key("气候气象") == "气候气象"
