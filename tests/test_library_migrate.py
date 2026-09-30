import json

import pytest

from lumia_briefing_room.pipeline.library_migrate import (
    MigrationConflict,
    migrate_library,
    undo_migration,
)


def _make_old(old):
    for name in (".thumbs", ".labels", ".games", ".proxy", ".staging"):
        (old / name).mkdir(parents=True, exist_ok=True)
    (old / "a.json").write_text('{"id":"a"}', encoding="utf-8")
    (old / "a.mp4").write_bytes(b"VIDEO-A")
    (old / ".thumbs" / "a.jpg").write_bytes(b"jpg")
    (old / ".labels" / "a.json").write_text('{"label":1}', encoding="utf-8")
    (old / ".games" / "k.json").write_text("{}", encoding="utf-8")
    (old / ".proxy" / "a.mp4").write_bytes(b"PROXY")
    return old


def test_moves_info_files_and_leaves_videos_and_proxy(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    assert migrate_library(old, lib) == 4
    assert json.loads((lib / "a.json").read_text(encoding="utf-8"))["id"] == "a"
    assert (lib / ".thumbs" / "a.jpg").read_bytes() == b"jpg"
    assert (lib / ".labels" / "a.json").exists() and (lib / ".games" / "k.json").exists()
    assert not (old / "a.json").exists() and not (old / ".thumbs" / "a.jpg").exists()
    assert (old / "a.mp4").read_bytes() == b"VIDEO-A"
    assert (old / ".proxy" / "a.mp4").read_bytes() == b"PROXY"
    assert not (lib / "a.mp4").exists()


def test_running_twice_is_the_same(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    migrate_library(old, lib)
    assert migrate_library(old, lib) == 0
    assert (lib / "a.json").exists()


def test_resumes_after_interruption_without_breaking(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    calls = {"n": 0}

    def crash(_src, _dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        migrate_library(old, lib, on_file=crash)
    assert list(old.glob("*.json")) or list((old / ".thumbs").glob("*")) or list((old / ".games").glob("*"))
    assert not list(lib.rglob("*.tmp"))
    migrate_library(old, lib)
    assert {p.name for p in lib.rglob("*") if p.is_file()} >= {"a.json", "a.jpg", "k.json"}
    assert not list(old.rglob("*.json"))


def test_partial_copy_left_by_crash_is_not_mistaken_for_done(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    lib.mkdir()
    (lib / "a.json.tmp").write_text("garbage", encoding="utf-8")
    migrate_library(old, lib)
    assert json.loads((lib / "a.json").read_text(encoding="utf-8"))["id"] == "a"
    assert not (lib / "a.json.tmp").exists()


def test_conflict_with_different_content_moves_nothing(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    (lib / ".thumbs").mkdir(parents=True)
    (lib / ".thumbs" / "a.jpg").write_bytes(b"DIFFERENT")
    with pytest.raises(MigrationConflict):
        migrate_library(old, lib)
    assert (old / "a.json").exists() and (old / ".thumbs" / "a.jpg").read_bytes() == b"jpg"
    assert not (lib / "a.json").exists()


def test_identical_file_already_at_destination_is_accepted(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    (lib / ".thumbs").mkdir(parents=True)
    (lib / ".thumbs" / "a.jpg").write_bytes(b"jpg")
    migrate_library(old, lib)
    assert not (old / ".thumbs" / "a.jpg").exists()
    assert (lib / ".thumbs" / "a.jpg").read_bytes() == b"jpg"


def test_legacy_trash_is_left_untouched_and_does_not_block(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    (old / ".trash").mkdir()
    (old / ".trash" / "x.json").write_text("{}", encoding="utf-8")
    assert migrate_library(old, lib) == 4
    assert (old / ".trash" / "x.json").exists() and not (lib / "x.json").exists()


def test_empty_legacy_trash_folder_is_removed(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    (old / ".trash").mkdir()
    migrate_library(old, lib)
    assert not (old / ".trash").exists()


def test_non_empty_staging_is_left_alone(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    (old / ".staging" / "job").mkdir()
    (old / ".staging" / "job" / "half.mp4").write_bytes(b"x")
    migrate_library(old, lib)
    assert (old / ".staging" / "job" / "half.mp4").exists()
    assert not (lib / ".staging").exists()


def test_empty_staging_folder_is_removed(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    migrate_library(old, lib)
    assert not (old / ".staging").exists()


def test_missing_old_folder_is_a_no_op(tmp_path):
    assert migrate_library(tmp_path / "nope", tmp_path / "lib") == 0


def test_vod_index_folder_is_moved(tmp_path):
    old, lib = tmp_path / "vod", tmp_path / "lib"
    (old / ".vods").mkdir(parents=True)
    (old / ".vods" / "v1.json").write_text("{}", encoding="utf-8")
    (old / ".vods" / "v1.states.jsonl.gz").write_bytes(b"gz")
    assert migrate_library(old, lib) == 2
    assert (lib / ".vods" / "v1.states.jsonl.gz").read_bytes() == b"gz"


def test_undo_restores_original_layout(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    migrate_library(old, lib)
    assert undo_migration(lib) == 4
    assert json.loads((old / "a.json").read_text(encoding="utf-8"))["id"] == "a"
    assert (old / ".thumbs" / "a.jpg").read_bytes() == b"jpg"
    assert not (lib / "a.json").exists()
    assert undo_migration(lib) == 0


def test_undo_refuses_when_original_spot_was_reused(tmp_path):
    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    migrate_library(old, lib)
    (old / "a.json").write_text('{"id":"NEW"}', encoding="utf-8")
    with pytest.raises(MigrationConflict):
        undo_migration(lib)
    assert json.loads((lib / "a.json").read_text(encoding="utf-8"))["id"] == "a"
    assert json.loads((old / "a.json").read_text(encoding="utf-8"))["id"] == "NEW"


def test_cli_dry_run_then_migrate_then_undo(tmp_path, capsys):
    from lumia_briefing_room.cli.library_migrate import main

    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    main(["--old", str(old), "--lib", str(lib), "--dry-run"])
    assert "4개 옮길 예정" in capsys.readouterr().out
    assert (old / "a.json").exists()
    main(["--old", str(old), "--lib", str(lib)])
    assert (lib / "a.json").exists() and not (old / "a.json").exists()
    main(["--old", str(old), "--lib", str(lib), "--undo"])
    assert (old / "a.json").exists() and not (lib / "a.json").exists()


def test_cli_conflict_exits_with_message(tmp_path):
    from lumia_briefing_room.cli.library_migrate import main

    old, lib = _make_old(tmp_path / "old"), tmp_path / "lib"
    lib.mkdir()
    (lib / "a.json").write_text("다른 내용", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--old", str(old), "--lib", str(lib)])
    assert (old / "a.json").exists()
