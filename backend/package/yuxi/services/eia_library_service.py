"""环评文件库服务（P1 进料区 + P2 canonical md 正源，spec 2026-10-18 方案 B）。

溯源契约：content_sha1 全库唯一，是 P2 语料管线产物 source 字段的对账锚点
（spec 2026-10-17-eia-file-library-design.md 决策 D1）；v19 起源文件正源为 MinIO
（object_key），docx 上传即秒级产 canonical md（md_object_key/md_status/front_meta）。
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from yuxi.repositories.eia_library_repository import EiaLibraryRepository
from yuxi.services.eia_canonical_md import CanonicalMd, docx_bytes_to_canonical_md, extract_front, make_rid
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_domain_factory import EiaLibraryFile
from yuxi.utils.upload_utils import MAX_UPLOAD_SIZE_BYTES, write_upload_to_path

MINIO_BUCKET = "knowledgebases"  # is_minio_url 白名单桶（kb_utils）；库对象统一 eia-library/ 前缀

ALLOWED_STAGES = {"planning_eia", "project_eia_underground", "project_eia_openpit", "post_eia", "tracking_eia"}


class LibraryFileTooLarge(ValueError):
    """上传文件超过大小上限（路由层映射 HTTP 413）。"""


class EiaLibraryService:
    def __init__(
        self,
        repo: EiaLibraryRepository | None = None,
        storage_root: str | Path | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        self.repo = repo or EiaLibraryRepository()
        self.storage_root = Path(storage_root or os.environ.get("EIA_LIBRARY_DIR", "/app/eia-library"))
        self.max_size_bytes = max_size_bytes or MAX_UPLOAD_SIZE_BYTES

    async def list_folders(self) -> list[dict]:
        return await self.repo.list_folders()

    async def count_files(self) -> int:
        return await self.repo.count_files()

    async def list_files(
        self, folder_id: int | None = None, q: str | None = None, uncategorized: bool = False
    ) -> list[dict]:
        return await self.repo.list_files(folder_id=folder_id, q=q, uncategorized=uncategorized)

    async def upload(self, file: UploadFile, folder_id: int | None, uploaded_by: str | None) -> dict:
        original = file.filename or ""
        if not original:
            raise ValueError("文件名不能为空")
        folder = None
        if folder_id is not None:
            folder = await self.repo.get_folder(folder_id)
            if folder is None:
                raise ValueError(f"目标文件夹不存在: {folder_id}")
        self.storage_root.mkdir(parents=True, exist_ok=True)
        tmp_path = self.storage_root / f".tmp-{os.getpid()}-{uuid.uuid4().hex}"
        try:
            try:
                await write_upload_to_path(
                    file,
                    tmp_path,
                    max_size_bytes=self.max_size_bytes,
                    too_large_message=f"文件超过大小上限（{self.max_size_bytes // (1024 * 1024)}MB）",
                )
            except ValueError as e:
                raise LibraryFileTooLarge(str(e)) from e
            sha1 = _sha1_of(tmp_path)
            existing = await self.repo.get_file_by_sha1(sha1)
            if existing is not None:
                existing_folder = (
                    await self.repo.get_folder(existing.folder_id) if existing.folder_id is not None else None
                )
                where = existing_folder.name if existing_folder else "未归类"
                raise FileExistsError(f"{existing.original_filename}（位于〈{where}〉）")
            data = tmp_path.read_bytes()
            stored_name = f"{sha1[:12]}__{_safe_filename(original)}"
            object_key = f"eia-library/{stored_name}"
            await get_minio_client().aupload_file(MINIO_BUCKET, object_key, data, file.content_type)
            md_fields = self._produce_md_fields(data, stored_name)
            md_bytes = md_fields.pop("_md_bytes", None)
            if md_bytes is not None:
                await self._put_md(md_fields["md_object_key"], md_bytes)
            row = EiaLibraryFile(
                folder_id=folder_id,
                original_filename=original,
                stored_path=stored_name,  # [遗留] 展示安全名；正源为 object_key
                content_sha1=sha1,
                size_bytes=len(data),
                content_type=file.content_type,
                status="stored",
                uploaded_by=uploaded_by,
                object_key=object_key,
                stage=folder.stage_key if folder is not None else None,  # 文件夹 stage_key 作加工默认
                mineral="coal",
                **md_fields,
            )
            try:
                await self.repo.insert_file(row)
            except IntegrityError:
                raise FileExistsError(original) from None  # 并发兜底：唯一约束再拦
            await self.repo.update_file(row.id, {"report_id": make_rid(row.id, Path(original).stem)})
            return (await self.repo.get_file(row.id)).to_dict()
        finally:
            tmp_path.unlink(missing_ok=True)

    def _produce_md_fields(self, data: bytes, stored_name: str) -> dict:
        """docx → canonical md 各字段（同步秒级；失败不阻断登记）。

        返回 {} 之外的键：md_object_key/md_status/md_chars/md_sha1/md_failed_reason/front_meta。
        非 docx → not_applicable；解析失败/零节号标题 → failed + 原因（登记照记）。
        """
        if not stored_name.lower().endswith(".docx"):
            return {"md_status": "not_applicable"}
        try:
            cm: CanonicalMd | None = docx_bytes_to_canonical_md(data, label=stored_name)
        except ValueError as e:
            return {"md_status": "failed", "md_failed_reason": str(e)[:500]}
        if cm is None:
            return {"md_status": "failed", "md_failed_reason": "零节号标题"}
        return {
            "md_object_key": f"eia-library/.canonical/{stored_name}.md",
            "md_status": "ready",
            "md_chars": cm.chars,
            "md_sha1": hashlib.sha1(cm.md.encode("utf-8")).hexdigest(),
            "front_meta": extract_front(cm.front_paras),
            "_md_bytes": cm.md.encode("utf-8"),  # 调用方 pop 后 _put_md 落 MinIO
        }

    async def _put_md(self, md_object_key: str, md_bytes: bytes) -> None:
        await get_minio_client().aupload_file(MINIO_BUCKET, md_object_key, md_bytes, "text/markdown")

    async def get_canonical_md(self, file_id: int) -> tuple[EiaLibraryFile, bytes]:
        row = await self.repo.get_file(file_id)
        if row is None or row.md_status != "ready" or not row.md_object_key:
            raise FileNotFoundError("canonical md 不存在")
        return row, await get_minio_client().adownload_file(MINIO_BUCKET, row.md_object_key)

    async def regenerate_md(self, file_id: int, operator: str | None) -> dict:
        """重产 canonical md（md_status=failed 行的手工修复动作）。"""
        row = await self.repo.get_file(file_id)
        if row is None:
            raise FileNotFoundError(file_id)
        if not (row.original_filename or "").lower().endswith(".docx") or not row.object_key:
            raise ValueError("仅 docx 且已迁移 MinIO 的文件可重产 md")
        data = await get_minio_client().adownload_file(MINIO_BUCKET, row.object_key)
        fields = self._produce_md_fields(data, row.stored_path)
        md_bytes = fields.pop("_md_bytes", None)
        if md_bytes is not None:
            await self._put_md(fields["md_object_key"], md_bytes)
        await self.repo.update_file(file_id, fields)
        return (await self.repo.get_file(file_id)).to_dict()

    async def update_meta(self, file_id: int, fields: dict) -> dict:
        """stage/mineral 行内编辑（白名单 + 值域守卫）。"""
        if "stage" in fields and fields["stage"] not in ALLOWED_STAGES:
            raise ValueError(f"非法 stage: {fields['stage']}")
        if "mineral" in fields and not (fields["mineral"] or "").strip():
            raise ValueError("mineral 不能为空")
        row = await self.repo.update_file(file_id, fields)
        if row is None:
            raise FileNotFoundError(file_id)
        return row.to_dict()

    async def _log(self, *, file_id: int | None, action: str, detail: dict | None, operator: str | None) -> None:
        await self.repo.insert_process_log(
            file_id=file_id,
            content_sha1=None,
            action=action,
            detail=detail,
            operator=operator,
        )

    async def bootstrap_from_manifest(self, manifest: list[dict], operator: str | None) -> dict:
        """既有 manifest.json（prepare_corpus 产物）按 file_name 回填 report_id/stage/mineral。

        D6：rid 与 stage/mineral 人工裁决资产原样回填；匹配失败的文件列入异常消息
        （部分成功已落库，补传后重跑幂等收敛）。
        """
        if not isinstance(manifest, list) or not manifest:
            raise ValueError("manifest 须为非空数组")
        files = {f["original_filename"]: f for f in await self.repo.list_files()}
        matched, unmatched = [], []
        for e in manifest:
            row = files.get(e.get("file_name", ""))
            if row is None:
                unmatched.append(e.get("file_name"))
                continue
            await self.repo.update_file(
                row["id"],
                {
                    "report_id": e["report_id"],
                    "stage": e["stage"],
                    "mineral": e.get("mineral") or "coal",
                },
            )
            matched.append(e["report_id"])
        await self._log(file_id=None, action="bootstrap", detail={"matched": matched, "unmatched": unmatched}, operator=operator)
        if unmatched:
            raise FileNotFoundError(f"以下文件未在文件库登记（请先上传后再引导）: {', '.join(map(str, unmatched))}")
        return {"matched": len(matched)}

    async def migrate_storage_to_minio(self, operator: str | None) -> dict:
        """存量本地卷文件一次性迁移：流式 sha1 校验 → put MinIO → 回填 object_key → 逐份重产 md。

        幂等：object_key 已置的行跳过；单行任何失败（缺失/sha1 不符/上传/解析）记入
        failed 不阻断整体，重跑自动重试未完成行。
        内存纪律：文件可达 80MB 级、docx DOM 膨胀数倍——逐份 del+gc，绝不跨迭代持留。
        """
        import gc

        from yuxi.utils.logging_config import logger

        client = get_minio_client()
        migrated: list[dict] = []
        failed: list[dict] = []
        md_ready = 0
        for row in await self.repo.list_files():
            if row["object_key"]:
                continue
            local = self.storage_root / row["stored_path"]
            if not local.is_file():
                failed.append({"id": row["id"], "reason": f"本地文件缺失: {row['stored_path']}"})
                continue
            if _sha1_of(local) != row["content_sha1"]:
                failed.append({"id": row["id"], "reason": "sha1 不符，拒绝迁移"})
                continue
            object_key = f"eia-library/{row['stored_path']}"
            data = local.read_bytes()
            try:
                await client.aupload_file(MINIO_BUCKET, object_key, data, row["content_type"])
                fields: dict = {"object_key": object_key, "md_status": "pending_backfill"}
                if (row["original_filename"] or "").lower().endswith(".docx"):
                    md_fields = self._produce_md_fields(data, row["stored_path"])
                    md_bytes = md_fields.pop("_md_bytes", None)
                    if md_bytes is not None:
                        await self._put_md(md_fields["md_object_key"], md_bytes)
                    fields.update(md_fields)
                    if md_fields.get("md_status") == "ready":
                        md_ready += 1
                await self.repo.update_file(row["id"], fields)
                migrated.append({"id": row["id"], "object_key": object_key})
            except Exception as exc:  # noqa: BLE001 单行失败不阻断（重跑幂等重试）
                logger.error(f"[eia-migrate] {row['original_filename']} 迁移失败: {exc}")
                failed.append({"id": row["id"], "reason": str(exc)[:200]})
            finally:
                del data
                gc.collect()
        await self._log(file_id=None, action="migrate", detail={"migrated": migrated, "failed": failed}, operator=operator)
        return {"migrated": len(migrated), "md_ready": md_ready, "failed": failed}

    async def move(self, file_id: int, folder_id: int | None) -> dict:
        if folder_id is not None and await self.repo.get_folder(folder_id) is None:
            raise ValueError(f"目标文件夹不存在: {folder_id}")
        row = await self.repo.move_file(file_id, folder_id)
        if row is None:
            raise FileNotFoundError(file_id)
        return row.to_dict()

    async def delete(self, file_id: int) -> None:
        row = await self.repo.get_file(file_id)
        if row is None:
            raise FileNotFoundError(file_id)
        await self.repo.delete_file(file_id)
        client = get_minio_client()
        if row.object_key:
            await client.adelete_file(MINIO_BUCKET, row.object_key)
        if row.md_object_key:
            await client.adelete_file(MINIO_BUCKET, row.md_object_key)
        elif not row.object_key:  # 存量未迁移行：本地卷清理（迁移完成后自然绝迹）
            (self.storage_root / row.stored_path).unlink(missing_ok=True)

    async def download(self, file_id: int) -> tuple:
        """返回 (row, Path|bytes)：MinIO 正源行走 bytes，存量本地卷行走 Path。"""
        row = await self.repo.get_file(file_id)
        if row is None:
            raise FileNotFoundError(file_id)
        if row.object_key:
            return row, await get_minio_client().adownload_file(MINIO_BUCKET, row.object_key)
        path = self.storage_root / row.stored_path
        if not path.is_file():
            raise FileNotFoundError(f"磁盘文件缺失: {row.stored_path}")
        return row, path


def _safe_filename(name: str) -> str:
    """去掉路径分隔与文件系统非法字符，保留 CJK；空名与点目录名兜底。"""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", Path(name).name).strip()
    # ".." 经 Path.name 原样透出（pathlib 不视其为普通名），作为文件名属非法路径组件
    return cleaned if cleaned not in ("", ".", "..") else "unnamed"


def _sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_service: EiaLibraryService | None = None


def get_eia_library_service() -> EiaLibraryService:
    global _service
    if _service is None:
        _service = EiaLibraryService()
    return _service
