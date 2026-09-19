from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_BUILTIN_DIR = Path(__file__).parent / "builtin"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates" / "digits"

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


def _load_builtin_rois(width: int, height: int) -> dict[str, Roi] | None:
    path = _BUILTIN_DIR / f"{width}x{height}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: Roi(*coords) for name, coords in data["rois"].items()}


def _templates_path(width: int, height: int) -> Path | None:
    path = _TEMPLATES_DIR / f"{width}x{height}.npz"
    return path if path.exists() else None


@dataclass(frozen=True)
class ResolutionProfile:
    width: int
    height: int
    rois: dict[str, Roi]
    measured: bool
    templates: Path | None = None

    @classmethod
    def builtin(cls, width: int, height: int) -> "ResolutionProfile":
        rois = _load_builtin_rois(width, height)
        if rois is None:
            raise ValueError(f"측정된 프로필이 없다: {width}x{height}")
        return cls(
            width=width,
            height=height,
            rois=rois,
            measured=True,
            templates=_templates_path(width, height),
        )

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
