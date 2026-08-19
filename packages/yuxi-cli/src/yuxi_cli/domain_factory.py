"""Domain Factory CLI — batch upload, task inspection, and pipeline triggers."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from yuxi_cli.client import ClientError, YuxiClient
from yuxi_cli.config import ConfigStore

# ---------------------------------------------------------------------------
# ETL pipeline status mapping
# ---------------------------------------------------------------------------

_PIPELINE_STAGES = [
    ("uploaded", "已上传"),
    ("parsed", "已解析"),
    ("classified", "已分类"),
    ("generalized", "已泛化"),
    ("waiting_review", "待审核"),
    ("committed", "已入库"),
]

_TERMINAL_STATUSES = {"committed", "failed"}

_STATUS_ICONS = {
    "uploaded": "📤",
    "parsed": "📄",
    "classified": "🏷️",
    "generalized": "📝",
    "waiting_review": "⏳",
    "committed": "✅",
    "failed": "❌",
}


def _status_label(status: str) -> str:
    for key, label in _PIPELINE_STAGES:
        if key == status:
            return f"{_STATUS_ICONS.get(key, '•')} {label}"
    return f"{_STATUS_ICONS.get(status, '•')} {status}"


def _render_task_table(tasks: list[dict], console: Console) -> None:
    if not tasks:
        console.print("[dim]无匹配任务[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Task ID", style="dim", width=28)
    table.add_column("文件名")
    table.add_column("领域")
    table.add_column("状态")
    table.add_column("报告类型")
    for t in tasks:
        task_id = t.get("task_id") or t.get("id", "-")
        file_name = t.get("file_name") or t.get("title", "-")
        domain = t.get("domain_code") or t.get("domain", "-")
        status = t.get("status") or t.get("df_status", "-")
        report_type = t.get("report_type_code") or t.get("report_type", "-")
        table.add_row(
            task_id,
            file_name[:60],
            domain,
            _status_label(status),
            report_type,
        )
    console.print(table)


def _render_task_detail(detail: dict, console: Console) -> None:
    status = detail.get("status") or detail.get("df_status", "-")
    lines = [
        f"[bold]Task ID:[/bold] {detail.get('task_id') or detail.get('id', '-')}",
        f"[bold]文件名:[/bold] {detail.get('file_name') or detail.get('title', '-')}",
        f"[bold]领域:[/bold] {detail.get('domain_code') or detail.get('domain', '-')}",
        f"[bold]状态:[/bold] {_status_label(status)}",
        f"[bold]报告类型:[/bold] {detail.get('report_type_code') or detail.get('report_type', '-')}",
        f"[bold]上传者:[/bold] {detail.get('uploaded_by') or detail.get('created_by', '-')}",
    ]
    error = detail.get("error") or detail.get("error_message") or ""
    if error:
        lines.append(f"[red][bold]错误:[/bold] {error}[/red]")
    console.print(Panel("\n".join(lines), title="任务详情"))


def _resolve_domain(client: YuxiClient, domain: str | None) -> str:
    if domain:
        return domain
    domains = client.list_domains().get("items", [])
    if not domains:
        raise ClientError("未找到任何领域，请先用 Web 界面创建领域")
    if len(domains) == 1:
        return domains[0]["code"]
    names = [d["code"] for d in domains]
    raise ClientError(f"必须指定 --domain，可用领域: {', '.join(names)}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class DomainFactoryError(Exception):
    pass


def upload_files(
    store: ConfigStore,
    remote_name: str | None,
    paths: list[Path],
    domain: str | None,
    document_type: str,
    report_type_code: str,
    wait: bool,
    poll_seconds: float,
    console: Console,
) -> None:
    config = store.load()
    remote = config.get_remote(remote_name)

    with YuxiClient(remote) as client:
        domain = _resolve_domain(client, domain)
        console.print(f"领域: {domain}  文档类型: {document_type}  报告类型: {report_type_code}")
        console.print()

        task_ids: list[str] = []
        for path in paths:
            if not path.is_file():
                console.print(f"[yellow]跳过非文件: {path}[/yellow]")
                continue
            console.print(f"上传: {path.name} ...", end=" ")
            try:
                result = client.upload_domain_file(
                    path,
                    domain=domain,
                    document_type=document_type,
                    report_type_code=report_type_code,
                )
                task_id = result.get("task_id", "")
                if not task_id:
                    console.print("[red]失败: 未返回 task_id[/red]")
                    continue
                task_ids.append(task_id)
                console.print(f"[green]成功 → {task_id}[/green]")
            except ClientError as exc:
                console.print(f"[red]失败: {exc}[/red]")

        if not wait or not task_ids:
            return

        console.print()
        console.print(f"等待 {len(task_ids)} 个任务完成 ETL 流水线...")
        console.print()

        remaining = set(task_ids)
        deadline = time.monotonic() + 600  # max 10 minutes
        while remaining and time.monotonic() < deadline:
            done: set[str] = set()
            for tid in list(remaining):
                try:
                    detail = client.get_domain_task(tid)
                except ClientError:
                    done.add(tid)
                    continue
                status = detail.get("status") or detail.get("df_status", "")
                if status in _TERMINAL_STATUSES:
                    icon = "✅" if status == "committed" else "❌"
                    console.print(f"  {icon} {tid} → {_status_label(status)}")
                    done.add(tid)
            remaining -= done
            if remaining:
                time.sleep(poll_seconds)

        if remaining:
            console.print(f"[yellow]等待超时，{len(remaining)} 个任务仍在处理中[/yellow]")
        else:
            console.print("[green]全部任务已完成[/green]")


def list_tasks(
    store: ConfigStore,
    remote_name: str | None,
    domain: str | None,
    status: str | None,
    console: Console,
) -> None:
    config = store.load()
    remote = config.get_remote(remote_name)

    with YuxiClient(remote) as client:
        data = client.list_domain_tasks(domain=domain, status=status)
        items = data.get("items") or data.get("tasks") or []
        console.print(f"共 {len(items)} 个任务")
        console.print()
        _render_task_table(items, console)


def show_task_status(
    store: ConfigStore,
    remote_name: str | None,
    task_id: str,
    console: Console,
) -> None:
    config = store.load()
    remote = config.get_remote(remote_name)

    with YuxiClient(remote) as client:
        detail = client.get_domain_task(task_id)
        _render_task_detail(detail, console)


def retry_task(
    store: ConfigStore,
    remote_name: str | None,
    task_id: str,
    console: Console,
) -> None:
    config = store.load()
    remote = config.get_remote(remote_name)

    with YuxiClient(remote) as client:
        detail = client.retry_domain_task(task_id)
        console.print(f"[green]已触发重试: {task_id}[/green]")


def commit_task(
    store: ConfigStore,
    remote_name: str | None,
    task_id: str,
    kb_id: str | None,
    console: Console,
) -> None:
    config = store.load()
    remote = config.get_remote(remote_name)

    with YuxiClient(remote) as client:
        detail = client.commit_domain_task(task_id, kb_id=kb_id)
        ingest_id = detail.get("ingest_task_id") or ""
        msg = f"[green]已入库: {task_id}[/green]"
        if ingest_id:
            msg += f"  (ingest: {ingest_id})"
        console.print(msg)
