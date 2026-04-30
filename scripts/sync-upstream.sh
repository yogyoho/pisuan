#!/usr/bin/env bash
# ============================================================
# sync-upstream.sh — 同步上游 Yuxi 仓库最新代码到 Pisuan
# ============================================================
# 工作模式（双分支策略）：
#   main          → 始终跟踪 upstream/main（纯净的上游代码）
#   pisuan-custom → 领域知识库工厂定制 + 上游基础（rebase 在 main 之上）
#
# 每次上游发新版后执行本脚本即可：
#   bash scripts/sync-upstream.sh
#
# 冲突处理：
#   脚本会自动 rebase，冲突时需要手动解决后执行:
#     git add -A && git rebase --continue
# ============================================================

set -euo pipefail

echo "==> [1/4] 拉取上游最新代码..."
git fetch upstream

echo ""
echo "==> [2/4] 更新本地 main 到 upstream/main..."
CURRENT_BRANCH=$(git branch --show-current)
git checkout main
git merge upstream/main --ff-only 2>/dev/null || {
  echo "⚠️  main 无法快进合并，可能有本地提交。请手动处理。"
  git checkout "$CURRENT_BRANCH"
  exit 1
}
echo "   main 已更新到 $(git rev-parse --short HEAD)"

echo ""
echo "==> [3/4] 将 pisuan-custom rebase 到最新 main..."
git checkout pisuan-custom
if git rebase main; then
  echo "   ✅ rebase 成功，无冲突"
else
  echo ""
  echo "⚠️  存在冲突，请手动解决后执行:"
  echo "    git add -A && git rebase --continue"
  echo "  放弃本次同步:"
  echo "    git rebase --abort"
  exit 1
fi

echo ""
echo "==> [4/4] 切回 pisuan-custom 分支"
git checkout pisuan-custom

echo ""
echo "============================================"
echo "✅ 同步完成！"
echo "  main:          $(git rev-parse --short main)"
echo "  pisuan-custom: $(git rev-parse --short pisuan-custom)"
echo "============================================"
