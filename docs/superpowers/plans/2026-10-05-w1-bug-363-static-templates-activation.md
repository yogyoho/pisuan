# bug-363 W1 第二项实施计划：静态模板容器激活 + 部署一致性清查

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 bug-363（容器栈 `/app/templates` 双缺口：镜像无 COPY、compose 无挂载 → 静态模板 30 条从未加载），并按 D2 拍板采集激活行为证据（ETL 命中构成 / 写手 source 分布 / D3 遮蔽），顺带完成 D3 部署一致性清查。

**Architecture:** 纯部署修复（Dockerfile COPY + compose api/worker 双挂载，零代码改动）→ 重建容器 → 三层验收（即时冒烟 / 真实 ETL 观测 / 写手侧观测）→ 资产断裂清查立案。

**Tech Stack:** Docker Compose / ARQ worker / pytest / SQL 观测

**设计依据:** [2026-10-05-bug-363-static-templates-activation-design.md](../specs/2026-10-05-bug-363-static-templates-activation-design.md)

---

## 全局上下文（每个 implementer 必读）

- 运行栈 compose 项目目录 = `C:\workspace\pisuan-localized`（容器 `pisuan-localized-api-1` / `pisuan-localized-worker-1`）。**localized 树勿直接语义开发**——改动一律先做在 `C:\workspace\pisuan` 源树，经 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1` 传播；若发现 localized 的 compose/Dockerfile 未被 sync 携带（手工维护），**停手上报**，由主控决定是否改 sync-dev 脚本。
- 挂载变更**必须重建容器**（`docker compose up -d api worker`），restart 无效。
- `docker exec` 一律 `MSYS_NO_PATHCONV=1` 前缀；容器内 python 脚本一律 `python -u`（bug-364：否则连接池线程挂住 + 块缓冲假死）。
- 容器内包名 `pisuan`；`pg_manager` 从 `pisuan.storage.postgres.manager` 导入（bug-362）。
- 回归口径（bug-360）：`pytest /app/test/unit` → **2681 passed / 0 failed / 61 skipped**；勿用 `/app/test`。
- **禁碰文件**（严禁卷入提交）：`backend/package/yuxi/agents/buildin/chatbot/prompt.py`、`backend/server/utils/lifespan.py`、`web/src/components/AgentChatComponent.vue`、`web/src/components/SettingsModal.vue`、其他会话未提交 docs。
- 管理员凭据在 `.env`（只读使用，严禁把密码明文写进报告/日志/提交）。
- 提交信息：中文 Conventional Commits + `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 1: 部署修复 + 即时激活验证

**Files:**
- Modify: `docker/api.Dockerfile`（:61 `COPY backend/server /app/server` 之后加一行）
- Modify: `docker-compose.yml`（api 服务 volumes 块 + worker 服务 volumes 块各加一行）

- [ ] **Step 1: Dockerfile 加 COPY**

```dockerfile
# 在 COPY backend/server /app/server 之后加：
COPY backend/templates /app/templates
```

- [ ] **Step 2: compose api + worker 双挂载**

api 服务（:56 volumes 块）与 worker 服务（:122 volumes 块）各加：

```yaml
      - ./backend/templates:/app/templates:ro
```

- [ ] **Step 3: 同步 + 验证传播**

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sync-dev.ps1
grep -n "templates" C:/workspace/pisuan-localized/docker-compose.yml
grep -n "templates" C:/workspace/pisuan-localized/docker/api.Dockerfile
```

Expected: 两个 grep 各有命中。**若无命中 → localized compose/Dockerfile 未被 sync 携带 → 停手上报（BLOCKED），勿直接改 localized 树。**

- [ ] **Step 4: 重建容器 + 验证挂载**

```bash
cd /c/workspace/pisuan-localized && docker compose up -d api worker && cd /c/workspace/pisuan
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 ls /app/templates
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-worker-1 ls /app/templates/coal/headers | wc -l
```

Expected: api 侧列出 `coal` 目录；worker 侧 30 个文件。

- [ ] **Step 5: 激活冒烟（-u！）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -u -c "
from pisuan.services.template_library import TemplateLibrary
from pisuan.services.template_matcher import TemplateMatcher
import asyncio
from pisuan.repositories.domain_factory_repository import DomainFactoryRepository

lib = TemplateLibrary()
lib.load_templates()
static = list(lib.templates.values())
print(f'static loaded={len(static)}, domains={set(t.get(\"domain\") for t in static)}')
assert len(static) == 30 and all(t.get('domain') == 'coal' for t in static)

async def main():
    learned = await DomainFactoryRepository().list_learned_templates(domain_code='coal', limit=200)
    lib.add_templates_from_list(learned)
    matcher = TemplateMatcher(lib.get_all_templates())
    hits_s = sum(1 for t in static if (t.get('match_rule') or {}).get('fallback_keywords')
                 and matcher.match('9.1 ' + t['match_rule']['fallback_keywords'][0], context={'domain': 'coal'}).matched)
    hits_l = sum(1 for t in learned if matcher.match(t['chapter'], context={'domain': 'coal'}).matched)
    print(f'templates total={len(matcher.templates)} (static 30 + learned {len(learned)}), static-probe hits={hits_s}/30, learned self-match={hits_l}')
    assert hits_s >= 28 and hits_l > 0
asyncio.run(main())
"
```

Expected: `static loaded=30, domains={'coal'}`；`total=230`；`static-probe hits ≥28/30`（个别正则怪癖可容忍，低于 28 要逐个人工核查原因）；`learned self-match ≥1`。

- [ ] **Step 6: unit 全量回归**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 pytest /app/test/unit -q --no-header 2>&1 | tail -3
```

Expected: `2681 passed, 0 failed, 61 skipped`。

- [ ] **Step 7: 提交**

```bash
git add docker/api.Dockerfile docker-compose.yml
git commit -m "fix: bug-363 静态模板容器激活——镜像 COPY + compose api/worker 双挂载

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 行为观测 + 部署一致性清查 + 收尾

**Files:**
- Modify: `docs/develop-guides/changelog.md`、`.wolf/buglog.json`、`.wolf/anatomy.md`、`.wolf/memory.md`

- [ ] **Step 1: 真实 ETL 观测**

用 `.env` 管理员凭据调 API 重解析一个既有已提交任务（先 `grep -n "重新\|reparse\|reprocess\|重跑" backend/server/routers/domain_factory_router.py` 定位端点；无现成端点则改用上传-审核一条新样例的完整链，凭据只从 .env 读）。ARQ 任务在 worker 执行，`docker logs pisuan-localized-worker-1 --tail 100` 观测。完成后记录该任务段落 `template_match` 的 static（非 `learned_` 前缀）/learned 构成。

**降级预案**：模型端点容器不可达或无可用样例 → 观察窗挂起，在 buglog-363 与 changelog 写明「待自然流量，判定标准 = 首次真实 ETL 完成后按本步口径采集」，不得造假数据。

- [ ] **Step 2: 写手侧观测基线**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -u -c "
import asyncio
from sqlalchemy import select, func
from pisuan.storage.postgres.manager import pg_manager
from pisuan.storage.postgres.models_domain_factory import DomainFactoryToolUsage
async def main():
    async with pg_manager.get_async_session_context() as s:
        rows = (await s.execute(select(DomainFactoryToolUsage.tool_name, DomainFactoryToolUsage.source, func.count()).group_by(DomainFactoryToolUsage.tool_name, DomainFactoryToolUsage.source))).all()
        print(f'total={sum(r[2] for r in rows)}')
        for r in rows: print(f'  {r[0]:24s} source={str(r[1]):10s} count={r[2]}')
asyncio.run(main())
"
```

记录为激活后基线（激活前 total=6 全 graph 冒烟）；后续 O6 裁决时对比 graph→db 转移。

- [ ] **Step 3: 部署一致性清查（D3，只立案不修复）**

```bash
grep -rn 'Path(__file__).parent' backend/package backend/server --include="*.py" | grep -v test | grep -vE 'parent\"\)$|parent, ' | head -40
```

对每处向上跳目录后落在 package/server 之外的资产引用，逐一在容器内 `ls` 验证存在性（`/app` 下 package、server、templates 之外缺什么）。产出清单（file:line → 容器内目标路径 → 存在/缺失），缺失项写入 buglog 新条目（一条汇总条即可，id 顺延 bug-365）。

- [ ] **Step 4: 收尾**

- changelog：`### pisuan 定制增量（2026-10-05）` 追加 `- fix(bug-363): 静态模板容器激活（镜像 COPY + compose api/worker 双挂载），附激活行为观测与 /app 资产断裂清查`
- buglog：bug-363 原位更新（fix 写实际修复 + 观测结果；ETL 观测降级时如实标注挂起）
- anatomy：docker-compose/Dockerfile 相关条目如需更新则更新；memory 追加一行
- 提交：

```bash
git add docs/develop-guides/changelog.md .wolf/buglog.json .wolf/anatomy.md .wolf/memory.md .wolf/cerebrum.md
git commit -m "docs: bug-363 收尾——激活观测与部署一致性清查立案

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成定义（DoD）

1. 两任务 checkbox 勾完，两笔提交落在 pisuan-custom 顶端并推送（推送由主控在终审后执行）。
2. 容器内 `/app/templates` 于 api+worker 双双在位；冒烟 30 静态 + 学习共存、static-probe ≥28/30。
3. unit 全量 2681/0/61 不回归。
4. ETL 观测数据或挂起判定标准落档；写手侧基线记录；清查清单立案。
