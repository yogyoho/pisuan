#Requires -Version 5.1
<#
.SYNOPSIS  Pisuan 离线部署包导出（在 pisuan-localized 树执行）
.EXAMPLE  .\scripts\offline-export.ps1 -OutDir E:\pisuan-pkg-work
#>
param(
  [Parameter(Mandatory=$true)][string]$OutDir,       # 外置盘工作区
  [switch]$SkipGpu,                                   # 跳过 GPU 镜像构建与导出
  [switch]$NoBuild,                                   # 不构建（要求镜像已在本地）
  [switch]$SkipPackage                                # 只 save 不 tar.gz（调试用）
)
$ErrorActionPreference = 'Stop'

# ── 分支守卫（与 sync 脚本同模式）──
$branch = git branch --show-current
if ($branch -ne 'pisuan-localized') { throw "必须在 pisuan-localized 分支运行（当前: $branch）；语义改动请回 pisuan-custom" }

$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Root

# ── 空间预检 ──
$drive = (Get-PSDrive ($OutDir.Substring(0,1))).Free/1GB
if ($drive -lt 90) { throw "工作区盘 $($OutDir[0]) 仅剩 $([int]$drive)G，需 ≥90G" }
$cFree = (Get-PSDrive C).Free/1GB
if (-not $NoBuild -and $cFree -lt 40) { throw "C 盘仅剩 $([int]$cFree)G，构建需 ≥40G" }

# ── 镜像清单（compose 管理 + 包外附加）──
$composeArgs = @('compose','--env-file','.env.prod','-f','docker-compose.prod.yml')
if (-not $SkipGpu) { $composeArgs += @('--profile','all') }
if ($NoBuild) {
  $images = @(docker @composeArgs config --images)
} else {
  # PS5.1 实测（5.1.19041）：EAP=Stop 下原生命令 2>&1 首行 stderr 即 NativeCommandError 终止——降级透传构建日志，退出码显式校验
  $ErrorActionPreference = 'Continue'
  docker @composeArgs build 2>&1 | ForEach-Object { Write-Host "[build] $_" }
  $ErrorActionPreference = 'Stop'
  if ($LASTEXITCODE -ne 0) { throw "镜像构建失败（docker build 退出码 $LASTEXITCODE）" }
  $images = @(docker @composeArgs config --images)
}
$images += Get-Content "$Root\deploy\offline\assets\extra-images.txt" | Where-Object { $_ -and -not $_.StartsWith('#') }
$images = $images | Select-Object -Unique

# ── gitea retag 为官方名（必须在缺失核对之前，否则核对先 throw）──
# PS5.1：2>$null 在 EAP=Stop 下镜像缺失即 NativeCommandError 终止——先降级再核对
$ErrorActionPreference = 'Continue'
$giteaExists = [bool](docker image inspect 'gitea/gitea:1.24' 2>$null)
$ErrorActionPreference = 'Stop'
if ($images -contains 'gitea/gitea:1.24' -and -not $giteaExists) {
  docker pull docker.m.daocloud.io/gitea/gitea:1.24
  docker tag docker.m.daocloud.io/gitea/gitea:1.24 gitea/gitea:1.24
}

# ── 缺失镜像核对（save 前把关；EAP 降级同上）──
$ErrorActionPreference = 'Continue'
$missing = @($images | Where-Object { -not (docker image inspect $_ 2>$null) })
$ErrorActionPreference = 'Stop'
if ($missing.Count -gt 0) { throw "本地缺镜像（先 docker pull 或去掉 -NoBuild）: $($missing -join ', ')" }

# ── 结构验证 ──
foreach ($img in $images) {
  $arch = (docker image inspect $img --format '{{.Architecture}}')
  if ($arch -ne 'amd64') { throw "$img 架构为 $arch，期望 amd64" }
}
$apiImage = $images | Where-Object { $_ -match '-api:' } | Select-Object -First 1
docker run --rm --entrypoint ls $apiImage /app/scripts /usr/local/bin/pisuan-entrypoint >$null
if ($LASTEXITCODE -ne 0) { throw "api 镜像内 /app/scripts 抽查失败（Task 2 的 COPY 未生效？）" }
Write-Host "[verify] 结构验证通过（amd64 + api 镜像 scripts 烘焙在位）"

# ── save 到工作区（pisuan-offline-work\staging；payload 同层）──
$work = Join-Path $OutDir "pisuan-offline-work"
$staging = Join-Path $work "staging"
New-Item -ItemType Directory -Force -Path "$staging\images\core","$staging\images\gpu" | Out-Null
$saved = @()
foreach ($img in $images) {
  if ($SkipGpu -and $img -match '-mineru:|-paddlex:') { continue }
  $safe = ($img -replace '[/:]','_') + '.tar'
  $sub = if ($img -match '-mineru:|-paddlex:') { 'gpu' } else { 'core' }
  $dest = "$staging\images\$sub\$safe"
  if (-not (Test-Path $dest)) { docker save -o $dest $img }
  $saved += @{ tag=$img; file="images/$sub/$safe" }
  Write-Host "[save] $img → $sub/$safe"
}

# ── 组装包目录 ──
$ErrorActionPreference = 'Continue'
$version = (git -C $Root describe --tags --abbrev=0 2>$null) -replace '^v',''
$ErrorActionPreference = 'Stop'
if (-not $version) { $version = (Select-String -Path "$Root\web\package.json" -Pattern '"version":\s*"([^"]+)"').Matches[0].Groups[1].Value }
$pkgName = "pisuan-offline-$version-$(Get-Date -Format yyyyMMdd)"
$pkg = Join-Path $OutDir $pkgName
New-Item -ItemType Directory -Force -Path $pkg | Out-Null
Copy-Item "$Root\deploy\offline\*" $pkg -Recurse -Force                      # 模板/手册/脚本/assets 全量随包
Copy-Item "$Root\docker-compose.prod.yml","$Root\docker-compose.langfuse.yml" $pkg
Copy-Item "$Root\docker\sandbox_provisioner\sandbox.env" "$pkg\docker\sandbox_provisioner\" -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$pkg\docker\sandbox_provisioner","$pkg\docs","$pkg\payload\docker","$pkg\payload\nvidia","$pkg\payload\models","$pkg\state" | Out-Null

# payload（Docker 引擎 / NVIDIA / bge-m3）来自工作区 pisuan-offline-work\payload（Task 6 下载落位）
$payloadSrc = Join-Path $work "payload"
if (Test-Path $payloadSrc) {
  Copy-Item "$payloadSrc\*" "$pkg\payload\" -Recurse -Force
  Write-Host "[payload] 已收入包内（$payloadSrc）"
} else {
  Write-Warning "[payload] $payloadSrc 不存在——包内 payload 为空，Docker 引擎/模型离线安装不可用"
}

# 镜像搬入包（同日重跑幂等：包内旧 images 先清除再搬入——Move-Item -Force 对已存在目录不合并会报错）
if (Test-Path "$pkg\images") { Remove-Item "$pkg\images" -Recurse -Force }
Move-Item "$staging\images" "$pkg\images" -Force

# manifest（txt 供 bash 比对；json 留 digest 基线扩展位）
# LF 行尾写入（Windows Set-Content 默认 CRLF；load-images.sh 消费端另有 \r 剥离守护，双保险——t4 质量审查 I6 同类）
$tags = ($saved | ForEach-Object { $_.tag } | Sort-Object) -join "`n"
[IO.File]::WriteAllText("$pkg\manifest.txt", "$tags`n")
$saved | ConvertTo-Json -Depth 3 | Set-Content "$pkg\manifest.json" -Encoding utf8
Set-Content "$pkg\VERSION" -Value $version -Encoding ascii -NoNewline   # 无 EOL：防 cat VERSION 把 \r 带进 PISUAN_VERSION（离线 tag 失配即死）

# 预置状态（refs-repo/gitea-data，来自本机运行栈 volumes）
$volSrc = Join-Path $Root "docker\volumes\pisuan"
foreach ($d in 'refs-repo','gitea-data') {
  $src = Join-Path $volSrc $d
  if (Test-Path $src) { Copy-Item $src "$pkg\state\pisuan\$d" -Recurse -Force; Write-Host "[state] $d 已收入包" }
  else { Write-Warning "[state] $volSrc\$d 不存在——refs/gitea 预置缺失，部署后需手工补" }
}

# ── tar.gz + sha256 ──
if (-not $SkipPackage) {
  $tgz = Join-Path $OutDir "$pkgName.tar.gz"
  if (Test-Path $tgz) { Remove-Item $tgz -Force }
  tar -czf $tgz -C $OutDir $pkgName
  $hash = (Get-FileHash $tgz -Algorithm SHA256).Hash.ToLower()
  [IO.File]::WriteAllText("$OutDir\$pkgName.sha256.txt", "$hash  $pkgName.tar.gz`n")   # LF 行尾：客户侧 sha256sum -c 对行尾 \r 敏感
}
$size = [math]::Round((Get-ChildItem $pkg -Recurse | Measure-Object Length -Sum).Sum/1GB,1)
$savedN = ($saved | Measure-Object).Count
Write-Host "`n✅ 包完成: $pkg ($size GB, $savedN 镜像)"
if (-not $SkipPackage) { Write-Host "   tar.gz + sha256 在 $OutDir" }
