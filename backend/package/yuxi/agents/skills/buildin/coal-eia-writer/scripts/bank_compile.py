#!/usr/bin/env python3
"""bank_compile.py — 样例库 → 技能衍生物的确定性编译器（geo-sample-bank 核心）。

EAI-CUSTOM (geo-sample-bank Phase 2 T5)：维护者离线动作脚本，把模块后端（geo_samples）
备好的脱敏报告语料编译进技能 references/ 的五处衍生物：
  1. 切片库   <refs>/samples_bank/<stage>/slices/ch<N>/<rid>__<N>.md（带溯源标记行）
  2. SL3 指纹池 <refs>/samples/<stage>/ch<N>__<rid>.md（裸切片文本，落同层即自动扩容
     consistency.check_sl3 的非递归 glob 指纹池；绝不放整本 source.md）
  3. bank_index <refs>/samples_bank/bank_index.json（stage → chN → 节条目索引）
  4. per 矿种深度基线 <refs>/depth_targets/<stage>/<mineral>.json——按 (stage, mineral)
     分组，组内切片临时命名为 chN_<rid>.md 后子进程调 sibling calibrate.py 聚中位数，
     成功后读回加 absolute_floor 落盘；某组 rc!=0 仅跳过该组并 stderr 警告。
  5. stage 级深度门 <refs>/depth_targets/<stage>.json——组间聚合（各矿种
     median_eff × coefficient 取中位，见 _aggregate_depth_targets），
     覆盖手维 stage 级文件（calibrate 复算替换手维值为既定语义）。
  6. forms_catalog <refs>/paradigms/forms_catalog.json——切片文本「表引导句」三形态
     统计（complete_sentence/standalone_caption/dangling，dangling 即 bug-394
     句中嵌表残句）+ 数值引用统计与例句池（spec §4.1），写手正样本。
  7. section_expectations <refs>/section_expectations/<stage>.json——节级数值-口径
     清单（spec §4.2）：两段号节内抽「量词+数值+单位」→ forms label 归并 field 路径，
     corpus_freq=报告覆盖率定 tier；未命中进 unmapped 池；per stage 文件（sections
     键 chN_Snn 跨 stage 碰撞，不能单文件合并）。

约束与语义：
  - 纯 stdlib + 子进程调 sibling calibrate.py；无网络；不 import build_output/ingest/consistency。
  - 维护者动作：输入缺失/全部报告零切片或被跳过 → 立即失败（绝不产空 bank_index）。
  - 退出码：0 = 至少一片并完成编译；1 = 输入缺失/manifest 非法/全部报告零切片或被跳过
    （source.md 缺失/非 UTF-8/无节号标题/重复章号/rid 非 slug——逐条 stderr 警告）。
  - 幂等：全部产物 sort_keys + newline="\\n" 确定性写——同输入必同字节。
  - 切片规则 SEC_RE = ^#{2,4}\\s+\\d+(?:\\.\\d+)*\\s（MULTILINE）：子节归父片
    （### 2.1 属 ## 2 片），节号首段为片号；片起点=标题行 start，终点=下一不同片
    标题的 start 或文末，标题行本身保留在片内。节号须与标题文本空格分隔
    （`## 2 标题`；`## 2.标题` 句点分隔不识别——上游解析器不产此形态，明确不做）。
  - 同一报告内重复章号（如 ## 1 … ## 2.1 … ## 1 … 切出两个 ch1 片）→ 整份报告跳过，
    绝不静默覆盖丢数据。
  - 恢复配方：文档移除/重编译后残留切片会继续进 SL3 指纹池——用 --prune 清理
    （只删命名合规 `<rid>__<N>.md` / `chN__<rid>.md` 但 rid 已不在当前 manifest 的文件；
    手写 chN_sample.md 无 __ 分隔、天然不匹配，绝不动）。

用法（模块后端 T7 调用）：
    python -X utf8 bank_compile.py --workdir <语料目录> --references <技能 references 目录>
    # workdir 下：<report_id>/source.md（脱敏全文）+ manifest.json：
    #   [{"report_id","stage","mineral","file_name"}]（stage/mineral 为 slug，模块侧直读可信）
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
CALIBRATE = SCRIPTS_DIR / "calibrate.py"
ABSOLUTE_FLOOR = 0.4  # 深度门硬下限，标定成功后统一补进基线 doc

# 节号标题：##/###/#### + 空白 + 数字节号 + 空白（MULTILINE 逐行锚定行首）
SEC_RE = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\s", re.MULTILINE)
# 编译产物命名（--prune 据此辨认「本管线产物」：手写 chN_sample.md 无 __ 分隔，天然不匹配）
SLICE_NAME_RE = re.compile(r"^(?P<rid>.+)__(?P<ch>\d+)\.md$")  # samples_bank: <rid>__<N>.md
SL3_NAME_RE = re.compile(r"^ch(?P<ch>\d+)__(?P<rid>.+)\.md$")  # samples: chN__<rid>.md
RID_RE = re.compile(r"[a-z0-9][a-z0-9\-_]*")  # rid slug 守卫（小写字母/数字/-/_）
# forms_catalog 形态统计：表题行（本管线 docx→md 不保留粗体；编号实测两形态——
# 全局号「表 N-M」271 行、章内号「表 N.M-M」7698 行为主流）与「X为 数值 单位」引用句；
# 表锚=GFM 表块首行（8584 块）
CAPTION_LINE_RE = re.compile(r"^\*{0,2}[表图]\s*\d+(?:\.\d+)*[-–—]\d+(?:\.\d+)*")
NUM_UNIT_SENT_RE = re.compile(r"([一-鿿A-Za-z]{2,12})为\s*(\d+(?:\.\d+)?)\s*([一-鿿A-Za-zμ/%°·()（）A-Z]{1,8})")
# section_expectations（spec §4.2）：「量词+为/达/是+数值+单位」句式，单位白名单限数值型
# 环评常用量纲（区别于 forms_catalog 的 NUM_UNIT_SENT_RE 宽口径）；含 NFKC 归一形
# （prepare_corpus 全文 NFKC，²→3→2 数字化：语料实为 km2/m2，不带 km² 会被 km 短路）
QUANTITY_RE = re.compile(
    r"([一-鿿]{2,8}?)(?:为|达|是)\s*(\d+(?:\.\d+)?)\s*"
    r"(dB\(A\)|mg/L|μg/m3|μg/m³|km2|km²|km|hm2|hm²|万m3|万m³|万t|万kW|%|m2|m²|t|d|m)"
)
SECTION_EXPECTATION_STAGES = (
    "planning_eia",
    "post_eia",
    "project_eia_openpit",
    "project_eia_underground",
    "tracking_eia",
)  # label_map 先到先得序
# 数值区间护栏（P5-P95，写前对账 warn 级）：只对强度/浓度类单位发布——extensive 量
# （km2/万t/万m3…）随产能走，scale 归一前置未熟（31 份中 scale 已知 4 份），
# 原始跨项目分布是噪声；发布门槛 distinct-rid≥5（小样本 P5/P95≈min/max 无意义）。
RANGE_UNITS = frozenset({"dB(A)", "mg/L", "μg/m3", "μg/m³", "%"})
RANGE_MIN_REPORTS = 5


def _json_write(path: Path, doc) -> None:
    """确定性 JSON 落盘：sort_keys + 末尾换行 + 强制 \\n（Windows 字节级幂等）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def _heading_title(line: str) -> str:
    """从标题行剥掉井号前缀与节号，余下文本即节标题（如 `## 2 地质特征` → `地质特征`）。"""
    no_hash = re.sub(r"^#{1,6}\s+", "", line)
    return re.sub(r"^\d+(?:\.\d+)*\s+", "", no_hash).strip()


def slice_report(text: str) -> tuple[list[dict], list[str]]:
    """把报告全文切成片：连续同片号的节归并进同一片（子节归父片）。

    返回 ([{chapter, seg, secs}], dup_chapters)：chapter=节号首段，seg=裸切片文本
    （起点=片首标题行 start，终点=下一保留片标题 start 或文末），secs=片内节条目
    [{sec, title}]（sec 为完整节号，如 2.1）；dup_chapters=发生同章多块的章号
    （已按「保留最长块」消解，见下）。无节号标题 → ([], [])。

    重复章号消解（2026-10-08 裁决）：同章多块保留 seg 最长的块——coal 语料的局部
    编号序列（附录计算步骤、保护煤柱清单）是几行碎片，真章是宏观段；被弃块的正文
    经「下一保留块起点」重算并入前块 seg，不丢内容；调用方对 dup 章号告警，绝不静默。
    """
    matches = list(SEC_RE.finditer(text))
    if not matches:
        return [], []
    slices: list[dict] = []
    cur: dict | None = None
    for m in matches:
        sec = m.group(2)
        chapter = sec.split(".")[0]
        if cur is None or cur["chapter"] != chapter:
            if cur is not None:
                slices.append(cur)
            cur = {"chapter": chapter, "start": m.start(), "secs": []}
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line = text[m.start() : line_end].rstrip("\r")
        cur["secs"].append({"sec": sec, "title": _heading_title(line)})
    if cur is not None:
        slices.append(cur)
    for i, s in enumerate(slices):
        s["end"] = slices[i + 1]["start"] if i + 1 < len(slices) else len(text)
    by_ch: dict[str, list[dict]] = {}
    for s in slices:
        by_ch.setdefault(s["chapter"], []).append(s)
    dup = sorted(ch for ch, blocks in by_ch.items() if len(blocks) > 1)
    kept = [
        blocks[0] if len(blocks) == 1 else max(blocks, key=lambda s: s["end"] - s["start"]) for blocks in by_ch.values()
    ]
    kept.sort(key=lambda s: s["start"])
    for i, s in enumerate(kept):
        end = kept[i + 1]["start"] if i + 1 < len(kept) else len(text)
        s["seg"] = text[s["start"] : end]
        del s["start"]
        del s["end"]
    return kept, dup


def classify_table_lead(prev_line: str) -> str:
    """表题行前一非空行形态：complete_sentence（句末收束）/ standalone_caption（表题行相邻）/
    dangling（残句——bug-394 形态）。"""
    s = prev_line.strip()
    if CAPTION_LINE_RE.match(s) or s.startswith("|"):
        return "standalone_caption"
    if not s:
        return "empty"
    if s.endswith(("。", "：", "；", "！", "？", "」", "）")):
        return "complete_sentence"
    return "dangling"


def build_forms_catalog(seg_samples) -> dict:
    """三形态统计+例句池（spec §4.1）。seg_samples: [(rid, seg_text)]。

    锚点=GFM 表块首行（语料 8584 表/31 报告实测；题注正则仅作 prev 归类用）。

    幂等：产物无时间戳（对齐 calibrate.py 先例与模块 docstring 幂等声明），同输入必同字节。"""
    from collections import Counter

    lead_counter: Counter = Counter()
    lead_examples: list[dict] = []
    num_counter: Counter = Counter()
    num_examples: list[dict] = []
    for rid, seg in seg_samples:
        lines = seg.splitlines()
        for i, ln in enumerate(lines):
            # 锚点=GFM 表块首行（每表恰测一次）：前一非空行即「表引导」候选
            # （题注行作 prev 交给 classify 判 standalone_caption，粗体/裸两形态通吃）
            if ln.startswith("|") and (i == 0 or not lines[i - 1].startswith("|")):
                prev = next((lines[j].strip() for j in range(i - 1, -1, -1) if lines[j].strip()), "")
                if prev:
                    form = classify_table_lead(prev)
                    lead_counter[form] += 1
                    # 例句池按形态配额（各 20）：文档序前 40 填充会被主导形态灌满，
                    # 池子必须同时给写手两种引导句的正样本
                    if form in ("complete_sentence", "dangling") and lead_counter[form] <= 20:
                        lead_examples.append({"report_id": rid, "form": form, "text": prev[:80]})
        for m in NUM_UNIT_SENT_RE.finditer(seg):
            num_counter["exact_with_unit"] += 1
            if len(num_examples) < 40:
                num_examples.append({"report_id": rid, "text": m.group(0)[:60]})
    total_lead = sum(lead_counter.values()) or 1
    total_num = sum(num_counter.values()) or 1
    return {
        "version": "1.0",
        "source": f"corpus slices statistics ({len(seg_samples)} report(s))",
        "forms": {
            "table_lead": {
                "desc": "表题行前一非空行形态（31 份实测：独立题注行为主形态，引导句 complete/dangling 各为正样本）",
                "stats": {
                    k: round(lead_counter.get(k, 0) / total_lead, 3)
                    for k in ("complete_sentence", "colon_lead", "standalone_caption", "dangling")
                },
                "templates": ["……{主题}如下表所列。", "……{主题}详见表 {ch}-{seq}。", "……{主题}："],
                "examples": lead_examples,
            },
            "numeric_citation": {
                "desc": "数值引用形态（exact_with_unit 为主形态；dangling 残句零容忍）",
                "stats": {k: round(num_counter.get(k, 0) / total_num, 3) for k in ("exact_with_unit",)},
                "templates": ["{量}为 {value} {unit}。", "……介于 {v1}～{v2} {unit} 之间。"],
                "examples": num_examples,
            },
            "caliber_disambiguation": {
                "desc": "同标签多值消歧写法（v1 从「按…计/按…口径」句式抽取；templates 固化推荐写法）",
                "stats": {},
                "templates": ["按{口径A}为 {v1}，按{口径B}为 {v2}。", "…（{口径}）…"],
                "examples": [],
            },
        },
    }


def extract_sec_texts(seg: str) -> dict[str, str]:
    """切片内按 SEC_RE 切真节文本：只取两段号（章.节），span 至下一个两段号或片尾。

    三段号+（子节）内容随 span 折叠进父节（子节文本语义上属于所在节正文）；
    单段号（章标题行）跳过——章引言量极少，深度门管章级，此处只做节级。"""
    spans = [(m.group(2), m.start()) for m in SEC_RE.finditer(seg) if m.group(2).count(".") == 1]
    return {
        sec: seg[start : (spans[i + 1][1] if i + 1 < len(spans) else len(seg))] for i, (sec, start) in enumerate(spans)
    }


def _map_caliber(label: str, forms_label_map: dict) -> tuple[str, str] | None:
    """语境名词 → forms field 归并：后缀滚动匹配（「主要声源源强」→「源强」）。

    惰性量词从左锚定会捕获带修饰语的全短语，forms label 是短词——依次试后缀
    （含全串，≥2 字），首个命中即归并；全未命中返回 None（进 unmapped 池）。"""
    for i in range(len(label) - 1):
        tail = label[i:]
        if tail in forms_label_map:
            return tail, forms_label_map[tail]
    return None


def _pctl(vals: list[float], q: float) -> float:
    """线性插值分位数（numpy 默认法）：pos=(n-1)q，相邻秩插值；输入无序、返回 4 位舍入。"""
    s = sorted(vals)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 4)


def build_section_expectations(seg_infos, forms_label_map: dict, stage: str) -> dict:
    """节级数值-口径清单（spec §4.2）。seg_infos: [{rid, chapter, sec, title, text}]。

    corpus_freq=报告覆盖率（提及该 caliber 的报告数/该节报告总数，distinct-rid——
    单报告多次提及不抬高频率）；tier：required ≥0.6 / optional 0.2-0.6 / contextual
    <0.2。field 归并走 forms_label_map 精确匹配，未命中进 unmapped 池（cap 200，
    spec：不静默丢弃）。幂等：产物无时间戳（Task 6 裁决），sections 键数值序排列。"""
    from collections import defaultdict

    sec_reports: dict[tuple, set] = defaultdict(set)  # (chapter, sec) -> rids
    sec_titles: dict[tuple, str] = {}
    sec_label_rids: dict[tuple, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    sec_label_unit: dict[tuple, dict[str, str]] = defaultdict(dict)  # 首见单位
    sec_label_values: dict[tuple, dict[str, dict[str, list[float]]]] = {}  # (key,caliber,unit)->数值
    unmapped: list[dict] = []
    for si in seg_infos:
        key = (si["chapter"], si["sec"])
        sec_reports[key].add(si["rid"])
        sec_titles.setdefault(key, si["title"])
        for m in QUANTITY_RE.finditer(si["text"]):
            label, unit = m.group(1), m.group(3)
            mapped = _map_caliber(label, forms_label_map)
            if mapped:
                caliber, field = mapped
                sec_label_rids[key][caliber].add(si["rid"])
                sec_label_unit[key].setdefault(caliber, unit)
                sec_label_values.setdefault(key, {}).setdefault(caliber, {}).setdefault(unit, []).append(
                    float(m.group(2))
                )
            elif len(unmapped) < 200:
                unmapped.append(
                    {
                        "section": f"ch{si['chapter']}",
                        "caliber": label,
                        "value": m.group(2),
                        "unit": unit,
                        "sample": si["rid"],
                    }
                )
    sections: dict[str, dict] = {}
    for key in sorted(sec_reports, key=lambda k: (int(k[0]), tuple(int(p) for p in k[1].split(".")))):
        ch, sec = key
        n = len(sec_reports[key])
        quants = []
        for caliber, rids in sec_label_rids[key].items():
            freq = len(rids) / n
            unit = sec_label_unit[key][caliber]
            q = {
                "field": forms_label_map[caliber],
                "caliber": caliber,
                "unit": unit,
                "tier": "required" if freq >= 0.6 else ("optional" if freq >= 0.2 else "contextual"),
                "corpus_freq": round(freq, 2),
            }
            # 区间只发布给强度/浓度类单位且 distinct-rid 达门槛；n_reports=提及报告数、
            # n_values=首见单位的值数（跨单位混入不计入同一分布）
            vals = sec_label_values.get(key, {}).get(caliber, {}).get(unit, [])
            if unit in RANGE_UNITS and len(rids) >= RANGE_MIN_REPORTS and vals:
                q["range"] = {
                    "p5": _pctl(vals, 0.05),
                    "p50": _pctl(vals, 0.5),
                    "p95": _pctl(vals, 0.95),
                    "n_values": len(vals),
                    "n_reports": len(rids),
                }
            quants.append(q)
        quants.sort(key=lambda q: -q["corpus_freq"])
        sections[f"ch{ch}_S{sec.split('.')[-1]:0>2}"] = {"title": sec_titles[key], "expected_quantities": quants}
    return {"version": "1.1", "stage_scope": stage, "sections": sections, "unmapped": unmapped}


def _run_calibrate(python: str, samples_dir: Path, output: Path) -> tuple[int, str]:
    """子进程调 sibling calibrate.py（脚本目录自动进 sys.path[0]，cwd 无关）。

    坏解释器等启动失败（OSError）→ 返回 (-1, 异常文本)，走既有「该组跳过+stderr 警告」路径。
    """
    try:
        proc = subprocess.run(
            [python, "-X", "utf8", str(CALIBRATE), "--samples-dir", str(samples_dir), "--output", str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return -1, str(exc)
    return proc.returncode, (proc.stderr or "").strip()


def _aggregate_depth_targets(refs: Path, stage: str) -> int | None:
    """per 矿种基线 → depth_targets/<stage>.json（门形状 chapters.{ch}.floor_chars）。

    floor_chars = 组间 median(median_eff × coefficient)——「基线」取组间中位，
    单章缺失矿种不参与该章统计；产物形状与手维版兼容（门零改动）。
    返回章数；无有效矿种基线（目录缺失/空/全损坏）→ stderr 告警并返回 None，
    不落盘——调用方据此不打印 AGGREGATED（不虚报）。"""
    mineral_dir = refs / "depth_targets" / stage
    docs, names = [], []
    for p in sorted(mineral_dir.glob("*.json")):
        try:
            docs.append(json.loads(p.read_text(encoding="utf-8")))
            names.append(p.name)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[bank_compile] 聚合跳过损坏文件 {p.name}: {exc}", file=sys.stderr)
    if not docs:
        print(f"[bank_compile] {stage} 聚合跳过：无有效矿种基线", file=sys.stderr)
        return None
    chapters: dict[str, dict] = {}
    all_chs = sorted({ch for d in docs for ch in d.get("per_chapter", {})})
    for ch in all_chs:
        floors = [d["per_chapter"][ch]["median_eff"] * d["coefficient"] for d in docs if ch in d.get("per_chapter", {})]
        chapters[ch] = {"floor_chars": int(statistics.median(floors))}
    doc = {
        "stage": stage,
        "confidence": "calibrated",
        "source": f"bank_compile aggregate: {', '.join(names)}",
        "chapters": chapters,
    }
    _json_write(refs / "depth_targets" / f"{stage}.json", doc)
    return len(chapters)


def _prune_stale_slices(refs: Path, keep_rids: set[str]) -> int:
    """删除命名合规但 rid 已不在当前 manifest 的残留切片（samples_bank + SL3 指纹池）。

    手写 chN_sample.md 无 __ 分隔、不匹配命名正则，绝不动；返回删除文件数。
    """
    removed = 0
    candidates = list(refs.glob("samples_bank/*/slices/*/*.md")) + list(refs.glob("samples/*/*.md"))
    for p in candidates:
        m = SLICE_NAME_RE.match(p.name) or SL3_NAME_RE.match(p.name)
        if m and m.group("rid") not in keep_rids:
            p.unlink()
            removed += 1
    return removed


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="样例库 → 技能衍生物（slices/SL3 指纹/bank_index/per 矿种基线）确定性编译")
    ap.add_argument("--workdir", required=True, help="语料目录：<report_id>/source.md + manifest.json")
    ap.add_argument("--references", required=True, help="技能 references 目录")
    ap.add_argument("--python", default=sys.executable, help="调 calibrate.py 用的解释器（默认当前解释器）")
    ap.add_argument(
        "--prune",
        action="store_true",
        help="删除 rid 已不在当前 manifest 的残留切片（含 SL3 指纹池）；手写 chN_sample.md 不受影响",
    )
    args = ap.parse_args(argv)

    workdir, refs = Path(args.workdir), Path(args.references)
    manifest_path = workdir / "manifest.json"
    if not manifest_path.is_file():
        print(f"[bank_compile] manifest 缺失：{manifest_path}", file=sys.stderr)
        return 1
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[bank_compile] manifest 不可读/非法 JSON：{exc}", file=sys.stderr)
        return 1
    if not isinstance(entries, list):
        print("[bank_compile] manifest 必须是对象数组", file=sys.stderr)
        return 1

    # 按 report_id 去重（首次出现胜出）——manifest 重复行不产生重复切片/索引条目
    seen: set[str] = set()
    manifest_rids: set[str] = set()
    reports = []
    for e in entries:
        rid = e.get("report_id") if isinstance(e, dict) else None
        if not rid or rid in seen:
            continue
        seen.add(rid)
        manifest_rids.add(rid)
        reports.append(e)

    index: dict = {}  # stage -> chN -> [节条目]
    groups: dict[tuple[str, str], list] = {}  # (stage, mineral) -> [(chapter, rid, seg)]
    text_map: dict[str, str] = {}  # rid -> 全文（切片成功路径记录，forms_catalog 统计输入）
    infos_by_stage: dict[str, list] = {}  # stage -> [{rid, chapter, sec, title, text}]（section_expectations 输入）
    total_slices = 0

    for e in reports:
        rid = e["report_id"]
        stage, mineral = e.get("stage") or "", e.get("mineral") or ""
        if not RID_RE.fullmatch(rid):
            print(f"[bank_compile] {rid} 非 slug（需 [a-z0-9][a-z0-9-_]*）——跳过", file=sys.stderr)
            continue
        src = workdir / rid / "source.md"
        if not stage or not mineral or not src.is_file():
            print(f"[bank_compile] {rid} 缺 stage/mineral 或 source.md 不存在——跳过", file=sys.stderr)
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(f"[bank_compile] {rid} source.md 非 UTF-8（{exc}）——跳过", file=sys.stderr)
            continue
        slices, dup = slice_report(text)
        if not slices:
            print(f"[bank_compile] {rid} 零切片（source.md 无节号标题）——跳过", file=sys.stderr)
            continue
        text_map[rid] = text
        if dup:
            # 2026-10-08 裁决：整份跳过会使 31/31 coal 报告不可编译（局部编号序列
            # 是体裁内在结构），改为 slice_report 内保留最长块；此处告警留痕，绝不静默
            print(
                f"[bank_compile] {rid} 重复章号 {'/'.join(dup)}——保留最长块消解，弃置碎片并入前块 seg", file=sys.stderr
            )
        for s in slices:
            chapter, seg, secs = s["chapter"], s["seg"], s["secs"]
            total_slices += 1
            # 1) 切片库：带溯源标记行
            bank_dir = refs / "samples_bank" / stage / "slices" / f"ch{chapter}"
            bank_dir.mkdir(parents=True, exist_ok=True)
            marker = f"【矿种】{mineral}｜【阶段】{stage}｜【report_id】{rid}｜【节号】{chapter}\n\n"
            (bank_dir / f"{rid}__{chapter}.md").write_text(marker + seg, encoding="utf-8", newline="\n")
            # 2) SL3 指纹池：裸切片文本（同层自动扩容 check_sl3 非递归 glob）
            sl3_dir = refs / "samples" / stage
            sl3_dir.mkdir(parents=True, exist_ok=True)
            (sl3_dir / f"ch{chapter}__{rid}.md").write_text(seg, encoding="utf-8", newline="\n")
            # 3) 索引条目 + 4) 标定分组
            ch_key = f"ch{chapter}"
            for item in secs:
                index.setdefault(stage, {}).setdefault(ch_key, []).append(
                    {
                        "report_id": rid,
                        "mineral": mineral,
                        "sec": item["sec"],
                        "title": item["title"],
                        "file": f"samples_bank/{stage}/slices/{ch_key}/{rid}__{chapter}.md",
                    }
                )
            groups.setdefault((stage, mineral), []).append((chapter, rid, seg))
            # 5) section_expectations 输入：两段号节文本（子节折叠进父节，spec §4.2）
            sec_title = {item["sec"]: item["title"] for item in secs}
            for sec, sec_text in extract_sec_texts(seg).items():
                infos_by_stage.setdefault(stage, []).append(
                    {"rid": rid, "chapter": chapter, "sec": sec, "title": sec_title.get(sec, ""), "text": sec_text}
                )

    if total_slices == 0:
        print("[bank_compile] 全部报告零切片或被跳过——拒绝生成空 bank_index", file=sys.stderr)
        return 1

    _json_write(refs / "samples_bank" / "bank_index.json", index)
    if args.prune:
        pruned = _prune_stale_slices(refs, manifest_rids)
        print(f"PRUNED: {pruned} stale slice(s)")
    # 6) forms_catalog：切片文本三形态统计（表引导句 + 数值引用），给写手正样本
    catalog = build_forms_catalog(
        [(e["report_id"], text_map[e["report_id"]]) for e in reports if e["report_id"] in text_map]
    )
    _json_write(refs / "paradigms" / "forms_catalog.json", catalog)
    tl = catalog["forms"]["table_lead"]["stats"]
    print(
        f"FORMS_CATALOG: {len(catalog['forms']['table_lead']['examples'])} lead example(s), "
        f"table_lead={tl.get('complete_sentence', 0)}/{tl.get('dangling', 0)}(complete/dangling)"
    )
    # 7) section_expectations：节级数值-口径清单（spec §4.2，per stage 文件——
    #    sections 键 chN_Snn 跨 stage 碰撞，不能单文件合并）
    label_map: dict[str, str] = {}
    for st in SECTION_EXPECTATION_STAGES:
        stage_doc = json.loads((refs / "stages" / f"{st}.json").read_text(encoding="utf-8"))
        for fam, fam_spec in stage_doc["forms"].items():
            for f in fam_spec.get("fields", []):
                label_map.setdefault(f["label"], f"{fam}.{f['name']}")  # 跨 stage 重名先到先得
    for st, infos in sorted(infos_by_stage.items()):
        exp_doc = build_section_expectations(infos, label_map, stage=st)
        _json_write(refs / "section_expectations" / f"{st}.json", exp_doc)
        n_q = sum(len(s["expected_quantities"]) for s in exp_doc["sections"].values())
        n_r = sum(1 for s in exp_doc["sections"].values() for q in s["expected_quantities"] if "range" in q)
        print(
            f"SECTION_EXPECTATIONS {st}: {len(exp_doc['sections'])} section(s), "
            f"{n_q} mapped quantity(ies), {n_r} range(s), {len(exp_doc['unmapped'])} unmapped"
        )
    print(f"BANK_COMPILED: {len(reports)} report(s), {total_slices} slice(s), {len(groups)} group(s)")

    # 4) per (stage, mineral) 标定：组内切片临时命名 chN_<rid>.md（满足 calibrate FNAME_RE
    #    ^ch(\d+)，同章多份自动聚 median——正是 per 矿种标定语义）；rc!=0 仅跳过该组。
    for (stage, mineral), items in sorted(groups.items()):
        with tempfile.TemporaryDirectory(prefix="bank_cal_") as td:
            tdir = Path(td)
            for chapter, rid, seg in items:
                (tdir / f"ch{chapter}_{rid}.md").write_text(seg, encoding="utf-8", newline="\n")
            out = refs / "depth_targets" / stage / f"{mineral}.json"
            out.parent.mkdir(parents=True, exist_ok=True)  # calibrate 不建父目录，须先备好
            rc, err = _run_calibrate(args.python, tdir, out)
            if rc != 0:
                print(f"[bank_compile] 标定失败 {stage}/{mineral}（rc={rc}），该组跳过：{err}", file=sys.stderr)
                continue
            doc = json.loads(out.read_text(encoding="utf-8"))
            doc["absolute_floor"] = ABSOLUTE_FLOOR
            _json_write(out, doc)
            print(f"  CALIBRATED {stage}/{mineral}: {len(doc.get('per_chapter', {}))} chapters -> {out}")

    # 5) stage 级聚合：per 矿种基线 → depth_targets/<stage>.json（写章深度门消费形状）
    for stage in sorted({s for (s, _m) in groups}):
        n = _aggregate_depth_targets(refs, stage)
        if n is not None:
            print(f"  AGGREGATED depth_targets/{stage}.json ({n} chapters)")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
