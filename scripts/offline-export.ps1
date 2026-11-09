#Requires -Version 5.1
<#
.SYNOPSIS  Yuxi 离线部署包导出（在 pisuan-localized 树执行）
.EXAMPLE  .\scripts\offline-export.ps1 -OutDir E:\yuxi-pkg-work
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

# ── 空间预检（SkipPackage 只做 staging 刷新：tar 复用不重写、快照逐目录先删后拷，增量远小于整包；55G 线是打包模式的 2× 包体积同盘余量）──
$drive = (Get-PSDrive ($OutDir.Substring(0,1))).Free/1GB
$floor = if ($SkipPackage) { 20 } else { 55 }
if ($drive -lt $floor) { throw "工作区盘 $($OutDir[0]) 仅剩 $([int]$drive)G，需 ≥${floor}G（staging 包目录 + tar.gz 同盘约 2×包体积；现包体约 25-30G）" }
$cFree = (Get-PSDrive C).Free/1GB
if (-not $NoBuild -and $cFree -lt 20) { throw "C 盘仅剩 $([int]$cFree)G，构建需 ≥20G" }

# ── 版本与镜像名钉定（终审 C1：现场 install.sh 固定写 COMPOSE_PROJECT_NAME=yuxi-prod
# 与 YUXI_VERSION=$(cat VERSION)，compose 镜像字段按二者插值；导出侧必须用进程环境
# 钉成同名（进程 env 优先于 --env-file），否则 save 的镜像名随导出机漂移，现场 up 必失败）
$ErrorActionPreference = 'Continue'
$version = (git -C $Root describe --tags --abbrev=0 2>$null) -replace '^v',''
$ErrorActionPreference = 'Stop'
if (-not $version) { $version = (Select-String -Path "$Root\web\package.json" -Pattern '"version":\s*"([^"]+)"').Matches[0].Groups[1].Value }
$env:COMPOSE_PROJECT_NAME = 'yuxi-prod'
$env:YUXI_VERSION = $version

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
# PS5.1 坑③：Get-Content 不带 -Encoding 时按 ANSI/GBK 解码 UTF-8 无 BOM 文件——中文注释行
# 末字节恰为 GBK 双字节前导字节时会吞掉换行符，把下一行镜像名合并进注释行一起被
# StartsWith('#') 滤掉（2026-11-09 实测：langfuse/langfuse:4 因此八轮导出全部漏 save）。
# 读仓库内含中文注释的资产文件一律显式 -Encoding UTF8。
$images += Get-Content "$Root\deploy\offline\assets\extra-images.txt" -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') }
$images = $images | Select-Object -Unique

# 钉定断言：必须出现 yuxi-prod-api:$version，且无 yuxi- 漂移前缀（外置镜像如 postgres:16 不受影响）
if (-not ($images -contains "yuxi-prod-api:$version") -or @($images | Where-Object { $_ -match '^yuxi-(?!prod-)' }).Count -gt 0) {
  throw "镜像名钉定断言失败：期望含 yuxi-prod-api:$version 且无 yuxi- 漂移前缀；实际: $($images -join ', ')"
}

# ── gitea retag 为官方名（必须在缺失核对之前，否则核对先 throw）──
# PS5.1 两个坑（19041 实测）：①2>$null 在 EAP=Stop 下原生命令写 stderr 即 NativeCommandError 终止——先降级；
# ②不能用 [bool](inspect 2>$null) 判存在——stderr ErrorRecord 泄漏进成功流，缺失镜像也被判真，
#   导致补拉分支被跳过、缺失核对漏报（2026-11-09 导出实测翻车）。存在性判定一律用 $LASTEXITCODE。
$ErrorActionPreference = 'Continue'
docker image inspect 'gitea/gitea:1.24' 2>$null | Out-Null
$giteaExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = 'Stop'
if ($images -contains 'gitea/gitea:1.24' -and -not $giteaExists) {
  docker pull docker.m.daocloud.io/gitea/gitea:1.24
  docker tag docker.m.daocloud.io/gitea/gitea:1.24 gitea/gitea:1.24
  if ($LASTEXITCODE -ne 0) { throw "gitea 镜像拉取/retag 失败（退出码 $LASTEXITCODE）" }
}

# ── 缺失镜像核对（save 前把关；存在性判定用 $LASTEXITCODE，同上坑②）──
$ErrorActionPreference = 'Continue'
$missing = @($images | Where-Object { docker image inspect $_ 2>$null | Out-Null; $LASTEXITCODE -ne 0 })
$ErrorActionPreference = 'Stop'
if ($missing.Count -gt 0) { throw "本地缺镜像（先 docker pull 或去掉 -NoBuild）: $($missing -join ', ')" }

# ── 结构验证（inspect 失败即缺失/损坏，显式报错而非空架构混过）──
$ErrorActionPreference = 'Continue'
foreach ($img in $images) {
  $arch = (docker image inspect $img --format '{{.Architecture}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { throw "本地缺镜像或 inspect 失败: $img" }
  if ($arch -ne 'amd64') { throw "$img 架构为 $arch，期望 amd64" }
}
$ErrorActionPreference = 'Stop'
$apiImage = $images | Where-Object { $_ -match '-api:' } | Select-Object -First 1
docker run --rm --entrypoint ls $apiImage /app/scripts /usr/local/bin/yuxi-entrypoint >$null
if ($LASTEXITCODE -ne 0) { throw "api 镜像内 /app/scripts 抽查失败（Task 2 的 COPY 未生效？）" }
Write-Host "[verify] 结构验证通过（amd64 + api 镜像 scripts 烘焙在位）"

# ── save 到工作区（yuxi-offline-work\staging；payload 同层）──
$work = Join-Path $OutDir "yuxi-offline-work"
$staging = Join-Path $work "staging"
New-Item -ItemType Directory -Force -Path "$staging\images\core" | Out-Null
$saved = @()
foreach ($img in $images) {
  $safe = ($img -replace '[/:]','_') + '.tar'
  $dest = "$staging\images\core\$safe"
  if ((Test-Path $dest) -and ((Get-Item $dest).Length -gt 0)) {
    Write-Host "[save] 复用已有 $safe"
  } else {
    docker save -o $dest $img
    if ($LASTEXITCODE -ne 0) { throw "docker save 失败（退出码 $LASTEXITCODE）：$img → $safe——磁盘满或镜像损坏，清理后重跑" }
  }
  $saved += @{ tag=$img; file="images/core/$safe" }
  Write-Host "[save] $img → core/$safe"
}

# ── 组装包目录 ──
$pkgName = "yuxi-offline-$version-$(Get-Date -Format yyyyMMdd)"
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
  # M2 终审修补：GPU OCR 服务已剥离，悬空默认值改空——客户切 mineru/paddlex 引擎时
  # 经设置 UI 或 .env.prod 显式配置，而非连向不存在的内置服务名
  if ($line -match '^  MINERU_API_URI:') { $stripped += '  MINERU_API_URI: ${MINERU_API_URI:-}   # 客户自有 MinerU 服务地址（设置 UI 或 .env.prod 配置；离线包无内置 mineru 服务）'; continue }
  if ($line -match '^  PADDLEX_URI:') { $stripped += '  PADDLEX_URI: ${PADDLEX_URI:-}   # 客户自有 PaddleOCR 服务地址（设置 UI 或 .env.prod 配置；离线包无内置 paddlex 服务）'; continue }
  $stripped += $line
}
if (@($stripped -match '^  (mineru-api|paddlex):').Count -gt 0) { throw "打包版 compose 剥离失败：仍含 mineru-api/paddlex 服务块" }
if (@($stripped -match '^networks:').Count -eq 0) { throw "打包版 compose 剥离失败：networks: 顶层键丢失" }
if (@($stripped -match '^  api:').Count -eq 0) { throw "打包版 compose 剥离失败：api 服务键丢失" }
[IO.File]::WriteAllLines("$pkg\docker-compose.prod.yml", $stripped)   # UTF-8 无 BOM；compose 对 CRLF/LF 均可解析
New-Item -ItemType Directory -Force -Path "$pkg\docker\sandbox_provisioner","$pkg\docs","$pkg\payload\docker","$pkg\state" | Out-Null
Copy-Item "$Root\docker\sandbox_provisioner\sandbox.env" "$pkg\docker\sandbox_provisioner\sandbox.env" -Force

# payload（Docker 引擎静态包 / compose 插件）来自导出工作区 yuxi-offline-work\payload
# （按包内 payload/README.md 清单下载落位）。缺失即拒绝导出：2026-11-09 round 8 实测教训——
# WARNING 不阻塞，带空 payload 出包，无预装 Docker 的客户现场 install-docker.sh 无料可装。
$payloadSrc = Join-Path $work "payload"
$payloadDocker = Join-Path $payloadSrc "docker"
$tgz = if (Test-Path $payloadDocker) { @(Get-ChildItem $payloadDocker -Filter 'docker-*.tgz') } else { @() }
if ($tgz.Count -eq 0 -or -not (Test-Path "$payloadDocker\docker-compose-linux-x86_64")) {
  throw "payload 缺失：$payloadDocker 下需有 docker-*.tgz 与 docker-compose-linux-x86_64（按包内 payload/README.md 清单下载落位）——payload 是交付内容，缺失即拒绝导出"
}
Copy-Item "$payloadSrc\*" "$pkg\payload\" -Recurse -Force
Write-Host "[payload] 已收入包内（$payloadSrc）"

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
Set-Content "$pkg\VERSION" -Value $version -Encoding ascii -NoNewline   # 无 EOL：防 cat VERSION 把 \r 带进 YUXI_VERSION（离线 tag 失配即死）

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
      if ($n -match '^([a-z])/') { $n = $n.Substring(0,1).ToUpper() + ':' + $n.Substring(1) }
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
  if (-not (Test-Path $Src)) { throw "数据卷缺失：$Src——数据快照是本包交付内容，缺失即拒绝导出（确认本机运行栈 docker\volumes 在位）" }
  if (Test-Path $Dst) { Remove-Item $Dst -Recurse -Force }   # 同日重跑幂等
  # robocopy /MT 多线程拷贝：快照是万级小文件（如 milvus\minio 5.3GB/1 万文件），
  # Copy-Item 单线程在本机实测仅 ~0.5MB/s（系统扫描服务放大逐文件开销），robocopy 快 10-50 倍。
  # 退出码 0-7 均为成功（位标志：有跳过/多出文件也算），≥8 才是真失败。
  robocopy $Src $Dst /E /MT:16 /R:2 /W:2 /NFL /NDL /NP /NJH | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "快照拷贝失败（robocopy 退出码 $LASTEXITCODE）：$Src → $Dst" }
  # PS5.1：-Recurse 结果混入 DirectoryInfo（无 Length）或为空集（空子卷如 milvus\minio_config）时
  # Measure-Object Length 直接抛错——用 -File 过滤并回退 0（空子卷合法，同 L209 警告不阻塞语义）
  $files = @(Get-ChildItem $Dst -Recurse -File)
  $gb = if ($files.Count -gt 0) { [math]::Round(($files | Measure-Object Length -Sum).Sum/1GB, 1) } else { 0 }
  Write-Host "[state] $Dst ← $Src（$gb GB）"
}
# 整树：yuxi（知识库文件库/threads/refs-repo/gitea-data/eia-library 等）、postgresql、neo4j\data
# ——缺失即拒绝导出（数据快照是裁定交付物，不完整的包不出手）
foreach ($pair in @(
  @{ src = "$volRoot\yuxi";     dst = "$stateDst\yuxi" },
  @{ src = "$volRoot\postgresql"; dst = "$stateDst\postgresql" },
  @{ src = "$volRoot\neo4j\data"; dst = "$stateDst\neo4j\data" }
)) { Copy-Snapshot $pair.src $pair.dst }   # PS5.1 实测：Copy-Item -Recurse -Force 会自建中间父目录（state\neo4j 无需预建）
# 子目录：milvus 取 milvus/etcd/minio/minio_config（logs 不进包；子目录缺失=警告，不阻塞导出）；
# redis 不拷——现场从空卷起，避免陈旧 broker 队列重放
foreach ($pair in @(
  @{ src = "$volRoot\milvus"; dst = "$stateDst\milvus"; subs = @('milvus','etcd','minio','minio_config') }
)) {
  if (-not (Test-Path $pair.src)) { throw "数据卷缺失：$($pair.src)——数据快照是本包交付内容，缺失即拒绝导出（确认本机运行栈 docker\volumes 在位）" }
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
