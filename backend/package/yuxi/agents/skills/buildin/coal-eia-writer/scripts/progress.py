#!/usr/bin/env python3
"""coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。

spec docs/designs/coal-eia-report-v2.md「两层状态模型」：报告 ~700 页 ≈ 77+ 节，派发/记账
是节级（chNN_SNN），门禁是章级（节无独立门）。progress.json 是唯一事实源（本脚本唯一写者，
防手改同 formula_state 惯例）；断点续跑靠磁盘不靠对话记忆。章条目带 sections 子表：

  {"ch6": {"status": "IN_PROGRESS",
    "sections": [
      {"id": "ch6_S01", "title": "矿区开采地表沉陷预测", "status": "VERIFIED",
       "dispatches": 1, "delivered": false},
      {"id": "ch6_S02", "title": "生态环境影响评价", "status": "DRAFTED", "dispatches": 1}]}}

状态机（章与节同构）：
  PENDING  --派发--> DRAFTED --门PASS--> VERIFIED --修改回路--> DRAFTED
  DRAFTED  --重派--> DRAFTED（dispatches 递增）
  DRAFTED  --门FAIL且重派耗尽--> BLOCKED --补数据/批准降档--> DRAFTED
  PENDING  --额度耗尽--> BLOCKED
  任意态   --stage 条件开关--> ABSENT --开关回翻--> PENDING（门/组装/记账跳过，D 决策）
VERIFIED 只能来自真门 rc=0 的自动回写：
  章 VERIFIED = `gate` 批量跑章门 PASS 自动回写（geo bug-3049 手动 mark 禁用）；
  节 VERIFIED = 所属章门 PASS 时随章自动回写（两层模型改造点①——节无独立门，唯一通道同源），
  手动 mark --sections VERIFIED 一律拒绝（bug-3049 同构）。

分章模式（`init --mode chapter`，spec §3 逐章管线；full 缺省零变化——progress.json 不写 mode 键）：
  章状态增 REVIEWED（审查步）与 CONFIRMED（用户确认，唯一通道 confirm-chapter）：
  PENDING→DRAFTED→(gate PASS)→VERIFIED→REVIEWED→CONFIRMED；CONFIRMED→DRAFTED 确认卡返工。
  next 单章聚焦编排 COLLECTING→gate→review→确认卡→下一章；CONFIRMED/ABSENT/BLOCKED 章跳过
  （恢复检测认 CONFIRMED 跳过前序；BLOCKED 挂起不阻后续章，协商后置到只剩 BLOCKED）；
  confirm-chapter 把本章 highlights 并入 state/key_points.json（增量幂等，ch13 结论章事实源）。

批量记账原语（两层模型改造点④；bug-3048：单 run bash ≤25 次，节粒度下逐节单发必烧穿）：
  mark --sections ch6_S01,ch6_S02 DRAFTED   按波批量记账节集（原子——任一未知/非法全批拒绝）
  delivered --sections … --wave N           交付子代理按波回执（delivered 布尔 + 交付波次，D6）

退出码：0 成功 / 1 用法错误、非法状态转移、重复 init、未知章节或节、批量门有 FAIL。

平台预算规避（bug-3040/3048 移植）：gate 批量单章门（一次 bash 跑完全部 DRAFTED 章）；
run-stage freeze/finalize 把固定脚本序列合并为一次 bash 调用。700 页规模下停车点规约见 SKILL.md。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

# finalize 的 consistency --standards 默认 = 技能规范索引（CC3 规范编号枚举门的真源；
# 缺文件时省略该旗标 → CC1/CC3 降为 manual，rc=2 由调用方按门拦语义处理）。
# coal-eia T1：references/standards_index.json 尚未落地（一期任务4），在册即自动启用。
STANDARDS_INDEX = Path(__file__).resolve().parent.parent / "references" / "standards_index.json"

# finalize 的 consistency --contracts 默认 = 技能合约注册表（T1b 改造点①条件激活门的真源；
# T4 并行会话维护，本脚本只读——在册即自动启用，缺文件时省略旗标，注册表门整体跳过）。
CONTRACTS_INDEX = Path(__file__).resolve().parent.parent / "references" / "consistency_contracts.json"

# 派发额度：700 页 ≈ 77+ 节派发（D10 规模约束），batch_task 分波是默认生存方式。
# 本脚本内预算只做展示与 WAVE1 路由提示；硬执行在 harness SubagentLimitMiddleware。
DISPATCH_BUDGET = 120

# 节 id 契约（stage JSON sections[].id 同形）：chNN_SNN——章前缀必须与所属章一致
SECTION_ID_RE = re.compile(r"^ch\d+_S\d+$")

TRANSITIONS: dict[str, set[str]] = {
    # PENDING→VERIFIED = gate 真跑门 PASS 自动补记（手动 mark VERIFIED 已禁用，bug-3049）
    "PENDING": {"DRAFTED", "VERIFIED", "BLOCKED", "ABSENT"},
    "DRAFTED": {"DRAFTED", "VERIFIED", "BLOCKED", "ABSENT"},  # DRAFTED→DRAFTED = 重派
    "VERIFIED": {"DRAFTED", "ABSENT", "REVIEWED"},  # 修改回路重写；条件开关翻出；审查收口 → REVIEWED
    # REVIEWED：审查步（coal-eia-reviewer 规程）完成待确认——章级专属（节无独立审查）
    "REVIEWED": {"DRAFTED", "ABSENT"},  # 审查退回重写；条件开关翻出
    "CONFIRMED": {"DRAFTED"},  # 确认卡返工唯一出口；CONFIRMED 本身 mark 禁达（唯一通道 confirm-chapter）
    "BLOCKED": {"DRAFTED", "ABSENT"},  # 补数据/批准降档后复活
    # ABSENT：stage 条件开关驱动（双模式互换/可选章缺席），门/组装/记账跳过；开关回翻 → PENDING
    "ABSENT": {"PENDING"},
}


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def section_sort_key(s: dict):
    m = re.match(r"^ch\d+_S(\d+)$", s.get("id", ""))
    return int(m.group(1)) if m else 99


def active_order(doc: dict) -> list[str]:
    """参与波次推导的章（ABSENT 章不占波、不派发、不跑门）。"""
    return [c for c in chapter_order(doc["chapters"]) if doc["chapters"][c]["status"] != "ABSENT"]


def iter_sections(doc: dict):
    """(章id, 节条目) 全量遍历。"""
    for c in chapter_order(doc["chapters"]):
        for s in doc["chapters"][c].get("sections", []):
            yield c, s


def find_section(doc: dict, sid: str) -> tuple[str, dict] | None:
    for c, s in iter_sections(doc):
        if s.get("id") == sid:
            return c, s
    return None


def load(state_dir: Path) -> dict:
    p = state_dir / "progress.json"
    if not p.exists():
        print(f"[progress] {p} 不存在——新任务先 init；续跑检查 --state-dir 路径", file=sys.stderr)
        raise SystemExit(EXIT_ERROR)
    return json.loads(p.read_text(encoding="utf-8"))


def save(state_dir: Path, doc: dict) -> None:
    """原子写（tmp + os.replace，build_output 同款）。不用 sort_keys：chapters 插入序=数值序。"""
    p = state_dir / "progress.json"
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, p)


def approved_set(doc: dict) -> set[str]:
    out: set[str] = set()
    for a in doc.get("downgrade_approvals", []):
        out.update(a.get("chapters", []))
    return out


def derive_phase(doc: dict) -> str:
    chs = doc["chapters"]
    act = active_order(doc)
    wave1 = act[:-1]
    wave2 = [act[-1]] if act else []
    unapproved = {c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc)
    if any(chs[c]["status"] in ("PENDING", "DRAFTED") for c in wave1):
        return "WAVE1"
    if unapproved:
        return "NEGOTIATE"
    if not doc.get("key_points_confirmed"):
        return "KEY_POINTS"
    if any(chs[c]["status"] in ("PENDING", "DRAFTED") for c in wave2):
        return "WAVE2"
    return "FINAL"


# 分章模式 phase ← 当前章状态映射（单章聚焦；CONFIRMED/ABSENT/BLOCKED 均非当前章候选）
CHAPTER_PHASE_BY_STATUS = {"PENDING": "COLLECTING", "DRAFTED": "GATE", "VERIFIED": "REVIEW", "REVIEWED": "CONFIRM"}


def derive_phase_chapter(doc: dict) -> str:
    """分章模式 phase：首个非 CONFIRMED/ABSENT/BLOCKED 章的状态定 phase；
    无当前章时——只剩 BLOCKED → NEGOTIATE（协商后置），否则 FINAL（全收口）。"""
    chs = doc["chapters"]
    act = active_order(doc)
    current = next((c for c in act if chs[c]["status"] not in ("CONFIRMED", "ABSENT", "BLOCKED")), None)
    if current is None:
        return "NEGOTIATE" if any(chs[c]["status"] == "BLOCKED" for c in act) else "FINAL"
    return CHAPTER_PHASE_BY_STATUS[chs[current]["status"]]


def derive_phase_any(doc: dict) -> str:
    """按模式分发 phase 推导：chapter → 单章聚焦；full（缺省/无 mode 键）→ 批量编排（零变化）。"""
    return derive_phase_chapter(doc) if doc.get("mode") == "chapter" else derive_phase(doc)


def _sections_line(ent: dict) -> str:
    """章内节状态摘要行（status 输出用）。"""
    secs = ent.get("sections", [])
    if not secs:
        return ""
    by: dict[str, int] = {}
    for s in secs:
        by[s.get("status", "?")] = by.get(s.get("status", "?"), 0) + 1
    delivered = sum(1 for s in secs if s.get("delivered"))
    tally = " ".join(f"{k} {v}" for k, v in sorted(by.items()))
    return f" 节[{len(secs)}] {tally} 已交付 {delivered}"


def _self_cmd(*extra: str) -> str:
    return "python -X utf8 " + str(Path(__file__).resolve()) + " " + " ".join(extra)


def next_action(doc: dict, state_dir: Path) -> str:
    phase = derive_phase(doc)
    chs = doc["chapters"]
    act = active_order(doc)
    wave1 = act[:-1]
    last = act[-1] if act else None
    sd = str(state_dir)
    lines = [f"PHASE: {phase}"]

    def pending_sections(ch_id: str) -> list[str]:
        return [s["id"] for s in chs[ch_id].get("sections", []) if s.get("status") in ("PENDING", "DRAFTED")]

    if phase == "WAVE1":
        drafted = [c for c in wave1 if chs[c]["status"] == "DRAFTED"]  # 先收口已起草的（批量一次跑完）
        if drafted:
            lines += [
                f"[NEXT] 批量跑门: {', '.join(drafted)}（DRAFTED——只信产物，不信子代理摘要；一次 bash 全部跑完，PASS 章自动转 VERIFIED）",
                f"命令: {_self_cmd('gate', '--state-dir', sd)}",
                "期望 rc: 0（GATE_BATCH_DONE passed=N failed=0，PASS 章及其全部节由 gate 自动转 VERIFIED）",
                '        1 → failed 章按 stderr 原文重派（原 prompt + stderr，每章 ≤1 次）；重派仍 FAIL → mark <chN> BLOCKED --gate FAIL --detail "<一句话差距>"',
            ]
            return "\n".join(lines)
        pending = [c for c in wave1 if chs[c]["status"] == "PENDING"]
        if doc.get("total_dispatches", 0) >= DISPATCH_BUDGET:
            lines += [
                f"[NEXT] 额度耗尽: 总派发 {doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET}，剩余 PENDING 章 {pending}",
                f'动作: 逐章 progress.py mark <chN> BLOCKED --state-dir {sd} --detail "派发额度耗尽" → 进协商（或请用户新会话续跑，progress 无损）',
            ]
            return "\n".join(lines)
        c = pending[0]
        ps = pending_sections(c)
        lines += [
            f"[NEXT] 按波派发: {c}（PENDING，wave1 独立章；节级派发，D9 粒度分层）",
            "动作: 按 SKILL.md 步骤4 派发契约组装 prompt（stage sections 要素链+范文索引+节级深度目标），batch_task 分波派子代理直写 state/sections/<节id>.md（每波 5–10 节）",
            "约束: 每轮 ≤3 个并发 task()（超发被运行时静默丢弃）；子代理只回 ≤10 行摘要（含本节要点）",
            f"记账（批量原语，节粒度禁逐节单发——bug-3048）: progress.py mark --sections {','.join(ps[:5])}{'…' if len(ps) > 5 else ''} DRAFTED --state-dir {sd}",
            f"收口: 波内节稿拼章稿 state/chapters/{c}.md → mark {c} DRAFTED → gate（PASS 章与其全部节自动转 VERIFIED）",
        ]
        return "\n".join(lines)

    if phase == "NEGOTIATE":
        un = sorted({c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc))
        lines += [
            f"[NEXT] 协商: 未批准 BLOCKED: {', '.join(un)}",
            "动作: 组差距表（章/实际 eff/目标/缺口——取各章 gate_detail 与单章门 stderr）单表单 ask_clarification 三选项:",
            "  ① 补数据（回 ingest → formula_runner → 相关节 mark --sections … DRAFTED 重派）",
            f'  ② 批准降档（progress.py approve-downgrade --state-dir {sd} --chapters {",".join(un)} --note "<用户批准依据>"）',
            "  ③ [待确认] 收尾（缺数信号放宽覆盖缩放，重写即可能达标）",
            "期望: 用户答复后才推进（单回合至多一次 ask_clarification；挂起即停，不推进）",
        ]
        return "\n".join(lines)

    if phase == "KEY_POINTS":
        lines += [
            "[NEXT] 要点包: wave1 已收口，蒸馏 state/key_points.json",
            "动作: 聚合各子代理摘要的「本节要点」+ formula_state 关键值（产能/沉陷预测/容量/水量平衡等冻结值）",
            '      写 state/key_points.json: {"chapters":{"ch1":[...],...},"highlights":{...},"issues":[...]}',
            f"      单表单 ask_clarification 呈现用户确认 → progress.py confirm-key-points --state-dir {sd}",
            "要点包 = ch13 结论章唯一事实来源（不重读 wave1 全文）",
        ]
        return "\n".join(lines)

    if phase == "WAVE2":
        if chs[last]["status"] == "DRAFTED":
            lines += [
                f"[NEXT] 跑门: {last}（DRAFTED，wave2 结论章——同款批量 gate 命令）",
                f"命令: {_self_cmd('gate', '--state-dir', sd)}",
                "期望 rc: 同 WAVE1 批量跑门分支（PASS→章与节 VERIFIED / FAIL→重派 ≤1 次→BLOCKED）",
            ]
            return "\n".join(lines)
        lines += [
            f"[NEXT] 派发: {last}（PENDING，wave2 结论章）",
            "动作: 派发契约同 wave1，输入追加 state/key_points.json——只依据要点包写投影式结论，不引入 wave1 之外的新数字",
        ]
        return "\n".join(lines)

    # FINAL
    blocked = sorted(c for c, s in chs.items() if s["status"] == "BLOCKED")
    gate_cmd = _self_cmd(
        "run-stage", "finalize", "--state-dir", sd, "--outputs-dir", '"<OUTPUTS>"', "--task", '"<本轮用户指令一句话>"'
    )
    if blocked:
        lines += [
            f"[NEXT] 终验（分级交付）: 已批准降档 {blocked}",
            f"命令: {gate_cmd}",
            "说明: 已批准降档自动加 --allow-partial（stdout PARTIAL_DELIVERY 行明示 N 章降档；manifest.partial 逐章留痕）——交付时向用户汇报降档章节与差距",
            "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ 交付（项目路径=交付子代理分波逐节 write_chapter；独立路径=present_files）",
            "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
        ]
        return "\n".join(lines)
    lines += [
        "[NEXT] 终验: 全部章节 VERIFIED",
        f"命令: {gate_cmd}",
        "说明: run-stage finalize 一次 bash 完成 build_output → consistency.py → snapshot.py save（交付名由脚本从 data/ 拼，stdout 原样透传）",
        "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ 交付（项目路径=交付子代理分波逐节 write_chapter；独立路径=present_files）",
        "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
    ]
    return "\n".join(lines)


def next_action_chapter(doc: dict, state_dir: Path) -> str:
    """分章模式 next：单章聚焦，恰好一个下一步动作——COLLECTING→gate→review→确认卡→下一章。

    恢复检测：CONFIRMED 前序自动跳过（断点续跑认 CONFIRMED）；BLOCKED 挂起不阻后续章，
    收口后置协商；全收口 → run-stage finalize 终验。"""
    chs = doc["chapters"]
    act = active_order(doc)
    sd = str(state_dir)
    done = [c for c in act if chs[c]["status"] == "CONFIRMED"]
    blocked = sorted(c for c in act if chs[c]["status"] == "BLOCKED")
    current = next((c for c in act if chs[c]["status"] not in ("CONFIRMED", "ABSENT", "BLOCKED")), None)
    if current is None:
        if blocked:
            un = sorted(set(blocked) - approved_set(doc))
            return "\n".join(
                [
                    "PHASE: NEGOTIATE",
                    f"[NEXT] 协商: 未批准 BLOCKED: {', '.join(un)}",
                    "动作: 组差距表（章/实际 eff/目标/缺口——取各章 gate_detail）单表单 ask_clarification 三选项:",
                    "  ① 补数据（回 ingest → formula_runner → mark DRAFTED 重派重跑门）",
                    f'  ② 批准降档（progress.py approve-downgrade --state-dir {sd} --chapters {",".join(un)} --note "<用户批准依据>"）',
                    "  ③ [待确认] 收尾（分级交付，终验 --allow-partial）",
                    "期望: 用户答复后才推进（挂起即停，不推进）",
                ]
            )
        finalize_cmd = _self_cmd(
            "run-stage",
            "finalize",
            "--state-dir",
            sd,
            "--outputs-dir",
            '"<OUTPUTS>"',
            "--task",
            '"<本轮用户指令一句话>"',
        )
        return "\n".join(
            [
                "PHASE: FINAL",
                f"[NEXT] 终验: 全部章 CONFIRMED（{len(done)}/{len(act)}）",
                f"命令: {finalize_cmd}",
                "说明: run-stage finalize 一次 bash 完成 build_output → consistency.py → snapshot.py save",
                "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ 交付",
                "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
            ]
        )
    phase = CHAPTER_PHASE_BY_STATUS[chs[current]["status"]]
    lines = [
        f"PHASE: {phase}",
        f"[NEXT] 当前章: {current}（{chs[current]['status']}，进度 {len(done)}/{len(act)} 章已确认）",
    ]
    if done:
        lines.append(f"恢复: 前序已确认 {len(done)} 章（跳过）：{', '.join(done)}")
    if blocked:
        lines.append(f"挂起: BLOCKED {', '.join(blocked)}（不阻当前章，收口后协商）")
    if phase == "COLLECTING":
        plan_p = state_dir / f"plan_{current}.json"
        choice_p = state_dir / f"fragment_choice_{current}.json"
        if not plan_p.exists():
            # 交互卡点·卡A：计划卡是管线第一步（用户确认前禁收资料/派发，红线 P13）。
            lines += [
                "动作: 先发本章编写计划卡给用户确认（一屏摘要: 本章定位/编写要点 3~5 条/需准备的数据/篇幅规模三选（详实版|精简版|自定义字数）/过程预告；业务语体，无命令路径与内部术语）",
                f'记账: {_self_cmd("plan-confirm", current, "--summary-file", "<卡面md>", "--notes", '"<用户补充意见，无则省略>"', "--state-dir", sd)}'
                f"（篇幅: 缺省详实版；精简版 --depth compact；自定义 --depth custom --target N）",
                "修订: 用户补充意见合入后重发修订版卡再确认（plan-confirm 幂等覆盖）——未确认前禁进资料汇集",
            ]
            return "\n".join(lines)
        if not choice_p.exists():
            lines += [
                "动作: ① 本章资料汇集（首章门1 全局包 `ingest.py check --global-only`，后续章冻结层已在）→ ② 模板推荐（按范式角色查 references/paradigms/roles/<stage>.json + 模板库，呈用户可跳过）→ ③ batch_task 分波派发子代理直写节稿（派发契约同 full：stage sections 要素链+范文索引+节级深度目标）",
                "派发前置（② 后 ③ 前必做）: sample_fragments.py --stage <stage> --chapter "
                + current
                + " --candidates 3 --out state/sample_candidates_"
                + current
                + ".json 列 3 份同类范例候选，呈用户挑选（编号选定或『不用范例』，业务语体呈现）→ "
                + _self_cmd("fragment-choice", current, "--report-id", "<选定id>|--none", "--state-dir", sd)
                + "；无 choice 禁派发（红线 P13）；选定后 sample_fragments.py --report-id <id> 取包注入派发契约",
            ]
        else:
            choice = json.loads(choice_p.read_text(encoding="utf-8"))
            rid = choice.get("report_id")
            lines += [
                "动作: ① 本章资料汇集（首章门1 全局包 `ingest.py check --global-only`，后续章冻结层已在）→ ② 模板推荐（按范式角色查 references/paradigms/roles/<stage>.json + 模板库，呈用户可跳过）→ ③ batch_task 分波派发子代理直写节稿（派发契约同 full：stage sections 要素链+范文索引+节级深度目标）",
                f"范例: 已选定 {'不用范例（派发契约如实注明用户选择）' if rid is None else rid}——③ 派发契约注入 sample_fragments 包与计划卡（state/plan_{current}.json 的要点与用户补充意见，写作须回扣）",
            ]
        lines += [
            f"记账: 节批量 mark --sections <节id csv> DRAFTED --state-dir {sd}（批量原语）→ 章稿齐后 progress.py mark {current} DRAFTED --state-dir {sd}",
        ]
    elif phase == "GATE":
        lines += [
            f"命令: {_self_cmd('gate', '--chapters', current, '--state-dir', sd)}",
            "期望 rc: 0（PASS 章及其全部节自动转 VERIFIED）；1 → stderr 差距原文重派 ≤1 次 → 仍 FAIL 则 mark BLOCKED",
        ]
    elif phase == "REVIEW":
        lines += [
            "动作: 按 coal-eia-reviewer 规程本章审查（--chapter，发现单 [PASS/WARN/FAIL] 条目|定位|证据摘录|修复建议；只审不改）",
            f"记账: 发现可收口 → progress.py mark {current} REVIEWED --state-dir {sd}；FAIL 退回 → progress.py mark {current} DRAFTED --state-dir {sd}（改后重跑门）",
        ]
    else:  # CONFIRM——发卡即停
        lines += [
            "动作: 单表单呈用户确认卡——章稿全文 + 审查发现单 + 本章要点；三选项 ① 确认进下一章 ② 修改意见（返工重写）③ 停车",
            f'确认: progress.py confirm-chapter {current} --highlights "要点1|要点2" --state-dir {sd}（highlights 并入 state/key_points.json）',
            "返工: progress.py mark " + current + " DRAFTED --state-dir " + sd + "（确认卡意见进重写 prompt）",
        ]
    return "\n".join(lines)


def _blank_section(s: dict) -> dict:
    return {"id": s["id"], "title": s.get("title", ""), "status": "PENDING", "dispatches": 0, "delivered": False}


def cmd_init(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    p = state_dir / "progress.json"
    if p.exists():
        print(f"[progress] {p} 已存在——续跑请用 next/status，勿重复 init 抹掉进度", file=sys.stderr)
        return EXIT_ERROR
    stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
    # 节 id 契约校验（stage sections 与 progress 解析的接口契约，T1 骨架即生效）：
    # id 形状 chNN_SNN、章前缀与所属章一致、章内唯一。
    chapters: dict = {}
    n_sections = 0
    for c in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][c]
        seen: set[str] = set()
        sections: list[dict] = []
        for s in ch.get("sections", []):
            sid = s.get("id", "")
            if not SECTION_ID_RE.match(sid):
                print(f"[progress] {c} 节 id 非法: {sid!r}（契约形 chNN_SNN，与章 {c} 同前缀）", file=sys.stderr)
                return EXIT_ERROR
            if not sid.startswith(c + "_S"):
                print(f"[progress] 节 {sid} 前缀与所属章 {c} 不一致（stage JSON 结构错误）", file=sys.stderr)
                return EXIT_ERROR
            if sid in seen:
                print(f"[progress] 节 {sid} 在 {c} 内重复（stage JSON 结构错误）", file=sys.stderr)
                return EXIT_ERROR
            seen.add(sid)
            sections.append(_blank_section(s))
        sections.sort(key=section_sort_key)
        n_sections += len(sections)
        chapters[c] = {
            "status": "PENDING",
            "dispatches": 0,
            "last_gate": None,
            "gate_detail": "",
            "blocked_reason": None,
            "sections": sections,
        }
    doc = {
        "stage_path": str(Path(args.stage).resolve()),
        "data_dir": str(Path(args.data_dir).resolve()) if args.data_dir else None,
        "phase": "WAVE1",
        "total_dispatches": 0,
        "chapters": chapters,
        "key_points_confirmed": False,
        "downgrade_approvals": [],
    }
    if args.mode == "chapter":
        doc["mode"] = "chapter"  # full 缺省不写键——progress.json 结构对既有管线零变化
    state_dir.mkdir(parents=True, exist_ok=True)
    save(state_dir, doc)
    n = len(doc["chapters"])
    extra = "（分章模式：逐章 COLLECTING→gate→review→确认卡）" if args.mode == "chapter" else ""
    print(
        f"PROGRESS_INIT: {n} 章 {n_sections} 节全部 PENDING（{', '.join(doc['chapters'])}）→ 下一步 progress.py next{extra}"
    )
    return EXIT_OK


def cmd_next(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if doc.get("mode") == "chapter":
        print(next_action_chapter(doc, state_dir))
    else:
        print(next_action(doc, state_dir))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    total_sections = sum(len(e.get("sections", [])) for e in doc["chapters"].values())
    verified_sections = sum(1 for _, s in iter_sections(doc) if s.get("status") == "VERIFIED")
    delivered_sections = sum(1 for _, s in iter_sections(doc) if s.get("delivered"))
    print(
        f"phase={derive_phase_any(doc)} 总派发={doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET} 要点包确认={doc.get('key_points_confirmed', False)} "
        f"节 VERIFIED {verified_sections}/{total_sections} 已交付 {delivered_sections}"
    )
    for c in chapter_order(doc["chapters"]):
        s = doc["chapters"][c]
        extra = f" reason={s['blocked_reason']}" if s.get("blocked_reason") else ""
        print(f"  {c}: {s['status']} 派发{s.get('dispatches', 0)} 门={s.get('last_gate')}{_sections_line(s)}{extra}")
    return EXIT_OK


def cmd_mark(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    status = args.status
    if bool(args.sections) == bool(args.chapter):
        print(
            "[progress] 用法: mark <chN> <status>（章）或 mark --sections <csv> <status>（节批量）——二选一",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if status == "VERIFIED":
        # bug-3049 定案（节级同构，两层模型改造点②）：--gate PASS 是调用方自证（自申报），
        # 非官方凭据——VERIFIED 一律拒绝手动 mark。唯一合法通道 = progress.py gate
        # （内部真跑 build_output.run_chapter_gate，PASS 章自动回写 VERIFIED 并随章回写全部节）。
        who = f"--sections {args.sections}" if args.sections else args.chapter
        print(
            f"[progress] {who} 手动 mark VERIFIED 已禁用（--gate PASS 是自证，bug-3049）——节 VERIFIED 唯一通道 = 所属章 `progress.py gate` 真跑章门 rc=0 自动回写",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if status == "CONFIRMED":
        print(
            "[progress] CONFIRMED 唯一通道 = confirm-chapter <chN>（确认卡契约——highlights 并入 state/key_points.json）",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if status == "REVIEWED" and args.sections:
        print("[progress] REVIEWED 是章级状态（审查步）——节无独立审查，节批量不接受 REVIEWED", file=sys.stderr)
        return EXIT_ERROR
    if status not in TRANSITIONS:
        print(f"[progress] mark 只接受 {'/'.join(TRANSITIONS)}（收到 {status}）", file=sys.stderr)
        return EXIT_ERROR

    # ── 节批量记账（两层模型改造点④：原子批量——任一未知/非法全批拒绝，bug-3048）──
    if args.sections:
        wanted = list(
            dict.fromkeys(x.strip() for x in args.sections.split(",") if x.strip())
        )  # 去重保序——重复 id 不重复记账
        if not wanted:
            print("[progress] --sections 为空", file=sys.stderr)
            return EXIT_ERROR
        resolved: list[tuple[str, dict]] = []
        unknown: list[str] = []
        for sid in wanted:
            hit = find_section(doc, sid)
            if hit is None:
                unknown.append(sid)
                continue
            resolved.append(hit)
        if unknown:
            inbook = [s.get("id") for _, s in iter_sections(doc)]
            print(f"[progress] 未知节 {unknown}（在册 {len(inbook)} 节，如 {inbook[:8]}…）", file=sys.stderr)
            return EXIT_ERROR
        illegal: list[str] = []
        for sid, (ch, ent) in zip(wanted, resolved):
            if status not in TRANSITIONS[ent["status"]]:
                illegal.append(f"{sid}: {ent['status']} → {status}")
        if illegal:
            print(f"[progress] 非法转移（批量原子拒绝，全批未动）: {'; '.join(illegal)}", file=sys.stderr)
            return EXIT_ERROR
        for sid, (ch, ent) in zip(wanted, resolved):
            ent["status"] = status
            if status == "DRAFTED":
                ent["dispatches"] = ent.get("dispatches", 0) + 1
                doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
            elif status == "BLOCKED":
                ent["note"] = args.detail or "节 BLOCKED"
            elif status == "ABSENT":
                ent["note"] = args.detail or "stage 条件开关驱动缺席"
            elif status == "PENDING":
                ent.pop("note", None)  # 开关回翻复位
        doc["phase"] = derive_phase_any(doc)
        save(state_dir, doc)
        print(f"MARKED_SECTIONS: {len(wanted)} 节 → {status}（{', '.join(wanted)}；phase={doc['phase']}）")
        return EXIT_OK

    # ── 章记账（geo 语义 + ABSENT）──
    ch_id = args.chapter
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    cur = doc["chapters"][ch_id]["status"]
    if status not in TRANSITIONS[cur]:
        print(
            f"[progress] 非法转移 {ch_id}: {cur} → {status}（合法: {cur} → {sorted(TRANSITIONS[cur])}）",
            file=sys.stderr,
        )
        return EXIT_ERROR
    ent = doc["chapters"][ch_id]
    if status == "REVIEWED" and ent.get("last_gate") != "PASS":
        # bug-4146 双保险：审查凭据=门凭据。正常链路 gate FAIL 已把 VERIFIED 回落 DRAFTED，
        # 此处拦手改 state 绕门（VERIFIED + last_gate=FAIL 的手改态）直达审查。
        print(
            f"[progress] {ch_id} 门凭据非 PASS（last_gate={ent.get('last_gate')}）——"
            f"重跑 `progress.py gate --chapters {ch_id}` 至 PASS 后再进审查",
            file=sys.stderr,
        )
        return EXIT_ERROR
    ent["status"] = status
    if status == "DRAFTED":
        ent["dispatches"] = ent.get("dispatches", 0) + 1
        doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
    elif status == "BLOCKED":
        ent["last_gate"] = args.gate or "FAIL"
        ent["gate_detail"] = args.detail or ""
        ent["blocked_reason"] = args.detail or ("门 FAIL 且重派耗尽" if args.gate != "PASS" else "派发额度耗尽")
    elif status == "ABSENT":
        # stage 条件开关驱动（双模式互换/可选章缺席）：章 ABSENT 级联其全部节 ABSENT
        # （门/组装/记账跳过同语义，两层状态模型）；开关回翻逐节 PENDING 复位（章内节状态按节回翻）。
        cascaded = 0
        for s in ent.get("sections", []):
            if s.get("status") != "ABSENT":
                s["status"] = "ABSENT"
                s["note"] = args.detail or f"章 {ch_id} 条件开关缺席级联"
                cascaded += 1
        ent["blocked_reason"] = args.detail or "stage 条件开关驱动缺席"
        doc["phase"] = derive_phase_any(doc)
        save(state_dir, doc)
        extra = f"，级联节 ABSENT {cascaded}" if cascaded else ""
        print(f"MARKED: {ch_id} {cur} → ABSENT（phase={doc['phase']}{extra}）")
        return EXIT_OK
    elif status == "REVIEWED":
        pass  # 审查收口不改门凭据——confirm-chapter 凭 last_gate=PASS 判定（bug-4146）
    else:  # PENDING（ABSENT 开关回翻——章回 PENDING，节按节回翻）
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
        flipped = 0
        for s in ent.get("sections", []):
            if s.get("status") == "ABSENT":
                s["status"] = "PENDING"
                s.pop("note", None)
                flipped += 1
        doc["phase"] = derive_phase_any(doc)
        save(state_dir, doc)
        extra = f"，级联节回 PENDING {flipped}" if flipped else ""
        print(f"MARKED: {ch_id} {cur} → PENDING（phase={doc['phase']}{extra}）")
        return EXIT_OK
    doc["phase"] = derive_phase_any(doc)
    save(state_dir, doc)
    print(f"MARKED: {ch_id} {cur} → {status}（phase={doc['phase']}）")
    return EXIT_OK


def _writeback_sections(doc: dict, ch_id: str) -> list[str]:
    """章门 PASS 自动回写节 VERIFIED（两层模型改造点②）：章作为门对象整体过门，
    其全部节随章转 VERIFIED（PENDING/DRAFTED→VERIFIED）；ABSENT 保持缺席；
    BLOCKED 节属罕见中间态，留原状由调用方 stderr 提示。返回未推进节 id。"""
    skipped: list[str] = []
    for s in doc["chapters"][ch_id].get("sections", []):
        if s.get("status") in ("PENDING", "DRAFTED"):
            s["status"] = "VERIFIED"
        elif s.get("status") == "BLOCKED":
            skipped.append(s.get("id", "?"))
    return skipped


def cmd_gate(args: argparse.Namespace) -> int:
    """批量单章门（平台预算规避，bug-3040/3048）：一次 bash 跑完全部指定章的门禁，
    PASS 章当场自动转 VERIFIED，并随章回写其全部节 VERIFIED（两层模型改造点②——
    节 VERIFIED 唯一通道，不变式不破：推进凭据就是 run_chapter_gate 无异常返回，
    progress.py 仍是 progress.json 唯一写者）。任一章 FAIL → stderr 打该章完整差距，
    不推进该章，rc=1。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if not doc.get("stage_path") or not doc.get("data_dir"):
        print(
            "[progress] progress.json 缺 stage_path/data_dir（init 须带 --stage 与 --data-dir 才能批量跑门）",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if args.chapters:
        wanted = [c.strip() for c in args.chapters.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in doc["chapters"]]
        if unknown:
            print(f"[progress] 未知章节 {unknown}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
            return EXIT_ERROR
    else:
        wanted = [c for c in chapter_order(doc["chapters"]) if doc["chapters"][c]["status"] == "DRAFTED"]
    if not wanted:
        print("[progress] 没有 DRAFTED 章（显式列表除外）——先按 next 指引派发", file=sys.stderr)
        return EXIT_ERROR
    stage = json.loads(Path(doc["stage_path"]).read_text(encoding="utf-8"))
    import build_output  # 同目录脚本；targets 语义与 build_output CLI 一致（--targets 仅调试）

    targets, _src = build_output.resolve_targets(
        args.targets, Path(doc["stage_path"]), data_dir=Path(doc["data_dir"])
    )  # EAI-CUSTOM (geo-sample-bank Phase 2 T4)
    passed: list[str] = []
    failed: list[str] = []

    def _fail(ch: str, msg: str) -> None:
        failed.append(ch)
        print(f"CHAPTER_GATE_FAIL: {ch}\n{msg}", file=sys.stderr)
        ent = doc["chapters"][ch]
        if ent["status"] not in ("VERIFIED", "REVIEWED"):
            return
        # bug-4146 门凭据时效不变式：last_gate 只代表「最近一次真跑门」——新门 FAIL 即旧 PASS
        # 凭据过期。VERIFIED 当场回落 DRAFTED（重写回路，默认门选章重新可见）；REVIEWED 状态不动
        # 但确认通道被 last_gate=FAIL 封死（重审由审查回路裁决）；CONFIRMED 终态不自动翻
        # （返工唯一出口 mark DRAFTED）。
        ent["last_gate"] = "FAIL"
        ent["gate_detail"] = msg.splitlines()[0][:200]
        if ent["status"] == "VERIFIED":
            ent["status"] = "DRAFTED"
            print(
                f"[progress] {ch} 门凭据失效：VERIFIED → DRAFTED（新门 FAIL，旧 PASS 过期）——重跑门至 PASS 再进审查",
                file=sys.stderr,
            )
        else:
            print(
                f"[progress] {ch} 门凭据失效：last_gate=FAIL（REVIEWED 确认通道已封死）——重跑门至 PASS 后重走审查",
                file=sys.stderr,
            )

    for ch in wanted:
        try:
            build_output.run_chapter_gate(stage, Path(doc["data_dir"]), state_dir, ch, targets)
            passed.append(ch)
        except ValueError as e:
            _fail(ch, str(e))
        except OSError as e:
            # coal-eia T1：冻结层缺失（formula_state.json 不存在）等文件级错误按该章门 FAIL 处理，
            # 不让 OSError 逃出批量门砸掉整批（geo 同路径会裸崩——两层模型下步骤2 先于步骤4 不再是隐含前提）。
            _fail(ch, f"文件级错误（冻结层/章稿缺失？先跑 run-stage freeze 或补齐产物）: {e}")
    skipped: list[str] = []
    for ch in passed:
        ent = doc["chapters"][ch]
        if "VERIFIED" not in TRANSITIONS[ent["status"]]:
            skipped.append(f"{ch}({ent['status']})")  # BLOCKED→VERIFIED 非法：先 mark DRAFTED 复活再跑门
            continue
        ent["status"] = "VERIFIED"
        ent["last_gate"] = "PASS"
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
        # 章门 PASS → 随章回写节 VERIFIED（唯一通道，改造点②）
        sec_skipped = _writeback_sections(doc, ch)
        if sec_skipped:
            print(
                f"[progress] {ch} 门过但节未推进（BLOCKED 节须先 mark --sections … DRAFTED 复活）: {sec_skipped}",
                file=sys.stderr,
            )
    doc["phase"] = derive_phase_any(doc)
    save(state_dir, doc)
    print(
        f"GATE_BATCH_DONE: passed={len(passed) - len(skipped)} failed={len(failed)}（failed: {', '.join(failed) or '无'}；skipped: {', '.join(skipped) or '无'}——stderr 逐条差距，原 prompt 重派 ≤1 次）"
    )
    if skipped:
        print(
            f"[progress] 门过但未推进（状态机不允许直接 {skipped}；先 mark DRAFTED 复活）: {skipped}", file=sys.stderr
        )
    return EXIT_ERROR if failed else EXIT_OK


def cmd_delivered(args: argparse.Namespace) -> int:
    """交付回执（D6）：交付子代理每波（≤5–10 节）write_chapter 后一次批量回执——
    节粒度禁逐节单发（bug-3048）。只接受 VERIFIED 节（交付起点=一致性 PASS 后，
    VERIFIED 是章门产物）；重复回执幂等（delivered 已真则 no-op）。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    wanted = [x.strip() for x in args.sections.split(",") if x.strip()]
    if not wanted:
        print("[progress] --sections 为空", file=sys.stderr)
        return EXIT_ERROR
    resolved: list[tuple[str, dict]] = []
    unknown: list[str] = []
    for sid in wanted:
        hit = find_section(doc, sid)
        if hit is None:
            unknown.append(sid)
            continue
        resolved.append(hit)
    if unknown:
        print(f"[progress] 未知节 {unknown}", file=sys.stderr)
        return EXIT_ERROR
    not_verified = [
        f"{sid}({ent['status']})" for sid, (ch, ent) in zip(wanted, resolved) if ent["status"] != "VERIFIED"
    ]
    if not_verified:
        print(
            f"[progress] 交付回执拒绝（仅 VERIFIED 节可交付，原子全批拒绝）: {'; '.join(not_verified)}", file=sys.stderr
        )
        return EXIT_ERROR
    fresh = 0
    for sid, (ch, ent) in zip(wanted, resolved):
        if not ent.get("delivered"):
            ent["delivered"] = True
            ent["delivery_wave"] = args.wave
            fresh += 1
    doc["phase"] = derive_phase_any(doc)
    save(state_dir, doc)
    print(f"DELIVERED_BATCH: wave={args.wave} fresh={fresh} idempotent={len(wanted) - fresh}（{', '.join(wanted)}）")
    return EXIT_OK


def _run_py(script: str, *cmd_args: str) -> int:
    """子进程跑同目录脚本，stdout/stderr 原样透传（BUILD_READY/CHAPTER_GATE_PASS 等交付粘贴行不丢失）。"""
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / script), *cmd_args]
    ).returncode


def cmd_run_stage(args: argparse.Namespace) -> int:
    """固定脚本序列合并为一次 bash（平台预算规避）：freeze = 冻结二连（manifest+execute），
    finalize = 组装→校验→快照三连。退出码逐步透传：build/manifest 1 即停；consistency 0/3
    继续（3=WARN/MANUAL，交付时汇报用户）、1/2 即停；snapshot 透传。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if not doc.get("stage_path") or not doc.get("data_dir"):
        print("[progress] progress.json 缺 stage_path/data_dir（init 须带 --stage 与 --data-dir）", file=sys.stderr)
        return EXIT_ERROR
    stage, data = doc["stage_path"], doc["data_dir"]
    if args.stage_name == "finalize" and not args.outputs_dir:
        print("[progress] run-stage finalize 需要 --outputs-dir（交付目录）", file=sys.stderr)
        return EXIT_ERROR
    if args.stage_name == "freeze":
        rc = _run_py(
            "chapter_planner.py", "manifest", "--stage", stage, "--output", str(state_dir / "chapter_manifest.json")
        )
        if rc:
            return rc
        print(
            "[run-stage] manifest OK → formula_runner execute（rc=3=有 anomalies，必须发卡逐条呈现用户确认）",
            file=sys.stderr,
        )
        freeze_cmd = [
            "formula_runner.py",
            "execute",
            "--stage",
            stage,
            "--data-dir",
            data,
            "--state-dir",
            str(state_dir),
        ]
        if args.chapters:
            # 目标章集切片冻结（bug-4143 方案A）：只冻目标章消费公式；缺省全量零变化
            freeze_cmd += ["--chapters", args.chapters]
        return _run_py(*freeze_cmd)
    # finalize：交付名唯一来源 = data/ 表单（expected_deliverable_name，与 build_output 交付名门同源）
    import build_output

    stage_doc = json.loads(Path(stage).read_text(encoding="utf-8"))
    report = Path(args.outputs_dir) / build_output.expected_deliverable_name(stage_doc, Path(data))
    blocked_approved = {c for c, s in doc["chapters"].items() if s["status"] == "BLOCKED"} & approved_set(doc)
    build_args = ["--stage", stage, "--data-dir", data, "--state-dir", str(state_dir), "--output", str(report)]
    if blocked_approved or args.allow_partial:
        build_args.append("--allow-partial")
        print(
            f"[run-stage] 分级交付模式（已批准降档 {sorted(blocked_approved)}——交付时如实汇报降档章节与差距）",
            file=sys.stderr,
        )
    rc = _run_py("build_output.py", *build_args)
    if rc:
        return rc
    # 复核修复（bug-3058）：build_output 内联门已按去附录正文（body scope）跑过 consistency 并写
    # consistency_check.json；此处再以完整报告重跑会以不同 scope 覆盖同一 JSON（附录文本/全文字数
    # 差异 → 汇总漂移、rc 语义漂移）。统一 scope：优先复用 body 文件（build 成功时必在），CLI rc 语义不变。
    _body = state_dir / "consistency_body.md"
    cons_args = [
        "--report",
        str(_body if _body.exists() else report),
        "--data-dir",
        data,
        "--stage",
        stage,
        "--state",
        str(state_dir / "formula_state.json"),
        "--output",
        str(state_dir / "consistency_check.json"),
    ]
    if STANDARDS_INDEX.exists():
        cons_args += ["--standards", str(STANDARDS_INDEX)]
    if CONTRACTS_INDEX.exists():
        cons_args += ["--contracts", str(CONTRACTS_INDEX)]
    rc = _run_py("consistency.py", *cons_args)
    if rc in (1, 2):
        return rc
    if rc == 3:
        print(
            "[run-stage] CONSISTENCY_RC3: 校验完成带 WARN/MANUAL——逐条汇报用户后再交付（state/consistency_check.json）",
            file=sys.stderr,
        )
    return _run_py(
        "snapshot.py",
        "save",
        "--task",
        args.task,
        "--stage",
        stage,
        "--data-dir",
        data,
        "--state-dir",
        str(state_dir),
        "--manifest",
        str(state_dir / "chapter_manifest.json"),
        "--formula-state",
        str(state_dir / "formula_state.json"),
        "--mapping",
        str(state_dir / "mapping.json"),
        "--report",
        str(report),
        "--output",
        str(Path(args.outputs_dir) / "project_snapshot.json"),
    )


def cmd_confirm(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    doc["key_points_confirmed"] = True
    doc["phase"] = derive_phase_any(doc)
    save(state_dir, doc)
    print(f"KEY_POINTS_CONFIRMED（phase={doc['phase']}）")
    return EXIT_OK


def cmd_plan_confirm(args: argparse.Namespace) -> int:
    """分章计划卡确认落盘（交互卡点·卡A）：state/plan_<ch>.json——卡面+用户补充意见+篇幅规模选择。
    写作前置确认凭据（红线 P13：无 plan 不开工）；幂等覆盖（补充意见修订回环=重发卡再确认）。
    depth 选择是 build_output 深度门的模式开关：full=详实版（推荐字数启用）/compact=精简版（不启用）/
    custom=用户指定字数。分章模式限定。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if doc.get("mode") != "chapter":
        print("[progress] plan-confirm 仅分章模式（init --mode chapter）——full 批量管线无计划卡", file=sys.stderr)
        return EXIT_ERROR
    ch_id = args.chapter
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    if args.depth == "custom" and not (args.target and args.target > 0):
        print("[progress] --depth custom 须带正整数 --target <字数>", file=sys.stderr)
        return EXIT_ERROR
    summary = Path(args.summary_file).read_text(encoding="utf-8").strip()
    plan = {
        "chapter": ch_id,
        "summary": summary,
        "notes": (args.notes or "").strip(),
        "depth": {"mode": args.depth, "target": args.target},
        "confirmed_at": datetime.now().isoformat(timespec="seconds"),
    }
    p = state_dir / f"plan_{ch_id}.json"
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    depth_desc = {
        "full": "详实版（篇幅目标启用）",
        "compact": "精简版（篇幅规则不启用，门如实注明）",
        "custom": f"自定义 {args.target} 字",
    }[args.depth]
    notes_desc = "；用户补充意见已记录" if plan["notes"] else "；无补充意见"
    print(f"PLAN_CONFIRMED: {ch_id}（篇幅: {depth_desc}{notes_desc}）→ 进资料汇集（门1 全局包）")
    return EXIT_OK


def cmd_fragment_choice(args: argparse.Namespace) -> int:
    """范例挑选落盘（交互卡点·卡B）：state/fragment_choice_<ch>.json——用户从 sample_fragments.py
    candidates 候选中选定的 report_id，或 --none 显式不用（红线 P10 禁的是 agent 自主跳过；
    用户显式豁免尊重，派发契约如实注明）。写作派发前置凭据（红线 P13：无 choice 不派发）；幂等覆盖。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if doc.get("mode") != "chapter":
        print("[progress] fragment-choice 仅分章模式（init --mode chapter）", file=sys.stderr)
        return EXIT_ERROR
    ch_id = args.chapter
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    if bool(args.report_id) == args.none:
        print("[progress] --report-id 与 --none 恰好传一个（选定范例或显式不用）", file=sys.stderr)
        return EXIT_ERROR
    choice = {
        "chapter": ch_id,
        "report_id": None if args.none else args.report_id,
        "chosen_at": datetime.now().isoformat(timespec="seconds"),
    }
    p = state_dir / f"fragment_choice_{ch_id}.json"
    p.write_text(json.dumps(choice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    choice_desc = "不参照范例（写法与篇幅把握打折，质量检查照常）" if args.none else f"范例报告 {args.report_id}"
    print(f"FRAGMENT_CHOICE: {ch_id} → {choice_desc} → 取包后进写作派发")
    return EXIT_OK


def cmd_confirm_chapter(args: argparse.Namespace) -> int:
    """分章模式确认卡（spec §3）：REVIEWED→CONFIRMED 唯一通道；本章 highlights 并入
    state/key_points.json（增量幂等——同章同要点重放 no-op 字节一致；要点变更须先
    mark DRAFTED 返工再走门与审查，禁越过门禁改确认）。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if doc.get("mode") != "chapter":
        print(
            "[progress] confirm-chapter 仅分章模式（init --mode chapter）——full 批量管线无逐章确认卡", file=sys.stderr
        )
        return EXIT_ERROR
    ch_id = args.chapter
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    highlights = [x.strip() for x in (args.highlights or "").split("|") if x.strip()]
    ent = doc["chapters"][ch_id]
    if ent["status"] == "CONFIRMED":
        if ent.get("highlights") == highlights:
            print(f"CONFIRMED_ALREADY: {ch_id}（幂等重放，未变更）")
            return EXIT_OK
        print(
            f"[progress] 非法转移 {ch_id}: CONFIRMED 已终态且要点变更——改确认卡先 mark {ch_id} DRAFTED 返工",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if ent["status"] != "REVIEWED":
        print(
            f"[progress] 非法转移 {ch_id}: {ent['status']} → CONFIRMED（合法: REVIEWED → CONFIRMED——章门 PASS 且审查收口后确认）",
            file=sys.stderr,
        )
        return EXIT_ERROR
    waived = ent.get("last_gate") != "PASS"
    if waived and ch_id not in approved_set(doc):
        # bug-4146：确认卡凭门凭据放行（last_gate=PASS）——凭据失效/缺失即拒绝；确要带缺陷确认，
        # 唯一豁免 = 用户显式降档批准（approve-downgrade 落盘为凭据），禁静默确认未过门的章。
        print(
            f"[progress] {ch_id} 门凭据非 PASS（last_gate={ent.get('last_gate')}）且无降档批准——"
            f"重跑 `progress.py gate --chapters {ch_id}` 至 PASS；确要带缺陷确认须用户先 "
            f"`progress.py approve-downgrade --chapters {ch_id} --note <原因>` 再确认",
            file=sys.stderr,
        )
        return EXIT_ERROR
    ent["status"] = "CONFIRMED"
    ent["highlights"] = highlights
    ent["blocked_reason"] = None
    kp_path = state_dir / "key_points.json"
    kp = json.loads(kp_path.read_text(encoding="utf-8")) if kp_path.exists() else {}
    kp.setdefault("chapters", {})[ch_id] = highlights
    kp_path.write_text(json.dumps(kp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    doc["phase"] = derive_phase_any(doc)
    save(state_dir, doc)
    print(
        f"CONFIRMED_CHAPTER: {ch_id}（highlights {len(highlights)} 条并入 state/key_points.json；phase={doc['phase']}"
        + ("；降档豁免——门凭据非 PASS，凭 approve-downgrade 放行）" if waived else "）")
    )
    return EXIT_OK


def cmd_approve(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    chs = [c.strip() for c in args.chapters.split(",") if c.strip()]
    unknown = [c for c in chs if c not in doc["chapters"]]
    if unknown:
        print(f"[progress] 未知章节 {unknown}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    doc.setdefault("downgrade_approvals", []).append(
        {
            "chapters": chs,
            "note": args.note or "",
            "approved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    doc["phase"] = derive_phase_any(doc)
    save(state_dir, doc)
    print(f"APPROVED: 降档批准 {chs}（累计批准集 {sorted(approved_set(doc))}，phase={doc['phase']}）")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — 两层状态机（章级门禁 × 节级派发，步骤4 控制器）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("init", help="按 stage 章节清单初始化 progress.json（章+节子表全 PENDING；已存在=续跑拒重置）")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--data-dir", help="记录数据目录（next 渲染精确命令用；缺省输出 <DATA> 占位）")
    sp.add_argument(
        "--mode",
        choices=["full", "chapter"],
        default="full",
        help="full=批量编排（缺省，行为零变化）；chapter=分章逐章管线（COLLECTING→gate→review→确认卡→下一章）",
    )
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("next", help="控制器每轮先读：恰好一个下一步动作 + 精确命令 + 期望 rc")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_next)
    sp = sub.add_parser("status", help="全章状态表（含节子表计数）+ 派发计数 + 额度余量")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser(
        "mark",
        help="状态转移（DRAFTED/BLOCKED/ABSENT/PENDING；REVIEWED 章级审查步）；VERIFIED 禁手动（唯一通道=gate）、CONFIRMED 禁手动（唯一通道=confirm-chapter）；章: mark <chN> <status>；节批量: mark --sections <csv> <status>（bug-3048）",
        epilog=(
            "用法全样例（status 是第二个位置参数，紧跟章 id）：\n"
            "  progress.py mark ch2 DRAFTED --state-dir state\n"
            '  progress.py mark ch2 BLOCKED --state-dir state --detail "重派耗尽"\n'
            "  progress.py mark --sections ch2_S01,ch2_S02 DRAFTED --state-dir state"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("chapter", nargs="?", help="章 id（与 --sections 二选一）")
    sp.add_argument("status")
    sp.add_argument("--sections", help="节 id 逗号清单批量记账（原子——任一未知/非法全批拒绝），如 ch6_S01,ch6_S02")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--gate", choices=["PASS", "FAIL"])
    sp.add_argument("--detail", default="")
    sp.set_defaults(fn=cmd_mark)
    sp = sub.add_parser(
        "gate",
        help="批量单章门：一次跑完全部（缺省）或指定章的门禁，PASS 章自动转 VERIFIED 并随章回写节 VERIFIED（两层模型改造点②——VERIFIED 唯一通道）",
        epilog=(
            "用法全样例（rc 须重定向后取，禁过管道）：\n"
            "  progress.py gate --state-dir state                # 全部 DRAFTED 章\n"
            "  progress.py gate --chapters ch2 --state-dir state\n"
            "  progress.py gate --chapters ch2 --state-dir state > /tmp/g.out 2>&1; echo rc=$?"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--chapters", help="逗号分隔，如 ch2,ch3；缺省=全部 DRAFTED 章")
    sp.add_argument("--targets", help="depth_targets.json 路径；仅调试，正式跑门绝不传（同 build_output 语义）")
    sp.set_defaults(fn=cmd_gate)
    sp = sub.add_parser(
        "delivered",
        help="交付回执：交付子代理按波批量回执节 delivered 布尔+交付波次（仅 VERIFIED 节；幂等；bug-3048 批量原语）",
    )
    sp.add_argument("--sections", required=True, help="节 id 逗号清单，如 ch1_S01,ch1_S02")
    sp.add_argument("--wave", type=int, required=True, help="交付波次（D6 分波回执）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_delivered)
    sp = sub.add_parser(
        "run-stage", help="固定脚本序列合并一次 bash：freeze=manifest+execute；finalize=build→consistency→snapshot"
    )
    sp.add_argument("stage_name", choices=["freeze", "finalize"])
    sp.add_argument(
        "--chapters",
        default=None,
        help="freeze 切片（bug-4143）：逗号分隔目标章 id（如 ch2,ch6）——只冻目标章消费公式；缺省=全量",
    )
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--outputs-dir", help="finalize 必填：交付目录（报告+project_snapshot.json 落这里）")
    sp.add_argument("--task", default="环评报告终验", help="snapshot last_task 一句话摘要")
    sp.add_argument("--allow-partial", action="store_true", help="强制分级交付（已批准降档时自动启用，无需显式传）")
    sp.set_defaults(fn=cmd_run_stage)
    sp = sub.add_parser("confirm-key-points", help="要点包已经用户单表单确认（解锁 ch13 结论章）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_confirm)
    sp = sub.add_parser(
        "confirm-chapter",
        help="分章模式确认卡：审查收口后用户确认本章（REVIEWED→CONFIRMED 唯一通道），highlights 并入 state/key_points.json（增量幂等）",
    )
    sp.add_argument("chapter", help="章 id，如 ch2")
    sp.add_argument("--highlights", default="", help="本章要点，| 分隔——并入 state/key_points.json 供 ch13 结论章引用")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_confirm_chapter)
    sp = sub.add_parser(
        "plan-confirm",
        help="分章计划卡确认落盘：state/plan_<ch>.json（卡面+用户补充意见+篇幅规模选择）——写作前置确认凭据（无 plan 不开工），幂等覆盖（修订版重确认）",
        epilog=(
            "用法全样例：\n"
            "  progress.py plan-confirm ch2 --summary-file state/plan_card_ch2.md --state-dir state\n"
            '  progress.py plan-confirm ch2 --summary-file state/plan_card_ch2.md --notes "补充: 需含村庄分布" --state-dir state\n'
            "  progress.py plan-confirm ch2 --summary-file state/plan_card_ch2.md --depth compact --state-dir state\n"
            "  progress.py plan-confirm ch2 --summary-file state/plan_card_ch2.md --depth custom --target 8000 --state-dir state"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("chapter", help="章 id，如 ch2")
    sp.add_argument("--summary-file", required=True, help="计划卡卡面 md 文件（内容原样存入 plan 工件）")
    sp.add_argument("--notes", default="", help="用户补充意见原文（修订回环取最新一版）")
    sp.add_argument(
        "--depth",
        choices=["full", "compact", "custom"],
        default="full",
        help="篇幅规模: full=详实版（推荐字数启用，缺省）/compact=精简版（篇幅规则不启用）/custom=用户指定字数",
    )
    sp.add_argument("--target", type=int, help="custom 模式目标字数（正整数，--depth custom 必带）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_plan_confirm)
    sp = sub.add_parser(
        "fragment-choice",
        help="范例挑选落盘：state/fragment_choice_<ch>.json——用户从 sample_fragments.py candidates 候选选定的 report_id（或 --none 显式不用）——派发前置凭据（无 choice 不派发）",
        epilog=(
            "用法全样例：\n"
            "  progress.py fragment-choice ch2 --report-id 2201 --state-dir state\n"
            "  progress.py fragment-choice ch2 --none --state-dir state"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("chapter", help="章 id，如 ch2")
    sp.add_argument("--report-id", help="候选卡中用户选定的报告 id（与 --none 二选一）")
    sp.add_argument("--none", action="store_true", help="用户选择不参照范例（派发契约如实注明，质量检查照常）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_fragment_choice)
    sp = sub.add_parser("approve-downgrade", help="记录用户批准的降档（--allow-partial 放行凭据）")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--chapters", required=True, help="逗号分隔，如 ch3,ch8")
    sp.add_argument("--note", default="")
    sp.set_defaults(fn=cmd_approve)
    args = p.parse_args()
    try:
        return args.fn(args)
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
        print(f"[progress] progress.json/stage 文件损坏或不可读（手改特征或路径错误）: {e!r}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
