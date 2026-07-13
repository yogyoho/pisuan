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
        c for c in fake_session.run.call_args_list if "SET" in str(c) or "MERGE" in str(c) or "DELETE" in str(c)
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
    fake_result.__iter__ = lambda self: iter(
        [
            {"id": "ch1", "title": "地形地貌"},
            {"id": "ch2", "title": "1.1.1 气候气象"},
        ]
    )
    fake_session.run.return_value = fake_result

    gov.backfill_keys(fake_driver)
    assert gov.report.fixed_keys == 2


def test_backfill_para_keys_uses_section_lookup():
    """backfill_para_keys 通过 Section 反查所属 ChapterTemplate 回填"""
    from scripts.governance.fix_existing_graph import GraphGovernance

    gov = GraphGovernance(dry_run=False)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter(
        [
            {"pt_id": "pt1", "ch_keys": ["地形地貌"], "ch_titles": []},
            {"pt_id": "pt2", "ch_keys": [], "ch_titles": ["气候气象"]},
            {"pt_id": "pt3", "ch_keys": [], "ch_titles": []},
        ]
    )
    fake_session.run.return_value = fake_result

    gov.backfill_para_keys(fake_driver)
    # pt1 有 ch_keys → 回填; pt2 从 title 推导 → 回填; pt3 都没有 → 跳过
    assert gov.report.fixed_para_keys == 2


def test_backfill_para_keys_dry_run_no_write():
    """dry-run 模式只统计不写入"""
    from scripts.governance.fix_existing_graph import GraphGovernance

    gov = GraphGovernance(dry_run=True)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.__iter__ = lambda self: iter([{"pt_id": "pt1", "ch_keys": ["地形地貌"], "ch_titles": []}])
    fake_session.run.return_value = fake_result

    gov.backfill_para_keys(fake_driver)
    assert gov.report.fixed_para_keys == 1  # 统计了
    # 但不应有 SET 写操作
    write_calls = [str(c) for c in fake_session.run.call_args_list if "SET pt.canonical" in str(c)]
    assert len(write_calls) == 0


def test_merge_general_branch_deduplicates_after_merge():
    """非 dry-run 模式下,合并后执行去重 Cypher(迁移关系 + 删除重复节点)"""
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
    # 去重 Cypher 应包含 DETACH DELETE + canonical_chapter_key
    assert any("DETACH DELETE" in c and "canonical_chapter_key" in c for c in cypher_calls), "合并后应执行去重 Cypher"


def test_merge_general_branch_dry_run_skips_dedup():
    """dry-run 模式不执行去重"""
    gov = GraphGovernance(dry_run=True)
    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_result = MagicMock()
    fake_result.single.return_value = {"cnt": 41}
    fake_session.run.return_value = fake_result

    gov.merge_general_branch(fake_driver)

    cypher_calls = [str(c) for c in fake_session.run.call_args_list]
    dedup_calls = [c for c in cypher_calls if "DETACH DELETE" in c and "canonical_chapter_key" in c]
    assert len(dedup_calls) == 0, "dry-run 不应执行去重"
