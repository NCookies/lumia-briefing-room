from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room import paths

_BUILTIN_DIR = Path(__file__).parent / "builtin"

_MEASURED_RESOLUTIONS: tuple[tuple[int, int], ...] = ((2560, 1440),)

# 코발트 프로토콜용 ROI 는 해상도마다 따로 실측한다(스트리머 VOD·사용자 자신의 스팀
# 녹화가 화면 배치가 서로 다르다는 게 실측으로 확인됨, plan.md §10-8·§10-11) - 다른
# 해상도의 `reference_rois`(정규화 기준)로 절대 안 빌려줘야 한다. 안 그러면 2560x1440
# 에 이 키를 추가하는 순간 `normalizedTo: [2560,1440]` 인 1920x1080 프로필이 자신의
# 네이티브 코발트 크롭을 이 키 이름이 같다는 이유만으로 엉뚱하게 확대해 버린다
# (2026-09-28 실사용 작업 중 발견 - 회귀 테스트로 고정).
_RESOLUTION_NATIVE_ONLY_ROIS = frozenset({
    "phase_digit", "cobalt_outcome", "cobalt_result_panel",
    "cobalt_teammate1", "cobalt_teammate2", "cobalt_teammate3",
    "cobalt_tk_value", "cobalt_k_value", "cobalt_a_value",
    "cobalt_face", "cobalt_minimap_icons",
})


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


def measured_resolutions() -> tuple[tuple[int, int], ...]:
    found = []
    for path in sorted(_BUILTIN_DIR.glob("*.json")):
        width, _, height = path.stem.partition("x")
        if width.isdigit() and height.isdigit():
            found.append((int(width), int(height)))
    return tuple(found)


def _template_path(kind: str, label: str, width: int, height: int) -> Path | None:
    path = paths.templates_dir(kind) / f"{width}x{height}.npz"
    if path.exists():
        return path
    paths.warn_missing(label, path)
    return None


def _templates_path(width: int, height: int) -> Path | None:
    return _template_path("digits", "K/A 숫자 본보기", width, height)


def _region_templates_path(width: int, height: int) -> Path | None:
    return _template_path("regions", "지역명 본보기", width, height)


def _day_templates_path(width: int, height: int) -> Path | None:
    return _template_path("days", "일차 본보기", width, height)


def _phase_templates_path(width: int, height: int) -> Path | None:
    return _template_path("phase", "코발트 페이즈 본보기", width, height)


def _cobalt_outcome_templates_path(width: int, height: int) -> Path | None:
    return _template_path("cobalt_outcome", "코발트 승패 본보기", width, height)


@dataclass(frozen=True)
class ResolutionProfile:
    width: int
    height: int
    rois: dict[str, Roi]
    measured: bool
    templates: Path | None = None
    region_templates: Path | None = None
    day_templates: Path | None = None
    phase_templates: Path | None = None
    cobalt_outcome_templates: Path | None = None
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
            reference_rois = {
                name: roi
                for name, roi in _load_builtin(ref_w, ref_h)[0].items()
                if name not in _RESOLUTION_NATIVE_ONLY_ROIS
            }
        return cls(
            width=width,
            height=height,
            rois=rois,
            measured=True,
            templates=_templates_path(ref_w, ref_h),
            region_templates=_region_templates_path(ref_w, ref_h),
            day_templates=_day_templates_path(ref_w, ref_h),
            # 코발트는 기준 해상도(2560x1440) 녹화가 없어 정규화하지 않는다 — 이 프로필
            # 자신의 해상도로 본보기를 찾는다(plan.md §10-1).
            phase_templates=_phase_templates_path(width, height),
            cobalt_outcome_templates=_cobalt_outcome_templates_path(width, height),
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
