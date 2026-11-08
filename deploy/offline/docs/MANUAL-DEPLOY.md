# Pisuan 全新部署手册（离线生产环境）

> 适用：无外网 Linux 服务器从零部署。部署完成后经 `http://<服务器IP>:<PISUAN_WEB_PORT>` 访问（默认 80 端口）。
> 角色：开发机（联网，打包）/ 生产服务器（离线，部署），传输介质为 U 盘或内网 scp。
>
> 本手册每一步都给出「脚本命令 + 手工等效」两种方式：优先跑 `install.sh` 一键部署；
> 脚本某一步失败时，按本手册对应小节手工执行等效命令后重跑脚本（幂等，安全）。

## 0. 前置条件

| 项 | 要求 | 检查命令 |
| --- | --- | --- |
| Docker | ≥28.0（无则先跑 install-docker.sh） | `docker --version` |
| compose | ≥v2.33.1（gw_priority 需要） | `docker compose version` |
| 磁盘 | ≥120GB | `df -h /opt` |
| 内存 | ≥32GB（GPU 模式） | `free -g` |
| GPU | NVIDIA 驱动 + Container Toolkit（ENABLE_GPU=true 时） | `nvidia-smi` |
| 架构 | x86_64（aarch64 需换对应 payload） | `uname -m` |

**包完整性校验（解压前）**：在包所在目录执行 `sha256sum -c <包名>.tar.gz.sha256.txt`，校验失败勿解压部署。

## 1. 安装 Docker（无 Docker 时）

```bash
sudo bash install-docker.sh
systemctl enable --now docker && docker --version
```

手工等效：见 `payload/docker/` 内 README 注释（tar 解压 /usr/bin + docker.service + compose 插件）。
信创发行版（deb/rpm 路径）：见附录 A。

## 2. 配置 deploy.conf（唯一手写）

```bash
cp deploy.conf.example deploy.conf && vi deploy.conf   # 填 3 个必填项
```

必填项：`PISUAN_SEED_SUPERADMIN_PASSWORD`（种子管理员密码）、
`PISUAN_SEED_DEFAULT_USER_PASSWORD`（批量默认账号初始密码）、
`GITEA_REFS_PASSWORD`（refsadmin 密码，prod compose `:?` 强制校验，缺失则 compose 拒绝启动）。

## 3. 一键部署

```bash
chmod +x install.sh && sudo ./install.sh
```

脚本依次：预检 → 生成 .env.prod（幂等）→ load 镜像 → GPU 层 → 落位预置状态 → up → 等健康 → 建管理员 → 沙盒冒烟 → 验证清单。
每步失败即中止并打印手工等效命令；重跑安全（幂等）。

## 4. 手工逐步部署（脚本失败时）

### 4.1 生成 .env.prod

```bash
cp .env.prod.example .env.prod
# 自动补全密钥（每个只生成一次；已存在则跳过）：
for k in JWT_SECRET_KEY API_KEY_DERIVATION_SECRET SANDBOX_PROVISIONER_TOKEN \
         POSTGRES_PASSWORD NEO4J_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY \
         PISUAN_INSTANCE_ID; do
  grep -q "^$k=..*" .env.prod || echo "$k=$(openssl rand -hex 32)" >> .env.prod
done
# LANGFUSE_STACK_* 10 个键同理（ENABLE_LANGFUSE=true 时）
# 再从 deploy.conf 注入：PISUAN_WEB_PORT / PISUAN_SEED_SUPERADMIN_* / PISUAN_SEED_DEFAULT_USER_PASSWORD / GITEA_REFS_PASSWORD / 开关
# 固定值：COMPOSE_PROJECT_NAME=pisuan-prod、PISUAN_VERSION=$(cat VERSION)（包根 VERSION 文件由打包脚本生成）
```

### 4.2 导入镜像

```bash
bash load-images.sh                     # 或逐个：docker load -i images/core/xxx.tar
docker images --format '{{.Repository}}:{{.Tag}}' | sort > /tmp/loaded.txt
diff <(sort manifest.txt) <(grep -Fxf /tmp/loaded.txt manifest.txt | sort) && echo "镜像核对一致"
```

### 4.3 GPU 层（ENABLE_GPU=true）

```bash
nvidia-smi || { bash payload/nvidia/install-driver.sh; }
```

**⚠️ 装驱动后必须重启服务器，重启后从本节 toolkit 安装步骤继续（或直接重跑 install.sh，幂等可续）**

```bash
sudo apt-get install -y ./payload/nvidia/libnvidia-container*.deb \
    ./payload/nvidia/nvidia-container-toolkit*.deb      # rpm 发行版用 yum localinstall
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
docker info | grep -i nvidia            # 期望出现 nvidia runtime
```

### 4.4 落位预置状态

```bash
sudo mkdir -p docker/volumes/pisuan
sudo cp -rn state/pisuan/. docker/volumes/pisuan/    # -n：已存在绝不覆盖
sudo chown -R 1000:1000 docker/volumes/pisuan/refs-repo docker/volumes/pisuan/gitea-data   # api 与 gitea 容器都以 1000:1000 访问各自挂载
```

### 4.5 启动

```bash
export COMPOSE="docker compose -p pisuan-prod --env-file .env.prod -f docker-compose.prod.yml"
$COMPOSE --profile all up -d   # ENABLE_GPU=true 时（含 GPU OCR 层）
$COMPOSE up -d                 # ENABLE_GPU=false 时（CPU-only，不启动 mineru/paddlex）
# Langfuse（ENABLE_LANGFUSE=true 时）：
docker compose -p langfuse --env-file .env.prod -f docker-compose.langfuse.yml up -d
```

### 4.6 等健康

```bash
# 改过端口的先 export 再执行（PISUAN_WEB_PORT；§4.8 同理用 PISUAN_SANDBOX_PORT）
for i in $(seq 1 60); do curl -sf http://127.0.0.1:${PISUAN_WEB_PORT:-80}/api/system/ready && break; sleep 10; done
$COMPOSE ps                             # 全部 Up(healthy)；storage-migrator Exited(0) 属正常
```

Milvus 冷启动最慢，请耐心等待；`storage-migrator` 显示 `Exited(0)` 是一次性迁移任务正常退出，不是故障。

### 4.7 建管理员

```bash
$COMPOSE exec api python -m scripts.seed_initial_users
```

### 4.8 沙盒冒烟

sandbox-provisioner 已发布到宿主机 `127.0.0.1:${PISUAN_SANDBOX_PORT:-9002}`（容器内 8002，健康端点 `/health`）：

```bash
curl -sf http://127.0.0.1:${PISUAN_SANDBOX_PORT:-9002}/health
# 宿主端口仅在 .env.prod 设置了 PISUAN_SANDBOX_PORT 时才变；该发布仅绑定 127.0.0.1。
# 也可从容器网络内验证（等价）：
$COMPOSE exec api curl -sf http://sandbox-provisioner:8002/health
```

## 5. 部署后配置（浏览器）

- 模型管理：对话 LLM / Embedding 全部指向内网地址（离线环境云端 API 不可用）。
- Embedding 应急（内网无 Embedding 服务时，复用 mineru 镜像内 vLLM）：

```bash
docker run -d --runtime nvidia --name bge-m3 -p 19999:8000 \
  -v $PWD/payload/models/bge-m3:/models pisuan-prod-mineru:latest \
  vllm serve /models --task embed --port 8000
```

  然后在模型管理 UI 配置 Embedding 地址为 `http://<服务器IP>:19999/v1`。
  注意：
  1. 启动后先 `curl -s http://127.0.0.1:19999/v1/models` 确认服务在位再配 UI（`--task embed` 语法未在仓库内验证过；若报 invalid choice 改试 `--task embedding`）。
  2. 该命令默认绑定 0.0.0.0，仅限可信内网，否则改 `-p 127.0.0.1:19999:8000`。
  3. 无 --restart 策略，宿主重启后需手动重跑（依赖 GPU runtime）。
- 内网 LLM 连通性检查：

```bash
docker exec pisuan-prod-api-1 curl -sS -m 5 <LLM_BASE_URL>/models
```

## 6. 验收清单（全绿为部署完成）

- [ ] `$COMPOSE ps` 全部 Up(healthy)
- [ ] `/api/system/health` 与 `/api/system/ready` 通过
- [ ] 管理员登录
- [ ] 真实对话
- [ ] 建知识库 → 上传 → 解析 → 索引
- [ ] 沙盒代码执行
- [ ] Langfuse 控制台 + trace（若启用）
- [ ] refs 导出 → 历史可浏览（Gitea `http://127.0.0.1:${PISUAN_GITEA_HTTP_PORT:-3000}`，账号 refsadmin）
- [ ] MinerU / PaddleX 各解析一份 PDF（ENABLE_GPU=true 时）

## 7. 故障排查（按「最先失败的服务」看起）

- `$COMPOSE logs --tail=80 api worker milvus`
- Milvus 冷启动最慢，整机重启后 api 依赖链会自动等待
- Redis 重建后 worker 失联：`$COMPOSE restart worker`
- 沙盒创建报镜像不存在：`docker images | grep all-in-one-sandbox`（缺 = 镜像没 load）
- 登录/对话报模型不可达：模型管理 UI 地址/密钥核对 + 容器内 curl
- refs 导出报错：查 api 日志 `REFS_*` 变量与 gitea 容器状态（`$COMPOSE logs gitea`）
- compose up 报 "GITEA_REFS_PASSWORD ... required a value"：deploy.conf 该项未填或为空 → 补填后重跑 install.sh
- 首次现场问题记录在此节追加（实测坑实录模式）

## 附录 A. 信创发行版 Docker 安装（deb/rpm）

`payload/docker/rpm-or-deb/` 内按发行版 `dpkg -i` / `rpm -ivh` 全量包安装，
随后同第 1 节执行 `systemctl enable --now docker && docker --version` 验证。

## 附录 B. 数据红线

同 README「数据红线」表：任何情况下不执行 `down -v`、`volume prune`、
`rm -rf docker/volumes`、`docker system prune -af`。

## 附录 C. 第三方许可证

见 `docs/LICENSES.md`（GPL/AGPL 再分发义务）。
