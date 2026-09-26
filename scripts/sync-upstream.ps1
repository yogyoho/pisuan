# ============================================================
# sync-upstream.ps1 — 同步上游 Yuxi 仓库最新代码到 Pisuan
# ============================================================
# 工作模式（三分支策略）：
#   main             → 始终跟踪 upstream/main（纯净的上游代码）
#   pisuan-custom    → 领域知识库工厂定制 + 上游基础（rebase 在 main 之上）
#   pisuan-localized → pisuan-custom + 机械改名层（yuxi→pisuan, 脚本重建, 可丢弃）
#
# 执行：.\scripts\sync-upstream.ps1
# 冲突时手动解决后执行：git add -A; git rebase --continue
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "==> [1/5] 拉取上游最新代码..." -ForegroundColor Cyan
git fetch upstream
if ($LASTEXITCODE -ne 0) { Write-Host "⚠️  拉取上游失败, 请检查网络。" -ForegroundColor Yellow; exit 1 }

Write-Host ""
Write-Host "==> [2/5] 更新本地 main 到 upstream/main..." -ForegroundColor Cyan
$currentBranch = git branch --show-current
git checkout main
git merge upstream/main --ff-only 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  main 无法快进合并，可能有本地提交。请手动处理。" -ForegroundColor Yellow
    git checkout $currentBranch
    exit 1
}
Write-Host "   main 已更新到 $(git rev-parse --short HEAD)"

Write-Host ""
Write-Host "==> [3/5] 将 pisuan-custom rebase 到最新 main..." -ForegroundColor Cyan
git checkout pisuan-custom
git rebase main
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ rebase 成功，无冲突" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "⚠️  存在冲突，请手动解决后执行:" -ForegroundColor Yellow
    Write-Host "    git add -A; git rebase --continue"
    Write-Host "  放弃本次同步:"
    Write-Host "    git rebase --abort"
    exit 1
}

Write-Host ""
Write-Host "==> [4/5] 推送 main 与 pisuan-custom 到 origin..." -ForegroundColor Cyan
git push origin main
if ($LASTEXITCODE -ne 0) { Write-Host "⚠️  main 推送失败，请手动处理。" -ForegroundColor Yellow; exit 1 }
# rebase 改写历史必须强推, lease 防覆盖他人
git push --force-with-lease origin pisuan-custom
if ($LASTEXITCODE -ne 0) { Write-Host "⚠️  pisuan-custom 推送失败，请手动处理。" -ForegroundColor Yellow; exit 1 }
Write-Host "   ✅ 推送完成" -ForegroundColor Green

Write-Host ""
Write-Host "==> [5/5] 重建 pisuan-localized（机械改名层重新生成）..." -ForegroundColor Cyan
$localizedDir = "$(Split-Path $PSScriptRoot -Parent)-localized"
$ok = $false
try {
    git -C $localizedDir fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch origin 失败" }
    git -C $localizedDir switch pisuan-localized
    if ($LASTEXITCODE -ne 0) { throw "git switch pisuan-localized 失败" }
    git -C $localizedDir reset --hard origin/pisuan-custom
    if ($LASTEXITCODE -ne 0) { throw "git reset --hard 失败" }
    python scripts/apply_pisuan_rename.py --apply --root $localizedDir
    if ($LASTEXITCODE -ne 0) { throw "apply_pisuan_rename.py 执行失败" }
    uv lock --directory (Join-Path $localizedDir "backend")
    if ($LASTEXITCODE -ne 0) { throw "backend uv lock 失败" }
    uv lock --directory (Join-Path $localizedDir "packages/pisuan-cli")
    if ($LASTEXITCODE -ne 0) { throw "pisuan-cli uv lock 失败" }
    git -C $localizedDir add -A
    git -C $localizedDir diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   无变化, 跳过提交与推送"
    } else {
        git -C $localizedDir commit -m "chore: 机械改名层 yuxi→pisuan（脚本重新生成）"
        if ($LASTEXITCODE -ne 0) { throw "git commit 失败" }
        git -C $localizedDir push github pisuan-localized --force-with-lease
        if ($LASTEXITCODE -ne 0) { throw "git push github 失败" }
    }
    $ok = $true
} catch {
    Write-Host "⚠️  localized 重建失败: $_" -ForegroundColor Yellow
    Write-Host "    pisuan-custom 已同步完成, localized 可稍后手动重建。"
}
if ($ok) { Write-Host "   ✅ pisuan-localized 已重建并推送" -ForegroundColor Green }

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ 同步完成！"
Write-Host "  main:             $(git rev-parse --short main)"
Write-Host "  pisuan-custom:    $(git rev-parse --short pisuan-custom)"
Write-Host "  pisuan-localized: $(git -C $localizedDir rev-parse --short HEAD)"
Write-Host "============================================" -ForegroundColor Green
Write-Host "提醒：pisuan-localized 禁止手工语义改动（红线纪律）。"
Write-Host "同步后验证清单见 docs/develop-guides/upstream-sync-guide.md 第五节。"
