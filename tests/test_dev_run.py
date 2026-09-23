import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dev_run  # noqa: E402


class FakeProc:
    def __init__(self, returncode=None, hang=False):
        self.returncode = returncode
        self.hang = hang
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        if not self.hang:
            self.returncode = 1

    def kill(self):
        self.killed = True
        self.returncode = 1

    def wait(self, timeout=None):
        self.waited = True
        if self.returncode is None:
            raise dev_run.subprocess.TimeoutExpired("x", timeout)
        return self.returncode


def test_is_source_change_only_python_files():
    assert dev_run.is_source_change({(1, "a/b.py")})
    assert not dev_run.is_source_change({(1, "a/b.pyc"), (1, "a/__pycache__/b.py")})
    assert not dev_run.is_source_change(set())


def test_build_command_opens_ui_only_on_first_start():
    first = dev_run.build_command(["--x"], first_start=True)
    again = dev_run.build_command(["--x"], first_start=False)
    assert first[-2:] == ["--x", "--open-ui"] or "--open-ui" in first
    assert "--open-ui" not in again
    assert again[1:3] == ["-m", "lumia_briefing_room.cli.app"]


def test_build_command_does_not_duplicate_open_ui():
    cmd = dev_run.build_command(["--open-ui"], first_start=True)
    assert cmd.count("--open-ui") == 1


def test_stop_kills_when_terminate_hangs():
    proc = FakeProc(hang=True)
    dev_run.stop(proc, timeout=0)
    assert proc.terminated and proc.killed and proc.returncode is not None


def test_run_restarts_on_python_change_only():
    spawned = []

    def spawn(cmd):
        p = FakeProc()
        spawned.append((cmd, p))
        return p

    batches = [{(1, "x.txt")}, {(1, "a.py")}, set()]
    dev_run.run([], watch=iter(batches), spawn=spawn)
    assert len(spawned) == 2
    assert "--open-ui" in spawned[0][0] and "--open-ui" not in spawned[1][0]
    assert spawned[0][1].terminated


def test_run_exits_when_app_quits_normally():
    spawned = []

    def spawn(cmd):
        p = FakeProc(returncode=0)
        spawned.append(p)
        return p

    dev_run.run([], watch=iter([set(), set()]), spawn=spawn)
    assert len(spawned) == 1


def test_run_waits_for_change_after_crash():
    procs = [FakeProc(returncode=1), FakeProc()]

    def spawn(cmd):
        return procs.pop(0)

    dev_run.run([], watch=iter([set(), {(1, "a.py")}]), spawn=spawn)
    assert procs == []


def test_frontend_change_builds_without_restart():
    spawned = []
    builds = []
    fe = str(dev_run.FRONTEND_SRC / "App.tsx")
    ignored = str(dev_run.FRONTEND_SRC / "notes.md")

    def spawn(cmd):
        p = FakeProc()
        spawned.append(p)
        return p

    dev_run.run(
        [],
        watch=iter([{(1, fe)}, {(1, ignored)}]),
        spawn=spawn,
        build_frontend=lambda: builds.append(1),
    )
    assert len(builds) == 1
    assert len(spawned) == 1
