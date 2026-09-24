import hmac
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .schemas import LabelBatch, LogBatch
from .storage import FileStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = FileStore(settings.data_dir)
    app = FastAPI(title="receiver", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_body_bytes:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        return await call_next(request)

    def require_token(x_api_token: str = Header(default="")) -> None:
        if not settings.api_token or not hmac.compare_digest(x_api_token, settings.api_token):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/v1/labels", dependencies=[Depends(require_token)])
    def post_labels(batch: LabelBatch):
        saved = store.save_labels(
            batch.installId, batch.appVersion, [l.model_dump(exclude_none=True) for l in batch.labels]
        )
        return {"saved": saved}

    @app.post("/v1/logs", dependencies=[Depends(require_token)])
    def post_logs(batch: LogBatch):
        store.append_log(
            batch.installId,
            {"env": batch.env.model_dump(), "entries": [e.model_dump() for e in batch.entries]},
        )
        return {"saved": len(batch.entries)}

    @app.delete("/v1/installs/{install_id}", dependencies=[Depends(require_token)])
    def delete_install(install_id: UUID):
        return {"deleted": store.delete_install(install_id)}

    return app
