# 手动触发归一化全集同步链（与实体变更后的自动同步同一套步骤）：
#   聚类校验 → 归并候选 → 全集导出 → Gitea 发布
# 用法（api 容器内）：
#   python -m scripts.governance.sync_normalization_inventory
import subprocess
import sys

STEPS = [
    ["python", "-m", "scripts.governance.audit_normalization", "--out", "/tmp/normalization-report.json"],
    ["python", "-m", "scripts.governance.report_merge_candidates", "--out", "/tmp/merge-candidates.json"],
    ["python", "-m", "scripts.governance.export_normalization_inventory"],
    ["python", "-m", "scripts.governance.publish_inventory_to_gitea"],
]

for cmd in STEPS:
    print(f"== {' '.join(cmd[3:])}", flush=True)
    r = subprocess.run(cmd, cwd="/app")
    if r.returncode != 0:
        print(f"步骤失败 exit={r.returncode}: {' '.join(cmd)}")
        sys.exit(r.returncode)
print("同步链完成：全集已发布 Gitea")
