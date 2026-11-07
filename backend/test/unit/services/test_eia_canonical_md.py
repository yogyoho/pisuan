"""canonical md 内核单测（合成 docx 夹具，不依赖真实语料）。

内核模块 pisuan.services.eia_canonical_md 的行为守护：
正文/前置边界/目录剔除/标题升级/表格前置段/零节号返回 None/extract_front/slice_report/make_rid。
金标准回归（33 份真实语料）在宿主机 test_eia_canonical_md_goldens.py，不入容器门禁。
"""

from __future__ import annotations

import io

import pytest
from docx import Document

from pisuan.services.eia_canonical_md import (
    FRONT_MARKER,
    docx_bytes_to_canonical_md,
    extract_front,
    make_rid,
    slice_report,
    split_canonical_md,
)


def _docx_bytes(
    cover: list[str], toc: list[str], body: list[str], table: list[list[str]] | None = None
) -> bytes:
    """合成 docx：封面段 + 可选封面表格 + 目录行（≥3 触发剔除）+ 正文节号标题段。

    表格须位于目录行之前——目录行「1 概述\t1」本身匹配 SEC_LINE_RE，RAW 前置段
    采集在其处截断（与真实语料同构：封面表格先于任何节号行）。"""
    doc = Document()
    for t in cover:
        doc.add_paragraph(t)
    if table is not None:
        tbl = doc.add_table(rows=len(table), cols=len(table[0]))
        for i, row in enumerate(table):
            for j, cell in enumerate(row):
                tbl.rows[i].cells[j].text = cell
    for t in toc:
        doc.add_paragraph(t)
    for t in body:
        doc.add_paragraph(t)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


COVER = ["某煤矿矿井及选煤厂项目", "环境影响报告书", "工程编号：H95011-2-BG", "二〇二四年三月"]
TOC = ["1 概述\t1", "2 场址与地质\t5", "3 环境影响分析\t12"]
BODY = ["1 概述", "项目背景与内容。", "2.1 地质特征", "构造简单。", "3.2.1 与《宁夏十四五规划》的符合性分析", "符合。"]


def test_canonical_md_body_marker_and_toc_strip():
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY), label="t.docx")
    assert cm is not None
    front, body = split_canonical_md(cm.md)
    assert FRONT_MARKER in cm.md
    assert not any("\t1" in ln or "\t5" in ln for ln in body)  # 目录区段已剔
    assert body.startswith("## 1 概述")  # 首个节号标题起为正文（单段号 → ##）
    assert cm.md.endswith("\n")
    assert "某煤矿矿井及选煤厂项目" in "\n".join(front)  # 封面保留为前置区


def test_canonical_md_heading_promotion_and_policy_exempt():
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY), label="t.docx")
    _, body = split_canonical_md(cm.md)
    assert "### 2.1 地质特征" in body  # 两段号 → ###
    # 书名号符合性分析节豁免超长上限（题名 >30 字仍升级）
    assert "#### 3.2.1 与《宁夏十四五规划》的符合性分析" in body


def test_canonical_md_front_paras_raw_and_table_cells():
    table = [["建设单位", "某矿业有限公司"], ["编制单位", "某环科院"]]
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY, table), label="t.docx")
    assert "某煤矿矿井及选煤厂项目" in cm.front_paras
    assert "某矿业有限公司" in cm.front_paras  # 封面表格单元段进入 RAW 前置段
    assert len(cm.front_paras) <= 300  # cap=300 与 read_front_paras 同构


def test_canonical_md_zero_heading_returns_none():
    cm = docx_bytes_to_canonical_md(_docx_bytes(["只有封面没有正文"], [], []), label="t.docx")
    assert cm is None


def test_extract_front_from_raw_paras():
    cm = docx_bytes_to_canonical_md(_docx_bytes(COVER, TOC, BODY), label="t.docx")
    f = extract_front(cm.front_paras)
    assert f["project_no"] == "H95011-2-BG"
    assert f["year"] == 2024
    assert f["report_title"].endswith("环境影响报告书")


def test_slice_report_merges_subsections():
    text = "# 1 概述\n甲。\n## 1.1 背景\n乙。\n## 2 现状\n丙。\n"
    kept, dup = slice_report(text)
    assert [s["chapter"] for s in kept] == ["1", "2"]
    assert "## 1.1 背景" in kept[0]["seg"]  # 子节归父片
    assert dup == []


def test_make_rid_ascii_slug_and_fallback():
    assert make_rid(1, "plain-stem") == "001-plain-stem"
    assert make_rid(2, "纯中文名") == "002-r"
    assert make_rid(3, "a" * 100) == "003-" + "a" * 56  # 截断到 60 字符
