import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import fetch_ffmpeg  # noqa: E402

LGPL_CONFIG = "configuration: --prefix=/ffbuild/prefix --enable-version3 --enable-libvmaf --enable-mediafoundation"
GPL_CONFIG = "configuration: --prefix=/ffbuild/prefix --enable-gpl --enable-version3 --enable-libx264"


def test_lgpl_build_is_accepted_and_gpl_is_refused():
    assert fetch_ffmpeg.is_lgpl_build(f"ffmpeg version N-1\n{LGPL_CONFIG}\n") is True
    assert fetch_ffmpeg.is_lgpl_build(f"ffmpeg version N-1\n{GPL_CONFIG}\n") is False


def test_nonfree_build_is_also_refused():
    assert fetch_ffmpeg.is_lgpl_build(f"x\nconfiguration: --enable-nonfree --enable-version3\n") is False


def test_a_build_without_a_configuration_line_is_refused():
    assert fetch_ffmpeg.is_lgpl_build("ffmpeg version 9.0\nbuilt with gcc\n") is False


def test_encoder_requirement_checks_for_a_usable_h264_encoder():
    listing = " V....D h264_mf              H264 via MediaFoundation (codec h264)\n V....D hevc_mf   x\n"
    assert fetch_ffmpeg.has_usable_h264(listing) is True
    assert fetch_ffmpeg.has_usable_h264(" V....D hevc_mf   x\n A....D aac  y\n") is False


def _zip_with(names: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in names.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def test_extract_takes_the_binaries_and_dlls_regardless_of_folder_name(tmp_path: Path):
    archive = tmp_path / "ffmpeg.zip"
    archive.write_bytes(
        _zip_with(
            {
                "ffmpeg-master-latest-win64-lgpl-shared/bin/ffmpeg.exe": b"FFMPEG",
                "ffmpeg-master-latest-win64-lgpl-shared/bin/ffprobe.exe": b"FFPROBE",
                "ffmpeg-master-latest-win64-lgpl-shared/bin/ffplay.exe": b"FFPLAY",
                "ffmpeg-master-latest-win64-lgpl-shared/bin/avcodec-63.dll": b"CODEC",
                "ffmpeg-master-latest-win64-lgpl-shared/bin/avutil-61.dll": b"UTIL",
                "ffmpeg-master-latest-win64-lgpl-shared/LICENSE.txt": b"LGPL",
                "ffmpeg-master-latest-win64-lgpl-shared/doc/ffmpeg.html": b"doc",
                "ffmpeg-master-latest-win64-lgpl-shared/include/libavutil/avutil.h": b"header",
            }
        )
    )
    dest = tmp_path / "vendor" / "ffmpeg"

    extracted = fetch_ffmpeg.extract_binaries(archive, dest)

    assert sorted(p.name for p in dest.iterdir()) == [
        "LICENSE.txt", "avcodec-63.dll", "avutil-61.dll", "ffmpeg.exe", "ffprobe.exe",
    ]
    assert (dest / "ffmpeg.exe").read_bytes() == b"FFMPEG"
    assert (dest / "avcodec-63.dll").read_bytes() == b"CODEC"
    assert not (dest / "ffplay.exe").exists()
    assert len(extracted) == 5


def test_static_build_without_dlls_still_works(tmp_path: Path):
    archive = tmp_path / "static.zip"
    archive.write_bytes(_zip_with({"x/bin/ffmpeg.exe": b"A", "x/bin/ffprobe.exe": b"B"}))
    dest = tmp_path / "out"

    fetch_ffmpeg.extract_binaries(archive, dest)

    assert sorted(p.name for p in dest.iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]


def test_extract_fails_clearly_when_the_archive_lacks_ffmpeg(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip_with({"other/bin/ffplay.exe": b"x"}))

    with pytest.raises(fetch_ffmpeg.FetchError, match="ffmpeg.exe"):
        fetch_ffmpeg.extract_binaries(archive, tmp_path / "out")


def test_extract_neutralizes_paths_that_try_to_escape(tmp_path: Path):
    """압축 안 경로가 아니라 파일 이름만 쓰므로 대상 폴더 밖으로 나갈 수 없다."""
    archive = tmp_path / "evil.zip"
    archive.write_bytes(_zip_with({"../../bin/ffmpeg.exe": b"x", "a/bin/ffprobe.exe": b"y"}))
    dest = tmp_path / "out"

    fetch_ffmpeg.extract_binaries(archive, dest)

    assert (dest / "ffmpeg.exe").read_bytes() == b"x"
    assert not (tmp_path.parent / "bin").exists()


def test_default_url_points_at_a_win64_lgpl_build():
    assert "lgpl" in fetch_ffmpeg.DEFAULT_URL
    assert "win64" in fetch_ffmpeg.DEFAULT_URL
    assert fetch_ffmpeg.DEFAULT_URL.startswith("https://")
