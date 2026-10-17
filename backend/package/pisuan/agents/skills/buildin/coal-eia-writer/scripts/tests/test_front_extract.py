"""front_extract 测试：docx 前置区五字段 / rid 全量排序位复算 / 体裁与去重门 / 幂等
（spec 2026-10-16-corpus-meta-pipeline-refactor）。stdlib-only，docx 用内联 zip 构造。"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import front_extract as fx  # noqa: E402
from prepare_corpus import make_rid  # noqa: E402


def _docx_bytes(paras: list[str | list[str]]) -> bytes:
    def runs(p: str | list[str]) -> str:
        parts = p if isinstance(p, list) else [p]
        return "".join(f"<w:r><w:t>{t}</w:t></w:r>" for t in parts)

    body = "".join(f"<w:p>{runs(p)}</w:p>" for p in paras)
    xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


# ── 字段抽取 ────────────────────────────────────────────────────────────────


def test_extract_three_segment_title():
    paras = ["甘肃省", "灵台矿区总体规划（修编）", "环境影响报告书", "二〇二五年六月", "目录", "1 总论"]
    f = fx.extract_front(paras)
    assert f["report_title"] == "甘肃省灵台矿区总体规划（修编）环境影响报告书"
    assert f["province"] == "甘肃"


def test_title_missing_is_none_and_basis_input():
    f = fx.extract_front(["某文件", "1 总论"])
    assert f["report_title"] is None


def test_labeled_org_wins_and_bare_names_are_candidates():
    paras = [
        "（WPS）月儿湾矿井及选煤厂",
        "环境影响报告书",
        "环评单位：中煤科工集团北京华宇工程有限公司",
        "建设单位：宁夏通达新能源集团有限公司",
    ]
    f = fx.extract_front(paras)
    assert f["eia_org"] == "中煤科工集团北京华宇工程有限公司"
    assert "宁夏通达新能源集团有限公司" in f["eia_org_candidates"]


def test_year_cjk_and_arabic():
    assert fx.extract_front(["二〇二五年六月", "1 总论"])["year"] == 2025
    assert fx.extract_front(["2024年4月", "1 总论"])["year"] == 2024
    assert fx.extract_front(["一九九九年", "1 总论"])["year"] is None  # 越界守卫


def test_project_no_normalizes_spaces():
    f = fx.extract_front(["工　程　编　号：H75041Z", "1 总论"])
    assert f["project_no"] == "H75041Z"


def test_cover_scale_variants():
    assert fx.extract_front(["矿区开发总规模：21.40 Mt/a", "1 总论"])["cover_scale_mt_a"] == 21.4
    assert fx.extract_front(["总规模：9.20Mt/a", "1 总论"])["cover_scale_mt_a"] == 9.2
    assert fx.extract_front(["结论：矿区开发总规模为 21.40 Mt/a。", "1 总论"])["cover_scale_mt_a"] is None


def test_province_falls_back_to_first_para():
    paras = ["新疆", "某矿区总体规划", "环境影响报告书", "1 总论"]
    f = fx.extract_front(paras)
    # 标题「某矿区总体规划环境影响报告书」无省名 → 首段省名开头兜底
    assert f["province"] == "新疆"


# ── rid 门与幂等 ────────────────────────────────────────────────────────────


def test_read_front_paras_stops_at_sec_heading(tmp_path: Path):
    docx = tmp_path / "1某报告.docx"
    docx.write_bytes(_docx_bytes(["某矿区总体规划", "环境影响报告书", "1 总论", "2024年4月", "某公司"]))
    assert fx.read_front_paras(docx) == ["某矿区总体规划", "环境影响报告书"]


def test_scale_read_across_split_runs(tmp_path: Path):
    docx = tmp_path / "1某报告.docx"
    docx.write_bytes(_docx_bytes([["矿区开发总规模：", "21.40", " Mt/a"], "1 总论"]))
    assert fx.extract_front(fx.read_front_paras(docx))["cover_scale_mt_a"] == 21.4


def test_gates_and_rid_parity(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    names = {
        "1四季屯矿山地质环境保护与土地复垦方案报告书.docx": ["封面", "1 总论"],  # 体裁门
        "2某矿区总体规划环境影响报告书.docx": ["封面", "2 某矿区"],  # 保留
        "3某报告旧版.docx": ["封面", "3 某报告"],  # 去重门
    }
    for name, paras in names.items():
        (corpus / name).write_bytes(_docx_bytes(paras))
    refs = tmp_path / "refs"
    wd = tmp_path / "wd"
    argv = [
        "--corpus-dir",
        str(corpus),
        "--references",
        str(refs),
        "--exclude",
        "3某报告旧版.docx",
        "--workdir",
        str(wd),
    ]
    assert fx.main_with_args(argv) == 0
    out = json.loads((refs / "samples_bank" / "front_matter.json").read_text(encoding="utf-8"))
    assert list(out) == [make_rid(2, "2某矿区总体规划环境影响报告书")]
    log = json.loads((wd / "front_extract_excluded.json").read_text(encoding="utf-8"))
    assert {e["reason"] for e in log} == {"genre", "duplicate"}
    assert log[0]["rid"] == make_rid(1, "1四季屯矿山地质环境保护与土地复垦方案报告书")
    assert (
        out[make_rid(2, "2某矿区总体规划环境影响报告书")]["source_sha1"]
        == hashlib.sha1((corpus / "2某矿区总体规划环境影响报告书.docx").read_bytes()).hexdigest()
    )


def test_idempotent_rerun_same_bytes(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "1某矿区总体规划环境影响报告书.docx").write_bytes(
        _docx_bytes(["甘肃省", "某矿区总体规划", "环境影响报告书", "二〇二五年六月", "1 总论"])
    )
    refs = tmp_path / "refs"
    argv = ["--corpus-dir", str(corpus), "--references", str(refs)]
    fx.main_with_args(argv)
    b1 = (refs / "samples_bank" / "front_matter.json").read_bytes()
    fx.main_with_args(argv)
    assert (refs / "samples_bank" / "front_matter.json").read_bytes() == b1


def test_office_lock_files_do_not_consume_positions(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "~$某报告.docx").write_bytes(b"not a docx")  # Office 属主锁：占目录不占位
    # 真文件名以中文开头（真实语料形态：~$ 排在中文前，计位漂移只发生在中文名文件上）
    (corpus / "某矿区总体规划环境影响报告书.docx").write_bytes(
        _docx_bytes(["甘肃省", "某矿区总体规划", "环境影响报告书", "1 总论"])
    )
    refs = tmp_path / "refs"
    assert fx.main_with_args(["--corpus-dir", str(corpus), "--references", str(refs)]) == 0
    out = json.loads((refs / "samples_bank" / "front_matter.json").read_text(encoding="utf-8"))
    assert list(out) == [make_rid(1, "某矿区总体规划环境影响报告书")]
