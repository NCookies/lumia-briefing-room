import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import release_tools  # noqa: E402

CHANGELOG = """# 패치노트

## [0.2.0] - 2026-10-01

### 새로 생겼어요
- 클립 목록에서 게임별로 묶어 볼 수 있어요.

### 고쳤어요
- 재생이 멈추던 문제

## [0.1.3] - 2026-09-25

### 좋아졌어요
- 진단 정보를 버튼 한 번으로 보낼 수 있어요.
"""


def test_tag_must_be_v_major_minor_patch():
    assert release_tools.parse_tag("v0.1.3") == "0.1.3"
    assert release_tools.parse_tag("v12.0.10") == "12.0.10"


@pytest.mark.parametrize("tag", ["0.1.3", "v0.1", "v0.1.3-rc1", "v0.1.3.4", "release-1", "", "v01.2.3"])
def test_malformed_tags_are_rejected(tag):
    with pytest.raises(release_tools.ReleaseError):
        release_tools.parse_tag(tag)


def test_tag_matching_the_code_version_passes():
    assert release_tools.verify_tag("v0.1.3", "0.1.3") == "0.1.3"


def test_tag_that_differs_from_the_code_version_fails_with_both_values():
    with pytest.raises(release_tools.ReleaseError) as caught:
        release_tools.verify_tag("v0.2.0", "0.1.3")
    assert "0.2.0" in str(caught.value) and "0.1.3" in str(caught.value)


def test_notes_are_the_section_for_that_version_only():
    notes = release_tools.extract_notes(CHANGELOG, "0.1.3")
    assert notes == "### 좋아졌어요\n- 진단 정보를 버튼 한 번으로 보낼 수 있어요."


def test_notes_stop_at_the_next_version_heading():
    notes = release_tools.extract_notes(CHANGELOG, "0.2.0")
    assert "재생이 멈추던 문제" in notes
    assert "0.1.3" not in notes and "진단 정보" not in notes


def test_missing_version_section_fails_so_a_release_never_ships_without_notes():
    with pytest.raises(release_tools.ReleaseError) as caught:
        release_tools.extract_notes(CHANGELOG, "0.3.0")
    assert "CHANGELOG" in str(caught.value)


def test_empty_version_section_fails():
    with pytest.raises(release_tools.ReleaseError):
        release_tools.extract_notes("## [0.1.0] - 2026-01-01\n\n## [0.0.9]\n- x\n", "0.1.0")


def test_version_heading_is_matched_exactly_not_by_prefix():
    text = "## [0.1.30] - 2026-01-01\n- 다른 버전\n"
    with pytest.raises(release_tools.ReleaseError):
        release_tools.extract_notes(text, "0.1.3")


def test_checksum_line_uses_the_sha256sum_binary_format():
    assert release_tools.checksum_line("ab" * 32, "setup.exe") == f"{'ab' * 32} *setup.exe\n"


def test_checksum_file_is_written_next_to_the_installer_and_matches_its_content(tmp_path: Path):
    installer = tmp_path / "LumiaBriefingRoom-0.1.3-setup.exe"
    installer.write_bytes(b"installer bytes")

    digest, checksum = release_tools.write_checksum_file(installer)

    assert digest == hashlib.sha256(b"installer bytes").hexdigest()
    assert checksum == tmp_path / "LumiaBriefingRoom-0.1.3-setup.exe.sha256"
    assert release_tools.parse_checksum(checksum.read_text(encoding="utf-8")) == (digest, installer.name)


def test_parse_checksum_accepts_text_mode_lines_too():
    assert release_tools.parse_checksum(f"{'CD' * 32}  setup.exe\n") == ("cd" * 32, "setup.exe")


@pytest.mark.parametrize("text", ["", "nothing here", f"{'z' * 64} *a.exe", f"{'a' * 63} *a.exe"])
def test_parse_checksum_rejects_garbage(text):
    with pytest.raises(release_tools.ReleaseError):
        release_tools.parse_checksum(text)


def test_asset_names_follow_the_version():
    assert release_tools.asset_names("0.1.3") == (
        "LumiaBriefingRoom-0.1.3-setup.exe",
        "LumiaBriefingRoom-0.1.3-setup.exe.sha256",
    )


def test_release_body_lists_notes_then_checksum():
    body = release_tools.release_body("### 좋아졌어요\n- 하나", installer="a-setup.exe", sha256="ab" * 32)
    assert body.startswith("### 좋아졌어요\n- 하나")
    assert "a-setup.exe" in body and "ab" * 32 in body
    assert "virustotal" not in body.lower()


def test_release_body_with_scan_link_mentions_false_positives():
    link = release_tools.virustotal_file_url("ab" * 32)
    body = release_tools.release_body("- x", installer="a.exe", sha256="ab" * 32, virustotal_url=link)
    assert link in body
    assert "오탐" in body


def test_virustotal_url_points_at_the_file_by_hash():
    assert release_tools.virustotal_file_url("ab" * 32) == f"https://www.virustotal.com/gui/file/{'ab' * 32}"


def test_multipart_body_carries_the_file_under_the_file_field():
    body, content_type = release_tools.multipart_file("setup.exe", b"\x00\x01data", boundary="BOUND")
    assert content_type == "multipart/form-data; boundary=BOUND"
    assert body.startswith(b"--BOUND\r\n")
    assert b'name="file"; filename="setup.exe"' in body
    assert b"\r\n\r\n\x00\x01data\r\n--BOUND--\r\n" in body


def test_prepare_writes_checksum_and_notes_and_checks_the_tag(tmp_path: Path):
    installer = tmp_path / release_tools.asset_names("0.1.3")[0]
    installer.write_bytes(b"x")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    notes_out = tmp_path / "notes.md"

    digest = release_tools.prepare(
        tag="v0.1.3", version="0.1.3", changelog=changelog, dist=tmp_path, notes_out=notes_out
    )

    assert digest == hashlib.sha256(b"x").hexdigest()
    assert (tmp_path / (installer.name + ".sha256")).exists()
    assert "진단 정보" in notes_out.read_text(encoding="utf-8")
    assert digest in notes_out.read_text(encoding="utf-8")


def test_prepare_refuses_a_tag_that_differs_from_the_version(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    with pytest.raises(release_tools.ReleaseError):
        release_tools.prepare(
            tag="v0.2.0", version="0.1.3", changelog=changelog, dist=tmp_path, notes_out=tmp_path / "n.md"
        )


def test_prepare_fails_when_the_installer_was_not_built(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    with pytest.raises(release_tools.ReleaseError) as caught:
        release_tools.prepare(
            tag="v0.1.3", version="0.1.3", changelog=changelog, dist=tmp_path, notes_out=tmp_path / "n.md"
        )
    assert "설치기" in str(caught.value)
