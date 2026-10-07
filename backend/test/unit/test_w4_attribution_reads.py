# W4 归属管理读接口单测：region 纯函数派生 + service 读函数（fake repo，无 DB）。
# 验证走容器道：
# MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" \
#   pisuan-api:0.7.3 pytest /app/test/unit/test_w4_attribution_reads.py --noconftest -q
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_region import (  # noqa: E402
    derive_template_region,
    region_label_for_key,
)
from yuxi.services.domain_factory_service import DomainFactoryService  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class TestDeriveTemplateRegion:
    def test_single_region(self):
        assert derive_template_region(["t1", "t2"], {"t1": "hengcheng", "t2": "hengcheng"}) == "hengcheng"

    def test_mixed_regions(self):
        assert derive_template_region(["t1", "t2"], {"t1": "hengcheng", "t2": "yining-beiqu"}) == "mixed"

    def test_empty_or_all_null_returns_none(self):
        assert derive_template_region([], {"t1": "hengcheng"}) is None
        assert derive_template_region(["t1"], {"t1": None}) is None
        assert derive_template_region(None, {}) is None

    def test_null_evidence_not_participating(self):
        # 归因集中 region 为 NULL 的任务不参与派生（与 min-permissive 的 NULL 不参与同语义）
        assert derive_template_region(["t1", "t2"], {"t1": "hengcheng", "t2": None}) == "hengcheng"


class TestRegionLabelForKey:
    def test_primary_vocab_reverse(self):
        assert region_label_for_key("hengcheng") == "横城矿区"
        assert region_label_for_key("yining-beiqu") == "伊宁矿区北区"

    def test_unknown_returns_none(self):
        assert region_label_for_key("no-such-region") is None


class FakeReadRepo:
    """list/board 读接口最小 fake（只实现被测三方法，返回形状与真实 repo 契约一致）。"""

    def __init__(self):
        self.calls = []

    async def list_tasks_with_attribution(self, scope=None, region_key=None, keyword=None, page=1, page_size=20):
        self.calls.append(
            {"scope": scope, "region_key": region_key, "keyword": keyword, "page": page, "page_size": page_size}
        )
        return [{"id": "t1", "file_name": "x.docx"}], 1

    async def list_regional_facts(self, region_key=None, fact_type=None, status=None, page=1, page_size=20):
        self.calls.append(
            {"region_key": region_key, "fact_type": fact_type, "status": status, "page": page, "page_size": page_size}
        )
        return [{"id": 1, "source_task_file_name": "x.docx"}], 1

    async def get_region_board_raw(self):
        return {
            "tasks_by_region": [
                {"region_key": "hengcheng", "region_label": "横城矿区", "count": 2},
                {"region_key": None, "region_label": None, "count": 1},
            ],
            "facts_by_region_type_status": [
                {"region_key": "hengcheng", "fact_type": "monitoring", "status": "confirmed", "count": 3},
                {"region_key": "hengcheng", "fact_type": "measure", "status": "draft", "count": 1},
                {"region_key": None, "fact_type": "measure", "status": "draft", "count": 2},
            ],
            "templates_by_scope": {"": 5, "regional": 2},
            "task_regions": {"t1": "hengcheng", "t2": "hengcheng", "t3": "yining-beiqu"},
            "templates": [
                {
                    "id": 1,
                    "chapter": "ch9 措施",
                    "scope": "regional",
                    "contributing_task_ids": ["t1", "t3"],
                    "updated_at": "2026-10-06T00:00:00",
                },
                {
                    "id": 2,
                    "chapter": "ch3 现状",
                    "scope": None,
                    "contributing_task_ids": [],
                    "updated_at": "2026-10-07T00:00:00",
                },
            ],
        }


def make_svc() -> DomainFactoryService:
    svc = DomainFactoryService.__new__(DomainFactoryService)  # 跳过 __init__（W3 fake 先例）
    svc.repo = FakeReadRepo()
    return svc


class TestListTasksWithAttribution:
    def test_passthrough_and_clamp(self):
        svc = make_svc()
        res = run(svc.list_tasks_with_attribution(page=0, page_size=500, keyword="横城"))
        assert res["page"] == 1 and res["page_size"] == 100
        assert res["total"] == 1 and len(res["items"]) == 1
        assert svc.repo.calls[-1]["keyword"] == "横城"

    def test_unassigned_passthrough(self):
        svc = make_svc()
        run(svc.list_tasks_with_attribution(scope="unassigned"))
        assert svc.repo.calls[-1]["scope"] == "unassigned"

    def test_invalid_scope_rejected(self):
        svc = make_svc()
        assert run(svc.list_tasks_with_attribution(scope="bogus")).get("error")


class TestListRegionalFacts:
    def test_valid_filters_passthrough(self):
        svc = make_svc()
        res = run(svc.list_regional_facts(region_key="hengcheng", fact_type="measure", status="draft"))
        assert res["total"] == 1
        assert svc.repo.calls[-1] == {
            "region_key": "hengcheng",
            "fact_type": "measure",
            "status": "draft",
            "page": 1,
            "page_size": 20,
        }

    def test_invalid_fact_type_rejected(self):
        svc = make_svc()
        assert run(svc.list_regional_facts(fact_type="bogus")).get("error")

    def test_invalid_status_rejected(self):
        svc = make_svc()
        assert run(svc.list_regional_facts(status="bogus")).get("error")


class TestBuildRegionBoard:
    def test_stats_tree_and_templates(self):
        svc = make_svc()
        board = run(svc.build_region_board())
        s = board["stats"]
        assert s["templates_by_scope"] == {"universal": 0, "regional": 2, "project": 0, "unassigned": 5}
        assert s["facts_by_status"] == {"draft": 3, "confirmed": 3, "retired": 0}
        assert {r["region_key"]: r["count"] for r in s["tasks_by_region"]} == {"hengcheng": 2, None: 1}
        tree = {n["region_key"]: n for n in board["region_tree"]}
        assert tree["hengcheng"]["task_count"] == 2
        assert tree["hengcheng"]["fact_count"] == 4
        assert tree["hengcheng"]["fact_counts_by_type"]["monitoring"] == 3
        assert tree[None]["task_count"] == 1
        assert tree[None]["template_count"] == 1  # 模板2 无归因 → 未归属伪节点
        # mixed 模板（t1+t3 跨 region）进明细但不计入任何树节点
        tpl = {t["id"]: t for t in board["templates"]}
        assert tpl[1]["region"] == "mixed" and tpl[1]["contributing_count"] == 2
        assert tpl[2]["region"] is None
        assert [t for t in board["templates"] if t["region"] == "hengcheng"] == []
        # 明细按 updated_at 倒序
        assert board["templates"][0]["id"] == 2
