import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumia_briefing_room import disk_identity
from lumia_briefing_room.pipeline import clip as clip_mod
from lumia_briefing_room.video.frames import write_merged_segment_file
from lumia_briefing_room.video.session import recording_in_progress
from lumia_briefing_room.video.throttle import Throttle, copy_throttled


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = 0.0

    def clock(self):
        return self.now

    def sleep(self, sec):
        self.slept += sec
        self.now += sec


def test_throttle_sleeps_so_the_average_rate_stays_under_the_limit():
    fake = FakeClock()
    t = Throttle(10_000_000, clock=fake.clock, sleep=fake.sleep)
    for _ in range(5):
        t.consume(4_000_000)
    assert fake.slept == pytest.approx(2.0)


def test_throttle_does_not_sleep_when_the_work_is_already_slower_than_the_limit():
    fake = FakeClock()
    t = Throttle(10_000_000, clock=fake.clock, sleep=fake.sleep)
    t.consume(1_000_000)
    fake.now += 5.0
    t.consume(1_000_000)
    assert fake.slept == pytest.approx(0.1)


def test_copy_throttled_copies_every_byte_and_counts_them(tmp_path):
    src = tmp_path / "a.bin"
    src.write_bytes(os.urandom(300_000))
    fake = FakeClock()
    t = Throttle(100_000, clock=fake.clock, sleep=fake.sleep)
    copy_throttled(src, tmp_path / "b.bin", t, block=64 * 1024)
    assert (tmp_path / "b.bin").read_bytes() == src.read_bytes()
    assert fake.slept == pytest.approx(3.0)


def _session_dir(root: Path, name: str, age_sec: float) -> Path:
    d = root / name
    d.mkdir(parents=True)
    stamp = time.time() - age_sec
    os.utime(d, (stamp, stamp))
    return d


def test_recording_in_progress_when_a_session_folder_changed_just_now(tmp_path):
    _session_dir(tmp_path, "bg_1049590_20260928_144503", age_sec=3600)
    _session_dir(tmp_path, "bg_1049590_20260930_151337", age_sec=5)
    assert recording_in_progress(tmp_path) is True


def test_recording_not_in_progress_when_every_session_is_stale(tmp_path):
    _session_dir(tmp_path, "bg_1049590_20260930_151337", age_sec=600)
    _session_dir(tmp_path, "not_a_session", age_sec=1)
    assert recording_in_progress(tmp_path) is False


def test_recording_not_in_progress_when_the_root_is_missing(tmp_path):
    assert recording_in_progress(tmp_path / "nope") is False


def test_same_disk_compares_physical_disks_even_across_drive_letters(monkeypatch):
    disks = {"H:": 1, "S:": 1, "C:": 2}
    monkeypatch.setattr(disk_identity, "physical_disk", lambda p: disks.get(Path(p).drive.upper()))
    assert disk_identity.same_disk(Path("H:/steam video"), Path("S:/full")) is True
    assert disk_identity.same_disk(Path("H:/steam video"), Path("C:/full")) is False


def test_same_disk_falls_back_to_the_drive_letter_when_the_disk_is_unknown(monkeypatch):
    monkeypatch.setattr(disk_identity, "physical_disk", lambda p: None)
    assert disk_identity.same_disk(Path("H:/a"), Path("h:/b")) is True
    assert disk_identity.same_disk(Path("H:/a"), Path("S:/b")) is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")
def test_physical_disk_reads_the_system_drive():
    assert isinstance(disk_identity.physical_disk(Path(os.environ["SystemDrive"] + "\\")), int)


class _Session:
    segment_duration_sec = 3.0
    start_utc = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def __init__(self, directory):
        self.directory = directory


def test_write_merged_segment_file_counts_every_byte_it_reads_from_the_recording(tmp_path):
    d = tmp_path / "bg_1049590_20260930_000000"
    d.mkdir()
    (d / "init-stream0.m4s").write_bytes(b"i" * 100)
    for n in (1, 2, 3):
        (d / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"c" * 1000)
    consumed = []

    class Recorder:
        def consume(self, n):
            consumed.append(n)

    used = write_merged_segment_file(_Session(d), 0, [1, 2, 3], tmp_path / "out.mp4", throttle=Recorder())

    assert used == [1, 2, 3]
    assert sum(consumed) == 3100
    assert (tmp_path / "out.mp4").stat().st_size == 3100


def test_copy_rate_is_limited_only_while_steam_is_recording(tmp_path, monkeypatch):
    session = _Session(tmp_path / "bg_1049590_20260930_000000")
    monkeypatch.setattr(clip_mod, "recording_in_progress", lambda root: root == tmp_path)
    assert clip_mod.copy_rate_for(session) == clip_mod.LIVE_RECORDING_BYTES_PER_SEC
    monkeypatch.setattr(clip_mod, "recording_in_progress", lambda root: False)
    assert clip_mod.copy_rate_for(session) is None
