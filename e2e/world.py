"""E2E 가 쓰는 임시 세계(저장 폴더·설정·시드 게임)와 서버 프로세스. 실제 사용자 폴더는 건드리지 않는다."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lumia_briefing_room.consent import CONSENT_VERSION  # noqa: E402
from lumia_briefing_room.pipeline.vod_store import save_index, vod_id  # noqa: E402

KEY_BR = "20260930_002400"
KEY_BR2 = "20260930_013000"
KEY_OLD = "20260928_030000"
KEY_COBALT = "20260928_050000"


def make_sample_video(ffmpeg: str, out: Path, seconds: int = 24) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=15:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def candidate(cid: str, start: float, end: float, *, certain: bool = False, title: str | None = None) -> dict:
    return {
        "id": cid, "start": start, "end": end, "combatStart": start + 2, "combatEnd": end - 2,
        "title": title or cid, "tags": ["kill"] if certain else ["no_result"], "certain": certain, "user": {},
    }


def game_json(key: str, *, mode: str = "battle_royale", placement: int | None = 3, with_video: bool = True,
              duration: float = 24.0, size: int = 1000, candidates: list[dict] | None = None) -> dict:
    day = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
    clock = f"{key[9:11]}:{key[11:13]}:{key[13:15]}"
    result = None
    if placement:
        result = {"matchType": "rank", "matchLabel": "랭크", "placement": placement, "total": 8, "outcome": None,
                  "nickname": None, "tk": 5, "kills": 3, "deaths": 1, "assists": 2}
    elif mode == "cobalt":
        result = {"matchType": "unknown", "matchLabel": "", "placement": None, "total": None, "outcome": "승리",
                  "nickname": None, "tk": None, "kills": 4, "deaths": 0, "assists": 1}
    video = None
    if with_video:
        video = {"path": "full.mp4", "sizeBytes": size, "durationSec": duration, "offsetSec": 0.0,
                 "segmentDurationSec": 3.0, "sourceIncomplete": False, "audioStatus": "full"}
    return {
        "gameKey": key, "matchStartUtc": f"{day}T{clock}Z", "matchEndUtc": f"{day}T{clock}Z",
        "sessionDir": "bg_1", "sessionStartUtc": f"{day}T00:00:00Z", "gameMode": mode,
        "sourceWidth": 2560, "sourceHeight": 1440, "matchResult": result,
        "portraits": {}, "pinned": False, "fullVideo": video,
        "candidates": candidates or [], "userCandidates": [], "markers": [],
    }


@dataclass
class World:
    home: Path
    root: Path
    sample_video: Path
    ffmpeg: str
    legacy: bool = False

    @property
    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            LOCALAPPDATA=str(self.home / "Local"), APPDATA=str(self.home / "Roaming"),
            USERPROFILE=str(self.home), LUMIA_FFMPEG=self.ffmpeg, PYTHONIOENCODING="utf-8",
        )
        env.pop("LUMIA_PROFILE", None)
        return env

    @property
    def config_path(self) -> Path:
        return self.home / "config.json"

    @property
    def steam_games(self) -> Path:
        return self.root / "full_video" / "steam_replay"

    @property
    def old_clips(self) -> Path:
        return self.home / "old" / "clips"

    @property
    def old_vod_clips(self) -> Path:
        return self.home / "old" / "vod"

    @property
    def vod_videos(self) -> Path:
        return self.home / "vods"

    @property
    def vod_games(self) -> Path:
        return self.root / "full_video" / "vod"

    @property
    def library_vod(self) -> Path:
        return self.home / "Local" / "LumiaBriefingRoom" / "library" / "vod"

    def write_config(self, *, consented: bool = True, extra: dict | None = None) -> None:
        cfg: dict = {"paths": {"root": str(self.root)}}
        if self.legacy:
            cfg["paths"] = {"clips": str(self.old_clips), "vodClips": str(self.old_vod_clips)}
        if self.vod_videos.exists():
            cfg["vod"] = {"sources": [str(self.vod_videos)]}
        if consented:
            cfg["consent"] = {"version": CONSENT_VERSION}
        for key, value in (extra or {}).items():
            cfg.setdefault(key, {}).update(value)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_game(self, key: str, **kwargs) -> Path:
        folder = self.steam_games / key
        folder.mkdir(parents=True, exist_ok=True)
        if kwargs.get("with_video", True):
            shutil.copyfile(self.sample_video, folder / "full.mp4")
            kwargs.setdefault("size", (folder / "full.mp4").stat().st_size)
        (folder / "game.json").write_text(json.dumps(game_json(key, **kwargs), ensure_ascii=False), encoding="utf-8")
        return folder

    def seed_default_games(self) -> None:
        """두 날짜·두 모드·풀영상 없는 게임까지 — 대부분의 화면 시나리오가 쓰는 기본 세계."""
        self.add_game(KEY_BR, placement=1, candidates=[
            candidate(f"{KEY_BR}_01", 3, 9, certain=True, title="첫 교전"),
            candidate(f"{KEY_BR}_02", 10, 16),
            candidate(f"{KEY_BR}_03", 17, 23, certain=True, title="마지막 교전"),
        ])
        self.add_game(KEY_BR2, placement=5, candidates=[candidate(f"{KEY_BR2}_01", 4, 12, certain=True)])
        self.add_game(KEY_OLD, placement=2, with_video=False,
                      candidates=[candidate(f"{KEY_OLD}_01", 4, 12, certain=True)])
        self.add_game(KEY_COBALT, mode="cobalt", placement=None,
                      candidates=[candidate(f"{KEY_COBALT}_01", 2, 10, certain=True)])


    def add_vod(self, name: str, *, streamer: str = "하이용가리", games: int = 2, tail: int = 0,
                original: bool = True, date_epoch: float = 1790000000.0, placements=(3, 1)) -> str:
        """영상 파일 하나(분석 끝남)와 그 게임 `games`개. 영상 id 가 겹치지 않게 `tail` 바이트를 붙여 다르게 만든다.
        `original=False` 면 원본 영상을 지운 상태(풀영상·클립만 남은 영상)."""
        self.vod_videos.mkdir(parents=True, exist_ok=True)
        video = self.vod_videos / f"{name}.mp4"
        shutil.copyfile(self.sample_video, video)
        with open(video, "ab") as f:
            f.write(b"x" * tail)
        vid = vod_id(video)
        os.utime(video, (date_epoch, date_epoch))
        index_games = []
        for i in range(1, games + 1):
            key = f"vod_{vid}_g{i:02d}"
            folder = self.vod_games / key
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.sample_video, folder / "full.mp4")
            data = game_json(key, placement=placements[(i - 1) % len(placements)], candidates=[
                candidate(f"{key}_{i:03d}1", 3, 9, certain=True, title=f"{name} 교전 {i}")])
            data.update({"source": "vod", "vodId": vid, "vodFile": str(video), "streamer": streamer, "vodGameIndex": i,
                         "vodStartSec": 100.0 * i, "vodEndSec": 100.0 * i + 24, "spanStartSec": 100.0 * i,
                         "spanEndSec": 100.0 * i + 24, "matchStartUtc": None, "matchEndUtc": None})
            data["fullVideo"]["sizeBytes"] = (folder / "full.mp4").stat().st_size
            (folder / "game.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            index_games.append({"index": i, "gameKey": key, "startSec": 100.0 * i, "endSec": 100.0 * i + 24, "clipIds": []})
        save_index(self.library_vod, {"id": vid, "path": str(video), "status": "done", "width": 1920, "height": 1080,
                                      "durationSec": 400.0, "games": index_games, "clips": [], "streamer": streamer})
        if not original:
            video.unlink()
        return vid


    def _sample_jpg(self, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-ss", "2", "-i", str(self.sample_video),
                        "-frames:v", "1", str(out)], check=True)
        return out

    def add_legacy_steam_clips(self, key: str = "20260928_160025", count: int = 2) -> list[str]:
        """0.1.x 가 만들던 클립 폴더: mp4 + json + .thumbs 가 한 폴더에 섞여 있다."""
        clips = self.old_clips
        clips.mkdir(parents=True, exist_ok=True)
        day = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        clock = f"{key[9:11]}:{key[11:13]}:{key[13:15]}"
        names = []
        self._sample_jpg(clips / ".thumbs" / f"{key}_result.jpg")
        for n in range(1, count + 1):
            name = f"{key}_{n:02d}"
            self._sample_jpg(clips / ".thumbs" / f"{name}.jpg")
            meta = {
                "title": f"옛 교전 {n}", "sessionDir": "bg_1_20260928_144503", "sessionStartUtc": f"{day}T15:45:00Z",
                "matchStartUtc": f"{day}T{clock}Z", "matchEndUtc": f"{day}T16:18:00Z", "gameMode": "battle_royale",
                "sourceWidth": 2560, "sourceHeight": 1440, "videoOffsetSec": 1000.0 * n, "durationSec": 24.0,
                "combatStartOffsetSec": 1000.0 * n + 5, "combatEndOffsetSec": 1000.0 * n + 15, "prerollSource": "combat",
                "thumbnailPath": f".thumbs/{name}.jpg", "tags": ["kill"], "killDelta": 1, "assistDelta": 0, "died": False,
                "pvpScore": 3.0, "pvpSignals": [], "region": "바지선", "gameDay": 1, "dayNight": "day",
                "detectorConfidence": 0.6, "matchKills": 2, "matchAssists": 1,
                "matchResult": {"matchType": "rank", "matchLabel": "랭크", "placement": 3, "total": 8,
                                "imagePath": f".thumbs/{key}_result.jpg"},
                "sourceIncomplete": False, "pinned": n == 1,
            }
            (clips / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            shutil.copyfile(self.sample_video, clips / f"{name}.mp4")
            names.append(name)
        return names

    def add_legacy_vod(self, name: str, *, original: bool, tail: int, clips: int = 2) -> str:
        """0.1.x 가 만든 영상 파일 분석 결과: `.vods/<id>.json` 색인 + 영상 클립 mp4/json. 원본이 있으면 판독 캐시도 있다."""
        from lumia_briefing_room.pipeline.vod_store import cache_path

        self.vod_videos.mkdir(parents=True, exist_ok=True)
        video = self.vod_videos / f"{name}.mp4"
        shutil.copyfile(self.sample_video, video)
        with open(video, "ab") as f:
            f.write(b"x" * tail)
        vid = vod_id(video)
        out = self.old_vod_clips
        out.mkdir(parents=True, exist_ok=True)
        ids = []
        for n in range(1, clips + 1):
            cid = f"vod_{vid}_g01_{n:06d}"
            self._sample_jpg(out / ".thumbs" / f"{cid}.jpg")
            meta = {
                "title": f"{name} 옛 클립 {n}", "source": "vod", "vodId": vid, "vodFile": str(video), "streamer": None,
                "vodGameIndex": 1, "gameStartOffsetSec": 100.0, "gameEndOffsetSec": 400.0, "sourceWidth": 1920,
                "sourceHeight": 1080, "videoOffsetSec": 100.0 + 30 * n, "durationSec": 24.0,
                "thumbnailPath": f".thumbs/{cid}.jpg", "sourceIncomplete": False, "audioStatus": "full",
                "combatStartOffsetSec": 105.0 + 30 * n, "combatEndOffsetSec": 115.0 + 30 * n, "prerollSource": "combat",
                "tags": ["kill"], "killDelta": 1, "assistDelta": 0, "died": False, "pvpScore": 3.0, "pvpSignals": [],
                "gameDay": 1, "dayNight": "day", "pinned": False, "matchKills": 2, "matchAssists": 1,
                "matchResult": {"matchType": "rank", "matchLabel": "랭크", "placement": 4, "total": 8},
            }
            (out / f"{cid}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            shutil.copyfile(self.sample_video, out / f"{cid}.mp4")
            ids.append(cid)
        result = {"matchType": "rank", "matchLabel": "랭크", "placement": 4, "total": 8}
        index = {"id": vid, "path": str(video), "size": video.stat().st_size, "durationSec": 400.0, "width": 1920,
                 "height": 1080, "fps": 30.0, "streamer": None, "status": "done", "error": None, "decodeDone": True,
                 "analyzedSec": 400.0, "analysisVersion": 2,
                 "games": [{"index": 1, "startSec": 100.0, "endSec": 400.0, "kFinal": 2, "aFinal": 1,
                            "result": result, "clipIds": ids}],
                 "clips": ids}
        save_index(out, index)
        if original:
            cache = cache_path(out, vid)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b"x")
        else:
            video.unlink()
        return vid


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Server:
    def __init__(self, world: World):
        self.world = world
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.log_path = world.home / "server.log"
        self.proc: subprocess.Popen | None = None

    def start(self, timeout: float = 40.0) -> "Server":
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "e2e" / "run_server.py"), "--config", str(self.world.config_path),
             "--port", str(self.port)],
            cwd=ROOT, env=self.world.env, stdout=log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                text = self.log_path.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(f"서버가 바로 죽었다:\n{text}")
            try:
                urllib.request.urlopen(f"{self.url}/api/first-run", timeout=1).read()
                return self
            except Exception:
                time.sleep(0.2)
        self.stop()
        raise RuntimeError("서버가 제한 시간 안에 시작되지 않았다")

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        self.proc.wait(timeout=10)

    def restart(self) -> None:
        self.stop()
        self.start()

    def api(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(f"{self.url}{path}", data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None
