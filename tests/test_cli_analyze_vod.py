import pytest

from lumia_briefing_room.cli import analyze_vod as cli
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress


def test_parser_defaults_are_safe():
    args = cli.build_parser().parse_args(["a.mp4"])

    assert args.force is False and args.rebuild is False
    assert args.clips_dir is None and args.streamer is None


def test_main_passes_options_and_prints_a_summary(tmp_path, monkeypatch, capsys):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")
    seen = {}

    def fake_analyze(path, cfg, **kw):
        seen.update(kw, path=path)
        kw["on_progress"](VodProgress("decode", 0.5, 1, 2, "절반"))
        return {
            "status": "done", "clips": ["c1", "c2"],
            "games": [{"index": 1, "startSec": 10.0, "endSec": 900.0, "kFinal": 6, "aFinal": 4,
                       "clipIds": ["c1", "c2"], "result": {"placement": 2, "total": 7}}],
        }

    monkeypatch.setattr(cli, "analyze_vod", fake_analyze)
    monkeypatch.setattr(cli, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")

    cli.main([str(video), "--streamer", "○○○", "--force", "--clips-dir", str(tmp_path / "out")])

    out = capsys.readouterr().out
    assert seen["streamer"] == "○○○" and seen["force"] is True and seen["rebuild"] is False
    assert seen["clips_dir"] == tmp_path / "out"
    assert "50.0%" in out and "게임 1판, 클립 2개 (done)" in out
    assert "2/7위" in out and "K 6 A 4" in out


def test_main_reports_a_missing_video(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")

    with pytest.raises(SystemExit) as exc:
        cli.main([str(tmp_path / "없음.mp4")])

    assert "영상 파일이 없다" in str(exc.value)


def test_main_tells_how_to_resume_after_cancel(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")

    def cancelled(*a, **k):
        raise VodCancelled()

    monkeypatch.setattr(cli, "analyze_vod", cancelled)
    monkeypatch.setattr(cli, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")

    with pytest.raises(SystemExit) as exc:
        cli.main([str(video)])

    assert "이어서" in str(exc.value)
