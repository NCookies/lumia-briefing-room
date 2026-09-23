from pathlib import Path

from lumia_briefing_room.recording_info import find_latest_session

MPD = """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT10M" maxSegmentDuration="PT3.0S">
  <Period id="0" start="PT0S">
    <AdaptationSet id="0" contentType="video" maxWidth="{w}" maxHeight="{h}">
      <Representation id="0" mimeType="video/mp4" codecs="{codec}" width="{w}" height="{h}">
        <SegmentTemplate timescale="1000000" duration="3000000" initialization="i" media="m" startNumber="1" />
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""


def _session(root: Path, name: str, w=2560, h=1440, codec="hev1.2.4.L123.B0", with_mpd=True) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    if with_mpd:
        (folder / "session.mpd").write_text(MPD.format(w=w, h=h, codec=codec), encoding="utf-8")


def test_missing_or_empty_root_returns_none(tmp_path: Path):
    assert find_latest_session(tmp_path / "nope") is None
    assert find_latest_session(tmp_path) is None


def test_picks_newest_eternal_return_session(tmp_path: Path):
    _session(tmp_path, "bg_1049590_20260901_100000", w=1920, h=1080)
    _session(tmp_path, "bg_1049590_20260923_095917", w=2560, h=1440)
    info = find_latest_session(tmp_path)
    assert info is not None
    assert (info.name, info.width, info.height) == ("bg_1049590_20260923_095917", 2560, 1440)
    assert info.codec == "hev1.2.4.L123.B0"


def test_prefers_eternal_return_over_newer_other_game(tmp_path: Path):
    _session(tmp_path, "bg_1049590_20260901_100000", w=1920, h=1080)
    _session(tmp_path, "bg_5075020_20260904_061655", w=1280, h=720)
    assert find_latest_session(tmp_path).width == 1920


def test_skips_sessions_without_readable_mpd(tmp_path: Path):
    _session(tmp_path, "bg_1049590_20260901_100000", w=1920, h=1080)
    _session(tmp_path, "bg_1049590_20260923_095917", with_mpd=False)
    assert find_latest_session(tmp_path).name == "bg_1049590_20260901_100000"


def test_falls_back_to_other_game_when_no_eternal_return_session(tmp_path: Path):
    _session(tmp_path, "bg_5075020_20260904_061655", w=1280, h=720)
    assert find_latest_session(tmp_path).height == 720
