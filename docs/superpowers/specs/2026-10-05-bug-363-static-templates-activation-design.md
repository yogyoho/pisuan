# bug-363 修复设计：静态模板容器激活 + 部署一致性清查

> 状态：已拍板（2026-10-05，用户裁决 D1/D2/D3 均按推荐）
> 前序：[bug-359 设计](2026-10-05-bug-359-domain-unify-match-rule-design.md)（W1 首项，已收口）；本项为 W1 第二项

## 1. 背景与根因

`TemplateLibrary.TEMPLATES_DIR` 解析为 `/app/templates`，但容器栈双缺口：`docker/api.Dockerfile` 无 `COPY backend/templates`（仅 pyproject/uv.lock/package/server/entrypoint）；`docker-compose.yml` 的 api(:56) 与 worker(:122) 服务均只挂 server/package/state。→ 容器内 `/app/templates` 不存在，静态模板 30 条**从未**参与 ETL 匹配与写手 `get_templates`。开发机直跑正常，属「开发机存在、运行栈缺席」的部署断裂。

关键约束：工厂 ETL 经 ARQ worker 执行（domain_factory_service.py 4 处 `tasker.enqueue`）→ **worker 与 api 都需要该资产**。`routing_config.json` 已确认无运行时消费方（仅加载器跳过），无需部署。

## 2. 拍板决策（2026-10-05）

- **D1 范围**：镜像 COPY + compose 双服务挂载**都做**——dev 栈靠 mount 即时生效（无需重建镜像），非 dev 部署靠镜像层补缺；只改其一留一半断裂。回退：摘 compose 挂载行即回退。
- **D2 行为评估 = 观察窗验收**：静态模板激活是行为变更（ETL 命中构成、写手 source 分布、D3 遮蔽效应），用三层验收采集证据，数据直接喂 O6 裁决（模板线停机/保留）。
- **D3 清查捆绑但不修复**：本项顺手扫 `/app` 相对路径资产的同类断裂，产出立案清单；修复另行立项。

## 3. 修复面

| # | 落点 | 改动 |
|---|------|------|
| 1 | `docker/api.Dockerfile:61` 附近 | `COPY backend/templates /app/templates` |
| 2 | `docker-compose.yml` api 服务 volumes | `- ./backend/templates:/app/templates:ro` |
| 3 | `docker-compose.yml` worker 服务 volumes | 同上 |
| 4 | 无代码改动 | loader 已按 `/app/templates` 解析（template_library.py:17） |

执行环境事实：运行栈 compose 项目目录 = `C:\workspace\pisuan-localized`（容器 pisuan-localized-api-1 / pisuan-localized-worker-1）；改动经 `scripts/sync-dev.ps1` 传播到 localized 树，随后须 `docker compose up -d api worker` **重建容器**（挂载变更 restart 无效）。

## 4. 验收标准

1. **即时激活**：挂载生效（docker inspect 可见）；冒烟 `templates total = 30 静态 + 学习注入数`，静态样例正则命中（如「7.1 矿区水资源承载力分析」类标题），学习模板自匹配仍 >0；unit 全量 2681/0/61 不回归。
2. **真实 ETL 观测**：激活后跑一次真实 ETL（重解析既有已提交任务，管理员凭据读 .env；若模型端点容器不可达，观察窗挂起为自然流量事件，写明判定标准），记录段落 `template_match` 的 static/learned 构成对比。
3. **写手侧观测**：`domain_factory_tool_usage` 激活后 source 分布（当前基线 total=6 全为 graph 冒烟记录）。
4. **清查清单**：/app 相对路径资产断裂扫描产出立案（预期候选：prompt refs、skill 资产、seed 文件）。
5. 回归口径沿用 bug-360 裁决：`pytest /app/test/unit`。

## 5. Out of scope

清查发现的断裂修复、W2 模板线深度重构、静态/学习模板优先级调整（D3 遮蔽语义维持 bug-359 拍板）。
