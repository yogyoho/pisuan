# 归一化全集清单发布到 Gitea（文件版本管理，供环评工程师查看/确认/追溯历史版本）。
#
# 数据源：/tmp/normalization-inventory/（export_normalization_inventory.py 产出）
# 目标：Gitea refsadmin/normalization-inventory 仓库（不存在则自动创建，internal 可读）
# 凭据：GITEA_REFS_USER / GITEA_REFS_PASSWORD（复用 refs-git 链的 push 凭据，勿入库）
# 地址：GITEA_API_BASE（默认 http://gitea:3000，api 容器内网直连）
#
# 用法（api 容器内）：
#   python -m scripts.governance.publish_inventory_to_gitea
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT_DIR = Path("/tmp/normalization-inventory")
FILES = ["归一化全集清单.md", "inventory.json"]
OWNER = "refsadmin"
REPO = "normalization-inventory"
API_BASE = os.environ.get("GITEA_API_BASE", "http://gitea:3000") + "/api/v1"
AUTH = (
    os.environ.get("GITEA_REFS_USER", "refsadmin"),
    os.environ.get("GITEA_REFS_PASSWORD", ""),
)


def main() -> None:
    if not AUTH[1]:
        print("GITEA_REFS_PASSWORD 未配置")
        sys.exit(1)

    # 1) 仓库存在性：404 则创建（internal 可读）
    r = requests.get(f"{API_BASE}/repos/{OWNER}/{REPO}", auth=AUTH, timeout=30)
    if r.status_code == 404:
        r = requests.post(
            f"{API_BASE}/user/repos",
            auth=AUTH,
            json={"name": REPO, "private": False, "description": "实体/属性归一化全集清单（自动导出，工程师确认工作稿）"},
            timeout=30,
        )
        print(f"仓库已创建: {r.status_code}")
    else:
        print(f"仓库已存在: {r.status_code}")

    ts = time.strftime("%Y-%m-%d %H:%M")
    for fname in FILES:
        local = OUT_DIR / fname
        if not local.exists():
            print(f"跳过（本地不存在）: {fname}")
            continue
        content = local.read_bytes()
        # 已有文件取 sha（PUT 更新必须带 sha）
        r = requests.get(
            f"{API_BASE}/repos/{OWNER}/{REPO}/contents/{fname}", auth=AUTH, timeout=30
        )
        payload = {
            "content": base64.b64encode(content).decode("ascii"),
            "message": f"归一化全集清单刷新 {ts}（293 实体 / 属性候选 205 组 / 实体候选 22 对）",
        }
        if r.status_code == 200:
            payload["sha"] = r.json()["sha"]
            r = requests.put(
                f"{API_BASE}/repos/{OWNER}/{REPO}/contents/{fname}", auth=AUTH, json=payload, timeout=60
            )
            action = "更新"
        else:
            r = requests.post(
                f"{API_BASE}/repos/{OWNER}/{REPO}/contents/{fname}", auth=AUTH, json=payload, timeout=60
            )
            action = "新建"
        ok = r.status_code in (200, 201)
        print(f"{action} {fname}: {'OK' if ok else f'FAIL {r.status_code} {r.text[:120]}'}")

    print(f"\n工程师访问入口: {os.environ.get('GITEA_API_BASE', 'http://gitea:3000').replace('/api/v1', '')}/{OWNER}/{REPO}")


if __name__ == "__main__":
    main()
