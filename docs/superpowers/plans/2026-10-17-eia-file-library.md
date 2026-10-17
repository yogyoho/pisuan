# 环评文件库（P1）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 环评文件库 P1 进料区 — 上传即登记（sha1 唯一）、五阶段文件夹归类、下载/移动/删除，为 P2 管线在线化提供文件正源。

**Spec:** `docs/superpowers/specs/2026-10-17-eia-file-library-design.md`（决策 D1–D6，AC1–9）。

**Architecture:** 新表 v18（folders + files，`content_sha1` 全库唯一）+ `EiaLibraryRepository`（薄仓储）+ `EiaLibraryService`（sha1 命名/去重/磁盘操作，storage_root 可注入）+ `domain_factory_router` 六端点（读 required / 写 admin）+ 前端 `LibraryPanel.vue`（eia-data 新 library 子页）。

**Tech Stack:** FastAPI + SQLAlchemy（pg_manager 会话上下文）/ antd Vue + lucide / 后端测试 pytest（容器内）；存储 bind mount `${YUXI_STATE_DIR:-./docker/volumes}/yuxi/eia-library`。

**执行约定（全程适用）：**
- 分支 `pisuan-custom` 直接开发（本项目既定实践，不另开 worktree）。
- 后端容器 `pisuan-localized-api-1`；代码改动后 `powershell.exe -NoProfile -File scripts/sync-dev.ps1` 热同步；迁移类改动需 `docker restart pisuan-localized-api-1`。
- ruff：宿主 `python -m ruff`（裸 `ruff` 不在 PATH）；前端链：`cd web && node node_modules/prettier/bin/prettier.cjs --write <file>` → sync-dev → `MSYS_NO_PATHCONV=1 docker exec pisuan-localized-web-1 sh -c "cd /app && ./node_modules/.bin/eslint <files>"`。
- 提交信息中文 Conventional Commits，结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 严禁运行 `backend/test/integration/services/test_eia_lexicon_service_flow.py`（清空 eia_lexicon_entries 表）。

---

### Task 1: v18 迁移 + ORM 模型（两表 + 五阶段种子）

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`（BigInteger 导入 + 文件末尾追加两个模型）
- Modify: `backend/package/yuxi/storage/postgres/manager.py`（版本注释、`BUSINESS_SCHEMA_VERSION`、新迁移方法）
- Modify: `backend/package/yuxi/storage_migration.py`（v18 调用块）

- [ ] **Step 1.1: models_domain_factory.py — BigInteger 入导入行**

第 7 行 sqlalchemy 导入加入 `BigInteger`：

```python
from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
```

- [ ] **Step 1.2: models_domain_factory.py — 末尾追加两模型**

```python


class EiaLibraryFolder(Base):
    """Domain Factory - 环评文件库文件夹（P1；stage_key 对齐 samples_bank 五阶段分类法）"""

    __tablename__ = "eia_library_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    stage_key = Column(String(50), nullable=True)  # NULL = 自定义夹（预留）
    sort = Column(Integer, nullable=False, default=0)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "stage_key": self.stage_key, "sort": self.sort}


class EiaLibraryFile(Base):
    """Domain Factory - 环评文件库文件（P1 进料区；content_sha1 全库唯一，P2 管线溯源锚点）"""

    __tablename__ = "eia_library_files"
    __table_args__ = (Index("ix_eia_library_files_folder", "folder_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_id = Column(Integer, ForeignKey("eia_library_folders.id"), nullable=True)  # NULL = 未归类
    original_filename = Column(String(500), nullable=False)
    stored_path = Column(String(1000), nullable=False)  # volume 内相对路径（sha1 前缀防碰撞）
    content_sha1 = Column(String(40), nullable=False, unique=True)
    size_bytes = Column(BigInteger, nullable=False)
    content_type = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="stored")  # P1 恒 stored；P2 扩加工态
    uploaded_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "folder_id": self.folder_id,
            "original_filename": self.original_filename,
            "stored_path": self.stored_path,
            "content_sha1": self.content_sha1,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "status": self.status,
            "uploaded_by": self.uploaded_by,
            "created_at": format_utc_datetime(self.created_at),
        }
```

- [ ] **Step 1.3: manager.py — 版本注释 + 常量提升**

第 46–47 行注释区追加一行；`BUSINESS_SCHEMA_VERSION = 17` 改 `18`：

```python
# v18：环评文件库（eia_library_folders / eia_library_files，五阶段种子）；
```

- [ ] **Step 1.4: manager.py — 新迁移方法（仿 v16_to_v17 形状，放其后面）**

```python
    async def upgrade_business_v17_to_v18(self) -> None:
        """[pisuan-custom] v18：环评文件库两表 + 五阶段种子（存量库 create_all 不补表，显式建 + 记版本）。

        幂等（version=18 直接返回）；种子以 WHERE NOT EXISTS 防重，全新库与升级库均收敛。
        """
        self._check_initialized()
        async with self.async_engine.begin() as conn:
            version = await conn.scalar(
                text(f"SELECT version FROM {SCHEMA_VERSION_TABLE} WHERE domain = 'business' FOR UPDATE")
            )
            if version == 18:
                return
            if version not in (None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
                raise RuntimeError(f"Unsupported business schema version: {version}")
            await conn.run_sync(
                lambda sync_conn: DomainFactoryBase.metadata.create_all(
                    sync_conn, tables=[EiaLibraryFolder.__table__, EiaLibraryFile.__table__]
                )
            )
            await conn.execute(
                text("""
                    INSERT INTO eia_library_folders (name, stage_key, sort)
                    SELECT * FROM (VALUES
                        ('规划环评', 'planning_eia', 1),
                        ('项目环评·井工', 'project_eia_underground', 2),
                        ('项目环评·露天', 'project_eia_openpit', 3),
                        ('后评价', 'post_eia', 4),
                        ('跟踪评价', 'tracking_eia', 5)
                    ) AS v(name, stage_key, sort)
                    WHERE NOT EXISTS (SELECT 1 FROM eia_library_folders WHERE stage_key = v.stage_key)
                """)
            )
            await conn.execute(
                text(f"""
                    INSERT INTO {SCHEMA_VERSION_TABLE} (domain, version, applied_at)
                    VALUES ('business', 18, CURRENT_TIMESTAMP)
                    ON CONFLICT (domain) DO UPDATE SET version = 18, applied_at = EXCLUDED.applied_at
                """)
            )
```

manager.py 顶部如缺 `EiaLibraryFolder, EiaLibraryFile` 导入则补（同 `EiaMetaAnnotation` 来源）。

- [ ] **Step 1.5: storage_migration.py — v17 块后追加 v18 块**

```python
            # [pisuan-custom] v18：环评文件库两表 + 五阶段种子（存量库显式补表，幂等）
            if business_version in {None, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}:
                await pg_manager.upgrade_business_v17_to_v18()
```

- [ ] **Step 1.6: 语法验证 + 容器迁移落库**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/storage/postgres/models_domain_factory.py', encoding='utf-8').read()); ast.parse(open('backend/package/yuxi/storage/postgres/manager.py', encoding='utf-8').read()); ast.parse(open('backend/package/yuxi/storage_migration.py', encoding='utf-8').read()); print('AST OK')"
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker restart pisuan-localized-api-1
docker exec pisuan-localized-api-1 python -c "
import asyncio, os, asyncpg
async def main():
    conn = await asyncpg.connect(os.environ['POSTGRES_URL'].replace('+asyncpg',''))
    tabs = await conn.fetch(\"SELECT tablename FROM pg_tables WHERE tablename LIKE 'eia_library%'\")
    print('tables:', sorted(r['tablename'] for r in tabs))
    seeds = await conn.fetch('SELECT name, stage_key FROM eia_library_folders ORDER BY sort')
    print('folders:', [(r['name'], r['stage_key']) for r in seeds])
    ver = await conn.fetchval(\"SELECT version FROM yuxi_schema_migrations WHERE domain='business'\")
    print('business version:', ver)
    await conn.close()
asyncio.run(main())
"
```

Expected: `tables: ['eia_library_files', 'eia_library_folders']`；folders 五条 (规划环评/planning_eia … 跟踪评价/tracking_eia)；`business version: 18`。API 日志无迁移报错（`docker logs pisuan-localized-api-1 --tail 30`）。

- [ ] **Step 1.7: Commit**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/storage_migration.py
git commit -m "feat(domain-factory): 环评文件库 v18 两表与五阶段种子

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: EiaLibraryRepository

**Files:**
- Create: `backend/package/yuxi/repositories/eia_library_repository.py`

- [ ] **Step 2.1: 实现仓储（形状同 eia_meta_repository：pg_manager 会话上下文）**

```python
"""环评文件库仓储（eia_library_folders / eia_library_files，P1 进料区）。"""

from __future__ import annotations

from sqlalchemy import func, select

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_domain_factory import EiaLibraryFile, EiaLibraryFolder


class EiaLibraryRepository:
    """文件库 CRUD（百份量级全量内存操作足够）。"""

    async def list_folders(self) -> list[dict]:
        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(EiaLibraryFolder, func.count(EiaLibraryFile.id))
                .outerjoin(EiaLibraryFile, EiaLibraryFile.folder_id == EiaLibraryFolder.id)
                .group_by(EiaLibraryFolder.id)
                .order_by(EiaLibraryFolder.sort)
            )
            return [{**folder.to_dict(), "file_count": count} for folder, count in rows.all()]

    async def get_folder(self, folder_id: int) -> EiaLibraryFolder | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLibraryFolder, folder_id)

    async def list_files(self, *, folder_id: int | None = None, q: str | None = None) -> list[dict]:
        async with pg_manager.get_async_session_context() as session:
            stmt = (
                select(EiaLibraryFile, EiaLibraryFolder.name)
                .outerjoin(EiaLibraryFolder, EiaLibraryFile.folder_id == EiaLibraryFolder.id)
                .order_by(EiaLibraryFile.created_at.desc(), EiaLibraryFile.id.desc())
            )
            if folder_id is not None:
                stmt = stmt.where(EiaLibraryFile.folder_id == folder_id)
            if q:
                stmt = stmt.where(EiaLibraryFile.original_filename.ilike(f"%{q}%"))
            rows = (await session.execute(stmt)).all()
            return [{**row.to_dict(), "folder_name": name} for row, name in rows]

    async def count_files(self) -> int:
        async with pg_manager.get_async_session_context() as session:
            return await session.scalar(select(func.count(EiaLibraryFile.id)))

    async def get_file(self, file_id: int) -> EiaLibraryFile | None:
        async with pg_manager.get_async_session_context() as session:
            return await session.get(EiaLibraryFile, file_id)

    async def get_file_by_sha1(self, sha1: str) -> EiaLibraryFile | None:
        async with pg_manager.get_async_session_context() as session:
            scalar = await session.scalars(
                select(EiaLibraryFile).where(EiaLibraryFile.content_sha1 == sha1)
            )
            return scalar.first()

    async def insert_file(self, row: EiaLibraryFile) -> EiaLibraryFile:
        async with pg_manager.get_async_session_context() as session:
            session.add(row)
            await session.commit()
            return row

    async def move_file(self, file_id: int, folder_id: int | None) -> EiaLibraryFile | None:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(EiaLibraryFile, file_id)
            if row is None:
                return None
            row.folder_id = folder_id
            await session.commit()
            return row

    async def delete_file(self, file_id: int) -> bool:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(EiaLibraryFile, file_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True
```

- [ ] **Step 2.2: 语法验证 + Commit**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/repositories/eia_library_repository.py', encoding='utf-8').read()); print('AST OK')"
git add backend/package/yuxi/repositories/eia_library_repository.py
git commit -m "feat(domain-factory): 环评文件库仓储层

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: EiaLibraryService + 单测（TDD）

**Files:**
- Create: `backend/package/yuxi/services/eia_library_service.py`
- Create: `backend/test/unit/test_eia_library_service.py`

- [ ] **Step 3.1: 先写失败测试**

```python
"""eia_library_service 单测：sha1 命名/去重、越限拒收、移动、删除、清单过滤（仓储以内存桩替身）。"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from yuxi.services.eia_library_service import (
    EiaLibraryService,
    LibraryFileTooLarge,
    _safe_filename,
)

SHA1_HELLO = "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"  # sha1(b"hello")


class FakeRepo:
    def __init__(self):
        self.folders = {1: SimpleNamespace(id=1, name="规划环评"), 2: SimpleNamespace(id=2, name="后评价")}
        self.files: list = []
        self._next = 1

    async def get_folder(self, folder_id):
        return self.folders.get(folder_id)

    async def get_file_by_sha1(self, sha1):
        return next((f for f in self.files if f.content_sha1 == sha1), None)

    async def insert_file(self, row):
        row.id = self._next
        self._next += 1
        self.files.append(row)
        return row

    async def get_file(self, file_id):
        return next((f for f in self.files if f.id == file_id), None)

    async def move_file(self, file_id, folder_id):
        row = await self.get_file(file_id)
        if row is not None:
            row.folder_id = folder_id
        return row

    async def delete_file(self, file_id):
        row = await self.get_file(file_id)
        if row is None:
            return False
        self.files.remove(row)
        return True


def make_service(tmp_path, max_size=None):
    return EiaLibraryService(repo=FakeRepo(), storage_root=tmp_path, max_size_bytes=max_size)


def make_upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


@pytest.mark.asyncio
async def test_upload_stores_sha1_named_file(tmp_path):
    svc = make_service(tmp_path)
    row = await svc.upload(make_upload(b"hello", "某矿区报告书.docx"), folder_id=1, uploaded_by="admin")
    assert row["content_sha1"] == SHA1_HELLO
    assert row["stored_path"] == f"{SHA1_HELLO[:12]}__某矿区报告书.docx"
    assert row["size_bytes"] == 5
    assert (tmp_path / row["stored_path"]).read_bytes() == b"hello"
    assert row["status"] == "stored"


@pytest.mark.asyncio
async def test_upload_duplicate_sha1_rejected_and_tmp_cleaned(tmp_path):
    svc = make_service(tmp_path)
    await svc.upload(make_upload(b"hello", "a.docx"), folder_id=None, uploaded_by="admin")
    with pytest.raises(FileExistsError):
        await svc.upload(make_upload(b"hello", "b.docx"), folder_id=None, uploaded_by="admin")
    assert len(svc.repo.files) == 1
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]


@pytest.mark.asyncio
async def test_upload_oversize_raises_too_large(tmp_path):
    svc = make_service(tmp_path, max_size=4)
    with pytest.raises(LibraryFileTooLarge):
        await svc.upload(make_upload(b"0123456789", "big.docx"), folder_id=None, uploaded_by="admin")
    assert svc.repo.files == []


@pytest.mark.asyncio
async def test_upload_to_unknown_folder_rejected(tmp_path):
    svc = make_service(tmp_path)
    with pytest.raises(ValueError, match="目标文件夹不存在"):
        await svc.upload(make_upload(b"x", "a.docx"), folder_id=99, uploaded_by="admin")


@pytest.mark.asyncio
async def test_move_updates_folder(tmp_path):
    svc = make_service(tmp_path)
    row = await svc.upload(make_upload(b"hello", "a.docx"), folder_id=1, uploaded_by="admin")
    out = await svc.move(row["id"], 2)
    assert out["folder_id"] == 2


@pytest.mark.asyncio
async def test_delete_removes_row_and_disk_file(tmp_path):
    svc = make_service(tmp_path)
    row = await svc.upload(make_upload(b"hello", "a.docx"), folder_id=None, uploaded_by="admin")
    await svc.delete(row["id"])
    assert svc.repo.files == []
    assert not (tmp_path / row["stored_path"]).exists()
    with pytest.raises(FileNotFoundError):
        await svc.delete(row["id"])


@pytest.mark.asyncio
async def test_list_files_joins_folder_name(tmp_path):
    svc = make_service(tmp_path)
    await svc.upload(make_upload(b"hello", "alpha.docx"), folder_id=1, uploaded_by="admin")
    await svc.upload(make_upload(b"world", "beta.docx"), folder_id=None, uploaded_by="admin")
    all_files = await svc.list_files()
    assert len(all_files) == 2
    names = {f["original_filename"]: f["folder_name"] for f in all_files}
    assert names["alpha.docx"] == "规划环评"
    assert names["beta.docx"] is None
    hit = await svc.list_files(q="alp")
    assert [f["original_filename"] for f in hit] == ["alpha.docx"]


def test_safe_filename_strips_unsafe_chars():
    assert _safe_filename(r'report\v2:final?.docx') == "report_v2_final_.docx"
    assert _safe_filename("..") == "unnamed"
```

- [ ] **Step 3.2: 跑测试确认失败（模块不存在）**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_library_service.py -v 2>&1 | tail -3
```

Expected: FAIL / collection error（`ModuleNotFoundError: eia_library_service`）— 证明测试咬得住。

- [ ] **Step 3.3: 实现 service**

```python
"""环评文件库服务（P1 进料区：上传即登记，加工属 P2 显式触发）。

溯源契约：content_sha1 全库唯一，是 P2 语料管线产物 source 字段的对账锚点
（spec 2026-10-17-eia-file-library-design.md 决策 D1）。
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
from yuxi.utils.upload_utils import MAX_UPLOAD_SIZE_BYTES, write_upload_to_path


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

    async def list_files(self, folder_id: int | None = None, q: str | None = None) -> list[dict]:
        return await self.repo.list_files(folder_id=folder_id, q=q)

    async def upload(self, file: UploadFile, folder_id: int | None, uploaded_by: str | None) -> dict:
        original = file.filename or ""
        if not original:
            raise ValueError("文件名不能为空")
        if folder_id is not None and await self.repo.get_folder(folder_id) is None:
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
                folder = await self.repo.get_folder(existing.folder_id) if existing.folder_id is not None else None
                where = folder.name if folder else "未归类"
                raise FileExistsError(f"{existing.original_filename}（位于〈{where}〉）")
            stored_name = f"{sha1[:12]}__{_safe_filename(original)}"
            dest = self.storage_root / stored_name
            os.replace(tmp_path, dest)
            row = EiaLibraryFile(
                folder_id=folder_id,
                original_filename=original,
                stored_path=stored_name,
                content_sha1=sha1,
                size_bytes=dest.stat().st_size,
                content_type=file.content_type,
                status="stored",
                uploaded_by=uploaded_by,
            )
            try:
                await self.repo.insert_file(row)
            except IntegrityError:
                raise FileExistsError(original) from None  # 并发兜底：唯一约束再拦
            return row.to_dict()
        finally:
            tmp_path.unlink(missing_ok=True)

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
        (self.storage_root / row.stored_path).unlink(missing_ok=True)

    async def download(self, file_id: int) -> tuple:
        row = await self.repo.get_file(file_id)
        if row is None:
            raise FileNotFoundError(file_id)
        path = self.storage_root / row.stored_path
        if not path.is_file():
            raise FileNotFoundError(f"磁盘文件缺失: {row.stored_path}")
        return row, path


def _safe_filename(name: str) -> str:
    """去掉路径分隔与文件系统非法字符，保留 CJK；空名兜底。"""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", Path(name).name).strip()
    return cleaned or "unnamed"


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
```

注：`FileExistsError` 携带既有位置文案（spec §6 的结构化 `existing` 字段收敛为 detail 文案，toast 语义等价）。

- [ ] **Step 3.4: 跑测试转绿**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1
docker exec pisuan-localized-api-1 pytest /app/test/unit/test_eia_library_service.py -v
```

Expected: 9 passed。（`pytest.mark.asyncio` 需工程已有 asyncio 配置——`test_eia_meta_service.py` 同目录若用 asyncio.run 风格则把用例改为 `asyncio.run(...)` 同步壳，保持一致。）

- [ ] **Step 3.5: ruff + Commit**

```bash
python -m ruff format backend/package/yuxi/services/eia_library_service.py backend/test/unit/test_eia_library_service.py
python -m ruff check backend/package/yuxi/services/eia_library_service.py backend/test/unit/test_eia_library_service.py
git add backend/package/yuxi/services/eia_library_service.py backend/test/unit/test_eia_library_service.py
git commit -m "feat(domain-factory): 环评文件库服务层（sha1 去重/命名/磁盘操作）与单测

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Router 六端点

**Files:**
- Modify: `backend/server/routers/domain_factory_router.py`（imports + eia meta 段后追加 library 段）

- [ ] **Step 4.1: imports 增补**

fastapi 导入行补 `Body, File, Form`（按现有行内缺哪个补哪个）；文件顶部 responses 导入：

```python
from fastapi.responses import FileResponse
```

service 导入（与 `get_eia_meta_service` 并排）：

```python
from yuxi.services.eia_library_service import LibraryFileTooLarge, get_eia_library_service
```

- [ ] **Step 4.2: eia meta 段后追加端点段**

```python
# =============================================================================
# EIA Library（环评文件库 P1：上传即登记；加工属 P2 显式触发）
# =============================================================================


@domain_factory.get("/eia/library/folders")
async def list_eia_library_folders(
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """文件夹树（含各夹计数）+ 全库登记总数。"""
    service = get_eia_library_service()
    return {"folders": await service.list_folders(), "total_files": await service.count_files()}


@domain_factory.post("/eia/library/files")
async def upload_eia_library_file(
    file: UploadFile = File(...),
    folder_id: int | None = Form(None),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """上传即登记：sha1 全库去重（409 携既有位置），超限 413。"""
    try:
        return await get_eia_library_service().upload(
            file, folder_id, current_user.username if current_user else None
        )
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=f"文件已存在：{e}")
    except LibraryFileTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.get("/eia/library/files")
async def list_eia_library_files(
    folder_id: int | None = None,
    q: str | None = None,
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """文件列表：folder_id 缺省=全库；q 文件名模糊。"""
    files = await get_eia_library_service().list_files(folder_id=folder_id, q=q)
    return {"files": files}


@domain_factory.get("/eia/library/files/{file_id}/download")
async def download_eia_library_file(
    file_id: int,
    current_user: User = Depends(get_required_user),
) -> FileResponse:
    """下载（FileResponse 以 original_filename 恢复原名）。"""
    try:
        row, path = await get_eia_library_service().download(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在（或磁盘文件已丢失）")
    return FileResponse(
        path=path, filename=row.original_filename, media_type=row.content_type or "application/octet-stream"
    )


@domain_factory.patch("/eia/library/files/{file_id}")
async def move_eia_library_file(
    file_id: int,
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """移动文件夹（folder_id=null 移出为未归类）。"""
    folder_id = body.get("folder_id")
    if folder_id is not None and not isinstance(folder_id, int):
        raise HTTPException(status_code=400, detail="folder_id 须为整数或 null")
    try:
        return await get_eia_library_service().move(file_id, folder_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@domain_factory.delete("/eia/library/files/{file_id}")
async def delete_eia_library_file(
    file_id: int,
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """删除（DB 记录与磁盘文件同删）。"""
    try:
        await get_eia_library_service().delete(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"success": True}
```

注：`UploadFile` 若 router 未导入需从 fastapi 补；`get_admin_user` 已在文件内使用（sync-task-center 处）。

- [ ] **Step 4.3: 冒烟验证（openapi 路由存在 + 鉴权挂载）**

```bash
powershell.exe -NoProfile -File scripts/sync-dev.ps1 && docker restart pisuan-localized-api-1
sleep 8
curl -s http://localhost:5050/api/domain-factory/openapi.json 2>/dev/null | python -c "import json,sys; paths=[p for p in json.load(sys.stdin)['paths'] if 'eia/library' in p]; print('\n'.join(sorted(paths)))"
```

Expected 恰好 6 条：`/eia/library/folders`、`/eia/library/files`、`/eia/library/files/{file_id}`、`/eia/library/files/{file_id}/download` 各带正确 method。若 openapi 前缀路径不同，以 `docker logs` 无路由冲突报错 + 页面联调为准。

- [ ] **Step 4.4: Commit**

```bash
git add backend/server/routers/domain_factory_router.py
git commit -m "feat(domain-factory): 环评文件库六端点（读 required/写 admin）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: compose 卷 + 前端 API 层

**Files:**
- Modify: `docker-compose.yml`（api 服务 volumes）
- Modify: `web/src/apis/base.js`（新增 apiPatch）
- Modify: `web/src/apis/eia_data_api.js`（library 方法组）

- [ ] **Step 5.1: docker-compose.yml — api 服务 volumes 追加（仿 threads 长语法）**

在 api 服务（运行栈容器名 pisuan-localized-api-1 对应的服务块）volumes 列表追加：

```yaml
      - source: ${YUXI_STATE_DIR:-./docker/volumes}/yuxi/eia-library
        target: /app/eia-library
        type: bind
```

- [ ] **Step 5.2: base.js — 新增 apiPatch（仿 apiDelete，method 换 PATCH；放在 apiPost 区之后）**

```js
export function apiPatch(url, data = {}, options = {}, requiresAuth = true, responseType = 'json') {
  return apiRequest(
    url,
    {
      method: 'PATCH',
      body: data instanceof FormData ? data : JSON.stringify(data),
      ...options
    },
    requiresAuth,
    responseType
  )
}
```

- [ ] **Step 5.3: eia_data_api.js — 导入扩展 + 方法组**

导入行改为 `import { apiDelete, apiGet, apiPatch, apiPost, apiRequest } from './base'`，对象内追加：

```js
  // ── 环评文件库（P1：上传即登记；加工属 P2 显式触发）──

  listLibraryFolders: () => apiGet('/api/domain-factory/eia/library/folders'),

  listLibraryFiles: (folderId, q) => {
    const params = new URLSearchParams()
    if (folderId != null) params.set('folder_id', String(folderId))
    if (q) params.set('q', q)
    const qs = params.toString()
    return apiGet(`/api/domain-factory/eia/library/files${qs ? `?${qs}` : ''}`)
  },

  uploadLibraryFile: (file, folderId) => {
    const form = new FormData()
    form.append('file', file)
    if (folderId != null) form.append('folder_id', String(folderId))
    return apiPost('/api/domain-factory/eia/library/files', form)
  },

  downloadLibraryFile: (id) =>
    apiRequest(`/api/domain-factory/eia/library/files/${id}/download`, {}, true, 'blob'),

  moveLibraryFile: (id, folderId) =>
    apiPatch(`/api/domain-factory/eia/library/files/${id}`, { folder_id: folderId }),

  deleteLibraryFile: (id) => apiDelete(`/api/domain-factory/eia/library/files/${id}`)
```

- [ ] **Step 5.4: 验证 + Commit**

```bash
docker compose config -q && echo COMPOSE_OK
cd web && node node_modules/prettier/bin/prettier.cjs --write src/apis/base.js src/apis/eia_data_api.js && cd ..
git add docker-compose.yml web/src/apis/base.js web/src/apis/eia_data_api.js
git commit -m "feat(domain-factory): 文件库存储卷挂载与前端 API 层

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

Expected: COMPOSE_OK；prettier 无差异报错。

---

### Task 6: 前端页面（LibraryPanel + 视图 + 路由 + 菜单）

**Files:**
- Create: `web/src/components/eia-data/LibraryPanel.vue`
- Create: `web/src/views/EiaLibraryView.vue`
- Modify: `web/src/router/index.js`（eia-data children 增加 library）
- Modify: `web/src/components/eia-data/EiaDataLayout.vue`（菜单 + FolderOpen 图标）

- [ ] **Step 6.1: router/index.js — meta 子路由后插入**

```js
            {
              path: 'library',
              name: 'EiaDataLibrary',
              component: () => import('../views/EiaLibraryView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
```

- [ ] **Step 6.2: EiaDataLayout.vue — lucide 导入加 `FolderOpen`；「语料与护栏」items **首位**插入**

```js
      { to: '/domain-factory/eia-data/library', label: '环评文件库', icon: FolderOpen },
```

- [ ] **Step 6.3: EiaLibraryView.vue**

```vue
<template>
  <LibraryPanel />
</template>

<script setup>
import LibraryPanel from '@/components/eia-data/LibraryPanel.vue'
</script>
```

- [ ] **Step 6.4: LibraryPanel.vue（完整组件）**

```vue
<template>
  <div class="lib">
    <!-- 标题卡（原型 head 区） -->
    <div class="card head-card">
      <span class="head-ic"><FolderOpen :size="18" /></span>
      <div class="head-tx">
        <h2>环评文件库</h2>
        <p class="dim">上传即登记 · 加工需显式触发（加工通道 P2 上线）</p>
      </div>
    </div>

    <div class="card body-card">
      <div class="toolbar">
        <span class="crumb">{{ scopeLabel }}</span>
        <div class="tools">
          <a-input
            v-model:value="q"
            class="search"
            placeholder="搜索文件名（全库）"
            allow-clear
            @press-enter="reload"
          />
          <input ref="fileInput" type="file" multiple accept=".docx,.pdf" hidden @change="onPickFiles" />
          <button class="btn btn-sm" :disabled="uploading" @click="$refs.fileInput.click()">
            <Upload :size="14" /> 上传
          </button>
        </div>
      </div>

      <div class="split">
        <!-- 左树：未归类 + 五阶段（固定两层，P1 无文件夹管理） -->
        <aside class="tree">
          <button
            class="tree-node"
            :class="{ on: folderId === null && !q }"
            @click="pickFolder(null)"
          >
            <Folder :size="14" /> 未归类 <span class="cnt">{{ rootCount }}</span>
          </button>
          <button
            v-for="f in folders"
            :key="f.id"
            class="tree-node"
            :class="{ on: folderId === f.id && !q }"
            @click="pickFolder(f.id)"
          >
            <Folder :size="14" /> {{ f.name }} <span class="cnt">{{ f.file_count }}</span>
          </button>
        </aside>

        <!-- 文件表 -->
        <div class="tbl-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th>文件名</th>
                <th style="width: 10%">状态</th>
                <th style="width: 9%">类型</th>
                <th style="width: 9%">大小</th>
                <th style="width: 13%">上传日期</th>
                <th class="r" style="width: 7%">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in files" :key="f.id">
                <td>
                  <div class="fname">{{ f.original_filename }}</div>
                  <div v-if="q" class="dim">位于〈{{ f.folder_name || '未归类' }}〉</div>
                </td>
                <td><span class="pill pill-ok">已入库</span></td>
                <td>{{ typeLabel(f.original_filename) }}</td>
                <td>{{ fmtSize(f.size_bytes) }}</td>
                <td>{{ fmtDate(f.created_at) }}</td>
                <td class="r">
                  <a-dropdown :trigger="['click']">
                    <button class="btn btn-txt btn-sm" title="更多操作">···</button>
                    <template #overlay>
                      <a-menu @click="({ key }) => onRowMenu(key, f)">
                        <a-menu-item key="download"><Download :size="14" /> 下载</a-menu-item>
                        <a-menu-item key="move"><FolderInput :size="14" /> 移动到…</a-menu-item>
                        <a-menu-item key="delete" class="danger"><Trash2 :size="14" /> 删除</a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>
                </td>
              </tr>
              <tr v-if="!files.length">
                <td colspan="6" class="empty">
                  暂无文件 — 点右上「上传」导入环评报告样例（docx / pdf）
                </td>
              </tr>
            </tbody>
          </table>
          <div class="tbl-foot">
            共 {{ files.length }}（{{ scopeLabel }}）· 已登记 {{ totalCount }}（全库）
          </div>
        </div>
      </div>
    </div>

    <!-- 移动对话框 -->
    <a-modal v-model:open="moveDlg.open" title="移动到文件夹" ok-text="移动" cancel-text="取消" @ok="doMove">
      <a-select v-model:value="moveDlg.folderId" style="width: 100%" :options="moveOptions" />
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { Download, Folder, FolderInput, FolderOpen, Trash2, Upload } from 'lucide-vue-next'
import { eiaDataApi } from '@/apis/eia_data_api'

const folders = ref([])
const files = ref([])
const folderId = ref(null) // null = 未归类（根）
const q = ref('')
const totalCount = ref(0)
const uploading = ref(false)
const fileInput = ref(null)
const moveDlg = reactive({ open: false, fileId: null, folderId: null })

const rootCount = computed(
  () => totalCount.value - folders.value.reduce((sum, f) => sum + (f.file_count || 0), 0)
)
const scopeLabel = computed(() =>
  q.value ? `全库搜索「${q.value}」` : folders.value.find((f) => f.id === folderId.value)?.name || '未归类'
)
const moveOptions = computed(() => [
  { value: null, label: '未归类' },
  ...folders.value.map((f) => ({ value: f.id, label: f.name }))
])

const reload = async () => {
  const queryFolder = q.value ? null : folderId.value
  const [folderRes, fileRes] = await Promise.all([
    eiaDataApi.listLibraryFolders(),
    eiaDataApi.listLibraryFiles(queryFolder, q.value || undefined)
  ])
  folders.value = folderRes.folders
  totalCount.value = folderRes.total_files
  files.value = fileRes.files
}

const pickFolder = (id) => {
  folderId.value = id
  q.value = ''
  reload()
}

const onPickFiles = async (e) => {
  const list = [...e.target.files]
  e.target.value = ''
  if (!list.length) return
  uploading.value = true
  try {
    for (const file of list) {
      try {
        await eiaDataApi.uploadLibraryFile(file, folderId.value)
        message.success(`「${file.name}」已登记`)
      } catch (err) {
        if (err?.status === 409) message.warning(`「${file.name}」${err.message}`)
        else message.error(`「${file.name}」上传失败：${err?.message || '未知错误'}`)
      }
    }
  } finally {
    uploading.value = false
    await reload()
  }
}

const onRowMenu = (key, f) => {
  if (key === 'download') doDownload(f)
  else if (key === 'move') {
    moveDlg.fileId = f.id
    moveDlg.folderId = f.folder_id
    moveDlg.open = true
  } else if (key === 'delete') confirmDelete(f)
}

const doMove = async () => {
  try {
    await eiaDataApi.moveLibraryFile(moveDlg.fileId, moveDlg.folderId)
    message.success('已移动')
    moveDlg.open = false
    await reload()
  } catch (err) {
    message.error(err?.message || '移动失败')
  }
}

const confirmDelete = (f) => {
  Modal.confirm({
    title: '删除文件',
    content: `将删除「${f.original_filename}」及其磁盘文件，不可恢复。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      await eiaDataApi.deleteLibraryFile(f.id)
      message.success('已删除')
      await reload()
    }
  })
}

const doDownload = async (f) => {
  try {
    const blob = await eiaDataApi.downloadLibraryFile(f.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = f.original_filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err?.message || '下载失败')
  }
}

const typeLabel = (name) => (/\.pdf$/i.test(name) ? 'PDF' : /\.docx$/i.test(name) ? 'DOCX' : '其他')
const fmtSize = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`)
const fmtDate = (s) => (s ? String(s).slice(0, 10).replaceAll('-', '/') : '')

onMounted(reload)
</script>

<style scoped lang="less">
.lib {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.head-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  .head-ic {
    color: var(--color-primary-600);
  }
  h2 {
    margin: 0;
    font-size: 15px;
  }
  p {
    margin: 2px 0 0;
    font-size: 12px;
  }
}
.body-card {
  padding: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  .tools {
    display: flex;
    gap: 8px;
  }
  .search {
    width: 220px;
  }
  .crumb {
    font-size: 13px;
    font-weight: 600;
  }
}
.split {
  display: flex;
  min-height: 320px;
}
.tree {
  width: 168px;
  flex: none;
  padding: 10px 8px;
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 0;
  background: none;
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text);
  cursor: pointer;
  text-align: left;
  .cnt {
    margin-left: auto;
    font-size: 11px;
    color: var(--color-text-tertiary);
  }
  &:hover {
    background: var(--color-fill-quaternary);
  }
  &.on {
    background: var(--color-primary-50);
    color: var(--color-primary-700);
    font-weight: 600;
  }
}
.tbl-wrap {
  flex: 1;
  min-width: 0;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  th,
  td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--color-border-split);
    font-size: 13px;
    text-align: left;
    overflow-wrap: break-word;
  }
  th {
    color: var(--color-text-secondary);
    font-weight: 600;
    background: var(--color-fill-quaternary);
  }
  .r {
    text-align: right;
  }
  .fname {
    word-break: break-all;
  }
  .empty {
    text-align: center;
    color: var(--color-text-tertiary);
    padding: 32px 0;
  }
}
.tbl-foot {
  padding: 8px 14px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.dim {
  color: var(--color-text-tertiary);
  font-size: 12px;
}
.pill-ok {
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: var(--color-success-50, var(--color-fill-quaternary));
  color: var(--color-success-700, var(--color-text));
}
.danger {
  color: var(--color-error-600);
}
</style>
```

注：pill/按钮/卡片基础类若 eia-data 既有共享样式已定义（`MetaPanel.vue` 同款 `.card/.btn/.pill`），以复用既有全局/共享类为准、删去重复定义；以渲染效果一致为验收。

- [ ] **Step 6.5: 前端链验证**

```bash
cd web && node node_modules/prettier/bin/prettier.cjs --write src/components/eia-data/LibraryPanel.vue src/views/EiaLibraryView.vue src/router/index.js src/components/eia-data/EiaDataLayout.vue && cd ..
powershell.exe -NoProfile -File scripts/sync-dev.ps1
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-web-1 sh -c "cd /app && ./node_modules/.bin/eslint src/components/eia-data/LibraryPanel.vue src/views/EiaLibraryView.vue src/router/index.js src/components/eia-data/EiaDataLayout.vue" && echo ESLINT_EXIT_0
```

Expected: ESLINT_EXIT_0；浏览器（isolatedContext，admin 登录）打开 `/domain-factory/eia-data/library` 菜单首位出现「环评文件库」，页面渲染出标题卡/左树五夹/空态文案。

- [ ] **Step 6.6: Commit**

```bash
git add web/src/components/eia-data/LibraryPanel.vue web/src/views/EiaLibraryView.vue web/src/router/index.js web/src/components/eia-data/EiaDataLayout.vue
git commit -m "feat(domain-factory): 环评文件库页面（上传/检索/下载/移动/删除）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 浏览器 QA（AC1–9）+ 文档收尾

- [ ] **Step 7.1: 卷生效确认** — `docker compose` 层面卷已在 Task 5 声明；运行栈需 `docker compose up -d api` 重建一次（挂载不热生效），随后 `docker exec pisuan-localized-api-1 ls /app/eia-library` 确认挂载点存在。

- [ ] **Step 7.2: 浏览器 QA**（isolatedContext + admin 表单登录；截图存 `.wolf/lib_qa_*.jpeg`）：

| AC | 操作 | 期望 |
|---|---|---|
| AC1 | 上传 1 个 docx + 批量 2 个到「规划环评」 | 列表即时可见，toast 逐文件成功；明暗两态截图 |
| AC2 | 容器内 `ls /app/eia-library` + DB 查 | `<sha1 12位>__<原名>` 落盘；DB sha1/size/uploaded_by 正确 |
| AC3 | 同文件再传 | warning toast 带〈既有文件夹〉，无重复行 |
| AC4 | 搜索框输关键词 | 全库命中，文件名下有「位于〈…〉」 |
| AC5 | 下载 | 原名落盘，sha1 与库内一致 |
| AC6 | 移动到另一夹 / 删除 | 行内即时更新；删除有确认框、磁盘文件消失 |
| AC7 | 底栏计数 | 共 N（当前范围）· 已登记 M（全库）正确 |
| AC8 | 全页走查 | 无任何加工入口（解析队列/加入加工） |
| AC9 | >100MB 文件（dd 生成） | 413 toast 明确文案 |

- [ ] **Step 7.3: changelog + 收尾**

`docs/develop-guides/changelog.md` 追加条目（环评文件库 P1：上传即登记/五阶段夹/sha1 去重/六端点/前端页；指向 spec 与本 plan）。

```bash
python -m ruff format backend/package/yuxi/services/eia_library_service.py backend/package/yuxi/repositories/eia_library_repository.py backend/server/routers/domain_factory_router.py backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/package/yuxi/storage_migration.py
python -m ruff check backend/ 2>&1 | tail -2
git add docs/develop-guides/changelog.md
git commit -m "docs(domain-factory): 环评文件库 P1 changelog

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 7.4: 汇报** — AC 表逐项结果 + 截图路径 + 遗留（如有）报给用户；push/再生 pisuan-localized 等用户明示指令。

---

## Self-Review 记录

- **Spec 覆盖**：D1（本计划不含回填任务，字段契约在 Task 1/3 落地）✓；D2 两表+volume+独立页（Task 1/5/6）✓；D3 收 docx/pdf——前端 accept 但**后端不拒**（库不把门，其他扩展名也可入库显示「其他」类型）✓；D4 五夹种子+未归类（Task 1）✓；D5 页面无加工入口（AC8）✓；D6 无预览（AC8 反向覆盖）✓；AC1–9 → Task 7 表 ✓。
- **与 spec 的两处收敛说明**：① 409 的 `existing` 结构化字段收敛为 detail 文案（toast 语义等价）；② folders 端点增补 `total_files`（底栏全库计数需要）。
- **占位符扫描**：无 TBD/TODO；所有代码步骤给出完整代码或精确仿写对象（v16_to_v17/apiDelete）。
- **类型一致性**：`to_dict()`/`folder_name`/`file_count`/`total_files` 在 Task 2→4→6 间传递一致；`FileExistsError`/`LibraryFileTooLarge`/`ValueError`/`FileNotFoundError` 四异常在 Task 3→4 映射闭合。
