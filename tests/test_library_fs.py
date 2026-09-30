from pathlib import Path

import pytest

from lumia_briefing_room.pipeline.library_fs import LibraryError, LibraryRoots


def touch(path: Path, data: bytes = b"v"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def single(tmp_path):
    root = tmp_path / "클립"
    root.mkdir()
    return LibraryRoots([("클립", root)], single=True), root


@pytest.fixture
def legacy(tmp_path):
    a, b = tmp_path / "clips", tmp_path / "vod"
    a.mkdir()
    b.mkdir()
    return LibraryRoots([("스팀 녹화", a), ("영상 파일", b)], single=False), a, b


def test_resolve_maps_relative_paths_inside_the_root(single):
    roots, root = single
    assert roots.resolve("") == root
    assert roots.resolve("캐릭터/아야") == root / "캐릭터" / "아야"
    assert roots.rel_of(root / "캐릭터" / "아야") == "캐릭터/아야"
    assert roots.rel_of(root) == ""


@pytest.mark.parametrize("bad", ["..", "../x", "a/../../x", "/abs", "C:/x", "C:\\x", "a\\..\\..\\x", ".cache", "a/.staging"])
def test_unsafe_paths_are_rejected(single, bad):
    roots, _ = single
    with pytest.raises(LibraryError):
        roots.resolve(bad)


def test_a_link_pointing_outside_the_root_is_rejected(single, tmp_path):
    roots, root = single
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("심볼릭 링크를 만들 권한이 없다")
    with pytest.raises(LibraryError):
        roots.resolve("link")


def test_legacy_layout_has_a_virtual_top_with_two_folders(legacy):
    roots, a, b = legacy
    assert roots.is_virtual("")
    assert [(f["name"], f["rel"]) for f in roots.list_folders("")] == [("스팀 녹화", "스팀 녹화"), ("영상 파일", "영상 파일")]
    assert roots.resolve("스팀 녹화/아야") == a / "아야" and roots.resolve("영상 파일") == b
    assert roots.rel_of(b / "x") == "영상 파일/x"
    with pytest.raises(LibraryError):
        roots.resolve("")  # 가상 최상위는 실제 폴더가 아니다


def test_list_folder_returns_subfolders_and_videos_but_hides_dot_folders_and_temp_files(single):
    roots, root = single
    touch(root / "a.mp4")
    touch(root / "메모.txt")
    touch(root / "b.replace.mp4")
    touch(root / ".cache" / "proxy" / "c.mp4")
    touch(root / "캐릭터" / "아야" / "d.mp4")
    (root / "빈 폴더").mkdir()
    folders, videos = roots.list_folder("")
    assert [f["name"] for f in folders] == ["빈 폴더", "캐릭터"]
    assert [v.name for v in videos] == ["a.mp4"]
    assert {f["name"]: f["clipCount"] for f in folders} == {"빈 폴더": 0, "캐릭터": 1}


def test_make_folder(single):
    roots, root = single
    assert roots.make_folder("", "새 폴더") == "새 폴더"
    assert (root / "새 폴더").is_dir()
    assert roots.make_folder("새 폴더", "안쪽") == "새 폴더/안쪽"
    with pytest.raises(LibraryError):
        roots.make_folder("", "새 폴더")
    for bad in ("", "a/b", "a\\b", "..", ".hidden", "a:b", "x?"):
        with pytest.raises(LibraryError):
            roots.make_folder("", bad)


def test_cannot_create_folders_in_the_virtual_top(legacy):
    roots, *_ = legacy
    with pytest.raises(LibraryError):
        roots.make_folder("", "새 폴더")


def test_rename_a_folder_and_a_video_keeps_the_extension(single):
    roots, root = single
    touch(root / "아야" / "x.mp4")
    assert roots.rename("아야", "아야 모음") == "아야 모음"
    assert roots.rename("아야 모음/x.mp4", "내 클립") == "아야 모음/내 클립.mp4"
    assert (root / "아야 모음" / "내 클립.mp4").exists()
    touch(root / "아야 모음" / "y.mp4")
    with pytest.raises(LibraryError):
        roots.rename("아야 모음/y.mp4", "내 클립")
    with pytest.raises(LibraryError):
        roots.rename("", "x")


def test_move_entries_moves_files_and_folders_and_nothing_on_conflict(single):
    roots, root = single
    touch(root / "a.mp4", b"A")
    touch(root / "묶음" / "b.mp4", b"B")
    (root / "대상").mkdir()
    roots.move(["a.mp4", "묶음"], "대상")
    assert (root / "대상" / "a.mp4").read_bytes() == b"A" and (root / "대상" / "묶음" / "b.mp4").read_bytes() == b"B"
    assert not (root / "묶음").exists()

    touch(root / "a.mp4", b"NEW")
    touch(root / "다른" / "c.mp4")
    with pytest.raises(LibraryError):
        roots.move(["다른", "a.mp4"], "대상")
    assert (root / "a.mp4").exists() and (root / "다른" / "c.mp4").exists(), "충돌하면 아무것도 안 옮긴다"
    assert (root / "대상" / "a.mp4").read_bytes() == b"A"


def test_a_folder_cannot_move_into_itself_or_its_children(single):
    roots, root = single
    touch(root / "a" / "b" / "x.mp4")
    with pytest.raises(LibraryError):
        roots.move(["a"], "a")
    with pytest.raises(LibraryError):
        roots.move(["a"], "a/b")


def test_moving_across_the_legacy_roots_is_allowed(legacy):
    roots, a, b = legacy
    touch(a / "x.mp4", b"X")
    roots.move(["스팀 녹화/x.mp4"], "영상 파일")
    assert (b / "x.mp4").read_bytes() == b"X" and not (a / "x.mp4").exists()


def test_moving_to_the_virtual_top_is_refused(legacy):
    roots, a, _ = legacy
    touch(a / "x.mp4")
    with pytest.raises(LibraryError):
        roots.move(["스팀 녹화/x.mp4"], "")


def test_collect_videos_lists_every_video_under_entries(single):
    roots, root = single
    touch(root / "a.mp4")
    touch(root / "묶음" / "깊이" / "b.mp4")
    touch(root / "묶음" / "메모.txt")
    assert sorted(v.name for v in roots.collect_videos(["a.mp4", "묶음"])) == ["a.mp4", "b.mp4"]


def test_the_root_folder_itself_cannot_be_deleted_or_moved(single, legacy):
    roots, _ = single
    with pytest.raises(LibraryError):
        roots.ensure_entry("")
    roots.ensure_entry("캐릭터")
    lroots, *_ = legacy
    with pytest.raises(LibraryError):
        lroots.ensure_entry("스팀 녹화")
    lroots.ensure_entry("스팀 녹화/아야")


def test_backslashes_are_not_allowed_in_exported_file_names():
    from lumia_briefing_room.api.export import sanitize_filename

    assert sanitize_filename("a" + chr(92) + "b") == "a_b"
