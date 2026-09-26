# yuxi→pisuan 全量本地化改名 + 上游同步流程改造 设计文档

- 日期：2026-09-26
- 状态：设计已经用户逐节确认
- 来源：brainstorming 会话（superpowers）

## 1. 背景与问题

用户提问：将前后端代码文件与目录中的 `yuxi` 替换为 `pisuan` 做本地化定制后，下次与 GitHub 上游（`xerrors/Yuxi`）同步差分是否能顺利进行？

直接全量改名会破坏上游 diff 对应关系（路径、导入、变量全变），因此需要一个**把"语义定制"与"机械改名"分离**的同步架构。

## 2. 已确认决策

| 决策点 | 选择 |
|---|---|
| 改名范围 | D：三层全改（品牌层 + 部署运维层 + 代码层全量） |
| 存量环境处理 | A：一次性迁移到位（数据目录 mv、DB 表 RENAME、`.env` 全换 `PISUAN_*`，旧名彻底消失） |
| 实施方案 | 方案 1：机械改名层（确定性脚本生成的独立提交） |
| 补充要求 | 保留当前本地工程（`C:\workspace\pisuan`）零打扰，新拷贝一份到 `C:\workspace\pisuan-localized` 做改造，推送到 GitHub 新分支 |

### yuxi 分布普查结论（设计依据）

- 后端：约 1904 行导入 / 507 文件（🔴 大头，机械重写）
- 前端：约 30 处（🟢，按内容甄别）
- docker-compose：约 69 处 + 数据目录 `docker/volumes/yuxi/`（🟡）
- DB：`SCHEMA_VERSION_TABLE = "yuxi_schema_migrations"` 单点常量（🟢）
- 环境变量：`.env` 中 `YUXI_*` 两个变量（🟢）

## 3. 架构：三分支 + 双目录

### GitHub 分支

| 分支 | 角色 | 命名空间 |
|---|---|---|
| `main` | 纯净镜像 upstream/main（现状不变） | yuxi |
| `pisuan-custom` | 全部语义定制（现状不变，同步流程与今天一字不差） | yuxi |
| `pisuan-localized`（新增） | = pisuan-custom + 1 个机械改名提交（脚本生成，位于分支顶端） | pisuan |

### 本地目录

| 目录 | 用途 |
|---|---|
| `C:\workspace\pisuan` | 现有工程，零打扰，服务继续跑 |
| `C:\workspace\pisuan-localized` | 新克隆，承载 pisuan-localized 分支与改造产物 |

### 核心性质

1. `pisuan-custom` 的同步流程与现在完全一致——改名层不侵入语义层。
2. `pisuan-localized` 是**可丢弃、可重新生成**的衍生物：每次 `pisuan-custom` 同步完成后，重跑改名脚本重建并 force-push。
3. 切换部署是独立决定，本设计附"切换日操作手册"+ 回滚路径，不在本次改造中强制执行。

## 4. 改名脚本与保留清单

### 4.1 脚本

`scripts/apply_pisuan_rename.py`，确定性 + 幂等（跑 N 遍结果一致），产物即分支顶端的"改名提交"。**规则为显式模式表，不做全局盲目 sed**：

| 模式 | 替换 | 范围 |
|---|---|---|
| `backend/package/yuxi/` 目录 | git mv → `backend/package/pisuan/` | 目录 |
| `from yuxi.` / `import yuxi.` / 字符串模块路径（monkeypatch、动态导入） | → `pisuan.` | 全部 Python |
| `YUXI_`（环境变量） | → `PISUAN_` | 代码 getenv、compose、`.env` 模板、docs |
| `yuxi_schema_migrations` | → `pisuan_schema_migrations` | `SCHEMA_VERSION_TABLE` 单点常量 |
| compose 内 `yuxi`（项目/镜像名默认值、数据目录默认值 `docker/volumes/yuxi`） | → `pisuan` | docker-compose.yml |
| 前端 30 处 | 按内容甄别：API 路径类连后端路由一起改；文案类直接改 | web/src |
| `pyproject.toml` 包名 | → pisuan | `uv.lock` 不 sed，重新生成 |

### 4.2 保留清单（脚本跳过，产出"残余报告"供人工核对）

- 文档/注释中指**上游项目本名**的 `Yuxi`（`xerrors/Yuxi`、"上游 Yuxi 项目"）——专有名词，非本方标识符
- 上游 LICENSE / 版权声明
- 切换手册中描述历史迁移的旧路径指称（如"从 `docker/volumes/yuxi` 迁移而来"）

### 4.3 纪律

改名提交**永不手工编辑**。发现漏改 = 修脚本规则 → 重新生成提交（幂等保证可无限重来）。

## 5. 同步流程改造

`scripts/sync-upstream.ps1` / `.sh` 增量改造，前两步与现状完全一致：

```
1. main 快进 upstream/main
2. pisuan-custom rebase + 推送              ← 与今天一字不差
3. 重建 pisuan-localized：
   git branch -f pisuan-localized pisuan-custom
   python scripts/apply_pisuan_rename.py
   git commit "chore: 机械改名层（脚本生成）" + force-push
4. 三段测试（在 localized 目录的容器上）
```

**红线纪律**：`pisuan-localized` 上禁止直接提交语义改动——所有语义改动一律进 `pisuan-custom`，否则下次重建即丢失。此纪律写入 `docs/develop-guides/upstream-sync-guide.md`。

## 6. 切换日操作手册（一次性，时机另行拍板）

1. 停旧栈（`C:\workspace\pisuan` 下 compose down）
2. 备份：数据目录整体 copy + pg dump
3. 迁移：
   - `docker/volumes/yuxi` → `docker/volumes/pisuan`
   - psql：`ALTER TABLE yuxi_schema_migrations RENAME TO pisuan_schema_migrations;`
   - `.env` 全部 `YUXI_*` → `PISUAN_*`
4. 在 `C:\workspace\pisuan-localized` 下 `docker compose up -d`（migrator 以改名后的表名读取 version 记录，迁移后即到位）
5. 验证：三段测试 + 探针（api/web/红线页脚）
6. **回滚路径**：compose down → 恢复备份目录与表名 → 旧目录原样拉起

## 7. 验收标准

1. 脚本输出的残余报告与保留清单逐项核对通过——无意外 `yuxi` 残留
2. 三段测试全绿（unit / integration / e2e）
3. **演练同步**：构造模拟"上游新提交改了导入行"的 scratch 分支，跑一遍完整同步流程，`pisuan-localized` 自动重建且零手工冲突——用事实证明改名后差分同步可行
4. （切换日后）服务在迁移后的存量数据上正常启动，探针全绿

## 8. 风险与边界

| 风险 | 缓解 |
|---|---|
| 正则误伤（`yuxi` 出现在不可改上下文） | 显式模式表 + 文件范围限定 + 残余报告人工核对 |
| 新建包名 `pisuan` 与既有 `pisuan` 品牌文案冲突 | 目录 mv 仅为 `backend/package/` 层级，前端文案不在脚本范围 |
| localized 分支被误改语义 | 红线纪律写入同步指南；分支可随时从 pisuan-custom 重建，损失为零 |
| DB 表改名后旧 migrator 混淆 | 迁移脚本一次性执行；改名后 `SCHEMA_VERSION_TABLE` 常量与新表名一致 |
| 数据目录 mv 后旧容器仍挂载旧路径 | 切换手册第 1 步先停旧栈 |

## 9. 任务 Checklist

- [ ] 新建 `C:\workspace\pisuan-localized` 克隆，创建 `pisuan-localized` 分支并推送
- [ ] 编写 `scripts/apply_pisuan_rename.py`（模式表 + 保留清单 + 幂等 + 残余报告）
- [ ] 执行脚本生成改名提交，残余报告核对
- [ ] localized 目录三段测试全绿
- [ ] 演练同步（scratch 分支模拟上游提交 → 全流程零手工冲突）
- [ ] `sync-upstream.ps1/.sh` 增加第 3 步（重建 localized）
- [ ] 更新 `docs/develop-guides/upstream-sync-guide.md`（三分支结构 + 红线纪律）
- [ ] （独立决定）切换日：按第 6 节手册执行迁移
