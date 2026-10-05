"""语料适配度测试（roadmap v2 spec §3.6）。

对 35 份语料（四族，复垦按 §3.7 排除）逐份渲染骨架，与 chapters.json 实测章树对比：
- 槽位集合完全匹配 >= 34/35（spec 36/38 等比收紧）
- 章序完全一致 >= 28/35（spec 30/38 等比收紧；声明院家风豁免后计）
不匹配项必须落差异单（--report 模式），改规则或登记豁免二选一，禁止静默忽略。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
FIXTURES = BACKEND / "test/data/corpus_census"
RENDERER = BACKEND / "scripts/render_report_skeletons.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("rrs", RENDERER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\d+$", "", s)
    s = re.sub(r"^第?[一二三四五六七八九十\d]+\s*[章节篇][\s\.、：:]*", "", s)
    return re.sub(r"^(\d+(\.\d+)*)[\s\.、：:]*", "", s)


def _alias_index(l1: dict) -> dict[str, str]:
    """归一化题/别名 → 章题。alias 与任意已登记章题同名时跳过（防同名误挂）。"""
    idx = {}
    for t, body in l1["chapters"].items():
        idx[_norm(t)] = t
    for t, body in l1.get("optional_chapters", {}).items():
        idx.setdefault(_norm(t), t)
    for src in (l1["chapters"], l1.get("optional_chapters", {})):
        for t, body in src.items():
            for a in body.get("aliases", []):
                if _norm(a) not in idx:  # alias==norm(章题) 时以章题为准，跳过 alias
                    idx[_norm(a)] = t
    return idx


@pytest.fixture(scope="module")
def env():
    rrs = _load_renderer()
    layers = rrs.load_layers()
    conds = json.loads((FIXTURES / "conditions.json").read_text(encoding="utf-8"))
    chapters = json.loads((FIXTURES / "chapters.json").read_text(encoding="utf-8"))
    return rrs, layers, conds, chapters


FIT_UNIVERSE = json.loads((BACKEND / "test/data/corpus_census/conditions.json").read_text(encoding="utf-8"))["universe"]
FIT_FILES = sorted(FIT_UNIVERSE)


def test_universe_is_35():
    assert len(FIT_FILES) == 35


def _match_file(env, fname):
    """返回 (slot_hits: list[章题], corpus_titles: list[归一化题], unmatched: list)。"""
    rrs, layers, _, chapters = env
    rendered = rrs.render(FIT_UNIVERSE[fname], layers)
    rendered_titles = [c["title"] for c in rendered["chapters"].values()]
    l1 = layers[FIT_UNIVERSE[fname]["report_family"]]["l1"]
    idx = _alias_index(l1)
    hits, unmatched = [], []
    for c in chapters[fname]["chapters"]:
        t = _norm(c["n"])
        if t in idx:
            hits.append(idx[t])
        else:
            unmatched.append(t)
    return rendered_titles, hits, unmatched


@pytest.mark.parametrize("fname", FIT_FILES)
def test_per_file_slot_match(env, fname):
    _, hits, unmatched = _match_file(env, fname)
    exemptions = FIT_UNIVERSE[fname].get("exemptions", {}).get("slots", [])
    effective_unmatched = [t for t in unmatched if t not in exemptions]
    assert not effective_unmatched, f"{fname[:40]} 未命中槽位（差异单必须处理）: {effective_unmatched}"


def test_fit_thresholds(env):
    rrs, layers, _, chapters = env
    slot_ok, order_ok, diffs = 0, 0, []
    for fname in FIT_FILES:
        rendered_titles, hits, unmatched = _match_file(env, fname)
        ex = FIT_UNIVERSE[fname].get("exemptions", {})
        if not [t for t in unmatched if t not in ex.get("slots", [])]:
            slot_ok += 1
        else:
            diffs.append((fname, "slots", unmatched))
        rendered_set = [t for t in rendered_titles]
        hit_seq = [t for t in hits]
        expected = [t for t in rendered_set if t in set(hit_seq)]
        if expected == hit_seq or ex.get("order"):
            order_ok += 1
        else:
            diffs.append((fname, "order", list(zip(expected, hit_seq))))
    report = "\n".join(f"{k} {f[:40]}: {v}" for f, k, v in diffs)
    assert slot_ok >= 34, f"槽位匹配 {slot_ok}/35 < 34\n{report}"
    assert order_ok >= 28, f"章序匹配 {order_ok}/35 < 28\n{report}"
