"""[pisuan-custom] W3 scope×region 归属判定纯函数模块

词表 + L1 规则 + min-permissive 聚合。零 I/O、零外部依赖，供四处复用：
- classify_paragraphs               → extract_region_signal / extract_fact_signal（段落并列键）
- _etl_pipeline_async（service）    → l1_task_attribution（任务级归属，L1 优先）
- _save_learned_templates_from_task → apply_min_permissive（模板 scope 聚合）
- backfill_task_scope.py            → l1_task_attribution（存量回填）

词表为人工维护常量：新矿区随 L3 confirm-region 落定后回填此处。
键只收矿区/规划区/煤田等「区域身份」名——项目名（如「伊泰煤矿」）不入表，
否则正文引用矿区名的项目报告会被误判 regional（Q2 语义）。
"""

import re

# 矿区/规划区名（取自 35 份语料文件名，2026-10-06 普查）→ slug 键（一地区一KB 分库键）
REGION_VOCAB: dict[str, str] = {
    "横城矿区": "hengcheng",
    "伊宁矿区北区": "yining-beiqu",
    "五间房矿区": "wujianfang",
    "淖毛湖矿区": "naomaohu",
    "沙井子矿区": "shajingzi",
    "三塘湖矿区": "santanghu",
    "灵台矿区": "lingtai",
    "伊敏矿区": "yimin",
    "胜利矿区": "shengli",
    "韦州矿区": "weizhou",
    "华亭矿区": "huating",
    "高头窑矿区": "gaotouyao",
    "鹤岗煤炭矿区": "hegang",
    "纳林希里矿区": "nalinxili",
    "七台河矿区": "qitaihe",
    "牙克石-五九煤田矿区": "yakeshi-wujiu",
    "东胜煤田": "dongsheng",
}

VALID_SCOPES: tuple[str, ...] = ("universal", "regional", "project")
_SCOPE_ORDER: dict[str, int] = {"project": 0, "regional": 1, "universal": 2}

# measures_regulation 拆分词表：命中 → constraint（标准限值/法规禁止），否则 measure
_CONSTRAINT_KEYWORDS: tuple[str, ...] = (
    "标准",
    "限值",
    "法规",
    "条例",
    "规定",
    "禁止",
    "不得",
    "严禁",
    "应符合",
    "执行标准",
)
_MEASURE_KEYWORDS: tuple[str, ...] = ("治理", "措施", "监测计划", "方案", "修复", "保护")

# B 类 category → 事实类型直映；measures_regulation 关键词拆分；C 类（project_basic 等）不落事实
_B_CATEGORY_DIRECT: dict[str, str] = {
    "natural_env": "monitoring",
    "env_quality": "monitoring",
    "sensitive_target": "sensitive_target",
    "impact_assessment": "constraint",
}

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def region_key_for_label(label: str) -> str | None:
    """展示名 → slug；未登记返回 None（L3 需显式传入新 slug，不静默造键）。"""
    return REGION_VOCAB.get(label.strip())


def extract_region_signal(text: str) -> dict[str, str] | None:
    """文本 → region 信号；词表多命中取最长名（防前缀遮蔽，如伊宁矿区北区）。"""
    hit: tuple[str, str] | None = None
    for name, key in REGION_VOCAB.items():
        if name in text and (hit is None or len(name) > len(hit[0])):
            hit = (name, key)
    return {"region_label": hit[0], "region_key": hit[1]} if hit else None


def extract_fact_signal(text: str) -> str | None:
    """文本 → fact 倾向信号（constraint/measure 词表拆分的段落级证据）。"""
    if any(k in text for k in _CONSTRAINT_KEYWORDS):
        return "constraint"
    if any(k in text for k in _MEASURE_KEYWORDS):
        return "measure"
    return None


def extract_year(text: str) -> int | None:
    """文本 → 合理年份（1900-2100，取首个命中）。"""
    m = _YEAR_RE.search(text)
    if not m:
        return None
    year = int(m.group())
    return year if 1900 <= year <= 2100 else None


def fact_type_for_category(category: str, content: str) -> str | None:
    """实体 category + 内容 → fact_type；非 B 类返回 None（C 类禁令）。"""
    if category == "measures_regulation":
        return "constraint" if any(k in content for k in _CONSTRAINT_KEYWORDS) else "measure"
    return _B_CATEGORY_DIRECT.get(category)


def l1_task_attribution(doc: dict) -> dict | None:
    """任务级 L1 归属：文档身份（文件名/文档类型/报告类型）词表命中 → regional。

    只认文档身份、不扫正文——正文引用矿区名的项目报告（如伊敏项目提「伊敏矿区」）
    不得误判。未命中返回 None（scope 留 NULL 交 L2/兜底）。
    """
    identity = " ".join(str(doc.get(k) or "") for k in ("file_name", "document_type", "report_type_code"))
    signal = extract_region_signal(identity)
    if signal is None:
        return None
    return {**signal, "scope": "regional"}


def min_permissive_scope(evidences: list[str | None]) -> str | None:
    """证据集 → 目标 scope；窄序 project < regional < universal；空证据 None。"""
    vals = [v for v in evidences if v in _SCOPE_ORDER]
    if not vals:
        return None
    if "project" in vals:
        return "project"
    if "regional" in vals:
        return "regional"
    return "universal"


def apply_min_permissive(current: str | None, evidences: list[str | None]) -> str | None:
    """模板现值 + 证据 → 落定 scope：永不升级，空证据不动，现值 NULL 直接取目标。"""
    target = min_permissive_scope(evidences)
    if target is None:
        return current
    if current not in _SCOPE_ORDER:
        return target
    return target if _SCOPE_ORDER[target] < _SCOPE_ORDER[current] else current
