# ============================================================
# auto-sync.ps1 — 无人值守上游代码同步（供定时任务调用）
# ============================================================
# 每天午夜执行：拉取 upstream/main，尝试自动 rebase。
# 无冲突 → 自动完成，记录日志
# 有冲突 → 中止 rebase，记录冲突文件清单，等待人工处理
# ============================================================

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$LogDir = "$RepoRoot\scripts\logs"
$LogFile = "$LogDir\sync-$(Get-Date -Format 'yyyy-MM-dd').log"

# 确保日志目录存在
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp  $Message" | Tee-Object -FilePath $LogFile -Append
}

Write-Log "========== 开始每日同步 =========="

Set-Location $RepoRoot

# 确保工作区干净
$dirty = git status --porcelain 2>$null
if ($dirty) {
    Write-Log "⚠️  工作区不干净，跳过本次同步"
    Write-Log "   脏文件: $($dirty -join ', ')"
    exit 0
}

# 1. 拉取上游
Write-Log "==> [1/4] 拉取 upstream ..."
$fetchResult = git fetch upstream 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "❌ fetch upstream 失败: $fetchResult"
    exit 1
}
Write-Log "   fetch 完成"

# 检查上游是否有新提交
$currentMain = git rev-parse main
$upstreamMain = git rev-parse upstream/main
if ($currentMain -eq $upstreamMain) {
    Write-Log "   upstream/main 无新提交，跳过同步"
    Write-Log "========== 同步结束（无变更） =========="
    exit 0
}
$newCount = (git rev-list --count main..upstream/main 2>$null)
Write-Log "   发现 $newCount 个新提交"

# 2. 更新 main
Write-Log "==> [2/4] 更新 main ..."
$savedBranch = git branch --show-current
git checkout main 2>&1 | Out-Null
$mergeResult = git merge upstream/main --ff-only 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "❌ main 快进合并失败: $mergeResult"
    git checkout $savedBranch 2>&1 | Out-Null
    exit 1
}
Write-Log "   main → $(git rev-parse --short main)"

# 3. Rebase pisuan-custom
Write-Log "==> [3/4] Rebase pisuan-custom ..."
git checkout pisuan-custom 2>&1 | Out-Null
$rebaseResult = git rebase main 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "⚠️  rebase 存在冲突，自动中止"
    git rebase --abort 2>&1 | Out-Null
    $conflictFiles = (git diff --name-only --diff-filter=U 2>$null) -join ', '
    Write-Log "   冲突文件: $conflictFiles"
    Write-Log "   请手动执行: git checkout pisuan-custom && git rebase main"
    Write-Log "========== 同步失败（需人工处理） =========="
    exit 1
}
Write-Log "   pisuan-custom → $(git rev-parse --short pisuan-custom)"

# 4. 切回 pisuan-custom
git checkout pisuan-custom 2>&1 | Out-Null

Write-Log "==> [4/4] 完成"
Write-Log "========== 同步成功 =========="
