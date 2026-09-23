"""배포에 동봉할 LGPL ffmpeg 를 vendor/ffmpeg 에 내려받는다. (plan-deploy.md D5)

usage: python tools/fetch_ffmpeg.py [--url URL] [--force]

**GPL 빌드를 동봉하면 안 된다**(SPEC §4, plan-deploy §2 D4). 개발 PC 에 깔린 winget ffmpeg 는
GPL 풀 빌드라 그대로 쓰면 배포 라이선스 의무가 생긴다. 그래서 받은 빌드가 정말 LGPL 인지
`-version` 의 configuration 줄로 확인한 뒤에만 자리를 잡는다.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "vendor" / "ffmpeg"
DEFAULT_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl-shared.zip"
)
WANTED = ("ffmpeg.exe", "ffprobe.exe")
LICENSE_NAMES = ("LICENSE.txt", "LICENSE", "COPYING.LGPLv2.1", "COPYING.LGPLv3")
FORBIDDEN_FLAGS = ("--enable-gpl", "--enable-nonfree")
USABLE_H264 = ("h264_mf", "libx264")
_ENCODER_LINE = re.compile(r"^\s*V\S*\s+(\S+)\s", re.M)


class FetchError(Exception):
    pass


def is_lgpl_build(version_output: str) -> bool:
    """configuration 줄에 GPL/nonfree 플래그가 없어야 한다. 줄 자체가 없으면 확인 불가라 거부한다."""
    for line in version_output.splitlines():
        if line.strip().startswith("configuration:"):
            return not any(flag in line for flag in FORBIDDEN_FLAGS)
    return False


def has_usable_h264(encoder_output: str) -> bool:
    names = set(_ENCODER_LINE.findall(encoder_output))
    return bool(names & set(USABLE_H264))


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"내려받는 중: {url}")
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)
    print(f"  {dest.stat().st_size / 1e6:.1f} MB")
    return dest


def wanted_names(archive_names: list[str]) -> list[str]:
    """꺼낼 파일 이름. shared 빌드는 exe 옆에 있어야 도는 DLL 까지 가져온다(ffplay·문서·헤더는 뺀다)."""
    names = [name.split("/")[-1] for name in archive_names if not name.endswith("/")]
    dlls = sorted({name for name in names if name.lower().endswith(".dll")})
    return [*WANTED, *dlls, *LICENSE_NAMES]


def extract_binaries(archive: Path, dest: Path) -> list[Path]:
    """zip 안의 ffmpeg.exe·ffprobe.exe·DLL·라이선스만 꺼낸다(최상위 폴더 이름은 빌드마다 다르다)."""
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        members = {name: name.split("/")[-1] for name in zf.namelist() if not name.endswith("/")}
        for wanted in wanted_names(zf.namelist()):
            for name, base in members.items():
                if base != wanted:
                    continue
                out = dest / base
                out.write_bytes(zf.read(name))
                extracted.append(out)
                break
    missing = [name for name in WANTED if not (dest / name).exists()]
    if missing:
        raise FetchError(f"압축 파일에서 {', '.join(missing)} 를 찾지 못했다: {archive}")
    return extracted


def verify(ffmpeg: Path) -> None:
    version = subprocess.run([str(ffmpeg), "-hide_banner", "-version"], capture_output=True, text=True).stdout
    if not is_lgpl_build(version):
        raise FetchError(
            "LGPL 빌드가 아니다(configuration 에 --enable-gpl/--enable-nonfree 가 있거나 확인할 수 없다). "
            "GPL 빌드는 동봉하지 않는다 — SPEC §4"
        )
    encoders = subprocess.run([str(ffmpeg), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if not has_usable_h264(encoders):
        raise FetchError(f"H.264 프록시용 인코더({'·'.join(USABLE_H264)})가 없다 — 재생 폴백이 동작하지 않는다")
    print(f"확인: LGPL 빌드이고 H.264 프록시 인코더가 있다\n  {version.splitlines()[0]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배포용 LGPL ffmpeg 내려받기")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--dest", type=Path, default=VENDOR_DIR)
    parser.add_argument("--force", action="store_true", help="이미 있어도 다시 받는다")
    parser.add_argument("--zip", type=Path, default=None, help="이미 받아 둔 zip 을 쓴다")
    args = parser.parse_args(argv)

    if (args.dest / "ffmpeg.exe").exists() and not args.force:
        print(f"이미 있다: {args.dest} (다시 받으려면 --force)")
        verify(args.dest / "ffmpeg.exe")
        return 0

    archive = args.zip or download(args.url, args.dest.parent / "_ffmpeg-download.zip")
    try:
        extract_binaries(archive, args.dest)
        verify(args.dest / "ffmpeg.exe")
    except FetchError as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.zip is None and archive.exists():
            archive.unlink()

    print(f"준비됨: {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
