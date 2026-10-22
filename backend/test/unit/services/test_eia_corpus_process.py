"""eia_corpus_process 单测：KB 为准选集 / workdir 物化 / 真 bank_compile 迷你重编译 / corpus_meta 合并 / fail fast。

技能 references 以 tmp_path 打桩（绝不触碰真产物）；KB 以 FakeKB 打桩
（list_document_files + get_file_download(variant="parsed")）。stages 夹具对齐
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
        "kb_file_id": None,
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


class FakeKB:
    """stem → (file_id, canonical md)；KB 文档名约定 = <文件库原名 stem>.md。"""

    def __init__(self, docs: dict[str, tuple[str, str]]):
        self.docs = docs

    async def list_document_files(self, kb_id, *, files_only=False, page=1, page_size=500, include_stats=True, **kw):
        items = [
            {"file_id": fid, "filename": f"{stem}.md", "status": "indexed"}
            for stem, (fid, _) in sorted(self.docs.items())
        ]
        return {
            "items": items,
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "parent_id": None,
            "path_prefix": "",
            "recursive": False,
        }

    async def get_file_download(self, kb_id, file_id, variant="original"):
        assert variant == "parsed"
        for stem, (fid, md) in self.docs.items():
            if fid == file_id:
                return {"filename": f"{stem}.md", "content": md.encode("utf-8"), "media_type": "text/markdown"}
        raise ValueError("文件尚未生成解析结果")


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
    stage_doc = json.dumps(
        {"forms": {"effluent": {"fields": [{"label": "化学需氧量", "name": "cod"}]}}}, ensure_ascii=False
    )
    for stage in ("planning_eia", "post_eia", "project_eia_openpit", "project_eia_underground", "tracking_eia"):
        (refs / "stages" / f"{stage}.json").write_text(stage_doc, encoding="utf-8")
    return refs


def _stub_kb_id(monkeypatch, kb_id="kb_x"):
    async def _resolve():
        return kb_id

    monkeypatch.setattr(svc, "_resolve_kb_id", _resolve)


def test_materialize_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "knowledge_base", FakeKB({"样例报告": ("file_1", MINI_CANONICAL_MD)}))
    rows = [{**_make_row(), "kb_file_id": "file_1"}]
    entries = asyncio.run(svc._materialize_workdir(tmp_path / "wd", "kb_x", rows))
    src = tmp_path / "wd" / "001-demo" / "source.md"
    assert src.is_file()
    assert src.read_text(encoding="utf-8").startswith("## 1 概述")  # 仅正文（前置区已剥）
    manifest = json.loads((tmp_path / "wd" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["report_id"] == "001-demo" and manifest[0]["stage"] == "post_eia"
    assert entries == manifest


def test_real_bank_compile_mini_corpus(tmp_path, monkeypatch):
    refs = _seed_refs(tmp_path)
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    monkeypatch.setattr(svc, "knowledge_base", FakeKB({"样例报告": ("file_1", MINI_CANONICAL_MD)}))
    bank = svc._load_bank_compile()
    # build_label_map 抽取共用（P2 联动）：词表页可映射性标注与编译器归并同查此表
    assert bank.build_label_map(refs) == {"化学需氧量": "effluent.cod"}
    wd = tmp_path / "wd"
    assert (
        bank.main_with_args(["--workdir", str(wd), "--references", str(refs), "--prune"]) == 1
    )  # 空 manifest → rc=1 拒绝

    rows = [{**_make_row(), "kb_file_id": "file_1"}]
    asyncio.run(svc._materialize_workdir(wd, "kb_x", rows))
    rc = bank.main_with_args(["--workdir", str(wd), "--references", str(refs), "--prune"])
    assert rc == 0
    # bank_index 形状：{stage: {chN: [{report_id, sec, file: slices/chN/<rid>__<sec>.md}]}}
    index = json.loads((refs / "samples_bank" / "bank_index.json").read_text(encoding="utf-8"))
    assert set(index) == {"post_eia"}
    assert set(index["post_eia"].keys()) == {"ch1", "ch2"}  # 迷你语料两章切片入库
    items = [it for lst in index["post_eia"].values() for it in lst]
    assert {it["report_id"] for it in items} == {"001-demo"}


def test_merge_corpus_meta_converges_to_compile_set(tmp_path, monkeypatch):
    """corpus_meta 随 KB 编译集收敛：新增合并、编译集外残条剔除、集内既有条目不动、幂等。"""
    refs = _seed_refs(tmp_path)
    (refs / "samples_bank").mkdir()
    meta_path = refs / "samples_bank" / "corpus_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "reports": {
                    "001-demo": {"report_title": "既有报告", "stage": "post_eia"},
                    "999-phantom": {"report_title": "换代残留"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    entries = [
        {"report_id": "001-demo", "stage": "post_eia", "mineral": "coal"},
        {"report_id": "002-new", "stage": "post_eia", "mineral": "coal"},
    ]
    svc._merge_corpus_meta(entries, {"001-demo": {}, "002-new": FRONT_META})
    doc = json.loads(meta_path.read_text(encoding="utf-8"))
    assert doc["reports"]["001-demo"]["report_title"] == "既有报告"  # 集内既有条目不动
    assert doc["reports"]["002-new"]["report_title"] == FRONT_META["report_title"]  # 新增合并
    assert doc["reports"]["002-new"]["stage"] == "post_eia"
    assert "999-phantom" not in doc["reports"]  # 编译集外残条剔除（rid 换代/文档删除）
    assert set(doc["reports"]) == {"001-demo", "002-new"}  # 收敛 = 编译集
    # 幂等：重跑不重复改写
    svc._merge_corpus_meta(entries, {"001-demo": {}, "002-new": {}})
    assert (
        json.loads(meta_path.read_text(encoding="utf-8"))["reports"]["002-new"]["report_title"]
        == FRONT_META["report_title"]
    )


def test_process_fails_fast_on_unmatched_kb_doc(monkeypatch):
    """KB 文档缺文件库登记（无法定位 rid/stage）→ fail fast。"""
    monkeypatch.setattr(svc, "_repo", FakeRepo([_make_row()]))
    monkeypatch.setattr(svc, "knowledge_base", FakeKB({"陌生文件": ("file_9", MINI_CANONICAL_MD)}))
    _stub_kb_id(monkeypatch)
    ctx = FakeContext()
    ctx.payload = {"scope": "all", "operator_id": "tester"}
    with pytest.raises(ValueError, match="缺文件库登记"):
        asyncio.run(svc.run_eia_corpus_process(ctx))


def test_process_fails_fast_on_missing_stage(monkeypatch):
    """KB 内文档对应库行 report_id/stage 未填 → fail fast。"""
    repo = FakeRepo([_make_row(stage=None)])
    monkeypatch.setattr(svc, "_repo", repo)
    monkeypatch.setattr(svc, "knowledge_base", FakeKB({"样例报告": ("file_1", MINI_CANONICAL_MD)}))
    _stub_kb_id(monkeypatch)
    ctx = FakeContext()
    ctx.payload = {"scope": "all", "operator_id": "tester"}
    with pytest.raises(ValueError, match="加工前置不满足"):
        asyncio.run(svc.run_eia_corpus_process(ctx))


def test_process_compiles_kb_set_excluding_library_only_rows(tmp_path, monkeypatch):
    """KB 为准：库中就绪但未推送 KB 的文件不入编，台账 library_not_in_kb 可见。"""
    refs = _seed_refs(tmp_path)
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    rows = [
        _make_row(id=1, report_id="001-demo", original_filename="样例报告.docx"),
        _make_row(id=2, report_id="002-unpushed", original_filename="库内新报告.docx"),
    ]
    repo = FakeRepo(rows)
    monkeypatch.setattr(svc, "_repo", repo)
    monkeypatch.setattr(svc, "knowledge_base", FakeKB({"样例报告": ("file_1", MINI_CANONICAL_MD)}))  # 002 不在 KB
    _stub_kb_id(monkeypatch)
    ctx = FakeContext()
    ctx.payload = {"scope": "all", "operator_id": "tester"}
    summary = asyncio.run(svc.run_eia_corpus_process(ctx))
    assert summary == {"compiled": 1}
    detail = repo.logs[0]["detail"]
    assert detail["library_not_in_kb"] == ["002-unpushed"]
    assert detail["kb_id"] == "kb_x"


def test_process_full_run_updates_processed_at_and_logs(tmp_path, monkeypatch):
    refs = _seed_refs(tmp_path)
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    rows = [_make_row()]
    repo = FakeRepo(rows)
    monkeypatch.setattr(svc, "_repo", repo)
    monkeypatch.setattr(svc, "knowledge_base", FakeKB({"样例报告": ("file_1", MINI_CANONICAL_MD)}))
    _stub_kb_id(monkeypatch)
    ctx = FakeContext()
    ctx.payload = {"scope": "all", "operator_id": "tester"}
    summary = asyncio.run(svc.run_eia_corpus_process(ctx))
    assert summary == {"compiled": 1}
    assert repo.updated and repo.updated[0][1].get("processed_at") is not None
    assert repo.logs[0]["action"] == "recompile"
    doc = json.loads((refs / "samples_bank" / "corpus_meta.json").read_text(encoding="utf-8"))
    assert "001-demo" in doc["reports"]  # 闭环：新 rid 已并入 corpus_meta


def test_process_file_ids_scope_only_stamps_processed_at(tmp_path, monkeypatch):
    """scope=file_ids：编译仍为 KB 全集，file_ids 仅圈定 processed_at；集合外 id 报错。"""
    refs = _seed_refs(tmp_path)
    monkeypatch.setattr(svc, "_SKILL_REFS", refs)
    rows = [
        _make_row(id=1, report_id="001-demo", original_filename="样例报告.docx"),
        _make_row(id=2, report_id="002-two", original_filename="第二份报告.docx"),
    ]
    repo = FakeRepo(rows)
    monkeypatch.setattr(svc, "_repo", repo)
    monkeypatch.setattr(
        svc,
        "knowledge_base",
        FakeKB({"样例报告": ("file_1", MINI_CANONICAL_MD), "第二份报告": ("file_2", MINI_CANONICAL_MD)}),
    )
    _stub_kb_id(monkeypatch)
    ctx = FakeContext()
    ctx.payload = {"file_ids": [1], "operator_id": "tester"}
    summary = asyncio.run(svc.run_eia_corpus_process(ctx))
    assert summary == {"compiled": 2}  # 编译恒为 KB 全集
    assert [fid for fid, _ in repo.updated] == [1]  # processed_at 仅登记目标

    ctx.payload = {"file_ids": [99], "operator_id": "tester"}
    with pytest.raises(ValueError, match="不在语料知识库编译集内"):
        asyncio.run(svc.run_eia_corpus_process(ctx))
