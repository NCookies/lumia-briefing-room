import logging
from pathlib import Path

from lumia_briefing_room import paths


def test_resource_dir_in_source_tree_is_repo_root():
    root = paths.resource_dir(frozen=False)
    assert (root / "data" / "characters.json").exists()
    assert (root / "pyproject.toml").exists()


def test_resource_dir_frozen_prefers_meipass(tmp_path: Path):
    assert paths.resource_dir(frozen=True, meipass=str(tmp_path), executable="C:/app/app.exe") == tmp_path


def test_resource_dir_frozen_falls_back_to_exe_dir(tmp_path: Path):
    exe = tmp_path / "LumiaBriefingRoom.exe"
    assert paths.resource_dir(frozen=True, meipass=None, executable=str(exe)) == tmp_path


def test_resource_dir_env_override_wins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    assert paths.resource_dir(frozen=False) == tmp_path
    assert paths.resource_dir(frozen=True, meipass="X", executable="Y") == tmp_path


def test_data_paths_are_under_resource_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    assert paths.characters_path() == tmp_path / "data" / "characters.json"
    assert paths.templates_dir("digits") == tmp_path / "data" / "templates" / "digits"
    assert paths.bundled_ffmpeg_dir() == tmp_path / "vendor" / "ffmpeg"


def test_is_frozen_false_in_tests():
    assert paths.is_frozen() is False


def test_warn_missing_logs_once(caplog):
    paths._warned.clear()
    with caplog.at_level(logging.WARNING, logger="lumia_briefing_room.paths"):
        paths.warn_missing("본보기", Path("a/b.npz"))
        paths.warn_missing("본보기", Path("a/b.npz"))
    assert len([r for r in caplog.records if "b.npz" in r.getMessage()]) == 1
