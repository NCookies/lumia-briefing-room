from datetime import datetime, timezone

import numpy as np
from PIL import Image

from lumia_briefing_room.pipeline.result_scan import result_image_name, save_result_image


def test_result_image_name_is_per_match_start():
    assert result_image_name(datetime(2026, 9, 20, 13, 48, 9, tzinfo=timezone.utc)) == "20260920_134809_result.jpg"


def test_save_result_image_writes_downscaled_jpeg_and_creates_folder(tmp_path):
    frame = np.full((1440, 2560, 3), 90, dtype=np.uint8)
    path = tmp_path / "nested" / "r.jpg"

    save_result_image(frame, path)

    with Image.open(path) as img:
        assert img.format == "JPEG"
        assert img.size == (1280, 720)
