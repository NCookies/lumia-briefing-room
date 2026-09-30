import json
from pathlib import Path

import pytest

from lumia_briefing_room.config import PathsConfig, resolve_paths
from lumia_briefing_room.pipeline.storage_migrate import (
    StorageMoveError,
    execute_storage_move,
    plan_storage_move,
    previous_paths,
    undo_storage_move,
)

STEAM_KEY = "20260928_160025"
VOD_KEY = "vod_3df9b3313b4e_g01"


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))


def legacy(tmp_path):
    base = tmp_path / "old"
    cfg = PathsConfig(clips=base / "clips", vod_clips=base / "vod", games=base / "games")
    (base / "clips" / "sub").mkdir(parents=True)
    (base / "vod").mkdir()
    (base / "clips" / "a.mp4").write_bytes(b"A")
    (base / "clips" / "sub" / "b.mp4").write_bytes(b"BB")
    (base / "clips" / "notes.txt").write_text("mine", encoding="utf-8")
    (base / "clips" / ".proxy").mkdir()
    (base / "clips" / ".proxy" / "a.mp4").write_bytes(b"P")
    (base / "vod" / "vod_x.mp4").write_bytes(b"V")
    for key in (STEAM_KEY, VOD_KEY):
        (base / "games" / key).mkdir(parents=True)
        (base / "games" / key / "full.mp4").write_bytes(b"FULL" + key.encode())
        (base / "games" / key / "game.json").write_text(json.dumps({"gameKey": key}), encoding="utf-8")
        (base / "games" / key / "result.jpg").write_bytes(b"jpg")
    (base / "games" / ".staging").mkdir()
    return cfg


def plan(tmp_path, old_cfg, **new):
    return plan_storage_move(resolve_paths(old_cfg), resolve_paths(PathsConfig(root=tmp_path / "store", **new)))


def test_plan_sends_each_kind_to_its_new_folder(tmp_path):
    p = plan(tmp_path, legacy(tmp_path))
    dsts = {str(d.relative_to(tmp_path / "store")).replace("\\", "/") for _, d in p.pairs}
    assert "clips/자동 보관/a.mp4" in dsts and "clips/자동 보관/sub/b.mp4" in dsts
    assert "clips/자동 보관/vod_x.mp4" in dsts
    assert f"full_video/steam_replay/{STEAM_KEY}/full.mp4" in dsts and f"full_video/vod/{VOD_KEY}/game.json" in dsts
    assert ".cache/proxy/a.mp4" in dsts
    assert not any("notes.txt" in d for d in dsts), "영상이 아닌 파일은 안 옮긴다"
    assert not any(".staging" in d for d in dsts)
    assert p.total_bytes > 0


def test_full_video_override_changes_only_the_game_destination(tmp_path):
    p = plan(tmp_path, legacy(tmp_path), full_videos=tmp_path / "hdd")
    games = [d for _, d in p.pairs if d.name in ("full.mp4", "game.json")]
    assert games and all(tmp_path / "hdd" in d.parents for d in games)
    clips = [d for _, d in p.pairs if d.name == "a.mp4" and "clips" in d.parts]
    assert clips and all(tmp_path / "store" in d.parents for d in clips)


def test_game_json_is_moved_after_the_other_files_of_its_folder(tmp_path):
    p = plan(tmp_path, legacy(tmp_path))
    names = [s.name for s, _ in p.pairs if s.parent.name == STEAM_KEY]
    assert names[-1] == "game.json"


def test_execute_moves_everything_and_keeps_unrelated_files(tmp_path):
    cfg = legacy(tmp_path)
    p = plan(tmp_path, cfg)
    ledger = tmp_path / "local" / "ledger.jsonl"
    seen = []

    moved = execute_storage_move(p, ledger, previous=previous_paths(cfg), progress=lambda d, t: seen.append((d, t)))

    store = tmp_path / "store"
    assert moved == len(p.pairs)
    assert (store / "clips" / "자동 보관" / "sub" / "b.mp4").read_bytes() == b"BB"
    assert (store / "full_video" / "steam_replay" / STEAM_KEY / "full.mp4").read_bytes().startswith(b"FULL")
    assert (store / ".cache" / "proxy" / "a.mp4").read_bytes() == b"P"
    old = tmp_path / "old"
    assert (old / "clips" / "notes.txt").exists()
    assert not (old / "clips" / "a.mp4").exists() and not (old / "games" / STEAM_KEY).exists()
    assert not (old / "clips" / "sub").exists(), "비게 된 하위 폴더는 치운다"
    assert seen[0][0] == 0 and seen[-1][0] == seen[-1][1] == p.total_bytes


def test_running_the_move_twice_is_harmless(tmp_path):
    cfg = legacy(tmp_path)
    ledger = tmp_path / "local" / "ledger.jsonl"
    execute_storage_move(plan(tmp_path, cfg), ledger, previous=previous_paths(cfg))
    again = plan(tmp_path, cfg)
    assert again.pairs == []
    assert execute_storage_move(again, ledger, previous=previous_paths(cfg)) == 0


def test_interrupted_move_resumes_where_it_stopped(tmp_path):
    cfg = legacy(tmp_path)
    ledger = tmp_path / "local" / "ledger.jsonl"
    p = plan(tmp_path, cfg)
    calls = {"n": 0}

    def boom(done, total):
        calls["n"] += 1
        if calls["n"] == 4:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_storage_move(p, ledger, previous=previous_paths(cfg), progress=boom)
    rest = plan(tmp_path, cfg)
    assert 0 < len(rest.pairs) < len(p.pairs)
    execute_storage_move(rest, ledger, previous=previous_paths(cfg))
    assert plan(tmp_path, cfg).pairs == []
    assert (tmp_path / "store" / "full_video" / "vod" / VOD_KEY / "game.json").exists()


def test_conflict_refuses_before_moving_anything(tmp_path):
    cfg = legacy(tmp_path)
    clash = tmp_path / "store" / "clips" / "자동 보관" / "a.mp4"
    clash.parent.mkdir(parents=True)
    clash.write_bytes(b"someone else")
    with pytest.raises(StorageMoveError):
        plan(tmp_path, cfg)
    assert (tmp_path / "old" / "clips" / "a.mp4").exists() and clash.read_bytes() == b"someone else"


def test_new_folder_inside_the_old_one_is_refused(tmp_path):
    cfg = legacy(tmp_path)
    with pytest.raises(StorageMoveError):
        plan_storage_move(resolve_paths(cfg), resolve_paths(PathsConfig(root=tmp_path / "old" / "clips" / "inner")))


def test_same_root_moves_nothing(tmp_path):
    p1 = PathsConfig(root=tmp_path / "store")
    assert plan_storage_move(resolve_paths(p1), resolve_paths(p1)).pairs == []


def test_moving_between_roots_keeps_user_subfolders(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    cfg = PathsConfig(root=a)
    (a / "clips" / "아야").mkdir(parents=True)
    (a / "clips" / "아야" / "x.mp4").write_bytes(b"X")
    (a / "clips" / "자동 보관").mkdir()
    (a / "clips" / "자동 보관" / "y.mp4").write_bytes(b"Y")
    (a / "full_video" / "steam_replay" / STEAM_KEY).mkdir(parents=True)
    (a / "full_video" / "steam_replay" / STEAM_KEY / "game.json").write_text("{}", encoding="utf-8")
    p = plan_storage_move(resolve_paths(cfg), resolve_paths(PathsConfig(root=b)))
    execute_storage_move(p, tmp_path / "local" / "l.jsonl", previous=previous_paths(cfg))
    assert (b / "clips" / "아야" / "x.mp4").read_bytes() == b"X" and (b / "clips" / "자동 보관" / "y.mp4").exists()
    assert (b / "full_video" / "steam_replay" / STEAM_KEY / "game.json").exists()


def test_undo_puts_everything_back_and_returns_the_previous_paths(tmp_path):
    cfg = legacy(tmp_path)
    ledger = tmp_path / "local" / "ledger.jsonl"
    execute_storage_move(plan(tmp_path, cfg), ledger, previous=previous_paths(cfg))

    restored = undo_storage_move(ledger)

    assert restored["clips"] == str(cfg.clips) and restored["games"] == str(cfg.games) and restored["root"] is None
    assert (tmp_path / "old" / "clips" / "sub" / "b.mp4").read_bytes() == b"BB"
    assert (tmp_path / "old" / "games" / VOD_KEY / "full.mp4").exists()
    assert not ledger.exists()
    assert plan(tmp_path, cfg).pairs, "되돌린 뒤엔 다시 옮길 수 있다"


def test_undo_refuses_when_an_original_spot_was_reused(tmp_path):
    cfg = legacy(tmp_path)
    ledger = tmp_path / "local" / "ledger.jsonl"
    execute_storage_move(plan(tmp_path, cfg), ledger, previous=previous_paths(cfg))
    (tmp_path / "old" / "clips" / "a.mp4").write_bytes(b"new file")
    with pytest.raises(StorageMoveError):
        undo_storage_move(ledger)
    assert (tmp_path / "store" / "clips" / "자동 보관" / "a.mp4").exists()


def test_undo_without_a_ledger_returns_none(tmp_path):
    assert undo_storage_move(tmp_path / "none.jsonl") is None


def test_empty_user_subfolders_move_with_the_videos(tmp_path):
    cfg = legacy(tmp_path)
    (tmp_path / "old" / "clips" / "비어 있는 폴더" / "안쪽").mkdir(parents=True)
    p = plan(tmp_path, cfg)
    execute_storage_move(p, tmp_path / "local" / "l.jsonl", previous=previous_paths(cfg))
    assert (tmp_path / "store" / "clips" / "자동 보관" / "비어 있는 폴더" / "안쪽").is_dir()
    assert (tmp_path / "store" / "clips" / "자동 보관" / "sub").is_dir()
    assert not (tmp_path / "old" / "clips" / "비어 있는 폴더").exists()


def test_emptied_legacy_folders_are_removed_but_a_folder_with_user_files_stays(tmp_path):
    cfg = legacy(tmp_path)
    execute_storage_move(plan(tmp_path, cfg), tmp_path / "local" / "l.jsonl", previous=previous_paths(cfg))
    old = tmp_path / "old"
    assert not (old / "vod").exists() and not (old / "games").exists(), "비게 된 옛 폴더는 치운다(숨김 작업 폴더 포함)"
    assert (old / "clips" / "notes.txt").exists(), "사용자 파일이 남은 폴더는 그대로 둔다"
    assert not (old / "clips" / ".proxy").exists()


def test_moving_between_roots_removes_the_old_structure_but_keeps_the_root_folder(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    cfg = PathsConfig(root=a)
    (a / "clips" / "아야").mkdir(parents=True)
    (a / "clips" / "빈 폴더").mkdir()
    (a / "clips" / "아야" / "x.mp4").write_bytes(b"X")
    (a / "full_video" / "steam_replay" / STEAM_KEY).mkdir(parents=True)
    (a / "full_video" / "steam_replay" / STEAM_KEY / "game.json").write_text("{}", encoding="utf-8")
    (a / ".cache" / "proxy").mkdir(parents=True)
    (a / ".staging").mkdir()
    (a / "메모.txt").write_text("내 파일", encoding="utf-8")
    execute_storage_move(
        plan_storage_move(resolve_paths(cfg), resolve_paths(PathsConfig(root=b))), tmp_path / "local" / "l.jsonl",
        previous=previous_paths(cfg),
    )
    assert (b / "clips" / "빈 폴더").is_dir() and (b / "clips" / "아야" / "x.mp4").exists()
    assert a.is_dir() and (a / "메모.txt").exists()
    assert not any(p.name in ("clips", "full_video", ".cache", ".staging") for p in a.iterdir())


def test_undo_brings_back_empty_folders_too(tmp_path):
    cfg = legacy(tmp_path)
    (tmp_path / "old" / "clips" / "비어 있는 폴더").mkdir()
    ledger = tmp_path / "local" / "l.jsonl"
    execute_storage_move(plan(tmp_path, cfg), ledger, previous=previous_paths(cfg))
    undo_storage_move(ledger)
    assert (tmp_path / "old" / "clips" / "비어 있는 폴더").is_dir()
    assert not (tmp_path / "store" / "clips" / "자동 보관" / "비어 있는 폴더").exists()


def test_old_clips_folder_named_clips_is_reorganized_in_place(tmp_path):
    """옛 기본 클립 폴더(`<루트>\clips`)가 새 `clips` 와 같은 이름이라, 저장 폴더를 그 상위로 고르면 안에서 `자동 보관` 으로 들어간다."""
    cfg = legacy(tmp_path)
    root = tmp_path / "old"
    new_cfg = PathsConfig(root=root)
    (root / "clips" / "빈 폴더").mkdir()
    p = plan_storage_move(resolve_paths(cfg), resolve_paths(new_cfg))
    execute_storage_move(p, tmp_path / "local" / "ledger.jsonl", previous=previous_paths(cfg))
    assert (root / "clips" / "자동 보관" / "a.mp4").read_bytes() == b"A"
    assert (root / "clips" / "자동 보관" / "sub" / "b.mp4").read_bytes() == b"BB"
    assert (root / "clips" / "자동 보관" / "vod_x.mp4").read_bytes() == b"V"
    assert (root / "clips" / "자동 보관" / "빈 폴더").is_dir()
    assert not (root / "clips" / "a.mp4").exists() and not (root / "clips" / "sub").exists()
    assert (root / "clips" / "notes.txt").exists(), "영상이 아닌 파일은 제자리에 둔다"
    assert (root / "full_video" / "steam_replay" / STEAM_KEY / "full.mp4").exists()
    assert plan_storage_move(resolve_paths(cfg), resolve_paths(new_cfg)).pairs == []


def test_in_place_reorganization_can_be_undone(tmp_path):
    cfg = legacy(tmp_path)
    root = tmp_path / "old"
    ledger = tmp_path / "local" / "ledger.jsonl"
    p = plan_storage_move(resolve_paths(cfg), resolve_paths(PathsConfig(root=root)))
    execute_storage_move(p, ledger, previous=previous_paths(cfg))
    previous = undo_storage_move(ledger)
    assert previous["clips"] == str(root / "clips")
    assert (root / "clips" / "a.mp4").read_bytes() == b"A" and (root / "clips" / "sub" / "b.mp4").exists()
    assert (root / "vod" / "vod_x.mp4").exists() and not (root / "clips" / "자동 보관" / "a.mp4").exists()
