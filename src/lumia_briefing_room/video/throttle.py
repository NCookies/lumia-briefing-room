"""녹화 중인 디스크를 몰아서 읽고 쓰지 않도록 복사 속도를 제한한다.

스팀은 녹화 드라이브에 3초마다 조각을 쓰는데, 같은 HDD 에서 수 GB 를 최대 속도로 읽고 쓰면 그 쓰기가 밀려
프레임이 버려지고, 2초 넘게 밀리면 스팀이 녹화 세션을 오류로 끝낸 뒤 게임을 다시 켤 때까지 녹화하지 않는다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

BLOCK = 4 * 1024 * 1024


class Throttle:
    def __init__(
        self,
        bytes_per_sec: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.bytes_per_sec = bytes_per_sec
        self._clock = clock
        self._sleep = sleep
        self._start = clock()
        self._total = 0

    def consume(self, n: int) -> None:
        self._total += n
        ahead = self._total / self.bytes_per_sec - (self._clock() - self._start)
        if ahead > 0:
            self._sleep(ahead)


def copy_throttled(src: Path, dst: Path, throttle: Throttle, *, block: int = BLOCK) -> None:
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while data := fin.read(block):
            fout.write(data)
            throttle.consume(len(data))
