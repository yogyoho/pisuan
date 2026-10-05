# bug-365 W1 第三项实施计划：存量 storage_path 一次性迁移

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 bug-365——存量任务行 storage_path 指向已废弃 `saves/` 相对根（全库唯一受影响行 f7b40b18），1 行 UPDATE 迁移到现行绝对路径惯例 + 轻验证 + 清淤备份删除。

**Architecture:** 纯数据迁移（零代码 diff）→ 秒级文件冒烟 → 台账收尾。

**Tech Stack:** psql / python-docx 冒烟

**设计依据:** [2026-10-05-bug-365-storage-path-migration-design.md](../specs/2026-10-05-bug-365-storage-path-migration-design.md)

---

## 全局上下文（implementer 必读）

- DB 只读/写一律 `MSYS_NO_PATHCONV=1 docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -c "..."`；**禁止容器内 python + pg_manager**（裸 exec 挂池）。
- python-docx 冒烟在 api 容器跑：`MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -u -c "..."`（纯文件操作，不 import pg_manager）。
- **禁碰文件**（严禁卷入提交）：`backend/package/yuxi/agents/buildin/chatbot/prompt.py`、`backend/server/utils/lifespan.py`、`web/src/components/AgentChatComponent.vue`、`web/src/components/SettingsModal.vue`。提交只用明确列出的 `git add <files>`。
- 本项**零代码 diff**：若发现任何 .py/.yml 需要改，停手上报。
- 提交信息：中文 Conventional Commits + `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

### Task 1: 迁移 + 冒烟 + 收尾

- [x] **Step 1: 迁移前三连取证**

```bash
# 病灶值与守卫条件确认（应返回恰好 1 行，saves/ 前缀）
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -c "SELECT id, storage_path FROM domain_factory_tasks WHERE id LIKE 'f7b40b18%' AND storage_path LIKE 'saves/%';"
# 目标文件在位确认（api 容器）
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 ls -la /app/user-data/domain_factory/coal/ | grep c5451b85
# 是否存在第二套 postgres 栈
docker ps --format "{{.Names}}" | grep -i postgres
```

Expected: SQL 恰 1 行 `saves/domain_factory/coal/c5451b85-...docx`；文件在位 ~13.9MB；第二套栈若存在则如实记录（主控裁决是否同修，通常只有 pisuan-localized-postgres-1）。

- [x] **Step 2: 1 行 UPDATE（双守卫）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -c "UPDATE domain_factory_tasks SET storage_path = '/app/user-data/' || substring(storage_path from 7) WHERE id LIKE 'f7b40b18%' AND storage_path LIKE 'saves/%';"
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -t -c "SELECT storage_path FROM domain_factory_tasks WHERE id LIKE 'f7b40b18%';"
```

Expected: `UPDATE 1`；迁移后值为 `/app/user-data/domain_factory/coal/c5451b85-...docx`（`substring(... from 7)` 跳过前 6 字符（`saves/` 为 6 字符，from 7 即从第 7 字符起取））。**非 UPDATE 1 即停手上报。**

- [x] **Step 3: 轻冒烟（秒级）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python -u -c "
from docx import Document
p = '/app/user-data/domain_factory/coal/c5451b85-44b6-4d34-8848-4f8aa56006b3_2新疆伊宁矿区北区总体规划_修编_环境影响报告书_-3.docx'
d = Document(p)
paras = [x.text for x in d.paragraphs if x.text.strip()]
print('opened OK, non-empty paragraphs =', len(paras))
assert len(paras) > 100
"
```

Expected: `opened OK, non-empty paragraphs =` 数百量级（354 段来自此文件），assert 过。（文件名以 Step 1 的 ls 输出为准，若有出入以实际为准并如实记录。）

- [x] **Step 4: 清淤备份删除（用户已拍板 D3）**

```bash
rm -rf /c/workspace/pisuan/.wolf/bug363-stale-coal_mining-backup
git -C /c/workspace/pisuan status --porcelain | grep -i "coal_mining" || echo "no residue"
```

Expected: 目录删除、git status 无残留。

- [x] **Step 5: 台账收尾 + 提交**

- buglog：bug-365 fix 原位更新为实际动作（UPDATE 1 行 + 冒烟结果 + 零代码 diff 声明）；
- changelog：`### pisuan 定制增量（2026-10-05）` 小节追加 `- fix(bug-365): 存量任务 storage_path 一次性迁移（saves/ → /app/user-data，全库唯一受影响行，零代码）`
- 计划本文勾账 + 执行记录两行；`.wolf/memory.md` 追加一行（gitignored 属预期）
- 提交：

```bash
git add docs/develop-guides/changelog.md .wolf/buglog.json docs/superpowers/plans/2026-10-05-w1-bug-365-storage-path-migration.md docs/superpowers/specs/2026-10-05-bug-365-storage-path-migration-design.md
git commit -m "docs: bug-365 收尾——存量 storage_path 迁移落账

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成定义（DoD）

1. UPDATE 1 行留痕 + 冒烟过（段落数 >0）；零代码 diff。
2. 备份目录已删、无残留。
3. 台账三件 + spec/plan 入提交，落 pisuan-custom 顶端（推送由主控评审后执行）。

---

## 执行记录

- 2026-10-05 五步全过、无偏离：Step 1 三连取证全中（SQL 恰 1 行 `saves/domain_factory/coal/c5451b85-...docx`；文件在位 13930396 字节 ≈13.9MB；仅 pisuan-localized-postgres-1 一套栈，无第二套）；Step 2 `UPDATE 1`，迁移后值 `/app/user-data/domain_factory/coal/c5451b85-...docx`；Step 3 冒烟 opened OK、非空段落 423（assert >100 过）；Step 4 备份目录已删、git status 无 coal_mining 残留。零代码 diff。
- spec 已在先前提交 c46b5308 入库，本项提交仅含 changelog + buglog + 本计划三文件。
