#!/usr/bin/env bash
# 离线安装 Docker Engine（static tgz）+ compose 插件；幂等（已装达标版本即跳过）
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

need_engine=1; need_compose=1
if command -v docker >/dev/null 2>&1; then
  v=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
  major=${v%%.*}; minor=${v#*.}
  [ "$major" -gt 28 ] || { [ "$major" -eq 28 ] && [ "$minor" -ge 0 ]; } && need_engine=0
  echo "检测到 Docker $v"
fi
if docker compose version >/dev/null 2>&1; then
  cv=$(docker compose version --short | grep -oE '[0-9]+\.[0-9]+' | head -1)
  cmaj=${cv%%.*}; cmin=${cv#*.}
  { [ "$cmaj" -gt 2 ] || { [ "$cmaj" -eq 2 ] && [ "$cmin" -ge 33 ]; }; } && need_compose=0
fi

[ "$need_engine" -eq 1 ] && {
  tgz=$(ls payload/docker/docker-*.tgz 2>/dev/null | head -1) || true
  [ -n "$tgz" ] || { echo "❌ 无 Docker Engine ≥28 且 payload/docker/ 无 docker-*.tgz"; exit 1; }
  echo "[docker] 解压 $tgz → /usr/bin"
  tar -xzf "$tgz" -C /usr/bin --strip-components=1 docker/docker docker/dockerd docker/docker-proxy docker/containerd docker/containerd-shim-runc-v2 docker/runc
  install -m 0644 assets/docker.service /etc/systemd/system/docker.service
  systemctl daemon-reload && systemctl enable --now docker
}
[ "$need_compose" -eq 1 ] && {
  cmp=$(ls payload/docker/docker-compose-*-linux-x86_64 2>/dev/null | head -1) || true
  [ -n "$cmp" ] || { echo "❌ 缺 compose 插件二进制"; exit 1; }
  mkdir -p /usr/local/lib/docker/cli-plugins
  install -m 0755 "$cmp" /usr/local/lib/docker/cli-plugins/docker-compose
}

docker --version && docker compose version
echo "✅ Docker 就绪"
