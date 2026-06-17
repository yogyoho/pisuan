# 品牌重命名：Yuxi → Pisuan

**日期**: 2026-05-13
**分支**: pisuan-custom

## 目标

将用户可见的品牌名从 Yuxi 替换为 Pisuan，创建独立的生产部署配置文件 `docker-compose-prod-hy.yml`，并提供离线镜像导出方案。

## 约束

- **Python 包名 `yuxi` 不改**：保持 `backend/package/yuxi/` 目录和所有 `import yuxi` 不变，确保上游代码同步不受影响
- **后端内部标识不改**：JWT audience/issuer (`yuxi-know-api`, `yuxi-know:`)、`YUXI_ENV`/`YUXI_INSTANCE_ID`/`YUXI_VERSION` 环境变量名、milvus 默认 db name 等保持不变
- **上游仓库 URL 改动**：前端中指向 `xerrors/Yuxi` 的文档链接和 GitHub 链接全部去掉

## 改动清单

### 1. UI 品牌替换

| 文件 | 行号 | 改动 |
|------|------|------|
| `web/src/views/LoginView.vue` | 235 | `'Yuxi-Know'` → `'Pisuan-Know'` |
| `web/src/layouts/AppLayout.vue` | 102 | `\|\| 'Yuxi'` → `\|\| 'Pisuan'` |
| `web/src/components/SettingsModal.vue` | 83,95,96,207,208 | 删除 Star 卡片相关代码 |
| `web/src/components/UserInfoComponent.vue` | 295 | 删除"帮助文档"跳转（指向上游 xerrors.github.io/Yuxi/） |
| `web/src/components/FileUploadModal.vue` | 1210 | 删除上游文档链接 |
| `web/src/components/modals/BenchmarkGenerateModal.vue` | 138 | 删除上游文档链接 |
| `web/src/components/modals/BenchmarkUploadModal.vue` | 95 | 删除上游文档链接 |

### 2. 新建 `docker-compose-prod-hy.yml`

基于 `docker-compose.prod.yml`，修改：

- 镜像名：`yuxi-api` → `pisuan-api`，`yuxi-web` → `pisuan-web`，`yuxi-sandbox-provisioner` → `pisuan-sandbox`
- 容器名：加 `pisuan-` 前缀
- 网络名：`app-network` → `pisuan-network`
- 数据库默认名：`yuxi_know` → `pisuan_know`
- Sandbox 相关默认值：`yuxi-sandbox` → `pisuan-sandbox`，`yuxi-know` → `pisuan`
- env_file：`.env.prod` → `.env.hy`
- YUXI_ENV 保持不变（后端内部标识）
- 第三方镜像（neo4j, etcd, minio, milvus, postgres, redis 等）保持不变

### 3. 新建 `.env.hy`

基于 `.env.template`，修改所有带 yuxi 的默认值：
- `POSTGRES_DB=pisuan_know`
- Sandbox 相关默认值替换为 pisuan
- 保留安全配置项供用户填写

### 4. 新建镜像导出脚本 `scripts/export-images.sh`

- 从 `docker-compose-prod-hy.yml` 中提取所有镜像
- 批量 `docker save` 为 `pisuan-images-{version}.tar`
- 配套 `scripts/import-images.sh` 用于目标服务器加载

## 不改的部分

- `backend/package/yuxi/` 目录和所有 Python import
- `backend/server/utils/auth_utils.py` 中的 JWT 常量
- `backend/server/routers/system_router.py` 中的 `YUXI_VERSION` 模板变量
- `backend/package/yuxi/knowledge/implementations/milvus.py` 中的默认 db name
- `backend/test/` 中所有测试文件
- `docker-compose.yml` 和 `docker-compose.prod.yml`（保持上游版本不变）
- `CLAUDE.md`、`ARCHITECTURE.md` 等开发文档中的包名引用
