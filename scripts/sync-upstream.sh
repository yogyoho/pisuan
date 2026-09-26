#!/usr/bin/env bash
# ============================================================
# sync-upstream.sh — 同步上游 Yuxi 仓库最新代码到 Pisuan
# ============================================================
# 工作模式（三分支策略）：
#   main             → 始终跟踪 upstream/main（纯净的上游代码）
#   pisuan-custom    → 领域知识库工厂定制 + 上游基础（rebase 在 main 之上）
#   pisuan-localized → pisuan-custom + 机械改名层（yuxi→pisuan, 脚本重建, 可丢弃）
#
# 每次上游发新版后执行本脚本即可：
#   bash scripts/sync-upstream.sh
#
# 冲突处理：
#   脚本会自动 rebase，冲突时需要手动解决后执行:
#     git add -A && git rebase --continue
# 注意: 修改本脚本时须同步维持 scripts/sync-upstream.ps1 语义对齐
# ============================================================

set -euo pipefail

echo "==> [1/5] 拉取上游最新代码..."
git fetch upstream || { echo "⚠️  拉取上游失败, 请检查网络。"; exit 1; }

echo ""
echo "==> [2/5] 更新本地 main 到 upstream/main..."
# fetch 强制 ff 更新本地 main ref: 非 ff 自动拒绝(fail-closed), 全程不触碰工作树——
# 兼容 .wolf 等跟踪文件的常态未提交改动(checkout 往返会被脏树拒绝)
git fetch upstream main:main || {
  echo "⚠️  main 无法快进到 upstream/main，请手动处理。"
  exit 1
}
echo "   main 已更新到 $(git rev-parse --short main)"

echo ""
echo "==> [3/5] 将 pisuan-custom rebase 到最新 main..."
git checkout pisuan-custom
# --autostash: 临时收起 .wolf 等未提交改动, rebase 后自动恢复, 冲突语义不变
if git rebase --autostash main; then
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
echo "==> [4/5] 推送 main 与 pisuan-custom 到 origin..."
git push origin main
# rebase 改写历史必须强推, lease 防覆盖他人
git push --force-with-lease origin pisuan-custom
echo "   ✅ 推送完成"

echo ""
echo "==> [5/5] 重建 pisuan-localized（机械改名层重新生成）..."
LOCALIZED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)-localized"

rebuild_localized() {
  git -C "$LOCALIZED_DIR" fetch origin || return 1
  git -C "$LOCALIZED_DIR" switch pisuan-localized || return 1
  git -C "$LOCALIZED_DIR" reset --hard origin/pisuan-custom || return 1
  python scripts/apply_pisuan_rename.py --apply --root "$LOCALIZED_DIR" || return 1
  uv lock --directory "$LOCALIZED_DIR/backend" || return 1
  uv lock --directory "$LOCALIZED_DIR/packages/pisuan-cli" || return 1
  git -C "$LOCALIZED_DIR" add -A || return 1
  if git -C "$LOCALIZED_DIR" diff --cached --quiet; then
    echo "   无变化, 跳过提交与推送"
  else
    git -C "$LOCALIZED_DIR" commit -m "chore: 机械改名层 yuxi→pisuan（脚本重新生成）" || return 1
    git -C "$LOCALIZED_DIR" push github pisuan-localized --force-with-lease || return 1
    echo "   ✅ pisuan-localized 已重建并推送"
  fi
  return 0
}

if ! rebuild_localized; then
  echo "⚠️  localized 重建失败, pisuan-custom 已同步完成, 可稍后手动重建。"
fi

echo ""
echo "============================================"
echo "✅ 同步完成！"
echo "  main:             $(git rev-parse --short main)"
echo "  pisuan-custom:    $(git rev-parse --short pisuan-custom)"
echo "  pisuan-localized: $(git -C "$LOCALIZED_DIR" rev-parse --short HEAD)"
echo "============================================"
echo "提醒：pisuan-localized 禁止手工语义改动（红线纪律）。"
echo "同步后验证清单见 docs/develop-guides/upstream-sync-guide.md 第五节。"
