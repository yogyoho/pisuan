"""状态锁测试（bug P3-11）：变更命令互斥持锁/next·status 只读不持锁/崩溃残留超时接管/异常释放。"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progress as prog

pytestmark = [pytest.mark.unit]


def _argv(*extra: str) -> list[str]:
    return ["progress.py", *extra]


def test_lock_exclusive_and_release(tmp_path, monkeypatch):
    """O_EXCL 独占：持锁期间第二次获取忙等后响亮失败；释放后可再取。"""
    lock = prog._state_lock(tmp_path)
    assert lock.exists() and json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()
    monkeypatch.setattr(prog, "LOCK_WAIT_SEC", 0.5)
    with pytest.raises(SystemExit):
        prog._state_lock(tmp_path)
    lock.unlink()
    assert prog._state_lock(tmp_path).exists()  # 释放后可再取（留下的锁由 tmp_path 清理）


def test_lock_none_when_state_dir_missing(tmp_path):
    """init 首跑 state 目录尚不存在 → 无从并发，返回 None 不持锁。"""
    assert prog._state_lock(tmp_path / "not_yet") is None


def test_lock_stale_takeover(tmp_path):
    """崩溃残留锁（mtime 超接管阈值）换名留证后重建，属新持有者。"""
    stale = tmp_path / ".progress.lock"
    stale.write_text('{"pid": 1}\n', encoding="utf-8")
    past = time.time() - prog.LOCK_STALE_SEC - 10
    os.utime(stale, (past, past))
    lock = prog._state_lock(tmp_path)
    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()
    evidence = tmp_path / ".progress.lock.stale"
    assert evidence.exists() and '"pid": 1' in evidence.read_text(encoding="utf-8")  # 残留留证
    lock.unlink()


def test_mutating_cmd_holds_lock_and_releases(tmp_path, monkeypatch):
    """变更命令（mark）全程持锁，正常返回后释放。"""
    seen = {}

    def fake_mark(args):
        seen["during"] = (tmp_path / ".progress.lock").exists()
        return prog.EXIT_OK

    monkeypatch.setattr(prog, "cmd_mark", fake_mark)
    monkeypatch.setattr(sys, "argv", _argv("mark", "ch2", "DRAFTED", "--state-dir", str(tmp_path)))
    assert prog.main() == prog.EXIT_OK
    assert seen["during"] is True
    assert not (tmp_path / ".progress.lock").exists()  # 释放


def test_release_on_error(tmp_path, monkeypatch):
    """命令抛错（损坏兜底路径 rc=1）锁仍释放——finally 保证，不留死锁残留。"""

    def boom(args):
        raise OSError("模拟损坏")

    monkeypatch.setattr(prog, "cmd_gate", boom)
    monkeypatch.setattr(sys, "argv", _argv("gate", "--state-dir", str(tmp_path)))
    assert prog.main() == prog.EXIT_ERROR
    assert not (tmp_path / ".progress.lock").exists()


def test_readonly_cmds_no_lock(tmp_path, monkeypatch):
    """next/status 只读不持锁（读到的恒为某次原子写完整快照）。"""
    for name in ("cmd_next", "cmd_status"):
        calls = []
        monkeypatch.setattr(prog, name, lambda args, c=calls: (c.append(1), prog.EXIT_OK)[1])
        monkeypatch.setattr(sys, "argv", _argv(name[4:], "--state-dir", str(tmp_path)))
        assert prog.main() == prog.EXIT_OK
        assert calls and not (tmp_path / ".progress.lock").exists()
