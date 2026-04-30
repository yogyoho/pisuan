# ============================================================
# setup-scheduled-sync.ps1 — 注册每日午夜上游同步任务
# ============================================================
# 使用方法（以管理员身份运行 PowerShell）：
#   .\scripts\setup-scheduled-sync.ps1
#
# 查看/管理任务：
#   taskschd.msc → 任务计划程序库 → PisuanAutoSync
# ============================================================

$ErrorActionPreference = "Stop"
$TaskName = "PisuanAutoSync"
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$ScriptPath = "$RepoRoot\scripts\auto-sync.ps1"

# 移除旧任务（如果存在）
$existing = schtasks /query /tn $TaskName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "移除已有任务..." -ForegroundColor Yellow
    schtasks /delete /tn $TaskName /f
}

# 创建计划任务：每天 00:00 执行
Write-Host "创建计划任务: $TaskName" -ForegroundColor Cyan
Write-Host "  脚本: $ScriptPath" -ForegroundColor Gray
Write-Host "  时间: 每天 00:00" -ForegroundColor Gray

schtasks /create `
    /tn $TaskName `
    /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
    /sc daily `
    /st 00:00 `
    /ru "SYSTEM" `
    /f

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ 任务注册成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "管理命令:" -ForegroundColor Cyan
    Write-Host "  查看任务: schtasks /query /tn $TaskName /v"
    Write-Host "  手动运行: schtasks /run /tn $TaskName"
    Write-Host "  删除任务: schtasks /delete /tn $TaskName /f"
    Write-Host "  查看日志: $RepoRoot\scripts\logs\sync-YYYY-MM-DD.log"
    Write-Host ""
    Write-Host "⚠️  注意: 如遇冲突需人工处理，日志中会记录冲突文件清单。"
} else {
    Write-Host "❌ 任务注册失败" -ForegroundColor Red
}
