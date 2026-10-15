"""范式 md 专名扫描（承方向 A A1 红线：导出写入前 0 命中）。

扫描集 = 24 份 sample_entities 黑名单 entities 五类（projects/mines/orgs/places/sensitive）
的并集，剔除通用词。通用词（豁免集）= ①各文件 generic_terms 显式声明（含「/」复合作逐段
拆分）②出现在 ≥3 份不同文件黑名单中的词 ③专名与任一通用词互为子串者。仅对剩余专名集
断言 0 命中（子串匹配）。
"""

from functools import lru_cache
import json
from pathlib import Path

from yuxi.services.eia_data_service import _SKILL_ROOT

ENTITIES_DIR = _SKILL_ROOT / "references" / "sample_entities"
GENERIC_MIN_FILES = 3


def _build_index(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    files: dict[str, set[str]] = {}
    generic: set[str] = set()
    for p in sorted(root.glob("*.json")):
        if p.name == "_index.json":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        for terms in doc.get("entities", {}).values():
            for t in terms:
                files.setdefault(t, set()).add(p.name)
        for g in doc.get("generic_terms", []):
            generic.update(g.split("/"))
    freq = {t for t, fs in files.items() if len(fs) >= GENERIC_MIN_FILES}
    generic |= freq
    proper = {t for t in files if t not in generic and not any(t in g or g in t for g in generic)}
    return frozenset(proper), frozenset(generic)


@lru_cache(maxsize=8)
def _cached(root: str) -> tuple[frozenset[str], frozenset[str]]:
    return _build_index(Path(root))


def _index():
    return _cached(str(ENTITIES_DIR))


def scan_text(text: str, root: Path | None = None) -> list[str]:
    """返回 text 中命中的专名（排序确定性）；root 仅测试注入用。

    lru_cache 按 root 串缓存；测试注入 root 后若同 root 文件中途变更需手动 _cached.cache_clear()。
    """
    proper, _ = _cached(str(root or ENTITIES_DIR))
    return sorted(t for t in proper if t in text)


def PROPER_NOUNS() -> frozenset[str]:
    return _index()[0]


def GENERIC_TERMS() -> frozenset[str]:
    return _index()[1]
