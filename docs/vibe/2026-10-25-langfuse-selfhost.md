# Langfuse 自托管部署（Docker）

- 日期：2026-10-25
- 需求：为本系统部署自托管 Langfuse，用于监控 agent 任务执行过程（trace 模型/工具调用、耗时、错误、用户反馈）。
- 前提调研：系统已原生支持 Langfuse 集成（见 `docs/advanced/langfuse-integration.md`），代码链路无需改动；仅缺可用的 Langfuse 服务端与运行栈密钥。

## 部署决策

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 部署形态 | 独立 compose 文件 `docker-compose.langfuse.yml`（项目 `name: langfuse`） | 不改上游 `docker-compose.yml`，三分支同步零冲突；生命周期独立（`down -v` 一键销毁） |
| 栈组成 | langfuse-web:4 + langfuse-worker:4 + postgres:17 + clickhouse:25.12 + redis:7 + minio（Langfuse v3+ 官方架构） | 与本系统容器内已装的 Python SDK `langfuse 4.14.5` 配套 |
| 端口 | 仅 web 发 `3100:3000`；基础设施（pg/ck/redis/minio）一律不发布宿主端口 | 本机 5432/6379/9000/9001/9091 已被 localized 主栈占用 |
| 统一 origin | `http://host.docker.internal:3100`（NEXTAUTH_URL 与 LANGFUSE_BASE_URL 同值） | 宿主已可解析 host.docker.internal（实测 ping → 192.168.2.38）；容器 SDK 上报、浏览器控制台、调试面板 trace 跳转三方同源，登录会话 cookie 不按 host 分裂 |
| 初始化 | `LANGFUSE_INIT_*` 首启自动创建管理员 `langfuse-admin@pisuan.local`、组织/项目 `pisuan`、预生成 API Key | 免手工 UI 注册，key 可预先写入运行栈 `.env` |
| 密钥管理 | 全部经 `${VAR}` 引用仓库根 `.env`（gitignored） | 跟踪文件无密钥 |
| 镜像获取 | `docker.m.daocloud.io` 前缀拉取后重打官方 tag | Docker Hub 直连超时；不动 Docker Desktop 全局配置 |

## 变更清单

- 新增 `docker-compose.langfuse.yml`（独立观测栈，6 服务 + 4 数据卷）
- `.env`（pisuan 与 pisuan-localized 两份）追加 `LANGFUSE_*` 客户端键与 `LANGFUSE_STACK_*` 栈密钥
- localized 运行栈重建 `api`/`worker` 使密钥生效

## 验收标准 / Checklist

- [x] compose 配置校验通过（`docker compose config --quiet`）
- [x] 6 个容器全部 running，langfuse-web 健康检查通过（Langfuse **4.70.0**）
- [x] `GET http://host.docker.internal:3100/api/public/health` 返回 200（宿主 + localized api 容器内双向可达）
- [x] `LANGFUSE_INIT_*` 生效：管理员/组织/项目/预置 API Key 全部落库
- [x] localized 栈 `is_langfuse_enabled()` 在容器内返回 True（包名经改名层为 `pisuan.services.langfuse_service`）
- [x] 端到端：经 yuxi 完整代码路径（`build_run_context` → CallbackHandler → flush）写入 trace，ClickHouse `events_full` 可查；`submit_user_feedback_score` 返回 True
- [ ] 真实 agent 对话产生 trace（用户后续验证：对话后在 Langfuse 控制台按 session 筛选）

## 实际部署中的差异与坑（记录给后来者）

1. **v4 环境变量对齐**：不能凭记忆/摘录转写官方 compose。v4 有大量改名（`CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000`、Redis 用 `REDIS_HOST/PORT/AUTH`、媒体系列 `LANGFUSE_S3_MEDIA_UPLOAD_*`），且 `NEXTAUTH_SECRET` 是 web 专属变量。权威底本存于 `.wolf/langfuse-deploy/official-ref.yml`。
2. **`LANGFUSE_INIT_*` 必须显式给 `LANGFUSE_INIT_ORG_ID`**（v4.70 行为），否则全部 init 变量被静默忽略。
3. **v4 `events_only` 模式**：OTLP（`/api/public/otel/v1/traces`）写入新表 `events_core`/`events_full`，旧 `/api/public/ingestion` 的 `trace-create` 被拒；**查数据查 `events_full`，不是 `traces`**。旧 SDK 才需要 `LANGFUSE_MIGRATION_V4_WRITE_MODE=dual` 桥接，本系统 SDK 4.14.5 原生走 OTLP 无需 dual。
4. **兼容性验证结论**：SDK 4.14.5 `CallbackHandler` 与 v4 服务器完全兼容；`create_trace_id(seed)` 的确定性 ID 与 OTLP trace_id 一致（yuxi 调试面板跳转链路无恙）；`get_trace_url` 需关键字参数（yuxi 调用方式正确）。
5. **Docker Hub 直连不通**：用 `docker.m.daocloud.io` / `docker.1panel.live` 前缀拉取后重打官方 tag；`cgr.dev`（chainguard）可直连。
6. **宿主与容器统一 origin**：Windows 宿主可解析 `host.docker.internal`（Docker Desktop 写入 hosts 文件），实现浏览器/容器同源，cookie 不分裂。
7. minio chainguard 镜像内置的 `local` alias 凭据陈旧（`mc ls local/` Access Denied 是红鲱鱼），验证用 `$MINIO_ROOT_USER/$MINIO_ROOT_PASSWORD` 重设 alias。
8. **yuxi 集成入口与本次部署无关的既有事实**：trace_id 在模型执行前固化进 `agent_run` 表；超管调试面板经 `GET /agents/runs/{run_id}/langfuse` 跳转。

## 回滚

```bash
docker compose -f docker-compose.langfuse.yml down -v   # 销毁观测栈及数据
# 还原两份 .env 中新增的 LANGFUSE_* / LANGFUSE_STACK_* 段落
```
