from pathlib import Path

from PIL import Image

from lumia_briefing_room import icon


def test_icon_image_is_square_rgba_of_requested_size():
    img = icon.app_icon_image(48)
    assert img.size == (48, 48)
    assert img.mode == "RGBA"


def test_icon_has_transparent_corners_and_a_filled_middle():
    img = icon.app_icon_image(64)
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((32, 32))[3] == 255


def test_icon_draws_a_light_play_mark_on_a_dark_field():
    img = icon.app_icon_image(64)
    mark = img.getpixel((30, 32))
    field = img.getpixel((12, 32))
    assert sum(mark[:3]) > sum(field[:3])


def test_save_ico_writes_a_multi_size_windows_icon(tmp_path: Path):
    out = tmp_path / "app.ico"
    icon.save_ico(out)

    assert out.exists() and out.stat().st_size > 0
    with Image.open(out) as opened:
        assert opened.format == "ICO"
        assert {16, 32, 48, 256} <= {size[0] for size in opened.info["sizes"]}


def test_save_ico_creates_missing_parent_directories(tmp_path: Path):
    out = tmp_path / "build" / "icons" / "app.ico"
    icon.save_ico(out)
    assert out.exists()


def test_tray_uses_the_same_icon():
    from lumia_briefing_room import tray

    assert tray.default_icon_image(32) == icon.app_icon_image(32)
