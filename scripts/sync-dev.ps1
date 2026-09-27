# sync-dev.ps1 — 开发期快速同步：pisuan 工作树 → pisuan-localized 运行栈
#
# 解决的问题：运行栈容器 bind-mount 的是 pisuan-localized 树，日常在 pisuan 目录改代码后
# 需要经历「提交 → push → fetch/reset → 改名」长链路才能热重载。本脚本跳过 git 提交流程，
# 把工作树改动（含未提交内容）按容器挂载清单直接落到 localized 并再生改名层，秒级生效。
#
# 用法：
#   .\scripts\sync-dev.ps1            # 同步（含未提交改动）到运行栈，热重载即时生效
#   .\scripts\sync-dev.ps1 -Revert    # 还原 localized 到镜像 tip（跑官方链 sync-upstream 前建议先执行）
#
# 机制：localized 以 detached HEAD 挂到 origin/pisuan-custom（yuxi 命名基线，改名脚本的合法
# 输入形态），覆盖拷贝工作树改动后整树再生改名层。pisuan-localized 分支引用全程不被触碰。
#
# 边界（务必知悉）：
#   1. 只同步容器挂载的代码路径；docs/packages 等非挂载路径不随 dev 同步更新；
#   2. 不搬运 backend/uv.lock（锁文件必须由 uv lock 机生，手搬即损坏）；依赖变更后需跑
#      官方链 scripts/sync-upstream.ps1 重生成锁文件，否则镜像重建会失败（热重载不受影响）；
#   3. 「删除文件」不被同步（detach 基线会还原已删文件）——删除类改动请跑官方链；
#   4. 不做任何 git 提交/推送；推送上 GitHub 由官方镜像链负责；
#   5. dev 同步后 localized 处于 detached + 工作树差异状态，跑官方链前先 -Revert 还原，
#      否则官方链第 5 步的 git switch 可能因脏树失败（仅降级警告，不阻断主流程）。

param(
  [switch]$Revert
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # 避免中文输出在控制台乱码
$sw = [Diagnostics.Stopwatch]::StartNew()

$root = Split-Path -Parent $PSScriptRoot   # C:\workspace\pisuan
$loc  = Join-Path (Split-Path -Parent $root) 'pisuan-localized'

if (-not (Test-Path (Join-Path $loc '.git'))) { throw "未找到 $loc，请确认双目录结构完好" }

# 护栏：localized/.env 必须被 gitignore，否则下面的强制重置会覆盖运行栈专属配置
git -C $loc check-ignore -q .env
if ($LASTEXITCODE -ne 0) { throw "localized/.env 未被 gitignore，强制重置会破坏运行栈配置，中止" }

# 容器挂载清单（见 localized docker-compose.yml：api/worker/web 服务的 bind-mount）
$syncPaths = @(
  'backend/server',
  'backend/package',
  'backend/test',
  'backend/scripts',
  'docker/sandbox_provisioner',
  'web/src',
  'web/test',
  'web/public'
)

if ($Revert) {
  # 还原：回到 pisuan-localized 分支并对齐镜像 tip，丢弃全部 dev 同步差异
  git -C $loc checkout --quiet -f pisuan-localized
  if ($LASTEXITCODE -ne 0) { throw "切回 pisuan-localized 分支失败" }
  git -C $loc reset --quiet --hard github/pisuan-localized
  if ($LASTEXITCODE -ne 0) { throw "对齐 github/pisuan-localized 失败" }
  foreach ($p in $syncPaths) {
    git -C $loc clean --quiet -fd -- $p
    if ($LASTEXITCODE -ne 0) { throw "git clean 失败: $p" }
  }
  Write-Host "✅ localized 已还原到镜像 tip：$(git -C $loc log -1 --format='%h %s')"
  exit 0
}

# ---- 主流程：detach 到 yuxi 命名基线 → 覆盖拷贝 → 整树改名再生 ----

# 1. 更新基线引用（离线时基线稍旧不影响挂载路径内容——它们来自 pisuan 工作树拷贝）
git -C $loc fetch --quiet origin
if ($LASTEXITCODE -ne 0) { Write-Warning "git fetch 失败（离线？），继续用本地 origin/pisuan-custom 旧基线" }

# 2. detached 挂到基线（-f 丢弃上一次 dev 同步的 tracked 差异；分支引用不动）
git -C $loc checkout --quiet --detach --force origin/pisuan-custom
if ($LASTEXITCODE -ne 0) { throw "detach 到 origin/pisuan-custom 失败" }
foreach ($p in $syncPaths) {
  git -C $loc clean --quiet -fd -- $p
  if ($LASTEXITCODE -ne 0) { throw "git clean 失败: $p" }
}

# 3. 按挂载清单拷贝工作树内容（排除缓存与虚拟环境目录）
$excludeDirs = @('__pycache__', '.pytest_cache', '.venv', 'node_modules', '.vite')
foreach ($p in $syncPaths) {
  $src = Join-Path $root $p
  $dst = Join-Path $loc $p
  if (-not (Test-Path $src)) { Write-Warning "源不存在，跳过: $p"; continue }
  $absExclude = $excludeDirs | ForEach-Object { Join-Path $src $_ }
  robocopy $src $dst /E /XD $absExclude /R:2 /W:2 /NFL /NDL /NJH /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy 失败（exit $LASTEXITCODE）: $p" }
}
# 单文件用 robocopy 文件模式（内容未变则跳过，避免 mtime 变动触发 vite 无谓重启）
$copyFiles = @('web/index.html', 'web/vite.config.js', 'backend/pyproject.toml')
foreach ($p in $copyFiles) {
  $srcDir = Join-Path $root (Split-Path $p)
  $dstDir = Join-Path $loc (Split-Path $p)
  $name = Split-Path -Leaf $p
  if (-not (Test-Path (Join-Path $root $p))) { Write-Warning "源不存在，跳过: $p"; continue }
  robocopy $srcDir $dstDir $name /R:2 /W:2 /NFL /NDL /NJH /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy 失败（exit $LASTEXITCODE）: $p" }
}

# 3.5 新拷贝的文件入索引（不提交）：改名脚本按 git ls-files（tracked）圈定处理范围，
# untracked 新文件会被漏改（yuxi 引用在运行栈成坏引用）；入索引后 -Revert 仍可整树还原
git -C $loc add -A -- (@($syncPaths) + $copyFiles)
if ($LASTEXITCODE -ne 0) { throw "git add 失败" }

# 4. 再生机械改名层（确定性变换；--allow-dirty 放行脚本自身制造的拷贝差异与行尾噪声）
python (Join-Path $root 'scripts/apply_pisuan_rename.py') --apply --allow-dirty --root $loc
if ($LASTEXITCODE -ne 0) { throw "apply_pisuan_rename 失败，localized 处于中间态：重跑本脚本或 -Revert 恢复" }

$sw.Stop()
# 自检基准是镜像 tip（改名层）：pisuan 无未提交改动时差异应为 0；
# （相对 detached HEAD 的 status 会显示整树改名层，~900 项，属预期常态，不作指标）
$dirty = (git -C $loc diff --name-only github/pisuan-localized -- @($syncPaths + $copyFiles) | Measure-Object).Count
Write-Host "✅ dev 同步完成（$([math]::Round($sw.Elapsed.TotalSeconds, 1))s），容器热重载即会生效"
Write-Host "   分支指针未动：pisuan-localized = $(git -C $loc log -1 --format='%h' pisuan-localized)"
Write-Host "   相对镜像 tip 差异 $dirty 个文件（= pisuan 当前未提交改动数，行尾噪声除外）；跑官方链前先 -Revert"
