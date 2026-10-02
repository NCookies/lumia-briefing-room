"""0.1.x 사용자가 업데이트한 직후를 임시 환경에 재현해 브라우저로 열어 준다(눈으로 확인용).

usage: python e2e/demo_legacy.py [--no-open] [--keep]

옛 폴더 구조(paths.clips·vodClips)의 합성 데이터 — 스팀 클립 2개(풀영상 없음), 영상 파일 2편(원본 있음/없음) — 로
앱을 띄운다. 켜자마자 뜨는 필수 이전 화면에서 폴더 선택(윈도우 폴더 선택 창) → 옮기기, 옵션에서 되돌리기를 직접 눌러 본다.
실제 사용자 설정·클립은 건드리지 않는다(임시 LOCALAPPDATA·APPDATA·USERPROFILE). Ctrl+C 로 끝내면 임시 폴더를 지운다(--keep 이면 남김).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e.world import Server, World, make_sample_video  # noqa: E402


def find_ffmpeg() -> str:
    for found in filter(None, [os.environ.get("LUMIA_FFMPEG"), shutil.which("ffmpeg")]):
        encoders = subprocess.run([found, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        if "libx264" in encoders:
            return found
    raise SystemExit("libx264 가 있는 ffmpeg 를 찾을 수 없다(PATH 또는 LUMIA_FFMPEG)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true", help="브라우저를 열지 않는다")
    parser.add_argument("--keep", action="store_true", help="끝나도 임시 폴더를 지우지 않는다")
    args = parser.parse_args()

    ffmpeg = find_ffmpeg()
    base = Path(tempfile.mkdtemp(prefix="lumia_demo_legacy_"))
    home = base / "home"
    (home / "Local").mkdir(parents=True)
    (home / "Roaming").mkdir()
    world = World(home=home, root=base / "storage", sample_video=make_sample_video(ffmpeg, base / "sample.mp4"),
                  ffmpeg=ffmpeg, legacy=True)
    world.add_legacy_steam_clips("20260928_160025", count=2)
    world.add_legacy_vod("방송A", original=True, tail=10)
    world.add_legacy_vod("방송B", original=False, tail=20)
    world.write_config(consented=True)
    server = Server(world).start()
    print(f"\n앱 주소: {server.url}   (임시 폴더: {base})")
    print(f"옛 클립 폴더: {world.old_clips}\n옛 영상 클립 폴더: {world.old_vod_clips}")
    print("확인 순서: 클립 탭 → '저장 폴더 설정 열기' → '새 구조로 옮기기…' → 폴더 선택… → 옮기기 → 되돌리기")
    print("끝내려면 Ctrl+C")
    if not args.no_open:
        webbrowser.open(server.url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        if not args.keep:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
