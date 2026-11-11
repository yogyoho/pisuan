# C批修复单测（C-4/C-5 纯函数部分 + C-1 迁移表）。容器内执行：
# docker exec pisuan-localized-api-1 pytest /app/test/unit/test_c_batch_fixes.py --noconftest -q
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from pisuan.repositories.domain_factory_repository import (
    TASK_STATUS_EDGES,
    _validate_status_transition,
)
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

    def test_digit_sequence_positional(self):
        # 纯数字序列位序写法：逐字映射拼接，不再塌缩为末位
        assert make_svc()._chinese_to_arabic("一二三") == "123"

    def test_digit_sequence_descending(self):
        assert make_svc()._chinese_to_arabic("三二一") == "321"

    def test_digit_sequence_leading_zero(self):
        assert make_svc()._chinese_to_arabic("零八一") == "081"


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


class TestStatusTransition:
    MAIN_CHAIN = [
        ("UPLOADED", "PARSING"),
        ("PARSING", "GENERALIZING"),
        ("GENERALIZING", "WAITING_REVIEW"),
        ("WAITING_REVIEW", "INGESTING"),
        ("INGESTING", "COMMITTED"),
        ("INGESTING", "COMMIT_PARTIAL"),
        ("INGESTING", "COMMIT_FAILED"),
    ]

    def test_main_chain_legal(self):
        for cur, nxt in self.MAIN_CHAIN:
            _validate_status_transition(cur, nxt)  # 不抛即合法

    def test_same_value_noop(self):
        _validate_status_transition("WAITING_REVIEW", "WAITING_REVIEW")
        _validate_status_transition("COMMITTED", "COMMITTED")

    def test_illegal_raises(self):
        with pytest.raises(ValueError):
            _validate_status_transition("COMMITTED", "PARSING")
        with pytest.raises(ValueError):
            _validate_status_transition("PARSING", "COMMITTED")
        with pytest.raises(ValueError):
            _validate_status_transition("INGESTING", "UPLOADED")

    def test_retry_and_resume_edges(self):
        # C-3 恢复边 + durable ETL 收敛边：UPLOADED→FAILED
        _validate_status_transition("UPLOADED", "FAILED")
        # 提交前校验中止边：WAITING_REVIEW→COMMIT_FAILED（既有行为）
        _validate_status_transition("WAITING_REVIEW", "COMMIT_FAILED")
        # 泛化失败收敛边
        _validate_status_transition("PARSING", "FAILED")
        _validate_status_transition("GENERALIZING", "FAILED")
        # resume 真实运行路径（FAILED_PROVIDER 已砍除，断点续跑不再有独立状态）：
        # retry 先重置 UPLOADED，管线跳过解析直达泛化
        _validate_status_transition("FAILED", "UPLOADED")
        _validate_status_transition("UPLOADED", "GENERALIZING")
        # retry（对齐 retry_task 守卫现状）：非运行态均可重置 UPLOADED
        for source in ("FAILED", "WAITING_REVIEW", "COMMIT_FAILED", "COMMIT_PARTIAL", "COMMITTED"):
            _validate_status_transition(source, "UPLOADED")

    def test_all_states_covered(self):
        for status in (
            "UPLOADED",
            "PARSING",
            "GENERALIZING",
            "WAITING_REVIEW",
            "INGESTING",
            "FAILED",
            "COMMITTED",
            "COMMIT_PARTIAL",
            "COMMIT_FAILED",
        ):
            assert status in TASK_STATUS_EDGES


# ------------------------------------------------------------------
# 终审收口：commit/reingest 发起路径（发起侧零状态副作用 + 确定性 ingest_task_id）
# 注：commit_task/reingest_task 内部为函数内 `from pisuan.services.task_service import
# tasker` 导入——拿到的是模块级 tasker 实例，monkeypatch 打在实例属性上即可生效。
# ------------------------------------------------------------------


def _make_launch_repo(task):
    """发起路径测试用 repo mock：get_task_with_domain 返回 task，update_task 为 AsyncMock。"""
    repo = MagicMock()
    repo.get_task_with_domain = AsyncMock(return_value=task)
    repo.update_task = AsyncMock()
    return repo


async def test_commit_enqueue_failure_raises_and_keeps_status(monkeypatch):
    """enqueue 失败 → ValueError 上抛 + 仅写 error_message（无 status 键，WAITING_REVIEW 保持可重发）"""
    from pisuan.services.task_service import tasker

    task = SimpleNamespace(status="WAITING_REVIEW", file_name="a.docx")
    svc = make_svc()
    svc.repo = _make_launch_repo(task)
    monkeypatch.setattr(tasker, "enqueue", AsyncMock(side_effect=Exception("queue down")))

    with pytest.raises(ValueError, match="入库任务注册失败"):
        await svc.commit_task("t1", reviewer="admin", knowledge_base_id="kb1")

    svc.repo.update_task.assert_awaited_once()
    data = svc.repo.update_task.await_args.args[1]
    assert "status" not in data
    assert "error_message" in data


async def test_commit_reingest_state_guard(monkeypatch):
    """守卫与 TASK_STATUS_EDGES 同宽：非发起态一律 ValueError 且 repo 零写入、零入队"""
    from pisuan.services.task_service import tasker

    enqueue_mock = AsyncMock()
    monkeypatch.setattr(tasker, "enqueue", enqueue_mock)

    def _svc(status):
        task = SimpleNamespace(status=status, file_name="a.docx")
        svc = make_svc()
        svc.repo = _make_launch_repo(task)
        return svc

    # commit：UPLOADED（未到审核态）与 INGESTING（运行中）均不可发起
    for status in ("UPLOADED", "INGESTING"):
        svc = _svc(status)
        with pytest.raises(ValueError, match="不允许发起入库"):
            await svc.commit_task("t1")
        svc.repo.update_task.assert_not_awaited()

    # reingest：WAITING_REVIEW（尚未入库）与 INGESTING 均不可发起
    for status in ("WAITING_REVIEW", "INGESTING"):
        svc = _svc(status)
        with pytest.raises(ValueError, match="无法再入库"):
            await svc.reingest_task("t1")
        svc.repo.update_task.assert_not_awaited()

    enqueue_mock.assert_not_awaited()


async def test_reingest_clears_attribution_only_after_enqueue(monkeypatch):
    """归属字段清（committed_at/reviewer→None）只发生在 enqueue 成功之后；enqueue 失败零写入"""
    from pisuan.services.task_service import tasker

    order: list[str] = []
    task = MagicMock()
    task.status = "COMMITTED"
    task.file_name = "a.docx"
    task.to_summary_dict.return_value = {"task_id": "t9"}

    async def ok_enqueue(**kwargs):
        order.append("enqueue")

    async def record_update(task_id, data):
        order.append("update")
        return task  # 对齐真实 repo.update_task 契约：返回更新后对象，reingest 尾部 to_summary_dict 依赖

    repo = _make_launch_repo(task)
    repo.update_task = AsyncMock(side_effect=record_update)
    monkeypatch.setattr(tasker, "enqueue", ok_enqueue)

    svc = make_svc()
    svc.repo = repo
    result = await svc.reingest_task("t9", knowledge_base_id="kb1")
    assert order == ["enqueue", "update"]
    repo.update_task.assert_awaited_once_with("t9", {"committed_at": None, "reviewer": None})
    assert result["ingest_task_id"] == "reingest_t9"

    # 失败路径：enqueue 抛错 → 不写任何字段 + ValueError 上抛（尚无字段可恢复）
    async def bad_enqueue(**kwargs):
        raise Exception("queue down")

    monkeypatch.setattr(tasker, "enqueue", bad_enqueue)
    with pytest.raises(ValueError, match="再入库任务注册失败"):
        await svc.reingest_task("t9", knowledge_base_id="kb1")
    assert repo.update_task.await_count == 1  # 仅成功路径那次
