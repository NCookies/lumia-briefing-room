"""서버 주소와 API 토큰을 어디서 가져오는지. 저장소가 공개되므로 토큰은 git 에 없고 빌드 때 번들에 들어간다. (docs/roadmap.md §4-2)

우선순위: 설정(`telemetry.apiToken`·`serverUrl`, 개발·시험용) → 환경변수(`LUMIA_RECEIVER_TOKEN`·`LUMIA_RECEIVER_URL`)
→ 번들 파일(`data/telemetry_endpoint.json`, tools/build_release.py 가 환경변수에서 만든다). 서버 주소도 코드에 없다(공개 저장소). 토큰이나 주소 중 하나라도 없으면 전송 기능은 꺼진 것과 같다.
"""

from __future__ import annotations

import json
import os

from lumia_briefing_room import paths
from lumia_briefing_room.telemetry.client import Endpoint

ENDPOINT_FILE = "telemetry_endpoint.json"
TOKEN_ENV = "LUMIA_RECEIVER_TOKEN"
URL_ENV = "LUMIA_RECEIVER_URL"


def bundled_endpoint() -> dict:
    try:
        data = json.loads((paths.data_dir() / ENDPOINT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_endpoint(cfg, environ=None) -> Endpoint | None:
    environ = os.environ if environ is None else environ
    bundled = bundled_endpoint()
    token = cfg.telemetry.api_token or environ.get(TOKEN_ENV) or bundled.get("token")
    url = cfg.telemetry.server_url or environ.get(URL_ENV) or bundled.get("url")
    if not isinstance(token, str) or not token.strip() or not isinstance(url, str) or not url.strip():
        return None
    return Endpoint(url=url.strip().rstrip("/"), token=token.strip())
