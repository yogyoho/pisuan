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
    assert cands[0]["sections"] == 4 and cands[0]["chars"] == len(LONG_A.strip())
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
