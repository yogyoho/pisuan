# Pisuan 升级手册（重打全量包模式）

## 原则

- 升级 = 新版本离线包重跑 install.sh（幂等：密钥/数据卷不动，storage-migrator 自动迁移）
- 升级前必须备份；数据在 `docker/volumes/` 与命名卷，镜像重建不丢

## 1. 升级前备份（停机窗口内）

```bash
export COMPOSE="docker compose -p pisuan-prod --env-file .env.prod -f docker-compose.prod.yml"
$COMPOSE down                                    # 不带 -v
tar czf backup-$(date +%Y%m%d)-volumes.tar.gz docker/volumes/
```

PostgreSQL 一致性备份：已停机状态下目录 tar 一致性足够；命名卷先 `docker volume inspect` 核对实际卷名。

## 2. 部署新包

解压新版包到新目录 → 拷贝旧 `.env.prod` + `deploy.conf` 到新目录 → `sudo ./install.sh`。
或原地覆盖 compose/镜像（`.env.prod` 不被覆盖——install.sh 幂等只补缺失键）。

## 3. 迁移与验证

storage-migrator 由 compose 依赖链自动执行；`$COMPOSE logs storage-migrator` 确认退出码 0。
按 MANUAL-DEPLOY §6 验收清单全绿 → 升级完成。

## 4. 回滚

保持服务停止 → 恢复备份卷 → 用旧版本包 install.sh → 验收清单。
（schema 迁移带版本校验；跨版本回滚需恢复备份，不可只回退代码。）

## 5. 红线

`down -v` / `volume prune` / `rm -rf docker/volumes` / `system prune -af` —— 任何情况下不执行。
