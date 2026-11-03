"""导出物化后的运行时传播：双包收敛（bank 输出家族镜像）→ 栈包 → skill-sources/shared（投影由 Agent Run 初始化自动刷）。

批次2 导出链此前止步于栈包：shared/投影要等容器重启 reseed 或宿主手动跑
refs_repo_distribute.py，专家导出后技能线程仍读旧数据。本模块把传播收进导出链，
两处调用点：

- commit_refs_export（权威 commit/push 完成后，eia_refs_git）
- run_eia_corpus_process（语料重编译落栈后，eia_corpus_task_service）

bank_compile（语料重编译唯一运行时入口）的全量输出家族——samples_bank 切片/
索引/corpus_meta、samples SL3 指纹池、depth_targets 标定与注册、
section_expectations——只写 writer 栈包，chapter 栈包无人喂（bug-4206：容器
守卫红且每次重编译复发）。传播头部先栈内收敛（_mirror_bank_outputs 原子替换
+ 内容跳过），再重播 shared：一个接线点让两条传播路径都获得「传播完成后双包
一致」不变量。

词表导出的 section_expectations 重编译不在本模块：编译输入 = 绑定语料 KB 全量
文档（容器内无静态 workdir），由既有 eia_corpus_process 任务承担（「不做局部
重编译」防口径与切片漂移，见 /eia/stages/expectations/recompile）；词表导出
服务负责排队该任务。

机制：与 lifespan init_builtin_skills 同一原子替换原语 _replace_skill_target
（临时目录拷贝 + rename）；内容未变的技能经 skill_dirs_equal（字节+执行位哈希，
与投影 copy-on-change 同判据）跳过，避免无谓整树复制。投影层不在此处触碰：
refresh_user_skill_projection 按字节 copy-on-change，每个 Agent Run 初始化自动
执行（backends/composite.sync_agent_context_skills）。

模块级串行锁：同进程并发导出的传播互斥，防 rename 替换交错。
"""

import logging
import shutil
import threading
from pathlib import Path
from typing import Any

from yuxi.services.skills.projection import skill_dirs_equal
from yuxi.services.skills.shared import (
    _replace_skill_target,  # noqa: SLF001 -- 传播必须与 init_builtin_skills 同一替换原语
    get_skills_root_dir,
    list_builtin_skill_specs,
)

logger = logging.getLogger(__name__)

_PROPAGATE_LOCK = threading.Lock()

# bank_compile 输出家族（模块 docstring 清单 1-7 全部落在这四目录；corpus_meta.json
# 由任务服务合并进 samples_bank）。writer→chapter 镜像只圈这四目录——chapter 独有
# 资产（stages/roles/style_targets 等静态件）不在此射程，由 repo 树 sync 脚本管。
_BANK_OUTPUT_DIRS = ("depth_targets", "samples", "samples_bank", "section_expectations")
_WRITER_SLUG = "coal-eia-writer"
_CHAPTER_SLUG = "coal-eia-chapter-writer"


def _mirror_bank_outputs() -> list[str]:
    """bank 输出家族 writer→chapter 栈包内镜像（bug-4206）。返回实际替换的目录名。

    writer 侧目录不存在（首次编译前）跳过——没东西可收敛，chapter 保持原状；
    chapter 包未安装跳过（无该技能的部署合法态）。中断残留（.{name}.tmp-/.bak-，
    落在 chapter references 内，skills_root 级清理够不到）先行清扫。
    """
    specs = {s["slug"]: Path(s["source_dir"]) for s in list_builtin_skill_specs()}
    writer = specs.get(_WRITER_SLUG)
    chapter = specs.get(_CHAPTER_SLUG)
    if writer is None or chapter is None:
        return []
    mirrored: list[str] = []
    for name in _BANK_OUTPUT_DIRS:
        src = writer / "references" / name
        if not src.is_dir():
            continue
        dst_parent = chapter / "references"
        for entry in dst_parent.iterdir():
            if entry.is_dir() and entry.name.startswith(".") and (".tmp-" in entry.name or ".bak-" in entry.name):
                shutil.rmtree(entry, ignore_errors=True)
        dst = dst_parent / name
        if dst.is_dir() and skill_dirs_equal(dst, src):
            continue
        _replace_skill_target(dst, src)
        mirrored.append(name)
    if mirrored:
        logger.info(f"[refs-propagate] bank 输出家族 writer→chapter 栈内镜像: {mirrored}")
    return mirrored


def propagate_refs_export() -> dict[str, Any]:
    """导出/重编译落栈后的运行时传播：清替换残留 → 双包收敛（bank 输出家族镜像）→ 栈包全量重播 shared。"""
    with _PROPAGATE_LOCK:
        skills_root = get_skills_root_dir()
        # 清理替换中断遗留目录。注意 _replace_skill_target 生成的是 .{slug}.tmp-{hex} /
        # .{slug}.bak-{hex}（点号前缀），须匹配 ".tmp-"/".bak-"——init_builtin_skills 里的
        # 同款清理条件写的是 "-tmp-"/"-bak-"，匹配不到实际残留（上游既有问题，此处不沿用）。
        for entry in skills_root.iterdir():
            if entry.is_dir() and entry.name.startswith(".") and (".tmp-" in entry.name or ".bak-" in entry.name):
                shutil.rmtree(entry, ignore_errors=True)

        mirrored = _mirror_bank_outputs()
        propagated: list[str] = []
        for spec in list_builtin_skill_specs():
            source = Path(spec["source_dir"])
            target = skills_root / spec["slug"]
            if target.is_dir() and skill_dirs_equal(target, source):
                continue
            _replace_skill_target(target, source)
            propagated.append(spec["slug"])
        if propagated:
            logger.info(f"[refs-propagate] 栈包 → shared 重播 {len(propagated)} 技能: {propagated}")
        return {"propagated": propagated, "mirrored": mirrored}
