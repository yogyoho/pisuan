"""语料限值提取内核（纯函数模块）。

从环评报告 Markdown 语料窗口中定位标准引用区块，解析限值行（GFM 表格 + 行内句式），
归一因子/等级/单位，并跨报告聚合置信度。不触 IO/DB，语料文本一律由调用方传入。
"""

import re
from dataclasses import dataclass

# --------------------------------------------------------------- 标准号归一
# 去噪口径借鉴 eia_standard_service._norm_std（内核保持零依赖，故本地实现不反向 import），
# 但保留「号-年」连字符：全大写、剔除空白与斜杠、破折号变体（含全角－）归一为 ASCII 连字符，
# 即 "GB 3096-2008" / "GB3096－2008" / "GB3096-2008" -> "GB3096-2008"。
_STD_NOISE_RE = re.compile(r"[\s/]+")
_STD_DASH_RE = re.compile(r"[—–－]")


def norm_code(code: str) -> str:
    """标准号归一：破折号变体归一为连字符，剔除空白与斜杠后全大写。"""
    return _STD_NOISE_RE.sub("", _STD_DASH_RE.sub("-", code)).upper()


_TABLE_BY_PREFIX = {
    "GB3096": "gb3096_zone_limits",
    "GB12348": "gb12348_boundary_limits",
    "GB3095": "gb3095_concentration_limits",
    "GB3838": "gb3838_category_limits",
    "GBT14848": "gbt14848_category_limits",
    "GB20426": "gb20426_emission_limits",
    "GBT13201": "gbt13201_a_value",
}


def table_key_for(code: str) -> str | None:
    """按归一码前缀映射已知限值表；未命中返回 None（候选表）。"""
    std = norm_code(code)
    return next((key for prefix, key in _TABLE_BY_PREFIX.items() if std.startswith(prefix)), None)


# --------------------------------------------------------------- 缺源候选（W1 标准面板 tab2）
_SAMPLE_SOURCE_CAP = 3  # 候选卡样例来源展示条数


def aggregate_cited_codes(meta: dict) -> dict[str, dict]:
    """corpus_meta 聚合：标准号原文 → {ref_count, sample_sources}（每报告计一次引用）。"""
    agg: dict[str, dict] = {}
    for rid, m in meta.get("reports", {}).items():
        for code in dict.fromkeys(m.get("standards_cited") or []):  # 同报告重复引用只计一次
            entry = agg.setdefault(code, {"ref_count": 0, "sample_sources": []})
            entry["ref_count"] += 1
            if len(entry["sample_sources"]) < _SAMPLE_SOURCE_CAP:
                entry["sample_sources"].append(rid)
    return agg


def diff_source_candidates(cited: dict[str, dict], covered_doc_codes: list[str]) -> list[dict]:
    """缺源候选差集（纯函数）：语料引用码归一化去重后减去 standard_indicators 已覆盖 doc_code。

    同归一码变体合并（ref_count 累加、样例来源并集去重截断），code 取先出现的原文写法；
    已覆盖的归一码剔除，输出按 ref_count 降序。
    """
    merged: dict[str, dict] = {}
    for code, info in cited.items():
        key = norm_code(code)
        entry = merged.setdefault(key, {"code": code, "ref_count": 0, "sample_sources": []})
        entry["ref_count"] += info["ref_count"]
        for src in info["sample_sources"]:
            if src not in entry["sample_sources"]:
                entry["sample_sources"].append(src)
    covered = {norm_code(c) for c in covered_doc_codes}
    out = [e for key, e in merged.items() if key not in covered]
    for e in out:
        e["sample_sources"] = e["sample_sources"][:_SAMPLE_SOURCE_CAP]
    out.sort(key=lambda c: -c["ref_count"])
    return out


# --------------------------------------------------------------- 因子/等级/单位归一
FACTOR_ALIASES = {
    "so2": "SO₂",
    "so₂": "SO₂",
    "二氧化硫": "SO₂",
    "no2": "NO₂",
    "no₂": "NO₂",
    "二氧化氮": "NO₂",
    "nox": "NOx",
    "noₓ": "NOx",
    "氮氧化物": "NOx",
    "pm10": "PM10",
    "pm₁₀": "PM10",
    "可吸入颗粒物": "PM10",
    "pm2.5": "PM2.5",
    "pm₂.₅": "PM2.5",
    "细颗粒物": "PM2.5",
    "tsp": "TSP",
    "总悬浮颗粒物": "TSP",
    "co": "CO",
    "一氧化碳": "CO",
    "o3": "O₃",
    "o₃": "O₃",
    "臭氧": "O₃",
    "cod": "COD",
    "化学需氧量": "COD",
    "bod5": "BOD₅",
    "生化需氧量": "BOD₅",
    "氨氮": "氨氮",
    "总磷": "总磷",
    "总氮": "总氮",
    "氟化物": "氟化物",
    "石油类": "石油类",
}


def norm_factor(name: str) -> str:
    """因子名归一：查别名表（键小写），未命中原样返回。"""
    return FACTOR_ALIASES.get(name.strip().lower(), name)


# 因子垃圾过滤——2026-10-19 试跑实证：惰性因子槽会吞进散文碎片与序号碎片。
# 后缀垃圾词实证样例：「中要求的不得超过」「的含盐量不得超过」「II类标准要求的」「监测结果」
# 「从2001年的」「均第95百分位数」「.5年均浓度分别」「点浓度差值不超过」「尘排放浓度均小于」。
_GARBAGE_TAIL_RE = re.compile(
    r"(?:的|要求|不超过|不得超过|小于|大于|以上|以下|监测|结果|标准|执行|满足|达到|分别|百分位数|差值|含盐量|浓度均)$"
)
# 前缀连接词实证样例：「即颗粒物」；纯数字/点号序号碎片实证样例：「4.」「60」「44.」。
_GARBAGE_HEAD_RE = re.compile(r"^即")
_GARBAGE_PURE_NUM_RE = re.compile(r"[\d.]+")


def _factor_ok(name: str) -> bool:
    """因子垃圾过滤：空名 / 纯数字点号碎片 / 垃圾前后缀命中均拒收。"""
    s = name.strip()
    if not s or _GARBAGE_PURE_NUM_RE.fullmatch(s) or _GARBAGE_HEAD_RE.match(s) or _GARBAGE_TAIL_RE.search(s):
        return False
    return True


# 等级归一：罗马数字各写法统一为 ASCII 大写（三/3/Ⅲ/III -> III）。
_ROMAN = {
    "一": "I",
    "二": "II",
    "三": "III",
    "四": "IV",
    "五": "V",
    "Ⅰ": "I",
    "Ⅱ": "II",
    "Ⅲ": "III",
    "Ⅳ": "IV",
    "Ⅴ": "V",
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
}

_GRADE_LEVEL_RE = re.compile(r"([一二三四五])级标准")
_GRADE_ROMAN_RE = re.compile(r"([ⅠⅡⅢⅣⅤ]+|[IV]+|[一二三四五])\s*类")
_GRADE_DIGIT_SUFFIX_RE = re.compile(r"(\d)\s*类(?:标准|区)")
_GRADE_DIGIT_RE = re.compile(r"([1-5])\s*类")


def norm_grade(ctx: str, digit_only: bool = False) -> str | None:
    """从上下文提取等级：N级标准 / 罗马数字类（三、3 -> III类）/ 声环境数字类（2类标准 -> 2类）。

    digit_only=True 仅供噪声表（GB 3096/GB 12348 只用 0-4 数字类档）：仅数字类正则命中且
    保留数字写法（3类），窗口重叠带入的水/气罗马档（III类）视为未命中——2026-10-19 试跑实证。
    """
    if not digit_only:
        m = _GRADE_LEVEL_RE.search(ctx)
        if m:
            return f"{m.group(1)}级标准"
        m = _GRADE_ROMAN_RE.search(ctx)
        if m:
            return _ROMAN.get(m.group(1), m.group(1)) + "类"
    m = _GRADE_DIGIT_SUFFIX_RE.search(ctx)
    if m:
        return f"{m.group(1)}类"
    m = _GRADE_DIGIT_RE.search(ctx)
    if m:
        return f"{m.group(1)}类" if digit_only else _ROMAN[m.group(1)] + "类"
    return None


_UNIT_FIXES = {
    "mg/m3": "mg/m³",
    "μg/m3": "μg/m³",
    "ug/m3": "μg/m³",
    "µg/m³": "μg/m³",
    "mg/l": "mg/L",
    "db(a)": "dB(A)",
}


def norm_unit(unit: str) -> str:
    """单位归一：剥尾部标点后查已知写法表；未命中返回剥标点后的原样。"""
    cleaned = unit.strip().strip("。，,；;：:")
    return _UNIT_FIXES.get(cleaned.lower(), cleaned)


def convert_limit(value: float, unit: str) -> tuple[float, str]:
    """μg/m³ 数值 ÷1000 归一为 mg/m³；其余单位原值返回（单位先归一）。"""
    u = norm_unit(unit)
    if u == "μg/m³":
        return value / 1000, "mg/m³"
    return value, u


# --------------------------------------------------------------- 区块定位
@dataclass
class Block:
    """一个标准号引用区块：命中行及其后至窗口边界的文本行。"""

    code: str
    lines: list[str]
    start: int


_CODE_RE = re.compile(r"(?:GB|HJ)(?:/T?)?\s?\d+(?:\.\d+)?[-—–]\d{4}")


def locate_standard_blocks(text: str, max_window: int = 30) -> list[Block]:
    """逐行找标准号，向后取窗口（<=max_window 行）。

    窗口遇 md 标题行或下一处标准号停；边界行计入当前块——语料中同一行常同时承载
    上一标准的行内限值与下一标准的引用（如「氨氮 1.0 mg/L。噪声执行…(GB 3096-2008)」），
    不含边界行会丢行。
    """
    lines = text.splitlines()
    blocks: list[Block] = []
    for i, line in enumerate(lines):
        m = _CODE_RE.search(line)
        if not m:
            continue
        window: list[str] = []
        j = i
        while j < len(lines) and len(window) < max_window:
            cur = lines[j]
            window.append(cur)
            if j > i and (cur.lstrip().startswith("#") or _CODE_RE.search(cur)):
                break
            j += 1
        blocks.append(Block(code=m.group(0), lines=window, start=i))
    return blocks


# --------------------------------------------------------------- 区块解析
_NUM_RE = re.compile(r"[≤<]?\s*(\d+(?:\.\d+)?)")
_UNIT_SCAN_RE = re.compile(r"mg/m³|mg/m3|μg/m³|μg/m3|ug/m3|mg/L|mg/l|dB\(A\)", re.IGNORECASE)
_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_NUMERIC_HEADER_RE = re.compile(r"限值|标准|浓度|a\s*值")

# 行内句式：因子(2-8 字，可带上标) + 可选时段 + 可选 浓度/标准值/限值/标准（可连用）
# + 可选比较词 + 数值 + 单位。因子必须惰性量词——贪婪会把无空格句式的数值首位
# 吞进因子（实测 "昼间65 dB(A)" -> day=5.0、"氨氮1.0mg/L" -> 0.0）。
_PERIOD = r"(日均|24小时|日平均|1小时|8小时|小时|年均|年)"
_KEYWORD = r"(?:(?:浓度|标准值|限值|标准)\s*)*"
_INLINE_RE = re.compile(
    r"([一-龥A-Za-z0-9._₂₅ₓ]{2,8}?)\s*"
    rf"{_PERIOD}?\s*"
    rf"{_KEYWORD}"
    r"[≤<为]?\s*"
    r"(\d+(?:\.\d+)?)\s*"
    r"(mg/m³|mg/m3|μg/m³|μg/m3|ug/m3|mg/L|mg/l|dB\(A\))",
    re.IGNORECASE,
)

_NOISE_TABLES = ("gb3096_zone_limits", "gb12348_boundary_limits")
_CATEGORY_TABLES = ("gb3838_category_limits", "gbt14848_category_limits")


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _cell_value(cell: str) -> float | None:
    m = _NUM_RE.search(cell)
    return float(m.group(1)) if m else None


def _extract_table(lines: list[str]) -> tuple[list[str], list[dict[str, str]]] | None:
    """找第一个 GFM 三段式表格（表头|分隔|数据…），返回（表头, 行 dict 列表）；无则 None。"""
    for i, line in enumerate(lines[:-1]):
        header = _split_row(line)
        if len(header) < 2 or not _SEP_RE.match(lines[i + 1]):
            continue
        rows = []
        for cur in lines[i + 2 :]:
            if not cur.strip() or cur.lstrip().startswith("#") or "|" not in cur:
                break
            if _SEP_RE.match(cur):
                break
            rows.append(dict(zip(header, _split_row(cur))))
        return header, rows
    return None


def _factor_col(header: list[str]) -> str | None:
    return next((h for h in header if "污染物" in h or "项目" in h), None)


def _map_table_rows(header: list[str], rows: list[dict[str, str]], table_key: str | None, ctx: str) -> list[dict]:
    """按表 schema 列映射为限值行；解析不出数值的行丢弃。"""
    if table_key in _NOISE_TABLES:
        unit_col = next((h for h in header if "单位" in h), None)
        day_col = next((h for h in header if "昼间" in h), None)
        night_col = next((h for h in header if "夜间" in h), None)
        out = []
        for row in rows:
            day, night = _cell_value(row.get(day_col, "")), _cell_value(row.get(night_col, ""))
            if day is None and night is None:
                continue
            out.append(
                {
                    "category": norm_grade(ctx, digit_only=True) or "",
                    "day": day,
                    "night": night,
                    "unit": norm_unit(row.get(unit_col, "")),
                }
            )
        return out

    num_cols = [h for h in header if _NUMERIC_HEADER_RE.search(h)]
    unit_col = next((h for h in header if "单位" in h), None)
    out = []
    for row in rows:
        if table_key is None:  # 候选表：保留原始列名，数值列照常提数
            mapped = {f"col_{h}": v for h, v in row.items()}
            for h in num_cols:
                if (val := _cell_value(row.get(h, ""))) is not None:
                    mapped[f"col_{h}"] = val
            out.append(mapped)
            continue
        numeric, unit_cell = None, ""
        for h in num_cols:
            val = _cell_value(row.get(h, ""))
            if val is not None:
                numeric = val
                if rest := _UNIT_SCAN_RE.search(row.get(h, "")):
                    unit_cell = rest.group(0)  # 数值单元格内残余单位优先
                break
        if numeric is None:
            continue
        pollutant = norm_factor(row.get(_factor_col(header), ""))
        if not _factor_ok(pollutant):  # 垃圾因子行拒收（候选表分支已在上方 continue，不受影响）
            continue
        if unit_cell == "" and unit_col:
            unit_cell = row.get(unit_col, "")
        value, unit = convert_limit(numeric, unit_cell)
        value_key = "a_value" if table_key == "gbt13201_a_value" else "limit_value"
        base = {"pollutant": pollutant, "unit": unit}
        if table_key == "gb3095_concentration_limits":
            period_col = next((h for h in header if "取值时间" in h or "时段" in h), None)
            out.append(
                {
                    **base,
                    "period": row.get(period_col) or "24小时",
                    "grade": norm_grade(ctx) or "二级标准",
                    value_key: value,
                }
            )
        elif table_key in _CATEGORY_TABLES:
            out.append({"category": norm_grade(ctx) or "III类", value_key: value, **base})
        else:  # 其余已知表（GB20426 排放表等）：通用三键
            out.append({**base, value_key: value})
    return out


def _scan_inline(lines: list[str], table_key: str | None, ctx: str) -> list[dict]:
    """无表格区块的行内句式扫描，按目标表 schema 装配行。"""
    out = []
    for line in lines:
        for m in _INLINE_RE.finditer(line):
            factor, period = m.group(1), m.group(2)
            value, unit = convert_limit(float(m.group(3)), m.group(4))
            if unit == "dB(A)" and table_key not in _NOISE_TABLES:
                # 非噪声表不收声级值——窗口重叠把 GB 12348 内容带进 GB3838 区块
                # （2026-10-19 试跑实证），与噪声表只收 dB(A) 的过滤对称。
                continue
            if table_key in _NOISE_TABLES:
                if unit != "dB(A)":  # 噪声表只收声级值，窗口重叠带入的水质行不收
                    continue
                key = "night" if "夜" in factor else "day"  # 昼/夜同行并现时按因子归属
                out.append({"category": norm_grade(ctx, digit_only=True) or "", key: value, "unit": unit})
            elif table_key == "gb3095_concentration_limits":
                if not _factor_ok(norm_factor(factor)):
                    continue
                out.append(
                    {
                        "pollutant": norm_factor(factor),
                        "period": period or "24小时",
                        "grade": norm_grade(ctx) or "二级标准",
                        "limit_value": value,
                        "unit": unit,
                    }
                )
            elif table_key in _CATEGORY_TABLES:
                if not _factor_ok(norm_factor(factor)):
                    continue
                out.append(
                    {
                        "category": norm_grade(ctx) or "III类",
                        "pollutant": norm_factor(factor),
                        "limit_value": value,
                        "unit": unit,
                    }
                )
            elif table_key is not None:  # 其余已知表（GB20426 排放表等）同样过垃圾过滤
                pollutant = norm_factor(factor)
                if not _factor_ok(pollutant):
                    continue
                out.append({"pollutant": pollutant, "limit_value": value, "unit": unit})
            else:  # 候选表：保留原始因子，不过滤
                out.append({"pollutant": norm_factor(factor), "limit_value": value, "unit": unit})
    return out


def parse_block(block: Block) -> list[dict]:
    """解析区块为限值行：优先 GFM 表格（schema 列映射），无表格则行内句式扫描。

    已知局限：等级/档位取块级 ctx 正则首处命中——同一区块一行并现多个档位
    （如 007 语料一行同时引用 2类与1类）时，后续档位的行会误标首档位；
    Task 9 试跑门观察项，不在内核层特判。
    """
    table_key = table_key_for(block.code)
    ctx = "\n".join(block.lines)
    table = _extract_table(block.lines)
    if table:
        return _map_table_rows(table[0], table[1], table_key, ctx)
    return _scan_inline(block.lines, table_key, ctx)


# --------------------------------------------------------------- 聚合置信
_AGG_NON_BIZ = {"limit_value", "day", "night", "a_value", "conflict_values"}


def _biz_key(row: dict) -> tuple:
    """业务键：除数值列外全部字段的 sorted tuple（值转 str）。"""
    return tuple(sorted((k, str(v)) for k, v in row.items() if k not in _AGG_NON_BIZ))


def aggregate_records(records: list[dict]) -> list[dict]:
    """按（标准, 表, 业务键）聚合限值记录并判定置信度。

    数值列（limit_value/day/night/a_value 取首个非空）全一致 ->
    不同 report_id >=2 为 multi，否则 single；
    不一致 -> conflict，row 附 conflict_values（升序唯一值）。code 保留首见原样。
    """
    groups: dict[tuple, dict] = {}
    for rec in records:
        key = (norm_code(rec["code"]), rec["table_key"], _biz_key(rec["row"]))
        g = groups.setdefault(
            key,
            {"code": rec["code"], "table_key": rec["table_key"], "row": dict(rec["row"]), "values": [], "sources": []},
        )
        row = rec["row"]
        g["values"].append(
            next((row[k] for k in ("limit_value", "day", "night", "a_value") if row.get(k) is not None), None)
        )
        g["sources"].append(rec["source"])
    out = []
    for g in groups.values():
        rids = {s.get("report_id") for s in g["sources"]}
        uniq = {v for v in g["values"] if v is not None}
        if len(uniq) > 1:
            g["row"]["conflict_values"] = sorted(uniq)
            g["confidence"] = "conflict"
        else:
            g["confidence"] = "multi" if len(rids) >= 2 else "single"
        out.append(
            {
                "code": g["code"],
                "table_key": g["table_key"],
                "row": g["row"],
                "confidence": g["confidence"],
                "sources": g["sources"],
            }
        )
    return out
