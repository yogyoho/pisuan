#Requires -Version 5.1
<#
.SYNOPSIS  Pisuan 离线部署包导出（在 pisuan-localized 树执行）
.EXAMPLE  .\scripts\offline-export.ps1 -OutDir E:\pisuan-pkg-work
#>
param(
  [Parameter(Mandatory=$true)][string]$OutDir,       # 外置盘工作区
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
if ($drive -lt 55) { throw "工作区盘 $($OutDir[0]) 仅剩 $([int]$drive)G，需 ≥55G（staging 包目录 + tar.gz 同盘约 2×包体积；现包体约 25-30G）" }
$cFree = (Get-PSDrive C).Free/1GB
if (-not $NoBuild -and $cFree -lt 20) { throw "C 盘仅剩 $([int]$cFree)G，构建需 ≥20G" }

# ── 镜像清单（compose 管理 + 包外附加；GPU OCR 层已全裁，不再带 --profile all）──
$composeArgs = @('compose','--env-file','.env.prod','-f','docker-compose.prod.yml')
if ($NoBuild) {
  $images = @(docker @composeArgs config --images)
  if ($LASTEXITCODE -ne 0) { throw "docker compose config --images 失败（退出码 $LASTEXITCODE）——检查 .env.prod 是否已准备、docker-compose.prod.yml 是否在位" }
} else {
  # PS5.1 实测（5.1.19041）：EAP=Stop 下原生命令 2>&1 首行 stderr 即 NativeCommandError 终止——降级透传构建日志，退出码显式校验
  $ErrorActionPreference = 'Continue'
  docker @composeArgs build 2>&1 | ForEach-Object { Write-Host "[build] $_" }
  $ErrorActionPreference = 'Stop'
  if ($LASTEXITCODE -ne 0) { throw "镜像构建失败（docker build 退出码 $LASTEXITCODE）" }
  $images = @(docker @composeArgs config --images)
  if ($LASTEXITCODE -ne 0) { throw "docker compose config --images 失败（退出码 $LASTEXITCODE）——检查 .env.prod 是否已准备、docker-compose.prod.yml 是否在位" }
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
  if ($LASTEXITCODE -ne 0) { throw "gitea 镜像拉取/retag 失败（退出码 $LASTEXITCODE）" }
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
New-Item -ItemType Directory -Force -Path "$staging\images\core" | Out-Null
$saved = @()
foreach ($img in $images) {
  $safe = ($img -replace '[/:]','_') + '.tar'
  $dest = "$staging\images\core\$safe"
  if (Test-Path $dest) {
    Write-Host "[save] 复用已有 $safe"
  } else {
    docker save -o $dest $img
  }
  $saved += @{ tag=$img; file="images/core/$safe" }
  Write-Host "[save] $img → core/$safe"
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
Copy-Item "$Root\docker-compose.langfuse.yml" $pkg
# 打包版 compose 剥离 GPU OCR 服务块（mineru/paddlex 全裁；仓库原文件不动，只裁打包副本）
$prodLines = Get-Content "$Root\docker-compose.prod.yml" -Encoding UTF8
$stripped = @(); $drop = $false
foreach ($line in $prodLines) {
  if ($line -match '^  (mineru-api|paddlex):') { $drop = $true; continue }
  if ($drop) {
    if ($line -match '^  \S' -or $line -match '^networks:') { $drop = $false }   # 下一个服务键 / 顶层键：停止删除
    else { continue }
  }
  $stripped += $line
}
if (@($stripped -match '^  (mineru-api|paddlex):').Count -gt 0) { throw "打包版 compose 剥离失败：仍含 mineru-api/paddlex 服务块" }
if (@($stripped -match '^networks:').Count -eq 0) { throw "打包版 compose 剥离失败：networks: 顶层键丢失" }
if (@($stripped -match '-api:').Count -eq 0) { throw "打包版 compose 剥离失败：api 服务 image 行丢失" }
[IO.File]::WriteAllLines("$pkg\docker-compose.prod.yml", $stripped)   # UTF-8 无 BOM；compose 对 CRLF/LF 均可解析
New-Item -ItemType Directory -Force -Path "$pkg\docker\sandbox_provisioner","$pkg\docs","$pkg\payload\docker","$pkg\state" | Out-Null
Copy-Item "$Root\docker\sandbox_provisioner\sandbox.env" "$pkg\docker\sandbox_provisioner\sandbox.env" -Force

# payload（Docker 引擎静态包 / compose 插件）来自工作区 pisuan-offline-work\payload（下载脚本落位）
$payloadSrc = Join-Path $work "payload"
if (Test-Path $payloadSrc) {
  Copy-Item "$payloadSrc\*" "$pkg\payload\" -Recurse -Force
  Write-Host "[payload] 已收入包内（$payloadSrc）"
} else {
  Write-Warning "[payload] $payloadSrc 不存在——包内 payload 为空，Docker 引擎/compose 插件离线安装不可用"
}

# 镜像搬入包（同日重跑幂等：包内旧 images 先清除再搬入——Move-Item -Force 对已存在目录不合并会报错）
# 旧版导出可能在工作区留有 images\gpu（mineru/paddlex tar）——全裁后一并清除，防陈旧 GPU 层流入包
if (Test-Path "$staging\images\gpu") { Remove-Item "$staging\images\gpu" -Recurse -Force }
if (Test-Path "$pkg\images") { Remove-Item "$pkg\images" -Recurse -Force }
Move-Item "$staging\images" "$pkg\images" -Force

# manifest（txt 供 bash 比对；json 留 digest 基线扩展位）
# LF 行尾写入（Windows Set-Content 默认 CRLF；load-images.sh 消费端另有 \r 剥离守护，双保险——t4 质量审查 I6 同类）
$tags = ($saved | ForEach-Object { $_.tag } | Sort-Object) -join "`n"
[IO.File]::WriteAllText("$pkg\manifest.txt", "$tags`n")
$saved | ConvertTo-Json -Depth 3 | Set-Content "$pkg\manifest.json" -Encoding utf8
Set-Content "$pkg\VERSION" -Value $version -Encoding ascii -NoNewline   # 无 EOL：防 cat VERSION 把 \r 带进 PISUAN_VERSION（离线 tag 失配即死）

# ── 预置状态快照（数据卷原样进包；2026-11-08 裁定：含开发期数据，不脱敏）──
# 停栈守卫：运行栈写入中拷贝会得到不一致快照，先实测有无容器挂载 docker\volumes 下的路径
$ErrorActionPreference = 'Continue'
$running = @(docker ps --format '{{.Names}}')
$psFailed = ($LASTEXITCODE -ne 0)
$mountHit = $null
if (-not $psFailed) {
  # Mounts.Source 在 Docker Desktop(WSL2) 下可能呈 Windows 形态（C:/...）或 /run/desktop/mnt/host/c/...，
  # 统一归一成 C:/... 形态后再与仓库 volumes 根比对（以本机实测为准，勿臆测）
  $volRootN = ($Root + '\docker\volumes').ToLower().Replace('\','/')
  foreach ($c in $running) {
    $srcs = @(docker inspect $c --format '{{range .Mounts}}{{println .Source}}{{end}}' | Where-Object { $_ -ne '' })
    foreach ($s in $srcs) {
      $n = $s.ToLower().Replace('\','/') -replace '^/run/desktop/mnt/host/',''
      if ($n -match '^/([a-z])/') { $n = $n.Substring(1,1).ToUpper() + ':' + $n.Substring(2) }
      if ($n -like "$volRootN*") { $mountHit = "容器 $c 挂载 $s"; break }
    }
    if ($mountHit) { break }
  }
}
$ErrorActionPreference = 'Stop'
if ($psFailed) { throw "docker ps 失败（退出码 $LASTEXITCODE）——无法确认数据卷静态，中止导出" }
if ($mountHit) { throw "数据卷正被运行栈写入（$mountHit）——先在仓库根执行 docker compose down（保留卷）再导出" }

$volRoot = Join-Path $Root 'docker\volumes'
$stateDst = "$pkg\state"
function Copy-Snapshot([string]$Src, [string]$Dst) {
  if (-not (Test-Path $Src)) { throw "数据卷缺失：$Src——数据快照是本包交付内容，整卷缺失即中止（确认本机运行栈 docker\volumes 在位）" }
  if (Test-Path $Dst) { Remove-Item $Dst -Recurse -Force }   # 同日重跑幂等
  Copy-Item $Src $Dst -Recurse -Force
  $gb = [math]::Round((Get-ChildItem $Dst -Recurse | Measure-Object Length -Sum).Sum/1GB, 1)
  Write-Host "[state] $Dst ← $Src（$gb GB）"
}
# 整树：pisuan（知识库文件库/threads/refs-repo/gitea-data/eia-library 等）、postgresql
foreach ($pair in @(
  @{ src = "$volRoot\pisuan";     dst = "$stateDst\pisuan" },
  @{ src = "$volRoot\postgresql"; dst = "$stateDst\postgresql" }
)) { Copy-Snapshot $pair.src $pair.dst }
# 子目录：milvus 取 milvus/etcd/minio/minio_config（logs 不进包）；neo4j 只取 data（logs 不进包）；
# redis 不拷——现场从空卷起，避免陈旧 broker 队列重放
foreach ($pair in @(
  @{ src = "$volRoot\milvus"; dst = "$stateDst\milvus"; subs = @('milvus','etcd','minio','minio_config') },
  @{ src = "$volRoot\neo4j";  dst = "$stateDst\neo4j";  subs = @('data') }
)) {
  if (-not (Test-Path $pair.src)) { throw "数据卷缺失：$($pair.src)——数据快照是本包交付内容，整卷缺失即中止（确认本机运行栈 docker\volumes 在位）" }
  if (Test-Path $pair.dst) { Remove-Item $pair.dst -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $pair.dst | Out-Null
  foreach ($s in $pair.subs) {
    if (Test-Path "$($pair.src)\$s") { Copy-Snapshot "$($pair.src)\$s" "$($pair.dst)\$s" }
    else { Write-Warning "[state] $($pair.src)\$s 不存在——该子卷预置缺失，部署后该组件从空卷初始化" }
  }
}

# ── tar.gz + sha256 ──
if (-not $SkipPackage) {
  $tgz = Join-Path $OutDir "$pkgName.tar.gz"
  if (Test-Path $tgz) { Remove-Item $tgz -Force }
  tar -czf $tgz -C $OutDir $pkgName
  if ($LASTEXITCODE -ne 0) { throw "tar 打包失败（退出码 $LASTEXITCODE）——常见原因：外置盘空间不足（包目录与 tgz 同盘约需 2×包体积）" }
  $hash = (Get-FileHash $tgz -Algorithm SHA256).Hash.ToLower()
  [IO.File]::WriteAllText("$OutDir\$pkgName.sha256.txt", "$hash  $pkgName.tar.gz`n")   # LF 行尾：客户侧 sha256sum -c 对行尾 \r 敏感
}
$size = [math]::Round((Get-ChildItem $pkg -Recurse | Measure-Object Length -Sum).Sum/1GB,1)
$savedN = ($saved | Measure-Object).Count
Write-Host "`n✅ 包完成: $pkg ($size GB, $savedN 镜像)"
if (-not $SkipPackage) { Write-Host "   tar.gz + sha256 在 $OutDir" }
