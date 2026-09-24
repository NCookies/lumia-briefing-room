"""번들이 제대로 묶였는지 스스로 점검한다. (plan-deploy.md D5)

빌드본에는 콘솔이 없어서 "왜 판독이 안 되는지" 를 볼 방법이 없다. `--selftest` 가 이 점검을
돌려 보고서를 파일로 남긴다 — PyInstaller hook 누락(onnxruntime·rapidocr 모델·opencv)이
조용한 기능 저하로 숨지 않게 하는 장치다.
"""

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lumia_briefing_room import __version__, paths
from lumia_briefing_room.config import discover_ffmpeg
from lumia_briefing_room.pipeline.proxy import PREFERRED_ENCODERS, list_encoders
from lumia_briefing_room.video.vod import find_ffprobe

MEASURED_SIZE = (2560, 1440)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def check_environment() -> list[Check]:
    mode = "배포(빌드본)" if paths.is_frozen() else "개발(소스 트리)"
    return [
        Check("실행 환경", True, f"버전 {__version__} · {mode} · {platform.platform()} · Python {sys.version.split()[0]}"),
        Check("리소스 폴더", paths.resource_dir().is_dir(), str(paths.resource_dir())),
    ]


def _file_check(name: str, path: Path, *, hint: str = "") -> Check:
    if path.exists():
        return Check(name, True, f"{path} ({path.stat().st_size / 1024:.0f} KB)")
    return Check(name, False, f"없다: {path}{f' — {hint}' if hint else ''}")


def check_resources() -> list[Check]:
    width, height = MEASURED_SIZE
    npz = f"{width}x{height}.npz"
    dist = paths.frontend_dist_dir()
    return [
        _file_check("캐릭터 이름표", paths.characters_path()),
        _file_check("K/A 숫자 본보기", paths.templates_dir("digits") / npz),
        _file_check("지역명 본보기", paths.templates_dir("regions") / npz),
        _file_check("일차 본보기", paths.templates_dir("days") / npz),
        _file_check("열람 UI (frontend/dist)", dist / "index.html", hint="npm run build 가 빠졌다"),
    ]


def check_tools() -> list[Check]:
    ffmpeg = discover_ffmpeg()
    ffprobe = find_ffprobe(ffmpeg) if ffmpeg else None
    checks = [
        Check("ffmpeg", ffmpeg is not None, str(ffmpeg) if ffmpeg else "찾을 수 없다 (번들·PATH 모두 없음)"),
        Check("ffprobe", ffprobe is not None, str(ffprobe) if ffprobe else "찾을 수 없다"),
    ]

    if ffmpeg is None:
        checks.append(Check("H.264 프록시 인코더", False, "ffmpeg 가 없어 확인하지 못했다"))
        return checks

    try:
        usable = [name for name in PREFERRED_ENCODERS if name in list_encoders(ffmpeg)]
    except Exception as exc:
        checks.append(Check("H.264 프록시 인코더", False, f"확인 실패: {exc}"))
        return checks

    detail = ", ".join(usable) if usable else f"{'·'.join(PREFERRED_ENCODERS)} 중 아무것도 없다"
    checks.append(Check("H.264 프록시 인코더", bool(usable), detail))
    return checks


def check_ocr() -> list[Check]:
    """엔진을 실제로 만들어 본다 — 모델 파일이나 onnxruntime 이 빠지면 여기서 드러난다."""
    try:
        from lumia_briefing_room.detect.ocr import OcrReader

        reader = OcrReader()
        blank = np.full((64, 256, 3), 255, dtype=np.uint8)
        lines = reader.read(blank, lang="korean")
    except Exception as exc:
        return [Check("결과 화면 OCR", False, f"{type(exc).__name__}: {exc}")]
    return [Check("결과 화면 OCR", True, f"엔진을 불러왔다 (빈 이미지에서 {len(lines)}줄)")]


def check_telemetry() -> list[Check]:
    """전송 기능이 빌드본에서 동작할 수 있는지 — httpx·인증서 번들·개인정보 안내 파일이 빠지면 여기서 드러난다."""
    checks = []
    try:
        import httpx

        from lumia_briefing_room.telemetry.client import Endpoint, ReceiverClient

        httpx.create_ssl_context()
        client = ReceiverClient(Endpoint("https://selftest.invalid", "x"), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
        checks.append(Check("전송 클라이언트(httpx·인증서)", client.post("/v1/logs", {}).outcome == "ok", f"httpx {httpx.__version__}"))
    except Exception as exc:
        checks.append(Check("전송 클라이언트(httpx·인증서)", False, f"{type(exc).__name__}: {exc}"))
    checks.append(_file_check("개인정보 처리 안내", paths.resource_dir() / "docs" / "privacy.md"))
    from lumia_briefing_room.telemetry.endpoint import bundled_endpoint

    has_token = bool(bundled_endpoint().get("token"))
    checks.append(Check("서버 연결 정보", True, "토큰이 들어 있다" if has_token else "토큰이 없다 — 이 빌드는 서버 전송이 꺼져 있다"))
    return checks


def run_all() -> tuple[list[Check], bool]:
    results = [*check_environment(), *check_resources(), *check_tools(), *check_ocr(), *check_telemetry()]
    return results, all(r.ok for r in results)


def format_report(results: list[Check], *, header: str) -> str:
    lines = [header, "=" * len(header), ""]
    for result in results:
        lines.append(f"[{' OK ' if result.ok else '실패'}] {result.name}")
        if result.detail:
            lines.append(f"        {result.detail}")
    failed = [r for r in results if not r.ok]
    lines += ["", f"{len(failed)}개 실패" if failed else "모두 통과"]
    return "\n".join(lines)
