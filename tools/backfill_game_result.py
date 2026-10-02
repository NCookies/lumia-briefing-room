"""이미 저장된 게임의 결과(순위·일반/랭크·스탯·결과표 이미지)를 풀영상 끝 30초로 다시 읽어 채운다.

usage:
    python tools/backfill_game_result.py [--games-dir DIR] [--clips-dir DIR] [--ffmpeg PATH] [--force] [게임키 ...]

대상: 결과가 없거나, 일반/랭크가 unknown 이거나, 순위가 빈 게임. `--force` 면 결과가 있는 게임도 다시 읽는다.
게임키(예: 20260929_154840)를 주면 그 게임만 읽는다. 사용자가 직접 고친 게임(matchResultSource="manual")은 `--force` 여도
건드리지 않고, 새로 읽은 값이 비면 예전 값을 남긴다. 풀영상이 없는 게임은 건너뛴다. 코발트 게임은 승패가 없을 때만 읽는다.
앱이 실행 중이어도 되지만, 게임 목록은 새로고침해야 바뀐 값이 보인다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.pipeline.game_backfill import backfill_game_results  # noqa: E402
from lumia_briefing_room.pipeline.result_tail import find_result_in_video  # noqa: E402

DEFAULT_ROOT = Path.home() / "Videos" / "LumiaBriefingRoom"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="읽을 게임키(생략하면 대상 전부)")
    parser.add_argument("--games-dir", type=Path, default=DEFAULT_ROOT / "games")
    parser.add_argument("--clips-dir", type=Path, default=DEFAULT_ROOT / "clips")
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="결과가 이미 채워진 게임도 다시 읽는다")
    args = parser.parse_args()

    ffmpeg = args.ffmpeg or discover_ffmpeg()
    if ffmpeg is None:
        raise SystemExit("ffmpeg를 찾을 수 없다")

    report = backfill_game_results(
        args.games_dir, args.clips_dir,
        find=lambda video: find_result_in_video(video, ffmpeg_path=ffmpeg),
        keys=args.keys or None, force=args.force,
        on_game=lambda key, text: print(f"{key}: {text}", flush=True),
    )
    print(
        f"{report.filled}개 채움, 대상 아님 {report.skipped}, 수동 잠금 {report.locked}, "
        f"풀영상 없음 {report.no_video}, 못 찾음 {report.not_found}, 실패 {report.failed}"
    )


if __name__ == "__main__":
    main()
