import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from lumia_briefing_room import procs

CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL = 0x00004000


def test_flags_hide_window_on_windows():
    assert procs.process_flags(platform="win32") == CREATE_NO_WINDOW


def test_flags_can_lower_priority():
    assert procs.process_flags(low_priority=True, platform="win32") == CREATE_NO_WINDOW | BELOW_NORMAL


def test_flags_are_zero_elsewhere():
    assert procs.process_flags(low_priority=True, platform="linux") == 0


def test_run_hidden_passes_creationflags_and_returns_result(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs, cmd=cmd)
        return "done"

    monkeypatch.setattr(procs.subprocess, "run", fake_run)
    monkeypatch.setattr(procs.sys, "platform", "win32")
    assert procs.run_hidden(["x"], check=True, capture_output=True) == "done"
    assert seen["creationflags"] == CREATE_NO_WINDOW
    assert seen["check"] is True and seen["capture_output"] is True


def test_popen_hidden_passes_creationflags(monkeypatch):
    seen = {}
    monkeypatch.setattr(procs.subprocess, "Popen", lambda cmd, **kw: seen.update(kw) or "proc")
    monkeypatch.setattr(procs.sys, "platform", "win32")
    assert procs.popen_hidden(["x"], stdout=1) == "proc"
    assert seen["creationflags"] == CREATE_NO_WINDOW


def test_run_hidden_really_runs():
    out = procs.run_hidden([sys.executable, "-c", "print('hi')"], capture_output=True, check=True)
    assert out.stdout.strip() == b"hi"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 작업 개체 전용")
def test_children_die_when_parent_dies(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    script = tmp_path / "parent.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import subprocess, sys, time
            from lumia_briefing_room import procs
            assert procs.kill_children_on_exit()
            child = procs.popen_hidden([sys.executable, "-c", "import time; time.sleep(60)"])
            open({str(pid_file)!r}, "w").write(str(child.pid))
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    src = Path(__file__).resolve().parents[1] / "src"
    parent = subprocess.Popen([sys.executable, str(script)], env={**__import__("os").environ, "PYTHONPATH": str(src)})
    try:
        deadline = time.time() + 10
        while not pid_file.exists() and time.time() < deadline:
            time.sleep(0.1)
        child_pid = int(pid_file.read_text())
        assert _alive(child_pid)
        parent.kill()
        parent.wait()
        deadline = time.time() + 5
        while _alive(child_pid) and time.time() < deadline:
            time.sleep(0.1)
        assert not _alive(child_pid)
    finally:
        parent.kill()


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 우선순위 전용")
def test_lower_current_process_priority_is_applied_in_a_child_process():
    code = (
        "import ctypes\n"
        "from lumia_briefing_room import procs\n"
        "assert procs.lower_current_process_priority()\n"
        "k=ctypes.WinDLL('kernel32'); k.GetPriorityClass.restype=ctypes.c_uint32\n"
        "k.GetPriorityClass.argtypes=[ctypes.c_void_p]; k.GetCurrentProcess.restype=ctypes.c_void_p\n"
        "print(k.GetPriorityClass(k.GetCurrentProcess()))\n"
    )
    src = Path(__file__).resolve().parents[1] / "src"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(src)},
    )
    assert out.stdout.strip() == str(BELOW_NORMAL), out.stderr
