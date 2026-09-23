"""Inno Setup 설치기를 만든다. (plan-deploy.md D6)

usage: python tools/build_installer.py

먼저 `build.bat`(tools/build_release.py)으로 `dist/LumiaBriefingRoom` 이 만들어져 있어야 한다.
버전·경로는 `__version__` 한 곳에서 나와 `/D` 정의로 .iss 에 넘어간다.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lumia_briefing_room import __version__  # noqa: E402
from lumia_briefing_room.icon import save_ico  # noqa: E402

APP_NAME = "LumiaBriefingRoom"
ISS_PATH = ROOT / "installer" / "lumia.iss"
ISCC_CANDIDATES = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
)


class InstallerError(Exception):
    pass


def installer_name(version: str) -> str:
    return f"{APP_NAME}-{version}-setup.exe"


def find_iscc() -> Path | None:
    for candidate in ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    return Path(found) if found else None


def iscc_defines(*, version: str, source_dir: Path, out_dir: Path, icon: Path, notices: Path) -> list[str]:
    return [
        f"/DAppVersion={version}",
        f"/DSourceDir={source_dir}",
        f"/DOutputDir={out_dir}",
        f"/DAppIcon={icon}",
        f"/DNoticesFile={notices}",
    ]


def build(*, version: str) -> Path:
    source_dir = ROOT / "dist" / APP_NAME
    if not (source_dir / f"{APP_NAME}.exe").exists():
        raise InstallerError(f"먼저 배포본을 만들어야 한다(build.bat) — 없다: {source_dir / f'{APP_NAME}.exe'}")

    iscc = find_iscc()
    if iscc is None:
        raise InstallerError(
            "Inno Setup 을 찾을 수 없다 — winget install JRSoftware.InnoSetup 으로 설치할 것"
        )

    out_dir = ROOT / "dist"
    defines = iscc_defines(
        version=version,
        source_dir=source_dir,
        out_dir=out_dir,
        icon=save_ico(ROOT / "build" / "icon.ico"),
        notices=ROOT / "THIRD_PARTY_NOTICES.md",
    )
    result = subprocess.run([str(iscc), *defines, str(ISS_PATH)], cwd=ROOT)
    if result.returncode != 0:
        raise InstallerError(f"ISCC 가 실패했다 (종료 코드 {result.returncode})")

    installer = out_dir / installer_name(version)
    if not installer.exists():
        raise InstallerError(f"설치기가 만들어지지 않았다: {installer}")
    return installer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="설치기 빌드")
    parser.add_argument("--version", default=__version__)
    args = parser.parse_args(argv)

    try:
        installer = build(version=args.version)
    except InstallerError as exc:
        print(f"설치기 빌드 실패: {exc}", file=sys.stderr)
        return 1

    print(f"설치기: {installer} ({installer.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
