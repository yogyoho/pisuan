# 第三方组件与许可证附录（离线部署包）

本附录覆盖离线部署包通过容器镜像再分发的第三方组件及其许可证义务。
镜像版本以包内 `docker-compose.prod.yml` / `docker-compose.langfuse.yml` 写死的 tag 为准；
现场交付核对见第 6 节。

## 1. Pisuan 本体

Pisuan 本体使用 MIT License。

注意：Pisuan 本体的许可证声明文件未随本离线包交付（交付态裁定）。这不影响、也不免除
下述第三方组件的许可证义务——再分发第三方镜像时，各组件自身的义务仍然完整适用。

## 2. 核心栈（docker-compose.prod.yml）

| 组件 | 镜像引用 | 许可证 |
| --- | --- | --- |
| Neo4j Community | `neo4j:5.26.29` | GPL-3.0-only |
| MinIO | 本地构建：`<项目名>-minio:RELEASE.2023-03-20T20-16-18Z`（离线包内项目名为 `pisuan-prod`） | AGPL-3.0 |
| Milvus | `milvusdb/milvus:v2.5.6` | Apache-2.0 |
| etcd | `quay.io/coreos/etcd:v3.5.5` | Apache-2.0 |
| PostgreSQL | `postgres:16` | PostgreSQL License |
| Redis | `redis:7.4.10-alpine` | RSALv2 / SSPLv1（均非 OSI 许可证） |
| Gitea | `gitea/gitea:1.24` | MIT |
| api / web / sandbox-provisioner | `<项目名>-api|web|sandbox-provisioner:<版本>` | Pisuan 本体镜像（MIT） |

MinIO 镜像由本仓库构建（`docker/minio/Dockerfile`）：Docker Hub 与 quay.io 上的官方镜像已
不再公开分发，构建时从官方 GitHub Release 下载固定版本二进制并校验 sha256，运行与下架前
镜像逐字节相同的 MinIO 二进制；基础镜像与镜像内附带文件不同。

## 3. Langfuse 观测栈（docker-compose.langfuse.yml；已随离线包交付——install.sh 在 ENABLE_LANGFUSE=true（默认）时自动启动）

镜像随 images/ 一并 load 入本地；deploy.conf 置 ENABLE_LANGFUSE=false 可整体关闭。

| 组件 | 镜像引用 | 许可证 |
| --- | --- | --- |
| PostgreSQL | `postgres:17` | PostgreSQL License |
| ClickHouse | `clickhouse/clickhouse-server:25.12` | Apache-2.0 |
| MinIO | `cgr.dev/chainguard/minio` | MinIO 软件 AGPL-3.0（镜像为 Chainguard 构建，镜像条款以其随附声明为准） |
| Redis | `redis:7` | RSALv2 / SSPLv1（均非 OSI 许可证） |
| Langfuse | `langfuse/langfuse:4`、`langfuse/langfuse-worker:4` | MIT（其仓库 ee/ 企业版目录按单独商业许可，以镜像随附声明为准） |

## 4. 沙盒运行时镜像（assets/extra-images.txt）

| 组件 | 镜像引用 | 许可证 |
| --- | --- | --- |
| 代码执行沙盒 | `enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:1.11.0` | 以镜像随附声明与上游仓库为准 |

## 5. 再分发义务（GPL / AGPL）

- **GPL-3.0（Neo4j Community）**：再分发镜像需保留许可文本与上游声明，并按 GPL 第 6 条
  提供匹配的完整对应源码，或附有效的书面源码要约。
- **AGPL-3.0（MinIO，两份镜像）**：同上需保留许可文本与上游声明；AGPL 第 13 条对"通过网络
  向用户提供服务"额外要求向用户提供对应源码。通过网络提供服务、修改 AGPL 组件或把组件
  集成进同一程序时，义务可能不同，不能只附一个上游链接就视为完成。
- **RSALv2 / SSPLv1（Redis）**：均非 OSI 开源许可证，再分发与托管需逐条核对各自条款。
- 商业部署可评估 Neo4j Enterprise、MinIO 商业订阅或其他兼容替代品，但这会带来新的协议、
  迁移和运维条件。

## 6. 现场核对

按包内 `manifest.json` 的镜像 digest 逐项核对实际交付内容。`postgres:16`、`redis:7.4.10-alpine`、
本地构建的 `<项目名>-minio:RELEASE...` 等浮动或本地构建 tag 的内容以实际 digest 为准，本表只对写死的
版本 tag 提供对应的版本预期；镜像还可能包含各自的基础系统和传递依赖，离线交付前按实际
digest 核对许可证、版权声明和对应源码。

## 7. 边界声明

以上为工程侧边界说明，不构成法律意见；再分发、修改组件或对外托管前，请让法务按具体
版本和交付方式确认。
