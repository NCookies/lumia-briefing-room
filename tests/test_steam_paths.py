from pathlib import Path

import pytest

from lumia_briefing_room.steam_paths import (
    discover_recording_root,
    find_steam_install_path,
    parse_vdf,
    read_background_record_path,
    read_buffer_minutes_override,
)

# research.md §1.1 / 실제 localconfig.vdf 에서 그대로 가져온 조각 (tab 구분자 실측 그대로).
REAL_SAMPLE = (
    '"UserLocalConfigStore"\n'
    "{\n"
    '\t"GameRecording"\n'
    "\t{\n"
    '\t\t"BackgroundRecordMode"\t\t"1"\n'
    '\t\t"PerGameSettings"\n'
    "\t\t{\n"
    '\t\t\t"2162800"\n'
    "\t\t\t{\n"
    '\t\t\t\t"enabled"\t\t"0"\n'
    '\t\t\t\t"minutes"\t\t"120"\n'
    "\t\t\t}\n"
    '\t\t\t"1049590"\n'
    "\t\t\t{\n"
    '\t\t\t\t"enabled"\t\t"1"\n'
    '\t\t\t\t"minutes"\t\t"45"\n'
    "\t\t\t}\n"
    "\t\t}\n"
    '\t\t"BackgroundRecordPath"\t\t"H:\\\\steam video"\n'
    "\t}\n"
    "}\n"
)


def _write_localconfig(steam_path: Path, account_id: str, vdf_text: str) -> None:
    config_dir = steam_path / "userdata" / account_id / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "localconfig.vdf").write_text(vdf_text, encoding="utf-8")


def test_parse_vdf_reads_nested_blocks_and_unescapes_backslashes():
    data = parse_vdf(REAL_SAMPLE)

    game_recording = data["UserLocalConfigStore"]["GameRecording"]
    assert game_recording["BackgroundRecordMode"] == "1"
    assert game_recording["BackgroundRecordPath"] == "H:\\steam video"
    assert game_recording["PerGameSettings"]["1049590"]["minutes"] == "45"


def test_read_background_record_path_found(tmp_path):
    _write_localconfig(tmp_path, "100000001", REAL_SAMPLE)

    assert read_background_record_path(tmp_path) == Path("H:\\steam video")


def test_read_background_record_path_picks_account_that_has_it_set(tmp_path):
    empty_sample = '"UserLocalConfigStore"\n{\n\t"GameRecording"\n\t{\n\t\t"BackgroundRecordMode"\t\t"0"\n\t}\n}\n'
    _write_localconfig(tmp_path, "100000002", empty_sample)
    _write_localconfig(tmp_path, "100000001", REAL_SAMPLE)

    assert read_background_record_path(tmp_path) == Path("H:\\steam video")


def test_read_background_record_path_none_when_no_account_has_it(tmp_path):
    empty_sample = '"UserLocalConfigStore"\n{\n\t"GameRecording"\n\t{\n\t\t"BackgroundRecordMode"\t\t"0"\n\t}\n}\n'
    _write_localconfig(tmp_path, "100000002", empty_sample)

    assert read_background_record_path(tmp_path) is None


def test_read_background_record_path_none_when_no_userdata_dir(tmp_path):
    assert read_background_record_path(tmp_path) is None


def test_read_buffer_minutes_override_found(tmp_path):
    _write_localconfig(tmp_path, "100000001", REAL_SAMPLE)

    assert read_buffer_minutes_override(tmp_path, "1049590") == 45.0
    assert read_buffer_minutes_override(tmp_path, "2162800") == 120.0


def test_read_buffer_minutes_override_none_when_appid_absent(tmp_path):
    _write_localconfig(tmp_path, "100000001", REAL_SAMPLE)

    assert read_buffer_minutes_override(tmp_path, "9999999") is None


def test_discover_recording_root_appends_video_subfolder(tmp_path):
    _write_localconfig(tmp_path, "100000001", REAL_SAMPLE)

    assert discover_recording_root(tmp_path) == Path("H:\\steam video") / "video"


def test_discover_recording_root_none_when_background_path_unset(tmp_path):
    empty_sample = '"UserLocalConfigStore"\n{\n\t"GameRecording"\n\t{\n\t\t"BackgroundRecordMode"\t\t"0"\n\t}\n}\n'
    _write_localconfig(tmp_path, "100000002", empty_sample)

    assert discover_recording_root(tmp_path) is None


def test_discover_recording_root_none_when_steam_path_none(monkeypatch):
    monkeypatch.setattr(
        "lumia_briefing_room.steam_paths.find_steam_install_path", lambda: None
    )
    assert discover_recording_root(None) is None


def test_find_steam_install_path_matches_real_registry_when_steam_installed():
    result = find_steam_install_path()
    if result is None:
        pytest.skip("이 PC 에는 스팀이 설치되어 있지 않다")
    assert result.exists()
