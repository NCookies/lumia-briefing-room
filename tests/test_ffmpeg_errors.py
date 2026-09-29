import subprocess

from lumia_briefing_room.pipeline.ffmpeg_errors import (
    DISK_FULL_MESSAGE,
    describe_clip_error,
    is_disk_full_error,
)


def _called_process_error(stderr: bytes | str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(returncode=1, cmd=["ffmpeg"], output=b"", stderr=stderr)


def test_is_disk_full_error_detects_the_usual_ffmpeg_message():
    exc = _called_process_error(b"av_interleaved_write_frame(): No space left on device\n")
    assert is_disk_full_error(exc) is True


def test_is_disk_full_error_is_case_insensitive_and_checks_other_phrasings():
    exc = _called_process_error("There is not enough space on the disk.\n")
    assert is_disk_full_error(exc) is True


def test_is_disk_full_error_false_for_unrelated_failure():
    exc = _called_process_error(b"Invalid data found when processing input\n")
    assert is_disk_full_error(exc) is False


def test_is_disk_full_error_false_when_exception_has_no_stderr():
    assert is_disk_full_error(RuntimeError("아무 이유")) is False


def test_describe_clip_error_returns_friendly_disk_full_message():
    exc = _called_process_error(b"No space left on device\n")
    assert describe_clip_error(exc) == DISK_FULL_MESSAGE


def test_describe_clip_error_includes_stderr_for_other_ffmpeg_failures():
    exc = _called_process_error(b"Invalid data found when processing input\n")
    message = describe_clip_error(exc)
    assert "Invalid data found when processing input" in message


def test_describe_clip_error_falls_back_to_str_for_non_ffmpeg_exceptions():
    exc = RuntimeError("판독 실패")
    assert describe_clip_error(exc) == "판독 실패"
