# 并行 worktree 环境

## 推荐方式

| 代码目录 | 运行环境 | 数据目录 |
| --- | --- | --- |
| `Pisuan` | 使用现有 `pisuan` 环境和默认端口 | `./docker/volumes` |
| 其他需要同时运行的 worktree | 每个 worktree 使用独立槽位 | `../.pisuan/slots/<槽位名>` |
| `Yuxi-prod` | 独立生产环境，不参与开发 | 生产专用目录 |

不运行服务的 worktree 不需要槽位；兼容分支也可以在旧服务停止后复用已有槽位。只有并行运行或 Schema 不兼容时才创建新槽位。

只运行 `Pisuan` 时无需增加配置，继续使用：

```bash
docker compose up -d
```

Compose 会按 project 自动隔离容器、网络、命名 volume 和本地镜像。其他 worktree 只需额外隔离数据目录和宿主端口。

## 创建分支环境

创建 worktree，并复用现有开发 `.env` 中的 API Key：

```bash
git worktree add ../Yuxi-feature-a -b feat/example upstream/main
cd ../Yuxi-feature-a
cp ../Yuxi/.env .env
chmod 600 .env
```

不要复制 `Yuxi-prod` 的 `.env`。

在新 worktree 的 `.env` 中添加以下配置；变量已存在时直接修改，不要重复添加：

```dotenv
COMPOSE_PROJECT_NAME=pisuan-dev-a
PISUAN_STATE_DIR=../.pisuan/slots/dev-a

PISUAN_API_PORT=25050
PISUAN_WEB_PORT=25173
PISUAN_CORS_ORIGINS=http://localhost:25173,http://127.0.0.1:25173
PISUAN_SANDBOX_PORT=28002
PISUAN_POSTGRES_PORT=25432
PISUAN_REDIS_PORT=26379
PISUAN_MINIO_API_PORT=29000
PISUAN_MINIO_CONSOLE_PORT=29001
PISUAN_MILVUS_PORT=29530
PISUAN_MILVUS_HEALTH_PORT=29091
PISUAN_NEO4J_HTTP_PORT=27474
PISUAN_NEO4J_BOLT_PORT=27687
```

使用 `all` profile 时，再设置 `PISUAN_MINERU_PORT` 和 `PISUAN_PADDLEX_PORT`。

启动：

```bash
docker compose config
docker compose up -d --build
```

常用命令：

```bash
docker compose ps
docker compose logs api worker
docker compose down  # 停止并保留数据
```

容器名由 Compose 生成，例如 `pisuan-dev-a-api-1`。命令和脚本应使用 service 名，不要依赖具体容器名。

## 数据规则

- 一个运行中的槽位只允许一套 API、worker 和 `storage-migrator` 写入。
- 同一槽位可以在执行 `docker compose down` 后交给兼容分支使用。
- Schema 不兼容时创建新槽位，不修改 `pisuan_schema_migrations` 伪装兼容。
- 知识库同时依赖 PostgreSQL、MinIO、Milvus 和 Neo4j；复制时必须在停机后备份整套状态。
- 不提交 `.env` 或状态目录，不对需要保留的槽位执行 `docker compose down -v`。
- 未经明确授权，Agent 不得删除 volume、状态目录、`.env` 或生产数据。

`make reset` 只处理 `Pisuan` 的默认 `./docker/volumes`，不会删除外部槽位。
