"""references 根解析（评审 P2-8 资产单源化）。

chapter 包自 2026-11 起不携带 references/（75MB 资产单源在 coal-eia-writer 包，
双包漂移面结构性清零）。脚本一律经 refs_root() 取 references 根：先查自身包，
缺则回落兄弟包 coal-eia-writer。四面运行布局（buildin 栈包 / skill-sources /
用户投影 / 沙箱 /home/gem/skills）均为平铺兄弟结构，回落路径恒可达——前提是
chapter 启用的用户同时被授权 writer（部署面现状即如此）。
"""

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SIBLING_WRITER = _PACKAGE_ROOT.parent / "coal-eia-writer"


def refs_root() -> Path:
    """技能 references 目录：先自身包，缺则回落 writer 包（两面都缺则返回自身路径，由调用方按存在性报错）。"""
    own = _PACKAGE_ROOT / "references"
    if own.is_dir():
        return own
    return _SIBLING_WRITER / "references"
