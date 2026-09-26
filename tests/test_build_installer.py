import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_installer  # noqa: E402


def test_installer_file_name_carries_the_version():
    assert build_installer.installer_name("0.1.0") == "LumiaBriefingRoom-0.1.0-setup.exe"


def test_iscc_is_found_in_a_user_scope_install(tmp_path: Path, monkeypatch):
    iscc = tmp_path / "Programs" / "Inno Setup 6" / "ISCC.exe"
    iscc.parent.mkdir(parents=True)
    iscc.write_text("x", encoding="utf-8")
    monkeypatch.setattr(build_installer, "ISCC_CANDIDATES", (iscc,))
    monkeypatch.setattr("shutil.which", lambda name: None)

    assert build_installer.find_iscc() == iscc


def test_iscc_on_path_is_used_when_no_known_folder_has_it(monkeypatch):
    monkeypatch.setattr(build_installer, "ISCC_CANDIDATES", ())
    monkeypatch.setattr("shutil.which", lambda name: r"C:\tools\ISCC.exe")

    assert build_installer.find_iscc() == Path(r"C:\tools\ISCC.exe")


def test_missing_iscc_is_reported_as_none(monkeypatch):
    monkeypatch.setattr(build_installer, "ISCC_CANDIDATES", ())
    monkeypatch.setattr("shutil.which", lambda name: None)

    assert build_installer.find_iscc() is None


def test_defines_pass_version_and_paths_to_the_script(tmp_path: Path):
    defines = build_installer.iscc_defines(
        version="0.1.0", source_dir=tmp_path / "dist" / "LumiaBriefingRoom", out_dir=tmp_path / "dist",
        icon=tmp_path / "icon.ico", notices=tmp_path / "THIRD_PARTY_NOTICES.md",
    )
    joined = " ".join(defines)

    assert "/DAppVersion=0.1.0" in joined
    assert f"/DSourceDir={tmp_path / 'dist' / 'LumiaBriefingRoom'}" in joined
    assert f"/DOutputDir={tmp_path / 'dist'}" in joined
    assert f"/DAppIcon={tmp_path / 'icon.ico'}" in joined
    assert f"/DNoticesFile={tmp_path / 'THIRD_PARTY_NOTICES.md'}" in joined


def test_build_refuses_to_run_without_a_built_app(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(build_installer, "ROOT", tmp_path)
    monkeypatch.setattr(build_installer, "find_iscc", lambda: Path("ISCC.exe"))

    with pytest.raises(build_installer.InstallerError, match="build.bat"):
        build_installer.build(version="0.1.0")


def test_build_refuses_without_iscc(tmp_path: Path, monkeypatch):
    app = tmp_path / "dist" / "LumiaBriefingRoom"
    app.mkdir(parents=True)
    (app / "LumiaBriefingRoom.exe").write_text("x", encoding="utf-8")
    monkeypatch.setattr(build_installer, "ROOT", tmp_path)
    monkeypatch.setattr(build_installer, "find_iscc", lambda: None)

    with pytest.raises(build_installer.InstallerError, match="Inno Setup"):
        build_installer.build(version="0.1.0")


ISS = (Path(__file__).resolve().parents[1] / "installer" / "lumia.iss").read_text(encoding="utf-8")


def test_installer_script_installs_without_admin_rights():
    assert "PrivilegesRequired=lowest" in ISS
    assert "DefaultDirName={autopf}\\LumiaBriefingRoom" in ISS


def test_installer_script_closes_a_running_app_through_the_single_instance_mutex():
    """앱이 쓰는 이름 있는 뮤텍스와 같아야 설치기가 실행 중인 앱을 감지한다."""
    from lumia_briefing_room.single_instance import DEFAULT_NAME

    assert f"AppMutex={DEFAULT_NAME}" in ISS


def test_installer_script_removes_the_autostart_value_on_uninstall():
    assert "CurrentVersion\\Run" in ISS
    assert "uninsdeletevalue" in ISS
    assert "ValueName: \"LumiaBriefingRoom\"" in ISS


def _directives() -> list[str]:
    """주석(;, //)을 뺀 실제 지시문 줄만 본다."""
    lines = []
    for raw in ISS.splitlines():
        line = raw.strip()
        if line and not line.startswith((";", "//")):
            lines.append(line)
    return lines


def test_installer_script_only_ever_deletes_the_settings_folder():
    lines = _directives()
    deleting = [line for line in lines if "DelTree" in line or "UninstallDelete" in line]
    assigned = [line for line in lines if "DataDir :=" in line]

    assert deleting == ["DelTree(DataDir, True, True, True);"]
    assert len(assigned) == 1
    assert "{localappdata}\\LumiaBriefingRoom" in assigned[0]
    assert not any("Videos" in line or "{userdocs}" in line for line in lines)


def test_uninstall_asks_before_deleting_settings():
    assert "MsgBox(" in ISS and "usPostUninstall" in ISS


def test_installer_script_ships_the_notices_file():
    assert "NoticesFile" in ISS
    assert "THIRD_PARTY_NOTICES" in ISS


def test_installer_script_offers_a_desktop_shortcut_as_an_option():
    assert "[Tasks]" in ISS
    assert "desktopicon" in ISS


def test_installer_script_uses_korean_display_name_and_version_define():
    assert "루미아 브리핑룸" in ISS
    assert "{#AppVersion}" in ISS


def test_silent_uninstall_does_not_block_on_a_dialog():
    assert "not UninstallSilent" in ISS


def test_installer_script_starts_the_app_and_opens_its_screen_after_an_interactive_install():
    """마침 화면의 "실행" 체크를 놓치거나 이미 첫 실행을 마친 PC 에서도 아무 일도 없어 보이지 않게, 물어보지 않고 화면까지 연다(조용한 설치는 제외)."""
    launch = [line for line in _directives() if '--open-ui' in line]
    assert len(launch) == 1
    assert "skipifsilent" in launch[0] and "nowait" in launch[0] and "postinstall" not in launch[0]
    assert launch[0].startswith('Filename: "{app}\{#AppExe}"')


def test_installer_script_finish_page_says_the_app_is_starting_and_where_to_find_it():
    finished = [line for line in _directives() if line.startswith("FinishedLabel=")]
    assert len(finished) == 1
    assert "브라우저" in finished[0] and "아이콘" in finished[0]
