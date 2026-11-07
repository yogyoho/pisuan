"""导出物化后的运行时传播：栈包 → skill-sources/shared（投影由 Agent Run 初始化自动刷）。

批次2 导出链此前止步于栈包：shared/投影要等容器重启 reseed 或宿主手动跑
refs_repo_distribute.py，专家导出后技能线程仍读旧数据。本模块把传播收进导出链，
两处调用点：

- commit_refs_export（权威 commit/push 完成后，eia_refs_git）
- run_eia_corpus_process（语料重编译落栈后，eia_corpus_task_service）

bank_compile（语料重编译唯一运行时入口）的全量输出家族——samples_bank 切片/
索引/corpus_meta、samples SL3 指纹池、depth_targets 标定与注册、
section_expectations——只写 writer 栈包。chapter 包自评审 P2-8（2026-11-03）
起不携带 references/（资产单源 writer，脚本经 _paths.py 运行时回落解析），此前的
writer→chapter 镜像（bug-4206）随之退役：chapter 无资产即无漂移面，镜像若保留
反而会把 references 复活回 chapter。本模块只剩清残留 + 栈包全量重播 shared。

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

from pisuan.services.skills.projection import skill_dirs_equal
from pisuan.services.skills.shared import (
    _replace_skill_target,  # noqa: SLF001 -- 传播必须与 init_builtin_skills 同一替换原语
    get_skills_root_dir,
    list_builtin_skill_specs,
)

logger = logging.getLogger(__name__)

_PROPAGATE_LOCK = threading.Lock()


def propagate_refs_export() -> dict[str, Any]:
    """导出/重编译落栈后的运行时传播：清替换残留 → 栈包全量重播 shared。"""
    with _PROPAGATE_LOCK:
        skills_root = get_skills_root_dir()
        # 清理替换中断遗留目录。注意 _replace_skill_target 生成的是 .{slug}.tmp-{hex} /
        # .{slug}.bak-{hex}（点号前缀），须匹配 ".tmp-"/".bak-"——init_builtin_skills 里的
        # 同款清理条件写的是 "-tmp-"/"-bak-"，匹配不到实际残留（上游既有问题，此处不沿用）。
        for entry in skills_root.iterdir():
            if entry.is_dir() and entry.name.startswith(".") and (".tmp-" in entry.name or ".bak-" in entry.name):
                shutil.rmtree(entry, ignore_errors=True)

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
        return {"propagated": propagated}
