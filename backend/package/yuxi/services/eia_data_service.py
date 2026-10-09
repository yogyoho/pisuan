"""环评域数据工厂（coal-eia-writer 技能）只读统计服务。

统计总览页唯一数据源：聚合技能 references/ 语料文件 + 案例切片现扫词表候选。
纯只读、无 DB 依赖；技能数据是 git 内置兜底真源（覆盖层架构 v1，页面对各数据集
的启停开关与 DB 运营层属一期后续，接口形状已按其预留 layers/candidates 结构）。

缓存：以源文件 mtime 指纹为版本戳，语料未变时直接复用上次聚合结果；
首次调用需全量扫描 477 个切片（秒级），命中后为纯 dict 返回。
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STAGES = (
    "planning_eia",
    "post_eia",
    "project_eia_openpit",
    "project_eia_underground",
    "tracking_eia",
)

_SKILL_ROOT = Path(__file__).resolve().parents[1] / "agents" / "skills" / "buildin" / "coal-eia-writer"
_REFS = _SKILL_ROOT / "references"
_BANK = _REFS / "samples_bank"

# ── 词表候选扫描口径（数值护栏词表 curated_lexicon 的候选原料）────────────────
# 量词正则直接从 bank_compile 加载（技能唯一口径真源，避免复制漂移）；
# 清洗/三分类规则为一期词表管线的现行版本，管线脚本建成后切换为读管线产物。

_MEASURE_RE = re.compile(
    r"(回用率|利用率|处置率|除尘效率|抑尘效率|降尘效率|捕尘效率|完好率|入洗率|回收率|节水率|脱灰率|防渗率|达标率|覆盖率)"
)
_SITE_RE = re.compile(r"(频率|超标率|盖度|优势度|城镇化率|保证率|含水率|纵坡|系数|检出限|浓度|水质标准|坡度)")
_STOP_TAIL = (
    "能",
    "可",
    "仅",
    "别",
    "分",
    "约",
    "超",
    "均",
    "的",
    "了",
    "在",
    "与",
    "和",
    "及",
    "或",
    "比",
    "按",
    "要",
    "应",
    "占",
)
_GENERIC_JUNK = {"平均值", "含量", "一般", "分别", "所占比例", "比例", "占比", "检出限", "类水质标准", "分"}
# 词表候选只收比率/浓度型单位（可发布 P5-P95 区间的口径）；km2/t/m 等 extensive
# 量随项目产能走，无区间意义，与语料普查口径一致（普查 94 候选全为比率/浓度型）
_CANDIDATE_UNITS = {"%", "dB(A)", "mg/L", "μg/m3", "μg/m³"}
_MIN_RANGE_REPORTS = 5

# 疑似乱码标题启发式（bank_index 既有脏数据形态，如「旷/t (年入选」「.22) :」）
_MOJI_HINT = re.compile(r"[一-鿿]/[a-z]{1,2}\s*\(|^\s*[.0-9a-zA-Z)\s:：,，\-]+$")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _skill_root_exists() -> bool:
    return _SKILL_ROOT.exists()


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_quantity_re() -> re.Pattern:
    """从 bank_compile.py 加载 QUANTITY_RE（模块可安全导入，见技能测试）。"""
    spec = importlib.util.spec_from_file_location("coal_eia_bank_compile", _SKILL_ROOT / "scripts" / "bank_compile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.QUANTITY_RE


def _clean_caliber(raw: str) -> str:
    """剥离口径尾噪声（「除尘效率可」→「除尘效率」），迭代剥到稳定。"""
    s = raw.strip()
    while s and s[-1] in _STOP_TAIL:
        s = s[:-1]
    return s.strip("的了与和及或")


def _classify_caliber(caliber: str) -> str:
    """三分类：measure=工程措施类（可入选）/ site=站点背景类（候选待业务确认）/ junk=其余。"""
    if _MEASURE_RE.search(caliber):
        return "measure"
    if _SITE_RE.search(caliber):
        return "site"
    return "junk"


def _iter_mentions():
    """全语料数值提及迭代器 (stage, rid, caliber, unit, value)——清洗过滤后的口径。

    统计扫描、词表导入、拆分素材、导出值收集四处共用同一迭代（口径单一真源，
    避免各处过滤条件漂移）；切片按路径排序保证确定性。"""
    qty_re = _load_quantity_re()
    for stage in STAGES:
        sdir = _BANK / stage / "slices"
        if not sdir.exists():
            continue
        for p in sorted(sdir.rglob("*.md")):
            rid = p.name.split("__", 1)[0]
            for m in qty_re.finditer(p.read_text(encoding="utf-8", errors="replace")):
                if m.group(3) not in _CANDIDATE_UNITS:
                    continue
                caliber = _clean_caliber(m.group(1))
                if len(caliber) < 2 or caliber in _GENERIC_JUNK:
                    continue
                yield stage, rid, caliber, m.group(3), float(m.group(2))


def _scan_all() -> list[dict[str, Any]]:
    """全量词表候选条目（不截断）：统计摘要与词表导入共用同一扫描（n≥2 报告门槛）。"""
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for stage, rid, caliber, unit, _value in _iter_mentions():
        ent = agg.setdefault((stage, caliber, unit), {"rids": set(), "n_values": 0})
        ent["rids"].add(rid)
        ent["n_values"] += 1

    top: list[dict[str, Any]] = []
    for (stage, caliber, unit), ent in agg.items():
        n_reports = len(ent["rids"])
        if n_reports < 2:
            continue  # 单报告孤例不构词表候选（护栏需跨报告支撑）
        cat = _classify_caliber(caliber)
        top.append(
            {
                "stage": stage,
                "caliber": caliber,
                "unit": unit,
                "category": cat,
                "n_reports": n_reports,
                "n_values": ent["n_values"],
                "range_ready": cat != "junk" and n_reports >= _MIN_RANGE_REPORTS,
            }
        )
    top.sort(key=lambda x: (-x["n_values"], x["stage"], x["caliber"]))
    return top


def _scan_candidates() -> dict[str, Any]:
    """统计摘要：全量扫描的三分类计数（含 per_stage 分布与 top15 明细）。"""
    top = _scan_all()
    per_stage: dict[str, dict[str, int]] = {s: {"measure": 0, "site": 0, "junk": 0} for s in STAGES}
    for e in top:
        per_stage[e["stage"]][e["category"]] += 1
    cat_total = Counter(e["category"] for e in top)
    return {
        "total": len(top),
        "measure": cat_total["measure"],
        "site": cat_total["site"],
        "junk": cat_total["junk"],
        "range_ready": sum(1 for e in top if e["range_ready"]),
        "per_stage": per_stage,
        "top": top[:15],
    }


def _corpus_stats() -> dict[str, Any]:
    corpus_meta = _read_json(_BANK / "corpus_meta.json")
    reports = corpus_meta.get("reports", {})
    by_province: Counter = Counter()
    per_stage_reports: Counter = Counter()
    for rid, r in reports.items():
        by_province[r.get("province") or "未知"] += 1
        per_stage_reports[r.get("stage") or "未知"] += 1

    per_stage: dict[str, dict[str, int]] = {}
    slices_total = samples_total = 0
    for stage in STAGES:
        slices = len(list((_BANK / stage / "slices").rglob("*.md"))) if (_BANK / stage / "slices").exists() else 0
        samples = len(list((_REFS / "samples" / stage).glob("*.md")))
        per_stage[stage] = {"slices": slices, "samples": samples, "reports": per_stage_reports.get(stage, 0)}
        slices_total += slices
        samples_total += samples
    return {
        "reports_total": len(reports),
        "slices_total": slices_total,
        "samples_total": samples_total,
        "per_stage": per_stage,
        "by_province": dict(by_province),
    }


def _expectations_stats() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for stage in STAGES:
        p = _REFS / "section_expectations" / f"{stage}.json"
        if not p.exists():
            continue
        d = _read_json(p)
        tiers: Counter = Counter()
        mapped = ranged = total = 0
        for sec in d.get("sections", {}).values():
            for q in sec.get("expected_quantities", []):
                total += 1
                tiers[q.get("tier", "?")] += 1
                if q.get("field"):
                    mapped += 1
                if q.get("range"):
                    ranged += 1
        out[stage] = {
            "sections": len(d.get("sections", {})),
            "quantities": total,
            "mapped": mapped,
            "unmapped": len(d.get("unmapped", [])),
            "tiers": dict(tiers),
            "ranged": ranged,
        }
    return out


def _layer_items(candidates: dict[str, Any], expectations: dict[str, Any]) -> list[dict[str, Any]]:
    """五层价值模型数据集块（UI 显示名 ← 文件真源；count=None+planned=本期预留位）。"""
    ann = _read_json(_BANK / "corpus_meta_annotations.json")
    corpus_meta = _read_json(_BANK / "corpus_meta.json")
    ac = _read_json(_BANK / "attachment_checklist.json")
    si = _read_json(_REFS / "standards_index.json")
    fm = _read_json(_REFS / "formulas.json")
    de = _read_json(_REFS / "data_expectations.json")
    cc = _read_json(_REFS / "consistency_contracts.json")
    fc = _read_json(_REFS / "paradigms" / "forms_catalog.json")
    se_idx = _read_json(_REFS / "sample_entities" / "_index.json")
    depth_chapters = sum(len(_read_json(_REFS / "depth_targets" / f"{s}.json").get("chapters", {})) for s in STAGES)

    def kb(name: str) -> float:
        return round((_REFS / name).stat().st_size / 1024, 1)

    return [
        {
            "layer": "语料与溯源",
            "items": [
                {
                    "key": "case_corpus",
                    "name": "案例语料库",
                    "count": None,
                    "unit": "切片",
                    "detail": "按语料规模分布卡计数",
                },
                {
                    "key": "corpus_meta",
                    "name": "语料元数据",
                    "file": "samples_bank/corpus_meta.json",
                    "count": len(corpus_meta.get("reports", {})),
                    "unit": "报告",
                },
                {
                    "key": "meta_annotations",
                    "name": "元数据人工标注",
                    "file": "samples_bank/corpus_meta_annotations.json",
                    "count": len(ann),
                    "unit": "报告",
                },
                {
                    "key": "attachment_checklist",
                    "name": "附件图件清单",
                    "file": "samples_bank/attachment_checklist.json",
                    "count": sum(int(v.get("base_reports", 0)) for v in ac.get("stages", {}).values()),
                    "unit": "基准报告",
                },
                {
                    "key": "chapter_examples",
                    "name": "章节范文",
                    "file": "chapter_examples/",
                    "count": len(list((_REFS / "chapter_examples").glob("*"))),
                    "unit": "文件",
                },
            ],
        },
        {
            "layer": "事实与护栏",
            "items": [
                {
                    "key": "section_expectations",
                    "name": "章节事实槽位",
                    "file": "section_expectations/*.json",
                    "count": sum(v["sections"] for v in expectations.values()),
                    "unit": "节",
                },
                {
                    "key": "curated_lexicon",
                    "name": "数值护栏词表",
                    "count": candidates["measure"] + candidates["site"],
                    "unit": "候选口径",
                    "detail": f"可发布区间 {candidates['range_ready']} 项",
                },
                {
                    "key": "standards_index",
                    "name": "标准与限值库",
                    "file": "standards_index.json",
                    "count": len(si.get("standards", [])),
                    "unit": "标准",
                    "detail": f"限值表 {len(si.get('limit_tables', []))} 张",
                },
                {
                    "key": "formulas",
                    "name": "计算公式参数",
                    "file": "formulas.json",
                    "count": len(fm.get("formulas", [])),
                    "unit": "公式",
                    "detail": f"派生槽位 {len(fm.get('derived_slots', []))} 个",
                },
                {
                    "key": "data_expectations",
                    "name": "备料数据清单",
                    "file": "data_expectations.json",
                    "count": len(de.get("per_chapter", [])),
                    "unit": "章",
                },
            ],
        },
        {
            "layer": "写作范式",
            "items": [
                {
                    "key": "forms_catalog",
                    "name": "句式范式目录",
                    "file": "paradigms/forms_catalog.json",
                    "count": len(fc.get("forms", {})),
                    "unit": "句式",
                },
                {
                    "key": "paradigms",
                    "name": "写作范式",
                    "file": "paradigms/*.md",
                    "count": len(list((_REFS / "paradigms").glob("*.md"))),
                    "unit": "文件",
                },
                {
                    "key": "consistency_contracts",
                    "name": "一致性契约",
                    "file": "consistency_contracts.json",
                    "count": len(cc.get("contracts", [])),
                    "unit": "条",
                },
                {
                    "key": "depth_targets",
                    "name": "篇幅深度基准",
                    "file": "depth_targets/",
                    "count": depth_chapters,
                    "unit": "章",
                },
            ],
        },
        {
            "layer": "术语与合规",
            "items": [
                {
                    "key": "terminology",
                    "name": "术语库",
                    "file": "terminology.md",
                    "count": kb("terminology.md"),
                    "unit": "KB",
                },
                {
                    "key": "compliance_checklist",
                    "name": "合规清单",
                    "file": "compliance_checklist.md",
                    "count": kb("compliance_checklist.md"),
                    "unit": "KB",
                },
            ],
        },
        {
            "layer": "实体与评测",
            "items": [
                {
                    "key": "sample_entities",
                    "name": "样例实体注册表",
                    "file": "sample_entities/",
                    "count": len(se_idx.get("samples", [])),
                    "unit": "实体",
                },
                {"key": "question_bank", "name": "质询问题库", "status": "planned"},
                {"key": "deep_annotations", "name": "深度标注片段库", "status": "planned"},
                {"key": "eval_cases", "name": "评测用例集", "status": "planned"},
                {"key": "regulation_library", "name": "法规条款库", "status": "planned"},
            ],
        },
    ]


def _quality_stats(expectations: dict[str, Any]) -> list[dict[str, Any]]:
    """数据质量体检：只报客观可算项；启发式项明确标注。"""
    items: list[dict[str, Any]] = []
    si = _read_json(_REFS / "standards_index.json")
    nv = sum(1 for s in si.get("standards", []) if s.get("needs_verification"))
    items.append(
        {
            "key": "standards_verify",
            "level": "warn",
            "label": "标准条目待人工核实",
            "count": nv,
            "hint": "standards_index 中 needs_verification 存量，人工确认后转 verified",
        }
    )
    unmapped_total = sum(v["unmapped"] for v in expectations.values())
    items.append(
        {
            "key": "unmapped_pool",
            "level": "info",
            "label": "未归并量词（unmapped 池）",
            "count": unmapped_total,
            "hint": "label 未命中 forms_label_map 的显式池，是词表候选扩充素材；planning 阶段存在 200 条截断上限",
        }
    )
    empty_titles = moji_titles = 0
    for stage in STAGES:
        d = _read_json(_REFS / "section_expectations" / f"{stage}.json")
        for sec in d.get("sections", {}).values():
            title = sec.get("title", "")
            if not title:
                empty_titles += 1
            elif _MOJI_HINT.search(title):
                moji_titles += 1
    items.append(
        {
            "key": "empty_titles",
            "level": "info",
            "label": "空标题节",
            "count": empty_titles,
            "hint": "语料切分边界产物，不影响事实槽位消费，可在语料清洗批次一并补齐",
        }
    )
    items.append(
        {
            "key": "moji_titles",
            "level": "warn",
            "label": "疑似乱码章节标题",
            "count": moji_titles,
            "hint": "启发式扫描（拉丁碎片穿插/纯符号标题），根因在语料源，修复需清洗后重建",
        }
    )
    ac = _read_json(_BANK / "attachment_checklist.json")
    insufficient = sum(len(v.get("rids_without_items", [])) for v in ac.get("stages", {}).values())
    thin_stages = [st for st, v in ac.get("stages", {}).items() if v.get("insufficient_base")]
    items.append(
        {
            "key": "attachment_insufficient",
            "level": "warn",
            "label": "附件清单不足报告",
            "count": insufficient,
            "hint": "rids_without_items：未提供必备附件图件的语料报告"
            + (f"；{len(thin_stages)} 个阶段基准语料不足（insufficient_base）" if thin_stages else ""),
        }
    )
    ann = _read_json(_BANK / "corpus_meta_annotations.json")
    reports_total = len(_read_json(_BANK / "corpus_meta.json").get("reports", {}))
    items.append(
        {
            "key": "meta_annotation_coverage",
            "level": "info",
            "label": "元数据人工标注覆盖",
            "count": len(ann),
            "total": reports_total,
            "hint": "已提交人工标注的报告数 / 语料报告总数",
        }
    )
    return items


def get_skill_stats() -> dict[str, Any]:
    """统计总览聚合入口。mtime 指纹未变时直接返回缓存。"""
    watch = [
        _BANK / "corpus_meta.json",
        _BANK / "corpus_meta_annotations.json",
        _BANK / "attachment_checklist.json",
        _REFS / "standards_index.json",
        _REFS / "formulas.json",
        _REFS / "data_expectations.json",
        _REFS / "consistency_contracts.json",
        _REFS / "paradigms" / "forms_catalog.json",
        _REFS / "sample_entities" / "_index.json",
        *(_REFS / "section_expectations" / f"{s}.json" for s in STAGES),
        *(_REFS / "depth_targets" / f"{s}.json" for s in STAGES),
    ]
    if not _SKILL_ROOT.exists():
        raise FileNotFoundError(f"coal-eia-writer 技能目录不存在: {_SKILL_ROOT}")
    fingerprint = max((p.stat().st_mtime for p in watch if p.exists()), default=0.0)
    for stage in STAGES:
        sdir = _BANK / stage / "slices"
        if sdir.exists():
            fingerprint = max(fingerprint, max((p.stat().st_mtime for p in sdir.rglob("*.md")), default=0.0))

    cached = _cache.get("stats")
    if cached and cached[0] == fingerprint:
        return cached[1]

    corpus = _corpus_stats()
    candidates = _scan_candidates()
    expectations = _expectations_stats()
    stats = {
        "skill": "coal-eia-writer",
        "stages": list(STAGES),
        "corpus": corpus,
        "layers": _layer_items(candidates, expectations),
        "candidates": candidates,
        "expectations": expectations,
        "quality": _quality_stats(expectations),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _cache["stats"] = (fingerprint, stats)
    return stats
