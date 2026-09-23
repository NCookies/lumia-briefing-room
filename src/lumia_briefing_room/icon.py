"""앱 아이콘 한 벌. 트레이·exe·설치기가 모두 여기서 나온다. (plan-deploy.md D5)

그림으로 그려 두면 저장소에 바이너리를 넣지 않아도 되고, 트레이와 exe 아이콘이 어긋나지 않는다.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FIELD_COLOR = (32, 58, 104, 255)
RING_COLOR = (90, 140, 255, 255)
MARK_COLOR = (226, 238, 255, 255)


def app_icon_image(size: int = 256) -> Image.Image:
    """파란 원판 위의 재생 삼각형. 16px 로 줄여도 형태가 남도록 단순하게 그린다."""
    scale = 8 if size < 64 else 2
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = big * 0.02
    draw.ellipse((pad, pad, big - pad, big - pad), fill=RING_COLOR)
    inner = big * 0.12
    draw.ellipse((inner, inner, big - inner, big - inner), fill=FIELD_COLOR)

    left, right = big * 0.40, big * 0.72
    top, bottom = big * 0.28, big * 0.72
    draw.polygon([(left, top), (right, big / 2), (left, bottom)], fill=MARK_COLOR)

    return img.resize((size, size), Image.LANCZOS)


def save_ico(path: Path, sizes: tuple[int, ...] = ICO_SIZES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    largest = app_icon_image(max(sizes))
    largest.save(path, format="ICO", sizes=[(s, s) for s in sizes])
    return path
