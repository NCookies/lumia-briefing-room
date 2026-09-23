import json
import os
import subprocess
from pathlib import Path

import pytest

from lumia_briefing_room.pipeline import proxy
from lumia_briefing_room.video.vod import find_ffprobe

from conftest import FFMPEG_PATH, requires_ffmpeg


def test_paths_live_under_dot_proxy():
    assert proxy.proxy_dir(Path("clips")) == Path("clips") / ".proxy"
    assert proxy.proxy_path(Path("clips"), "abc") == Path("clips") / ".proxy" / "abc.mp4"


def test_bitrate_scales_with_pixels_and_has_a_floor():
    assert proxy.proxy_bitrate_kbps(1080) == 8000
    assert proxy.proxy_bitrate_kbps(720) < proxy.proxy_bitrate_kbps(1080)
    assert proxy.proxy_bitrate_kbps(144) == 1500


def test_encoder_plan_prefers_media_foundation_then_x264_and_skips_missing():
    assert proxy.encoder_plan({"h264_mf", "libx264", "h264_nvenc"}) == ["h264_mf", "libx264"]
    assert proxy.encoder_plan({"libx264"}) == ["libx264"]
    assert proxy.encoder_plan({"h264_mf"}) == ["h264_mf"]
    assert proxy.encoder_plan(set()) == []


def test_parse_encoders_lists_video_encoder_names():
    text = (
        " V....D libx264              libx264 H.264 / AVC\n"
        " V....D h264_mf              H264 via MediaFoundation (codec h264)\n"
        " A....D aac                  AAC\n"
        " ------\n"
    )
    assert proxy.parse_encoders(text) == {"libx264", "h264_mf"}


def test_command_for_media_foundation_uses_bitrate_and_never_upscales():
    cmd = proxy.build_proxy_command(Path("ffmpeg"), Path("in.mp4"), Path("out.mp4"), encoder="h264_mf", height=1080, crf=23)
    joined = " ".join(cmd)
    assert "-c:v h264_mf" in joined and "-b:v 8000k" in joined
    assert "scale=-2:min(1080\\,ih)" in joined
    assert "-crf" not in cmd
    assert cmd[-1] == "out.mp4"
    assert "+faststart" in cmd


def test_command_for_x264_uses_crf():
    cmd = proxy.build_proxy_command(Path("ffmpeg"), Path("in.mp4"), Path("out.mp4"), encoder="libx264", height=720, crf=25)
    assert "-crf" in cmd and cmd[cmd.index("-crf") + 1] == "25"
    assert "-b:v" not in cmd


def test_is_fresh_requires_existing_nonempty_and_not_older_than_source(tmp_path: Path):
    source = tmp_path / "a.mp4"
    source.write_bytes(b"src")
    out = tmp_path / ".proxy" / "a.mp4"
    assert proxy.is_proxy_fresh(out, source) is False

    out.parent.mkdir()
    out.write_bytes(b"")
    assert proxy.is_proxy_fresh(out, source) is False

    out.write_bytes(b"proxy")
    os.utime(source, (1000, 1000))
    os.utime(out, (2000, 2000))
    assert proxy.is_proxy_fresh(out, source) is True

    os.utime(source, (3000, 3000))
    assert proxy.is_proxy_fresh(out, source) is False


def test_remove_orphan_proxies_keeps_only_existing_clips(tmp_path: Path):
    clips, trash = tmp_path, tmp_path / ".trash"
    trash.mkdir()
    for cid, where in [("live", clips), ("trashed", trash)]:
        (where / f"{cid}.json").write_text(json.dumps({"sessionDir": "s"}), encoding="utf-8")
        (where / f"{cid}.mp4").write_bytes(b"x")
    pdir = proxy.proxy_dir(clips)
    pdir.mkdir()
    for cid in ["live", "trashed", "gone"]:
        (pdir / f"{cid}.mp4").write_bytes(b"p")
    (pdir / "gone.tmp.mp4").write_bytes(b"p")

    removed = proxy.remove_orphan_proxies(clips, trash)

    assert sorted(p.name for p in pdir.iterdir()) == ["live.mp4", "trashed.mp4"]
    assert {p.name for p in removed} == {"gone.mp4", "gone.tmp.mp4"}


def test_create_proxy_falls_back_to_next_encoder_on_failure(tmp_path: Path, monkeypatch):
    tried = []

    def fake_encode(cmd, duration_sec, on_progress):
        encoder = cmd[cmd.index("-c:v") + 1]
        tried.append(encoder)
        if encoder == "h264_mf":
            raise proxy.ProxyError("mf 실패")
        Path(cmd[-1]).write_bytes(b"ok")

    monkeypatch.setattr(proxy, "_run_encode", fake_encode)
    monkeypatch.setattr(proxy, "list_encoders", lambda ffmpeg: {"h264_mf", "libx264"})
    src = tmp_path / "a.mp4"
    src.write_bytes(b"s")
    out = tmp_path / ".proxy" / "a.mp4"

    used = proxy.create_proxy(Path("ffmpeg"), src, out, height=1080, crf=23, duration_sec=5)

    assert used == "libx264" and tried == ["h264_mf", "libx264"]
    assert out.read_bytes() == b"ok"
    assert not list(out.parent.glob("*.tmp*"))


def test_create_proxy_raises_when_every_encoder_fails(tmp_path: Path, monkeypatch):
    def always_fail(cmd, duration_sec, on_progress):
        raise proxy.ProxyError("실패")

    monkeypatch.setattr(proxy, "_run_encode", always_fail)
    monkeypatch.setattr(proxy, "list_encoders", lambda ffmpeg: {"h264_mf"})
    src = tmp_path / "a.mp4"
    src.write_bytes(b"s")
    with pytest.raises(proxy.ProxyError):
        proxy.create_proxy(Path("ffmpeg"), src, tmp_path / ".proxy" / "a.mp4", height=1080, crf=23, duration_sec=5)
    assert not list((tmp_path / ".proxy").glob("*"))


def _make_hevc(path: Path, seconds: int = 4, size: str = "1920x1080") -> None:
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx265", "-tag:v", "hev1", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True, capture_output=True,
    )


def _probe(path: Path) -> dict:
    out = subprocess.run(
        [str(find_ffprobe(FFMPEG_PATH)), "-v", "error", "-show_entries",
         "stream=codec_name,codec_type,width,height,pix_fmt", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return {s["codec_type"]: s for s in json.loads(out)["streams"]}


@requires_ffmpeg
def test_real_hevc_source_becomes_playable_h264_with_progress(tmp_path: Path):
    src = tmp_path / "clip.mp4"
    try:
        _make_hevc(src)
    except subprocess.CalledProcessError:
        pytest.skip("이 ffmpeg 에 libx265 가 없다")
    out = tmp_path / ".proxy" / "clip.mp4"
    progress = []

    used = proxy.create_proxy(FFMPEG_PATH, src, out, height=720, crf=28, duration_sec=4, on_progress=progress.append)

    assert used in ("h264_mf", "libx264")
    streams = _probe(out)
    assert streams["video"]["codec_name"] == "h264"
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["video"]["height"] == 720
    assert streams["audio"]["codec_name"] == "aac"
    assert progress and progress[-1] == pytest.approx(1.0, abs=0.05)
    assert all(0.0 <= p <= 1.0 for p in progress)


@requires_ffmpeg
def test_small_source_is_not_upscaled(tmp_path: Path):
    src = tmp_path / "clip.mp4"
    try:
        _make_hevc(src, size="640x360")
    except subprocess.CalledProcessError:
        pytest.skip("이 ffmpeg 에 libx265 가 없다")
    out = tmp_path / ".proxy" / "clip.mp4"
    proxy.create_proxy(FFMPEG_PATH, src, out, height=1080, crf=23, duration_sec=4)
    assert _probe(out)["video"]["height"] == 360
