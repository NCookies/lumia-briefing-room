from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline import disk_alert as da
from lumia_briefing_room.pipeline.disk_space import DiskStatus
from lumia_briefing_room.pipeline.notices import NoticeCenter


def _cfg(tmp_path):
    return Config(paths=PathsConfig(clips=tmp_path / "clips"))


def _status(low):
    message = "여유 공간이 1.0GB 남았습니다." if low else None
    return DiskStatus(free_bytes=1, expected_bytes=1, threshold_bytes=2, low=low, message=message)


def test_low_space_posts_a_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(da, "disk_status", lambda cfg: _status(True))
    center = NoticeCenter()
    da.check_and_notify(_cfg(tmp_path), center)
    assert [n["kind"] for n in center.list()] == ["disk_low"]


def test_enough_space_clears_an_old_notice(tmp_path, monkeypatch):
    center = NoticeCenter()
    center.post("disk_low", "old")
    monkeypatch.setattr(da, "disk_status", lambda cfg: _status(False))
    da.check_and_notify(_cfg(tmp_path), center)
    assert center.list() == []


def test_unreadable_disk_is_ignored(tmp_path, monkeypatch):
    def boom(cfg):
        raise OSError("gone")

    monkeypatch.setattr(da, "disk_status", boom)
    assert da.check_and_notify(_cfg(tmp_path), NoticeCenter()) is None


def test_full_video_failure_is_posted():
    center = NoticeCenter()
    da.report_full_video_failure("저장 공간이 부족", center)
    assert center.list()[0]["kind"] == "full_video_failed"
