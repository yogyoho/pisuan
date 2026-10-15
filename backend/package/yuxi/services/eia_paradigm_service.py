"""写作范式层编辑服务（s12/s13：DB 草稿=编辑唯一真相 + admin 导出物化回写 references/paradigms/*）。

编辑边界（2026-10-14 设计）：paradigm md 整文件草稿；forms_catalog 仅 desc/templates 两键
（stats/examples 为 bank_compile 语料统计只读）；_roles.json 只读。导出 validate-all-then-write：
锚点小节 / forms 两键形状 / 专名扫描任一不过 → 全批不写。写入字节纪律：forms 走整文件
json round-trip（indent=2 + 结尾换行，与现文件逐字节恒等）仅改两键，键序不重排；md 整文件
写回。base_hash 为存草稿时文件 sha256，导出前重算比对 → drift 标记（不阻断，admin 确认
diff 即以草稿为准恢复）。线程池内只做文件 IO；DB 行进池前先摊平为纯数据元组。
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.concurrency import run_in_threadpool

from yuxi.repositories.eia_paradigm_repository import EiaParadigmRepository
from yuxi.services import eia_paradigm_scan
from yuxi.services.eia_data_service import _SKILL_ROOT
from yuxi.utils import logger

_PARADIGM_DIR = _SKILL_ROOT / "references" / "paradigms"
KIND_MD = "paradigm_md"
KIND_FORMS = "forms_catalog"
KINDS = (KIND_MD, KIND_FORMS)
PARADIGM_IDS = ("opener", "baseline", "analysis", "measures")
FAMILY_IDS = ("caliber_disambiguation", "numeric_citation", "table_lead")
ANCHORS = ("## 适用", "## 结构骨架", "## 范文", "## 节尾收束段", "## 句式模式", "## 反模式")

# 草稿行进线程池前的纯数据形态：(kind, asset_id, content, base_hash, updated_by, updated_at)


def _md_file(asset_id: str) -> Path:
    return _PARADIGM_DIR / f"{asset_id}.md"


def _asset_path(kind: str, asset_id: str) -> Path:
    if kind == KIND_MD:
        return _md_file(asset_id)
    return _PARADIGM_DIR / "forms_catalog.json"


def _known_asset(kind: str, asset_id: str) -> None:
    if kind not in KINDS:
        raise KeyError(f"未知资产类型: {kind}")
    if kind == KIND_MD and asset_id not in PARADIGM_IDS:
        raise KeyError(f"未知资产: {asset_id}")
    if kind == KIND_FORMS and asset_id not in FAMILY_IDS:
        raise KeyError(f"未知资产: {asset_id}")


def _read_text(path) -> str:
    if not path.exists():
        raise KeyError(f"数据文件未找到: {path}")
    return path.read_text(encoding="utf-8", newline="")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_md(text: str) -> list[str]:
    """锚点小节在位（前缀匹配——范文/反模式标题带括号后缀）。"""
    return [f"锚点小节缺失: {a}" for a in ANCHORS if not any(line.startswith(a) for line in text.splitlines())]


def _load_forms_doc(text: str) -> dict:
    doc = json.loads(text)
    if not isinstance(doc.get("forms"), dict):
        raise ValueError("forms_catalog.json 结构异常：缺 forms 对象")
    return doc


def _validate_forms_content(asset_id: str, content: dict) -> None:
    extra = set(content) - {"desc", "templates"}
    if extra:
        raise ValueError(f"{asset_id}: 草稿仅接受 desc/templates 两键（stats/examples 只读），多余键: {sorted(extra)}")
    if not isinstance(content.get("desc"), str) or not content["desc"].strip():
        raise ValueError(f"{asset_id}: desc 必须为非空字符串")
    tpls = content.get("templates")
    if not isinstance(tpls, list) or not tpls or not all(isinstance(t, str) and t.strip() for t in tpls):
        raise ValueError(f"{asset_id}: templates 必须为非空字符串数组")


def _splice_forms(text: str, drafts: dict[str, dict]) -> tuple[str, bool]:
    """仅替换有草稿 family 的 desc/templates 两键；json round-trip 保证其余字节不动。"""
    doc = _load_forms_doc(text)
    for fid, content in drafts.items():
        fam = doc["forms"][fid]
        fam["desc"] = content["desc"]
        fam["templates"] = content["templates"]
    new_text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return new_text, new_text != text


def _unified_diff(name: str, old: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), fromfile=f"{name}: 文件", tofile=f"{name}: 草稿", lineterm=""
        )
    )


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


class EiaParadigmService:
    """范式层：overview / get / save_draft / withdraw_draft / preview_export / export_paradigms。"""

    def __init__(self, repo: EiaParadigmRepository | None = None):
        self.repo = repo or EiaParadigmRepository()

    @staticmethod
    def _flatten(rows) -> list[tuple]:
        """ORM 行/SimpleNamespace 行 → 纯数据元组（进线程池前摊平，池内不触 DB 对象）。"""
        return [(d.asset_kind, d.asset_id, d.content, d.base_hash, d.updated_by, d.updated_at) for d in rows]

    # ── 查询 ──

    async def load_overview(self) -> dict[str, Any]:
        rows = self._flatten(await self.repo.list_drafts())
        return await run_in_threadpool(self._overview_sync, rows)

    def _overview_sync(self, rows: list[tuple]) -> dict[str, Any]:
        drafts = {(k, a): (c, h, ub) for k, a, c, h, ub, _ua in rows}
        roles = json.loads(_read_text(_PARADIGM_DIR / "_roles.json"))
        role_map = {k: v for k, v in roles.items() if not k.startswith("_")}
        counts = {r: sum(1 for v in role_map.values() if v == r) for r in PARADIGM_IDS}
        forms_text = _read_text(_PARADIGM_DIR / "forms_catalog.json")
        forms_doc = _load_forms_doc(forms_text)
        forms_hash = _sha(forms_text)
        paradigms = []
        for aid in PARADIGM_IDS:
            d = drafts.get((KIND_MD, aid))
            fh = _sha(_read_text(_md_file(aid)))
            paradigms.append(
                {
                    "kind": KIND_MD,
                    "asset_id": aid,
                    "has_draft": d is not None,
                    "drift": bool(d) and d[1] != fh,
                    "updated_by": d[2] if d else None,
                    "file_hash": fh,
                }
            )
        families = []
        for fid in FAMILY_IDS:
            d = drafts.get((KIND_FORMS, fid))
            fam = forms_doc["forms"][fid]
            families.append(
                {
                    "kind": KIND_FORMS,
                    "asset_id": fid,
                    "desc": fam.get("desc", ""),
                    "templates": fam.get("templates", []),
                    "has_draft": d is not None,
                    "drift": bool(d) and d[1] != forms_hash,
                    "updated_by": d[2] if d else None,
                }
            )
        return {"paradigms": paradigms, "families": families, "role_counts": counts, "roles_map": role_map}

    async def get_asset(self, kind: str, asset_id: str) -> dict[str, Any]:
        _known_asset(kind, asset_id)
        rows = self._flatten(await self.repo.list_drafts())
        return await run_in_threadpool(self._get_sync, kind, asset_id, rows)

    def _get_sync(self, kind: str, asset_id: str, rows: list[tuple]) -> dict[str, Any]:
        drafts = {(k, a): (c, h, ub, ua) for k, a, c, h, ub, ua in rows}
        text = _read_text(_asset_path(kind, asset_id))
        fh = _sha(text)
        d = drafts.get((kind, asset_id))
        out: dict[str, Any] = {
            "kind": kind,
            "asset_id": asset_id,
            "file_hash": fh,
            "drift": bool(d) and d[1] != fh,
            "draft": (
                {
                    "content": d[0],
                    "base_hash": d[1],
                    "updated_by": d[2],
                    "updated_at": d[3].isoformat() if hasattr(d[3], "isoformat") else d[3],
                }
                if d
                else None
            ),
        }
        if kind == KIND_MD:
            out["file_text"] = text
        else:
            fam = _load_forms_doc(text)["forms"][asset_id]
            out["family"] = {k: fam.get(k) for k in ("desc", "templates", "examples", "stats")}
        return out

    # ── 草稿 ──

    async def save_draft(self, kind: str, asset_id: str, content: dict, username: str) -> dict[str, Any]:
        _known_asset(kind, asset_id)
        if kind == KIND_MD:
            md = content.get("md") if isinstance(content, dict) else None
            if not isinstance(md, str) or not md.strip():
                raise ValueError("md 草稿不能为空")
            clean = {"md": md}
        else:
            _validate_forms_content(asset_id, content)
            clean = {"desc": content["desc"], "templates": content["templates"]}
        base_hash = await run_in_threadpool(lambda: _sha(_read_text(_asset_path(kind, asset_id))))
        row = await self.repo.upsert_draft(kind, asset_id, clean, base_hash, username)
        logger.info(f"[eia-paradigm] 草稿落库 {kind}/{asset_id}（by {username}）")
        return {"asset_kind": kind, "asset_id": asset_id, "base_hash": row.base_hash, "updated_by": username}

    async def withdraw_draft(self, kind: str, asset_id: str) -> bool:
        _known_asset(kind, asset_id)
        return await self.repo.delete_draft(kind, asset_id)

    # ── 导出（validate-all-then-write） ──

    async def preview_export(self) -> dict[str, Any]:
        rows = self._flatten(await self.repo.list_drafts())
        return await run_in_threadpool(self._preview_from_rows, rows)

    def _preview_from_rows(self, rows: list[tuple]) -> dict[str, Any]:
        drafts = {(k, a): (c, h) for k, a, c, h, _ub, _ua in rows}
        items: list[dict[str, Any]] = []
        forms_drafts = {aid: c for (k, aid), (c, _h) in drafts.items() if k == KIND_FORMS}
        for aid in PARADIGM_IDS:
            if (KIND_MD, aid) not in drafts:
                continue
            content, base_hash = drafts[(KIND_MD, aid)]
            old = _read_text(_md_file(aid))
            new = content["md"]
            errors = _validate_md(new)
            hits = eia_paradigm_scan.scan_text(new)
            if hits:
                errors.append(f"专名扫描命中（须去实体化）: {hits}")
            items.append(
                {
                    "kind": KIND_MD,
                    "asset_id": aid,
                    "drift": base_hash != _sha(old),
                    "ok": not errors,
                    "errors": errors,
                    "diff": _unified_diff(f"{aid}.md", old, new),
                }
            )
        if forms_drafts:
            old = _read_text(_PARADIGM_DIR / "forms_catalog.json")
            forms_hash = _sha(old)
            drift = any(h != forms_hash for (k, _a), (_c, h) in drafts.items() if k == KIND_FORMS)
            try:
                new, changed = _splice_forms(old, forms_drafts)
                diff = _unified_diff("forms_catalog.json", old, new) if changed else ""
                errors: list[str] = []
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                new, changed, diff, errors = None, False, "", [f"forms_catalog 拼装失败: {e}"]
            items.append(
                {
                    "kind": KIND_FORMS,
                    "asset_id": "、".join(sorted(forms_drafts)),
                    "drift": drift,
                    "ok": not errors,
                    "errors": errors,
                    "diff": diff,
                }
            )
        if not items:
            raise ValueError("无待导出的范式草稿")
        return {"items": items, "all_ok": all(i["ok"] for i in items)}

    async def export_paradigms(self, username: str) -> dict[str, Any]:
        rows = self._flatten(await self.repo.list_drafts())
        preview = await run_in_threadpool(self._preview_from_rows, rows)
        md_contents = {a: c["md"] for k, a, c, _h, _ub, _ua in rows if k == KIND_MD}
        forms_contents = {a: c for k, a, c, _h, _ub, _ua in rows if k == KIND_FORMS}
        if not preview["all_ok"]:
            failed = [f"{i['kind']}/{i['asset_id']}: {'；'.join(i['errors'])}" for i in preview["items"] if not i["ok"]]
            raise ValueError("写前校验未通过（全批不写）—" + " | ".join(failed))
        return await run_in_threadpool(self._export_sync, preview, md_contents, forms_contents, username)

    def _export_sync(self, preview: dict, md_contents: dict, forms_contents: dict, username: str) -> dict[str, Any]:
        written: list[tuple[Any, str]] = []
        results: dict[str, dict[str, Any]] = {}
        try:
            for item in preview["items"]:
                if item["kind"] == KIND_MD:
                    path = _md_file(item["asset_id"])
                    original = _read_text(path)
                    _atomic_write(path, md_contents[item["asset_id"]])
                    written.append((path, original))
                    results[f"{KIND_MD}/{item['asset_id']}"] = {"materialized": True, "drift": item["drift"]}
                else:
                    path = _PARADIGM_DIR / "forms_catalog.json"
                    original = _read_text(path)
                    new, changed = _splice_forms(original, forms_contents)
                    if not changed:
                        results[f"{KIND_FORMS}/{item['asset_id']}"] = {"materialized": False, "drift": item["drift"]}
                        continue
                    _atomic_write(path, new)
                    written.append((path, original))
                    results[f"{KIND_FORMS}/{item['asset_id']}"] = {"materialized": True, "drift": item["drift"]}
        except Exception:
            for path, original in reversed(written):
                _atomic_write(path, original)
            raise
        logger.info(f"[eia-paradigm] 导出物化 {len(written)} 文件 → references/paradigms/（by {username}）")
        return {
            "results": results,
            "paths": sorted({str(p.relative_to(_SKILL_ROOT)) for p, _ in written}) or ["(无变更)"],
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


_service: EiaParadigmService | None = None


def get_eia_paradigm_service() -> EiaParadigmService:
    global _service
    if _service is None:
        _service = EiaParadigmService()
    return _service
