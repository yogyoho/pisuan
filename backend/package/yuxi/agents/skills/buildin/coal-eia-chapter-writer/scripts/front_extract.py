#!/usr/bin/env python3
"""front_extract.py — 语料封面/前置区元数据抽取器（spec 2026-10-16-corpus-meta-pipeline-refactor）。

输入：<语料目录>/*.docx（stdlib zipfile+XML 只读；docx 不入 git，sha1 记录出处）。
输出：<references>/samples_bank/front_matter.json（幂等 sort_keys）+ workdir 排除日志。
rid 推导：按目录全量排序位复算 prepare_corpus.make_rid（含被排除文件）——与切片入库
逐字符一致；体裁门（复垦/监测报告/水土保持）与 --exclude 去重门在 rid 计算之后应用。
用法：python -X utf8 front_extract.py --corpus-dir <dir> [--references <dir>] [--exclude <文件名>]… [--workdir <dir>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from prepare_corpus import make_rid  # noqa: E402  rid 单一事实源，绝不复制实现

# 前置区边界：首个节号标题（与 prepare_corpus 范围裁剪同一判据）
SEC_HEAD_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*\S|\S)\s*$")
PARA_RE = re.compile(r"<w:p[ >].*?</w:p>", re.S)
TEXT_RE = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")
SPACE_RE = re.compile(r"[\s　]+")

TITLE_TAIL_RE = re.compile(r"(环境影响报告书|环境影响报告表|环境影响跟踪评价报告书|环境影响后评价报告书|环评报告书)$")
BACK_JOIN_BLOCK_RE = re.compile(r"[：:年月]|^\d")
ORG_LABEL_RE = re.compile(r"^(?:环评|编制|评价)单位[：:]")
ORG_NAME_RE = re.compile(r"(有限公司|研究院|设计院|评估中心|科学研究院|勘查院|集团公司)")
ORG_NOISE_RE = re.compile(r"(项目|矿井|矿区|报告|选煤厂|煤矿$)")
DATE_RE = re.compile(r"[〇零一二三四五六七八九]{4}年(?:[一二三四五六七八九十]{1,3}月)?|\d{4}年(?:\d{1,2}月)?")
PROJECT_NO_RE = re.compile(r"工程编号[：:](\S+)")
SCALE_LINE_RE = re.compile(r"^(?:矿区)?(?:开发)?总规模[：:](\d+(?:\.\d+)?)Mt?/?a?$")
GENRE_RE = re.compile(r"(复垦|监测报告|水土保持)")
_CJK_DIGITS = str.maketrans(
    {
        "〇": "0",
        "零": "0",
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
    }
)
PROVINCES = (
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 "
    "山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆"
).split()
PROVINCES_BY_LEN = sorted(PROVINCES, key=len, reverse=True)


def _parse_year(fragment: str) -> int | None:
    digits = re.sub(r"\D", "", fragment.translate(_CJK_DIGITS))
    if len(digits) < 4:
        return None
    y = int(digits[:4])
    return y if 2000 <= y <= 2100 else None


def read_front_paras(docx_path: Path, cap: int = 300) -> list[str]:
    """首个节号标题之前的全部非空段落（封面+扉页+签署页；空白归一）。"""
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    paras: list[str] = []
    for pa in PARA_RE.findall(xml):
        raw = "".join(TEXT_RE.findall(pa))
        t = SPACE_RE.sub("", raw)
        if not t:
            continue
        if SEC_HEAD_RE.match(raw.strip()):  # 判界用归一前原文（SPACE 归一会杀死 \s+ 判据）
            break
        paras.append(t)
        if len(paras) >= cap:
            break
    return paras


def extract_front(paras: list[str]) -> dict:
    paras = [p for p in (SPACE_RE.sub("", x) for x in paras) if p]  # 归一与 read_front_paras 同规（全角空格变体）
    title = org_labeled = year = project_no = cover_scale = None
    org_candidates: list[str] = []
    for i, s in enumerate(paras):
        if title is None and len(s) <= 45 and TITLE_TAIL_RE.search(s):
            back: list[str] = []
            for j in range(i - 1, max(-1, i - 4), -1):
                if len(paras[j]) <= 50 and not BACK_JOIN_BLOCK_RE.search(paras[j]):
                    back.insert(0, paras[j])
                else:
                    break
            title = "".join(back) + s
        if year is None and (m := DATE_RE.search(s)):
            year = _parse_year(m.group())
        if project_no is None and (m := PROJECT_NO_RE.search(s)):
            project_no = m.group(1)
        if cover_scale is None and (m := SCALE_LINE_RE.match(s)):
            cover_scale = round(float(m.group(1)), 2)
        if ORG_LABEL_RE.match(s):
            val = ORG_LABEL_RE.sub("", s)
            if val and len(val) <= 50:
                if org_labeled is None:
                    org_labeled = val
                elif val not in org_candidates:
                    org_candidates.append(val)
        elif ORG_NAME_RE.search(s) and not ORG_NOISE_RE.search(s) and len(s) < 50:
            bare = re.sub(r"^(?:建设|环评|编制|评价)单位[：:]", "", s)
            if bare not in org_candidates:
                org_candidates.append(bare)
    org_candidates = [c for c in org_candidates if c != org_labeled][:5]
    province = None
    if title:
        province = next((p for p in PROVINCES_BY_LEN if p in title), None)
    if province is None:
        for s in paras[:6]:
            province = next((p for p in PROVINCES_BY_LEN if s.startswith(p)), None)
            if province:
                break
    return {
        "report_title": title,
        "eia_org": org_labeled,
        "eia_org_candidates": org_candidates,
        "year": year,
        "project_no": project_no,
        "cover_scale_mt_a": cover_scale,
        "province": province,
    }


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="封面/前置区元数据抽取（front_matter.json，幂等）")
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--references", default=str(SCRIPTS_DIR.parent / "references"))
    ap.add_argument("--exclude", action="append", default=[], help="排除文件名（可重复）——重复副本门")
    ap.add_argument("--workdir", default=None, help="排除日志输出目录；省略时仅 stderr")
    args = ap.parse_args(argv)
    corpus = Path(args.corpus_dir)
    refs = Path(args.references)
    excludes = set(args.exclude)
    entries: dict[str, dict] = {}
    excluded: list[dict] = []
    docxs = [p for p in sorted(corpus.glob("*.docx")) if not p.name.startswith("~$")]  # Office 属主锁不占排序位
    for seq, docx in enumerate(docxs, start=1):
        rid = make_rid(seq, docx.stem)  # 全量排序位——两门在 rid 之后应用（spec §4 约束）
        if GENRE_RE.search(docx.name):
            excluded.append({"file": docx.name, "rid": rid, "reason": "genre"})
            print(f"[front_extract] {docx.name} -> {rid} 非环评体裁——排除", file=sys.stderr)
            continue
        if docx.name in excludes:
            excluded.append({"file": docx.name, "rid": rid, "reason": "duplicate"})
            print(f"[front_extract] {docx.name} -> {rid} 重复副本——排除", file=sys.stderr)
            continue
        try:
            f = extract_front(read_front_paras(docx))
        except Exception as exc:  # noqa: BLE001
            print(f"[front_extract] {docx.name} 读取失败——跳过：{exc}", file=sys.stderr)
            continue
        entries[rid] = {"source_file": docx.name, "source_sha1": hashlib.sha1(docx.read_bytes()).hexdigest(), **f}
        print(
            f"[front_extract] {docx.name} -> {rid}"
            f"（title={'有' if f['report_title'] else '无'} year={f['year']} org={'有' if f['eia_org'] else '无'}）"
        )
    out = refs / "samples_bank" / "front_matter.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(entries, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    if args.workdir:
        log_path = Path(args.workdir) / "front_extract_excluded.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(excluded, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"FRONT_EXTRACT: {len(entries)} report(s) -> {out}；排除 {len(excluded)}")
    return 0 if entries else 1


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
