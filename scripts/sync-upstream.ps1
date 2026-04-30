# ============================================================
# sync-upstream.ps1 — 同步上游 Yuxi 仓库最新代码到 Pisuan
# ============================================================
# 工作模式（双分支策略）：
#   main          → 始终跟踪 upstream/main（纯净的上游代码）
#   pisuan-custom → 领域知识库工厂定制 + 上游基础（rebase 在 main 之上）
#
# 执行：.\scripts\sync-upstream.ps1
# 冲突时手动解决后执行：git add -A; git rebase --continue
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "==> [1/4] 拉取上游最新代码..." -ForegroundColor Cyan
git fetch upstream

Write-Host ""
Write-Host "==> [2/4] 更新本地 main 到 upstream/main..." -ForegroundColor Cyan
$currentBranch = git branch --show-current
git checkout main
try {
    git merge upstream/main --ff-only 2>$null
} catch {
    Write-Host "⚠️  main 无法快进合并，可能有本地提交。请手动处理。" -ForegroundColor Yellow
    git checkout $currentBranch
    exit 1
}
Write-Host "   main 已更新到 $(git rev-parse --short HEAD)"

Write-Host ""
Write-Host "==> [3/4] 将 pisuan-custom rebase 到最新 main..." -ForegroundColor Cyan
git checkout pisuan-custom
try {
    git rebase main
    Write-Host "   ✅ rebase 成功，无冲突" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "⚠️  存在冲突，请手动解决后执行:" -ForegroundColor Yellow
    Write-Host "    git add -A; git rebase --continue"
    Write-Host "  放弃本次同步:"
    Write-Host "    git rebase --abort"
    exit 1
}

Write-Host ""
Write-Host "==> [4/4] 切回 pisuan-custom 分支" -ForegroundColor Cyan
git checkout pisuan-custom

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ 同步完成！"
Write-Host "  main:          $(git rev-parse --short main)"
Write-Host "  pisuan-custom: $(git rev-parse --short pisuan-custom)"
Write-Host "============================================"
