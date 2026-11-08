#!/usr/bin/env bash
# Yuxi 生产离线部署 — install.sh（幂等；失败即中止并打印手工等效命令）
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

COMPOSE="docker compose -p yuxi-prod --env-file .env.prod -f docker-compose.prod.yml"
WEB_PORT_DEFAULT=80

log_i(){ echo "[INFO]  $*"; }
log_w(){ echo "[WARN]  $*"; }
log_e(){ echo "[ERROR] $*"; }
die(){ log_e "$*"; echo ">>> 手工续行见 docs/MANUAL-DEPLOY.md 对应章节"; exit 1; }

# ─ [0] 预检 ────────────────────────────────────────────────
preflight(){
  command -v docker >/dev/null || die "Docker 未安装：先执行 bash install-docker.sh"
  docker compose version >/dev/null || die "compose 插件缺失"
  command -v openssl >/dev/null || die "缺 openssl（密钥生成必需）"
  command -v curl >/dev/null || die "缺 curl（健康检查必需）"
  disk=$(df -BG . | awk 'NR==2{print $4}' | sed 's/G//'); [ "$disk" -ge 120 ] || log_w "磁盘仅 ${disk}G（建议 ≥120G）"
  mem=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0); [ "$mem" -ge 30000 ] || log_w "内存不足 30G（建议 ≥32G，Milvus 随知识库数据量线性增长）"
  mapcnt=$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo 0)
  if [ "$mapcnt" -lt 262144 ]; then
    echo "vm.max_map_count=262144" | tee /etc/sysctl.d/99-yuxi.conf >/dev/null
    sysctl -p /etc/sysctl.d/99-yuxi.conf
    log_i "vm.max_map_count 已设为 262144（Milvus 硬需求）"
  fi
  # 沙盒地址池冲突警告（与宿主 IP 同 /20 即提示）
  hostnet=$(ip -4 addr show scope global 2>/dev/null | grep -oE 'inet [0-9.]+' | awk '{print $2}' | head -1 || true)
  [ -n "$hostnet" ] && [ "${hostnet%%.*}" = "10" ] && [ "${hostnet#10.253.}" != "$hostnet" ] && \
    log_w "宿主 IP $hostnet 可能与沙盒地址池 10.253.240.0/20 冲突——部署前改 .env.prod 的 SANDBOX_DOCKER_ADDRESS_POOL"
  grep -E ':(0050|17A2|1920|1CD3|2710|2711|5032|276B|211A|21EF|0BB8|232A)\b' /proc/net/tcp* >/dev/null 2>&1 && \
    log_w "部分端口可能被占用（/proc/net/tcp 粗检）——完整端口清单见 MANUAL-DEPLOY §0"
  return 0
}

# ─ [1] deploy.conf → .env.prod（幂等定向注入）────────────────
gen_env(){
  [ -f deploy.conf ] || die "缺 deploy.conf：cp deploy.conf.example deploy.conf 后填写必填项"
  [ -f .env.prod ] || sed 's/\r$//' .env.prod.example > .env.prod
  local gen_keys="JWT_SECRET_KEY API_KEY_DERIVATION_SECRET SANDBOX_PROVISIONER_TOKEN POSTGRES_PASSWORD
    NEO4J_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY YUXI_INSTANCE_ID
    LANGFUSE_STACK_NEXTAUTH_SECRET LANGFUSE_STACK_SALT LANGFUSE_STACK_ENCRYPTION_KEY LANGFUSE_STACK_PG_PASS
    LANGFUSE_STACK_CH_PASSWORD LANGFUSE_STACK_REDIS_AUTH LANGFUSE_STACK_MINIO_PASS
    LANGFUSE_STACK_INIT_USER_PASSWORD LANGFUSE_STACK_INIT_PROJECT_PUBLIC_KEY LANGFUSE_STACK_INIT_PROJECT_SECRET_KEY"
  for k in $gen_keys; do
    grep -q "^$k=..*" .env.prod || echo "$k=$(openssl rand -hex 32)" >> .env.prod
  done
  grep -q "^COMPOSE_PROJECT_NAME=" .env.prod || echo "COMPOSE_PROJECT_NAME=yuxi-prod" >> .env.prod
  [ -f VERSION ] || die "包根缺 VERSION（打包脚本应生成）"
  grep -q "^YUXI_VERSION=" .env.prod || echo "YUXI_VERSION=$(cat VERSION)" >> .env.prod
  grep -q "^YUXI_ENV=" .env.prod || echo "YUXI_ENV=production" >> .env.prod
  # deploy.conf 注入（去行内注释与空白后追加；已存在跳过；空值不注入→必填校验兜底）
  while IFS='=' read -r k v; do
    k="${k#"${k%%[![:space:]]*}"}"
    case "$k" in ''|\#*) continue;; esac
    v=$(printf '%s' "$v" | sed -e 's/[[:space:]]#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [ -z "$v" ] && continue
    grep -q "^$k=" .env.prod || echo "$k=$v" >> .env.prod
  done < deploy.conf
  # deploy.conf 必填校验（空值即中止；三项由现场手填，不自动生成）
  for k in YUXI_SEED_SUPERADMIN_PASSWORD YUXI_SEED_DEFAULT_USER_PASSWORD GITEA_REFS_PASSWORD; do
    grep -q "^$k=..*" .env.prod || die "必填项 $k 未填写：补全 deploy.conf 后重跑"
  done
  log_i ".env.prod 就绪（密钥幂等生成；已存在的键一律不动）"
}

# ─ [2] 镜像导入 ────────────────────────────────────────────
load_images(){ bash load-images.sh images || die "镜像导入失败（load-images.sh 输出见上）"; }

# ─ [3] 预置状态落位（绝不覆盖已有）─────────────────────────
# 包内 state/ 为全量数据快照（知识库/文件库/图谱/数据库/refs，2026-11-08 裁定不脱敏）；
# cp -rn：现场已产生数据一律跳过（幂等重装安全）
state_sync(){
  # YUXI_STATE_DIR 在 .env.prod（含 deploy.conf 注入）有定义时随其落位，否则用默认
  local state_dir
  state_dir=$(grep -E '^YUXI_STATE_DIR=' .env.prod | cut -d= -f2- || true)
  state_dir=${state_dir:-./docker/volumes}
  mkdir -p "$state_dir"
  cp -rn state/. "$state_dir"/ && log_i "预置状态落位（全量数据快照；已存在项跳过）" || die "预置状态落位失败（磁盘/权限？）"
  # chown 只对非 root 服务做（uid 均为镜像实测，勿凭记忆改）：
  #   postgres:16 → 999:999（docker run --rm postgres:16 id postgres 实测）
  #   neo4j:5.26.29 → 7474:7474（docker run --rm neo4j:5.26.29 id 实测）
  #   milvusdb/milvus:v2.5.6、quay.io/coreos/etcd:v3.5.5 → root（id 实测）→ 不 chown
  #   api 卷目录 → api 容器 user "1000:1000"（prod compose；api.Dockerfile USER 同值）
  #   gitea → USER_UID=1000（prod compose）——故 yuxi/ 整树统一 1000:1000
  [ -d "$state_dir/postgresql" ] && chown -R 999:999 "$state_dir/postgresql"
  [ -d "$state_dir/neo4j/data" ] && chown -R 7474:7474 "$state_dir/neo4j/data"
  [ -d "$state_dir/yuxi" ] && chown -R 1000:1000 "$state_dir/yuxi"
  return 0
}

# ─ [4] 启动 ────────────────────────────────────────────────
up_stack(){
  $COMPOSE up -d || die "compose up 失败"
  if grep -q "^ENABLE_LANGFUSE=true" .env.prod; then
    docker compose -p langfuse --env-file .env.prod -f docker-compose.langfuse.yml up -d \
      || log_w "Langfuse 栈启动失败（观测能力暂缺，不阻塞核心交付；docker compose -p langfuse logs 排查后重跑该命令）"
  fi
}

# ─ [5] 等健康 ──────────────────────────────────────────────
wait_ready(){
  local port; port=$(grep '^YUXI_WEB_PORT=' .env.prod | cut -d= -f2 || true); port=${port:-$WEB_PORT_DEFAULT}
  local i; for i in $(seq 1 60); do
    curl -sf "http://127.0.0.1:${port}/api/system/ready" >/dev/null 2>&1 && { log_i "API ready（$((i*10))s）"; return 0; }
    sleep 10
  done
  $COMPOSE ps; $COMPOSE logs --tail=40 api worker 2>/dev/null || true
  die "10 分钟未就绪：按最先失败的服务排查（MANUAL-DEPLOY §7）"
}

# ─ [6] 建管理员 ────────────────────────────────────────────
seed_admin(){
  # 已初始化库会显式报"系统已初始化"并以非零退出——属预期跳过，非失败（与 MANUAL-UPGRADE §2 表述一致）
  $COMPOSE exec -T api python -m scripts.seed_initial_users && log_i "管理员已创建" || \
    log_w "seed 未执行（users 表非空=已初始化，属正常；其余情况查 api 日志）"
}

# ─ [7] 沙盒冒烟 ────────────────────────────────────────────
sandbox_smoke(){
  local sbport; sbport=$(grep '^YUXI_SANDBOX_PORT=' .env.prod | cut -d= -f2 || true); sbport=${sbport:-9002}
  curl -sf "http://127.0.0.1:${sbport}/health" >/dev/null && log_i "provisioner 健康" || log_w "provisioner /health 不通——查 $COMPOSE logs sandbox-provisioner"
  local img; img=$(grep '^SANDBOX_IMAGE=' .env.prod | cut -d= -f2 || true); img=${img:-enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:1.11.0}
  docker image inspect "$img" >/dev/null 2>&1 \
    && log_i "沙盒镜像本地在位" || log_w "⚠️ 沙盒镜像缺失——首次建沙盒将联网拉取并失败！"
}

# ─ [8] 验证清单 ────────────────────────────────────────────
summary(){
  local port; port=$(grep '^YUXI_WEB_PORT=' .env.prod | cut -d= -f2 || true); port=${port:-$WEB_PORT_DEFAULT}
  cat <<EOF

══════════════════════════════════════════════
  Yuxi 部署完成
  访问:  http://<服务器IP>:${port}
  管理员账号随预置快照交付（开发期原样数据；deploy.conf 种子密码仅对全新空库生效）
  下一步（MANUAL-DEPLOY §5-6）:
  [ ] 模型管理 UI 配内网 LLM/Embedding 地址（OpenAI 兼容）
  [ ] OCR 默认 rapid_ocr 开箱即用；客户自有引擎在设置 UI 接入
  [ ] 验收清单逐项核对
══════════════════════════════════════════════
EOF
}

guard_down(){ for a in "$@"; do case "$a" in -v|--volumes) log_e "禁止 down -v（销毁数据卷）"; exit 1;; esac; done; $COMPOSE down "$@"; }

case "${1:-install}" in
  install) preflight; gen_env; load_images; state_sync; up_stack; wait_ready; seed_admin; sandbox_smoke; summary;;
  down|stop) shift; guard_down "$@";;
  status) $COMPOSE ps;;
  logs) shift; $COMPOSE logs -f --tail=100 "$@";;
  *) echo "用法: $0 [install|down|status|logs <svc>]"; exit 1;;
esac
