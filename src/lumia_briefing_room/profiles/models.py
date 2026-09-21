from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_BUILTIN_DIR = Path(__file__).parent / "builtin"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates" / "digits"
_REGION_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates" / "regions"
_DAY_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates" / "days"

_MEASURED_RESOLUTIONS: tuple[tuple[int, int], ...] = ((2560, 1440),)


@dataclass(frozen=True)
class Roi:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def scaled(self, sx: float, sy: float) -> "Roi":
        return Roi(
            x0=round(self.x0 * sx),
            y0=round(self.y0 * sy),
            x1=round(self.x1 * sx),
            y1=round(self.y1 * sy),
        )


def _load_builtin(width: int, height: int) -> tuple[dict[str, Roi], tuple[int, int] | None] | None:
    path = _BUILTIN_DIR / f"{width}x{height}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    rois = {name: Roi(*coords) for name, coords in data["rois"].items()}
    normalized_to = data.get("normalizedTo")
    return rois, tuple(normalized_to) if normalized_to else None


def _templates_path(width: int, height: int) -> Path | None:
    path = _TEMPLATES_DIR / f"{width}x{height}.npz"
    return path if path.exists() else None


def _region_templates_path(width: int, height: int) -> Path | None:
    path = _REGION_TEMPLATES_DIR / f"{width}x{height}.npz"
    return path if path.exists() else None


def _day_templates_path(width: int, height: int) -> Path | None:
    path = _DAY_TEMPLATES_DIR / f"{width}x{height}.npz"
    return path if path.exists() else None


@dataclass(frozen=True)
class ResolutionProfile:
    width: int
    height: int
    rois: dict[str, Roi]
    measured: bool
    templates: Path | None = None
    region_templates: Path | None = None
    day_templates: Path | None = None
    reference_rois: dict[str, Roi] | None = None

    @classmethod
    def builtin(cls, width: int, height: int) -> "ResolutionProfile":
        loaded = _load_builtin(width, height)
        if loaded is None:
            raise ValueError(f"측정된 프로필이 없다: {width}x{height}")
        rois, normalized_to = loaded
        ref_w, ref_h = normalized_to or (width, height)
        reference_rois = None
        if normalized_to:
            reference_rois = _load_builtin(ref_w, ref_h)[0]
        return cls(
            width=width,
            height=height,
            rois=rois,
            measured=True,
            templates=_templates_path(ref_w, ref_h),
            region_templates=_region_templates_path(ref_w, ref_h),
            day_templates=_day_templates_path(ref_w, ref_h),
            reference_rois=reference_rois,
        )

    def crop(self, frame, name: str):
        """ROI 조각을 잘라낸다. 기준 해상도로 정규화되는 프로필이면 기준 ROI 크기로 키워, 기준 해상도의 본보기·픽셀 임계를 그대로 쓰게 한다."""
        roi = self.rois[name]
        piece = frame[roi.y0 : roi.y1, roi.x0 : roi.x1]
        ref = self.reference_rois.get(name) if self.reference_rois else None
        if ref is None or piece.shape[:2] == (ref.height, ref.width):
            return piece
        import cv2

        return cv2.resize(piece, (ref.width, ref.height), interpolation=cv2.INTER_CUBIC)

    @classmethod
    def for_resolution(cls, width: int, height: int) -> "ResolutionProfile":
        try:
            return cls.builtin(width, height)
        except ValueError:
            pass
        base_w, base_h = _MEASURED_RESOLUTIONS[0]
        base = cls.builtin(base_w, base_h)
        sx, sy = width / base_w, height / base_h
        rois = {name: roi.scaled(sx, sy) for name, roi in base.rois.items()}
        return cls(width=width, height=height, rois=rois, measured=False, templates=None)
