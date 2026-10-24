#!/usr/bin/env python3
"""global_families 派生：data_expectations.json 顶层增 global_families（build 派生，不手拍）。

口径（spec §3.2 / chapter-writer plan Task 5）：
    global_families = 跨 ≥2 章 per_chapter 出现的数据族
                    ∪ 冻结公式依赖的数据表单族
                    （跨 ≥2 章消费公式族的 FORMULA_FORM_DEPS ∪ derived 常算块依赖）

与 spec 预估（4~5 族：规划方案/沉陷参数/标准确认/敏感目标）的偏差说明：机械派生结果为 12 族——
跨章数据族实为 7 个（air/eco/economy/monitoring/planning_indicators/projection/water，
ch13 收束章引用全部公式族使冻结依赖面覆盖 subsidence_params/water/air/noise + derived 三表单），
并集后标准确认/敏感目标不在内（单章数据族且非公式依赖）。门 1 全局包随之变重；
若需瘦身应收紧派生口径（如 clause1 限前部章），而非手拍清单。

CLI：
    python derive_globals.py [--stage planning_eia] [--expectations FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from formula_runner import FORMULA_FORM_DEPS  # noqa: E402

REFS = Path(__file__).resolve().parent.parent / "references"
EXPECTATIONS_PATH = REFS / "data_expectations.json"


def _cross_chapter_families(stage: dict) -> set[str]:
    """跨 ≥2 章消费的公式族（章 → sections uses.formulas 计数）。"""
    use: dict[str, set[str]] = {}
    for cid, ch in stage.get("chapters", {}).items():
        for sec in ch.get("sections", []):
            for f in (sec.get("uses") or {}).get("formulas") or []:
                use.setdefault(f, set()).add(cid)
    return {f for f, chs in use.items() if len(chs) >= 2}


def derive(expectations: dict, stage: dict, formula_deps: dict | None = None) -> list[str]:
    """跨≥2章数据族 ∪ 冻结依赖表单族，排序返回。formula_deps 缺省用 formula_runner 事实清单。"""
    deps = formula_deps if formula_deps is not None else FORMULA_FORM_DEPS
    seen: dict[str, int] = {}
    for ch in expectations.get("per_chapter", []):
        for f in ch.get("data_families") or []:
            seen[f["family"]] = seen.get(f["family"], 0) + 1
    cross_data = {f for f, n in seen.items() if n >= 2}
    freeze_forms: set[str] = set(deps.get("_derived") or ())
    for f in _cross_chapter_families(stage):
        freeze_forms.update(deps.get(f) or ())
    return sorted(cross_data | freeze_forms)


def write_globals(expectations_path: Path, stage: dict) -> list[str]:
    """派生并写回 expectations 的 global_families 键。

    文本级插入/替换（非整档重排）：原文件为紧凑数组手写风格，json.dumps 重排会产生数百行
    噪声 diff——只动 global_families 一处，其余字节零扰动；重跑幂等。"""
    # raw I/O（newline=""）：绕过 universal-newline 翻译，CRLF/LF 文件均字节级保形
    with open(expectations_path, encoding="utf-8", newline="") as f:
        text = f.read()
    doc = json.loads(text)
    globals_ = derive(doc, stage)
    key = '"global_families": ' + json.dumps(globals_, ensure_ascii=False)
    nl = "\r\n" if "\r\n" in text[:200] else "\n"  # 沿用文件既有换行符，插入行不破坏原形状
    if "global_families" in doc:
        text = re.sub(r'"global_families": \[[^\]]*\]', key, text, count=1)
    else:
        text = text.replace("{", "{" + nl + "  " + key + ",", 1)
    with open(expectations_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return globals_


def load_globals() -> list[str]:
    """读已派生的 global_families（ingest check --global-only 消费）；未派生即报错——禁手拍兜底。"""
    doc = json.loads(Path(EXPECTATIONS_PATH).read_text(encoding="utf-8"))
    globals_ = doc.get("global_families")
    if globals_ is None:
        raise ValueError(f"{EXPECTATIONS_PATH} 缺 global_families——先跑 derive_globals.py 派生，禁手拍")
    return globals_


def main() -> int:
    ap = argparse.ArgumentParser(description="派生 data_expectations.json 的 global_families（跨章族 ∪ 冻结依赖族）")
    ap.add_argument("--stage", default="planning_eia")
    ap.add_argument("--expectations", default=str(EXPECTATIONS_PATH))
    ap.add_argument("--stage-json", default=str(REFS / "stages"))
    a = ap.parse_args()
    stage = json.loads((Path(a.stage_json) / f"{a.stage}.json").read_text(encoding="utf-8"))
    globals_ = write_globals(Path(a.expectations), stage)
    print(f"GLOBAL_FAMILIES: {len(globals_)} 族 → {a.expectations}")
    for f in globals_:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
