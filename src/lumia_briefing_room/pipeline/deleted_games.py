"""사용자가 `게임 전체 삭제` 한 게임 키 기록. 이전 버전 클립·영상 색인 통합이 남은 클립·색인으로 그 게임을 되살리지 않게 한다.

`games_dir/.deleted_games.txt` 에 한 줄에 키 하나. 폴더가 아니라 `list_games` 에 안 잡힌다.
"""

from __future__ import annotations

from pathlib import Path

FILENAME = ".deleted_games.txt"


def load(games_dir: Path) -> set[str]:
    try:
        return {line.strip() for line in (games_dir / FILENAME).read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        return set()


def add(games_dir: Path, key: str) -> None:
    games_dir.mkdir(parents=True, exist_ok=True)
    with (games_dir / FILENAME).open("a", encoding="utf-8") as f:
        f.write(key + "\n")
