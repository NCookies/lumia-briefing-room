"""E2E 용 서버 실행기: 브라우저·pywebview 를 열지 않고 API + frontend/dist 만 띄운다.

usage: python e2e/run_server.py --config <config.json> --port <port>
환경변수(LOCALAPPDATA·APPDATA·USERPROFILE)는 호출하는 쪽(e2e/world.py)이 임시 폴더로 바꿔 준다.
"""

import argparse
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.cli.serve import build_app  # noqa: E402
from lumia_briefing_room.config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    app = build_app(load_config(args.config), config_path=args.config)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", log_config=None)


if __name__ == "__main__":
    main()
