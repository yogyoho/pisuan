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
# 机制：只把 HEAD 指针 detach 到 origin/pisuan-custom（update-ref，工作树不动），覆盖拷贝
# 工作树改动后再生改名层。rename 规则幂等，对上轮已改名的树零替换不落盘——收敛轮零写入。
# pisuan-localized 分支引用全程不被触碰。
#
# 边界（务必知悉）：
#   1. 只同步容器挂载的代码路径 + 脚本内单文件清单（含部署文件）；docs/packages 等其余路径不随 dev 同步更新；
#   2. 不搬运 backend/uv.lock（锁文件必须由 uv lock 机生，手搬即损坏）；依赖变更后需跑
#      官方链 scripts/sync-upstream.ps1 重生成锁文件，否则镜像重建会失败（热重载不受影响）；
#   3. 「删除文件」不被同步（本地化树会保留旧文件；索引中的对应条目由 git add -A 自动清退）
#      ——删除类改动请跑官方链；
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
  'backend/templates',
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

# ---- 主流程：HEAD 指针 detach 到基线（工作树不动）→ 覆盖拷贝 → 幂等改名再生 ----

# 1. 更新基线引用（离线时基线稍旧不影响挂载路径内容——它们来自 pisuan 工作树拷贝）
git -C $loc fetch --quiet origin
if ($LASTEXITCODE -ne 0) { Write-Warning "git fetch 失败（离线？），继续用本地 origin/pisuan-custom 旧基线" }

# 2. 只挪 HEAD 指针到基线（--no-deref 脱离分支且不触碰 index/工作树）。
#    千万不要用 checkout/reset 重置工作树：基线是 yuxi 命名，重置会把上轮改名层整树
#    打回 yuxi 形态再靠 rename 改回来，每轮全树两次写入（vite 全量重启/容器抖动）。
#    rename 规则幂等（对已是 pisuan 形态的内容零替换不落盘），无需先回到基线内容。
git -C $loc update-ref --no-deref HEAD (git -C $loc rev-parse origin/pisuan-custom)
if ($LASTEXITCODE -ne 0) { throw "HEAD 指到 origin/pisuan-custom 失败" }
foreach ($p in $syncPaths) {
  git -C $loc clean --quiet -fd -- $p
  if ($LASTEXITCODE -ne 0) { throw "git clean 失败: $p" }
}

# 3. 拷贝工作树内容（python walker 单进程：路径翻译 + 内容变换 + 差异比较后才落盘）
#    源树（pisuan 仓库）是 yuxi 命名，本地化树是 pisuan 命名——直接整目录拷贝会与改名层
#    撞名（backend/package/yuxi vs pisuan）。walker 对每个文件：路径组件按 is_rename_dir
#    翻译、文件名与内容按 rewrite_text 变换，变换后与目标一致则不写（收敛轮零 mtime 事件，
#    vite 不重启）。注意：python 代码必须经临时 .py 文件调用——PS 5.1 向原生命令传含双引号
#    的 -c 代码会坏参
# 单文件清单：随挂载代码一起经 walker 传播（同样的内容变换）。部署文件（compose/Dockerfile）
# 也在列——否则部署面改动只能走官方链长链路，dev 栈永远慢一拍（bug-363 教训）
$copyFiles = @('web/index.html', 'web/vite.config.js', 'backend/pyproject.toml', 'docker-compose.yml', 'docker/api.Dockerfile')
$pyFile = Join-Path $env:TEMP 'syncdev_copy.py'
@'
import sys, hashlib
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location("apr", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
src_root, dst_root = Path(sys.argv[2]), Path(sys.argv[3])
EXCLUDE = {"__pycache__", ".pytest_cache", ".venv", "node_modules", ".vite"}
written = 0
for rel in sys.argv[4:]:
    base = src_root / rel
    if not base.exists():
        continue
    files = base.rglob("*") if base.is_dir() else [base]
    for f in files:
        if not f.is_file():
            continue
        rp = f.relative_to(src_root)
        if any(part in EXCLUDE for part in rp.parts):
            continue
        parts = list(rp.parts[:-1])
        for i, comp in enumerate(parts):
            if m.is_rename_dir(comp):
                parts[i] = m.rewrite_text(comp)[0]
        name = m.rewrite_text(rp.parts[-1])[0]
        dst = dst_root.joinpath(*parts, name)
        raw = f.read_bytes()
        try:
            data = m.rewrite_text(raw.decode("utf-8"))[0].encode("utf-8")
        except UnicodeDecodeError:
            data = raw  # 二进制：仅路径翻译
        if dst.exists() and dst.read_bytes() == data:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        written += 1
print(f"walker: {written} files written")
'@ | Set-Content -Path $pyFile -Encoding UTF8
python $pyFile (Join-Path $root 'scripts/apply_pisuan_rename.py') $root $loc (@($syncPaths) + $copyFiles)
$walkerExit = $LASTEXITCODE
Remove-Item $pyFile -Force
if ($walkerExit -ne 0) { throw "拷贝 walker 失败" }

# 3.5 仓库级 add（不提交）：让索引镜像工作树的 pisuan 形态。改名脚本按 git ls-files
# （索引）圈定范围——新拷贝文件不入索引会被漏改；索引若残留 yuxi 命名旧路径，rename
# 会规划目录搬迁并撞上工作树已改名目标而崩溃，仓库级 add 使两者永远一致
git -C $loc add -A
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
Write-Host "   相对镜像 tip 差异 $dirty 个文件（≈ pisuan 当前未提交改动数，行尾噪声除外；官方链再生前 templates/部署文件含滞后基线差异，属过渡期预期）；跑官方链前先 -Revert"
