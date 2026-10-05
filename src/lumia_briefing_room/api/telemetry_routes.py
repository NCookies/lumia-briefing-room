"""전송 상태·미리보기·삭제 요청과 개인정보 처리 안내 API. (plan-deploy.md D10)

미리보기와 삭제 요청은 사용자가 직접 누르는 동작이라 전송 동의(`telemetry.sendLabels`/`sendLogs`)와 무관하게 동작한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room import paths
from lumia_briefing_room.telemetry import runtime_stats
from lumia_briefing_room.telemetry.sender import TelemetrySender


playback_log = logging.getLogger("lumia_briefing_room.playback")
_reported_playback: set[tuple[str, str]] = set()
_PLAYBACK_KINDS = {"fullvideo": "풀영상"}


def privacy_path() -> Path:
    return paths.resource_dir() / "docs" / "privacy.md"


def register_telemetry_routes(app: FastAPI) -> None:
    def sender() -> TelemetrySender:
        injected = getattr(app.state, "telemetry_sender", None)
        return injected or TelemetrySender(config_path=app.state.config_path)

    @app.get("/api/telemetry/status")
    def get_status():
        return sender().status()

    @app.get("/api/telemetry/preview")
    def get_preview():
        return sender().preview()

    @app.post("/api/telemetry/delete")
    def delete_sent_data():
        result = sender().delete_remote()
        if result["ok"]:
            return result
        if result["reason"] == "no-endpoint":
            raise HTTPException(503, "이 빌드에는 서버 연결 정보가 없어 삭제 요청을 보낼 수 없습니다")
        if result["reason"] == "network":
            raise HTTPException(502, "서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 다시 시도해 주세요")
        raise HTTPException(502, f"서버가 요청을 처리하지 못했습니다 (HTTP {result.get('httpStatus')})")

    zip_hint = " 그래도 안 되면 '진단 정보 zip 받기'로 파일을 저장해 보내 주세요."

    @app.get("/api/telemetry/diagnostics/preview")
    def get_diagnostics_preview():
        return sender().diagnostics_preview()

    @app.post("/api/telemetry/diagnostics/send")
    def send_diagnostics():
        result = sender().send_diagnostics()
        if result["ok"]:
            return result
        reason = result["reason"]
        if reason == "no-endpoint":
            raise HTTPException(503, "이 빌드에는 서버 연결 정보가 없어 보낼 수 없습니다." + zip_hint)
        if reason == "dev-blocked":
            raise HTTPException(409, "개발 모드에서는 서버로 보내지 않습니다." + zip_hint)
        if reason == "network":
            raise HTTPException(502, "서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 다시 시도해 주세요." + zip_hint)
        if reason == "rejected":
            raise HTTPException(502, f"서버가 이 내용을 받지 않았습니다 (HTTP {result.get('httpStatus')})." + zip_hint)
        raise HTTPException(502, f"서버가 요청을 처리하지 못했습니다 (HTTP {result.get('httpStatus')})." + zip_hint)

    @app.get("/api/privacy")
    def get_privacy():
        try:
            return {"markdown": privacy_path().read_text(encoding="utf-8")}
        except OSError:
            raise HTTPException(404, "개인정보 처리 안내를 찾을 수 없습니다")

    @app.post("/api/client-capabilities")
    def post_client_capabilities(body: dict):
        """브라우저만 아는 값(HEVC 재생 가능 여부)을 받아 환경 정보에 쓸 수 있게 기록한다. 서버로 보내는 것이 아니라 로컬 기록이다."""
        playable = body.get("hevcPlayable")
        if not isinstance(playable, bool):
            raise HTTPException(400, "hevcPlayable 은 true/false 여야 합니다")
        info = {k: body[k] for k in runtime_stats.BROWSER_FIELDS if k in body}
        if any(not isinstance(v, str) for v in info.values()):
            raise HTTPException(400, "browser·hevcProbe·browserGpu 는 문자열이어야 합니다")
        runtime_stats.record_hevc(playable)
        runtime_stats.record_browser(info)
        return {"ok": True}

    @app.post("/api/client-events/playback-failure")
    def post_playback_failure(body: dict):
        """브라우저가 영상을 못 그렸다는 보고(오류 없이 검게 나오는 경우 포함)를 오류 기록에 남긴다. 같은 내용은 앱을 켠 동안 한 번만."""
        kind, detail = body.get("kind"), body.get("detail")
        if kind not in _PLAYBACK_KINDS or not isinstance(detail, str) or not detail:
            raise HTTPException(400, "kind(fullvideo)와 detail 이 필요합니다")
        key = (kind, detail[:300])
        if key not in _reported_playback:
            _reported_playback.add(key)
            playback_log.error("브라우저가 %s 을 재생하지 못했다: %s", _PLAYBACK_KINDS[kind], key[1])
        return {"ok": True}
