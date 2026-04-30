# 上游代码同步与本地化扩展实施方案

## 一、双分支策略

```
upstream/main (xerrors/Yuxi)
    │
    │ git fetch upstream && git merge upstream/main
    ▼
main ────────────→ 纯净跟踪 upstream/main，禁止直接提交任何定制代码
    │
    │ git checkout pisuan-custom && git rebase main
    ▼
pisuan-custom ───→ 领域知识库工厂 + 本地化定制，基于最新 main 之上
```

| 分支 | 用途 | 规则 |
|------|------|------|
| `main` | 上游代码镜像 | **禁止直接提交**，仅通过 `git merge upstream/main` 更新 |
| `pisuan-custom` | 本地定制分支 | 所有定制代码在此分支，定期 rebase 到 main |

## 二、同步步骤

### 自动化（推荐）

```bash
# Windows PowerShell
.\scripts\sync-upstream.ps1

# Linux/macOS
bash scripts/sync-upstream.sh
```

### 手动（当脚本报冲突时）

```bash
# 1. 拉取上游
git fetch upstream

# 2. 更新 main
git checkout main
git merge upstream/main --ff-only

# 3. Rebase 定制分支
git checkout pisuan-custom
git rebase main

# 4. 如有冲突，按下方规则解决后继续
git add -A
git rebase --continue

# 若冲突复杂想放弃本次同步：
# git rebase --abort
```

## 三、不可覆盖的本地定制清单

以下文件和内容在同步冲突时必须优先保留，**禁止使用 upstream 版本直接覆盖**。

### 3.1 整体替换类（禁止覆盖）

这些文件是 pisuan 完全重写的，冲突时直接使用 `pisuan-custom` 版本：

| 文件 | 内容 | 说明 |
|------|------|------|
| `web/src/views/HomeView.vue` | Landing 首页 | 全新移植，不可覆盖 |
| `web/src/views/LoginView.vue` | 登录页 | 全新移植，不可覆盖 |

### 3.2 局部定制类（谨慎合并）

这些文件同时包含上游通用代码和 pisuan 定制，冲突时需手动合并：

| 文件 | 定制内容 | 合并策略 |
|------|----------|----------|
| `web/src/assets/css/base.css` | 蓝色主题色变量 (`--ant-primary-color: #1890ff` 等) | 保留上游新增变量 + 保留我们的主题色 |
| `web/src/assets/css/base.dark.css` | 暗色模式主题色 | 同 base.css |
| `web/src/layouts/AppLayout.vue` | ① 领域工厂导航项 (`Layers` 图标) ② 任务中心独立位置 ③ UserInfoComponent 简化用法 ④ GitHub 已移除 | 保留我们的导航结构和组件用法，上游新增的 ConversationNavSection 等特性可以合并 |
| `backend/package/yuxi/config/static/info.template.yaml` | 页脚版权: `"© 北京华宇工程有限公司 2026 v1.6.0"` | 始终使用我们的版本 |

### 3.3 追加合并类（双方保留）

| 文件 | 定制内容 | 合并策略 |
|------|----------|----------|
| `backend/package/yuxi/storage/postgres/manager.py` | domain_factory 系列 DDL（建表/索引/种子数据） | 保留上游新增的 DDL + 保留我们的 domain_factory DDL |
| `backend/server/routers/__init__.py` | domain_factory / entity_type / section_routing 路由注册 | 保留上游新增路由 + 保留我们的路由注册 |
| `docs/develop-guides/roadmap.md` | 领域知识工厂相关条目 | 保留上游更新 + 末尾追加我们的条目 |

### 3.4 上游优先类（接受覆盖）

| 文件 | 原因 |
|------|------|
| `README.md` | 上游官方 README，本地说明不放这里 |
| `docs/intro/model-config.md` | 上游产品文档 |
| `docs/.vitepress/config.mts` | 上游文档配置 |

### 3.5 纯新增类（无冲突风险）

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
backend/server/standard_code_skills.json
backend/scripts/import_domain_factory_data.sql
backend/scripts/migrate_domain_factory.sql
backend/templates/coal_mining/
```

**前端新增：**
```
web/src/views/DomainFactoryView.vue
web/src/views/PromptConfigView.vue
web/src/views/SectionRoutingView.vue
web/src/views/StandardCodeView.vue
web/src/components/domain-factory/
web/src/apis/domain_factory_api.js
web/src/apis/entity_type_api.js
web/src/assets/css/main.less
```

## 四、按文件类型的合并策略速查

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

## 五、同步后验证

每次同步完成后必须验证以下内容：

- [ ] Docker 容器正常启动：`docker compose up -d --build`
- [ ] 首页 `/` 显示 pisuan 定制 Landing 页
- [ ] 登录页 `/login` 显示 pisuan 定制登录页
- [ ] 主题色为蓝色系（非上游默认色）
- [ ] 侧边栏有"领域工厂"导航入口
- [ ] 页脚显示"北京华宇工程有限公司"
- [ ] 领域工厂各页面正常加载
