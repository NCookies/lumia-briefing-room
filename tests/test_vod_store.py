from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.vod_store import StateCache, load_index, save_index, vod_id


def make_file(path, data: bytes):
    path.write_bytes(data)
    return path


def state(t, **kw):
    base = dict(
        t=t, combat=True, face_value=101.5, face_sat=22.0, k=3, a=None,
        day_night="day", spectating=False, dead_teammates=(1,), region=None,
        enemy_rings=2, game_day=4, team_combat=False, ally_rings=1,
    )
    base.update(kw)
    return FrameState(**base)


def test_vod_id_depends_on_content_not_on_path(tmp_path):
    data = bytes(range(256)) * 10_000
    a = make_file(tmp_path / "a.mp4", data)
    (tmp_path / "moved").mkdir()
    b = make_file(tmp_path / "moved" / "b.mp4", data)

    assert vod_id(a) == vod_id(b)
    assert len(vod_id(a)) == 12


def test_vod_id_changes_when_content_or_size_changes(tmp_path):
    data = bytes(range(256)) * 10_000
    a = make_file(tmp_path / "a.mp4", data)
    b = make_file(tmp_path / "b.mp4", data + b"x")
    c = make_file(tmp_path / "c.mp4", b"y" + data[1:])

    assert len({vod_id(a), vod_id(b), vod_id(c)}) == 3


def test_vod_id_reads_head_and_tail_of_large_files(tmp_path):
    big = tmp_path / "big.mp4"
    with open(big, "wb") as f:
        f.write(b"A" * 1024 * 1024)
        f.write(b"M" * 3 * 1024 * 1024)
        f.write(b"Z" * 1024 * 1024)
    first = vod_id(big)
    with open(big, "r+b") as f:
        f.seek(2 * 1024 * 1024)
        f.write(b"changed-in-the-middle")

    assert vod_id(big) == first


def test_state_cache_round_trips_frame_states(tmp_path):
    cache = StateCache(tmp_path / "x.states.jsonl.gz")
    states = [state(1.0), state(2.0, k=None, dead_teammates=None, day_night=None)]

    cache.append(states)

    assert cache.load() == states


def test_state_cache_appends_across_calls_and_reports_last_time(tmp_path):
    cache = StateCache(tmp_path / "x.states.jsonl.gz")
    assert cache.load() == [] and cache.last_t() is None

    cache.append([state(1.0), state(2.0)])
    cache.append([state(3.0)])

    assert [s.t for s in cache.load()] == [1.0, 2.0, 3.0]
    assert cache.last_t() == 3.0


def test_state_cache_survives_a_truncated_tail(tmp_path):
    path = tmp_path / "x.states.jsonl.gz"
    cache = StateCache(path)
    cache.append([state(1.0), state(2.0)])
    cache.append([state(3.0), state(4.0)])
    raw = path.read_bytes()
    path.write_bytes(raw[:-6])

    loaded = cache.load()

    assert [s.t for s in loaded][:2] == [1.0, 2.0]
    cache.append([state(9.0)])
    assert [s.t for s in cache.load()][-1] == 9.0


def test_state_cache_clear_removes_everything(tmp_path):
    cache = StateCache(tmp_path / "x.states.jsonl.gz")
    cache.append([state(1.0)])

    cache.clear()

    assert cache.load() == []
    assert not (tmp_path / "x.states.jsonl.gz").exists()


def test_index_round_trip_and_atomic_write(tmp_path):
    index = {"id": "abc", "path": "H:/vod/a.mp4", "status": "done", "games": [{"index": 1}]}

    save_index(tmp_path, index)

    assert load_index(tmp_path, "abc") == index
    assert load_index(tmp_path, "missing") is None
    assert not list((tmp_path / ".vods").glob("*.tmp"))
