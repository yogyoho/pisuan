"""eia_corpus_process 单测：workdir 物化 / 真 bank_compile 迷你重编译 / corpus_meta 合并 / 前置校验 fail fast。

技能 references 以 tmp_path 打桩（绝不触碰真产物）；stages 夹具对齐
bank_compile.SECTION_EXPECTATION_STAGES 的 forms.fields[].label/name 形状。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuxi.services import eia_corpus_task_service as svc

MINI_CANONICAL_MD = (
    "某矿项目环境影响报告书\n\n"
    "<!-- EIA-FRONT-MATTER-END -->\n\n"
    "## 1 概述\n内容甲。\n## 1.1 背景\n内容乙。\n## 2 现状\n内容丙。\n"
)
FRONT_META = {"report_title": "某矿项目环境影响报告书", "year": 2024, "province": "宁夏"}


def _make_row(**kw):
    row = {
        "id": 1,
        "original_filename": "样例报告.docx",
        "md_status": "ready",
        "md_object_key": "eia-library/.canonical/x.md",
        "report_id": "001-demo",
        "stage": "post_eia",
        "mineral": "coal",
        "front_meta": dict(FRONT_META),
    }
    row.update(kw)
    return row


class FakeRepo:
    def __init__(self, rows):
        self.rows = rows
        self.updated: list[tuple[int, dict]] = []
        self.logs: list[dict] = []

    async def list_files(self, **kw):
        return [dict(r) for r in self.rows]

    async def get_file(self, file_id):
        return None

    async def update_file(self, file_id, fields):
        self.updated.append((file_id, dict(fields)))
        return SimpleNamespace(**{**self.rows[0], **fields})

    async def insert_process_log(self, **kw):
        self.logs.append(kw)


class FakeMinIO:
    def __init__(self, body_by_key):
        self.body_by_key = body_by_key

    async def adownload_file(self, bucket, obj):
        return self.body_by_key[obj].encode("utf-8")


class FakeContext:
    payload: dict = {}
    task_id = "t1"
    worker_id = "w1"

    async def raise_if_cancelled(self):
        pass

    async def set_progress(self, pct, msg):
        self.msg = msg

    async def set_result(self, result):
        self.result = result


def _seed_refs(tmp_path: Path) -> Path:
    """stages 夹具须覆盖 bank_compile.SECTION_EXPECTATION_STAGES 全集（--prune 逐 stage 读取）。"""
    refs = tmp_path / "refs"
    (refs / "stages").mkdir(parents=True)
    stage_doc = json.dumps({"forms": {"effluent": {"fields": [{"label": "化学需氧量", "name": "cod"}]}}}, ensure_ascii=False)
    for stage in ("planning_eia", "post_eia", "project_eia_openpit", "project_eia_underground", "tracking_eia"):
        (refs / "stages" / f"{stage}.json").write_text(stage_doc, encoding="utf-8")
    return refs


def test_materialize_workdir(tmp_path):
    rows = [_make_row()]
    client = FakeMinIO({rows[0]["md_object_key"]: MINI_CANONICAL_MD})
    entries = asyncio.run(svc._materialize_workdir(tmp_path / "wd", client, rows))
    src = tmp_path / "wd" / "001-demo" / "source.md"
    assert src.is_file()
    assert src.read_text(encoding="utf-8").startswith("## 1 概述")  # 仅正文（前置区已剥）
    manifest = json.loads((tmp_path / "wd" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["report_id"] == "001-demo" and manifest[0]["stage"] == "post_eia"
    assert entries == manifest


def test_real_bank_compile_mini_corpus(tmp_path, monkeypatch):
    refs = _seed_refs(tmp_path)
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    bank = svc._load_bank_compile()
    wd = tmp_path / "wd"
    assert bank.main_with_args(["--workdir", str(wd), "--references", str(refs), "--prune"]) == 1  # 空 manifest → rc=1 拒绝

    rows = [_make_row()]
    asyncio.run(svc._materialize_workdir(wd, FakeMinIO({rows[0]["md_object_key"]: MINI_CANONICAL_MD}), rows))
    rc = bank.main_with_args(["--workdir", str(wd), "--references", str(refs), "--prune"])
    assert rc == 0
    # bank_index 形状：{stage: {chN: [{report_id, sec, file: slices/chN/<rid>__<sec>.md}]}}
    index = json.loads((refs / "samples_bank" / "bank_index.json").read_text(encoding="utf-8"))
    assert set(index) == {"post_eia"}
    assert set(index["post_eia"].keys()) == {"ch1", "ch2"}  # 迷你语料两章切片入库
    items = [it for lst in index["post_eia"].values() for it in lst]
    assert {it["report_id"] for it in items} == {"001-demo"}


def test_merge_corpus_meta_adds_new_rid_only(tmp_path, monkeypatch):
    refs = _seed_refs(tmp_path)
    (refs / "samples_bank").mkdir()
    meta_path = refs / "samples_bank" / "corpus_meta.json"
    meta_path.write_text(
        json.dumps({"reports": {"001-old": {"report_title": "既有报告", "stage": "post_eia"}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    svc._merge_corpus_meta(
        [{"report_id": "001-demo", "stage": "post_eia", "mineral": "coal"}], {"001-demo": FRONT_META}
    )
    doc = json.loads(meta_path.read_text(encoding="utf-8"))
    assert doc["reports"]["001-old"]["report_title"] == "既有报告"  # 既有条目不动
    new = doc["reports"]["001-demo"]
    assert new["report_title"] == FRONT_META["report_title"]
    assert new["scale_basis"] == "needs_review" and new["stage"] == "post_eia"
    # 幂等：重跑不重复改写
    svc._merge_corpus_meta([{"report_id": "001-demo", "stage": "post_eia", "mineral": "coal"}], {"001-demo": {}})
    assert json.loads(meta_path.read_text(encoding="utf-8"))["reports"]["001-demo"]["report_title"] == FRONT_META["report_title"]


def test_process_fails_fast_on_missing_stage(monkeypatch):
    repo = FakeRepo([_make_row(stage=None)])
    monkeypatch.setattr(svc, "_repo", repo)
    ctx = FakeContext()
    ctx.payload = {"scope": "all", "operator_id": "tester"}
    with pytest.raises(ValueError, match="stage 未填"):
        asyncio.run(svc.run_eia_corpus_process(ctx))


def test_process_full_run_updates_processed_at_and_logs(tmp_path, monkeypatch):
    refs = _seed_refs(tmp_path)
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    rows = [_make_row()]
    repo = FakeRepo(rows)
    monkeypatch.setattr(svc, "_repo", repo)
    monkeypatch.setattr(svc, "get_minio_client", lambda: FakeMinIO({rows[0]["md_object_key"]: MINI_CANONICAL_MD}))
    ctx = FakeContext()
    ctx.payload = {"scope": "all", "operator_id": "tester"}
    summary = asyncio.run(svc.run_eia_corpus_process(ctx))
    assert summary == {"compiled": 1}
    assert repo.updated and repo.updated[0][1].get("processed_at") is not None
    assert repo.logs[0]["action"] == "recompile"
    doc = json.loads((refs / "samples_bank" / "corpus_meta.json").read_text(encoding="utf-8"))
    assert "001-demo" in doc["reports"]  # 闭环：新 rid 已并入 corpus_meta
