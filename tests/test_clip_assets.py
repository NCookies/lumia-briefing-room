from pathlib import Path

from lumia_briefing_room.pipeline.clip_assets import resolve_result_image, resolve_thumbnail, stored_asset_path


def test_stored_asset_path_is_relative_inside_base(tmp_path):
    assert stored_asset_path(tmp_path / ".thumbs" / "a.jpg", tmp_path) == ".thumbs/a.jpg"


def test_stored_asset_path_keeps_absolute_outside_base(tmp_path):
    outside = tmp_path / "elsewhere" / "a.jpg"
    assert stored_asset_path(outside, tmp_path / "clips") == str(outside)


def test_resolve_thumbnail_relative_follows_meta_folder(tmp_path):
    (tmp_path / ".thumbs").mkdir()
    (tmp_path / ".thumbs" / "a.jpg").write_bytes(b"x")

    found = resolve_thumbnail(tmp_path / "a.json", {"thumbnailPath": ".thumbs/a.jpg"})

    assert found == tmp_path / ".thumbs" / "a.jpg"


def test_resolve_thumbnail_stale_absolute_falls_back_to_meta_folder(tmp_path):
    (tmp_path / ".thumbs").mkdir()
    (tmp_path / ".thumbs" / "a.jpg").write_bytes(b"x")
    stale = str(tmp_path.parent / "old_location" / ".thumbs" / "a.jpg")

    found = resolve_thumbnail(tmp_path / "a.json", {"thumbnailPath": stale})

    assert found == tmp_path / ".thumbs" / "a.jpg"


def test_resolve_thumbnail_absolute_outside_clip_folder_is_kept(tmp_path):
    custom = tmp_path / "custom" / "a.jpg"
    custom.parent.mkdir()
    custom.write_bytes(b"x")

    found = resolve_thumbnail(tmp_path / "clips" / "a.json", {"thumbnailPath": str(custom)})

    assert found == custom


def test_resolve_thumbnail_none_when_not_recorded(tmp_path):
    assert resolve_thumbnail(tmp_path / "a.json", {}) is None


def test_resolve_result_image_for_trashed_clip_uses_clips_root(tmp_path):
    (tmp_path / ".thumbs").mkdir()
    (tmp_path / ".thumbs" / "r_result.jpg").write_bytes(b"x")
    (tmp_path / ".trash").mkdir()

    found = resolve_result_image(
        tmp_path / ".trash" / "a.json", {"matchResult": {"imagePath": ".thumbs/r_result.jpg"}}
    )

    assert found == tmp_path / ".thumbs" / "r_result.jpg"


def test_resolve_result_image_stale_absolute_falls_back(tmp_path):
    (tmp_path / ".thumbs").mkdir()
    (tmp_path / ".thumbs" / "r_result.jpg").write_bytes(b"x")

    found = resolve_result_image(
        tmp_path / "a.json", {"matchResult": {"imagePath": str(Path("Z:/gone/.thumbs/r_result.jpg"))}}
    )

    assert found == tmp_path / ".thumbs" / "r_result.jpg"
