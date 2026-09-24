"""전송 상태·미리보기·삭제 요청과 개인정보 처리 안내 API. (plan-deploy.md D10)

미리보기와 삭제 요청은 사용자가 직접 누르는 동작이라 전송 동의(`telemetry.sendLabels`/`sendLogs`)와 무관하게 동작한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room import paths
from lumia_briefing_room.telemetry import runtime_stats
from lumia_briefing_room.telemetry.sender import TelemetrySender


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
        runtime_stats.record_hevc(playable)
        return {"ok": True}
