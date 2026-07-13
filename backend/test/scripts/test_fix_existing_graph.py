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


def test_merge_general_branch_executes_cypher_when_not_dry_run():
    """非 dry-run 模式下执行合并 Cypher"""
    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.single.return_value = {"cnt": 41}
    fake_result.peek.return_value = True
    fake_session.run.return_value = fake_result

    gov.merge_general_branch(fake_driver)

    cypher_calls = [str(c) for c in fake_session.run.call_args_list]
    assert any("report_type" in c and "eia_report" in c for c in cypher_calls)


def test_clean_titles_uses_clean_chapter_title():
    """clean_titles 步骤调用 clean_chapter_title 处理每个 title"""
    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter([{"id": "ch1", "title": "1.1.1 3.1.1 地形地貌"}])
    fake_session.run.return_value = fake_result

    gov.clean_titles(fake_driver)
    assert gov.report.cleaned_titles >= 1


def test_backfill_keys_increments_fixed_keys():
    """backfill_keys 步骤对 canonical_chapter_key 为空的章节回填并计数"""
    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter([
        {"id": "ch1", "title": "地形地貌"},
        {"id": "ch2", "title": "1.1.1 气候气象"},
    ])
    fake_session.run.return_value = fake_result

    gov.backfill_keys(fake_driver)
    assert gov.report.fixed_keys == 2
