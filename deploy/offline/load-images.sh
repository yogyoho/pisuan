#!/usr/bin/env bash
# 导入 images/ 下全部 tar + 核对 manifest.txt
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

IMG_DIR="${1:-images}"
TOTAL=0; FAIL=0
for tarfile in "$IMG_DIR"/*/*.tar "$IMG_DIR"/*.tar; do
  [ -f "$tarfile" ] || continue
  echo "[load] $tarfile"
  docker load -i "$tarfile" || { echo "❌ load 失败: $tarfile"; FAIL=$((FAIL+1)); }
  TOTAL=$((TOTAL+1))
done
[ "$TOTAL" -gt 0 ] || { echo "❌ images/ 下无 tar"; exit 1; }

if [ -f manifest.txt ]; then
  MISS=0
  while IFS= read -r tag; do
    tag=${tag%$'\r'}
    [ -z "$tag" ] && continue
    docker image inspect "$tag" >/dev/null 2>&1 || { echo "❌ 缺镜像: $tag"; MISS=$((MISS+1)); }
  done < manifest.txt
  [ "$MISS" -eq 0 ] || { echo "❌ $MISS 个镜像缺失，中止（防 compose 尝试联网 build）"; exit 1; }
  echo "✅ 全部 $(grep -c . manifest.txt) 个镜像在位"
fi
[ "$FAIL" -eq 0 ] || exit 1
