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
