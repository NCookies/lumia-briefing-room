"""일회성 조사 도구: Player.log의 매치 구간(로컬 시각)을
녹화 세션의 세그먼트 번호로 변환해 본다.

세그먼트 N의 시작 시각 = availabilityStartTime(UTC) + (N-1) * segment_duration
usage: time_map.py <player.log> <session_dir>
"""
import re, sys, os, datetime as dt

LOG, SESSION = sys.argv[1], sys.argv[2]

mpd = open(os.path.join(SESSION, "session.mpd"), encoding="utf-8").read()
m = re.search(r'availabilityStartTime="([^"]+)"', mpd)
if m:
    avail = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    src = "availabilityStartTime"
else:  # type="static" 세션은 폴더명이 UTC 시작 시각
    b = os.path.basename(SESSION.rstrip("/\\"))
    avail = dt.datetime.strptime("_".join(b.split("_")[2:4]), "%Y%m%d_%H%M%S").replace(tzinfo=dt.timezone.utc)
    src = "folder name"
dur = int(re.search(r'duration="(\d+)"', mpd).group(1)) / int(re.search(r'timescale="(\d+)"', mpd).group(1))
print(f"session start (UTC) = {avail.isoformat()}  [{src}]   segment duration = {dur}s\n")

def seg_of(local: dt.datetime) -> float:
    off = (local.astimezone(dt.timezone.utc) - avail).total_seconds()
    return off

TZ = dt.datetime.now().astimezone().tzinfo
LINE = re.compile(r"^\[(\w+)\]\[[^\]]+\]\[([\d\-]+ [\d:,]+)\]\[\d+\]\[([\w:]+)\] (.*)$")
MARK = ("ClientService:StartGame", "OnUpdateGamePlayPhase", "GameResultTeamPlayerSlot",
        "LoadingView:Show", "GameClient:Init")

for raw in open(LOG, encoding="utf-8", errors="replace"):
    mm = LINE.match(raw.rstrip("\n"))
    if not mm or not any(k in mm.group(3) for k in MARK):
        continue
    ts = dt.datetime.strptime(mm.group(2), "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=TZ)
    off = seg_of(ts)
    if off < 0:
        continue
    num = int(off // dur) + 1
    exists = os.path.isfile(os.path.join(SESSION, f"chunk-stream0-{num:05d}.m4s"))
    print(f"{mm.group(2)}  off={off:8.1f}s  seg={num:5d} {'있음' if exists else '없음(삭제)'}  "
          f"{mm.group(3)}  {mm.group(4)[:60]}")
