"""样例片段包测试（bug-4147）：主导报告选择 / 预算节标题截断 / 空章降级 rc=2 / 确定性。"""

import io
import json
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sample_fragments as sf

BANK = {
    "planning_eia": {
        "ch2": [
            # 报告 A：条目多（章节最完整）→ 主导；多条目指向同一文件（标题级展开语义）
            {"file": "samples_bank/planning_eia/slices/ch2/A__2.md", "report_id": "A", "sec": "2", "title": "章"},
            {"file": "samples_bank/planning_eia/slices/ch2/A__2.md", "report_id": "A", "sec": "2.1", "title": "一"},
            {"file": "samples_bank/planning_eia/slices/ch2/A__2.md", "report_id": "A", "sec": "2.2", "title": "二"},
            {"file": "samples_bank/planning_eia/slices/ch2/A__2.md", "report_id": "A", "sec": "2.3", "title": "三"},
            # 报告 B：条目少
            {"file": "samples_bank/planning_eia/slices/ch2/B__2.md", "report_id": "B", "sec": "2", "title": "章"},
            {"file": "samples_bank/planning_eia/slices/ch2/B__2.md", "report_id": "B", "sec": "2.1", "title": "一"},
        ],
    }
}

LONG_A = (
    "【矿种】coal｜【阶段】planning_eia｜【report_id】A｜【节号】2\n\n"
    "### 2.1 第一节\n"
    + ("甲段叙述句。" * 50)
    + "\n\n### 2.2 第二节\n"
    + ("乙段叙述句。" * 50)
    + "\n\n### 2.3 第三节\n尾段\n"
)


def _refs(tmp: Path, bank=BANK, a_text: str = LONG_A) -> Path:
    refs = tmp / "references"
    d = refs / "samples_bank" / "planning_eia" / "slices" / "ch2"
    d.mkdir(parents=True)
    (d / "A__2.md").write_text(a_text, encoding="utf-8")
    (d / "B__2.md").write_text("【矿种】coal｜【report_id】B\n\n### 2.1 B节\n短文\n", encoding="utf-8")
    (refs / "samples_bank" / "bank_index.json").write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    return refs


def _main(args: Namespace) -> int:
    """复刻 main() 主体（不走 argparse，便于断言 rc）。"""
    try:
        bank = sf.load_bank(Path(args.references_dir))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"SAMPLE_FRAGMENTS_FAIL: {e}", file=sys.stderr)
        return 1
    stage = Path(args.stage).stem  # 容错：--stage 传 stages/<id>.json 路径时取回 id（全脚本口径为路径，裸 id 亦收）
    if stage not in bank:
        print(
            f"SAMPLE_FRAGMENTS_FAIL: stage '{args.stage}'（归一为 '{stage}'）不在样例库（顶层键：{'、'.join(bank)}）",
            file=sys.stderr,
        )
        return 1
    if getattr(args, "per_section", False):
        if getattr(args, "candidates", None) or getattr(args, "content_dir", None):
            print(
                "SAMPLE_FRAGMENTS_FAIL: --per-section 与 --candidates/--content-dir 互斥（候选卡走章级口径）",
                file=sys.stderr,
            )
            return 1
        rid_arg = getattr(args, "report_id", None)
        if rid_arg:
            valid = {
                c["report_id"] for c in sf.pick_candidates(bank, stage, args.chapter, 10**9, Path(args.references_dir))
            }
            if rid_arg not in valid:
                print(f"SAMPLE_FRAGMENTS_FAIL: 候选中无报告 {rid_arg}", file=sys.stderr)
                return 1
        out_dir = getattr(args, "out_dir", None)
        if not out_dir:
            print("SAMPLE_FRAGMENTS_FAIL: --per-section 需 --out-dir（节包落盘目录）", file=sys.stderr)
            return 1
        manifest, rid = sf.build_section_packs(
            bank, stage, args.chapter, args.max_chars, Path(args.references_dir), Path(out_dir), rid_arg
        )
        if not manifest:
            print(f"SAMPLE_FRAGMENTS_EMPTY: {stage}/{args.chapter} 无样例切片或切不出 ### 节", file=sys.stderr)
            return 2
        detail = " ".join(f"{m['sec']}={m['chars']}字" for m in manifest)
        print(f"SAMPLE_FRAGMENTS_PER_SECTION_OK: {len(manifest)} 节 → {out_dir}（{rid}；{detail}）")
        return 0
    if getattr(args, "candidates", None):
        content_dir = getattr(args, "content_dir", None)
        cands, rc = sf.export_candidates(
            bank,
            stage,
            args.chapter,
            args.candidates,
            Path(args.references_dir),
            Path(args.out),
            Path(content_dir) if content_dir else None,
        )
        if rc == 2:
            print(f"SAMPLE_FRAGMENTS_EMPTY: {args.stage}/{args.chapter} 无样例切片", file=sys.stderr)
            return 2
        print(f"SAMPLE_CANDIDATES_OK: {len(cands)} 份候选 → {args.out}")
        return 0
    rid_arg = getattr(args, "report_id", None)
    if rid_arg:
        valid = {
            c["report_id"] for c in sf.pick_candidates(bank, stage, args.chapter, 10**9, Path(args.references_dir))
        }
        if rid_arg not in valid:
            print(f"SAMPLE_FRAGMENTS_FAIL: 候选中无报告 {rid_arg}", file=sys.stderr)
            return 1
    pack, rid, clipped = sf.build_pack(bank, stage, args.chapter, args.max_chars, Path(args.references_dir), rid_arg)
    if not pack:
        print(f"SAMPLE_FRAGMENTS_EMPTY: {stage}/{args.chapter} 无样例切片", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pack, encoding="utf-8", newline="\n")
    print(f"SAMPLE_FRAGMENTS_OK: {out}（主导报告 {rid} · {len(pack)} 字符）")
    return 0


def _run(
    tmp: Path,
    refs: Path,
    tag: str = "x",
    max_chars: int = 12000,
    chapter: str = "ch2",
    candidates: int | None = None,
    report_id: str | None = None,
    stage: str = "planning_eia",
    per_section: bool = False,
    out_dir: str | None = None,
) -> tuple[int, Path, str]:
    out = tmp / (f"cands_{tag}.json" if candidates else f"pack_{tag}.md")
    args = Namespace(
        references_dir=str(refs),
        stage=stage,
        chapter=chapter,
        out=str(out),
        max_chars=max_chars,
        candidates=candidates,
        report_id=report_id,
        per_section=per_section,
        out_dir=out_dir,
    )
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
        code = _main(args)
    return code, out, err.getvalue()


def test_dominant_report_and_dedupe(tmp_path):
    refs = _refs(tmp_path)
    rc, out, _ = _run(tmp_path, refs, tag="dom")
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "report_id】A" in text and "B节" not in text  # 取主导报告 A
    assert "主导报告 A" in text.split("\n")[1]  # 包头注释标注来源


def test_budget_clip_at_heading_boundary(tmp_path):
    refs = _refs(tmp_path)
    rc, out, _ = _run(tmp_path, refs, tag="clip", max_chars=400)
    assert rc == 0
    body = out.read_text(encoding="utf-8").split("\n", 2)[2]  # 去掉两行包头
    assert len(body) <= 400
    assert "### 2.1 第一节" in body and "乙段" not in body and "### 2.3 第三节" not in body  # 预算内最后节标题处收口


def test_whole_file_under_budget_verbatim(tmp_path):
    refs = _refs(tmp_path)
    rc, out, _ = _run(tmp_path, refs, tag="full", max_chars=10**6)
    text = out.read_text(encoding="utf-8")
    assert LONG_A.strip() in text and "截断" not in text.split("\n")[1]


def test_empty_chapter_rc2(tmp_path):
    refs = _refs(tmp_path)
    rc, _, err = _run(tmp_path, refs, tag="empty", chapter="ch99")
    assert rc == 2 and "无样例切片" in err
    assert not (tmp_path / "pack_empty.md").exists()


def test_deterministic_bytes(tmp_path):
    refs = _refs(tmp_path)
    rc1, out1, _ = _run(tmp_path, refs, tag="d1")
    rc2, out2, _ = _run(tmp_path, refs, tag="d2")
    assert rc1 == rc2 == 0
    assert out1.read_bytes() == out2.read_bytes()


def test_missing_bank_rc1(tmp_path):
    rc, _, err = _run(tmp_path, tmp_path / "nope", tag="nobank")
    assert rc == 1 and "bank_index 缺失" in err


def test_candidates_sorted_deterministic(tmp_path):
    """范例挑选卡数据面：条目数降序主导在前；sections/chars 如实；字节确定。"""
    refs = _refs(tmp_path)
    rc, out, _ = _run(tmp_path, refs, tag="c1", candidates=3)
    assert rc == 0
    cands = json.loads(out.read_text(encoding="utf-8"))
    assert [c["report_id"] for c in cands] == ["A", "B"]  # 条目数 4>2 降序
    # 覆盖节数=节级口径（### 级真节）：A 的 secs {2,2.1,2.2,2.3}——2 被扩展=章题，真节 3；B 只 2.1 一节
    assert cands[0]["sections"] == 3 and cands[1]["sections"] == 1
    assert cands[0]["chars"] == len(LONG_A.strip())
    rc2, out2, _ = _run(tmp_path, refs, tag="c2", candidates=3)
    assert out.read_bytes() == out2.read_bytes()


def test_candidates_top_n_truncates(tmp_path):
    refs = _refs(tmp_path)
    rc, out, _ = _run(tmp_path, refs, tag="top1", candidates=1)
    cands = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0 and len(cands) == 1 and cands[0]["report_id"] == "A"


def test_candidates_empty_rc2(tmp_path):
    rc, out, err = _run(tmp_path, _refs(tmp_path), tag="ce", candidates=3, chapter="ch99")
    assert rc == 2 and "无样例切片" in err and not out.exists()


def test_candidates_content_export(tmp_path):
    """卡B 内容面：--content-dir 逐份导出整章原文，候选 JSON 增记 content_file 路径（用户点开预览通读比对）。"""
    refs = _refs(tmp_path)
    out = tmp_path / "state" / "candidates_ch2.json"
    content_dir = tmp_path / "state" / "candidates_content_ch2"
    cands, rc = sf.export_candidates(sf.load_bank(refs), "planning_eia", "ch2", 3, refs, out, content_dir)
    assert rc == 0 and len(cands) == 2
    f1 = Path(cands[0]["content_file"])
    assert f1.exists() and "甲段叙述句" in f1.read_text(encoding="utf-8")
    assert "范例候选1" in f1.read_text(encoding="utf-8")
    f2 = Path(cands[1]["content_file"])
    assert f2.exists() and "B节" in f2.read_text(encoding="utf-8")
    recorded = json.loads(out.read_text(encoding="utf-8"))
    assert [Path(c["content_file"]).name for c in recorded] == [
        "candidate-1-A.md",
        "candidate-2-B.md",
    ]


def test_candidates_no_content_dir_unchanged(tmp_path):
    """不传 --content-dir 时行为与旧版一致（纯摘要 JSON，无 content_file 键）。"""
    refs = _refs(tmp_path)
    out = tmp_path / "state" / "candidates_ch2.json"
    cands, rc = sf.export_candidates(sf.load_bank(refs), "planning_eia", "ch2", 3, refs, out, None)
    assert rc == 0 and all("content_file" not in c for c in cands)


def test_report_id_pick_and_unknown_rc1(tmp_path):
    """用户选定取件：--report-id B 取 B 切片；候选外 id rc=1。"""
    refs = _refs(tmp_path)
    rc, out, _ = _run(tmp_path, refs, tag="pickB", report_id="B")
    assert rc == 0 and "report_id】B" in out.read_text(encoding="utf-8")
    rc2, _, err = _run(tmp_path, refs, tag="pickZ", report_id="ZZZ")
    assert rc2 == 1 and "候选中无报告 ZZZ" in err


def test_stage_path_normalized_to_id(tmp_path):
    """bug-4154：--stage 传 stages/*.json 路径（全脚本口径）自动取回 id 命中样例库——此前路径被当 id 查找，误判库空。"""
    refs = _refs(tmp_path)
    rc, out, _ = _run(
        tmp_path, refs, tag="spath", candidates=3, stage="/skills/coal-eia-writer/references/stages/planning_eia.json"
    )
    assert rc == 0
    cands = json.loads(out.read_text(encoding="utf-8"))
    assert [c["report_id"] for c in cands] == ["A", "B"]


def test_unknown_stage_rc1_not_empty(tmp_path):
    """未知 stage 是参数错误 rc=1（带顶层键提示），不得与「库空」rc=2 混同。"""
    rc, out, err = _run(tmp_path, _refs(tmp_path), tag="badstage", candidates=3, stage="planning_eia_rev")
    assert rc == 1 and "不在样例库" in err and "planning_eia" in err  # 提示里列出合法顶层键
    assert not out.exists()


# ------------------------------------------------- --per-section 节级切包（P1-5）

FULL_A = (
    "【矿种】coal｜【阶段】planning_eia｜【report_id】A｜【节号】2\n\n"
    "## 2 工程分析章\n\n"
    "章头引言段。\n\n"
    "### 2.1 第一节\n"
    "#### 2.1.1 小节甲\n甲小节正文。\n"
    "#### 2.1.2 小节乙\n乙小节正文。\n\n"
    "### 2.2 第二节\n乙段叙述句。\n\n"
    "### 2.3 第三节\n尾段\n"
)


def _refs_full(tmp: Path) -> Path:
    """带章题行/#### 子节的规范切片 fixture。"""
    refs = tmp / "references"
    d = refs / "samples_bank" / "planning_eia" / "slices" / "ch2"
    d.mkdir(parents=True)
    (d / "A__2.md").write_text(FULL_A, encoding="utf-8")
    (d / "B__2.md").write_text("【矿种】coal｜【report_id】B\n\n### 2.1 B节\n短文\n", encoding="utf-8")
    (refs / "samples_bank" / "bank_index.json").write_text(json.dumps(BANK, ensure_ascii=False), encoding="utf-8")
    return refs


def test_split_sections_merges_duplicates():
    """切节：### 级定界、#### 子节随节；同节号重复按文档序并包；章题行单独提取。"""
    text = "## 2 章\n\n### 2.1 一\n甲\n\n#### 2.1.1 子\n子文\n\n### 2.2 二\n乙\n\n### 2.1 又一\n丙\n"
    chapter_line, secs = sf.split_sections(text)
    assert chapter_line == "## 2 章"
    assert [s for s, _ in secs] == ["2.1", "2.2"]  # 同节号并包不新增
    merged = dict(secs)["2.1"]
    assert "#### 2.1.1 子" in merged and "甲" in merged and "丙" in merged  # 文档序并包
    assert "乙" not in merged  # 节间不串


def test_per_section_writes_packs(tmp_path):
    """节包逐节落盘 <节号>.md：包头红线注释+章题行上下文+节文本；stdout 列节号字数映射。"""
    refs = _refs_full(tmp_path)
    out_dir = tmp_path / "state" / "fragment_packs" / "ch2"
    rc, _, _ = _run(tmp_path, refs, tag="ps", per_section=True, out_dir=str(out_dir))
    assert rc == 0
    assert (out_dir / "2.1.md").exists() and (out_dir / "2.2.md").exists() and (out_dir / "2.3.md").exists()
    p22 = (out_dir / "2.2.md").read_text(encoding="utf-8")
    assert "§2.2" in p22 and "## 2 工程分析章" in p22  # 包头 + 章题行上下文
    assert "乙段叙述句" in p22 and "甲小节正文" not in p22 and "尾段" not in p22  # 只含本节
    p21 = (out_dir / "2.1.md").read_text(encoding="utf-8")
    assert "#### 2.1.1 小节甲" in p21 and "#### 2.1.2 小节乙" in p21  # 子节随节
    assert "禁抄数值/实体入正文" in p21  # 红线注释随包头
    # stdout 列节号字数映射（控制器派发时按此取对应节包）
    buf = io.StringIO()
    with redirect_stdout(buf):
        _main(
            Namespace(
                references_dir=str(refs),
                stage="planning_eia",
                chapter="ch2",
                out=str(tmp_path / "unused.md"),
                max_chars=12000,
                candidates=None,
                report_id=None,
                per_section=True,
                out_dir=str(tmp_path / "stdout_run"),
            )
        )
    assert "PER_SECTION_OK" in buf.getvalue() and "2.1=" in buf.getvalue() and "2.3=" in buf.getvalue()


def test_per_section_budget_clip_per_sec(tmp_path):
    """预算按节独立截断：超预算节在 #### 小节标题处收口并注记，未超预算节全文。"""
    refs = _refs_full(tmp_path)
    out_dir = tmp_path / "state" / "fragment_packs" / "ch2"
    rc, _, _ = _run(tmp_path, refs, tag="psclip", per_section=True, out_dir=str(out_dir), max_chars=40)
    assert rc == 0
    p21 = (out_dir / "2.1.md").read_text(encoding="utf-8")
    assert "截断自" in p21 and "#### 2.1.2" not in p21  # 预算内最后小节标题处收口
    p23 = (out_dir / "2.3.md").read_text(encoding="utf-8")
    assert "尾段" in p23 and "截断" not in p23  # 未超预算节全文


def test_per_section_report_id_pick(tmp_path):
    """节包同样支持选定报告：--report-id B 取 B 切片切节；溯源行在首个 ### 前不随节（包头注释已带 rid）。"""
    refs = _refs_full(tmp_path)
    out_dir = tmp_path / "state" / "fragment_packs" / "ch2"
    rc, _, _ = _run(tmp_path, refs, tag="psb", per_section=True, out_dir=str(out_dir), report_id="B")
    assert rc == 0
    p21 = (out_dir / "2.1.md").read_text(encoding="utf-8")
    assert "选定报告 B" in p21 and "B节" in p21  # B 切片 + 包头标注选定
    assert "甲小节正文" not in p21  # 不串 A 的内容


def test_per_section_no_heading_rc2(tmp_path):
    """切片无 ### 节标题（薄 stage/脏切片）→ rc=2 节级降级用章包，不落任何文件。"""
    refs = tmp_path / "references"
    d = refs / "samples_bank" / "planning_eia" / "slices" / "ch2"
    d.mkdir(parents=True)
    (d / "A__2.md").write_text("## 2 章\n\n只有章头引言，无节标题。\n", encoding="utf-8")
    (refs / "samples_bank" / "bank_index.json").write_text(json.dumps(BANK, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "state" / "fragment_packs" / "ch2"
    rc, _, err = _run(tmp_path, refs, tag="psnoh", per_section=True, out_dir=str(out_dir))
    assert rc == 2 and "切不出" in err
    assert not out_dir.exists()


def test_per_section_arg_conflicts_rc1(tmp_path):
    """参数错误 rc=1：与 --candidates/--content-dir 互斥；缺 --out-dir。"""
    refs = _refs_full(tmp_path)
    rc, _, err = _run(tmp_path, refs, tag="psc1", candidates=3, per_section=True, out_dir=str(tmp_path / "d1"))
    assert rc == 1 and "互斥" in err
    rc2, _, err2 = _run(tmp_path, refs, tag="psc2", per_section=True)
    assert rc2 == 1 and "--out-dir" in err2


def test_per_section_deterministic_bytes(tmp_path):
    refs = _refs_full(tmp_path)
    d1 = tmp_path / "f1"
    d2 = tmp_path / "f2"
    rc1, _, _ = _run(tmp_path, refs, tag="pd1", per_section=True, out_dir=str(d1))
    rc2, _, _ = _run(tmp_path, refs, tag="pd2", per_section=True, out_dir=str(d2))
    assert rc1 == rc2 == 0
    for f in sorted(d1.iterdir()):
        assert f.read_bytes() == (d2 / f.name).read_bytes(), f.name
