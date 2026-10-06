# W3 facts 写入流/级联聚合单测（fake repo，无 DB）。容器道同 test_w3_region_rules.py 头注。
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import DomainFactoryService  # noqa: E402


class FakeTaskRow:
    def __init__(self, task_id="t1", region_key=None, scope=None):
        self.id = task_id
        self.region_key = region_key
        self.scope = scope
        self.file_name = "横城矿区总体规划（修编）环评.docx"
        self.document_type = "通用"
        self.report_type_code = "通用"


class FakeRepo:
    def __init__(self):
        self.task = FakeTaskRow()
        self.facts: list[dict] = []
        self.templates: dict[int, dict] = {}
        self.task_updates: list[dict] = []
        self.retired = 0

    async def get_task(self, task_id):
        return self.task if self.task.id == task_id else None

    async def update_task(self, task_id, data):
        self.task_updates.append({"task_id": task_id, **data})
        for k, v in data.items():
            setattr(self.task, k, v)
        return self.task

    async def insert_regional_fact(self, **kw):
        for f in self.facts:
            if f["source_task_id"] == kw["source_task_id"] and f["entity_key"] == kw["entity_key"]:
                return "skipped"
        self.facts.append(kw)
        return "created"

    async def confirm_facts_for_task(self, task_id, region_key):
        return len(self.facts)

    async def retire_regional_facts(self, ids):
        self.retired = len(ids)
        return len(ids)

    async def get_learned_templates_by_ids(self, ids):
        # 同构真实 repo 契约：返回行含 id 键
        return [dict(self.templates[i], id=i) for i in ids if i in self.templates]

    async def get_learned_templates_by_contributing_task(self, task_id):
        return [
            dict(t, id=tid)
            for tid, t in self.templates.items()
            if task_id in (t.get("extra_meta", {}).get("contributing_task_ids") or [])
        ]

    async def get_task_scopes(self, task_ids):
        return {tid: (self.task.scope if tid == self.task.id else None) for tid in task_ids}

    async def update_learned_template_scope(self, template_id, scope, extra_meta):
        self.templates[template_id]["scope"] = scope
        self.templates[template_id]["extra_meta"] = extra_meta


def make_svc_with(repo) -> DomainFactoryService:
    svc = DomainFactoryService.__new__(DomainFactoryService)
    svc.repo = repo
    return svc


class TestFactsForEntity:
    def test_b_class_creates_draft(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        status = asyncio.run(
            svc._insert_facts_for_entity(
                "t1", repo.task,
                {"entity_key": "st_x", "name_cn": "某居民点", "category": "sensitive_target",
                 "description": "距工业场地 500m", "source_ref": "para-3"},
            )
        )
        assert status == "created"
        fact = repo.facts[0]
        assert fact["fact_type"] == "sensitive_target"
        assert fact["region_key"] is None  # 任务未归属 → 未归属事实（靠 source_task_id 追补）
        assert fact["source_task_id"] == "t1"
        assert fact["entity_key"] == "st_x"
        assert "某居民点" in fact["content"]

    def test_c_class_rejected(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        status = asyncio.run(
            svc._insert_facts_for_entity(
                "t1", repo.task,
                {"entity_key": "pb_1", "name_cn": "矿井产能", "category": "project_basic", "description": "500万t/a"},
            )
        )
        assert status == "not_b_class"
        assert repo.facts == []

    def test_measures_split_constraint_keyword(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        status = asyncio.run(
            svc._insert_facts_for_entity(
                "t1", repo.task,
                {"entity_key": "mr_1", "name_cn": "排放标准", "category": "measures_regulation",
                 "description": "执行标准限值"},
            )
        )
        assert status == "created"
        assert repo.facts[0]["fact_type"] == "constraint"

    def test_dedup_via_repo_key(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        entity = {"entity_key": "st_x", "name_cn": "某居民点", "category": "sensitive_target", "description": "d"}
        assert asyncio.run(svc._insert_facts_for_entity("t1", repo.task, entity)) == "created"
        assert asyncio.run(svc._insert_facts_for_entity("t1", repo.task, entity)) == "skipped"
        assert len(repo.facts) == 1


class TestConfirmRegionCascade:
    def test_cascade_three_steps(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        repo.templates[11] = {"scope": "universal", "extra_meta": {"contributing_task_ids": ["t1"]}}
        result = asyncio.run(svc.confirm_region("t1", "横城矿区", None, "regional"))
        assert "error" not in result
        # 步骤1：任务列落定
        assert repo.task_updates[0]["region_key"] == "hengcheng"
        assert repo.task_updates[0]["scope"] == "regional"
        # 步骤2：facts 确认（fake 返回行数）
        assert result["facts_confirmed"] == len(repo.facts)
        # 步骤3：归因集模板重算——universal + regional 证据 → 降级 regional
        assert result["templates_recalculated"] >= 1
        assert repo.templates[11]["scope"] == "regional"
        assert "t1" in repo.templates[11]["extra_meta"]["contributing_task_ids"]

    def test_region_key_fallback_to_vocab(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("t1", "横城矿区", None, None))
        assert result["region_key"] == "hengcheng"

    def test_unregistered_region_requires_key(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("t1", "未知矿区", None, "regional"))
        assert "error" in result

    def test_invalid_scope_rejected(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("t1", "横城矿区", "hengcheng", "world"))
        assert "error" in result

    def test_task_not_found(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("nope", "横城矿区", "hengcheng", "regional"))
        assert "error" in result


class TestRetire:
    def test_retire_passthrough(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        assert asyncio.run(svc.retire_regional_facts([1, 2, 3])) == 3
        assert repo.retired == 3


class TestAggregationPure:
    def test_aggregate_writes_scope_and_meta(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        repo.task.scope = "project"
        repo.templates[21] = {"scope": None, "extra_meta": {}}
        updated = asyncio.run(svc._aggregate_template_scopes([21], "t1"))
        assert updated == 1
        assert repo.templates[21]["scope"] == "project"
        assert repo.templates[21]["extra_meta"]["contributing_task_ids"] == ["t1"]

    def test_never_upgrades_on_reaggregate(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        repo.templates[22] = {"scope": "project", "extra_meta": {"contributing_task_ids": ["t1"]}}
        asyncio.run(svc._aggregate_template_scopes([22], "t1"))
        assert repo.templates[22]["scope"] == "project"  # 证据空/弱都不升级
