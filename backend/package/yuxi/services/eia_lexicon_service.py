"""环评数值护栏词表运营服务（DB 覆盖层 + overrides 物化）。

分层（设计：docs/vibe/2026-10-09-eia-lexicon-stack.md；上游架构 docs/design/eia-data-factory.md §4）：
  - DB（eia_lexicon_entries / eia_dataset_switches）= 运营唯一真相
  - 显式「导出物化」→ references/overrides/curated_lexicon.json（gitignored 运行态）
  - bank_compile 文件存在即消费；开关关闭即删文件 → 管线回到 builtin 字节级行为
语义要点：
  - 导入幂等：existing 指纹一律跳过（绝不覆盖人工决策），只补新增
  - 导出重算：常规条目 range 从 slices 现算（不信任 DB 快照）；
    拆分子条目用页面裁决值集（子口径不在语料中逐字出现，重算必为空）
  - 区间门槛/分位数语义全部动态取自 bank_compile（口径单一真源）
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_lexicon_repository import EiaLexiconRepository
from yuxi.services.eia_data_service import (
    _SKILL_ROOT,
    _iter_mentions,
    _scan_all,
    collect_mention_details,
)
from yuxi.storage.postgres.models_domain_factory import EiaLexiconEntry, _LEXICON_BLOCKLIST_SEED
from yuxi.utils import logger
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive

OVERRIDES_PATH = _SKILL_ROOT / "references" / "overrides" / "curated_lexicon.json"
_SKILL_REFS = _SKILL_ROOT / "references"
CURATED_LEXICON_KEY = "curated_lexicon"

# 导入预置状态（2026-10-09 用户裁决）：A 类直接入选 / B 类候选待业务确认 / C 类留档；
# 「控制效率」值簇语义混叠（不同设备的效率混在同一口径），直接发布会产生混杂区间，须先拆分
_IMPORT_STATUS = {"measure": "approved", "site": "candidate", "junk": "rejected"}
_SPLIT_CALIBERS = {"控制效率"}

# 导入抑制（2026-10-10 方案B 裁决 + P4 对话框延续）：已改名条目的旧断章指纹，重扫不再
# 复活（measure 类会按预置直接回 approved）。种子 7 条由 v13 迁移播种进抑制表，UI 改名
# 继续自动登记运行态行——导入判跳过一律查 DB（suppressed_keys），本常量仅为种子的同名
# 再导出（钉单测全集，防新装库漏种复活；常量放 models 层因 manager 迁移播种要读，留在
# service 会成 import 环）。指纹级屏蔽把「重扫复活」变成可断言行为；语料若出现同名新
# 句式需复评，删除对应抑制行即可。
_IMPORT_BLOCKLIST: set[tuple[str, str, str]] = {(s["stage"], s["caliber"], s["unit"]) for s in _LEXICON_BLOCKLIST_SEED}
_IMPORT_NOTE = {
    "approved": "措施效率类自动入选（导入预置）",
    "candidate": "现状监测类候选待业务确认",
    "rejected": "非护栏杂项留档（默认视图隐藏）",
    "splitting": "控制效率须先拆分（值簇语义混叠）",
}

# PATCH 可直接流转的状态（splitting → approved 禁止：入选必须经拆分携带值集）
_PATCHABLE_STATUS = {"candidate", "approved", "rejected"}


@lru_cache(maxsize=1)
def _load_bank_compile():
    """动态加载 bank_compile 模块（QUANTITY_RE / _pctl / RANGE_MIN_REPORTS 单一口径真源）。"""
    path = _SKILL_ROOT / "scripts" / "bank_compile.py"
    spec = importlib.util.spec_from_file_location("coal_eia_bank_compile_lexicon", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _preset_status(category: str, caliber: str) -> str:
    """导入预置状态（纯函数）：控制效率→splitting，其余按三分类映射。"""
    if caliber in _SPLIT_CALIBERS:
        return "splitting"
    return _IMPORT_STATUS[category]


def collect_mentions(stage: str, caliber: str, unit: str) -> list[dict[str, Any]]:
    """(stage, caliber, unit) 在切片中的原始提及清单（拆分对话框素材），路径序确定。"""
    return [
        {"rid": rid, "value": value, "unit": u}
        for s, rid, cal, u, value in _iter_mentions()
        if s == stage and cal == caliber and u == unit
    ]


def collect_stage_values() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], dict[str, Any]]]:
    """全语料首见单位表 + (stage, caliber, unit) 值聚合（导出重算输入）。"""
    first_unit: dict[tuple[str, str], str] = {}
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for stage, rid, caliber, unit, value in _iter_mentions():
        first_unit.setdefault((stage, caliber), unit)
        ent = agg.setdefault((stage, caliber, unit), {"rids": set(), "vals": []})
        ent["rids"].add(rid)
        ent["vals"].append(value)
    return first_unit, agg


def _build_range(vals: list[float], n_reports: int) -> dict[str, Any] | None:
    """语料区间护栏：distinct 报告数门槛与 P5/P50/P95 分位数语义取自 bank_compile。"""
    mod = _load_bank_compile()
    if n_reports < mod.RANGE_MIN_REPORTS or not vals:
        return None
    return {
        "p5": mod._pctl(vals, 0.05),
        "p50": mod._pctl(vals, 0.5),
        "p95": mod._pctl(vals, 0.95),
        "n_values": len(vals),
        "n_reports": n_reports,
    }


class EiaLexiconService:
    """数值护栏词表运营服务：导入 / 确认流 / 拆分 / 开关 / 导出物化。"""

    def __init__(self) -> None:
        self.repo = EiaLexiconRepository()

    # ── 导入 ──

    async def import_entries(self) -> dict[str, Any]:
        """重扫语料幂等导入：existing 指纹一律跳过（绝不覆盖人工决策），只补新增。

        改名条目的旧断章指纹查 DB 抑制表一并跳过（复活抑制，可断言）。"""
        cands = await run_in_threadpool(_scan_all)
        existing = await self.repo.existing_keys()
        suppressed = await self.repo.suppressed_keys()
        fresh: list[EiaLexiconEntry] = []
        blocked = 0
        for c in cands:
            key = (c["stage"], c["caliber"], c["unit"])
            if key in existing:
                continue
            if key in suppressed:
                blocked += 1
                continue
            status = _preset_status(c["category"], c["caliber"])
            fresh.append(
                EiaLexiconEntry(
                    stage=c["stage"],
                    caliber=c["caliber"],
                    unit=c["unit"],
                    category=c["category"],
                    status=status,
                    note=_IMPORT_NOTE[status],
                    decided_by="import",
                    decided_at=utc_now_naive(),
                )
            )
        if fresh:
            await self.repo.add_entries(fresh)
        logger.info(f"[eia-lexicon] 导入完成：扫描 {len(cands)} 候选，新增 {len(fresh)} 条，抑制 {blocked} 条")
        return {"scanned": len(cands), "added": len(fresh), "blocklist_skipped": blocked}

    # ── 查询 ──

    async def list_entries(
        self,
        stage: str | None = None,
        category: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """全量条目 + 语料实时计数 + 范式字段可映射性（forms_field，与编译器同判）。"""
        entries = await self.repo.list_entries()
        scan_index = {(c["stage"], c["caliber"], c["unit"]): c for c in await run_in_threadpool(_scan_all)}
        bank = _load_bank_compile()
        label_map = bank.build_label_map(_SKILL_REFS)
        counts = Counter(e.status for e in entries)
        items: list[dict[str, Any]] = []
        for e in entries:
            if stage and e.stage != stage:
                continue
            if category and e.category != category:
                continue
            if status and e.status != status:
                continue
            if q and q.lower() not in e.caliber.lower():
                continue
            d = e.to_dict()
            c = scan_index.get((e.stage, e.caliber, e.unit), {})
            d["n_reports"] = c.get("n_reports", 0)
            d["n_values"] = c.get("n_values", 0)
            d["range_ready"] = bool(c.get("range_ready"))
            mapped = bank._map_caliber(e.caliber, label_map)
            d["forms_field"] = mapped[1] if mapped else None
            items.append(d)
        return {
            "items": items,
            "total": len(items),
            "counts": {k: counts.get(k, 0) for k in ("candidate", "approved", "rejected", "splitting")},
        }

    async def get_mentions(self, entry_id: int) -> dict[str, Any]:
        """条目语境素材（拆分/改名对话框）：mentions 行为 [before, hit, after] 三段文本。

        改名行新名非语料逐字出现（机制必然零命中）时回落旧指纹语境（source=
        old_fingerprint），按 (stage, unit, new_caliber=本行名) 反查抑制表。"""
        entry = await self.repo.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"条目不存在: {entry_id}")
        details = await run_in_threadpool(collect_mention_details, entry.stage, entry.caliber, entry.unit)
        source = "current"
        if not details:
            old = await self.repo.find_fingerprint_suppression(entry.stage, entry.unit, entry.caliber)
            if old is not None:
                details = await run_in_threadpool(collect_mention_details, old.stage, old.caliber, entry.unit)
                source = "old_fingerprint"
        return {"entry": entry.to_dict(), "source": source, "mentions": details}

    # ── 确认流 ──

    async def update_entry(self, entry_id: int, patch: dict[str, Any], username: str) -> dict[str, Any]:
        entry = await self.repo.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"条目不存在: {entry_id}")
        if "status" in patch:
            status = patch["status"]
            if status not in _PATCHABLE_STATUS:
                raise ValueError(f"非法状态 {status!r}（splitting 仅可经拆分动作进入子口径）")
            if entry.status == "splitting" and status == "approved":
                raise ValueError("splitting 条目须先完成拆分（子口径携带值集）方可入选；放弃拆分请驳回")
            entry.status = status
            entry.decided_by = username
            entry.decided_at = utc_now_naive()
        if "note" in patch:
            entry.note = patch["note"]
        if "caliber" in patch:
            new = str(patch["caliber"]).strip()
            if len(new) < 2:
                raise ValueError("口径名过短")
            if entry.status == "splitting":
                raise ValueError("splitting 条目不可改名（须先完成拆分；放弃拆分请驳回）")
            if new != entry.caliber:
                if new in _SPLIT_CALIBERS:
                    raise ValueError(f"「{new}」为拆分专用口径名，禁止用作普通口径名")
                clash = await self.repo.find_key(entry.stage, new, entry.unit)
                if clash is not None and clash.id != entry.id:
                    raise ValueError(f"口径已存在: {entry.stage}/{new}/{entry.unit}")
                # 先插抑制、后落库改名（session-per-call 两事务）：抑制失败时改名不落地。
                # 旧指纹自动入抑制清单，重扫导入不再复活断章名（方案B 机制教训）
                await self.repo.add_suppression(
                    stage=entry.stage,
                    caliber=entry.caliber,
                    unit=entry.unit,
                    new_caliber=new,
                    reason=f"改名抑制：{entry.caliber} → {new}",
                    created_by=username,
                )
                entry.caliber = new
                entry.decided_by = username
                entry.decided_at = utc_now_naive()
        await self.repo.save_entry(entry)
        return entry.to_dict()

    async def split_entry(self, entry_id: int, items: list[dict[str, Any]], username: str) -> dict[str, Any]:
        """拆分：1 条 splitting → N 条 approved 子条目（携带裁决值集）+ 原条目 rejected。"""
        entry = await self.repo.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"条目不存在: {entry_id}")
        if entry.status != "splitting":
            raise ValueError(f"仅 splitting 状态条目可拆分（当前 {entry.status}）")
        if not items:
            raise ValueError("拆分至少需要一条子口径")

        existing = await self.repo.existing_keys()
        clean_items: list[tuple[str, str | None, list[dict[str, Any]]]] = []
        seen: set[str] = set()
        for it in items:
            cal = str(it.get("caliber") or "").strip()
            if len(cal) < 2:
                raise ValueError(f"子口径名过短: {cal!r}")
            if (entry.stage, cal, entry.unit) in existing or cal in seen:
                raise ValueError(f"子口径重复或已存在: {cal}")
            vals = it.get("values")
            if not isinstance(vals, list) or not vals:
                raise ValueError(f"子口径「{cal}」缺少值集")
            clean_vals: list[dict[str, Any]] = []
            for v in vals:
                rid = str(v.get("rid") or "").strip()
                try:
                    value = float(v["value"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"子口径「{cal}」值集含非法项: {v!r}") from exc
                if not rid:
                    raise ValueError(f"子口径「{cal}」值集含缺 rid 项")
                clean_vals.append({"rid": rid, "value": value})
            seen.add(cal)
            clean_items.append((cal, it.get("note"), clean_vals))

        for cal, note, clean_vals in clean_items:
            await self.repo.add_entry(
                EiaLexiconEntry(
                    stage=entry.stage,
                    caliber=cal,
                    unit=entry.unit,
                    category=entry.category,
                    status="approved",
                    values_json=clean_vals,
                    note=note or f"自「{entry.caliber}」拆分",
                    decided_by=username,
                    decided_at=utc_now_naive(),
                )
            )
        entry.status = "rejected"
        entry.decided_by = username
        entry.decided_at = utc_now_naive()
        entry.note = f"已拆分为 {len(clean_items)} 条子口径"
        await self.repo.save_entry(entry)
        logger.info(f"[eia-lexicon] 拆分 {entry.stage}/{entry.caliber} → {len(clean_items)} 条子口径")
        return {"parent_id": entry_id, "children": len(clean_items)}

    # ── 抑制名单 ──

    async def list_suppressions(self) -> dict[str, Any]:
        """抑制行全量列表（改名自动登记 + 手工登记 + 迁移种子）。"""
        items = await self.repo.list_suppressions()
        return {"items": [s.to_dict() for s in items], "total": len(items)}

    async def scan_candidates(self) -> dict[str, Any]:
        """重扫导入将带进来的候选差集（添加抑制下拉数据源）：_scan_all − 已入库 − 已抑制。"""
        cands = await run_in_threadpool(_scan_all)
        existing = await self.repo.existing_keys()
        suppressed = await self.repo.suppressed_keys()
        skip = existing | suppressed
        items = [c for c in cands if (c["stage"], c["caliber"], c["unit"]) not in skip]
        return {"items": items, "total": len(items)}

    async def add_suppression(self, payload: dict[str, Any], username: str) -> dict[str, Any]:
        """手工登记抑制：仅限扫描差集内的候选指纹——屏蔽语料中不存在的指纹永不生效，
        属误操作须报错而非静默吞掉；已抑制指纹幂等刷新（repo upsert）；手工行
        new_caliber=''，无语境回落（无改名目标即无回落，语义自洽）。"""
        stage = str(payload.get("stage") or "").strip()
        caliber = str(payload.get("caliber") or "").strip()
        unit = str(payload.get("unit") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if not stage or not caliber:
            raise ValueError("stage 与 caliber 必填")
        cands = await run_in_threadpool(_scan_all)
        if (stage, caliber, unit) not in {(c["stage"], c["caliber"], c["unit"]) for c in cands}:
            raise ValueError(f"指纹不在语料扫描结果中，抑制无效果: {stage}/{caliber}/{unit}")
        if (stage, caliber, unit) in await self.repo.existing_keys():
            raise ValueError(f"该指纹已是词表条目，请在词条上直接操作: {stage}/{caliber}/{unit}")
        await self.repo.add_suppression(
            stage=stage, caliber=caliber, unit=unit, new_caliber="", reason=reason, created_by=username
        )
        logger.info(f"[eia-lexicon] 手工登记抑制 {stage}/{caliber}/{unit}（{username}）")
        return {"success": True}

    async def withdraw_suppression(self, suppression_id: int, username: str) -> dict[str, Any]:
        """撤回抑制（硬删行，无补种机制）：重扫可能复活旧指纹，UI 撤回前须明示两条后果。"""
        row = await self.repo.get_suppression(suppression_id)
        if row is None:
            raise KeyError(f"抑制行不存在: {suppression_id}")
        await self.repo.delete_suppression(suppression_id)
        logger.info(f"[eia-lexicon] 撤回抑制 {row.stage}/{row.caliber}/{row.unit}（{username}）")
        return row.to_dict()

    # ── 开关与导出 ──

    async def get_switches(self) -> list[dict[str, Any]]:
        switches = {s.dataset_key: s for s in await self.repo.list_switches()}
        s = switches.get(CURATED_LEXICON_KEY)
        return [
            {
                "dataset_key": CURATED_LEXICON_KEY,
                "enabled": bool(s.enabled) if s else False,
                "overrides_file": OVERRIDES_PATH.is_file(),
                "updated_by": s.updated_by if s else None,
                "updated_at": format_utc_datetime(s.updated_at) if s else None,
            }
        ]

    async def set_switch(self, dataset_key: str, enabled: bool, username: str) -> dict[str, Any]:
        if dataset_key != CURATED_LEXICON_KEY:
            raise ValueError(f"未知数据集开关: {dataset_key}")
        switch = await self.repo.save_switch(dataset_key, enabled, username)
        if not enabled and OVERRIDES_PATH.is_file():
            OVERRIDES_PATH.unlink()
            logger.info(f"[eia-lexicon] 关闭 {dataset_key}：物化文件已删除（管线回到 builtin）")
        return {**switch.to_dict(), "overrides_file": OVERRIDES_PATH.is_file()}

    async def export_overrides(self, username: str) -> dict[str, Any]:
        """物化 approved 条目 → overrides 文件 + 开关置位。range 一律现算（不信任 DB 快照）。

        未映射范式表单字段的条目一并跳过（与 bank_compile 的 curated 消费同判）——否则条目
        入了覆盖层也会在编译时被静默丢弃，页面却显示正常。"""
        entries = sorted(
            (e for e in await self.repo.list_entries() if e.status == "approved"),
            key=lambda x: (x.stage, x.caliber, x.unit),
        )
        if not entries:
            raise ValueError("无 approved 条目可导出：请先在词表页完成确认")
        first_unit, agg = await run_in_threadpool(collect_stage_values)

        doc_entries: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        bank = _load_bank_compile()
        label_map = bank.build_label_map(_SKILL_REFS)
        for e in entries:
            if bank._map_caliber(e.caliber, label_map) is None:
                skipped.append(
                    {
                        "stage": e.stage,
                        "caliber": e.caliber,
                        "unit": e.unit,
                        "reason": "未映射范式表单字段（编译时会跳过）",
                    }
                )
                continue
            reason: str | None = None
            vals: list[float] = []
            rids: set[str] = set()
            if e.values_json:  # 拆分子条目：值集来自页面裁决
                vals = [float(v["value"]) for v in e.values_json]
                rids = {str(v["rid"]) for v in e.values_json}
            else:
                fu = first_unit.get((e.stage, e.caliber))
                ent = agg.get((e.stage, e.caliber, e.unit))
                if fu != e.unit:
                    reason = f"语料首见单位已变为 {fu!r}（跨单位不混布）"
                elif ent is None:
                    reason = "语料中已无该口径提及"
                else:
                    vals, rids = ent["vals"], ent["rids"]
            rng = None if reason else _build_range(vals, len(rids))
            if reason is None and rng is None:
                reason = f"distinct 报告数不足（{len(rids)} < {_load_bank_compile().RANGE_MIN_REPORTS}）"
            if reason:
                skipped.append({"stage": e.stage, "caliber": e.caliber, "unit": e.unit, "reason": reason})
                continue
            doc_entries.append({"stage": e.stage, "caliber": e.caliber, "unit": e.unit, "range": rng})

        if not doc_entries:
            raise ValueError("导出失败：无任何 approved 条目满足发布门槛（distinct 报告数 ≥ 5）")
        doc = {
            "version": 1,
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": "eia_lexicon_entries",
            "entries": doc_entries,
        }
        OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDES_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        await self.repo.save_switch(CURATED_LEXICON_KEY, True, username)
        logger.info(f"[eia-lexicon] 导出物化 {len(doc_entries)} 条 → {OVERRIDES_PATH.name}（跳过 {len(skipped)}）")
        return {
            "materialized": len(doc_entries),
            "skipped": skipped,
            "path": "references/overrides/curated_lexicon.json",
        }


_service: EiaLexiconService | None = None


def get_eia_lexicon_service() -> EiaLexiconService:
    global _service
    if _service is None:
        _service = EiaLexiconService()
    return _service
