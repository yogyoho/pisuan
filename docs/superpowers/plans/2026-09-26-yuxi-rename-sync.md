# yuxi→pisuan 全量本地化改名 + 上游同步流程改造 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `pisuan-localized` 分支（= `pisuan-custom` + 脚本生成的机械改名提交），使全量 yuxi→pisuan 本地化与上游差分同步两全。

**Architecture:** 三分支（main 纯净镜像 / pisuan-custom 语义定制 / pisuan-localized 机械改名衍生物）+ 本地双目录（`C:\workspace\pisuan` 零打扰、`C:\workspace\pisuan-localized` 承载改造）。改名由确定性幂等脚本生成唯一提交，位于分支顶端，每次同步后丢弃重建。

**Tech Stack:** Python 3.13+（宿主 3.14 可跑，stdlib-only 脚本）、git、docker compose、uv 0.11+（宿主已装）、PowerShell/bash。

**设计文档:** `docs/superpowers/specs/2026-09-26-yuxi-rename-sync-design.md`

**已核实的关键事实**（执行者勿重新普查）：
- 跟踪文件中的 yuxi 目录共 2 个：`backend/package/yuxi/`（325 文件）、`packages/yuxi-cli/`（Makefile audit-dependencies 引用它）
- 打包坐标：`backend/pyproject.toml`（name=`yuxi-workspace`，members `["yuxi"]`，`yuxi = { path = "package" }`）、`backend/package/pyproject.toml`（name=`yuxi`，setuptools packages.find）
- `SCHEMA_VERSION_TABLE = "yuxi_schema_migrations"` 单点在 `backend/package/yuxi/storage/postgres/manager.py:35`
- compose 端口经 `YUXI_*_PORT` 发布（默认值两栈相同，并存必须改端口）；`.env` 无 `COMPOSE_PROJECT_NAME`（项目名=目录名，两栈容器名天然不冲突）；compose 无 override 文件
- `.env` 中 YUXI 变量：`YUXI_INSTANCE_ID`（未跟踪文件，归 Task 5 手工处理）
- web/src 含 yuxi 行 29 处；`web/src/apis/base.js` 有 `'http://yuxi.local'`
- scripts/ 测试约定：stdlib `unittest`，仓库根执行 `python -m unittest scripts.test_xxx`（见 Makefile:65 `verify-trust`）
- 宿主工具链：Python 3.14.4（无 pytest，用 unittest）、uv 0.11.21、git bash
- 当前运行容器：`pisuan-api-1` 等（项目名 pisuan），测试用 `docker exec pisuan-api-1 pytest ...` 的方式在 localized 栈中对应为 `pisuan-localized-api-1`
- 三段测试基线：unit 2530 passed / integration 141 passed 205 skipped 3 error（存量 FK，非阻塞）/ e2e passed

**约定**：bash 命令在 git bash 中执行；涉及 `C:\workspace\pisuan-localized` 的命令用 `/c/workspace/pisuan-localized`。所有 git 提交信息以 `Co-Authored-By: Claude Code <noreply@anthropic.com>` 结尾。

---

### Task 1: 改名脚本（TDD：先测后码）

**Files:**
- Create: `scripts/test_apply_pisuan_rename.py`
- Create: `scripts/apply_pisuan_rename.py`

- [ ] **Step 1: 写失败测试**

创建 `scripts/test_apply_pisuan_rename.py`（完整内容）：

```python
"""scripts/apply_pisuan_rename.py 的单元测试。

运行（仓库根执行）: python -m unittest scripts.test_apply_pisuan_rename -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.apply_pisuan_rename import rewrite_text

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "apply_pisuan_rename.py"


class RewriteTextTest(unittest.TestCase):
    """纯函数测试: 替换规则本体。"""

    def test_structural_renames(self):
        text, n = rewrite_text("from yuxi.storage import db\nimport yuxi.models\nYUXI_API_PORT = 1\n")
        self.assertEqual(
            text, "from pisuan.storage import db\nimport pisuan.models\nPISUAN_API_PORT = 1\n"
        )
        self.assertEqual(n, 3)

    def test_bare_and_brand(self):
        text, _ = rewrite_text('X = "yuxi"\n# Yuxi 是一个知识库平台\n')
        self.assertEqual(text, 'X = "pisuan"\n# Pisuan 是一个知识库平台\n')

    def test_url_and_data_path(self):
        text, _ = rewrite_text("const u = new URL(url, 'http://yuxi.local')\nv: ./docker/volumes/yuxi\n")
        self.assertEqual(
            text, "const u = new URL(url, 'http://pisuan.local')\nv: ./docker/volumes/pisuan\n"
        )

    def test_protected_line(self):
        """含上游指称的行: 裸词不动，结构化标识符照改。"""
        text, _ = rewrite_text(
            "fork 自 xerrors/Yuxi，同步上游 Yuxi 项目\n路径: backend/package/yuxi/config\n"
        )
        self.assertEqual(
            text, "fork 自 xerrors/Yuxi，同步上游 Yuxi 项目\n路径: backend/package/pisuan/config\n"
        )

    def test_idempotent(self):
        once, _ = rewrite_text("from yuxi.a import b  # yuxi\nsee http://yuxi.local/api\n")
        twice, n = rewrite_text(once)
        self.assertEqual(once, twice)
        self.assertEqual(n, 0)


class EndToEndTest(unittest.TestCase):
    """临时 git 仓库端到端: 目录 mv + 内容重写 + 幂等。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.root = root
        (root / "backend/package/yuxi").mkdir(parents=True)
        (root / "packages/yuxi-cli").mkdir(parents=True)
        (root / "docs/superpowers/specs").mkdir(parents=True)
        (root / "backend/package/yuxi/core.py").write_text(
            "from yuxi.storage import db\n# 上游 Yuxi 项目\n", encoding="utf-8"
        )
        (root / "packages/yuxi-cli/main.py").write_text("YUXI_API_PORT = 1\n", encoding="utf-8")
        (root / "docs/guide.md").write_text(
            "fork 自 xerrors/Yuxi\n见 backend/package/yuxi/README\n", encoding="utf-8"
        )
        (root / "docs/superpowers/specs/design.md").write_text("yuxi 保持原貌\n", encoding="utf-8")
        (root / "backend/uv.lock").write_text('name = "yuxi"\n', encoding="utf-8")
        for args in (
            ["init", "-q"],
            ["add", "-A"],
            ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        ):
            subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *extra: str) -> str:
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *extra],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return r.stdout

    def test_apply_renames_and_idempotent(self):
        out = self._run("--apply")
        self.assertIn("backend/package/yuxi -> backend/package/pisuan", out)
        self.assertIn("packages/yuxi-cli -> packages/pisuan-cli", out)
        self.assertEqual(
            (self.root / "backend/package/pisuan/core.py").read_text(encoding="utf-8"),
            "from pisuan.storage import db\n# 上游 Yuxi 项目\n",
        )
        self.assertEqual(
            (self.root / "backend/uv.lock").read_text(encoding="utf-8"),
            'name = "yuxi"\n',  # uv.lock 由 uv lock 重新生成, 脚本跳过
        )
        self.assertIn(
            "yuxi 保持原貌",
            (self.root / "docs/superpowers/specs/design.md").read_text(encoding="utf-8"),
        )
        # 幂等: 复跑无任何新变化
        out2 = self._run("--apply")
        self.assertIn("目录 mv 实际执行: 0", out2)
        self.assertIn("内容改写文件: 0", out2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /c/workspace/pisuan && python -m unittest scripts.test_apply_pisuan_rename -v
```
预期：`ImportError: cannot import name 'rewrite_text'`（模块尚不存在）。

- [ ] **Step 3: 实现脚本**

创建 `scripts/apply_pisuan_rename.py`（完整内容）：

```python
#!/usr/bin/env python3
"""apply_pisuan_rename.py — 生成 yuxi→pisuan 机械改名层。

设计文档: docs/superpowers/specs/2026-09-26-yuxi-rename-sync-design.md

原则:
- 确定性: 相同树状态永远产出相同结果
- 幂等: 重复执行不再产生变化
- 显式模式表: 结构化标识符替换 + 带行保护的裸词替换, 不做盲目全局 sed
- 只触碰 git 跟踪文件; 运行时数据/未跟踪文件归切换日手册处理

用法:
  python scripts/apply_pisuan_rename.py           # dry-run: 只打印计划与残余报告
  python scripts/apply_pisuan_rename.py --apply   # 实际执行 git mv + 内容重写
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# 目录整体跳过（按路径组件名匹配）: .wolf 是会话元数据; docs/superpowers 是设计/计划
# 文档本身, 其中对 yuxi 的引用是对改名对象的描述而非待改标识符
SKIP_DIRS = {".git", ".wolf", "node_modules", "superpowers", ".venv"}
SKIP_FILES = {"uv.lock"}  # 由 uv lock 重新生成, 不做文本替换
SKIP_SUFFIXES = (".egg-info",)  # 路径组件以此结尾即跳过（构建产物）

# 结构化替换: 带分隔符上下文的标识符（路径/导入/环境变量）, 任何行都改。
# 否则代码跑不起来, 不受"上游指称"行保护约束
STRUCTURAL_RULES = [
    (r"YUXI_(?=[A-Z0-9_])", "PISUAN_"),  # 环境变量名 YUXI_API_PORT 等
    (r"(?<![\w.\-])yuxi(?=[./_\-])", "pisuan"),  # yuxi. yuxi/ yuxi_ yuxi-
]

# 裸词替换: 独立出现的 yuxi / Yuxi（导入尾词、引号内、品牌文案、路径末段）。
# 注意 lookbehind 不含 "/" —— 否则 volumes/yuxi 这类"分隔符+行尾"的路径末段会漏改。
# 含上游指称关键词的行整体跳过 —— 那是对上游项目的描述, 属保留清单
BARE_RULES = [
    (r"(?<![\w._\-])yuxi(?![\w./_\-])", "pisuan"),
    (r"(?<![\w._\-])Yuxi(?![\w./_\-])", "Pisuan"),
]
PROTECTED_LINE = ("xerrors", "上游", "upstream")

# 目录改名: 基名恰为 yuxi 或以 yuxi- 开头的跟踪目录
# （已知命中: backend/package/yuxi、packages/yuxi-cli）
DIR_EXACT = "yuxi"
DIR_PREFIX = "yuxi-"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def tracked_files(root: Path) -> list[Path]:
    out = git(root, "ls-files", "-z")
    paths = []
    for chunk in out.split("\0"):
        if not chunk:
            continue
        parts = Path(chunk).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if any(part in SKIP_FILES for part in parts):
            continue
        if any(part.endswith(SKIP_SUFFIXES) for part in parts):
            continue
        paths.append(root / chunk)
    return paths


def plan_dir_moves(files: list[Path], root: Path) -> list[tuple[Path, Path]]:
    """收集需要改名的目录（每个文件命中最顶层组件即止）。"""
    planned: dict[Path, Path] = {}
    for p in files:
        rel = p.relative_to(root)
        for i, part in enumerate(rel.parts[:-1]):
            if part == DIR_EXACT or part.startswith(DIR_PREFIX):
                src = root / Path(*rel.parts[: i + 1])
                planned.setdefault(src, src.parent / part.replace("yuxi", "pisuan", 1))
                break
    return sorted(planned.items())


def apply_dir_moves(root: Path, moves: list[tuple[Path, Path]]) -> list[tuple[str, str]]:
    done = []
    for src, dst in moves:
        if dst.exists():
            continue  # 幂等: 已改名
        git(root, "mv", "--", str(src.relative_to(root)), str(dst.relative_to(root)))
        done.append((str(src.relative_to(root)), str(dst.relative_to(root))))
    return done


def rewrite_text(text: str) -> tuple[str, int]:
    """应用全部替换规则, 返回 (新文本, 替换次数)。字节级保真（不动行尾）。"""
    count = 0
    for pattern, repl in STRUCTURAL_RULES:
        text, n = re.subn(pattern, repl, text)
        count += n
    lines = []
    for line in text.splitlines(keepends=True):
        if any(k in line for k in PROTECTED_LINE):
            lines.append(line)
            continue
        for pattern, repl in BARE_RULES:
            line, n = re.subn(pattern, repl, line)
            count += n
        lines.append(line)
    return "".join(lines), count


def residue_report(root: Path, files: list[Path]) -> list[str]:
    """改名后仍含 yuxi 字样的位置（应全部落在保留清单内）。"""
    hits = []
    for p in files:
        try:
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # 二进制文件
        for lineno, line in enumerate(text.splitlines(), 1):
            if "yuxi" in line.lower():
                hits.append(f"{p.relative_to(root)}:{lineno}: {line.strip()[:120]}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 yuxi→pisuan 机械改名层")
    ap.add_argument("--apply", action="store_true", help="实际执行（缺省 dry-run）")
    ap.add_argument("--root", default=None, help="仓库根（缺省取本脚本上上级目录）")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    moves = plan_dir_moves(tracked_files(root), root)
    applied = apply_dir_moves(root, moves) if args.apply else []

    files = tracked_files(root)  # 目录改名后重新枚举
    changed = 0
    for p in files:
        try:
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        new_text, n = rewrite_text(text)
        if n and new_text != text:
            if args.apply:
                p.write_bytes(new_text.encode("utf-8"))
            changed += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"== pisuan 改名 [{mode}] ==")
    print(f"目录 mv 计划: {len(moves)}")
    for src, dst in moves:
        print(f"  {src.relative_to(root)} -> {dst.relative_to(root)}")
    print(f"目录 mv 实际执行: {len(applied)}")
    for old, new in applied:
        print(f"  {old} -> {new}")
    print(f"内容改写文件: {changed}")
    residues = residue_report(root, files)
    print(f"残余 yuxi 位置: {len(residues)}")
    for h in residues:
        print(f"  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /c/workspace/pisuan && python -m unittest scripts.test_apply_pisuan_rename -v
```
预期：`Ran 6 tests ... OK`。

- [ ] **Step 5: 真仓库 dry-run 体检**

```bash
cd /c/workspace/pisuan && python scripts/apply_pisuan_rename.py
```
预期（ eyeball 核对，数字允许小幅浮动）：
- `目录 mv 计划: 2`（backend/package/yuxi、packages/yuxi-cli）
- `目录 mv 实际执行: 0`（dry-run）
- `内容改写文件` 数量级 400-600（后端 ~325 + compose/文档/前端/工作流）
- `内容改写文件: 0` 之外的 git 状态保持干净（dry-run 不落盘）——`git status --short` 应无输出
- 残余清单主要是 docs/ 与 CLAUDE.md 中含 `xerrors/上游/upstream` 的行

- [ ] **Step 6: 提交**

```bash
cd /c/workspace/pisuan && git add scripts/apply_pisuan_rename.py scripts/test_apply_pisuan_rename.py && git commit -m "$(cat <<'EOF'
feat: 新增 yuxi→pisuan 机械改名层生成脚本

确定性幂等脚本: 结构化标识符替换 + 带行保护的裸词替换 + 目录 git mv,
产出残余报告供保留清单核对。设计见 docs/superpowers/specs/2026-09-26-yuxi-rename-sync-design.md。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)" && git log --oneline -1
```
预期：输出新提交哈希。

---

### Task 2: 双目录与 pisuan-localized 分支

**Files:** 无代码文件；git 结构操作。

- [ ] **Step 1: 克隆出 localized 目录**

```bash
git clone /c/workspace/pisuan /c/workspace/pisuan-localized
```
预期：克隆完成，HEAD 为 pisuan-custom（源仓库当前分支）。

- [ ] **Step 2: 建分支并接通 GitHub remote**

```bash
cd /c/workspace/pisuan-localized
git switch -c pisuan-localized
git remote add github "$(git -C /c/workspace/pisuan remote get-url origin)"
git push -u github pisuan-localized
git remote -v
```
预期：`origin` → `/c/workspace/pisuan`，`github` → 与 pisuan 仓库 origin 相同的 URL；push 成功。

- [ ] **Step 3: 基线确认**

```bash
cd /c/workspace/pisuan-localized && git log --oneline -1 && ls scripts/apply_pisuan_rename.py
```
预期：顶端提交与 `C:\workspace\pisuan` 的 pisuan-custom 顶端一致；脚本存在。

---

### Task 3: 执行改名 + uv.lock 重生成 + 幂等验证 + 提交推送

**Files:** 由脚本批量改写（约 400-600 个跟踪文件 + 2 个目录 mv）；`backend/uv.lock` 由 uv 重生成。

- [ ] **Step 1: 执行改名**

```bash
cd /c/workspace/pisuan-localized && python scripts/apply_pisuan_rename.py --apply
```
预期：`目录 mv 实际执行: 2`；内容改写文件数与 Task 1 Step 5 的 dry-run 一致。

- [ ] **Step 2: 重新生成 uv.lock**

```bash
cd /c/workspace/pisuan-localized/backend && uv lock && cd ..
```
预期：`Resolved N packages`，uv.lock 中 `yuxi-workspace`/`yuxi` 条目变为 `pisuan-*`/`pisuan`。若 uv 因缺缓存需要联网属正常。

- [ ] **Step 3: 幂等复跑**

```bash
cd /c/workspace/pisuan-localized && python scripts/apply_pisuan_rename.py --apply
```
预期：`目录 mv 实际执行: 0`、`内容改写文件: 0`；残余清单与 Step 1 完全相同。

- [ ] **Step 4: 残余报告核对（验收标准 1）**

```bash
cd /c/workspace/pisuan-localized && git grep -in yuxi | grep -viE "xerrors|上游|upstream" | head -20
```
预期：**空输出**（所有非上游指称的 yuxi 已清零）。若有命中，逐条判断：属保留清单 → 在 `apply_pisuan_rename.py` 的 SKIP/规则中补充并从 Task 3 Step 1 重来；属漏改 → 补规则重来。核对通过后浏览 `git status --short | head -30` 确认改动面合理。

- [ ] **Step 5: 提交改名提交并推送**

```bash
cd /c/workspace/pisuan-localized && git add -A && git commit -m "$(cat <<'EOF'
chore: 机械改名层 yuxi→pisuan（apply_pisuan_rename.py 脚本生成）

唯一机械提交, 位于分支顶端, 每次同步后丢弃重建。
目录 mv: backend/package/yuxi→pisuan, packages/yuxi-cli→pisuan-cli。
含导入/路径/环境变量/DB schema 表常量/compose/前端 API 路径全量改写,
uv.lock 由 uv lock 重新生成。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)" && git push github pisuan-localized && git log --oneline -2
```
预期：推送成功；分支顶端 = 改名提交，其父 = pisuan-custom 顶端。

---

### Task 4: localized 栈启动 + 三段测试 + 探针

**Files:** 无代码文件；`.env`（未跟踪，本地手工配置）。

- [ ] **Step 1: 配置 localized .env（含并存端口覆盖）**

```bash
cd /c/workspace/pisuan-localized
cp /c/workspace/pisuan/.env .env
sed -i 's/YUXI_/PISUAN_/g' .env
cat >> .env <<'EOF'

# —— 并存端口覆盖（旧栈 C:\workspace\pisuan 继续占用默认端口）——
PISUAN_API_PORT=6050
PISUAN_WEB_PORT=6173
PISUAN_POSTGRES_PORT=15432
PISUAN_REDIS_PORT=16379
PISUAN_MINIO_API_PORT=19000
PISUAN_MINIO_CONSOLE_PORT=19001
PISUAN_MILVUS_PORT=19531
PISUAN_MILVUS_HEALTH_PORT=19092
PISUAN_NEO4J_HTTP_PORT=7475
PISUAN_NEO4J_BOLT_PORT=7688
PISUAN_SANDBOX_PORT=18002
PISUAN_MINERU_PORT=18003
PISUAN_PADDLEX_PORT=18004
EOF
grep -c PISUAN_ .env
```
预期：PISUAN_ 计数 ≥ 14。

- [ ] **Step 2: 启动 localized 栈**

```bash
cd /c/workspace/pisuan-localized && docker compose up -d
```
预期：与旧栈相同的镜像层缓存命中，构建快速；一次性容器 `pisuan-localized-storage-migrator-1` ExitCode 0（`docker inspect --format '{{.State.ExitCode}}' pisuan-localized-storage-migrator-1` 输出 `0`）。全新 postgres 卷上 migrator 以新表名 `pisuan_schema_migrations` 完成 schema v8 初始化。旧栈 10 个容器不受影响。

- [ ] **Step 3: api 就绪探针**

```bash
docker inspect --format '{{.State.Health.Status}}' pisuan-localized-api-1
docker logs pisuan-localized-api-1 --tail 20
```
预期：`healthy`；日志含 startup complete。若 unhealthy，按 `.wolf/buglog.json` bug-130 两步序排查（migrator 先行 → restart api/worker）。

- [ ] **Step 4: 三段测试（在 localized 容器内）**

```bash
docker exec pisuan-localized-api-1 pytest /app/test/unit -m "not slow" -q
docker exec pisuan-localized-api-1 pytest /app/test/integration -q
docker exec pisuan-localized-api-1 pytest /app/test/e2e/test_deterministic_agent_path_e2e.py -m e2e -q
```
预期依次：`2530 passed`（数量允许随上游微动）；`141 passed, 205 skipped, 3 errors`（3 个 error 为上游存量 FK 问题，见 buglog）；`passed`。任何新失败 = 改名层缺陷，回到 Task 3 修脚本规则重来。

- [ ] **Step 5: 探针与收尾**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:6050/health || docker exec pisuan-localized-api-1 python -c "import pisuan; print('import-ok', pisuan.__file__)"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:6173
cd /c/workspace/pisuan-localized && docker compose down
```
预期：api 健康（200 或 import-ok 且路径指向 `/app/package/pisuan/...`）；web 200；down 后旧栈继续服务。

---

### Task 5: sync-upstream 脚本改造（第 5 步：重建 localized）

**Files:**
- Modify: `scripts/sync-upstream.ps1`（整文件重写）
- Modify: `scripts/sync-upstream.sh`（整文件重写）

- [ ] **Step 1: 重写 sync-upstream.ps1**

完整新内容：

```powershell
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

Write-Host ""
Write-Host "==> [2/5] 更新本地 main 到 upstream/main..." -ForegroundColor Cyan
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
Write-Host "==> [3/5] 将 pisuan-custom rebase 到最新 main..." -ForegroundColor Cyan
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
Write-Host "==> [4/5] 推送 pisuan-custom..." -ForegroundColor Cyan
git push origin pisuan-custom

Write-Host ""
Write-Host "==> [5/5] 重建 pisuan-localized（机械改名层重新生成）..." -ForegroundColor Cyan
$localizedDir = "C:\workspace\pisuan-localized"
if (Test-Path $localizedDir) {
    Push-Location $localizedDir
    try {
        git fetch origin
        git switch pisuan-localized
        git reset --hard origin/pisuan-custom
        python scripts/apply_pisuan_rename.py --apply
        Set-Location backend
        uv lock
        Set-Location ..
        git add -A
        git commit -m "chore: 机械改名层 yuxi→pisuan（脚本重新生成）"
        git push github pisuan-localized --force-with-lease
        Write-Host "   ✅ pisuan-localized 已重建并推送" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  localized 重建失败: $_" -ForegroundColor Yellow
        Write-Host "    pisuan-custom 已同步完成, localized 可稍后手动重建。"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "   跳过（未找到 $localizedDir）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ 同步完成！"
Write-Host "  main:             $(git rev-parse --short main)"
Write-Host "  pisuan-custom:    $(git rev-parse --short pisuan-custom)"
Write-Host "  pisuan-localized: $(git -C C:\workspace\pisuan-localized rev-parse --short pisuan-localized)"
Write-Host "============================================"
```

- [ ] **Step 2: 重写 sync-upstream.sh**

完整新内容：

```bash
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
# ============================================================

set -euo pipefail

echo "==> [1/5] 拉取上游最新代码..."
git fetch upstream

echo ""
echo "==> [2/5] 更新本地 main 到 upstream/main..."
CURRENT_BRANCH=$(git branch --show-current)
git checkout main
git merge upstream/main --ff-only 2>/dev/null || {
  echo "⚠️  main 无法快进合并，可能有本地提交。请手动处理。"
  git checkout "$CURRENT_BRANCH"
  exit 1
}
echo "   main 已更新到 $(git rev-parse --short HEAD)"

echo ""
echo "==> [3/5] 将 pisuan-custom rebase 到最新 main..."
git checkout pisuan-custom
if git rebase main; then
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
echo "==> [4/5] 推送 pisuan-custom..."
git push origin pisuan-custom

echo ""
echo "==> [5/5] 重建 pisuan-localized（机械改名层重新生成）..."
LOCALIZED_DIR="/c/workspace/pisuan-localized"
if [ -d "$LOCALIZED_DIR" ]; then
  if (
    cd "$LOCALIZED_DIR" &&
    git fetch origin &&
    git switch pisuan-localized &&
    git reset --hard origin/pisuan-custom &&
    python scripts/apply_pisuan_rename.py --apply &&
    (cd backend && uv lock) &&
    git add -A &&
    git commit -m "chore: 机械改名层 yuxi→pisuan（脚本重新生成）" &&
    git push github pisuan-localized --force-with-lease
  ); then
    echo "   ✅ pisuan-localized 已重建并推送"
  else
    echo "⚠️  localized 重建失败, pisuan-custom 已同步完成, 可稍后手动重建。"
  fi
  echo "  pisuan-localized: $(git -C "$LOCALIZED_DIR" rev-parse --short pisuan-localized)"
else
  echo "   跳过（未找到 $LOCALIZED_DIR）"
fi

echo ""
echo "============================================"
echo "✅ 同步完成！"
echo "  main:          $(git rev-parse --short main)"
echo "  pisuan-custom: $(git rev-parse --short pisuan-custom)"
echo "============================================"
```

- [ ] **Step 3: 语法验证**

```bash
bash -n /c/workspace/pisuan/scripts/sync-upstream.sh && echo SH-OK
```
预期：`SH-OK`。PowerShell 侧：`pwsh -NoProfile -Command "[void][System.Management.Automation.Language.Parser]::ParseFile('C:\workspace\pisuan\scripts\sync-upstream.ps1', [ref]$null, [ref]$err); if ($err) { $err; exit 1 } else { 'PS-OK' }"`，预期 `PS-OK`（若宿主无 pwsh 则跳过并记录）。

- [ ] **Step 4: 提交**

```bash
cd /c/workspace/pisuan && git add scripts/sync-upstream.ps1 scripts/sync-upstream.sh && git commit -m "$(cat <<'EOF'
feat: 同步脚本升级三分支——自动重建 pisuan-localized

新增第 4 步推送 pisuan-custom 与第 5 步 localized 重建
（reset 到最新 pisuan-custom → 重跑改名脚本 → uv lock → force-push）。
localized 重建失败不阻断主同步流程。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)" && git log --oneline -1
```

---

### Task 6: 演练同步（验收标准 3：证明改名后差分可行）

**Files:** 无；全部在临时 rehearsal 分支上，结束即清理。

- [ ] **Step 1: 伪造一个"上游新提交"（改 yuxi 导入行）**

```bash
cd /c/workspace/pisuan
git switch -c rehearsal-upstream main
sed -i '1i from yuxi.storage.postgres.manager import BUSINESS_SCHEMA_VERSION  # rehearsal' backend/package/yuxi/models/chat.py
git add -A && git commit -m "chore: 模拟上游提交（改导入行）"
```

- [ ] **Step 2: 语义 rebase 演练（预期零冲突）**

```bash
cd /c/workspace/pisuan
git switch -c rehearsal-custom pisuan-custom
git rebase rehearsal-upstream
```
预期：`Successfully rebased`（语义层无改名，上游动 yuxi 空间不产生冲突）。

- [ ] **Step 3: localized 侧重建演练**

```bash
cd /c/workspace/pisuan-localized
git fetch origin
git reset --hard origin/rehearsal-custom
python scripts/apply_pisuan_rename.py --apply
grep -n "rehearsal" backend/package/pisuan/models/chat.py
```
预期：命中行内容为 `from pisuan.storage.postgres.manager import BUSINESS_SCHEMA_VERSION  # rehearsal`——上游新导入行被自动改名，**全程零手工冲突**。

- [ ] **Step 4: 清理演练痕迹**

```bash
cd /c/workspace/pisuan
git switch pisuan-custom
git branch -D rehearsal-upstream rehearsal-custom
cd /c/workspace/pisuan-localized
git fetch github
git reset --hard github/pisuan-localized
```
预期：两个 rehearsal 分支删除；localized 工作树回到 Task 3 推送的正式改名态（`git log --oneline -1` 顶端为机械改名提交）。

---

### Task 7: 文档更新

**Files:**
- Modify: `docs/develop-guides/upstream-sync-guide.md`（文末追加两节）
- Modify: `CLAUDE.md`（上游代码同步一节补一行）
- Modify: `docs/develop-guides/changelog.md`（追加条目）

- [ ] **Step 1: upstream-sync-guide.md 文末追加**

```markdown
## pisuan-localized 分支（机械改名层）

`pisuan-localized` = `pisuan-custom` + 1 个脚本生成的改名提交（分支顶端），可随时丢弃重建。

- 同步流程：sync-upstream 脚本第 5 步自动重建（reset 到最新 pisuan-custom → 重跑 `scripts/apply_pisuan_rename.py` → `uv lock` → force-push）
- **红线：禁止在 pisuan-localized 上直接提交语义改动**；一切语义改动进 pisuan-custom，否则下次重建即丢失
- 发现改名遗漏：修改 `scripts/apply_pisuan_rename.py` 规则后重建，**永不手改改名提交**
- 本地目录：`C:\workspace\pisuan-localized`（origin = 本仓库本地目录，github = GitHub）
- 保留清单（脚本不改）：指上游项目的 `Yuxi`/`xerrors/Yuxi` 引用、上游 LICENSE、`docs/superpowers/`、`.wolf/`、`uv.lock`（由 uv lock 重生成）

### 切换日操作手册（一次性，时机另行拍板）

1. 停旧栈：`cd C:\workspace\pisuan && docker compose down`
2. 备份：数据目录整体 copy + `pg_dump`
3. 迁移：`docker/volumes/yuxi` → `docker/volumes/pisuan`；psql 执行
   `ALTER TABLE yuxi_schema_migrations RENAME TO pisuan_schema_migrations;`；`.env` 中 `YUXI_*` → `PISUAN_*`
4. 起新栈：`cd C:\workspace\pisuan-localized && docker compose up -d`（移除并存端口覆盖后即用默认端口）
5. 验证：三段测试 + 探针（api healthy / web 200 / 华宇页脚）
6. 回滚：compose down → 恢复备份目录与旧表名 → 旧目录 `docker compose up -d`
```

- [ ] **Step 2: CLAUDE.md 补三分支说明**

在「上游代码同步（双分支策略）」一节的 `- **pisuan-custom**` 行之后插入：

```markdown
- **`pisuan-localized`** → `pisuan-custom` + 机械改名层（yuxi→pisuan，脚本生成、可丢弃重建），由 sync-upstream 脚本第 5 步自动维护，红线禁止直接提交语义改动
```

- [ ] **Step 3: changelog.md 追加**

在 changelog 顶部适当位置（按该文件现有条目格式）追加：

```markdown
- yuxi→pisuan 本地化改名基建：新增 `scripts/apply_pisuan_rename.py`（确定性幂等改名脚本 + unittest）；新增 `pisuan-localized` 分支（= pisuan-custom + 脚本生成的机械改名提交）；sync-upstream 脚本升级三分支流程（第 5 步自动重建 localized）；演练同步验证改名后与上游差分零手工冲突
```

- [ ] **Step 4: 提交并推送 pisuan-custom**

```bash
cd /c/workspace/pisuan && git add docs/develop-guides/upstream-sync-guide.md CLAUDE.md docs/develop-guides/changelog.md && git commit -m "$(cat <<'EOF'
docs: 三分支同步架构文档——localized 分支红线与切换日手册

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)" && git push origin pisuan-custom && git log --oneline -1
```
预期：推送成功。

---

### Task 8: 验收核对（对照设计第 7 节）

无代码改动，逐项核对并输出结论：

- [ ] **Step 1: 验收清单**

1. 残余报告与保留清单逐项核对通过 → Task 3 Step 4 的 `git grep -in yuxi | grep -viE "xerrors|上游|upstream"` 输出为空
2. 三段测试全绿 → Task 4 Step 4 三条命令结果与基线一致（integration 3 个存量 FK error 不算失败）
3. 演练同步零手工冲突 → Task 6 Step 3 的 grep 命中已自动改名的 rehearsal 行
4. 切换日不在本次范围（手册已随 Task 7 落档），现网服务始终由 `C:\workspace\pisuan` 旧栈承载且未被触碰（`docker ps` 中 `pisuan-api-1` 等 10 容器全程在线）

- [ ] **Step 2: 收尾记录**

按 OpenWolf 协议：`.wolf/memory.md` 追加会话流水；`.wolf/cerebrum.md` 记录三分支架构决策（Decision Log）与 rename 脚本规则要点（Key Learnings）；`.wolf/anatomy.md` 补新文件条目。若 Task 4 排障命中新问题，同步记入 `.wolf/buglog.json`。
