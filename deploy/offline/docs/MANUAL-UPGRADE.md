# Yuxi 升级手册（重打全量包模式）

## 原则

- 升级 = 新版本离线包重跑 install.sh（幂等：密钥/数据卷不动，storage-migrator 自动迁移）
- 升级前必须备份；核心栈数据全部在 `docker/volumes/`（bind mount，prod compose 无命名卷），镜像重建不丢

## 1. 升级前备份（停机窗口内）

```bash
export COMPOSE="docker compose -p yuxi-prod --env-file .env.prod -f docker-compose.prod.yml"
$COMPOSE down                                    # 不带 -v
tar czf backup-$(date +%Y%m%d)-volumes.tar.gz docker/volumes/
```

PostgreSQL 一致性备份：已停机状态下目录 tar 一致性足够。

启用 Langfuse 观测栈时另有独立命名卷（langfuse 项目声明：`database_data` / `clickhouse_data` / `clickhouse_logs` / `minio_data` / `redis_data`，容器内实际卷名带 `langfuse_` 前缀，先 `docker volume ls` 核对）。如需一并备份，逐卷执行（可选，核心栈恢复不依赖它们；`clickhouse_logs` 为日志卷，可不备）：

```bash
docker run --rm -v <卷名>:/v -v $PWD:/b postgres:16 tar czf /b/<卷名>.tar.gz -C /v .
```

## 2. 部署新包

解压新版包到新目录 → 拷贝旧 `.env.prod` + `deploy.conf` 到新目录 → `sudo ./install.sh`。
或原地覆盖 compose/镜像（`.env.prod` 不被覆盖——install.sh 幂等只补缺失键）。

```bash
# 换新目录部署时重新 export COMPOSE（§1 的变量不随目录走）
```

install.sh 的建管理员步骤在已初始化库上会报「系统已初始化」并跳过，属预期，非失败。

## 3. 迁移与验证

storage-migrator 由 compose 依赖链自动执行；`$COMPOSE logs storage-migrator` 确认退出码 0。
按 MANUAL-DEPLOY §6 验收清单全绿 → 升级完成。

## 4. 回滚

保持服务停止 → 恢复备份卷 → 用旧版本包 install.sh → 验收清单。
（schema 迁移带版本校验；跨版本回滚需恢复备份，不可只回退代码。）

## 5. 红线

`down -v` / `volume prune` / `rm -rf docker/volumes` / `system prune -af` —— 任何情况下不执行。
