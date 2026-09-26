# 上游代码同步与本地化扩展实施方案

## 一、三分支架构与双目录

```
upstream/main (xerrors/Yuxi)
    │
    │ git fetch upstream main:main   （强制 ff，非 ff 自动拒绝）
    ▼
main ────────────→ 纯净镜像 upstream/main，禁止直接提交任何定制代码
    │
    │ git rebase --autostash main
    ▼
pisuan-custom ───→ 领域知识库工厂 + 本地化定制（yuxi 命名空间），语义改动的唯一入口 <!-- rename-keep -->
    │
    │ scripts/apply_pisuan_rename.py --apply（同步脚本第 5 步自动执行）
    ▼
pisuan-localized ─→ pisuan-custom 顶端 + 1 个脚本生成的机械改名提交（yuxi→pisuan） <!-- rename-keep -->
```

| 分支 | 用途 | 规则 |
|------|------|------|
| `main` | 上游代码镜像 | **禁止直接提交**，仅由同步脚本经 `git fetch upstream main:main` 快进更新 |
| `pisuan-custom` | 语义定制分支 | 所有定制代码在此分支（yuxi 命名空间），由脚本 rebase 到 main | <!-- rename-keep -->
| `pisuan-localized` | 机械改名层 | = pisuan-custom 顶端 + 脚本生成提交；**可丢弃可重建**；推送到 github `yogyoho/pisuan` |

**双目录**：

| 目录 | 定位 |
|------|------|
| `C:\workspace\pisuan` | 日常工程仓（main / pisuan-custom 在此） |
| `C:\workspace\pisuan-localized` | 改名衍生物克隆（pisuan-localized 在此），**勿直接开发** |

**红线纪律**：`pisuan-localized` 上禁止直接语义改动——一切语义改动进 `pisuan-custom`，否则下次重建即丢失。改名层由脚本从语义树确定性再生（相同输入永远产出字节级一致输出），分支损坏时 `reset --hard origin/pisuan-custom` 后重跑脚本即可，损失为零。

## 二、同步步骤

### 运行前置契约

- **必须从 `pisuan-custom` 分支运行**（两脚本均有前置守卫，其他分支/detached HEAD 明确拒绝并显示当前分支）；
- **容忍 `.wolf` 等跟踪文件的常态未提交改动**：main 更新用 `git fetch upstream main:main`（强制 ff、fail-closed、不触碰工作树），rebase 用 `--autostash`（脏改动自动收放）——无需手工 stash；
- 上游无新提交时全链路为幂等 no-op（main 不动、rebase up-to-date、推送 Everything up-to-date、localized 重建提交跳过或仅差量）。

### ⚠️ 上游历史重写的恢复流程（2026-08-20 实战记录）

上游 force-push 重写过 main 历史（旧 merge commit 被拍平，SHA 全变但内容大部分 patch 等价）。症状与处理：

```bash
# 症状：git fetch upstream 显示 (forced update)；main 与 upstream/main 显示
# behind 2501 / ahead 2269，共同祖先停在 2024-07-14。
# 真实差异用 --cherry-pick 过滤 SHA 噪声：
git rev-list --left-right --cherry-pick --count upstream/main...main

# 1. main 硬重置（纯镜像不能 --ff-only）：
git checkout main && git reset --hard upstream/main

# 2. rebase 定制分支（先开 rerere，.wolf 元数据冲突一律 checkout --ours）：
git config rerere.enabled true
git checkout pisuan-custom && git rebase main
```

已知坑（详见 .wolf/buglog.json）：

1. **上游 CLAUDE.md 是符号链接**（指向 AGENTS.md）：与 pisuan 普通文件构成 merge-ort 类型冲突，自动改名文件含提交主题冒号，Windows 非法路径导致 pick 直接失败。需先把 HEAD 的 CLAUDE.md 恢复为普通文件（`git update-index --cacheinfo 100644,<blob>,CLAUDE.md`，Windows 下 `git add` 不改 mode），再 continue。
2. **v0.7.2 新增 .env 必填密钥**：`JWT_SECRET_KEY` / `API_KEY_DERIVATION_SECRET` / `SANDBOX_PROVISIONER_TOKEN` / `YUXI_INSTANCE_ID`（跑 `bash scripts/init.sh` 生成），缺失时启动组件硬失败。改 .env 后必须 `docker compose up -d --force-recreate`（restart 不重读 env）。
3. **合并 pyproject 后必须 `cd backend && uv lock`**：否则 Docker 构建 `uv sync --frozen` 因 manifest 哈希不匹配失败。
4. **pytorch 等大包构建超时**：默认 `UV_HTTP_TIMEOUT=30s` 扛不住 torch（200MB+），docker/api.Dockerfile 已放宽至 600s；uv 的 `--no-cache` 使失败的 RUN 层整体重下，一次构建约 40 分钟，失败重试成本高。
5. **镜像 tag 漂移**：新版 compose 默认 `YUXI_VERSION=0.7.2.dev0`，本地已有镜像是旧 tag；开发环境可在 .env 钉 `YUXI_VERSION=<已有tag>` + `--no-build` 重建容器，镜像重建等镜像源可用后再做（lock 的 wheel URL 若指向失效镜像源需换源重生）。
6. **DB 遗留 lightrag 空库会硬失败**：上游把"使用中但不受支持的 KB 类型"从跳过改为启动失败，需备份后清理（`knowledge_bases_backup_lightrag_20260820`）。
7. **上游可能彻底移除依赖**（v0.7.3 移除 torch、前端移除 lucide-vue-next/sigma/highlight.js）：定制侧对应配置随之失效是正常现象，不要"恢复"；上游新增替代机制（如 @lucide/vue、SKILL.md frontmatter 元数据、presets/ 目录自动发现）时，定制内容必须迁移到新机制而不是固守旧注册点。
8. **rebase 冲突取 `--ours` 前先分清语义**：rebase 中 ours=上游新代码、theirs=定制提交。上游删掉的旧注册结构（如 BUILTIN_SKILLS 列表）取 ours 没问题，但定制**追加内容**（DDL、路由注册、依赖元数据）会随之丢失——rebase 结束后必须按清单校验定制最终态（grep domain_factory DDL、路由注册、writer preset、skill frontmatter），缺的从旧链 `git show <旧链>:<file>` 提取合入。
9. **幽灵引用**：手工合并路由/导出注册时，以旧链**最终态**（`git show 227c8c1d:...`）为准，不要照搬中间定制提交的旧内容（如已废弃的 section_routing，会被 domain_entity_builder 取代），否则引入 ImportError。



### 自动化（推荐）

```bash
# Windows PowerShell
.\scripts\sync-upstream.ps1

# Linux/macOS
bash scripts/sync-upstream.sh

### 定时自动同步（Windows 任务计划）

```powershell
# 注册每日午夜 00:00 自动执行（以管理员身份运行一次即可）
.\scripts\setup-scheduled-sync.ps1

# 查看/管理任务
taskschd.msc → 任务计划程序库 → PisuanAutoSync
```

- 无冲突 → 自动完成，日志写入 `scripts/logs/sync-YYYY-MM-DD.log`
- 有冲突 → 自动中止，日志记录冲突文件清单，等待人工处理
```

### 手动（当脚本报冲突时）

```bash
# 1. 拉取上游并强制 ff 更新 main（不触碰工作树）
git fetch upstream
git fetch upstream main:main

# 2. rebase 定制分支（autostash 自动收放脏改动）
git checkout pisuan-custom
git rebase --autostash main

# 3. 如有冲突，按下方规则解决后继续
git add -A
git rebase --continue

# 若冲突复杂想放弃本次同步：
# git rebase --abort
```

## 三、pisuan-localized 重建与残余口径

同步脚本第 5 步自动重建 `pisuan-localized`（失败降级为警告，不阻断主流程）：

```
fetch origin → switch pisuan-localized → reset --hard origin/pisuan-custom
  → python scripts/apply_pisuan_rename.py --apply --root <localized>
  → uv lock（backend 与 packages/pisuan-cli 两处）
  → 无变化跳过提交，否则提交后 push github pisuan-localized --force-with-lease
```

### 残余报告口径（2026-09-26 实测）

改名后残余 yuxi 位置 **227 = 199 保护词行 + 16 文档自描述行 + 12 项 allowlist**： <!-- rename-keep -->

- **199 保护词行**：含 `xerrors` / `上游` / `upstream` 关键词，属"对上游项目的指称"，裸词规则刻意不动（结构化标识符仍会改写）；
- **16 文档自描述行**：本指南 / CLAUDE.md / changelog 中以旧名为内容自描述改名的行（切换日指令、架构与口径自述），行内嵌 `<!-- rename-keep -->` 哨兵，整行逐字存活——行级保护，同文件真实路径照常改写；
- **12 项 allowlist**：无保护词且任何规则均不命中的存活 token；与文档自描述行合计共 7 类：

| 类别 | 处数 | 位置 | 保留原因 |
|------|------|------|----------|
| 文档自描述行哨兵 | 16 | 本指南 / `CLAUDE.md` / `changelog.md` | 行内嵌 `<!-- rename-keep -->` 整行逐字存活（改名指令/口径自述）；行级保护，不伤同文件真实路径 |
| 种子账号默认口令字面量 | 2 | `backend/scripts/seed_initial_users.py` | 口令字符串值，改名即无法登录（仅限开发环境，见 六） |
| 测试夹具请求 ID | 1 | `backend/test/integration/services/test_live_api_cleanup_run_rows.py` | `YUXI-TEST-*` 历史数据对账取值 | <!-- rename-keep -->
| 文档站部署 base 路径 | 3 | `docs/.vitepress/config.mts` | `/Yuxi/` 为 GitHub Pages 部署路径，改动即断链 | <!-- rename-keep -->
| 上游克隆指引 | 1 | `docs/develop-guides/contributing.md` | 指引用户克隆上游仓库 |
| 平行 worktree 环境命名 | 4 | `docs/develop-guides/parallel-worktree-environments.md` | 既有环境目录名，非本仓标识符 |
| 运营渠道参数 | 1 | `web/src/components/model-management/ModelProviderManagePanel.vue` | `promo=YUXI` 为渠道方定义的取值 | <!-- rename-keep -->

**核对方法论**：新增受保护行（保护词行或哨兵行随文档演进增长）= 预期；未知 / allowlist 外新增残余 = 改名脚本漏改，处理纪律是修脚本规则 → 重新生成本地化层，**禁止在 pisuan-localized 手工修补**。allowlist 与哨兵行均由 `scripts/test_apply_pisuan_rename.py` 机检（`ResidueAllowlistTest` / `ProtectedDocLinesTest`，防规则误伤与清单脱节双向漂移）。

### 已知保留：数据库库名

`POSTGRES_DB=yuxi_know` 不属 `YUXI_*` 变量交换范围（库名不是前缀命名空间），本次改造未含库名迁移，记为**已知保留**。如需彻底更名须 `ALTER DATABASE` + 停机窗口，属可选独立决策。 <!-- rename-keep -->

## 四、切换日操作手册（一次性，时机另行拍板）

1. 停旧栈（`C:\workspace\pisuan` 下 `docker compose down`）
2. 备份：数据目录整体 copy + pg dump
3. 迁移：
   - `docker/volumes/yuxi` → `docker/volumes/pisuan` <!-- rename-keep -->
   - psql：`ALTER TABLE yuxi_schema_migrations RENAME TO pisuan_schema_migrations;` <!-- rename-keep -->
   - `.env` 全部 `YUXI_*` → `PISUAN_*` <!-- rename-keep -->
4. 在 `C:\workspace\pisuan-localized` 下 `docker compose up -d`（migrator 以改名后的表名读取 version 记录，迁移后即到位）
5. 验证：三段测试 + 探针（见 五、六）
6. **回滚路径**：compose down → 恢复备份目录与表名 → 旧目录原样拉起

**实测缺口（T4 启动演练坐实，切换日必须补齐）：**

- **Neo4j 章节模板种子迁移**：启动链只覆盖 Postgres，不播 Neo4j——不迁移则图谱章节模板功能为空，unit 4 个种子依赖用例必失败。切换日需从旧栈 Neo4j 导出章节模板种子导入新栈。
- **库名保留**：`POSTGRES_DB=yuxi_know` 不随 `.env` 置换自动更名（见 三）。 <!-- rename-keep -->
- **探针口径**：`/health` 端点不存在（bug-273），以 `import pisuan` 路径检查 + `GET /api/system/ready` 全量 JSON + web 首页 200 为准。
- **栈运行期间热写 pyc**：改名树运行时容器向 `backend/package/pisuan/**/__pycache__/` 热写 ignored 字节码，会物理占据重建目标路径（bug-272）。栈 down 后可选 scoped 清理：`git -C C:/workspace/pisuan-localized clean -fdX backend/package/pisuan`——**只许此等路径级清理，严禁 repo 级 `git clean -fdX`**（会抹掉 `.env` 与 bind-mount 部署数据）。改名脚本自身已内置"占据即 scoped 清理"逻辑，此步仅为运行时整洁。

## 五、测试基线口径（2026-09-26 实测）

两种栈状态下跑出的数字**都合法**，差异根因如下：

| 范围 | 全新栈（localized） | 旧栈 | 说明 |
|------|------|------|------|
| unit | 2526 passed + 4 failed | 2530 passed | 4 failed 均为 Neo4j 章节模板种子依赖（全新栈未播种子，见 四），非代码缺陷 |
| integration | 141 passed / 205 skipped / 3 errors | — | 3 errors 为上游存量 FK 问题（`test_project_api.py`），非本次改动引入 |
| e2e | 12 skipped（无凭据） | — | **skipped ≠ 通过**；凭据版前置 `E2E_USERNAME`/`E2E_PASSWORD` + 种子账号 |

e2e 已知限制：确定性回放路径依赖模型端点从容器内可达；当前 `OPENAI_API_BASE` 为宿主机 LAN 地址，容器内不可达，凭据版 12 failed 属环境限制。回放服务器位于 `backend/test/support/openai_replay_server.py`，跨容器接线未打通，如实记录。

## 六、品牌归属与账号安全

- **campaign 归属（Minor-A）**：注册渠道链接 `fluxionai.space/...?campaign=pisuan` 的 `campaign=pisuan` 为 pisuan 侧投放归属参数；`promo=YUXI` 为渠道方定义的取值（在 12 项 allowlist 内，勿改）。统计口径按 `campaign=pisuan` 归属。 <!-- rename-keep -->
- **种子账号口令（Minor-B）**：`seed_initial_users.py` 的 `DEFAULT_USER_PASSWORD = "yuxi123456"` 仅供开发环境种子；任何对外环境必须轮换。该字面量在改名 allowlist 内——若轮换口令须同步更新 `scripts/test_apply_pisuan_rename.py` 的 `ResidueAllowlistTest` fixtures。 <!-- rename-keep -->

## 七、不可覆盖的本地定制清单

以下文件和内容在同步冲突时必须优先保留，**禁止使用 upstream 版本直接覆盖**。

### 7.1 整体替换类（禁止覆盖）

这些文件是 pisuan 完全重写的，冲突时直接使用 `pisuan-custom` 版本：

| 文件 | 内容 | 说明 |
|------|------|------|
| `web/src/views/HomeView.vue` | Landing 首页 | 全新移植，不可覆盖 |
| `web/src/views/LoginView.vue` | 登录页 | 全新移植，不可覆盖 |

### 7.2 局部定制类（谨慎合并）

这些文件同时包含上游通用代码和 pisuan 定制，冲突时需手动合并：

| 文件 | 定制内容 | 合并策略 |
|------|----------|----------|
| `web/src/assets/css/base.css` | 蓝色主题色变量 (`--ant-primary-color: #1890ff` 等) | 保留上游新增变量 + 保留我们的主题色 |
| `web/src/assets/css/base.dark.css` | 暗色模式主题色 | 同 base.css |
| `web/src/layouts/AppLayout.vue` | ① 领域工厂导航项 (`Layers` 图标) ② 任务中心独立位置 ③ UserInfoComponent 简化用法 ④ GitHub 已移除 | 保留我们的导航结构和组件用法，上游新增的 ConversationNavSection 等特性可以合并 |
| `backend/package/yuxi/config/static/info.template.yaml` | 页脚版权: `"© 北京华宇工程有限公司 2026 v1.6.0"` | 始终使用我们的版本 |

### 7.3 追加合并类（双方保留）

| 文件 | 定制内容 | 合并策略 |
|------|----------|----------|
| `backend/package/yuxi/storage/postgres/manager.py` | domain_factory 系列 DDL（建表/索引/种子数据） | 保留上游新增的 DDL + 保留我们的 domain_factory DDL |
| `backend/server/routers/__init__.py` | domain_factory / entity_type / section_routing 路由注册 | 保留上游新增路由 + 保留我们的路由注册 |
| `docs/develop-guides/roadmap.md` | 领域知识工厂相关条目 | 保留上游更新 + 末尾追加我们的条目 |

### 7.4 上游优先类（接受覆盖）

| 文件 | 原因 |
|------|------|
| `README.md` | 上游官方 README，本地说明不放这里 |
| `docs/intro/model-config.md` | 上游产品文档 |
| `docs/.vitepress/config.mts` | 上游文档配置 |

### 7.5 纯新增类（无冲突风险）

以下文件和目录是 pisuan 独立新增的，不会与上游产生冲突：

**后端新增：**
```
backend/package/yuxi/repositories/domain_factory_repository.py
backend/package/yuxi/services/domain_factory_service.py
backend/package/yuxi/services/entity_meta_service.py
backend/package/yuxi/services/graph_builder.py
backend/package/yuxi/services/template_generator.py
backend/package/yuxi/services/template_library.py
backend/package/yuxi/services/template_matcher.py
backend/package/yuxi/storage/postgres/models_domain_factory.py
backend/package/yuxi/config/static/prompt_templates.yaml
backend/package/yuxi/agents/skills/buildin/slot-filler/
backend/package/yuxi/agents/skills/buildin/template-recommender/
backend/server/routers/domain_factory_router.py
backend/server/routers/entity_type_router.py
backend/server/routers/section_routing_router.py
backend/server/coal_eia_entity_types.json
backend/server/standard_code_mapping_list.json

backend/scripts/import_domain_factory_data.sql
backend/scripts/migrate_domain_factory.sql
backend/templates/coal_mining/
```

**前端新增：**
```
web/src/views/DomainFactoryView.vue
web/src/views/PromptConfigView.vue
web/src/views/SectionRoutingView.vue

web/src/components/domain-factory/
web/src/apis/domain_factory_api.js
web/src/apis/entity_type_api.js
web/src/assets/css/main.less
```

## 八、按文件类型的合并策略速查

### 前端文件

```
.vue     → 一般需手动合并，优先保留我们的页面和导航结构
.css     → 保留我们的主题变量，合并上游新增变量
.less    → 同 .css
.js      → api/ 下的新增文件无冲突；stores/ 和 router/ 需手动检查
```

### 后端文件

```
routers/__init__.py  → 追加合并：上游新路由 + 我们的路由
manager.py           → 追加合并：上游新 DDL + 我们的 DDL, entities=[]
services/*.py        → 纯新增文件，一般无冲突
config/static/*.yaml → 检查双发改动，品牌定制类优先保留我们的
```

### 文档文件

```
README.md            → 上游优先
docs/intro/*.md      → 上游优先
docs/develop-guides/ → 上游优先，允许末尾追加我们的条目
docs/vibe/*.md       → 纯我们的文档，无冲突
```

## 九、同步后验证

每次同步完成后必须验证以下内容：

- [ ] Docker 容器正常启动：`docker compose up -d --build`
- [ ] 首页 `/` 显示 pisuan 定制 Landing 页
- [ ] 登录页 `/login` 显示 pisuan 定制登录页
- [ ] 主题色为蓝色系（非上游默认色）
- [ ] 侧边栏有"领域工厂"导航入口
- [ ] 页脚显示"北京华宇工程有限公司"
- [ ] 领域工厂各页面正常加载
- [ ] localized 重建成功（或明确降级原因）：三 tip 汇总行齐全，残余口径 227 = 199 保护词行 + 16 文档自描述行 + 12 项 allowlist，无漂移
- [ ] `git ls-remote` 前后对比：pisuan-custom 与 pisuan-localized 新 tip 已上 GitHub
