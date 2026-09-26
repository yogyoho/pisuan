"""scripts/apply_pisuan_rename.py 的单元测试。

运行（仓库根执行）: python -m unittest scripts.test_apply_pisuan_rename -v
"""

import os
import shutil
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

    def test_embedded_identifiers(self):
        text, _ = rewrite_text(
            "class YuxiWorker: ...\nx-yuxi-uid\n.yuxi/tmp\n_message_chunk_yuxi_events\n"
        )
        self.assertEqual(
            text,
            "class PisuanWorker: ...\nx-pisuan-uid\n.pisuan/tmp\n_message_chunk_pisuan_events\n",
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
            "from yuxi.storage import db\n# 上游 Yuxi 项目\n", encoding="utf-8", newline=""
        )
        (root / "packages/yuxi-cli/main.py").write_text(
            "YUXI_API_PORT = 1\n", encoding="utf-8", newline=""
        )
        (root / "docs/guide.md").write_text(
            "fork 自 xerrors/Yuxi\n见 backend/package/yuxi/README\n", encoding="utf-8", newline=""
        )
        (root / "docs/superpowers/specs/design.md").write_text(
            "yuxi 保持原貌\n", encoding="utf-8", newline=""
        )
        (root / "backend/uv.lock").write_text('name = "yuxi"\n', encoding="utf-8", newline="")
        (root / "packages/yuxi-cli/src/yuxi_cli").mkdir(parents=True)
        (root / "packages/yuxi-cli/src/yuxi_cli/main.py").write_text(
            "from yuxi_cli.util import x\n", encoding="utf-8", newline=""
        )
        (root / "docs/public").mkdir(parents=True)
        (root / "docs/public/yuxi-icon.svg").write_text("<svg/>\n", encoding="utf-8", newline="")
        (root / "docs/yuxi-lockup-on-light.svg").write_text("<svg/>\n", encoding="utf-8", newline="")
        (root / "pkgs/yuxi_tool_yuxi").mkdir(parents=True)
        (root / "pkgs/yuxi_tool_yuxi/x.py").write_text("x = 1\n", encoding="utf-8", newline="")
        (root / "scripts").mkdir()
        for name in ("apply_pisuan_rename.py", "test_apply_pisuan_rename.py"):
            shutil.copy2(REPO_ROOT / "scripts" / name, root / "scripts" / name)
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
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},  # Windows 管道默认 locale 编码, 强制子进程 UTF-8
            check=True,
        )
        return r.stdout

    def test_apply_renames_and_idempotent(self):
        # dry-run: 零改动
        dry = self._run()
        self.assertIn("目录 mv 实际执行: 0", dry)
        self.assertIn("当前含 yuxi 位置", dry)
        self.assertIn("跳过非 UTF-8 文件: 0", dry)
        # dry-run 须展示嵌套闭包的完整计划与文件改名计划
        self.assertIn("packages/yuxi-cli/src/yuxi_cli -> packages/pisuan-cli/src/pisuan_cli", dry)
        self.assertIn("pkgs/yuxi_tool_yuxi -> pkgs/pisuan_tool_pisuan", dry)
        self.assertIn("文件改名计划: 2", dry)
        self.assertIn("文件改名实际执行: 0", dry)
        for rel, expected in (
            ("backend/package/yuxi/core.py", "from yuxi.storage import db\n# 上游 Yuxi 项目\n"),
            ("backend/uv.lock", 'name = "yuxi"\n'),
            ("docs/guide.md", "fork 自 xerrors/Yuxi\n见 backend/package/yuxi/README\n"),
        ):
            self.assertEqual((self.root / rel).read_bytes(), expected.encode("utf-8"))
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
        # 嵌套目录两级都改名 + 文件基名改名
        self.assertIn("packages/yuxi-cli/src/yuxi_cli -> packages/pisuan-cli/src/pisuan_cli", out)
        self.assertIn("docs/public/yuxi-icon.svg -> docs/public/pisuan-icon.svg", out)
        self.assertIn("docs/yuxi-lockup-on-light.svg -> docs/pisuan-lockup-on-light.svg", out)
        self.assertEqual(
            (self.root / "packages/pisuan-cli/src/pisuan_cli/main.py").read_text(encoding="utf-8"),
            "from pisuan_cli.util import x\n",
        )
        self.assertTrue((self.root / "docs/public/pisuan-icon.svg").exists())
        self.assertIn("pkgs/yuxi_tool_yuxi -> pkgs/pisuan_tool_pisuan", out)
        self.assertTrue((self.root / "pkgs/pisuan_tool_pisuan/x.py").exists())
        # 幂等: 复跑无任何新变化（首次 apply 后工作树必然是脏的, 需显式放行）
        out2 = self._run("--apply", "--allow-dirty")
        self.assertIn("目录 mv 实际执行: 0", out2)
        self.assertIn("文件改名实际执行: 0", out2)
        self.assertIn("内容改写文件: 0", out2)

    def test_tool_files_excluded_from_rewrite(self):
        """改名工具与其测试被复制进仓库后, --apply 不得改写它们（否则自毁规则/断言）。"""
        self._run("--apply")
        for name in ("apply_pisuan_rename.py", "test_apply_pisuan_rename.py"):
            self.assertEqual(
                (self.root / "scripts" / name).read_bytes(),
                (REPO_ROOT / "scripts" / name).read_bytes(),
            )

    def test_dirty_worktree_guard(self):
        """--apply 遇未提交改动拒绝执行; --allow-dirty 显式放行。"""
        core = self.root / "backend/package/yuxi/core.py"
        core.write_text("from yuxi.storage import db\n# 上游 Yuxi 项目\ndirty = True\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), "--apply"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("拒绝", r.stderr)
        self.assertTrue((self.root / "backend/package/yuxi").exists())
        self.assertEqual(
            core.read_text(encoding="utf-8"),
            "from yuxi.storage import db\n# 上游 Yuxi 项目\ndirty = True\n",
        )
        out = self._run("--apply", "--allow-dirty")
        self.assertIn("backend/package/yuxi -> backend/package/pisuan", out)
        self.assertTrue((self.root / "backend/package/pisuan/core.py").exists())


if __name__ == "__main__":
    unittest.main()
