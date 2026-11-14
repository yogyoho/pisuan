"""E2E 诊断脚本①：数据源页 + 工作台读链（真实栈，服务层等价路径）。

覆盖页面：数据源页（上传/任务列表/原文预览）、工作台 Step1 读（任务详情/段落树/校验）。

流程：
  1. python-docx 合成一份小型「探针技术说明」docx（标题层级/正文/表格）
  2. save_uploaded_file + create_task（与 POST /upload 完全同路径）→ 任务行 UPLOADED + tasker 入队
  3. 轮询任务状态，记录观察到的状态序列（真实 worker ETL）
  4. 断言数据源页读端点（list_pending_tasks）与工作台读端点（get_task_detail）的页面级数据形态
  5. validate_task 只读校验（不改状态）
  6. 成功则把 task_id 写入 /tmp/e2e_probe_task_id.txt 供脚本②（commit 链）使用；失败则清理

用法（api 容器内）：
  docker exec pisuan-localized-api-1 uv run --no-sync python /app/scripts/verify_source_etl_e2e.py
退出码：0=全部通过；1=存在 FAIL。任务保留给脚本②（其 finally 负责彻底清理）。
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import uuid

from docx import Document
from sqlalchemy import select

from pisuan.repositories.domain_factory_repository import GENERAL_DOMAIN_CODE
from pisuan.services.domain_factory_service import get_domain_factory_service
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import DomainFactoryLearnedTemplate

TASK_ID_FILE = "/tmp/e2e_probe_task_id.txt"
MATCHCOUNT_FILE = "/tmp/e2e_probe_matchcounts.json"
FILE_NAME = "E2E探针技术说明.docx"
POLL_INTERVAL = 3
POLL_TIMEOUT = 600

_checks: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _checks.append((bool(ok), f"{label}{('：' + detail) if detail else ''}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return bool(ok)


def build_probe_docx() -> bytes:
    """合成探针 docx：两级标题 + 带数值正文 + 一张表（覆盖解析/切块/分类/泛化）。"""
    doc = Document()
    doc.add_heading("1 总则", level=1)
    doc.add_heading("1.1 评价目的", level=2)
    doc.add_paragraph(
        "本次评价针对探针工程开展环境影响分析，依据2026年现场调查与监测数据，"
        "识别主要环境影响因素，提出可行的污染防治措施，为工程设计与环境管理提供依据。"
    )
    doc.add_heading("2 环境现状调查", level=1)
    doc.add_heading("2.1 环境空气质量", level=2)
    doc.add_paragraph(
        "根据2026年5月监测数据，评价区二氧化氮日均浓度为0.038mg/m³，"
        "可吸入颗粒物日均浓度为0.072mg/m³，均满足《环境空气质量标准》（GB 3095-2012）二级标准要求。"
    )
    doc.add_paragraph(
        "监测期间区域主导风向为西北风，年平均风速2.3m/s，年均气温8.6℃，"
        "大气扩散条件总体一般，冬季逆温出现频率较高。"
    )
    table = doc.add_table(rows=3, cols=3)
    rows = [("监测因子", "日均浓度", "标准限值"), ("二氧化氮", "0.038mg/m³", "0.08mg/m³"), ("可吸入颗粒物", "0.072mg/m³", "0.15mg/m³")]
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            table.rows[i].cells[j].text = val
    doc.add_heading("3 环境保护措施", level=1)
    doc.add_paragraph(
        "施工期应落实洒水降尘、密闭运输与噪声控制措施，运营期配套建设布袋除尘设施，"
        "确保颗粒物排放满足《大气污染物综合排放标准》（GB 16297-1996）要求。"
    )
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def wait_task(svc, task_id: str) -> tuple[str, list[str]]:
    states: list[str] = []
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        task = await svc.repo.get_task(task_id)
        if task is None:
            return "MISSING", states
        if not states or states[-1] != task.status:
            states.append(task.status)
            print(f"       状态 → {task.status}")
        if task.status in ("WAITING_REVIEW", "FAILED", "COMMITTED", "COMMIT_FAILED", "COMMIT_PARTIAL"):
            return task.status, states
        await asyncio.sleep(POLL_INTERVAL)
    return "TIMEOUT", states


async def snapshot_match_counts() -> int:
    """ETL 的模板匹配会给他源学习模板 match_count +1（不按 attribution 隔离），
    先快照基线，供脚本③（commit 链）结束后回写差异行。"""
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.execute(
                select(DomainFactoryLearnedTemplate.id, DomainFactoryLearnedTemplate.match_count)
            )
        ).all()
    with open(MATCHCOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump({r.id: r.match_count for r in rows}, f)
    return len(rows)


async def main() -> int:
    svc = get_domain_factory_service()
    print(f"学习模板 match_count 基线快照 {await snapshot_match_counts()} 行 → {MATCHCOUNT_FILE}")
    task_id = ""
    cleanup = True
    try:
        print("===== 数据源页：上传 → ETL =====")
        content = build_probe_docx()
        task_id, path = await svc.save_uploaded_file(content, FILE_NAME, GENERAL_DOMAIN_CODE)
        dto = await svc.create_task(
            domain_code=GENERAL_DOMAIN_CODE,
            file_name=FILE_NAME,
            file_path=path,
            uploaded_by="e2e_probe",
            document_type="技术报告",
            report_type_code="通用",
        )
        check(dto.status == "UPLOADED", "S1 上传建任务行（UPLOADED）", f"task_id={dto.id}")
        task_id = dto.id

        final, states = await wait_task(svc, task_id)
        check(final == "WAITING_REVIEW", "S2 worker ETL 全链到达 WAITING_REVIEW", f"状态序列={states}")
        # GENERALIZING 只观察不判定：3s 轮询可能整段错过（实测同一脚本有时 4 态、有时 3 态），
        # 状态机正确性由 test/unit/test_commit_pipeline_status.py 的确定性用例覆盖。
        check("PARSING" in states, "S3 观察到 PARSING 中间态", f"{states}")
        print(f"  [观察] GENERALIZING 是否被轮询捕获：{'是' if 'GENERALIZING' in states else '否（跳变过快）'}")

        print("\n===== 数据源页：任务列表读端点 =====")
        pending = await svc.list_pending_tasks()
        mine = next((t for t in pending if t.get("id") == task_id), None)
        check(mine is not None, "S4 数据源页列表包含该任务（status=WAITING_REVIEW 可见）")
        if mine:
            print(f"       summary={ {k: mine.get(k) for k in ('file_name', 'status', 'document_type', 'report_type_code')} }")

        print("\n===== 工作台 Step1：任务详情/段落树/原文 =====")
        detail = await svc.get_task_detail(task_id)
        ok = detail is not None
        check(ok, "S5 get_task_detail 返回详情")
        paras = (detail or {}).get("source_paragraphs") or []
        blocks = (detail or {}).get("structured_blocks") or []
        check(len(paras) > 0, "S6 段落产物非空（前端章节树可重建）", f"paragraphs={len(paras)}")
        check(len(blocks) > 0, "S7 structured_blocks 非空（右栏五类渲染数据源）", f"blocks={len(blocks)}")
        cls = {}
        for p in paras:
            cls[p.get("classify_type") or "?"] = cls.get(p.get("classify_type") or "?", 0) + 1
        print(f"       classify_type 分布={cls}")
        gen = [p for p in paras if isinstance(p.get("template"), dict) and p["template"].get("generalized")]
        slots_total = sum(len(p["template"].get("slots") or []) for p in gen)
        check(len(gen) > 0, "S8 泛化产物：段落模板含 generalized", f"{len(gen)}/{len(paras)} 段")
        # LLM 输出方差：同一份探针文档在不同轮次实测得到 4/5/9/0 个 slot。
        # slot 可绑定性由 verify_workbench_remap_e2e.py 单独确定性验证，此处只观察不判定，
        # 否则一次模型波动就会阻断后续 commit 链脚本。
        print(f"  [观察] 模板 slot 合计={slots_total}（LLM 方差，不参与判定）")

        print("\n===== 工作台：只读校验 =====")
        before_status = (await svc.repo.get_task(task_id)).status
        report = await svc.validate_task(task_id)
        after = await svc.repo.get_task(task_id)
        check(isinstance(report, dict) and not report.get("error"), "S9 validate_task 返回校验报告",
              f"keys={list(report)[:8] if isinstance(report, dict) else type(report)}")
        check(after.status == before_status, "S10 校验只读：不改任务状态", f"{before_status}→{after.status}")

        raw_md = (await svc.repo.get_task(task_id)).raw_markdown or ""
        check(len(raw_md) > 100, "S11 原文预览可用（raw_markdown 非空）", f"{len(raw_md)} 字符")

        failures = [label for ok_, label in _checks if not ok_]
        if failures:
            print(f"\n存在 FAIL，清理探针任务: {task_id}")
        else:
            cleanup = False
            with open(TASK_ID_FILE, "w", encoding="utf-8") as f:
                f.write(task_id)
            print(f"\n任务保留给 commit 链脚本: {task_id}（写入 {TASK_ID_FILE}）")
        return 1 if failures else 0
    finally:
        if cleanup and task_id:
            try:
                await svc.delete_task(task_id)
                print(f"已清理探针任务 {task_id}")
            except Exception as e:  # noqa: BLE001
                print(f"清理失败（需人工）: {e}")
        if pg_manager.async_engine is not None:
            await pg_manager.async_engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
