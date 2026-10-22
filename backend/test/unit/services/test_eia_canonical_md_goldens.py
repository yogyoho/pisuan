"""金标准回归：canonical md 内核 × 33 份真实语料（宿主机专用，开发机跑）。

三断言（spec 2026-10-18 §3 等价性承诺）：
  ① 标记后正文 == 离线 workdir <rid>/source.md（逐字节）；
  ② extract_front(前置段落) 与技能资产 front_matter.json 同 rid 七字段全等；
  ③ slice_report(正文) 章号集 == bank_index.json 同 rid 章号集。

语料与 workdir 不入 git，路径参数化；缺环境 skip 并显式声明。宿主机运行：
  python -X utf8 -m pytest backend/test/unit/services/test_eia_canonical_md_goldens.py -v
环境变量：EIA_GOLDENS_WORKDIR（缺省 .wolf/corpus-workdir）、EIA_GOLDENS_CORPUS（缺省 C:\\项目管理\\样例文件）
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pisuan.services.eia_canonical_md import (
    docx_bytes_to_canonical_md,
    extract_front,
    slice_report,
    split_canonical_md,
)

_REPO = Path(__file__).resolve().parents[4]
WORKDIR = Path(os.environ.get("EIA_GOLDENS_WORKDIR", _REPO / ".wolf" / "corpus-workdir"))
CORPUS = Path(os.environ.get("EIA_GOLDENS_CORPUS", r"C:\项目管理\样例文件"))
SKILL_REFS = _REPO / "backend" / "package" / "pisuan" / "agents" / "skills" / "buildin" / "coal-eia-writer" / "references"

pytestmark = [
    pytest.mark.skipif(not (WORKDIR / "manifest.json").is_file(), reason=f"金标准 workdir 缺失: {WORKDIR}"),
    pytest.mark.skipif(not CORPUS.is_dir(), reason=f"金标准语料缺失: {CORPUS}"),
]


def _manifest() -> list[dict]:
    return json.loads((WORKDIR / "manifest.json").read_text(encoding="utf-8"))


def _bank_slices_for(bank_index: dict, rid: str, stage: str | None) -> set[str]:
    """bank_index.json（SL3 池 ch<N>__<rid>.md）同 rid 章号集；stage 未知则空集跳过断言。"""
    chs: set[str] = set()
    stage_files = bank_index.get(stage or "", {})
    for _label, items in stage_files.items():
        for item in items:
            fn = item["file"].rsplit("/", 1)[-1]
            tail = fn.removeprefix("ch").split("__", 1)
            if len(tail) == 2 and tail[1].startswith(rid):
                chs.add(tail[0])
    return chs


@pytest.mark.parametrize("entry", _manifest(), ids=lambda e: e["report_id"])
def test_golden_entry(entry):
    rid, fname, stage = entry["report_id"], entry["file_name"], entry.get("stage") or None
    src = CORPUS / fname
    if not src.is_file():
        mirror = WORKDIR / "_mirror_corpus" / fname
        if not mirror.is_file():
            pytest.skip(f"语料缺失: {fname}")
        src = mirror
    cm = docx_bytes_to_canonical_md(src.read_bytes(), label=fname)
    assert cm is not None, f"{rid} 零节号标题"

    # ① 正文逐字节 == workdir source.md
    golden_body = (WORKDIR / rid / "source.md").read_text(encoding="utf-8")
    _, body = split_canonical_md(cm.md)
    assert body == golden_body, f"{rid} 正文漂移"

    # ② extract_front == front_matter.json 同 rid（七字段）
    golden_front = json.loads((SKILL_REFS / "samples_bank" / "front_matter.json").read_text(encoding="utf-8")).get(rid)
    if golden_front is not None:
        f = extract_front(cm.front_paras)
        for field in (
            "report_title",
            "eia_org",
            "eia_org_candidates",
            "year",
            "project_no",
            "cover_scale_mt_a",
            "province",
        ):
            assert f.get(field) == golden_front.get(field), f"{rid}.{field}: {f.get(field)!r} != {golden_front.get(field)!r}"

    # ③ slice_report 章号集 == bank_index.json 同 rid
    golden_index = json.loads((SKILL_REFS / "samples_bank" / "bank_index.json").read_text(encoding="utf-8"))
    expected = _bank_slices_for(golden_index, rid, stage)
    if expected:
        kept, _dup = slice_report(body)
        assert sorted(s["chapter"] for s in kept) == sorted(expected), f"{rid} 章号集漂移"
