import subprocess

import pytest

from lumia_briefing_room.detect.pvp import PvpScore
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.vod_clips import build_vod_metadata, cut_vod_clip, vod_clip_id
from lumia_briefing_room.video.vod import find_ffprobe, probe_video

FFMPEG_PATH = None
try:
    from lumia_briefing_room.config import discover_ffmpeg

    FFMPEG_PATH = discover_ffmpeg()
except Exception:  # pragma: no cover
    FFMPEG_PATH = None
FFPROBE_PATH = find_ffprobe(FFMPEG_PATH) if FFMPEG_PATH else None
requires_ffmpeg = pytest.mark.skipif(
    FFMPEG_PATH is None or FFPROBE_PATH is None, reason="ffmpeg/ffprobe를 찾을 수 없다"
)


@pytest.fixture
def vod_file(tmp_path):
    path = tmp_path / "vod.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "20", "-c:v", "libx264", "-g", "10", "-keyint_min", "10",
            "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        ],
        check=True,
    )
    return path


def interval(**kw):
    base = dict(
        start=100.0, end=130.0, tags=frozenset({"kill"}), k_delta=1, a_delta=0,
        died=False, day_night="day", confidence=0.9, teammate_deaths=0,
        region=None, enemy_ring_mean=1.5, game_day=3,
    )
    base.update(kw)
    return CombatInterval(**base)


def test_vod_clip_id_is_unique_per_game_and_start():
    assert vod_clip_id("3fa91c02b7de", 3, 15234.7) == "vod_3fa91c02b7de_g03_015234"
    assert vod_clip_id("3fa91c02b7de", 3, 15234.7) != vod_clip_id("3fa91c02b7de", 4, 15234.7)


@requires_ffmpeg
def test_cut_vod_clip_cuts_the_requested_window_without_reencoding(vod_file, tmp_path):
    out = tmp_path / "out" / "clip.mp4"

    cut = cut_vod_clip(vod_file, ClipRange(5.0, 12.0, "combat"), out, ffmpeg_path=FFMPEG_PATH)

    assert out.exists()
    info = probe_video(out, ffprobe_path=FFPROBE_PATH)
    assert info.codec == "h264"
    assert cut.duration_sec == pytest.approx(info.duration_sec, abs=0.3)
    assert 6.5 <= cut.duration_sec <= 8.0


@requires_ffmpeg
def test_cut_vod_clip_keeps_the_audio_track(vod_file, tmp_path):
    out = tmp_path / "clip.mp4"
    cut_vod_clip(vod_file, ClipRange(2.0, 9.0, "combat"), out, ffmpeg_path=FFMPEG_PATH)

    probe = subprocess.run(
        [str(FFPROBE_PATH), "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert "aac" in probe.stdout


@requires_ffmpeg
def test_cut_vod_clip_can_drop_audio(vod_file, tmp_path):
    out = tmp_path / "clip.mp4"
    cut_vod_clip(vod_file, ClipRange(2.0, 9.0, "combat"), out, ffmpeg_path=FFMPEG_PATH, include_audio=False)

    probe = subprocess.run(
        [str(FFPROBE_PATH), "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == ""


def result_screen():
    return ResultScreen(
        placement=2, total=7, match_type="rank", match_label="랭크", outcome="실험 종료",
        nickname="스트리머", character="마르티나", character_raw="MARTIN",
        stats={"tk": 15, "kills": 6, "deaths": 1, "assists": 6},
        teammates=[{"nickname": "a", "character": "레온"}], image=None,
    )


def build(**kw):
    args = dict(
        title="3일차 낮 교전", vod_id="3fa91c02b7de", vod_file="H:/vod/a.mp4", streamer="○○○",
        game_index=3, game_start=90.0, game_end=900.0, width=1920, height=1080,
        interval=interval(), clip_range=ClipRange(95.0, 138.0, "combat"), duration_sec=43.0,
        thumbnail_path="thumbs/x.jpg", pvp=PvpScore(score=1.0, signals=["kill_delta"]),
        match_kills=6, match_assists=6, match_result=result_screen(), result_image_path=None,
    )
    args.update(kw)
    return build_vod_metadata(**args)


def test_vod_metadata_marks_source_and_carries_position_fields():
    meta = build()

    assert meta["source"] == "vod"
    assert meta["vodId"] == "3fa91c02b7de"
    assert meta["vodFile"] == "H:/vod/a.mp4"
    assert meta["streamer"] == "○○○"
    assert meta["vodGameIndex"] == 3
    assert meta["gameStartOffsetSec"] == 90.0 and meta["gameEndOffsetSec"] == 900.0
    assert meta["videoOffsetSec"] == 95.0 and meta["durationSec"] == 43.0
    assert meta["combatStartOffsetSec"] == 100.0 and meta["combatEndOffsetSec"] == 130.0
    assert (meta["sourceWidth"], meta["sourceHeight"]) == (1920, 1080)
    for steam_only in ("sessionDir", "segmentStart", "matchStartUtc"):
        assert steam_only not in meta


def test_vod_metadata_shares_the_steam_clip_fields_the_ui_reads():
    meta = build()

    assert meta["tags"] == ["kill"]
    assert meta["killDelta"] == 1 and meta["assistDelta"] == 0
    assert meta["pvpScore"] == 1.0 and meta["pvpSignals"] == ["kill_delta"]
    assert meta["gameDay"] == 3 and meta["dayNight"] == "day"
    assert meta["phaseIndex"] == 4 and meta["reviveCost"] == "credit"
    assert meta["myCharacter"] == "마르티나" and meta["teamCharacters"] == ["레온"]
    assert meta["matchKills"] == 6 and meta["matchAssists"] == 6
    assert meta["matchResult"]["placement"] == 2
    assert meta["userLabel"] is None and meta["pinned"] is False and meta["deletedAt"] is None
    assert meta["sourceIncomplete"] is False and meta["thumbnailPath"] == "thumbs/x.jpg"


def test_vod_metadata_without_result_screen_or_streamer():
    meta = build(match_result=None, streamer=None)

    assert meta["matchResult"] is None
    assert meta["streamer"] is None
    assert meta["myCharacter"] is None and meta["teamCharacters"] == []
