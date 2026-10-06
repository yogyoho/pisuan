"""docx 入口防护：病态文件诊断 + 悬空关系项 zip 手术（bug-355）。

docx 实为 zip 包；WPS 等生成器可能写出指向不存在部件的关系项
（如 Target="NULL"），python-docx 严格解析时 KeyError 崩溃（Word 本身容错，
文件能打开，程序解析不了）。本模块提供：
- diagnose_docx：四态诊断 ok / dangling_rels / unidocsa / corrupt
- repair_dangling_rels：剔除悬空内部关系项，产出内存修复副本（原文件不动）
- guard_docx_bytes：同步守卫（大纲提取等直接以 bytes 打开的消费面）
- guarded_reparse：异步守卫（ETL 主解析失败后的诊断 + 修复重试恰一次）

设计 spec：docs/superpowers/specs/2026-10-06-bug355-etl-docx-guard-design.md
"""

import io
import logging
import posixpath
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

USER_MESSAGES = {
    "unidocsa": "文件为 WPS 私有格式（UniDocSa），非标准 docx 容器，无法解析；"
    "请用 Word/WPS 打开后另存为标准 .docx 再上传",
    "corrupt": "文件损坏或非标准 docx 容器，无法解析",
}


@dataclass
class DocxDiagnosis:
    kind: str  # "ok" | "dangling_rels" | "unidocsa" | "corrupt"
    details: list[str] = field(default_factory=list)  # 悬空条目清单（进日志，不进用户报错）


def _dangling_rels_in(member: str, payload: bytes, namelist: set[str]) -> list[tuple[str, str]]:
    """单个 .rels 内的悬空 (Id, Target) 列表；TargetMode="External" 豁免。

    Target 解析规则：以 "/" 开头按包根绝对路径；否则相对 .rels 所在部件的
    目录（word/_rels/document.xml.rels → base "word"；_rels/.rels → base ""）。
    """
    base = posixpath.dirname(posixpath.dirname(member))
    dangling: list[tuple[str, str]] = []
    for rel in ElementTree.fromstring(payload):
        if rel.get("TargetMode") == "External":
            continue
        raw_target = rel.get("Target") or ""
        if raw_target.startswith("/"):
            resolved = raw_target.lstrip("/")
        elif raw_target:
            resolved = posixpath.normpath(posixpath.join(base, raw_target))
        else:
            resolved = ""
        if resolved not in namelist:
            dangling.append((rel.get("Id") or "", raw_target))
    return dangling


def diagnose_docx(data: bytes) -> DocxDiagnosis:
    """诊断 docx bytes 的病类。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        if data[:8].startswith(b"UniDocSa"):
            return DocxDiagnosis("unidocsa", ["文件头为 WPS 私有格式 UniDocSa"])
        return DocxDiagnosis("corrupt", [f"非 zip 容器，头 8 字节 {data[:8]!r}"])

    namelist = set(zf.namelist())
    dangling: list[str] = []
    for member in zf.namelist():
        if not member.endswith(".rels"):
            continue
        for rel_id, target in _dangling_rels_in(member, zf.read(member), namelist):
            dangling.append(f"{member}: {rel_id} -> {target}")
    if dangling:
        return DocxDiagnosis("dangling_rels", dangling)
    return DocxDiagnosis("ok")


def _strip_dangling(member: str, payload: bytes, namelist: set[str]) -> bytes:
    dangling = set(_dangling_rels_in(member, payload, namelist))
    if not dangling:
        return payload
    root = ElementTree.fromstring(payload)
    for rel in list(root):
        if (rel.get("Id") or "", rel.get("Target") or "") in dangling:
            root.remove(rel)
    ElementTree.register_namespace("", RELS_NS)
    return ElementTree.tostring(root, xml_declaration=True, encoding="UTF-8")


def repair_dangling_rels(data: bytes) -> bytes:
    """剔除悬空内部关系项，返回修复副本（bytes→bytes，原数据不动）。

    其余 zip 条目逐字节原样复制（保留原 compress_type）。
    """
    diag = diagnose_docx(data)
    if diag.kind != "dangling_rels":
        raise ValueError(f"repair_dangling_rels 仅处理 dangling_rels 病类，收到 {diag.kind}")
    src = zipfile.ZipFile(io.BytesIO(data))
    namelist = set(src.namelist())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename.endswith(".rels"):
                payload = _strip_dangling(info.filename, payload, namelist)
            dst.writestr(info, payload)
    return buf.getvalue()


def guard_docx_bytes(data: bytes, label: str = "") -> bytes:
    """同步守卫：直接以 bytes 打开 docx 的消费面（大纲提取等）。

    ok → 原样返回；dangling_rels → 修复后返回（记 warning）；
    不可救病类 → ValueError(USER_MESSAGES[kind])。
    """
    diag = diagnose_docx(data)
    if diag.kind == "ok":
        return data
    if diag.kind == "dangling_rels":
        logger.warning(f"docx 存在悬空关系项，剔除后继续: {label}, 条目={diag.details}")
        return repair_dangling_rels(data)
    raise ValueError(USER_MESSAGES[diag.kind])


async def _fetch_file_bytes(file_path: str) -> bytes:
    """取任务文件 bytes：MinIO URL 走 adownload_file，本地路径走 aiofiles。"""
    from yuxi.knowledge.utils.kb_utils import is_minio_url, parse_minio_url

    if is_minio_url(file_path):
        from yuxi.storage.minio.client import get_minio_client

        bucket_name, object_name = parse_minio_url(file_path)
        return await get_minio_client().adownload_file(bucket_name, object_name)

    import aiofiles

    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


async def guarded_reparse(file_path: str, original_error: Exception, parse_fn) -> str:
    """解析失败后的 docx 守卫：诊断病类，可救则 zip 手术后重试恰一次（bug-355）。

    仅 .docx 后缀生效（剥 MinIO query 后判定，ocr_service 同款）。
    ok → 原样 re-raise（病不在文件，守卫不掩盖）；unidocsa/corrupt →
    ValueError(USER_MESSAGES) chain 原异常；dangling_rels → 修复副本重试
    一次，仍败则链式报错。原文件永不修改，临时副本 finally 清理。
    parse_fn 注入以便测试（生产传 parse_document）。
    """
    suffix = Path(file_path.split("?", 1)[0]).suffix.lower()
    if suffix != ".docx":
        raise original_error

    data = await _fetch_file_bytes(file_path)
    diag = diagnose_docx(data)
    if diag.kind == "ok":
        raise original_error
    if diag.kind in USER_MESSAGES:
        raise ValueError(USER_MESSAGES[diag.kind]) from original_error

    # dangling_rels：剔除悬空关系项后重试解析恰一次
    logger.warning(f"docx 存在悬空关系项，剔除后重试解析: {file_path}, 条目={diag.details}")
    fixed = repair_dangling_rels(data)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
            tf.write(fixed)
            temp_path = tf.name
        return await parse_fn(temp_path)
    except Exception as retry_error:  # noqa: BLE001
        raise ValueError(
            f"docx 解析失败，自动修复（剔除 {len(diag.details)} 个悬空关系项）后仍失败: {file_path}"
        ) from retry_error
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
